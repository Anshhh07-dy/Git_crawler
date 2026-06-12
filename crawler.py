"""
Crawler orchestration.

This is the heart of the pipeline:

  seed URL -> link extraction -> recursive BFS crawl -> content parsing
  -> classification -> scoring -> dedup -> storage -> (final) graph build

Runs as a background asyncio task per job (started via FastAPI
BackgroundTasks). Designed for a local/demo scale (tens to low-hundreds
of pages, max_depth 1-3) — for production scale, this loop becomes a
Celery task per page as described in the architecture doc, with the
frontier living in Redis instead of an in-process queue.

Concurrency design note:
  SQLAlchemy Sessions are NOT safe to share across concurrently-running
  coroutines. So this module splits each unit of work into:
    1. an async, I/O-bound "gather" phase (HTTP fetches + classification)
       that runs CONCURRENCY tasks in parallel with NO db access, and
    2. a sequential "apply" phase that takes the gathered results and
       performs all DB writes (page/resource/log rows) on a single
       Session, one item at a time.
  This keeps the speedup from concurrent network I/O while avoiding any
  shared-session corruption — safe on SQLite and Postgres alike.
"""
import asyncio
from collections import deque
from datetime import datetime

from sqlalchemy.orm import Session

from app.core.db import SessionLocal, CrawlJob, CrawlLogEntry, Page, Resource, new_id
from app.core.links import (
    extract_links_from_html, extract_links_from_markdown, normalize_url,
    is_crawlable_url, is_low_value_domain, is_github_repo_url, domain_of,
)
from app.core.fetcher import fetch_page
from app.core.github_client import fetch_repo_metadata, fetch_readme, fetch_repo_topics_text
from app.core.classifier import classify_page
from app.core.scoring import compute_quality_score
from app.core.dedup import find_duplicate
from app.core.graph import build_relations

# Per-job hard caps so a single crawl can't run forever
DEFAULT_MAX_DEPTH = 2
DEFAULT_MAX_PAGES = 60
CONCURRENCY = 5


def _log(db: Session, job_id: str, depth: int, status: str, url: str, note: str = ""):
    entry = CrawlLogEntry(id=new_id(), job_id=job_id, depth=depth, status=status, url=url, note=note)
    db.add(entry)
    db.commit()


async def run_crawl_job(job_id: str):
    """Entry point — runs the full pipeline for a job, updating its status as it goes."""
    db = SessionLocal()
    try:
        job = db.query(CrawlJob).filter(CrawlJob.id == job_id).first()
        if not job:
            return

        job.status = "running"
        db.commit()

        seed = normalize_url(job.seed_url)
        max_depth = job.max_depth or DEFAULT_MAX_DEPTH
        max_pages = job.max_pages or DEFAULT_MAX_PAGES

        visited: set[str] = set()
        queue: deque[tuple[str, int, str | None]] = deque()
        queue.append((seed, 0, None))

        _log(db, job_id, 0, "seed", seed, "Crawl started")

        while queue and len(visited) < max_pages:
            batch: list[tuple[str, int, str | None]] = []
            while queue and len(batch) < CONCURRENCY and len(visited) + len(batch) < max_pages:
                url, depth, parent = queue.popleft()
                if url in visited:
                    continue
                visited.add(url)
                batch.append((url, depth, parent))

            if not batch:
                break

            # Phase 1: concurrent I/O (fetch + classify), NO db access
            fetch_results = await asyncio.gather(
                *[_fetch_and_classify(url, depth) for url, depth, _ in batch],
                return_exceptions=True,
            )

            # Phase 2: sequential DB writes
            for (url, depth, parent), result in zip(batch, fetch_results):
                if isinstance(result, Exception):
                    _log(db, job_id, depth, "error", url, str(result)[:120])
                    continue

                child_links = _apply_result(db, job_id, url, depth, parent, result)

                if depth < max_depth:
                    for link in child_links:
                        if link not in visited and is_crawlable_url(link):
                            queue.append((link, depth + 1, url))

            job.pages_visited = len(visited)
            db.commit()

        relations_created = build_relations(db, job_id)

        job.status = "done"
        job.finished_at = datetime.utcnow()
        job.resources_found = (
            db.query(Resource).filter(Resource.job_id == job_id, Resource.is_duplicate == False).count()  # noqa: E712
        )
        job.duplicates_removed = (
            db.query(Resource).filter(Resource.job_id == job_id, Resource.is_duplicate == True).count()  # noqa: E712
        )
        db.commit()

        _log(db, job_id, 0, "done", seed,
             f"Finished: {job.pages_visited} pages, {job.resources_found} resources, "
             f"{job.duplicates_removed} duplicates, {relations_created} relations")

    except Exception as e:
        job = db.query(CrawlJob).filter(CrawlJob.id == job_id).first()
        if job:
            job.status = "failed"
            job.error = str(e)[:500]
            db.commit()
        _log(db, job_id, 0, "error", job.seed_url if job else "", f"Crawl failed: {e}")
    finally:
        db.close()


# ---------------------------------------------------------------------------
# Phase 1: pure async I/O — fetch + classify, NO database access.
# Returns a plain dict describing what was found, consumed by _apply_result.
# ---------------------------------------------------------------------------

