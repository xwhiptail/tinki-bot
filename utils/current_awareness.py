import inspect
import re
import time
from email.utils import parsedate_to_datetime
from dataclasses import dataclass
from datetime import datetime, timezone
from html import unescape
from html.parser import HTMLParser
from typing import Awaitable, Callable, Dict, List, Optional, Tuple
from urllib.parse import parse_qs, urlencode, urlparse, unquote
import xml.etree.ElementTree as ET

import aiohttp


DEFAULT_TIMEZONE = "America/New_York"
CURRENT_AWARENESS_CACHE_TTL_SECONDS = 300

FRESHNESS_TERMS = (
    "today",
    "tonight",
    "yesterday",
    "latest",
    "current",
    "currently",
    "newest",
    "what's new",
    "what is new",
    "new in",
    "news",
    "just added",
    "just announced",
    "announced",
    "released",
    "release",
    "patch",
    "update",
    "hotfix",
    "season",
    "this week",
    "right now",
)
GAMING_TERMS = (
    "gaming",
    "game",
    "games",
    "wow",
    "warcraft",
    "world of warcraft",
    "ffxiv",
    "ff14",
    "final fantasy",
    "aoe4",
    "age of empires",
    "civ",
    "civilization",
    "drg",
    "raid",
    "dungeon",
    "opener",
    "rotation",
)
PATCH_SENSITIVE_GAME_TERMS = (
    "opening rotation",
    "opener",
    "rotation",
    "best in slot",
    "bis",
    "tier list",
    "build",
    "talent",
    "talents",
    "class guide",
    "job guide",
)
GAME_QUERY_ALIASES = {
    "aoe4": "Age of Empires IV",
    "ffxiv": "Final Fantasy XIV",
    "ff14": "Final Fantasy XIV",
    "wow": "World of Warcraft",
    "drg": "Final Fantasy XIV Dragoon",
}
GAMING_FEEDS = (
    "https://www.ageofempires.com/news/feed/",
    "https://news.xbox.com/en-us/feed/",
    "https://na.finalfantasyxiv.com/lodestone/news/news.xml",
    "https://www.pcgamer.com/rss/",
    "https://www.gamespot.com/feeds/news/",
)
WORLD_FEEDS = (
    "https://feeds.bbci.co.uk/news/world/rss.xml",
    "https://feeds.npr.org/1001/rss.xml",
)

_LIVE_CONTEXT_CACHE: Dict[str, Tuple[float, List["CurrentAwarenessSource"]]] = {}


@dataclass(frozen=True)
class CurrentAwarenessSource:
    title: str
    url: str
    snippet: str = ""
    published: str = ""
    source: str = "web"


class _DuckDuckGoResultParser(HTMLParser):
    def __init__(self, limit: int):
        super().__init__()
        self.limit = limit
        self.results: List[CurrentAwarenessSource] = []
        self._in_title = False
        self._in_snippet = False
        self._current_href = ""
        self._title_parts: List[str] = []
        self._snippet_parts: List[str] = []

    def handle_starttag(self, tag, attrs):
        attrs_dict = dict(attrs)
        class_name = attrs_dict.get("class", "")
        if tag == "a" and "result__a" in class_name:
            self._flush_result()
            self._in_title = True
            self._current_href = attrs_dict.get("href", "")
            self._title_parts = []
            self._snippet_parts = []
            return
        if "result__snippet" in class_name:
            self._in_snippet = True
            self._snippet_parts = []

    def handle_endtag(self, tag):
        if tag == "a" and self._in_title:
            self._in_title = False
            return
        if self._in_snippet and tag in {"a", "div", "span"}:
            self._in_snippet = False

    def handle_data(self, data):
        if self._in_title:
            self._title_parts.append(data)
        elif self._in_snippet:
            self._snippet_parts.append(data)

    def close(self):
        super().close()
        self._flush_result()

    def _flush_result(self):
        if len(self.results) >= self.limit:
            return
        title = _clean_text(" ".join(self._title_parts))
        url = _clean_duckduckgo_url(self._current_href)
        snippet = _clean_text(" ".join(self._snippet_parts))
        self._title_parts = []
        self._snippet_parts = []
        self._current_href = ""
        if not title or not url:
            return
        if any(existing.url == url for existing in self.results):
            return
        self.results.append(
            CurrentAwarenessSource(
                title=title,
                url=url,
                snippet=snippet,
                source="DuckDuckGo",
            )
        )


