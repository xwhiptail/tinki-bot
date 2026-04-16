import logging
import discord
from discord.ext import commands
from fuzzywuzzy import process

import config

logging.basicConfig(level=logging.INFO)

intents = discord.Intents.all()
bot = commands.Bot(command_prefix='!', intents=intents)

COGS = [
    'cogs.bowling',
    'cogs.uma',
    'cogs.personas',
    'cogs.reminders',
    'cogs.emotes',
    'cogs.tracking',
    'cogs.ai',
    'cogs.utility',
    'cogs.admin',
    'cogs.url_filter',
]


for cog in COGS:
    bot.load_extension(cog)


@bot.event
async def on_ready():
    logging.info("on_ready: cogs loaded = %s", list(bot.cogs.keys()))
    await bot.change_presence(activity=discord.Game(name="!commands"))
    admin_cog = bot.cogs.get('Admin')
    logging.info("on_ready: admin_cog = %s", admin_cog)
    if admin_cog:
        bot.loop.create_task(admin_cog.run_startup_tests())


@bot.event
async def on_message(message):
    if message.author == bot.user:
        return
    if message.content.startswith('$'):
        return
    await bot.process_commands(message)


@bot.event
async def on_command_error(ctx, error):
    if isinstance(error, commands.CommandNotFound):
        attempted = ctx.invoked_with
        names = [cmd.name for cmd in bot.commands]
        match, score = process.extractOne(attempted, names)
        if score >= 60:
            await ctx.send(f"`!{attempted}` doesn't exist, genius. Did you mean `!{match}`?")
        return
    raise error


bot.run(config.TOKEN)
