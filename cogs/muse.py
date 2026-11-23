"""Muse notes bridge: mirrors the Muse <-> Claude Code notes mailbox into #muse.

The mailbox runs on the bot host (muse-notes.service) and exposes a small JSON API.
Its token is part of the URL path, so URLs and raw aiohttp errors are never logged.
"""

import asyncio
import json
import logging
import os
from collections import deque
from datetime import datetime

import aiohttp
import discord
from discord.ext import commands, tasks

from config import (CHANNEL_MUSE, MUSE_BRIDGE_FILE, MUSE_NOTES_TOKEN, MUSE_NOTES_URL,
                    USER_WHIPTAIL_ID, user_matches)

log = logging.getLogger("discord.cogs.muse")

POLL_SECONDS = 30
FETCH_LIMIT = 50
MAX_FETCH_PAGES = 200
MAX_BACKOFF_POLLS = 20
NOTE_MAX_CHARS = 4000
EMBED_DESCRIPTION_LIMIT = 4096
DISCORD_MESSAGE_LIMIT = 2000
MUSE_COMMAND_DEFAULT = 5
MUSE_COMMAND_MAX = 20
COMPACT_TEXT_LIMIT = 200
ECHO_ID_LIMIT = 200
HTTP_TIMEOUT_SECONDS = 10

SUCCESS_EMOJI = "✅"
FAILURE_EMOJI = "❌"

SENDER_LABELS = {
    "muse": "Merlin (Muse)",
    "claude": "Claude Code",
    "matthew": "Matthew",
}
SENDER_COLORS = {
    "muse": 0x9B59B6,
    "claude": 0xD97757,
    "matthew": 0x55A7F7,
}
UNKNOWN_SENDER_LABEL = "Unknown sender"

OWNER_ONLY_MESSAGE = "You do not have permission to use this command."
NOT_CONFIGURED_MESSAGE = "Muse bridge is not configured (MUSE_NOTES_URL / MUSE_NOTES_TOKEN missing)."
FETCH_FAILED_MESSAGE = "Couldn't reach the Muse notes mailbox. Try again in a bit."
NO_NOTES_MESSAGE = "No Muse notes yet."
POST_FAILED_MESSAGE = "Couldn't send that to Muse. Try again in a bit."
TOO_LONG_MESSAGE = f"Too long for Muse notes (max {NOTE_MAX_CHARS} characters)."
NO_ALLOWED_MENTIONS = discord.AllowedMentions.none()


class MuseNotesError(Exception):
    """Mailbox request failed. The message is safe to log: it never contains the URL or token."""


def sender_label(sender):
    return SENDER_LABELS.get(sender, UNKNOWN_SENDER_LABEL)


def split_note_text(text, limit=EMBED_DESCRIPTION_LIMIT):
    """Split text into chunks of at most `limit` chars, preferring newline then space boundaries."""
    text = text or ""
    if len(text) <= limit:
        return [text]
    chunks = []
    remaining = text
    while len(remaining) > limit:
        window = remaining[:limit]
        cut = window.rfind("\n")
        if cut < limit // 2:
            cut = window.rfind(" ")
        if cut < limit // 2:
            cut = limit
        chunks.append(remaining[:cut])
        remaining = remaining[cut:].lstrip("\n ") if cut < limit else remaining[cut:]
    if remaining:
        chunks.append(remaining)
    return chunks


def parse_note_time(value):
    if not value:
        return None
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None


def build_note_embeds(note):
    sender = note.get("sender")
    chunks = split_note_text(str(note.get("text", "")))
    timestamp = parse_note_time(note.get("at"))
    embeds = []
    for index, chunk in enumerate(chunks, start=1):
        embed = discord.Embed(
            description=chunk,
            color=SENDER_COLORS.get(sender, 0x95A5A6),
            timestamp=timestamp,
        )
        embed.set_author(name=sender_label(sender))
        footer = f"Note #{note.get('id')}"
        if len(chunks) > 1:
            footer += f" (part {index}/{len(chunks)})"
        embed.set_footer(text=footer)
        embeds.append(embed)
    return embeds


def format_compact_note(note):
    text = " ".join(str(note.get("text", "")).split())
    if len(text) > COMPACT_TEXT_LIMIT:
        text = text[:COMPACT_TEXT_LIMIT - 3].rstrip() + "..."
    when = parse_note_time(note.get("at"))
    when_text = f"<t:{int(when.timestamp())}:f>" if when and when.tzinfo else str(note.get("at") or "?")
    label = sender_label(note.get("sender"))
    return f"`#{note.get('id')}` {when_text} **{label}:** {discord.utils.escape_markdown(text)}"


