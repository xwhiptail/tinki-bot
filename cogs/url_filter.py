import asyncio

import discord
from discord.ext import commands

from config import (
    TWITTER_COM_PATTERN, X_COM_PATTERN, INSTAGRAM_COM_PATTERN,
    TIKTOK_COM_PATTERN, REDDIT_COM_PATTERN, TWITCH_CLIP_PATTERN,
)
from utils.url_rewriter import rewrite_social_urls

_SOCIAL_PATTERNS = [
    TWITTER_COM_PATTERN,
    X_COM_PATTERN,
    INSTAGRAM_COM_PATTERN,
    TIKTOK_COM_PATTERN,
    REDDIT_COM_PATTERN,
]


class URLFilter(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.Cog.listener()
    async def on_message(self, message):
        if message.author.bot:
            return

        # Social URL rewrites
        if any(p.search(message.content) for p in _SOCIAL_PATTERNS):
            rewritten = rewrite_social_urls(message.content)
            if rewritten != message.content:
                await message.channel.send(
                    f"{message.author.mention} originally posted: {rewritten}", silent=True
                )
                await message.delete()
                await asyncio.sleep(3)

        # Twitch clip embed fix
        if TWITCH_CLIP_PATTERN.search(message.content):
            if any(embed.type == 'video' for embed in message.embeds):
                return
            base_url = TWITCH_CLIP_PATTERN.search(message.content).group(1)
            for suffix in ['#', '?a', '?b', '?c', '?d', '?e']:
                sent = await message.channel.send(
                    f"{message.author.mention} originally posted: {base_url}{suffix}", silent=True
                )
                await asyncio.sleep(3)
                sent = await message.channel.fetch_message(sent.id)
                if any(embed.type == 'video' for embed in sent.embeds):
                    break
                await sent.delete()
            await message.delete()


def setup(bot):
    bot.add_cog(URLFilter(bot))
