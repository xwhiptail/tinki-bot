import html
import json
import random
import re
from typing import Optional

import aiohttp
import discord
from discord.ext import commands

import config
from config import (
    GIPHY_API_KEY,
    GREMLIN_SYSTEM_STYLE,
    OPENAI_MODEL,
    UMA_67_TRIGGER_NAME,
    UMA_CHARACTER_GIF_URLS,
    UMA_CHARACTER_IMAGE_URLS,
    UMA_NON_SSR_DELETE_AFTER,
    UMA_PITY_CAP,
    UMA_PROFILE_BASE_URL,
    UMA_PROFILE_SLUGS,
    UMA_R,
    UMA_SR,
    UMA_SR_RATE,
    UMA_SSR,
    UMA_SSR_RATE,
)
from utils.openai_helpers import get_openai_client

META_IMAGE_PATTERNS = (
    re.compile(r'<meta[^>]+property=["\']og:image["\'][^>]+content=["\']([^"\']+)["\']', re.IGNORECASE),
    re.compile(r'<meta[^>]+content=["\']([^"\']+)["\'][^>]+property=["\']og:image["\']', re.IGNORECASE),
    re.compile(r'<meta[^>]+name=["\']twitter:image["\'][^>]+content=["\']([^"\']+)["\']', re.IGNORECASE),
    re.compile(r'<meta[^>]+content=["\']([^"\']+)["\'][^>]+name=["\']twitter:image["\']', re.IGNORECASE),
)
UMA_67_PATTERN = re.compile(r'(?<!\d)6(?:[\s\W_]*)7(?!\d)')
UMA_REPULL_EMOJI = '♻️'
UMA_REPULL_TIMEOUT = 30.0


