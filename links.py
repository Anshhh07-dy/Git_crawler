"""
Link extraction and URL normalization.
Pure functions, no I/O — easy to unit test.
"""
import re
from urllib.parse import urljoin, urlparse, urlunparse, parse_qsl, urlencode

TRACKING_PARAMS = {
    "utm_source", "utm_medium", "utm_campaign", "utm_term", "utm_content",
    "ref", "fbclid", "gclid", "mc_cid", "mc_eid", "source",
}

SKIP_EXTENSIONS = (
    ".css", ".js", ".png", ".jpg", ".jpeg", ".gif", ".svg", ".ico",
    ".woff", ".woff2", ".ttf", ".eot", ".mp4", ".mp3", ".zip", ".gz",
    ".tar", ".exe", ".dmg", ".webp", ".avif",
)

SKIP_SCHEMES = ("javascript:", "mailto:", "tel:", "data:", "#")

# Domains that are almost never useful resource pages — deprioritized,
# logged as "skip" in the trace rather than crawled.
LOW_VALUE_DOMAINS = {
    "twitter.com", "x.com", "facebook.com", "instagram.com",
    "linkedin.com", "pinterest.com", "tiktok.com",
}


def normalize_url(url: str) -> str:
    """Strip fragments, tracking params, trailing slashes; lowercase host."""
    parsed = urlparse(url)
    netloc = parsed.netloc.lower()

    query_pairs = [
        (k, v) for k, v in parse_qsl(parsed.query)
        if k.lower() not in TRACKING_PARAMS
    ]
    query = urlencode(query_pairs)

    path = parsed.path
    if path.endswith("/") and path != "/":
        path = path[:-1]

    cleaned = urlunparse((parsed.scheme, netloc, path, parsed.params, query, ""))
    return cleaned


def is_crawlable_url(url: str, base_url: str | None = None) -> bool:
    """Filter out junk: assets, anchors, non-http schemes, etc."""
    lowered = url.lower().strip()

    if any(lowered.startswith(s) for s in SKIP_SCHEMES):
        return False

    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https"):
        return False

    if any(parsed.path.lower().endswith(ext) for ext in SKIP_EXTENSIONS):
        return False

    if not parsed.netloc:
        return False

    return True


def is_low_value_domain(url: str) -> bool:
    host = urlparse(url).netloc.lower().replace("www.", "")
    return any(host == d or host.endswith("." + d) for d in LOW_VALUE_DOMAINS)


def extract_links_from_html(html: str, base_url: str) -> list[str]:
    """Extract + normalize all <a href> links from an HTML document."""
    from bs4 import BeautifulSoup

    soup = BeautifulSoup(html, "html.parser")
    links: set[str] = set()
    normalized_base = normalize_url(base_url)

    for tag in soup.find_all("a", href=True):
        href = tag["href"].strip()
        if not href:
            continue
        # Pure same-page anchors (e.g. "#section") resolve to the page's own
        # URL once the fragment is stripped — exclude these self-links.
        if href.startswith("#"):
            continue
        absolute = urljoin(base_url, href)
        if not is_crawlable_url(absolute, base_url):
            continue
        normalized = normalize_url(absolute)
        if normalized == normalized_base:
            continue
        links.add(normalized)

    return sorted(links)


MARKDOWN_LINK_RE = re.compile(r"\[([^\]]*)\]\((https?://[^\s\)]+)\)")
BARE_URL_RE = re.compile(r"(?<![\(\[])(https?://[^\s\)\]\>\"']+)")


def extract_links_from_markdown(md: str, base_url: str | None = None) -> list[tuple[str, str]]:
    """
    Extract links from markdown (e.g. a GitHub README).
    Returns list of (link_text, url) tuples — link text is useful context
    for classification (e.g. "Awesome Vision APIs" tells us more than the bare URL).
    """
    found: dict[str, str] = {}

    for text, url in MARKDOWN_LINK_RE.findall(md):
        norm = normalize_url(url)
        if is_crawlable_url(norm):
            found[norm] = text.strip()

    for url in BARE_URL_RE.findall(md):
        norm = normalize_url(url)
        if is_crawlable_url(norm) and norm not in found:
            found[norm] = ""

    return [(url, text) for url, text in found.items()]


def domain_of(url: str) -> str:
    return urlparse(url).netloc.lower().replace("www.", "")


def is_github_repo_url(url: str) -> tuple[bool, str | None, str | None]:
    """
    Detect if a URL is a GitHub repository root (not a file/issue/etc).
    Returns (is_repo, owner, repo) or (False, None, None).
    """
    parsed = urlparse(url)
    if parsed.netloc.lower().replace("www.", "") != "github.com":
        return False, None, None

    parts = [p for p in parsed.path.split("/") if p]
    if len(parts) >= 2 and parts[0] not in (
        "topics", "search", "marketplace", "sponsors", "settings", "notifications"
    ):
        return True, parts[0], parts[1]

    return False, None, None
