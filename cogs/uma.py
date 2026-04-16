import json
import random
from typing import Optional

import aiohttp
import discord
from discord.ext import commands

import config
from config import (
    GIPHY_API_KEY,
    GREMLIN_SYSTEM_STYLE,
    OPENAI_MODEL,
    UMA_PITY_CAP,
    UMA_R,
    UMA_SR,
    UMA_SR_RATE,
    UMA_SSR,
    UMA_SSR_RATE,
)
from utils.openai_helpers import get_openai_client


class Uma(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.pity_file = config.UMA_PITY_FILE

    def load_pity(self) -> dict:
        try:
            with open(self.pity_file) as f:
                return json.load(f)
        except (FileNotFoundError, json.JSONDecodeError):
            return {}

    def save_pity(self, data: dict):
        with open(self.pity_file, 'w') as f:
            json.dump(data, f, indent=2)

    def _single_pull(self, pity: int) -> tuple:
        """Return (rarity, name, new_pity). Forces SSR at cap."""
        force = pity + 1 >= UMA_PITY_CAP
        roll = random.random()
        if force or roll < UMA_SSR_RATE:
            return ("SSR", random.choice(UMA_SSR), 0)
        if roll < UMA_SSR_RATE + UMA_SR_RATE:
            return ("SR", random.choice(UMA_SR), pity + 1)
        return ("R", random.choice(UMA_R), pity + 1)

    def _featured_pull(self, pulls):
        for pull_rarity, name in pulls:
            if pull_rarity == "SSR":
                return pull_rarity, name
        return None

    def _gif_query(self, horse_name: Optional[str] = None) -> str:
        if horse_name:
            return f"{horse_name} uma musume"
        return "uma musume"

    async def _gif(self, horse_name: Optional[str] = None) -> Optional[str]:
        if not GIPHY_API_KEY:
            return None
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    "https://api.giphy.com/v1/gifs/search",
                    params={
                        "api_key": GIPHY_API_KEY,
                        "q": self._gif_query(horse_name),
                        "limit": 25,
                        "rating": "g",
                    },
                ) as resp:
                    data = await resp.json()
                    items = data.get("data", [])
                    if items:
                        return random.choice(items)["images"]["original"]["url"]
        except Exception:
            pass
        return None

    @commands.command(name="gacha")
    async def uma_gacha(self, ctx, count: int = 10):
        if count not in (1, 10):
            await ctx.send("Pull 1 or 10 at a time.")
            return

        pity_data = self.load_pity()
        uid = str(ctx.author.id)
        pity = pity_data.get(uid, 0)
        pulls = []
        for _ in range(count):
            rarity, name, pity = self._single_pull(pity)
            pulls.append((rarity, name))
        pity_data[uid] = pity
        self.save_pity(pity_data)

        ssrs = [name for rarity, name in pulls if rarity == "SSR"]
        srs = [name for rarity, name in pulls if rarity == "SR"]
        r_count = sum(1 for rarity, _ in pulls if rarity == "R")

        lines = []
        for name in ssrs:
            lines.append(f"* **[SSR] {name}**")
        for name in srs:
            lines.append(f"+ [SR] {name}")
        if r_count:
            lines.append(f"- [R] x{r_count}")

        result = "\n".join(lines) if lines else "- [R] x10"
        featured_pull = self._featured_pull(pulls)
        gif = await self._gif(featured_pull[1]) if featured_pull else None

        if ssrs:
            footer = f"\nSSR! You got: **{', '.join(ssrs)}** (pity reset to 0)"
        else:
            footer = f"\n*Pity: {pity}/{UMA_PITY_CAP}*"

        await ctx.send(f"**{ctx.author.display_name}'s pull results:**\n{result}{footer}")
        if gif:
            await ctx.send(gif)

    @commands.command(name="pity")
    async def uma_pity(self, ctx, member: discord.Member = None):
        target = member or ctx.author
        pity_data = self.load_pity()
        pity = pity_data.get(str(target.id), 0)
        remaining = UMA_PITY_CAP - pity
        bar = "#" * (pity // 10) + "." * ((UMA_PITY_CAP - pity) // 10)
        await ctx.send(
            f"**{target.display_name}'s pity:** {pity}/{UMA_PITY_CAP} "
            f"({remaining} pulls until guaranteed SSR)\n`{bar}`"
        )

    @commands.command(name="uma")
    async def uma_assign(self, ctx, member: discord.Member = None):
        target = member or ctx.author
        rarity = random.choices(
            ["SSR", "SR", "R"],
            weights=[UMA_SSR_RATE, UMA_SR_RATE, 1 - UMA_SSR_RATE - UMA_SR_RATE],
        )[0]
        pool = {"SSR": UMA_SSR, "SR": UMA_SR, "R": UMA_R}[rarity]
        horse = random.choice(pool)
        prefix = "*" if rarity == "SSR" else ("+" if rarity == "SR" else "-")
        await ctx.send(f"{prefix} **{target.display_name}** is **{horse}** [{rarity}]")

    @commands.command(name="race")
    async def uma_race(self, ctx, *members: discord.Member):
        if len(members) < 2:
            await ctx.send("Tag at least 2 people to race.")
            return
        names = [m.display_name for m in members]
        client = get_openai_client()
        prompt = (
            f"Narrate a short, chaotic Uma Musume horse race between: {', '.join(names)}. "
            "Pick a winner. Keep it under 4 sentences. Be dramatic and funny."
        )
        completion = client.chat.completions.create(
            model=OPENAI_MODEL,
            messages=[
                {"role": "system", "content": GREMLIN_SYSTEM_STYLE},
                {"role": "user", "content": prompt},
            ],
        )
        result = completion.choices[0].message.content if completion.choices else "The race exploded. No winner."
        gif = await self._gif()
        await ctx.send(f"RACE START\n{result}")
        if gif:
            await ctx.send(gif)

    @commands.command(name="umagif")
    async def uma_gif_cmd(self, ctx):
        gif = await self._gif()
        if gif:
            await ctx.send(gif)
        else:
            await ctx.send("Giphy came up empty. The gremlin is disappointed.")


def setup(bot):
    bot.add_cog(Uma(bot))
