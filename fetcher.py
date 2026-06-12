"""
General-purpose web fetcher.

Uses httpx for the request and BeautifulSoup for content extraction.
This handles the vast majority of documentation sites, university pages,
scholarship directories etc. — anything that returns meaningful HTML
without requiring JS execution.

A note on scope: full headless-browser crawling (Playwright/Crawl4AI) is
in the original architecture for JS-heavy SPAs. This fetcher is the
fast-path that covers most real sites; swapping in a Playwright-based
fetcher behind the same `fetch_page()` signature is a drop-in upgrade
(see comment at bottom of file).
"""
import hashlib
import httpx
from bs4 import BeautifulSoup

USER_AGENT = "ResourceDiscoveryEngine/0.1 (+https://github.com/your-org/resource-engine)"

# Tags whose text content is noise, not signal
STRIP_TAGS = ("script", "style", "noscript", "svg", "nav", "footer")


class FetchResult:
    def __init__(self, url, status_code, html=None, title=None, text=None, error=None):
        self.url = url
        self.status_code = status_code
        self.html = html
        self.title = title
        self.text = text
        self.error = error

    @property
    def success(self) -> bool:
        return self.error is None and self.status_code is not None and self.status_code < 400

    @property
    def content_hash(self) -> str | None:
        if not self.text:
            return None
        return hashlib.sha256(self.text.encode("utf-8")).hexdigest()


async def fetch_page(url: str, timeout: float = 12.0) -> FetchResult:
    """Fetch a URL and extract clean title + text content."""
    headers = {"User-Agent": USER_AGENT}
    try:
        async with httpx.AsyncClient(
            timeout=timeout, follow_redirects=True, headers=headers
        ) as client:
            resp = await client.get(url)
    except httpx.RequestError as e:
        return FetchResult(url, None, error=str(e))

    content_type = resp.headers.get("content-type", "")
    if "text/html" not in content_type and "application/xhtml" not in content_type:
        # Non-HTML resource (PDF, JSON API response, etc.) — record but don't parse as HTML
        return FetchResult(url, resp.status_code, html=None, title=None, text=None)

    html = resp.text
    soup = BeautifulSoup(html, "html.parser")

    for tag_name in STRIP_TAGS:
        for tag in soup.find_all(tag_name):
            tag.decompose()

    title = None
    if soup.title and soup.title.string:
        title = soup.title.string.strip()
    if not title:
        h1 = soup.find("h1")
        if h1:
            title = h1.get_text(strip=True)

    text = soup.get_text(separator=" ", strip=True)
    text = " ".join(text.split())  # collapse whitespace

    return FetchResult(url, resp.status_code, html=html, title=title, text=text)


# ---------------------------------------------------------------------------
# Upgrade path: to use Crawl4AI / Playwright for JS-rendered pages, implement
# an alternative fetcher with the same signature:
#
#   async def fetch_page_js(url: str, timeout: float = 12.0) -> FetchResult:
#       from crawl4ai import AsyncWebCrawler
#       async with AsyncWebCrawler(headless=True) as crawler:
#           result = await crawler.arun(url=url, bypass_cache=True)
#           return FetchResult(url, 200, html=result.html,
#                               title=result.metadata.get("title"),
#                               text=result.markdown)
#
# Then in crawler.py, try fetch_page() first and fall back to fetch_page_js()
# when `text` comes back empty/very short (a common signal of a JS-only SPA).
# ---------------------------------------------------------------------------
