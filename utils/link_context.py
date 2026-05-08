import ipaddress
import re
from dataclasses import dataclass
from html import unescape
from html.parser import HTMLParser
from typing import List, Optional
from urllib.parse import urlparse

import aiohttp


URL_PATTERN = re.compile(r"https?://[^\s<>()]+", re.IGNORECASE)
DISCORD_MESSAGE_URL_PATTERN = re.compile(
    r"https?://(?:(?:ptb|canary)\.)?discord(?:app)?\.com/channels/\S+",
    re.IGNORECASE,
)
MAX_LINKS = 2
MAX_PAGE_BYTES = 200_000


@dataclass(frozen=True)
class LinkContext:
    url: str
    title: str
    description: str = ""
    site_name: str = ""


class _PageSummaryParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.title_parts: List[str] = []
        self.in_title = False
        self.meta = {}

    def handle_starttag(self, tag, attrs):
        attrs_dict = {str(key).lower(): value for key, value in attrs if value is not None}
        if tag.lower() == "title":
            self.in_title = True
            return
        if tag.lower() != "meta":
            return
        key = (attrs_dict.get("property") or attrs_dict.get("name") or "").lower()
        content = attrs_dict.get("content", "")
        if key and content and key not in self.meta:
            self.meta[key] = _clean_text(content)

    def handle_endtag(self, tag):
        if tag.lower() == "title":
            self.in_title = False

    def handle_data(self, data):
        if self.in_title:
            self.title_parts.append(data)

    @property
    def title(self) -> str:
        return _clean_text(" ".join(self.title_parts))


def _clean_text(text: str) -> str:
    return re.sub(r"\s+", " ", unescape(text or "")).strip()


def _trim_url(url: str) -> str:
    return (url or "").rstrip(".,!?)]}'\"")


def _is_blocked_host(hostname: str) -> bool:
    host = (hostname or "").strip("[]").lower().rstrip(".")
    if not host:
        return True
    if host in {"localhost"} or host.endswith((".localhost", ".local")):
        return True
    try:
        ip = ipaddress.ip_address(host)
    except ValueError:
        return False
    return (
        ip.is_private
        or ip.is_loopback
        or ip.is_link_local
        or ip.is_multicast
        or ip.is_reserved
        or ip.is_unspecified
    )


def is_public_http_url(url: str) -> bool:
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"}:
        return False
    return not _is_blocked_host(parsed.hostname or "")


def extract_public_links(text: str, limit: int = MAX_LINKS) -> List[str]:
    links: List[str] = []
    for match in URL_PATTERN.finditer(text or ""):
        url = _trim_url(match.group(0))
        if DISCORD_MESSAGE_URL_PATTERN.fullmatch(url):
            continue
        if not is_public_http_url(url):
            continue
        if url in links:
            continue
        links.append(url)
        if len(links) >= limit:
            break
    return links


def parse_link_context(html: str, url: str) -> Optional[LinkContext]:
    parser = _PageSummaryParser()
    parser.feed(html or "")
    title = (
        parser.meta.get("og:title")
        or parser.meta.get("twitter:title")
        or parser.title
    )
    description = (
        parser.meta.get("og:description")
        or parser.meta.get("twitter:description")
        or parser.meta.get("description")
    )
    site_name = parser.meta.get("og:site_name", "")
    if not title and not description:
        return None
    return LinkContext(
        url=url,
        title=_clean_text(title or url)[:180],
        description=_clean_text(description)[:360],
        site_name=_clean_text(site_name)[:80],
    )


async def _fetch_single_link_context(session, url: str) -> Optional[LinkContext]:
    async with session.get(url, allow_redirects=True, max_redirects=3) as response:
        if not is_public_http_url(str(response.url)):
            return None
        if response.status != 200:
            return None
        content_type = (response.headers.get("Content-Type") or "").lower()
        if not any(kind in content_type for kind in ("text/html", "application/xhtml+xml", "text/plain")):
            return None
        payload = await response.content.read(MAX_PAGE_BYTES + 1)
        html = payload[:MAX_PAGE_BYTES].decode(response.charset or "utf-8", errors="replace")
        return parse_link_context(html, str(response.url))


async def fetch_link_contexts(text: str, limit: int = MAX_LINKS) -> List[LinkContext]:
    urls = extract_public_links(text, limit=limit)
    if not urls:
        return []
    headers = {
        "User-Agent": "Mozilla/5.0 (compatible; TinkiBot/1.0; +https://github.com/xwhiptail/tinki-bot)"
    }
    contexts: List[LinkContext] = []
    try:
        async with aiohttp.ClientSession(headers=headers, timeout=aiohttp.ClientTimeout(total=6)) as session:
            for url in urls:
                try:
                    context = await _fetch_single_link_context(session, url)
                except Exception:
                    context = None
                if context:
                    contexts.append(context)
    except Exception:
        return []
    return contexts


def format_link_context(contexts: List[LinkContext]) -> str:
    if not contexts:
        return ""
    lines = ["Linked page context (fetched live; use only these snippets for linked pages):"]
    for context in contexts:
        label = context.site_name or urlparse(context.url).netloc
        snippet = f" - {context.description}" if context.description else ""
        lines.append(f"- [{label}] {context.title}{snippet}")
        lines.append(f"  {context.url}")
    return "\n".join(lines)


async def build_link_context(text: str, limit: int = MAX_LINKS) -> str:
    return format_link_context(await fetch_link_contexts(text, limit=limit))