async def _fetch_and_classify(url: str, depth: int) -> dict:
    is_repo, owner, repo = is_github_repo_url(url)

    if is_repo:
        return await _fetch_github_repo(url, owner, repo)

    if is_low_value_domain(url):
        return {"kind": "skip", "reason": "Low-value domain (social media)"}

    result = await fetch_page(url)

    if not result.success:
        return {"kind": "error", "reason": f"Fetch failed (status {result.status_code})"}

    if not result.text or len(result.text) < 50:
        return {"kind": "skip", "reason": "Empty or near-empty page"}

    classification = await classify_page(result.title or "", url, result.text)

    return {
        "kind": "web_page",
        "title": result.title,
        "text": result.text,
        "html": result.html,
        "content_hash": result.content_hash,
        "status_code": result.status_code,
        "classification": classification,
    }


async def _fetch_github_repo(url: str, owner: str, repo: str) -> dict:
    meta = await fetch_repo_metadata(owner, repo)
    if meta is None:
        return {"kind": "error", "reason": "GitHub API fetch failed (rate limit or not found)"}

    readme = await fetch_readme(owner, repo)
    topics_text = await fetch_repo_topics_text(meta)
    content = (readme or "") + "\n\n" + topics_text

    classification = await classify_page(meta["full_name"], url, content)

    child_links: list[str] = []
    if readme:
        for link_url, _link_text in extract_links_from_markdown(readme, url):
            child_links.append(link_url)
    if meta.get("homepage") and is_crawlable_url(meta["homepage"]):
        child_links.append(normalize_url(meta["homepage"]))

    return {
        "kind": "github_repo",
        "meta": meta,
        "content": content,
        "classification": classification,
        "child_links": child_links,
    }


# ---------------------------------------------------------------------------
# Phase 2: sequential DB writes. Single Session, called once per result.
# Returns the list of child links to enqueue.
# ---------------------------------------------------------------------------

def _apply_result(db: Session, job_id: str, url: str, depth: int, parent: str | None, result: dict) -> list[str]:
    kind = result["kind"]

    if kind == "skip":
        _log(db, job_id, depth, "skip", url, result["reason"])
        return []

    if kind == "error":
        _log(db, job_id, depth, "error", url, result["reason"])
        return []

    if kind == "github_repo":
        return _apply_github_repo(db, job_id, url, depth, parent, result)

    # kind == "web_page"
    page = Page(
        id=new_id(), job_id=job_id, url=url, title=result["title"],
        cleaned_content=(result["text"] or "")[:5000], content_hash=result["content_hash"],
        depth=depth, parent_url=parent, status_code=result["status_code"],
        source_type="web",
    )
    db.add(page)
    db.commit()

    classification = result["classification"]
    if classification.is_resource:
        _store_resource(db, job_id, page, url, classification, result["content_hash"])
        _log(db, job_id, depth, "found", url, f"{classification.category.value} — {classification.title[:60]}")
    else:
        _log(db, job_id, depth, "skip", url, "Not classified as a resource")

    return extract_links_from_html(result["html"], url) if result["html"] else []


def _apply_github_repo(db: Session, job_id: str, url: str, depth: int, parent: str | None, result: dict) -> list[str]:
    meta = result["meta"]
    classification = result["classification"]

    page = Page(
        id=new_id(), job_id=job_id, url=url, title=meta["full_name"],
        cleaned_content=result["content"][:8000], content_hash=None,
        depth=depth, parent_url=parent, status_code=200,
        source_type="github_repo",
    )
    db.add(page)
    db.commit()

    _store_resource(
        db, job_id, page, url, classification, None,
        stars=meta["stars"], forks=meta["forks"], last_modified=meta["pushed_at"],
        extra_meta={
            "stars": meta["stars"], "forks": meta["forks"],
            "language": meta["language"], "license": meta["license"],
            "topics": meta["topics"],
        },
        override_category_if_unknown="open_source_tool",
        description_override=meta["description"] or classification.description,
    )
    _log(db, job_id, depth, "found", url,
         f"GitHub repo — {meta['stars']}★ {meta['language'] or ''}".strip())

    return result["child_links"]


def _store_resource(
    db: Session, job_id: str, page: Page, url: str, classification, content_hash,
    stars: int = 0, forks: int = 0, last_modified: str | None = None,
    extra_meta: dict | None = None,
    override_category_if_unknown: str | None = None,
    description_override: str | None = None,
):
    category = classification.category
    if category.value == "unknown" and override_category_if_unknown:
        from app.core.db import ResourceCategory
        category = ResourceCategory(override_category_if_unknown)

    scores = compute_quality_score(
        url=url,
        classification_confidence=classification.confidence,
        stars=stars, forks=forks, last_modified_iso=last_modified,
    )

    candidate = {
        "url": url,
        "title": classification.title or page.title or url,
        "description": description_override or classification.description,
        "category": category,
        "content_hash": content_hash,
    }

    duplicate_of = find_duplicate(db, job_id, candidate)

    resource = Resource(
        id=new_id(), job_id=job_id, page_id=page.id,
        title=candidate["title"], description=candidate["description"],
        category=category, url=url, domain=domain_of(url),
        tags=classification.tags,
        extra={**(extra_meta or {}), "content_hash": content_hash},
        is_duplicate=duplicate_of is not None,
        duplicate_of=duplicate_of,
        **scores,
    )
    db.add(resource)
    db.commit()
