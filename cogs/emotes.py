import asyncio
import io
import logging
import random
import time

import aiohttp
import discord
import seventv
from discord.ext import commands, menus
from fuzzywuzzy import process
from PIL import Image


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
        self.sticker_users = {}

    @commands.Cog.listener()
    async def on_message(self, message):
        if message.author.bot:
            return

        content = message.content

        # Grinding commands
        if content.startswith('!spinny'):
            parts = content.split()
            if len(parts) < 2:
                await message.channel.send("Please mention a user to activate the grinding.")
                return
            user_id = parts[1].strip('<@!>')
            user = message.guild.get_member(int(user_id))
            if user:
                self.sticker_users[user_id] = True
                await message.channel.send(f"Grinding activated for {user.mention}!", silent=True)
            else:
                await message.channel.send("Could not find the user you mentioned.")
            return

        if content.startswith('!stopspinny'):
            parts = content.split()
            if len(parts) < 2:
                await message.channel.send("Please specify a user to deactivate the grinding.")
                return
            target = parts[1]
            if target.startswith('<@') and target.endswith('>'):
                user_id = target.strip('<@!>')
            else:
                user_id = await _get_user_id_from_username(message.guild, target)
            if user_id and user_id in self.sticker_users:
                self.sticker_users.pop(user_id, None)
                await message.channel.send("Grinding deactivated.", silent=True)
            else:
                await message.channel.send("Could not find the user you mentioned.")
            return

        if content.startswith('!silentspinny'):
            if message.author.name == "whiptail":
                parts = content.split()
                if len(parts) < 2:
                    await message.channel.send("Please specify a user.")
                    return
                user_id = await _get_user_id_from_username(message.guild, parts[1])
                if user_id:
                    self.sticker_users[user_id] = True
                    await message.channel.send(f"Grinding activated for {parts[1]}!", silent=True)
                else:
                    await message.channel.send("Could not find the user you mentioned.")
            else:
                await message.channel.send("You do not have permission to use this command.", silent=True)
            return

        # Send SPINNY sticker to users with grinding active
        if str(message.author.id) in self.sticker_users:
            sticker = discord.utils.get(message.guild.stickers, name="SPINNY")
            if sticker:
                await message.channel.send(stickers=[sticker], silent=True)
            else:
                await message.channel.send("Sticker 'SPINNY' not found.")

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
        if size not in [1, 2, 3, 4]:
            await ctx.send("Invalid size. Please choose a size between 1 and 4.")
            return

        back_emoji = '⬅️'
        first_emoji = '🔙'
        random_emoji = '🎲'
        next_emoji = '➡️'
        no_emoji = '❌'
        number_emojis = ['1️⃣', '2️⃣', '3️⃣', '4️⃣', '5️⃣']
        page = 1
        per_page = 5
        max_retries = 3
        retry = 0
        backoff = 1

        while True:
            messages = []
            session = aiohttp.ClientSession()
            stv = seventv.seventv()
            try:
                if retry == 0:
                    emotes = await stv.emote_search(
                        emote_name, limit=per_page, page=page,
                        case_sensitive=False, exact_match=True
                    )
                    if not emotes:
                        if page == 1:
                            await ctx.send("No emotes found.")
                            break
                        else:
                            await ctx.send("No more emotes, returning to the beginning.")
                            page = 1
                            continue

                    for i, em in enumerate(emotes):
                        url = f"https:{em.host_url}/2x.webp"
                        async with session.get(url) as resp:
                            if resp.status == 200:
                                img = Image.open(io.BytesIO(await resp.read()))
                                ext = 'gif' if getattr(img, "is_animated", False) and img.n_frames > 1 else 'png'
                        msg = await ctx.send(f"https:{em.host_url}/2x.{ext}", silent=True)
                        messages.append(msg)
                        await msg.add_reaction(number_emojis[i])

                    if page > 1:
                        await messages[-1].add_reaction(back_emoji)
                    await messages[-1].add_reaction(first_emoji)
                    await messages[-1].add_reaction(random_emoji)
                    if len(emotes) == per_page:
                        await messages[-1].add_reaction(next_emoji)
                    await messages[-1].add_reaction(no_emoji)

                    def check(reaction, user):
                        return (
                            user == ctx.author
                            and reaction.message.id in [m.id for m in messages]
                            and str(reaction.emoji) in number_emojis[:len(emotes)] + [
                                next_emoji, back_emoji, first_emoji, random_emoji, no_emoji
                            ]
                        )

                    try:
                        reaction, _ = await self.bot.wait_for('reaction_add', timeout=60.0, check=check)
                    except asyncio.TimeoutError:
                        await ctx.send('🚫 No reaction received in time.')
                        for m in messages:
                            try:
                                await m.delete()
                            except discord.NotFound:
                                pass
                        return

                    for m in messages:
                        try:
                            await m.delete()
                        except discord.NotFound:
                            pass

                    emoji_str = str(reaction.emoji)

                    if emoji_str == next_emoji:
                        try:
                            next_emotes = await stv.emote_search(
                                emote_name, limit=per_page, page=page + 1,
                                case_sensitive=False, exact_match=True
                            )
                            if next_emotes:
                                page += 1
                        except Exception as e:
                            if "No Items Found" in str(e):
                                await ctx.send("No more emotes, going back to the beginning.")
                                page = 1
                            elif "Rate Limit Reached" in str(e) and retry < max_retries:
                                wait = backoff * (2 ** retry)
                                await ctx.send(f"Rate limit reached, retrying in {wait}s...")
                                await asyncio.sleep(wait)
                                retry += 1
                            else:
                                await ctx.send(f"An error occurred: {e}")
                                break
                        continue

                    elif emoji_str == back_emoji:
                        page = max(1, page - 1)
                        continue

                    elif emoji_str == first_emoji:
                        page = 1
                        continue

                    elif emoji_str == random_emoji:
                        chosen = random.choice(emotes)
                        async with session.get(f"https:{chosen.host_url}/4x.webp") as resp:
                            if resp.status == 200:
                                img = Image.open(io.BytesIO(await resp.read()))
                                ext = 'gif' if getattr(img, "is_animated", False) and img.n_frames > 1 else 'png'
                        await ctx.send(f"https:{chosen.host_url}/{size}x.{ext}")
                        break

                    elif emoji_str == no_emoji:
                        await ctx.send("None selected... cleaning up...", delete_after=5.0)
                        await ctx.message.delete()
                        return

                    else:
                        idx = number_emojis.index(emoji_str)
                        if idx < len(emotes):
                            chosen = emotes[idx]
                            async with session.get(f"https:{chosen.host_url}/4x.webp") as resp:
                                if resp.status == 200:
                                    img = Image.open(io.BytesIO(await resp.read()))
                                    ext = 'gif' if getattr(img, "is_animated", False) and img.n_frames > 1 else 'png'
                            await ctx.send(f"https:{chosen.host_url}/{size}x.{ext}")
                            break
                        else:
                            await ctx.send("An error occurred")
                            continue

            except Exception as e:
                logging.error(f"Emote command error: {e}")
                err = str(e)
                if "Rate Limit Reached" in err and retry < max_retries:
                    wait = backoff * (2 ** retry)
                    await ctx.send(f"Rate limit reached, retrying in {wait}s...", delete_after=wait)
                    await asyncio.sleep(wait)
                    retry += 1
                    continue
                elif "Search returned no results" in err:
                    if page > 1:
                        await ctx.send("No more emotes, returning to the beginning.")
                        page = 1
                        continue
                    else:
                        await ctx.send("No emotes found.")
                        break
                elif "Server disconnected" in err and retry < max_retries:
                    wait = backoff * (2 ** retry)
                    await ctx.send(f"Retrying in {wait}s...", delete_after=wait)
                    await asyncio.sleep(wait)
                    retry += 1
                    continue
                else:
                    await ctx.send(f"An error occurred: {e}")
                    break
            finally:
                await session.close()
                await stv.close()

            retry = 0


def setup(bot):
    bot.add_cog(Emotes(bot))