def _clean_text(text: str) -> str:
    return re.sub(r"\s+", " ", unescape(text)).strip()


def _clean_html_text(text: str) -> str:
    without_tags = re.sub(r"<[^>]+>", " ", text or "")
    return _clean_text(without_tags)


def _clean_duckduckgo_url(href: str) -> str:
    href = unescape(href or "").strip()
    if not href:
        return ""
    parsed = urlparse(href)
    query = parse_qs(parsed.query)
    if "uddg" in query and query["uddg"]:
        return unquote(query["uddg"][0])
    return href


def _local_timezone(timezone_name: str = DEFAULT_TIMEZONE):
    try:
        from zoneinfo import ZoneInfo

        return ZoneInfo(timezone_name)
    except Exception:
        return timezone.utc


def _format_datetime(value: datetime) -> str:
    hour = value.strftime("%I").lstrip("0") or "0"
    return (
        f"{value.strftime('%A, %B')} {value.day}, {value.year}, "
        f"{hour}:{value.strftime('%M %p')} {value.tzname() or 'UTC'}"
    )


def build_current_time_context(
    now: Optional[datetime] = None,
    timezone_name: str = DEFAULT_TIMEZONE,
) -> str:
    local_tz = _local_timezone(timezone_name)
    if now is None:
        local_now = datetime.now(local_tz)
    elif now.tzinfo is None:
        local_now = now.replace(tzinfo=local_tz)
    else:
        local_now = now.astimezone(local_tz)
    utc_now = local_now.astimezone(timezone.utc)
    return "\n".join(
        (
            "Current date/time:",
            f"- {timezone_name}: {_format_datetime(local_now)}",
            f"- UTC: {_format_datetime(utc_now)}",
            f"Use the {timezone_name} date when users say today/tonight unless they specify another timezone.",
        )
    )


def needs_current_awareness(text: str) -> bool:
    lowered = f" {text.lower()} "
    if any(term in lowered for term in FRESHNESS_TERMS):
        return True
    has_gaming_context = any(term in lowered for term in GAMING_TERMS)
    has_patch_sensitive_term = any(term in lowered for term in PATCH_SENSITIVE_GAME_TERMS)
    return has_gaming_context and has_patch_sensitive_term


def build_search_query(text: str) -> str:
    lowered = text.lower()
    suffix = " gaming news" if any(term in lowered for term in GAMING_TERMS) else " current news"
    query = _clean_text(text)
    for alias, expansion in GAME_QUERY_ALIASES.items():
        if alias in lowered and expansion.lower() not in lowered:
            query = f"{query} {expansion}"
    if suffix.strip() not in lowered:
        query = f"{query}{suffix}"
    return query[:220]


def parse_duckduckgo_results(html: str, limit: int = 4) -> List[CurrentAwarenessSource]:
    parser = _DuckDuckGoResultParser(limit)
    parser.feed(html or "")
    parser.close()
    return parser.results[:limit]


def _xml_text(element, child_name: str, namespace: str = "") -> str:
    if namespace:
        child = element.find(f"{{{namespace}}}{child_name}")
    else:
        child = element.find(child_name)
    if child is None or child.text is None:
        return ""
    return _clean_html_text(child.text)


