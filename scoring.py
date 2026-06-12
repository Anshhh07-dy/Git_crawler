"""
Resource quality scoring.

Three sub-scores (authority, freshness, popularity) combine into an
overall quality_score. Signals come from whatever's available:
 - GitHub repos: stars, forks, last push date -> popularity & freshness
 - Any page: domain reputation list -> authority
 - Everything: classification confidence contributes a small factor
"""
from datetime import datetime, timezone
from urllib.parse import urlparse

# A small curated list of high-authority domains for this problem space.
# Real deployments would maintain this as a DB table, scored via backlink
# graphs or a domain-rank API.
HIGH_AUTHORITY_DOMAINS = {
    "github.com": 0.85,
    "arxiv.org": 0.95,
    "doi.org": 0.95,
    "openalex.org": 0.9,
    "docs.openalex.org": 0.9,
    "huggingface.co": 0.88,
    "kaggle.com": 0.85,
    "zenodo.org": 0.9,
    "ieee.org": 0.92,
    "acm.org": 0.92,
    "nature.com": 0.95,
    "nih.gov": 0.93,
    "ed.gov": 0.9,
    "europa.eu": 0.88,
    ".edu": 0.85,  # suffix match
    ".gov": 0.88,
    ".ac.uk": 0.85,
}

DEFAULT_AUTHORITY = 0.45


def authority_score(url: str) -> float:
    host = urlparse(url).netloc.lower().replace("www.", "")

    if host in HIGH_AUTHORITY_DOMAINS:
        return HIGH_AUTHORITY_DOMAINS[host]

    for suffix, score in HIGH_AUTHORITY_DOMAINS.items():
        if suffix.startswith(".") and host.endswith(suffix):
            return score

    return DEFAULT_AUTHORITY


def freshness_score(last_modified_iso: str | None, decay_days: int = 730) -> float:
    """Linear decay from 1.0 (today) to 0.0 (decay_days ago or older). Unknown -> neutral 0.5."""
    if not last_modified_iso:
        return 0.5
    try:
        dt = datetime.fromisoformat(last_modified_iso.replace("Z", "+00:00"))
    except ValueError:
        return 0.5

    now = datetime.now(timezone.utc)
    age_days = (now - dt).days
    if age_days < 0:
        return 1.0
    return max(0.0, 1.0 - (age_days / decay_days))


def popularity_score(stars: int = 0, forks: int = 0, signal_cap: int = 5000) -> float:
    """Log-ish normalization so a repo with 50k stars doesn't dwarf everything to 1.0 vs 0."""
    import math
    raw = stars + forks * 2
    if raw <= 0:
        return 0.3  # neutral-low baseline for pages with no popularity signal
    normalized = math.log10(raw + 1) / math.log10(signal_cap + 1)
    return min(1.0, normalized)


def compute_quality_score(
    url: str,
    classification_confidence: float,
    stars: int = 0,
    forks: int = 0,
    last_modified_iso: str | None = None,
) -> dict:
    auth = authority_score(url)
    fresh = freshness_score(last_modified_iso)
    pop = popularity_score(stars, forks)

    weights = {"authority": 0.35, "freshness": 0.2, "popularity": 0.3, "confidence": 0.15}

    overall = (
        auth * weights["authority"]
        + fresh * weights["freshness"]
        + pop * weights["popularity"]
        + classification_confidence * weights["confidence"]
    )

    return {
        "quality_score": round(overall, 3),
        "authority_score": round(auth, 3),
        "freshness_score": round(fresh, 3),
        "popularity_score": round(pop, 3),
    }
