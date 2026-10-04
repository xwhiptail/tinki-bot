"""Bounded, on-demand channel history retrieval and source-backed rendering."""

import asyncio
import json
import re
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Optional

import discord


SCAN_LIMIT = 2000
SCAN_TIMEOUT = 20
SOURCE_LIMIT = 24
MESSAGE_CHARS = 500
STOPWORDS = set("a an and about are as at be behind by channel did do explain for from happened history how i in incident is it joke lore me of on or our please said server story tell that the this to was we what when where who why with you your tinki bot".split())


@dataclass(frozen=True)
class HistoryRequest:
    mode: str
    query: str = ""
    days: int = 7
    before: Optional[datetime] = None


@dataclass(frozen=True)
class HistorySource:
    message_id: int
    channel_id: int
    guild_id: int
    author: str
    created_at: datetime
    content: str

    @property
    def url(self):
        return f"https://discord.com/channels/{self.guild_id}/{self.channel_id}/{self.message_id}"


@dataclass
class HistoryScan:
    sources: list = field(default_factory=list)
    scanned: int = 0
    oldest: Optional[datetime] = None
    newest: Optional[datetime] = None
    limited: bool = False
    timed_out: bool = False


def parse_lore_request(text: str) -> HistoryRequest:
    before = None
    match = re.search(r"\bbefore:(\S+)", text, re.IGNORECASE)
    if match:
        try:
            before = datetime.strptime(match[1], "%Y-%m-%d").replace(tzinfo=timezone.utc)
        except ValueError:
            raise ValueError("Use `before:YYYY-MM-DD`, for example `!lore before:2025-01-01 toaster`.") from None
        text = text[:match.start()] + text[match.end():]
    query = text.strip()
    if not query or not keywords(query):
        raise ValueError("Give me a topic to investigate, like `!lore toaster`.")
    if len(query) > 300:
        raise ValueError("Keep the lore topic under 300 characters so I can focus the search.")
    return HistoryRequest("lore", query=query, before=before)


def parse_history_request(text: str) -> Optional[HistoryRequest]:
    text = re.sub(r"^\s*(?:hey[, ]+)?tinki(?:-bot)?[\s,:!-]*", "", text, flags=re.I).strip()
    if re.search(r"\b(?:what (?:did|have) i miss(?:ed)?|catch me up|recap (?:this |the )?(?:channel|chat)|summari[sz]e (?:this |the )?(?:channel|chat))\b", text, re.I):
        days = 30 if re.search(r"\bmonth\b", text, re.I) else 7
        if re.search(r"\b(?:today|yesterday|day)\b", text, re.I):
            days = 1
        count = re.search(r"\b(\d+)\s+days?\b", text, re.I)
        if count:
            days = int(count[1])
        return HistoryRequest("recap", days=days)
    patterns = (
        r"\b(?:lore|story) behind (.+)",
        r"\b(?:channel|server) (?:lore|history) (?:of|about) (.+)",
        r"\bexplain (?:the )?(.+\b(?:incident|inside joke|running joke))\s*[?.!]*$",
        r"\bwhen did we (?:first )?(?:start|begin) (?:talking|joking) about (.+)",
    )
    for pattern in patterns:
        match = re.search(pattern, text, re.I)
        if match:
            query = match[1].strip().rstrip("?.!")
            return HistoryRequest("lore", query=query)
    return None


def keywords(text):
    return {word for word in re.findall(r"\w+", text.casefold()) if len(word) > 1 and word not in STOPWORDS}


async def scan_channel_history(message, request: HistoryRequest) -> HistoryScan:
    result = HistoryScan()
    before = request.before or message
    after = message.created_at - timedelta(days=request.days) if request.mode == "recap" else None
    terms = keywords(request.query)

    async def collect():
        async for entry in message.channel.history(limit=SCAN_LIMIT, before=before, after=after, oldest_first=False):
            if result.scanned >= SCAN_LIMIT:
                break
            result.scanned += 1
            result.oldest = entry.created_at if result.oldest is None else min(result.oldest, entry.created_at)
            result.newest = entry.created_at if result.newest is None else max(result.newest, entry.created_at)
            if entry.channel.id != message.channel.id or entry.guild is None or entry.guild.id != message.guild.id:
                continue
            if entry.id >= message.id or entry.author.bot:
                continue
            content = (entry.content or "").strip()
            if not content or content.startswith(("!", "$")):
                continue
            # Retain a bounded excerpt around the query, not just the first line.
            start = 0
            if terms:
                positions = [match.start() for match in re.finditer(r"\w+", content.casefold()) if match[0] in terms]
                if positions:
                    start = max(0, min(positions) - 120)
            excerpt = content[start:start + MESSAGE_CHARS]
            if start:
                excerpt = "..." + excerpt
            if start + MESSAGE_CHARS < len(content):
                excerpt += "..."
            result.sources.append(HistorySource(
                entry.id, entry.channel.id, entry.guild.id, entry.author.display_name,
                entry.created_at, excerpt,
            ))
        result.limited = result.scanned >= SCAN_LIMIT

    try:
        await asyncio.wait_for(collect(), timeout=SCAN_TIMEOUT)
    except asyncio.TimeoutError:
        result.timed_out = True
    return result


