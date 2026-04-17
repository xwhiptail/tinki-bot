import asyncio
import io
import json
import logging
import random
import time

import aiohttp
import discord
import seventv
from discord.ext import commands, menus
from fuzzywuzzy import process
from PIL import Image

from config import GRINDING_STATE_FILE, STICKER_SPINNY, USER_WHIPTAIL_ID, user_matches

EMOTE_SUGGESTION_DISMISS_EMOJI = "\u274c"
EMOTE_BROWSER_PREV = "\u2b05\ufe0f"
EMOTE_BROWSER_NEXT = "\u27a1\ufe0f"
EMOTE_BROWSER_PICK = "\u2705"
EMOTE_BROWSER_MORE = "\U0001f4c4"
EMOTE_BROWSER_CANCEL = "\u274c"
EMOTE_BROWSER_CONTROLS = [
    EMOTE_BROWSER_PREV,
    EMOTE_BROWSER_NEXT,
    EMOTE_BROWSER_PICK,
    EMOTE_BROWSER_MORE,
    EMOTE_BROWSER_CANCEL,
]


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

        suggestion_msg = await message.channel.send("Did you mean...? (React with the correct emote or ❌ to dismiss)")
        for match, score in closest:
            match_emote = discord.utils.get(all_emotes, name=match)
            if match_emote:
                await suggestion_msg.add_reaction(match_emote)
        await suggestion_msg.add_reaction('❌')

        def check(reaction, user):
            return (
                user == message.author
                and reaction.message.id == suggestion_msg.id
                and (str(reaction.emoji) in [str(discord.utils.get(all_emotes, name=m[0])) for m in closest]
                     or str(reaction.emoji) == '❌')
            )

        try:
            reaction, _ = await self.bot.wait_for('reaction_add', timeout=60.0, check=check)
        except asyncio.TimeoutError:
            await suggestion_msg.delete()
            await message.channel.send("Suggestion timeout. Please try the command again.")
            return

        if str(reaction.emoji) == '❌':
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
        """Browse 7TV emotes one at a time.
        ⬅️➡️ flip through results · ✅ send at chosen size · 📄 next page · ❌ cancel
        """
        if size not in [1, 2, 3, 4]:
            await ctx.send("Invalid size. Please choose a size between 1 and 4.")
            return

        PREV, NEXT, PICK, MORE, CANCEL = '⬅️', '➡️', '✅', '📄', '❌'
        CONTROLS = list(EMOTE_BROWSER_CONTROLS)
        per_page    = 5
        max_retries = 3
        backoff     = 1
        ext_cache   = {}   # host_url → 'gif'/'png', avoid re-fetching per navigation

        async def detect_ext(session, emote):
            if emote.host_url in ext_cache:
                return ext_cache[emote.host_url]
            try:
                async with session.get(f"https:{emote.host_url}/2x.webp") as resp:
                    if resp.status == 200:
                        img = Image.open(io.BytesIO(await resp.read()))
                        ext = 'gif' if getattr(img, "is_animated", False) and img.n_frames > 1 else 'png'
                        ext_cache[emote.host_url] = ext
                        return ext
            except Exception:
                pass
            ext_cache[emote.host_url] = 'png'
            return 'png'

        async def prefetch(session, emotes_list):
            """Fire off ext detection for the whole page concurrently."""
            await asyncio.gather(*[detect_ext(session, e) for e in emotes_list],
                                 return_exceptions=True)

        async def search(stv, page, exact=True):
            return await stv.emote_search(
                emote_name, limit=per_page, page=page,
                case_sensitive=False, exact_match=exact,
            )

        async def card_text(session, emotes_list, idx, page):
            em = emotes_list[idx]
            ext = await detect_ext(session, em)
            total = len(emotes_list)
            return (
                f"https:{em.host_url}/2x.{ext}\n"
                f"**{em.name}** · {idx + 1} of {total} · page {page}"
            )

        async with aiohttp.ClientSession() as session:
            stv = seventv.seventv()
            try:
                page  = 1
                retry = 0
                emotes = []

                # ── initial search ────────────────────────────────────────────
                while not emotes:
                    try:
                        emotes = await search(stv, page, exact=True)
                        if not emotes:
                            # fuzzy fallback when exact match finds nothing
                            emotes = await search(stv, page, exact=False)
                        if not emotes:
                            await ctx.send(f"No 7TV emotes found for `{emote_name}`.")
                            return
                    except Exception as e:
                        err = str(e)
                        if ("Rate Limit" in err or "Server disconnected" in err) and retry < max_retries:
                            wait = backoff * (2 ** retry)
                            await ctx.send(f"Retrying in {wait}s...", delete_after=wait)
                            await asyncio.sleep(wait)
                            retry += 1
                        else:
                            await ctx.send(f"Search failed: {e}")
                            return

                idx = 0
                # pre-fetch ext for all results on this page in the background
                asyncio.create_task(prefetch(session, emotes))

                card = await ctx.send(await card_text(session, emotes, idx, page))
                for emoji in CONTROLS:
                    await card.add_reaction(emoji)

                # ── interaction loop ──────────────────────────────────────────
                while True:
                    def check(reaction, user):
                        return (
                            user == ctx.author
                            and reaction.message.id == card.id
                            and str(reaction.emoji) in CONTROLS
                        )

                    try:
                        reaction, _ = await self.bot.wait_for(
                            'reaction_add', timeout=60.0, check=check
                        )
                    except asyncio.TimeoutError:
                        try:
                            await card.delete()
                        except discord.NotFound:
                            pass
                        return

                    emoji_str = str(reaction.emoji)

                    # remove the user's reaction so they can react again without un-reacting
                    try:
                        await card.remove_reaction(emoji_str, ctx.author)
                    except (discord.Forbidden, discord.HTTPException):
                        pass

                    if emoji_str == CANCEL:
                        try:
                            await card.delete()
                            await ctx.message.delete()
                        except (discord.Forbidden, discord.NotFound):
                            pass
                        return

                    elif emoji_str == PICK:
                        chosen = emotes[idx]
                        ext = await detect_ext(session, chosen)
                        await ctx.send(f"https:{chosen.host_url}/{size}x.{ext}")
                        try:
                            await card.delete()
                        except discord.NotFound:
                            pass
                        return

                    elif emoji_str == PREV:
                        idx = (idx - 1) % len(emotes)
                        await card.edit(content=await card_text(session, emotes, idx, page))

                    elif emoji_str == NEXT:
                        idx = (idx + 1) % len(emotes)
                        await card.edit(content=await card_text(session, emotes, idx, page))

                    elif emoji_str == MORE:
                        try:
                            new_emotes = await search(stv, page + 1, exact=True)
                            if new_emotes:
                                page += 1
                                emotes = new_emotes
                            else:
                                # wrap back to page 1
                                page = 1
                                emotes = await search(stv, 1, exact=True) or emotes
                        except Exception:
                            pass  # stay on current page/results
                        idx = 0
                        asyncio.create_task(prefetch(session, emotes))
                        await card.edit(content=await card_text(session, emotes, idx, page))

            finally:
                await stv.close()


async def setup(bot):
    await bot.add_cog(Emotes(bot))
