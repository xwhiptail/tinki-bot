import random
import subprocess
from pathlib import Path
from urllib.parse import urlparse

import aiohttp
import discord
import pyfiglet
from discord.ext import commands

from config import (CHANNEL_PINS, GIPHY_API_KEY, GITHUB_REPO_URL,
                    SERVER_FEATURE_REMOVED_MESSAGE, USER_WHIPTAIL_ID, user_matches)

BARK_VARIATIONS = [
    "Bark", "Arf", "Woof", "Bork", "Boof", "Yap", "Yip",
    "Bow-wow", "Ruff", "Wuff", "Borf", "Baroo",
]


class Utility(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    def _repo_root(self):
        return Path(__file__).resolve().parent.parent

    def _github_repo_slug(self):
        parsed = urlparse(GITHUB_REPO_URL)
        path = parsed.path.strip("/")
        if path.endswith(".git"):
            path = path[:-4]
        return path

    def _local_changelog_entries(self, limit):
        try:
            result = subprocess.run(
                [
                    "git",
                    "log",
                    f"-n{limit}",
                    "--pretty=format:%h|%s",
                ],
                cwd=self._repo_root(),
                capture_output=True,
                text=True,
                check=True,
                timeout=5,
            )
        except (OSError, subprocess.SubprocessError):
            return []

        entries = []
        for line in result.stdout.splitlines():
            if "|" not in line:
                continue
            commit_hash, subject = line.split("|", 1)
            commit_hash = commit_hash.strip()
            subject = subject.strip()
            if commit_hash and subject:
                entries.append((commit_hash, subject))
        return entries

    async def _github_changelog_entries(self, limit):
        slug = self._github_repo_slug()
        if not slug:
            return []

        url = f"https://api.github.com/repos/{slug}/commits?per_page={limit}"
        async with aiohttp.ClientSession() as session:
            async with session.get(url) as response:
                if response.status != 200:
                    return []
                payload = await response.json()

        entries = []
        for item in payload:
            commit_hash = (item.get("sha") or "")[:7]
            subject = item.get("commit", {}).get("message", "").splitlines()[0].strip()
            if commit_hash and subject:
                entries.append((commit_hash, subject))
        return entries

    async def _get_changelog_entries(self, limit):
        entries = self._local_changelog_entries(limit)
        if entries:
            return entries
        try:
            return await self._github_changelog_entries(limit)
        except aiohttp.ClientError:
            return []

    def _render_changelog(self, entries):
        lines = ["Recent changes:"]
        for commit_hash, subject in entries:
            lines.append(f"`{commit_hash}` - {subject}")
        return "\n".join(lines)

    @commands.Cog.listener()
    async def on_raw_reaction_add(self, payload):
        """Forward 📌 reactions to the #pins channel."""
        if payload.user_id == self.bot.user.id:
            return
        if str(payload.emoji) != '📌':
            return

        channel = self.bot.get_channel(payload.channel_id)
        if not channel:
            return
        try:
            message = await channel.fetch_message(payload.message_id)
        except discord.NotFound:
            return

        pins_channel = discord.utils.get(
            message.guild.channels, name=CHANNEL_PINS, type=discord.ChannelType.text
        )
        if pins_channel:
            embed = discord.Embed(title="Pinned Message", description=message.content, color=0x00ff00)
            embed.add_field(name="Original Author", value=message.author.display_name, inline=False)
            embed.add_field(name="Timestamp", value=message.created_at.strftime("%Y-%m-%d %H:%M:%S"), inline=False)
            if message.attachments:
                embed.set_image(url=message.attachments[0].url)
            embed.add_field(name="Link", value=f"[Jump to message]({message.jump_url})", inline=False)
            await pins_channel.send(embed=embed, silent=True)
            await message.add_reaction('✅')
            user = payload.member or await message.guild.fetch_member(payload.user_id)
            await message.remove_reaction(payload.emoji, user)
        else:
            await message.add_reaction('❌')

    async def _fetch_url(self, session, url):
        async with session.get(url) as response:
            return await response.json()

    @commands.command(name='purge')
    async def purge_bot_messages(self, ctx):
        if not user_matches(ctx.author, USER_WHIPTAIL_ID, 'whiptail'):
            await ctx.send("You do not have permission to use this command.")
            return
        import re
        pattern = re.compile(r'^\$\w+')
        def is_purgeable(m):
            return (
                m.author == self.bot.user
                or m.content.startswith('!')
                or pattern.match(m.content)
                or self.bot.user in m.mentions
            )
        deleted = await ctx.channel.purge(limit=100, check=is_purgeable)
        await ctx.send(f"Deleted {len(deleted)} messages.", delete_after=5)

    @commands.command(name='gif')
    async def send_gif(self, ctx):
        try:
            async with aiohttp.ClientSession() as session:
                resp = await session.get(
                    f"https://api.giphy.com/v1/gifs/random?api_key={GIPHY_API_KEY}&tag=bowling&rating=g"
                )
                data = await resp.json()
                url = data.get('data', {}).get('images', {}).get('original', {}).get('url')
                if url:
                    await ctx.send(url)
                else:
                    await ctx.send("Unexpected API response structure.")
        except Exception as e:
            await ctx.send(f"Error fetching GIF: {e}")

    @commands.command(name='random')
    async def random_cmd(self, ctx):
        try:
            pinned = await ctx.channel.pins()
            if not pinned:
                await ctx.send("There are no pinned messages in this channel.")
                return
            msg = random.choice(pinned)
            author_info = f"Message by {msg.author.display_name} [Jump to message]({msg.jump_url})"
            if msg.content:
                await ctx.send(f"{author_info}\n\n{msg.content}")
            else:
                await ctx.send(author_info)
            if msg.attachments:
                await ctx.send(msg.attachments[0].url)
        except Exception as e:
            await ctx.send(f"An error occurred: {e}")

    @commands.command()
    async def roulette(self, ctx):
        try:
            async with aiohttp.ClientSession() as session:
                resp = await session.get(f"https://api.giphy.com/v1/gifs/random?api_key={GIPHY_API_KEY}")
                data = await resp.json()
                url = data.get('data', {}).get('images', {}).get('original', {}).get('url')
                if url:
                    await ctx.send(url)
                else:
                    await ctx.send("Unexpected API response structure.")
        except Exception as e:
            await ctx.send(f"Error fetching GIF: {e}")

    @commands.command()
    async def cat(self, ctx):
        async with aiohttp.ClientSession() as session:
            try:
                data = await self._fetch_url(session, 'https://api.thecatapi.com/v1/images/search')
                if data:
                    embed = discord.Embed()
                    embed.set_image(url=data[0]['url'])
                    await ctx.send(embed=embed)
                else:
                    await ctx.send("Error fetching cat image.")
            except Exception as e:
                await ctx.send(f"Error fetching cat image: {e}")

    @commands.command()
    async def dog(self, ctx):
        async with aiohttp.ClientSession() as session:
            try:
                data = await self._fetch_url(session, 'https://dog.ceo/api/breeds/image/random')
                if data and data['status'] == 'success':
                    embed = discord.Embed()
                    embed.set_image(url=data['message'])
                    await ctx.send(embed=embed)
                else:
                    await ctx.send(f"Dog API responded unexpectedly: {data}")
            except Exception as e:
                await ctx.send(f"Error fetching dog image: {e}")

    @commands.command()
    async def dogbark(self, ctx):
        await ctx.send(f"```\n{pyfiglet.figlet_format(random.choice(BARK_VARIATIONS))}\n```")

    @commands.command()
    async def ss(self, ctx):
        await ctx.send(
            "https://cdn.discordapp.com/attachments/616874355821117483/1210844596263854120/redirect.jpg"
            "?ex=65ec09e8&is=65d994e8&hm=f8337efba567168da864124a7d3364381e322e436fb5ff02821219b65e649d19&"
        )

    @commands.command(name='github')
    async def github_repo(self, ctx):
        await ctx.send(f"Tinki-bot source: {GITHUB_REPO_URL}")

    @commands.command(name='changelog')
    async def changelog(self, ctx, count: int = 5):
        limit = max(1, min(count, 10))
        entries = await self._get_changelog_entries(limit)
        if not entries:
            await ctx.send("I couldn't read recent commits right now.")
            return
        await ctx.send(self._render_changelog(entries))

    @commands.command(name='commands')
    async def show_commands(self, ctx):
        part1 = """
**Bot Commands List - Part 1**

`!pb` - Shows Jun's personal best score.
`!avg` - Shows Jun's average score.
`!all` - Displays all of Jun's scores with timestamps.
`!delete [timestamp]` - Deletes a score with the specified timestamp.
`!bowlinggraph` - Generates a scatterplot of Jun's scores over time.
`!bowlingdistgraph` - Generates a KDE plot of Jun's scores over time.
`!commands` - Shows this list of available commands.
`!add [score] '%Y-%m-%d %H:%M:%S'` - Allows you to add a bowling score.
`!median` - Shows Jun's median score.
`!purge` - Purges messages sent by the bot. Only usable by whiptail.
`!gif` - Posts a random bowling gif.
`!random` - Posts a random pinned message to the chat.
`!remind` - Shows the reminder command format.
`!remindme in [x]` - Sets a reminder with a link to the message.
`!remindme` - Lists upcoming reminders.
`!deletereminder [ID]` - Deletes a reminder with the specified ID.
`!currenttime` - Shows the current server time.
`!github` - Links to the bot source repository.
`!changelog [count]` - Shows recent commit summaries.
`!awscost` - Shows AWS month-to-date and projected monthly cost (admin only).
`!statusreport` - Shows EC2/runtime status with a summary plus attachment (admin only).
        """
        part2 = """
**Bot Commands List - Part 2**

`$[emotename] [number]` - Sends the emote as the bot the number of times (optional).
`$randomemote [number]` - Sends a random emote as the bot the number of times (optional).
`!allemotes` - Lists all available emotes to send.
`!roulette` - Sends a random gif.
`!cat` - Sends a random cat.
`!dog` - Sends a random dog.
`!dogbark` - Sends a random bark word in block letters.
`!emote [name] [1x-4x]` - search 7TV, preview results in the picker, choose a size, and send
`!spinny @[user]` - grinding activated for @user
`!stopspinny @[user]` - grinding deactivated for @user
`!sussy` - shows how sussy lhea is
`!sussygraph` - graphs lhea's sussy
`!explode` - shows how many times Whiptail exploded
`!explodegraph` - graph of explode
        """
        part3 = """
**Bot Commands List - Part 3**
`!grindcount` - shows how many times grinding happened
`!grindgraph` - graph of grinding over time
`!startminecraft` - retired command; server hosting was removed
`!stopminecraft` - retired command; server hosting was removed
`!minecraftstatus` - retired command; server hosting was removed
`!minecraftserver` - retired command; server hosting was removed
`!startskyfactory` - retired command; server hosting was removed
`!stopskyfactory` - retired command; server hosting was removed
`!skyfactorystatus` - retired command; server hosting was removed
`!skyfactoryserver` - retired command; server hosting was removed
`!uptime` - retired command placeholder
`!testurls` - tests the url rewrites
`!runtests` - unit tests for the commands
`!restart` - restarts the bot (admin only)
`!deploy` - pulls latest from GitHub and restarts (admin only)
`!awscost` - shows AWS month-to-date and projected monthly cost (admin only)
`!statusreport` - shows EC2/runtime status with a summary plus attachment (admin only)

**Uma Musume**
`!gacha [1|10]` - simulate pulls (3% SSR, pity at 200)
`!pity [@user]` - show pity counter and progress bar
`!uma [@user]` - assign a random horse girl
`!race @user1 @user2 ...` - GPT-narrated race between members
`!umagif` - random Uma Musume gif
        """
        try:
            await ctx.author.send(part1)
            await ctx.author.send(part2)
            await ctx.author.send(part3)
            await ctx.send(f"{ctx.author.mention}, I've sent you a DM with the list of commands!")
        except discord.Forbidden:
            await ctx.send(f"{ctx.author.mention}, I couldn't send you a DM. Please check your privacy settings.")

    # Retired server commands
    @commands.command()
    async def startminecraft(self, ctx):
        await ctx.send(SERVER_FEATURE_REMOVED_MESSAGE)

    @commands.command()
    async def stopminecraft(self, ctx):
        await ctx.send(SERVER_FEATURE_REMOVED_MESSAGE)

    @commands.command()
    async def minecraftstatus(self, ctx):
        await ctx.send(SERVER_FEATURE_REMOVED_MESSAGE)

    @commands.command(name='minecraftserver')
    async def fetch_server_ip(self, ctx):
        await ctx.send(SERVER_FEATURE_REMOVED_MESSAGE)

    @commands.command()
    async def startskyfactory(self, ctx):
        await ctx.send(SERVER_FEATURE_REMOVED_MESSAGE)

    @commands.command()
    async def stopskyfactory(self, ctx):
        await ctx.send(SERVER_FEATURE_REMOVED_MESSAGE)

    @commands.command()
    async def skyfactorystatus(self, ctx):
        await ctx.send(SERVER_FEATURE_REMOVED_MESSAGE)

    @commands.command(name='skyfactoryserver')
    async def fetch_skyfactory_ip(self, ctx):
        await ctx.send(SERVER_FEATURE_REMOVED_MESSAGE)

    @commands.command(name='uptime')
    async def uptime(self, ctx):
        await ctx.send(SERVER_FEATURE_REMOVED_MESSAGE)


async def setup(bot):
    await bot.add_cog(Utility(bot))
