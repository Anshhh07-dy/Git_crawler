"""
Resource classification.

Two modes:
  1. Heuristic (default, no API key needed) — keyword/pattern matching
     against title, URL, and content. Fast, free, deterministic, and
     surprisingly effective for this domain because resource pages use
     predictable vocabulary ("apply by", "stargazers", "syllabus", etc.)

  2. LLM-assisted (optional) — if ANTHROPIC_API_KEY or OPENAI_API_KEY is
     set, ambiguous pages (heuristic confidence below threshold) get a
     second pass through an LLM for classification + a clean summary.

This keeps the system fully functional offline / with no keys, while
giving a real quality upgrade when keys are available.
"""
import os
import re
from dataclasses import dataclass, field

from app.core.db import ResourceCategory

ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY", "").strip()
OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY", "").strip()


@dataclass
class Classification:
    is_resource: bool
    category: ResourceCategory
    confidence: float
    title: str
    description: str
    tags: list[str] = field(default_factory=list)


# Ordered: more specific categories first, so e.g. "scholarship" beats "course"
# when both terms appear.
KEYWORD_RULES: list[tuple[ResourceCategory, list[str], float]] = [
    (ResourceCategory.SCHOLARSHIP, [
        "scholarship", "scholarships", "tuition waiver", "merit award", "study grant",
    ], 0.85),
    (ResourceCategory.FELLOWSHIP, [
        "fellowship", "fellow program", "fellows program",
    ], 0.85),
    (ResourceCategory.INTERNSHIP, [
        "internship", "intern program", "summer intern", "apply for internship",
    ], 0.8),
    (ResourceCategory.GRANT, [
        "grant program", "research grant", "funding opportunity", "apply for grant",
        "seed grant",
    ], 0.8),
    (ResourceCategory.GOV_SCHEME, [
        "government scheme", "ministry of", "national portal", "gov.in", ".gov",
        "public sector scheme", "subsidy scheme",
    ], 0.75),
    (ResourceCategory.COMPETITION, [
        "hackathon", "competition", "challenge submission", "leaderboard", "kaggle",
    ], 0.8),
    (ResourceCategory.DATASET, [
        "dataset", "data snapshot", "download data", "csv download", "data dump",
        "corpus", ".jsonl", "bulk data",
    ], 0.8),
    (ResourceCategory.API, [
        "api reference", "api documentation", "rest api", "graphql api",
        "endpoint", "api key", "rate limit", "swagger", "openapi",
    ], 0.78),
    (ResourceCategory.DOCUMENTATION, [
        "documentation", "docs", "getting started", "user guide", "api reference",
        "schema reference", "developer guide",
    ], 0.6),  # lower confidence — overlaps heavily with API
    (ResourceCategory.RESEARCH_PAPER, [
        "arxiv", "doi.org", "abstract", "preprint", "conference paper",
        "journal of", "citation", "peer-reviewed",
    ], 0.75),
    (ResourceCategory.COURSE, [
        "syllabus", "course outline", "lecture notes", "enroll now", "certificate course",
        "moocs", "course catalog",
    ], 0.75),
    (ResourceCategory.LEARNING_RESOURCE, [
        "tutorial", "learn ", "guide to", "how to", "beginner's guide", "cheat sheet",
    ], 0.55),
    (ResourceCategory.COMMUNITY, [
        "discord", "slack community", "forum", "google groups", "mailing list",
        "subreddit", "community guidelines",
    ], 0.7),
    (ResourceCategory.STARTUP, [
        "startup directory", "yc batch", "y combinator", "seed-funded", "founders",
        "pitch deck",
    ], 0.7),
    (ResourceCategory.FUNDING, [
        "venture capital", "investment fund", "angel investors", "term sheet",
    ], 0.7),
    (ResourceCategory.OPEN_SOURCE_TOOL, [
        "github.com", "open source", "mit license", "npm install", "pip install",
        "build from source", "contributing.md",
    ], 0.6),
]

NON_RESOURCE_PATTERNS = [
    "404", "page not found", "login required", "sign in to continue",
    "access denied", "this page has been removed",
]


def _score_text(text: str) -> tuple[ResourceCategory, float]:
    lowered = text.lower()
    best_cat = ResourceCategory.UNKNOWN
    best_score = 0.0
    best_hits = 0

    for category, keywords, base_conf in KEYWORD_RULES:
        hits = sum(1 for kw in keywords if kw in lowered)
        if hits == 0:
            continue
        # more keyword hits -> higher confidence, capped at 0.97
        score = min(0.97, base_conf + 0.05 * (hits - 1))
        if score > best_score or (score == best_score and hits > best_hits):
            best_cat = category
            best_score = score
            best_hits = hits

    return best_cat, best_score