def parse_feed_sources(xml_text: str, limit: int = 8) -> List[CurrentAwarenessSource]:
    try:
        root = ET.fromstring(xml_text or "")
    except ET.ParseError:
        return []

    results: List[CurrentAwarenessSource] = []
    channel = root.find("channel")
    feed_title = _xml_text(channel, "title") if channel is not None else ""
    for item in root.findall(".//item"):
        if len(results) >= limit:
            break
        title = _xml_text(item, "title")
        url = _xml_text(item, "link")
        snippet = _xml_text(item, "description")
        published = _xml_text(item, "pubDate")
        if title and url:
            results.append(
                CurrentAwarenessSource(
                    title=title,
                    url=url,
                    snippet=snippet,
                    published=published,
                    source=feed_title or "RSS feed",
                )
            )

    atom_ns = "http://www.w3.org/2005/Atom"
    atom_title = _xml_text(root, "title", atom_ns)
    for entry in root.findall(f".//{{{atom_ns}}}entry"):
        if len(results) >= limit:
            break
        title = _xml_text(entry, "title", atom_ns)
        link_element = entry.find(f"{{{atom_ns}}}link")
        url = ""
        if link_element is not None:
            url = link_element.attrib.get("href", "")
        snippet = _xml_text(entry, "summary", atom_ns) or _xml_text(entry, "content", atom_ns)
        published = _xml_text(entry, "published", atom_ns) or _xml_text(entry, "updated", atom_ns)
        if title and url:
            results.append(
                CurrentAwarenessSource(
                    title=title,
                    url=url,
                    snippet=snippet,
                    published=published,
                    source=atom_title or "Atom feed",
                )
            )

    return results[:limit]


def _keyword_tokens(text: str) -> set:
    return {
        token
        for token in re.findall(r"[a-z0-9][a-z0-9_-]{2,}", text.lower())
        if token not in {"the", "and", "for", "with", "what", "was", "were", "today", "news", "current"}
    }


def _score_source(query: str, source: CurrentAwarenessSource) -> int:
    query_tokens = _keyword_tokens(query)
    source_text = " ".join((source.title, source.snippet, source.url))
    text_tokens = _keyword_tokens(source_text)
    score = len(query_tokens & text_tokens)
    lowered_query = query.lower()
    lowered_text = source_text.lower()
    if "aoe4" in lowered_query and "age of empires iv" in lowered_text:
        score += 4
    if "ffxiv" in lowered_query and "final fantasy xiv" in lowered_text:
        score += 4
    if "wow" in lowered_query and "world of warcraft" in lowered_text:
        score += 4
    if any(term in lowered_query for term in ("today", "just added", "added", "released")):
        if any(term in lowered_text for term in ("available now", "live today", "out today", "has come to")):
            score += 3
        published = _published_timestamp(source)
        if published and time.time() - published < 36 * 60 * 60:
            score += 2
    return score


def _published_timestamp(source: CurrentAwarenessSource) -> float:
    if not source.published:
        return 0.0
    try:
        parsed = parsedate_to_datetime(source.published)
    except Exception:
        return 0.0
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.timestamp()


def _news_rss_url(query: str) -> str:
    return "https://news.google.com/rss/search?" + urlencode(
        {
            "q": query,
            "hl": "en-US",
            "gl": "US",
            "ceid": "US:en",
        }
    )


def _feed_urls_for_query(query: str) -> List[str]:
    lowered = query.lower()
    urls = [_news_rss_url(query)]
    if any(term in lowered for term in GAMING_TERMS) or any(alias in lowered for alias in GAME_QUERY_ALIASES):
        urls.extend(GAMING_FEEDS)
    else:
        urls.extend(WORLD_FEEDS)
    return urls


async def _fetch_text(session, url: str) -> str:
    async with session.get(url) as response:
        if response.status != 200:
            return ""
        return await response.text()


