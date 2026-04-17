import asyncio
import io
import json
import logging
import random
import time
from dataclasses import dataclass

import aiohttp
import discord
from discord.ext import commands, menus
from fuzzywuzzy import process
from PIL import Image, ImageDraw

from config import GRINDING_STATE_FILE, STICKER_SPINNY, USER_WHIPTAIL_ID, user_matches

EMOTE_SUGGESTION_DISMISS_EMOJI = "\u274c"
EMOTE_BROWSER_MORE_EMOJI = "\U0001f4c4"
EMOTE_BROWSER_CANCEL_EMOJI = "\u274c"
EMOTE_BROWSER_COLOR = 0x55A7F7
EMOTE_BROWSER_PAGE_SIZE = 10
SEVENTV_GQL_ENDPOINT = "https://7tv.io/v3/gql"
SEVENTV_SEARCH_QUERY = (
    "query SearchEmotes($query: String!, $page: Int, $sort: Sort, $limit: Int, $filter: EmoteSearchFilter) {\n"
    " emotes(query: $query, page: $page, sort: $sort, limit: $limit, filter: $filter) {\n"
    "  items {\n"
    "   id\n"
    "   name\n"
    "   owner {\n"
    "    username\n"
    "   }\n"
    "   host {\n"
    "    url\n"
    "   }\n"
    "  }\n"
    " }\n"
    "}"
)


@dataclass
class SevenTvEmoteResult:
    id: str
    name: str
    host_url: str
    owner_username: str = ""


async def _get_user_id_from_username(guild, username):
    user = discord.utils.get(guild.members, name=username)
    return str(user.id) if user else None


class EmoteListSource(menus.ListPageSource):
    async def format_page(self, menu, items):
        embed = discord.Embed(title="Available Emotes", description='\n'.join(items), color=0x55a7f7)
        embed.set_footer(text=f"Page {menu.current_page + 1}/{self.get_max_pages()}")
        return embed


class EmotesMenu(menus.MenuPages):
    pass


class SevenTvPreviewButton(discord.ui.Button):
    def __init__(self, browser, index: int):
        self.browser = browser
        self.preview_index = index
        row = 0 if index < 5 else 1
        super().__init__(label=str(index + 1), style=discord.ButtonStyle.secondary, row=row)

    async def callback(self, interaction: discord.Interaction):
        await self.browser.handle_selection(interaction, self.preview_index)