def select_history_sources(scan: HistoryScan, request: HistoryRequest):
    ordered = sorted(scan.sources, key=lambda item: (item.created_at, item.message_id))
    if request.mode == "recap":
        if len(ordered) <= SOURCE_LIMIT:
            return ordered
        # Spread short blocks across the window, retaining adjacent conversation.
        indices = set()
        for block in range(6):
            start = round(block * (len(ordered) - 4) / 5)
            indices.update(range(start, start + 4))
        return [ordered[index] for index in sorted(indices)]
    terms = keywords(request.query)
    matches = [index for index, item in enumerate(ordered) if terms & keywords(item.content)]
    if not matches:
        return []
    ranked = sorted(matches, key=lambda index: (-len(terms & keywords(ordered[index].content)), index))
    # Anchor both ends of the story and strongest matches, leaving room for replies
    # that say things like "that's why" without repeating the topic's keyword.
    anchors = list(dict.fromkeys(matches[:2] + matches[-2:] + ranked))[:SOURCE_LIMIT // 2]
    chosen = set(anchors)
    for index in anchors:
        for neighbor in (index - 1, index + 1):
            if (0 <= neighbor < len(ordered)
                    and abs((ordered[neighbor].created_at - ordered[index].created_at).total_seconds()) <= 300
                    and len(chosen) < SOURCE_LIMIT):
                chosen.add(neighbor)
    return [ordered[index] for index in sorted(chosen)]


def source_payload(sources):
    return [{"source": index, "time_utc": item.created_at.isoformat(), "author": item.author, "text": item.content}
            for index, item in enumerate(sources, 1)]


def _safe_text(text):
    return discord.utils.escape_markdown(discord.utils.escape_mentions(" ".join(text.split())))


def _citation(source):
    label = _safe_text(f"{source.created_at:%Y-%m-%d} · {source.author}")
    return f"[{label}](<{source.url}>)"


def render_history_answer(raw: str, sources):
    """Accept only bounded points with valid source IDs; construct every link here."""
    try:
        points = json.loads(raw)["points"]
        if not isinstance(points, list) or not 1 <= len(points) <= 6:
            return None
        lines = []
        for point in points:
            text, refs = point["text"], point["sources"]
            if not isinstance(text, str) or not text.strip() or len(text) > 400 or re.search(r"https?://", text, re.I):
                return None
            if not isinstance(refs, list) or not 1 <= len(refs) <= 3:
                return None
            if any(type(ref) is not int or not 1 <= ref <= len(sources) for ref in refs):
                return None
            links = " ".join(_citation(sources[ref - 1]) for ref in dict.fromkeys(refs))
            lines.append(f"- {_safe_text(text)}\n  {links}")
        return lines
    except (ValueError, TypeError, KeyError):
        return None


def quote_fallback(sources):
    return [f'- "{_safe_text(source.content[:240])}"\n  {_citation(source)}' for source in sources[:5]]


def coverage_note(scan, selected, request):
    if scan.oldest is None:
        if scan.timed_out:
            return "The history lookup timed out before any messages arrived. Try again in a moment."
        return "No channel history was available in this search."
    note = f"Read {scan.scanned:,} messages from {scan.oldest:%Y-%m-%d} to {scan.newest:%Y-%m-%d} (UTC); used {len(selected)} source messages."
    if scan.limited or scan.timed_out:
        note += " Search stopped at the message or time limit; older messages may be missing."
    if request.mode == "recap" and len(scan.sources) > len(selected):
        note += " This recap uses a sample of the conversation."
    if request.mode == "lore":
        note += " Earliest found does not prove where the story started."
        note += " To search further back: `!lore before:YYYY-MM-DD <topic>` (UTC)."
    return note
