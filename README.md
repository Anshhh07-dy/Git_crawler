# Resource Discovery & Intelligence Engine

A working local pipeline that takes any GitHub repo, docs site, awesome-list,
or general URL and recursively crawls, classifies, scores, deduplicates, and
indexes the resources hidden within it — with a live UI showing the crawl
trace, results, category breakdown, and derived knowledge graph.

## Run it

### Option A — Docker (recommended)

```bash
docker compose up --build
```

Open http://localhost:8000

### Option B — Direct (no Docker)

```bash
pip install -r requirements.txt
uvicorn app.main:app --reload
```

Open http://localhost:8000

## Optional environment variables

```bash
# Higher GitHub API rate limit (5000/hr vs 60/hr unauthenticated)
export GITHUB_TOKEN=ghp_xxxxx

# Enables LLM-assisted classification for ambiguous pages
# (heuristic classifier works fully without this — it's an upgrade, not a requirement)
export ANTHROPIC_API_KEY=sk-ant-xxxxx
```

With docker-compose, put these in a `.env` file in the project root:

```
GITHUB_TOKEN=ghp_xxxxx
ANTHROPIC_API_KEY=sk-ant-xxxxx
```

## How it works

```
Seed URL
  -> is it a GitHub repo? -> GitHub API: repo metadata + README (markdown links)
  -> otherwise            -> HTTP fetch + BeautifulSoup: HTML links + text content
  -> classify content (heuristic keyword rules, optional LLM fallback)
  -> score (authority / freshness / popularity / confidence)
  -> deduplicate (exact URL, content hash, near-duplicate title overlap)
  -> store as Resource
  -> recurse into discovered links (up to max_depth / max_pages)
  -> after crawl: derive knowledge graph edges (documents / links_to)
```

Try it with:
- `https://github.com/ourresearch/OpenAlex` — research API + docs + datasets
- `https://github.com/cheahjs/free-llm-api-resources` — awesome-list of APIs
- Any university scholarships page, docs portal, etc.

## Project structure

```
app/
  main.py            FastAPI app + all API endpoints
  core/
    db.py            SQLAlchemy models (SQLite by default)
    links.py         URL normalization, link/markdown extraction
    fetcher.py       HTTP fetch + content extraction (httpx + BeautifulSoup)
    github_client.py GitHub API client (repo metadata, README)
    classifier.py    Heuristic classification (+ optional LLM upgrade)
    scoring.py       Quality/authority/freshness/popularity scoring
    dedup.py         Exact + near-duplicate detection
    graph.py         Knowledge graph relation extraction
    crawler.py       Orchestrates the full recursive pipeline
  static/
    index.html       Frontend (React via CDN, no build step)
```

## API endpoints

| Method | Path | Description |
|---|---|---|
| POST | `/api/crawl-jobs` | Start a crawl (`{seed_url, max_depth, max_pages}`) |
| GET | `/api/crawl-jobs/{id}` | Job status + stats |
| GET | `/api/crawl-jobs/{id}/log` | Crawl trace log |
| GET | `/api/crawl-jobs/{id}/resources` | Resources found (filter by `category`, `q`, `min_score`) |
| GET | `/api/crawl-jobs/{id}/categories` | Category counts |
| GET | `/api/crawl-jobs/{id}/graph` | Knowledge graph edges |
| GET | `/api/search?q=...` | Search across all completed jobs |

## Scaling beyond local/demo use

This implementation favors a working single-process pipeline you can run
immediately. The original architecture (Celery + Redis + Postgres +
Meilisearch + Playwright/Crawl4AI) is the production path:

- **SQLite -> Postgres**: change `DATABASE_URL`; models are already portable
  (the one Postgres-specific JSON query was avoided on purpose).
- **In-process queue -> Redis + Celery**: `_fetch_and_classify` / `_apply_result`
  in `crawler.py` map directly to a Celery task per URL, with the frontier
  as a Redis set/list instead of an in-memory `deque`.
- **httpx fetcher -> Crawl4AI/Playwright**: swap `fetcher.fetch_page` for a
  headless-browser fetcher with the same `FetchResult` signature (see
  comment at the bottom of `fetcher.py`) to handle JS-rendered sites.
- **Heuristic classifier -> LLM-first**: `classifier.py` already supports
  this via `ANTHROPIC_API_KEY`; lower the confidence threshold to send more
  pages through the LLM.
- **Token-overlap dedup -> embeddings**: `dedup.py`'s `_text_similarity` is
  a drop-in replacement target for cosine similarity over embeddings stored
  in pgvector.
