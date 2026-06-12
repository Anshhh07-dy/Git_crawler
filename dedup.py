"""
Deduplication.

Two layers, both dependency-free (no embeddings/vector DB needed for a
local run, but the structure mirrors how you'd slot in pgvector later):

  1. Exact: same normalized URL, or identical content hash (catches
     mirrors / copies with different URLs but byte-identical content).

  2. Near-duplicate: token-overlap similarity (Jaccard on title+description
     word sets) within the same category. Catches things like
     "OpenAlex API" vs "OpenAlex API Reference" pointing at slightly
     different URLs for the same underlying resource.

Upgrade path: replace `_text_similarity` with cosine similarity over
sentence-transformer embeddings stored in pgvector — same call signature.
"""
import re
from sqlalchemy.orm import Session

from app.core.db import Resource

_WORD_RE = re.compile(r"[a-z0-9]+")


def _tokenize(text: str) -> set[str]:
    return set(_WORD_RE.findall((text or "").lower()))


def _text_similarity(a: str, b: str) -> float:
    ta, tb = _tokenize(a), _tokenize(b)
    if not ta or not tb:
        return 0.0
    intersection = len(ta & tb)
    union = len(ta | tb)
    return intersection / union if union else 0.0


SIMILARITY_THRESHOLD = 0.6


def find_duplicate(db: Session, job_id: str, candidate: dict) -> str | None:
    """
    Returns the id of an existing Resource that `candidate` duplicates,
    or None if it's unique. `candidate` is a dict with url, title,
    description, category, content_hash.
    """
    # Layer 1a: exact URL match
    existing = (
        db.query(Resource)
        .filter(Resource.job_id == job_id, Resource.url == candidate["url"])
        .filter(Resource.is_duplicate == False)  # noqa: E712
        .first()
    )
    if existing:
        return existing.id

    # Layer 1b: exact content hash match (different URL, identical content).
    # Done in Python rather than a JSON-path SQL query so this works
    # identically on SQLite and Postgres.
    if candidate.get("content_hash"):
        job_resources = (
            db.query(Resource)
            .filter(Resource.job_id == job_id, Resource.is_duplicate == False)  # noqa: E712
            .all()
        )
        for existing in job_resources:
            if (existing.extra or {}).get("content_hash") == candidate["content_hash"]:
                return existing.id

    # Layer 2: near-duplicate via title+description token overlap,
    # restricted to same category to keep this cheap and meaningful
    same_category = (
        db.query(Resource)
        .filter(
            Resource.job_id == job_id,
            Resource.category == candidate["category"],
            Resource.is_duplicate == False,  # noqa: E712
        )
        .all()
    )

    candidate_text = f"{candidate['title']} {candidate.get('description', '')}"
    for existing in same_category:
        existing_text = f"{existing.title} {existing.description or ''}"
        if _text_similarity(candidate_text, existing_text) >= SIMILARITY_THRESHOLD:
            return existing.id

    return None
