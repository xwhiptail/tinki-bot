import re
import sqlite3
from datetime import datetime, timedelta, timezone
from math import ceil

import discord
import pytz
from discord.ext import commands, tasks

from config import CHANNEL_REMINDERS, DATABASE_FILE


class Reminders(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self._create_table()

    @commands.Cog.listener()
    async def on_ready(self):
        if not self.check_reminders.is_running():
            self.check_reminders.start()

    def cog_unload(self):
        self.check_reminders.cancel()

    def _connect(self):
        return sqlite3.connect(DATABASE_FILE)

    def _create_table(self):
        with self._connect() as conn:
            c = conn.cursor()
            c.execute('''CREATE TABLE IF NOT EXISTS reminders
                        (reminder_id INTEGER PRIMARY KEY, user_id TEXT, channel_id TEXT,
                         reminder_time TEXT, message TEXT, sent INTEGER DEFAULT 0)''')
            conn.commit()

    def _delete_expired(self):
        with self._connect() as conn:
            c = conn.cursor()
            now = datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S')
            c.execute('DELETE FROM reminders WHERE reminder_time < ? AND sent = 1', (now,))
            conn.commit()

    @tasks.loop(seconds=10)
    async def check_reminders(self):
        with self._connect() as conn:
            c = conn.cursor()
            now = datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S')
            c.execute('SELECT user_id, channel_id, reminder_time, message FROM reminders WHERE reminder_time<=? AND sent=0', (now,))
            reminders = c.fetchall()
            for user_id, channel_id, reminder_time, message in reminders:
                user = await self.bot.fetch_user(user_id)
                channel = discord.utils.get(self.bot.get_all_channels(), name=CHANNEL_REMINDERS)
                if channel:
                    await channel.send(f"{user.mention}, {message}")
                    c.execute('UPDATE reminders SET sent=1 WHERE user_id=? AND reminder_time=?', (user_id, reminder_time))
                    conn.commit()

    @check_reminders.before_loop
    async def before_check_reminders(self):
        await self.bot.wait_until_ready()

    @commands.command()
    async def remind(self, ctx, *, args=None):
        await ctx.send("Please follow this format: !remindme in X seconds/minutes/hours/days.")

    @commands.command()
    async def remindme(self, ctx, *, args=None):
        try:
            self._delete_expired()
            with self._connect() as conn:
                c = conn.cursor()
                if args is None:
                    c.execute(
                        'SELECT reminder_id, reminder_time, message FROM reminders WHERE user_id=?',
                        (str(ctx.author.id),)
                    )
                    reminders = c.fetchall()
                    if not reminders:
                        await ctx.send(f"{ctx.author.mention}, you have no reminders set.")
                        return
                    now = datetime.utcnow()
                    upcoming = [r for r in reminders if datetime.strptime(r[1], '%Y-%m-%d %H:%M:%S') > now]
                    missed = [r for r in reminders if r not in upcoming]
                    if upcoming:
                        lines = "\n".join(
                            f"ID {r[0]} - At {r[1]} ({ceil((datetime.strptime(r[1], '%Y-%m-%d %H:%M:%S') - now).total_seconds() / 60)} min left): {r[2]}"
                            for r in upcoming
                        )
                        await ctx.send(f"{ctx.author.mention}, your upcoming reminders:\n{lines}")
                    if missed:
                        lines = "\n".join(
                            f"ID {r[0]} - At {r[1]} (Past, {ceil((now - datetime.strptime(r[1], '%Y-%m-%d %H:%M:%S')).total_seconds() / 60)} min ago): {r[2]}"
                            for r in missed
                        )
                        await ctx.send(f"{ctx.author.mention}, your past reminders:\n{lines}")
                    return

                msg_ref = ctx.message.reference
                link = f"https://discord.com/channels/{ctx.guild.id}/{ctx.channel.id}/{msg_ref.message_id if msg_ref else ctx.message.id}"

                if re.match(r'in (\d+ [a-z]+(, )?)+', args):
                    match = re.findall(r'(\d+) ([a-z]+)', args)
                    if not match:
                        await ctx.send(f"{ctx.author.mention}, couldn't understand the format.")
                        return
                    time_units = {
                        'second': 'seconds', 'sec': 'seconds',
                        'minute': 'minutes', 'min': 'minutes',
                        'hour': 'hours', 'hr': 'hours',
                        'day': 'days', 'week': 'weeks',
                        'month': 'days', 'year': 'days',
                    }
                    delta_args = {}
                    for qty, unit in match:
                        unit = unit.lower().rstrip('s')
                        if unit not in time_units:
                            await ctx.send(f"{ctx.author.mention}, couldn't understand time unit '{unit}'.")
                            return
                        key = time_units[unit]
                        factor = 30 if unit == "month" else (365 if unit == "year" else 1)
                        delta_args[key] = delta_args.get(key, 0) + int(qty) * factor
                    reminder_time = datetime.utcnow() + timedelta(**delta_args)
                else:
                    for fmt in ["%I:%M%p %Y-%m-%d", "%I:%M%p %m-%d-%Y", "%I:%M %Y-%m-%d"]:
                        try:
                            parts = args.split(' at ')
                            if len(parts) > 1:
                                reminder_time = datetime.strptime(parts[1], fmt).replace(tzinfo=pytz.utc)
                                break
                            else:
                                await ctx.send(f"{ctx.author.mention} Please follow this format: !remindme in X seconds/minutes/hours/days.")
                                return
                        except ValueError:
                            continue
                    else:
                        await ctx.send(f"{ctx.author.mention} Please follow this format: !remindme in X seconds/minutes/hours/days.")
                        return

                reminder_time_str = reminder_time.strftime('%Y-%m-%d %H:%M:%S')
                c.execute(
                    'INSERT INTO reminders (user_id, channel_id, reminder_time, message, sent) VALUES (?, ?, ?, ?, 0)',
                    (str(ctx.author.id), str(ctx.channel.id), reminder_time_str, f'Reminder! [Link]({link})')
                )
                conn.commit()
                await ctx.send(f"{ctx.author.mention}, reminder set for {reminder_time_str} with ID `{c.lastrowid}`!")

        except Exception as e:
            await ctx.send(f"An error occurred: {e}")

    @commands.command()
    async def deletereminder(self, ctx, reminder_id: int):
        with self._connect() as conn:
            c = conn.cursor()
            c.execute('SELECT reminder_id FROM reminders WHERE reminder_id=? AND user_id=?',
                      (reminder_id, str(ctx.author.id)))
            if c.fetchone():
                c.execute('DELETE FROM reminders WHERE reminder_id=?', (reminder_id,))
                conn.commit()
                await ctx.send(f"{ctx.author.mention}, reminder `{reminder_id}` deleted!")
            else:
                await ctx.send(f"{ctx.author.mention}, no reminder found with ID `{reminder_id}`.")

    @commands.command()
    async def currenttime(self, ctx):
        await ctx.send(datetime.now().strftime('%Y-%m-%d %H:%M:%S'))


def setup(bot):
    bot.add_cog(Reminders(bot))
