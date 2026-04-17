import asyncio
import json
import logging
import matplotlib.dates as mdates
import matplotlib.pyplot as plt
import numpy as np
import seaborn as sns
import discord
from datetime import datetime, timezone
from discord.ext import commands
from scipy.stats import linregress

from config import SCORES_FILE, DATA_DIR, SCORE_PATTERN, USER_CATE_ID, user_matches


class Bowling(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.scores = []
        self._load()

    def _load(self):
        try:
            with open(SCORES_FILE, 'r') as f:
                data = json.load(f)
                self.scores = [
                    (int(score), datetime.fromisoformat(ts)) for score, ts in data
                ]
        except FileNotFoundError:
            self.scores = []

    def _save(self):
        for i, (score, ts) in enumerate(self.scores):
            if ts.tzinfo is None or ts.tzinfo.utcoffset(ts) is None:
                self.scores[i] = (score, ts.replace(tzinfo=timezone.utc))
        unique = list({(s, t.isoformat()): (s, t) for s, t in self.scores}.values())
        unique.sort(key=lambda x: x[1])
        with open(SCORES_FILE, 'w') as f:
            json.dump([(s, t.isoformat()) for s, t in unique], f)

    @commands.Cog.listener()
    async def on_message(self, message):
        if message.author.bot:
            return
        if not user_matches(message.author, USER_CATE_ID, '_cate') or not SCORE_PATTERN.match(message.content):
            return
        score_value = int(message.content)
        score_timestamp = message.created_at
        entry = (score_value, score_timestamp)
        if entry not in self.scores:
            self.scores.append(entry)
            self._save()
            avg = sum(s[0] for s in self.scores) / len(self.scores)
            if score_value > avg:
                confirm_msg = await message.channel.send(
                    f"Score of {score_value} on {score_timestamp.strftime('%Y-%m-%d %H:%M:%S')}UTC "
                    f"recorded for Jun! Great job, that's above your average of {avg:.2f}!",
                    silent=True,
                )
            else:
                confirm_msg = await message.channel.send(
                    f"Score of {score_value} on {score_timestamp.strftime('%Y-%m-%d %H:%M:%S')}UTC "
                    f"recorded for Jun. Your average is {avg:.2f}.",
                    silent=True,
                )
            await message.add_reaction("🎳")
            await confirm_msg.add_reaction("❌")
            asyncio.create_task(
                self._undo_window(confirm_msg, entry)
            )

    async def _undo_window(self, confirm_msg, entry):
        """Wait 30 s for _cate to react ❌ and undo the score if she does."""
        def check(reaction, user):
            return (
                str(reaction.emoji) == '❌'
                and reaction.message.id == confirm_msg.id
                and user.name == '_cate'
                and not user.bot
            )

        try:
            await self.bot.wait_for('reaction_add', timeout=30.0, check=check)
            # _cate reacted — remove the entry and confirm
            if entry in self.scores:
                self.scores.remove(entry)
                self._save()
            await confirm_msg.edit(content=f"~~{confirm_msg.content}~~ Score undone. ↩️")
            try:
                await confirm_msg.clear_reactions()
            except (discord.Forbidden, discord.HTTPException):
                pass
        except Exception:
            # Timeout (or any other error) — just remove the ❌ reaction silently
            try:
                await confirm_msg.remove_reaction('❌', confirm_msg.guild.me)
            except (discord.Forbidden, discord.HTTPException, AttributeError):
                pass

    @commands.command(name='pb')
    async def personal_best(self, ctx):
        if not self.scores:
            await ctx.send("No scores found for Jun.")
            return
        await ctx.send(f"Jun's personal best score is: {max(s[0] for s in self.scores)}")

    @commands.command(name='avg')
    async def average_score(self, ctx):
        if not self.scores:
            await ctx.send("No scores found for Jun.")
            return
        avg = sum(s[0] for s in self.scores) / len(self.scores)
        await ctx.send(f"Jun's average score is: {avg:.2f}")

    @commands.command(name='median')
    async def median_score(self, ctx):
        if not self.scores:
            await ctx.send("No scores found for Jun.")
            return
        vals = sorted(s[0] for s in self.scores)
        n = len(vals)
        median = (vals[n // 2 - 1] + vals[n // 2]) / 2 if n % 2 == 0 else vals[n // 2]
        await ctx.send(f"Jun's median score is: {median:.2f}")

    @commands.command(name='all')
    async def all_scores(self, ctx):
        try:
            if not self.scores:
                await ctx.send("No scores found for Jun.")
                return
            seen = set()
            unique = []
            for score, ts in self.scores:
                if ts not in seen:
                    unique.append((score, ts))
                    seen.add(ts)
            response = "Jun's scores:\n"
            for score, ts in sorted(unique, key=lambda x: x[1]):
                line = f"Score: {score} on {ts.strftime('%Y-%m-%d %H:%M:%S')}\n"
                if len(response) + len(line) > 2000:
                    await ctx.send(response)
                    response = "Jun's scores (contd.):\n"
                response += line
            await ctx.send(response)
            logging.info("Processed !all command successfully.")
        except Exception as e:
            logging.error(f"Error in !all command: {e}")
            await ctx.send("An error occurred while processing the command.")

    @commands.command(name='delete')
    async def delete_score(self, ctx, *, timestamp_str):
        try:
            target = datetime.strptime(timestamp_str, '%Y-%m-%d %H:%M:%S')
            matches = [
                (s, t) for s, t in self.scores
                if t.date() == target.date()
                and t.hour == target.hour
                and t.minute == target.minute
            ]
            if not matches:
                await ctx.send("Score with the given timestamp not found.")
            elif len(matches) == 1:
                self.scores.remove(matches[0])
                self._save()
                await ctx.send(f"Score from {matches[0][1].strftime('%Y-%m-%d %H:%M:%S')} deleted.")
            else:
                lines = "\n".join(f"{i+1}. Score: {s} on {t.strftime('%Y-%m-%d %H:%M:%S')}" for i, (s, t) in enumerate(matches))
                await ctx.send(f"Multiple scores found:\n{lines}")
        except ValueError:
            await ctx.send("Invalid timestamp format. Use %Y-%m-%d %H:%M:%S.")

    @commands.command(name='add')
    async def add_score(self, ctx, score: int, *, timestamp_str: str):
        try:
            ts = datetime.strptime(timestamp_str, '%Y-%m-%d %H:%M:%S')
            self.scores.append((score, ts))
            self._save()
            await ctx.send(f"Added score {score} on {ts.strftime('%Y-%m-%d %H:%M:%S')}.")
        except ValueError:
            await ctx.send("Invalid timestamp format. Please use %Y-%m-%d %H:%M:%S.")

    @commands.command(name='bowlinggraph')
    async def graph_scores(self, ctx):
        try:
            dates = [s[1] for s in self.scores]
            vals = [s[0] for s in self.scores]
            plt.scatter(dates, vals, color='blue', label='Scores')
            x = np.array([d.timestamp() for d in dates])
            y = np.array(vals)
            slope, intercept, r_value, *_ = linregress(x, y)
            plt.plot(dates, intercept + slope * x, color='red', label=f'Trendline (R={r_value:.2f})')
            plt.title("Jun's Bowling Scores Over Time")
            plt.xlabel('Date (MM-DD-YY)')
            plt.ylabel('Score')
            plt.legend()
            plt.tight_layout()
            plt.gca().xaxis.set_major_formatter(mdates.DateFormatter('%m-%d-%Y'))
            plt.gca().xaxis.set_major_locator(mdates.MonthLocator())
            plt.gcf().autofmt_xdate()
            path = str(DATA_DIR / "scores_graph.png")
            plt.savefig(path)
            plt.close()
            await ctx.send(file=discord.File(path))
        except Exception as e:
            await ctx.send(f"Error generating graph: {e}")

    @commands.command(name='bowlingdistgraph')
    async def distribution_graph(self, ctx):
        vals = [s[0] for s in self.scores]
        plt.figure(figsize=(10, 6))
        sns.histplot(vals, bins=30, kde=True, color='blue')
        plt.title("Distribution of Jun's Bowling Scores")
        plt.xlabel('Score')
        plt.ylabel('Frequency')
        plt.tight_layout()
        path = str(DATA_DIR / "distribution_graph.png")
        plt.savefig(path)
        plt.close()
        await ctx.send(file=discord.File(path))


async def setup(bot):
    await bot.add_cog(Bowling(bot))
