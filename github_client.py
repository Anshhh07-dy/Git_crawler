"""
GitHub API integration.

Why use the API instead of scraping github.com:
 - README content comes back as clean markdown (no HTML noise)
 - Stars/forks/last-push give real popularity & freshness signals for free
 - Avoids GitHub's aggressive scraping defenses entirely
 - Authenticated requests get 5000 req/hr vs 60 req/hr unauthenticated

Set GITHUB_TOKEN in the environment for the higher rate limit.
Works without a token too (lower limit, fine for small crawls/demos).
"""
import os
import base64
import httpx

GITHUB_API = "https://api.github.com"
GITHUB_TOKEN = os.environ.get("GITHUB_TOKEN", "").strip()

_HEADERS = {"Accept": "application/vnd.github+json", "User-Agent": "resource-discovery-engine"}
if GITHUB_TOKEN:
    _HEADERS["Authorization"] = f"Bearer {GITHUB_TOKEN}"


async def fetch_repo_metadata(owner: str, repo: str) -> dict | None:
    """Fetch repo-level metadata: stars, forks, description, last push, topics."""
    url = f"{GITHUB_API}/repos/{owner}/{repo}"
    async with httpx.AsyncClient(timeout=15) as client:
        resp = await client.get(url, headers=_HEADERS)
        if resp.status_code != 200:
            return None
        data = resp.json()
        return {
            "full_name": data.get("full_name"),
            "description": data.get("description") or "",
            "stars": data.get("stargazers_count", 0),
            "forks": data.get("forks_count", 0),
            "open_issues": data.get("open_issues_count", 0),
            "topics": data.get("topics", []),
            "pushed_at": data.get("pushed_at"),
            "homepage": data.get("homepage") or "",
            "html_url": data.get("html_url"),
            "default_branch": data.get("default_branch", "main"),
            "language": data.get("language"),
            "license": (data.get("license") or {}).get("spdx_id"),
        }


async def fetch_readme(owner: str, repo: str) -> str | None:
    """Fetch and decode the repo's README as markdown text."""
    url = f"{GITHUB_API}/repos/{owner}/{repo}/readme"
    async with httpx.AsyncClient(timeout=15) as client:
        resp = await client.get(url, headers=_HEADERS)
        if resp.status_code != 200:
            return None
        data = resp.json()
        content = data.get("content", "")
        if not content:
            return None
        try:
            return base64.b64decode(content).decode("utf-8", errors="replace")
        except Exception:
            return None


async def fetch_repo_topics_text(meta: dict) -> str:
    """Build a short text blob from repo metadata for classification context."""
    parts = [meta.get("full_name", ""), meta.get("description", "")]
    if meta.get("topics"):
        parts.append("Topics: " + ", ".join(meta["topics"]))
    if meta.get("language"):
        parts.append(f"Primary language: {meta['language']}")
    return "\n".join(p for p in parts if p)