class Uma(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.pity_file = config.UMA_PITY_FILE
        self.profile_image_cache = {}

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
            return ('SSR', random.choice(UMA_SSR), 0)
        if roll < UMA_SSR_RATE + UMA_SR_RATE:
            return ('SR', random.choice(UMA_SR), pity + 1)
        return ('R', random.choice(UMA_R), pity + 1)

    def _featured_pull(self, pulls):
        for pull_rarity, name in pulls:
            if pull_rarity == 'SSR':
                return pull_rarity, name
        return None

    def _gif_queries(self, horse_name: Optional[str] = None):
        if not horse_name:
            return ['uma musume']

        aliases = {
            'Vodka': [
                'ウオッカ ウマ娘',
                'Uma Musume Vodka',
                'Vodka uma musume',
            ],
            'Curren Chan': [
                'Curren Chan uma musume',
                'Uma Musume Curren Chan',
                'カレンチャン ウマ娘',
            ],
            'T.M. Opera O': [
                'T M Opera O uma musume',
                'TM Opera O uma musume',
                'T.M. Opera O uma musume',
            ],
        }

        base_queries = [
            f'{horse_name} uma musume',
            f'uma musume {horse_name}',
            f'{horse_name} anime',
        ]

        seen = set()
        ordered = []
        for query in aliases.get(horse_name, []) + base_queries:
            key = query.casefold()
            if key not in seen:
                seen.add(key)
                ordered.append(query)
        return ordered

    def _gif_match_terms(self, horse_name: str):
        terms = {horse_name.casefold(), 'uma musume', 'umamusume'}
        special_terms = {
            'Vodka': {'ウオッカ', 'vodka', 'uma musume', 'umamusume'},
            'Curren Chan': {'curren chan', 'karen chan', 'カレンチャン', 'uma musume', 'umamusume'},
            'T.M. Opera O': {'t.m. opera o', 'tm opera o', 't m opera o', 'uma musume', 'umamusume'},
        }
        return special_terms.get(horse_name, terms)

    def _gif_matches_horse(self, item: dict, horse_name: Optional[str]) -> bool:
        if not horse_name:
            return True

        text = ' '.join(str(item.get(key, '')) for key in ('title', 'slug', 'username')).casefold()
        terms = self._gif_match_terms(horse_name)
        has_horse = any(term in text for term in terms if term not in {'uma musume', 'umamusume'})
        has_series = 'uma musume' in text or 'umamusume' in text or 'ウマ娘' in text
        return has_horse and has_series

    async def _gif(self, horse_name: Optional[str] = None) -> Optional[str]:
        if not GIPHY_API_KEY:
            return None
        try:
            async with aiohttp.ClientSession() as session:
                for query in self._gif_queries(horse_name):
                    async with session.get(
                        'https://api.giphy.com/v1/gifs/search',
                        params={
                            'api_key': GIPHY_API_KEY,
                            'q': query,
                            'limit': 25,
                            'rating': 'g',
                        },
                    ) as resp:
                        data = await resp.json()
                        items = data.get('data', [])
                        if not items:
                            continue

                        if horse_name:
                            items = [item for item in items if self._gif_matches_horse(item, horse_name)]
                            if not items:
                                continue

                        return random.choice(items)['images']['original']['url']
        except Exception:
            pass
        return None

    @staticmethod
    def _extract_meta_image_url(page_html: str) -> Optional[str]:
        for pattern in META_IMAGE_PATTERNS:
            match = pattern.search(page_html)
            if match:
                return html.unescape(match.group(1))
        return None

    @staticmethod
    def _matches_67_trigger(content: str) -> bool:
        return bool(UMA_67_PATTERN.search(content))

    def _character_profile_url(self, name: str) -> Optional[str]:
        slug = UMA_PROFILE_SLUGS.get(name)
        if not slug:
            return None
        return f'{UMA_PROFILE_BASE_URL}/{slug}'

    async def _character_image_url(self, name: str) -> Optional[str]:
        if name in self.profile_image_cache:
            return self.profile_image_cache[name]

        profile_url = self._character_profile_url(name)
        if not profile_url:
            return None

        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(profile_url) as resp:
                    if resp.status != 200:
                        return None
                    page_html = await resp.text()
        except Exception:
            return None

        image_url = self._extract_meta_image_url(page_html)
        if image_url:
            self.profile_image_cache[name] = image_url
        return image_url

    async def _send_character_media(self, destination, name: str) -> bool:
        explicit_gif = UMA_CHARACTER_GIF_URLS.get(name)
        if explicit_gif:
            await destination.send(explicit_gif)
            return True

        profile_url = self._character_profile_url(name)
        explicit_image = UMA_CHARACTER_IMAGE_URLS.get(name)
        if explicit_image:
            embed = discord.Embed(title=name, url=profile_url)
            embed.set_image(url=explicit_image)
            await destination.send(embed=embed)
            return True

        gif = await self._gif(name)
        if gif:
            await destination.send(gif)
            return True

        image_url = await self._character_image_url(name)
        if image_url:
            embed = discord.Embed(title=name, url=profile_url)
            embed.set_image(url=image_url)
            await destination.send(embed=embed)
            return True

        if profile_url:
            await destination.send(profile_url)
            return True

        return False

    async def _send_gacha_results(self, ctx, count: int):
        pity_data = self.load_pity()
        uid = str(ctx.author.id)
        pity = pity_data.get(uid, 0)
        pulls = []
        for _ in range(count):
            rarity, name, pity = self._single_pull(pity)
            pulls.append((rarity, name))
        pity_data[uid] = pity
        self.save_pity(pity_data)

        ssrs = [name for rarity, name in pulls if rarity == 'SSR']
        srs = [name for rarity, name in pulls if rarity == 'SR']
        r_count = sum(1 for rarity, _ in pulls if rarity == 'R')

        lines = []
        for name in ssrs:
            lines.append(f'* **[SSR] {name}**')
        for name in srs:
            lines.append(f'+ [SR] {name}')
        if r_count:
            lines.append(f'- [R] x{r_count}')

        result = '\n'.join(lines) if lines else f'- [R] x{count}'
        if ssrs:
            footer = f"\nSSR! You got: **{', '.join(ssrs)}** (pity reset to 0)"
        else:
            footer = f'\n*Pity: {pity}/{UMA_PITY_CAP}*'

        result_message = await ctx.send(
            f"**{ctx.author.display_name}'s pull results:**\n{result}{footer}",
            delete_after=None if ssrs else UMA_NON_SSR_DELETE_AFTER,
        )
        for name in ssrs:
            await self._send_character_media(ctx, name)
        return result_message

    async def _offer_repull(self, ctx, result_message, count: int):
        try:
            await result_message.add_reaction(UMA_REPULL_EMOJI)
        except (discord.Forbidden, discord.HTTPException, AttributeError):
            return

        def check(reaction, user):
            return (
                reaction.message.id == result_message.id
                and str(reaction.emoji) == UMA_REPULL_EMOJI
                and user.id == ctx.author.id
            )

        try:
            await self.bot.wait_for('reaction_add', timeout=UMA_REPULL_TIMEOUT, check=check)
        except Exception:
            try:
                await result_message.remove_reaction(UMA_REPULL_EMOJI, ctx.bot.user)
            except (discord.Forbidden, discord.HTTPException, AttributeError):
                pass
            return

        await self.uma_gacha(ctx, count)

    @commands.Cog.listener()
    async def on_message(self, message):
        if message.author.bot:
            return
        if message.content.startswith(('!', '$')):
            return
        if not self._matches_67_trigger(message.content):
            return
        await self._send_character_media(message.channel, UMA_67_TRIGGER_NAME)

    @commands.command(name='gacha')
    async def uma_gacha(self, ctx, count: int = 10):
        if count not in (1, 10):
            await ctx.send('Pull 1 or 10 at a time.')
            return
        result_message = await self._send_gacha_results(ctx, count)
        await self._offer_repull(ctx, result_message, count)

    @commands.command(name='pity')
    async def uma_pity(self, ctx, member: discord.Member = None):
        target = member or ctx.author
        pity_data = self.load_pity()
        pity = pity_data.get(str(target.id), 0)
        remaining = UMA_PITY_CAP - pity
        bar = '#' * (pity // 10) + '.' * ((UMA_PITY_CAP - pity) // 10)
        await ctx.send(
            f"**{target.display_name}'s pity:** {pity}/{UMA_PITY_CAP} "
            f"({remaining} pulls until guaranteed SSR)\n`{bar}`"
        )

    @commands.command(name='uma')
    async def uma_assign(self, ctx, member: discord.Member = None):
        target = member or ctx.author
        rarity = random.choices(
            ['SSR', 'SR', 'R'],
            weights=[UMA_SSR_RATE, UMA_SR_RATE, 1 - UMA_SSR_RATE - UMA_SR_RATE],
        )[0]
        pool = {'SSR': UMA_SSR, 'SR': UMA_SR, 'R': UMA_R}[rarity]
        horse = random.choice(pool)
        prefix = '*' if rarity == 'SSR' else ('+' if rarity == 'SR' else '-')
        await ctx.send(f'{prefix} **{target.display_name}** is **{horse}** [{rarity}]')

    @commands.command(name='race')
    async def uma_race(self, ctx, *members: discord.Member):
        if len(members) < 2:
            await ctx.send('Tag at least 2 people to race.')
            return
        names = [m.display_name for m in members]
        client = get_openai_client()
        prompt = (
            f"Narrate a short, chaotic Uma Musume horse race between: {', '.join(names)}. "
            'Pick a winner. Keep it under 4 sentences. Be dramatic and funny.'
        )
        completion = client.chat.completions.create(
            model=OPENAI_MODEL,
            messages=[
                {'role': 'system', 'content': GREMLIN_SYSTEM_STYLE},
                {'role': 'user', 'content': prompt},
            ],
        )
        result = completion.choices[0].message.content if completion.choices else 'The race exploded. No winner.'
        gif = await self._gif()
        await ctx.send(f'RACE START\n{result}')
        if gif:
            await ctx.send(gif)

    @commands.command(name='umagif')
    async def uma_gif_cmd(self, ctx):
        gif = await self._gif()
        if gif:
            await ctx.send(gif)
        else:
            await ctx.send('Giphy came up empty. The gnome is annoyed.')


async def setup(bot):
    await bot.add_cog(Uma(bot))