async def fetch_feed_sources(query: str, limit: int = 4) -> List[CurrentAwarenessSource]:
    sources: List[CurrentAwarenessSource] = []
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (compatible; TinkiBot/1.0; +https://github.com/xwhiptail/tinki-bot)"
        )
    }
    try:
        async with aiohttp.ClientSession(
            headers=headers,
            timeout=aiohttp.ClientTimeout(total=6),
        ) as session:
            for url in _feed_urls_for_query(query):
                xml_text = await _fetch_text(session, url)
                sources.extend(parse_feed_sources(xml_text, limit=12))
                if len(sources) >= limit * 3:
                    break
    except Exception:
        return []

    ranked = sorted(
        sources,
        key=lambda source: (-_score_source(query, source), -_published_timestamp(source), source.title),
    )
    filtered = [source for source in ranked if _score_source(query, source) > 0]
    chosen = filtered or ranked
    unique: List[CurrentAwarenessSource] = []
    seen_urls = set()
    for source in chosen:
        if source.url in seen_urls:
            continue
        seen_urls.add(source.url)
        unique.append(source)
        if len(unique) >= limit:
            break
    return unique


async def fetch_current_awareness_sources(query: str, limit: int = 4) -> List[CurrentAwarenessSource]:
    cache_key = f"{limit}:{query.lower().strip()}"
    cached = _LIVE_CONTEXT_CACHE.get(cache_key)
    now = time.monotonic()
    if cached and now - cached[0] < CURRENT_AWARENESS_CACHE_TTL_SECONDS:
        return cached[1]

    sources = await fetch_feed_sources(query, limit=limit)
    if sources:
        _LIVE_CONTEXT_CACHE[cache_key] = (now, sources)
        return sources

    url = "https://duckduckgo.com/html/?" + urlencode({"q": query})
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (compatible; TinkiBot/1.0; +https://github.com/xwhiptail/tinki-bot)"
        )
    }
    try:
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=5)) as session:
            async with session.get(url, headers=headers) as response:
                if response.status != 200:
                    sources: List[CurrentAwarenessSource] = []
                else:
                    sources = parse_duckduckgo_results(await response.text(), limit=limit)
    except Exception:
        sources = []

    _LIVE_CONTEXT_CACHE[cache_key] = (now, sources)
    return sources


def format_source_context(
    sources: List[CurrentAwarenessSource],
    fetched_at: Optional[datetime] = None,
    timezone_name: str = DEFAULT_TIMEZONE,
) -> str:
    local_tz = _local_timezone(timezone_name)
    if fetched_at is None:
        fetched = datetime.now(local_tz)
    elif fetched_at.tzinfo is None:
        fetched = fetched_at.replace(tzinfo=local_tz)
    else:
        fetched = fetched_at.astimezone(local_tz)
    lines = [
        f"Live source context (web search fetched {_format_datetime(fetched)}; use only these snippets for fresh facts):"
    ]
    for source in sources:
        label = source.source
        if source.published:
            label = f"{label}, {source.published}"
        snippet = f" - {source.snippet}" if source.snippet else ""
        lines.append(f"- [{label}] {source.title}{snippet}")
        lines.append(f"  {source.url}")
    return "\n".join(lines)


async def _call_fetcher(fetcher, query: str, limit: int):
    value = fetcher(query, limit=limit)
    if inspect.isawaitable(value):
        return await value
    return value


async def build_current_awareness_context(
    text: str,
    now: Optional[datetime] = None,
    timezone_name: str = DEFAULT_TIMEZONE,
    fetcher: Optional[Callable[..., Awaitable[List[CurrentAwarenessSource]]]] = None,
    limit: int = 4,
) -> str:
    lines = [build_current_time_context(now=now, timezone_name=timezone_name)]
    if not needs_current_awareness(text):
        return "\n".join(lines)

    query = build_search_query(text)
    source_fetcher = fetcher or fetch_current_awareness_sources
    sources = await _call_fetcher(source_fetcher, query, limit)
    if sources:
        lines.append(
            format_source_context(
                list(sources)[:limit],
                fetched_at=now,
                timezone_name=timezone_name,
            )
        )
    else:
        lines.append(
            "Live lookup returned no usable source snippets for this fresh/current question. "
            "Say the lookup came up thin or ask for a source/link; do not invent details, "
            "and do not ask for a date if the user already gave one."
        )
    return "\n".join(lines)
