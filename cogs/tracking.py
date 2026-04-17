import json
import re
from datetime import datetime, timedelta

import discord
import matplotlib.dates as mdates
import matplotlib.pyplot as plt
from discord.ext import commands

from config import (DATA_DIR, EXPLODE_FILE, SPINNY_FILE, STICKER_SPINNY, SUS_FILE,
                    USER_LHEA_ID, USER_WHIPTAIL_ID, user_matches)


class Tracking(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.sus_and_sticker_usage = []
        self.explode = []
        self.spinny = []
        self._load_sus()
        self._load_explode()
        self._load_spinny()

    def _load_sus(self):
        try:
            with open(SUS_FILE, 'r') as f:
                self.sus_and_sticker_usage = json.load(f)
        except FileNotFoundError:
            self.sus_and_sticker_usage = []

    def _save_sus(self):
        with open(SUS_FILE, 'w') as f:
            json.dump(self.sus_and_sticker_usage, f, indent=4, default=str)

    def _load_explode(self):
        try:
            with open(EXPLODE_FILE, 'r') as f:
                self.explode = json.load(f)
        except FileNotFoundError:
            self.explode = []

    def _save_explode(self):
        with open(EXPLODE_FILE, 'w') as f:
            json.dump(self.explode, f, indent=4, default=str)

    def _load_spinny(self):
        try:
            with open(SPINNY_FILE, 'r') as f:
                self.spinny = json.load(f)
        except FileNotFoundError:
            self.spinny = []

    def _save_spinny(self):
        with open(SPINNY_FILE, 'w') as f:
            json.dump(self.spinny, f, indent=4, default=str)

    def _make_entry(self, message):
        return {
            'user_id': message.author.id,
            'timestamp': message.created_at.isoformat(),
            'message_id': message.id,
        }

    @commands.Cog.listener()
    async def on_message(self, message):
        if message.author.bot or message.content.startswith('!'):
            return

        # Track whiptail's :explode: usage
        if user_matches(message.author, USER_WHIPTAIL_ID, 'whiptail') and ":explode:" in message.content.lower():
            self.explode.append(self._make_entry(message))
            self._save_explode()

        # Track SPINNY sticker usage
        if any(s.name == STICKER_SPINNY for s in message.stickers):
            self.spinny.append(self._make_entry(message))
            self._save_spinny()

        # Track lhea's sus usage
        if user_matches(message.author, USER_LHEA_ID, 'lhea.'):
            sus_count = len(re.findall(r'\bsus\b', message.content, re.IGNORECASE))
            sussy_count = len(re.findall(r'\bsussy\b', message.content, re.IGNORECASE))
            sticker_count = sum(s.name.lower() in ["sussydoge", "sus"] for s in message.stickers)
            emoji_count = sum(
                "sus" in e.name.lower() for e in message.guild.emojis if str(e) in message.content
            )
            total = sus_count + sussy_count + sticker_count + emoji_count
            for _ in range(total):
                self.sus_and_sticker_usage.append(self._make_entry(message))
            if total > 0:
                self._save_sus()

    def _build_cumulative_graph(self, data, title, xlabel, start_date, filename):
        data_sorted = sorted(data, key=lambda x: x['timestamp'])
        timestamps = [datetime.fromisoformat(e['timestamp']) for e in data_sorted]
        filtered_ts = [timestamps[0]]
        filtered_counts = [1]
        for i in range(1, len(timestamps)):
            if timestamps[i] >= filtered_ts[-1]:
                filtered_ts.append(timestamps[i])
                filtered_counts.append(len(filtered_ts))
        plt.figure(figsize=(15, 6))
        plt.scatter(filtered_ts, filtered_counts)
        plt.gca().xaxis.set_major_formatter(mdates.DateFormatter('%Y-%m'))
        plt.gca().xaxis.set_major_locator(mdates.MonthLocator())
        plt.xlim([start_date, max(filtered_ts) + timedelta(days=30)])
        plt.grid(False)
        plt.gcf().autofmt_xdate()
        plt.xlabel('Date')
        plt.ylabel('Cumulative Count')
        plt.title(title)
        path = str(DATA_DIR / filename)
        plt.savefig(path)
        plt.close()
        return path

    @commands.command(name='sussy')
    async def sussy_count(self, ctx):
        await ctx.send(f"Lhea has used 'sus' a total of {len(self.sus_and_sticker_usage)} times.")

    @commands.command(name='sussygraph')
    async def sussy_graph(self, ctx):
        try:
            path = self._build_cumulative_graph(
                self.sus_and_sticker_usage, 'Lhea "sus" Usage Over Time', 'Date',
                datetime(2020, 1, 1), 'sussy_usage_graph.png'
            )
            await ctx.send(file=discord.File(path))
        except Exception as e:
            await ctx.send(f"Error: {e}")

    @commands.command(name='explode')
    async def explode_count(self, ctx):
        emote_name = 'explode'
        emote = discord.utils.get(ctx.guild.emojis, name=emote_name)
        if not emote:
            all_emotes = [e for g in self.bot.guilds for e in g.emojis if e.available]
            emote = discord.utils.find(lambda e: e.name == emote_name, all_emotes)
        emote_str = str(emote) if emote else ''
        await ctx.send(f"Whiptail has {emote_str} a total of {len(self.explode)} times.")

    @commands.command(name='explodegraph')
    async def explode_graph(self, ctx):
        try:
            path = self._build_cumulative_graph(
                self.explode, "Whiptail's Explosions Over Time", 'Date',
                datetime(2022, 4, 1), 'explode_usage_graph.png'
            )
            await ctx.send(file=discord.File(path))
        except Exception as e:
            await ctx.send(f"Error: {e}")

    @commands.command(name='grindcount')
    async def spinny_count(self, ctx):
        await ctx.send(f"Grinding has occurred {len(self.spinny)} times.")

    @commands.command(name='grindgraph')
    async def spinny_graph(self, ctx):
        try:
            path = self._build_cumulative_graph(
                self.spinny, 'Grinding Usage Over Time', 'Date',
                datetime(2021, 10, 1), 'spinny_usage_graph.png'
            )
            await ctx.send(file=discord.File(path))
        except Exception as e:
            await ctx.send(f"Error: {e}")


def setup(bot):
    bot.add_cog(Tracking(bot))