def chunk_lines(lines, limit=DISCORD_MESSAGE_LIMIT):
    messages, current = [], ""
    for line in lines:
        candidate = f"{current}\n{line}" if current else line
        if len(candidate) > limit and current:
            messages.append(current)
            current = line
        else:
            current = candidate
    if current:
        messages.append(current)
    return messages


class MuseNotesClient:
    def __init__(self, base_url, token, session_factory=aiohttp.ClientSession):
        self._base = f"{base_url.rstrip('/')}/{token}/api"
        self._session_factory = session_factory

    async def _request(self, method, path, **kwargs):
        timeout = aiohttp.ClientTimeout(total=HTTP_TIMEOUT_SECONDS)
        try:
            async with self._session_factory(timeout=timeout) as session:
                async with session.request(method, f"{self._base}{path}", **kwargs) as resp:
                    if resp.status != 200:
                        raise MuseNotesError(f"HTTP {resp.status}")
                    data = await resp.json(content_type=None)
        except MuseNotesError:
            raise
        except asyncio.TimeoutError:
            raise MuseNotesError("timed out") from None
        except (aiohttp.ClientError, ValueError) as e:
            # Exception text can include the request URL, which contains the token.
            raise MuseNotesError(type(e).__name__) from None
        if not isinstance(data, dict) or not data.get("ok"):
            raise MuseNotesError("mailbox returned ok=false")
        return data

    async def fetch_notes(self, after_id=0, limit=FETCH_LIMIT):
        data = await self._request("GET", "/notes", params={"limit": limit, "after_id": int(after_id)})
        notes = data.get("notes") or []
        return sorted((n for n in notes if isinstance(n, dict) and "id" in n), key=lambda n: int(n["id"]))

    async def post_note(self, text):
        data = await self._request("POST", "/notes", json={"sender": "matthew", "text": text})
        return int(data["id"])

    async def fetch_all_after(self, after_id=0):
        """Page forward from after_id to the newest note (bounded)."""
        notes = []
        cursor = int(after_id)
        for _ in range(MAX_FETCH_PAGES):
            page = await self.fetch_notes(cursor, FETCH_LIMIT)
            if not page:
                break
            notes.extend(page)
            cursor = int(page[-1]["id"])
            if len(page) < FETCH_LIMIT:
                break
        return notes


def build_default_client():
    if not MUSE_NOTES_URL or not MUSE_NOTES_TOKEN:
        return None
    return MuseNotesClient(MUSE_NOTES_URL, MUSE_NOTES_TOKEN)