def _clean_description(text: str, max_len: int = 220) -> str:
    text = re.sub(r"\s+", " ", text).strip()
    if len(text) <= max_len:
        return text
    cut = text[:max_len]
    last_space = cut.rfind(" ")
    if last_space > max_len * 0.6:
        cut = cut[:last_space]
    return cut + "…"


def classify_heuristic(title: str, url: str, content: str) -> Classification:
    """Rule-based classification — always available, no external deps."""
    combined = " ".join([title or "", url or "", (content or "")[:3000]])
    lowered = combined.lower()

    if any(pat in lowered for pat in NON_RESOURCE_PATTERNS):
        return Classification(
            is_resource=False,
            category=ResourceCategory.UNKNOWN,
            confidence=0.9,
            title=title or url,
            description="",
            tags=[],
        )

    category, confidence = _score_text(combined)

    is_resource = confidence >= 0.5 and bool((content or "").strip())

    description = _clean_description(content or "") if content else ""
    clean_title = (title or url).strip()

    tags = _extract_tags(combined, category)

    return Classification(
        is_resource=is_resource,
        category=category,
        confidence=confidence,
        title=clean_title,
        description=description,
        tags=tags,
    )


TAG_VOCAB = [
    "python", "javascript", "typescript", "rust", "go", "java",
    "machine-learning", "deep-learning", "nlp", "computer-vision",
    "free", "open-source", "rest-api", "graphql", "no-auth-required",
    "jupyter", "tutorial", "beginner-friendly", "india", "remote",
    "fully-funded", "undergraduate", "graduate", "phd",
]


def _extract_tags(text: str, category: ResourceCategory, limit: int = 5) -> list[str]:
    lowered = text.lower()
    tags = []
    for t in TAG_VOCAB:
        variant = t.replace("-", " ")
        # word-boundary match to avoid e.g. "go" matching inside "Google"
        pattern = r"\b" + re.escape(variant) + r"\b"
        if re.search(pattern, lowered) or re.search(r"\b" + re.escape(t) + r"\b", lowered):
            tags.append(t)
    # always include the category as a tag-ish hint if nothing else found
    if not tags:
        tags = [category.value.replace("_", "-")]
    return tags[:limit]


# ---------------------------------------------------------------------------
# Optional LLM-assisted classification
# ---------------------------------------------------------------------------

LLM_PROMPT_TEMPLATE = """Classify this web page for a resource discovery engine.

Title: {title}
URL: {url}
Content excerpt: {content}

Respond with ONLY valid JSON (no markdown fences):
{{
  "is_resource": true or false,
  "category": "one of: research_paper, dataset, api, open_source_tool, scholarship, fellowship, internship, competition, grant, course, learning_resource, documentation, community, startup, funding, gov_scheme, unknown",
  "title": "cleaned short title",
  "description": "one sentence summary, max 30 words",
  "tags": ["3-5", "lowercase-hyphenated", "tags"]
}}"""


async def classify_with_llm(title: str, url: str, content: str) -> Classification | None:
    """
    Returns None if no LLM key is configured or the call fails —
    callers should fall back to classify_heuristic() in that case.
    """
    if not ANTHROPIC_API_KEY:
        return None

    import httpx
    import json as jsonlib

    prompt = LLM_PROMPT_TEMPLATE.format(
        title=title or "(no title)",
        url=url,
        content=(content or "")[:1500],
    )

    try:
        async with httpx.AsyncClient(timeout=20) as client:
            resp = await client.post(
                "https://api.anthropic.com/v1/messages",
                headers={
                    "x-api-key": ANTHROPIC_API_KEY,
                    "anthropic-version": "2023-06-01",
                    "content-type": "application/json",
                },
                json={
                    "model": "claude-sonnet-4-6",
                    "max_tokens": 400,
                    "messages": [{"role": "user", "content": prompt}],
                },
            )
        if resp.status_code != 200:
            return None

        data = resp.json()
        text_blocks = [b["text"] for b in data.get("content", []) if b.get("type") == "text"]
        raw = "".join(text_blocks).strip()
        raw = re.sub(r"^```json\s*|\s*```$", "", raw.strip())

        parsed = jsonlib.loads(raw)
        return Classification(
            is_resource=bool(parsed.get("is_resource", False)),
            category=ResourceCategory(parsed.get("category", "unknown")),
            confidence=0.9,
            title=parsed.get("title", title or url),
            description=parsed.get("description", ""),
            tags=parsed.get("tags", []),
        )
    except Exception:
        return None


async def classify_page(title: str, url: str, content: str, confidence_threshold: float = 0.65) -> Classification:
    """
    Main entry point. Always returns a heuristic result; upgrades to
    LLM classification for low-confidence pages if a key is available.
    """
    heuristic = classify_heuristic(title, url, content)

    if heuristic.confidence < confidence_threshold and ANTHROPIC_API_KEY:
        llm_result = await classify_with_llm(title, url, content)
        if llm_result is not None:
            return llm_result

    return heuristic