class SevenTvEmoteBrowserView(discord.ui.View):
    def __init__(self, cog, ctx, emote_name: str, size: int, session, emotes, exact_match: bool):
        super().__init__(timeout=60)
        self.cog = cog
        self.ctx = ctx
        self.owner_id = ctx.author.id
        self.emote_name = emote_name
        self.size = size
        self.session = session
        self.emotes = list(emotes)
        self.page = 1
        self.exact_match = exact_match
        self.ext_cache = {}
        self.message = None
        self._closed = False
        self.selected_index = 0
        self.preview_buttons = [SevenTvPreviewButton(self, index) for index in range(EMOTE_BROWSER_PAGE_SIZE)]
        for button in self.preview_buttons:
            self.add_item(button)
        self._refresh_preview_buttons()

    async def start(self):
        file = await self.cog._build_7tv_browser_file(self.session, self.emotes, self.selected_index)
        self.message = await self.ctx.send(embed=self.build_embed(file is not None), view=self, file=file)

    def build_embed(self, has_preview_grid: bool = False):
        return self.cog._build_7tv_browser_embed(
            self.emote_name,
            self.size,
            self.emotes,
            self.page,
            self.exact_match,
            selected_index=self.selected_index,
            has_preview_grid=has_preview_grid,
        )

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.owner_id:
            await interaction.response.send_message("This emote picker belongs to someone else.", ephemeral=True)
            return False
        return True

    async def handle_selection(self, interaction: discord.Interaction, index: int):
        self.selected_index = max(0, min(index, len(self.emotes) - 1))
        self._refresh_preview_buttons()
        await self._edit_with_preview(interaction)

    def _refresh_preview_buttons(self):
        for index, button in enumerate(self.preview_buttons):
            if index < len(self.emotes):
                button.disabled = False
                button.label = str(index + 1)
                button.style = (
                    discord.ButtonStyle.primary
                    if index == self.selected_index
                    else discord.ButtonStyle.secondary
                )
            else:
                button.disabled = True
                button.label = "-"
                button.style = discord.ButtonStyle.secondary

    async def _edit_with_preview(self, interaction: discord.Interaction):
        file = await self.cog._build_7tv_browser_file(self.session, self.emotes, self.selected_index)
        await interaction.response.edit_message(
            embed=self.build_embed(file is not None),
            view=self,
            attachments=[file] if file is not None else [],
        )

    @discord.ui.button(label="Send", emoji="\u2705", style=discord.ButtonStyle.success, row=2)
    async def send_selected(self, interaction: discord.Interaction, button: discord.ui.Button):
        chosen = self.emotes[self.selected_index]
        url = await self.cog._resolve_7tv_media_url(self.session, chosen, self.size, self.ext_cache)
        await interaction.response.defer()
        await self.ctx.send(url)
        await self._finish()

    @discord.ui.button(label="More", emoji=EMOTE_BROWSER_MORE_EMOJI, style=discord.ButtonStyle.secondary, row=2)
    async def more(self, interaction: discord.Interaction, button: discord.ui.Button):
        try:
            next_page = self.page + 1
            new_emotes = await self.cog._search_7tv_page(
                self.session,
                self.emote_name,
                next_page,
                exact_match=self.exact_match,
            )
            if new_emotes:
                self.page = next_page
                self.emotes = list(new_emotes)
                self.selected_index = 0
            else:
                self.page = 1
                first_page = await self.cog._search_7tv_page(
                    self.session,
                    self.emote_name,
                    1,
                    exact_match=self.exact_match,
                )
                if first_page:
                    self.emotes = list(first_page)
                    self.selected_index = 0
            self._refresh_preview_buttons()
            await self._edit_with_preview(interaction)
        except Exception as exc:
            await interaction.response.send_message(f"Search failed: {exc}", ephemeral=True)

    @discord.ui.button(label="Cancel", emoji=EMOTE_BROWSER_CANCEL_EMOJI, style=discord.ButtonStyle.danger, row=2)
    async def cancel(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer()
        await self._finish(delete_command=True)

    async def on_timeout(self):
        await self._finish(delete_command=True)

    async def _finish(self, delete_command: bool = False):
        if self._closed:
            return
        self._closed = True
        self.stop()
        try:
            if self.message is not None:
                await self.message.delete()
        except (discord.Forbidden, discord.NotFound, discord.HTTPException):
            pass
        if delete_command:
            try:
                await self.ctx.message.delete()
            except (discord.Forbidden, discord.NotFound, discord.HTTPException, AttributeError):
                pass
        await self._close_clients()

    async def _close_clients(self):
        await self.session.close()


class Emotes(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.sticker_users = self._load_grinding_state()

    def _load_grinding_state(self) -> dict:
        try:
            with open(GRINDING_STATE_FILE, 'r') as f:
                return json.load(f)
        except (FileNotFoundError, json.JSONDecodeError):
            return {}

    def _save_grinding_state(self):
        with open(GRINDING_STATE_FILE, 'w') as f:
            json.dump(self.sticker_users, f)

    def _preview_7tv_url(self, emote: SevenTvEmoteResult) -> str:
        return f"https:{emote.host_url}/2x.webp"

    def _dedupe_7tv_results(self, emotes):
        seen = set()
        unique = []
        for emote in emotes:
            key = (emote.id, emote.host_url)
            if key in seen:
                continue
            seen.add(key)
            unique.append(emote)
        return unique

    def _display_owner(self, emote: SevenTvEmoteResult) -> str:
        return getattr(emote, "owner_username", "") or "unknown owner"

    def _build_7tv_browser_embed(
        self,
        emote_name: str,
        size: int,
        emotes,
        page: int,
        exact_match: bool,
        *,
        selected_index: int = 0,
        has_preview_grid: bool = False,
    ) -> discord.Embed:
        match_mode = "exact" if exact_match else "fuzzy"
        safe_selected_index = max(0, min(selected_index, len(emotes) - 1)) if emotes else 0
        description = "\n".join(
            f"{'->' if (index - 1) == safe_selected_index else '  '} `{index}.` **{emote.name}** by `{self._display_owner(emote)}`"
            for index, emote in enumerate(emotes, start=1)
        )
        embed = discord.Embed(
            title=f"7TV results for `{emote_name}`",
            description=description or "No results found.",
            color=EMOTE_BROWSER_COLOR,
        )
        if emotes:
            selected_emote = emotes[safe_selected_index]
            embed.add_field(
                name="Selected",
                value=f"**{selected_emote.name}** by `{self._display_owner(selected_emote)}`",
                inline=False,
            )
            if has_preview_grid:
                embed.set_image(url="attachment://7tv-page.png")
            else:
                embed.set_image(url=self._preview_7tv_url(selected_emote))
        embed.set_footer(text=f"Page {page} - {match_mode} search - click a number to preview, Send to post at {size}x")
        return embed

    async def _fetch_7tv_preview_tile(self, session: aiohttp.ClientSession, emote: SevenTvEmoteResult):
        try:
            async with session.get(self._preview_7tv_url(emote)) as resp:
                if resp.status != 200:
                    return None
                return Image.open(io.BytesIO(await resp.read())).convert("RGBA")
        except Exception:
            return None

    async def _build_7tv_browser_file(self, session: aiohttp.ClientSession, emotes, selected_index: int):
        if not emotes:
            return None

        cols = 5
        rows = max(1, (len(emotes) + cols - 1) // cols)
        tile_size = 96
        gap = 8
        label_height = 18
        width = cols * tile_size + (cols + 1) * gap
        height = rows * (tile_size + label_height) + (rows + 1) * gap
        canvas = Image.new("RGBA", (width, height), (24, 26, 37, 255))
        draw = ImageDraw.Draw(canvas)

        previews = await asyncio.gather(*(self._fetch_7tv_preview_tile(session, emote) for emote in emotes))
        for index, preview in enumerate(previews):
            col = index % cols
            row = index // cols
            x = gap + col * (tile_size + gap)
            y = gap + row * (tile_size + label_height + gap)
            draw.rounded_rectangle(
                (x, y, x + tile_size, y + tile_size),
                radius=10,
                fill=(40, 44, 61, 255),
                outline=(79, 172, 254, 255) if index == selected_index else (85, 88, 108, 255),
                width=3 if index == selected_index else 1,
            )
            if preview is not None:
                preview.thumbnail((tile_size - 8, tile_size - 8))
                px = x + (tile_size - preview.width) // 2
                py = y + (tile_size - preview.height) // 2
                canvas.alpha_composite(preview, (px, py))
            draw.text((x + 6, y + tile_size + 2), str(index + 1), fill=(255, 255, 255, 255))

        output = io.BytesIO()
        canvas.save(output, format="PNG")
        output.seek(0)
        return discord.File(output, filename="7tv-page.png")

    async def _search_7tv_page(
        self,
        session: aiohttp.ClientSession,
        searchterm: str,
        page: int,
        *,
        exact_match: bool,
        limit: int = EMOTE_BROWSER_PAGE_SIZE,
        max_retries: int = 3,
        backoff: int = 1,
    ):
        payload = {
            "operationName": "SearchEmotes",
            "variables": {
                "query": searchterm,
                "limit": limit,
                "page": page,
                "sort": {
                    "value": "popularity",
                    "order": "DESCENDING",
                },
                "filter": {
                    "category": "TOP",
                    "exact_match": exact_match,
                    "case_sensitive": False,
                    "ignore_tags": False,
                    "zero_width": False,
                    "animated": False,
                    "aspect_ratio": "",
                },
            },
            "query": SEVENTV_SEARCH_QUERY,
        }
        headers = {"Content-Type": "application/json"}

        for attempt in range(max_retries + 1):
            try:
                async with session.post(SEVENTV_GQL_ENDPOINT, json=payload, headers=headers) as response:
                    response.raise_for_status()
                    response_data = await response.json()
                if response_data.get("errors"):
                    raise RuntimeError(response_data["errors"][0].get("message", "unknown 7TV error"))
                items = response_data.get("data", {}).get("emotes", {}).get("items", [])
                return self._dedupe_7tv_results([
                    SevenTvEmoteResult(
                        id=item.get("id", ""),
                        name=item.get("name", ""),
                        owner_username=item.get("owner", {}).get("username", ""),
                        host_url=item.get("host", {}).get("url", ""),
                    )
                    for item in items
                    if item.get("host", {}).get("url")
                ])
            except Exception as exc:
                retriable = any(
                    marker in str(exc)
                    for marker in ("429", "Rate Limit", "Server disconnected", "502", "503", "504")
                )
                if retriable and attempt < max_retries:
                    await asyncio.sleep(backoff * (2 ** attempt))
                    continue
                raise

    async def _detect_7tv_ext(self, session: aiohttp.ClientSession, emote: SevenTvEmoteResult, ext_cache: dict) -> str:
        if emote.host_url in ext_cache:
            return ext_cache[emote.host_url]
        try:
            async with session.get(self._preview_7tv_url(emote)) as resp:
                if resp.status == 200:
                    img = Image.open(io.BytesIO(await resp.read()))
                    ext = "gif" if getattr(img, "is_animated", False) and img.n_frames > 1 else "png"
                    ext_cache[emote.host_url] = ext
                    return ext
        except Exception:
            pass
        ext_cache[emote.host_url] = "png"
        return "png"

    async def _resolve_7tv_media_url(
        self,
        session: aiohttp.ClientSession,
        emote: SevenTvEmoteResult,
        size: int,
        ext_cache: dict,
    ) -> str:
        ext = await self._detect_7tv_ext(session, emote, ext_cache)
        return f"https:{emote.host_url}/{size}x.{ext}"

    @commands.command(name='spinny')
    async def spinny_activate(self, ctx, user: discord.Member):
        self.sticker_users[str(user.id)] = True
        self._save_grinding_state()
        await ctx.send(f"Grinding activated for {user.mention}!", silent=True)

    @commands.command(name='stopspinny')
    async def spinny_deactivate(self, ctx, *, target: str):
        target = target.strip()
        if target.startswith('<@') and target.endswith('>'):
            user_id = target.strip('<@!>')
        else:
            user_id = await _get_user_id_from_username(ctx.guild, target)
        if user_id and user_id in self.sticker_users:
            self.sticker_users.pop(user_id, None)
            self._save_grinding_state()
            await ctx.send("Grinding deactivated.", silent=True)
        else:
            await ctx.send("Could not find the user you mentioned.")

    @commands.command(name='silentspinny')
    async def silent_spinny(self, ctx, target: str):
        if not user_matches(ctx.author, USER_WHIPTAIL_ID, 'whiptail'):
            await ctx.send("You do not have permission to use this command.")
            return
        user_id = await _get_user_id_from_username(ctx.guild, target)
        if user_id:
            self.sticker_users[user_id] = True
            self._save_grinding_state()
            await ctx.send(f"Grinding activated for {target}!", silent=True)
        else:
            await ctx.send("Could not find the user you mentioned.")

    @commands.Cog.listener()
    async def on_message(self, message):
        if message.author.bot:
            return

        content = message.content

        # Send SPINNY sticker to users with grinding active
        if str(message.author.id) in self.sticker_users:
            sticker = discord.utils.get(message.guild.stickers, name=STICKER_SPINNY)
            if sticker:
                await message.channel.send(stickers=[sticker], silent=True)
            else:
                await message.channel.send(f"Sticker '{STICKER_SPINNY}' not found.")

        # $ emote commands
        if not content.startswith('$'):
            return
        if not content[1:].split()[0]:
            return

        content_parts = content[1:].split(' ')
        emote_name = content_parts[0]

        try:
            repeat_times = int(content_parts[1]) if len(content_parts) > 1 else 1
        except ValueError:
            repeat_times = 1

        if repeat_times < 1 or repeat_times > 24:
            await message.channel.send("Error: The number of emotes must be between 1 and 24.")
            return

        if emote_name == "randomemote":
            available = [e for guild in self.bot.guilds for e in guild.emojis if e.available]
            if not available:
                await message.channel.send("No emotes found on any server.")
                return
            slot_msg = await message.channel.send(str(available[0]))
            start = time.time()
            while time.time() - start < 5:
                await slot_msg.edit(content=str(random.choice(available)))
                await asyncio.sleep(0.5)
            await slot_msg.edit(content=(str(random.choice(available)) * repeat_times)[:2000])
            return

        emote = discord.utils.get(message.guild.emojis, name=emote_name)
        if emote:
            await message.channel.send((str(emote) * repeat_times)[:2000], silent=True)
            return

        all_emotes = [e for guild in self.bot.guilds for e in guild.emojis if e.available]
        emote = discord.utils.find(lambda e: e.name == emote_name, all_emotes)
        if emote:
            await message.channel.send((str(emote) * repeat_times)[:2000], silent=True)
            return

        # Fuzzy match suggestions
        all_names = [e.name for e in all_emotes]
        closest = process.extract(emote_name, all_names, limit=5)
        if not closest:
            await message.channel.send(f'No emote found with the name "{emote_name}".')
            return

        suggestion_msg = await message.channel.send(
            f"Did you mean...? (React with the correct emote or {EMOTE_SUGGESTION_DISMISS_EMOJI} to dismiss)"
        )
        for match, score in closest:
            match_emote = discord.utils.get(all_emotes, name=match)
            if match_emote:
                await suggestion_msg.add_reaction(match_emote)
        await suggestion_msg.add_reaction(EMOTE_SUGGESTION_DISMISS_EMOJI)

        def check(reaction, user):
            return (
                user == message.author
                and reaction.message.id == suggestion_msg.id
                and (str(reaction.emoji) in [str(discord.utils.get(all_emotes, name=m[0])) for m in closest]
                     or str(reaction.emoji) == EMOTE_SUGGESTION_DISMISS_EMOJI)
            )

        try:
            reaction, _ = await self.bot.wait_for('reaction_add', timeout=60.0, check=check)
        except asyncio.TimeoutError:
            await suggestion_msg.delete()
            await message.channel.send("Suggestion timeout. Please try the command again.")
            return

        if str(reaction.emoji) == EMOTE_SUGGESTION_DISMISS_EMOJI:
            await suggestion_msg.delete()
            await message.delete()
            await message.channel.send("None selected... cleaning up...", delete_after=5.0)
        else:
            await message.channel.send((str(reaction.emoji) * repeat_times)[:2000], silent=True)
            await suggestion_msg.delete()

    @commands.command(name='allemotes')
    async def all_emotes(self, ctx):
        emotes = ctx.guild.emojis
        if not emotes:
            await ctx.send("No emotes found on the server.")
            return
        emotes_list = [f"{e} :`:{e.name}:`" for e in emotes]
        pages = EmotesMenu(source=EmoteListSource(emotes_list, per_page=10))
        await pages.start(ctx)

    @commands.command()
    async def emote(self, ctx, emote_name: str, size: int = 2):
        """Search 7TV and pick from a page of results."""
        if size not in [1, 2, 3, 4]:
            await ctx.send("Invalid size. Please choose a size between 1 and 4.")
            return

        session = aiohttp.ClientSession()
        try:
            exact_match = True
            emotes = await self._search_7tv_page(session, emote_name, 1, exact_match=True)
            if not emotes:
                exact_match = False
                emotes = await self._search_7tv_page(session, emote_name, 1, exact_match=False)
            if not emotes:
                await ctx.send(f"No 7TV emotes found for `{emote_name}`.")
                return

            if len(emotes) == 1:
                url = await self._resolve_7tv_media_url(session, emotes[0], size, {})
                await ctx.send(url)
                await session.close()
                return

            view = SevenTvEmoteBrowserView(
                self,
                ctx,
                emote_name,
                size,
                session,
                emotes,
                exact_match,
            )
            await view.start()
        except Exception as exc:
            await session.close()
            await ctx.send(f"Search failed: {exc}")


async def setup(bot):
    await bot.add_cog(Emotes(bot))