class Muse(commands.Cog):
    def __init__(self, bot, client="default", state_file=MUSE_BRIDGE_FILE):
        self.bot = bot
        self.client = build_default_client() if client == "default" else client
        self.state_file = state_file
        self.last_id = self._load_last_id()
        self._echo_ids = set()
        self._echo_order = deque()
        self._lock = asyncio.Lock()
        self._failures = 0
        self._skip_polls = 0
        self._warned_missing_channel = False

    @property
    def configured(self):
        return self.client is not None

    def status_line(self):
        if not self.configured:
            return "Muse bridge: idle (MUSE_NOTES_URL / MUSE_NOTES_TOKEN not set)"
        return f"Muse bridge: polling every {POLL_SECONDS}s into #{CHANNEL_MUSE}"

    async def cog_load(self):
        if self.configured:
            self.poll_notes.start()
        else:
            log.warning("Muse bridge idle: MUSE_NOTES_URL / MUSE_NOTES_TOKEN not set")

    async def cog_unload(self):
        self.poll_notes.cancel()

    # ── state ────────────────────────────────────────────────────────────────

    def _load_last_id(self):
        try:
            with open(self.state_file, "r", encoding="utf-8") as f:
                value = json.load(f).get("last_id")
            return int(value) if value is not None else None
        except FileNotFoundError:
            return None
        except (ValueError, TypeError, AttributeError, OSError):
            log.warning("Muse bridge state file unreadable; treating as first run")
            return None

    def _save_last_id(self):
        tmp_path = f"{self.state_file}.tmp"
        with open(tmp_path, "w", encoding="utf-8") as f:
            json.dump({"last_id": self.last_id}, f)
        os.replace(tmp_path, self.state_file)

    def _remember_echo_id(self, note_id):
        if note_id in self._echo_ids:
            return
        self._echo_ids.add(note_id)
        self._echo_order.append(note_id)
        while len(self._echo_order) > ECHO_ID_LIMIT:
            self._echo_ids.discard(self._echo_order.popleft())

    def _muse_channel(self):
        return discord.utils.get(self.bot.get_all_channels(), name=CHANNEL_MUSE)

    # ── outbound: mailbox -> #muse ───────────────────────────────────────────

    @tasks.loop(seconds=POLL_SECONDS)
    async def poll_notes(self):
        try:
            await self.poll_once()
        except Exception:
            log.exception("Muse bridge poll failed unexpectedly")

    @poll_notes.before_loop
    async def before_poll_notes(self):
        await self.bot.wait_until_ready()

    async def poll_once(self):
        if not self.configured:
            return
        if self._skip_polls > 0:
            self._skip_polls -= 1
            return
        async with self._lock:
            try:
                if self.last_id is None:
                    notes = await self.client.fetch_all_after(0)
                else:
                    notes = await self.client.fetch_notes(self.last_id, FETCH_LIMIT)
            except MuseNotesError as e:
                self._failures += 1
                self._skip_polls = min(2 ** (self._failures - 1), MAX_BACKOFF_POLLS)
                log.warning("Muse bridge fetch failed (%s); backing off %d poll(s)", e, self._skip_polls)
                return
            self._failures = 0

            if self.last_id is None:
                # First run: start from the newest note and post nothing (no backfill flood).
                self.last_id = int(notes[-1]["id"]) if notes else 0
                self._save_last_id()
                log.info("Muse bridge initialized at note id %s", self.last_id)
                return

            if not notes:
                return
            channel = self._muse_channel()
            if channel is None:
                if not self._warned_missing_channel:
                    log.warning("Muse bridge: #%s channel not found; holding notes", CHANNEL_MUSE)
                    self._warned_missing_channel = True
                return
            self._warned_missing_channel = False

            for note in notes:
                note_id = int(note["id"])
                if note_id <= self.last_id:
                    continue
                if note_id in self._echo_ids:
                    self._echo_ids.discard(note_id)
                else:
                    try:
                        for embed in build_note_embeds(note):
                            await channel.send(embed=embed, allowed_mentions=NO_ALLOWED_MENTIONS)
                    except discord.HTTPException as e:
                        log.warning("Muse bridge could not post note %s: %s", note_id, type(e).__name__)
                        return
                self.last_id = note_id
                self._save_last_id()

    # ── inbound: #muse -> mailbox ────────────────────────────────────────────

    def _is_bridge_message(self, message):
        if message.author.bot or message.guild is None:
            return False
        if getattr(message.channel, "name", None) != CHANNEL_MUSE:
            return False
        if not user_matches(message.author, USER_WHIPTAIL_ID, 'whiptail'):
            return False
        return not message.content.startswith('!')

    @commands.Cog.listener()
    async def on_message(self, message):
        if not self.configured or not self._is_bridge_message(message):
            return
        text = message.content.strip()
        if not text:
            return
        if len(text) > NOTE_MAX_CHARS:
            await message.add_reaction(FAILURE_EMOJI)
            await message.reply(TOO_LONG_MESSAGE, mention_author=False)
            return
        async with self._lock:
            try:
                note_id = await self.client.post_note(text)
            except MuseNotesError as e:
                log.warning("Muse bridge post failed (%s)", e)
                note_id = None
            if note_id is not None:
                self._remember_echo_id(note_id)
        if note_id is None:
            await message.add_reaction(FAILURE_EMOJI)
            await message.reply(POST_FAILED_MESSAGE, mention_author=False)
        else:
            await message.add_reaction(SUCCESS_EMOJI)

    # ── command ──────────────────────────────────────────────────────────────

    async def _latest_notes(self, count):
        notes = []
        if self.last_id:
            notes = await self.client.fetch_all_after(max(0, self.last_id - 200))
        if len(notes) < count:
            notes = await self.client.fetch_all_after(0)
        return notes[-count:]

    @commands.command(name="muse")
    async def muse(self, ctx, count: str = None):
        if not user_matches(ctx.author, USER_WHIPTAIL_ID, 'whiptail'):
            await ctx.send(OWNER_ONLY_MESSAGE)
            return
        if not self.configured:
            await ctx.send(NOT_CONFIGURED_MESSAGE)
            return
        try:
            n = int(count) if count is not None else MUSE_COMMAND_DEFAULT
        except ValueError:
            n = MUSE_COMMAND_DEFAULT
        n = max(1, min(n, MUSE_COMMAND_MAX))
        try:
            notes = await self._latest_notes(n)
        except MuseNotesError as e:
            log.warning("Muse !muse fetch failed (%s)", e)
            await ctx.send(FETCH_FAILED_MESSAGE)
            return
        if not notes:
            await ctx.send(NO_NOTES_MESSAGE)
            return
        for chunk in chunk_lines([format_compact_note(note) for note in notes]):
            await ctx.send(chunk, allowed_mentions=NO_ALLOWED_MENTIONS)


async def setup(bot):
    await bot.add_cog(Muse(bot))
