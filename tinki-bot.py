import asyncio
import logging
import discord
from discord.ext import commands
from fuzzywuzzy import process

import config

logging.basicConfig(level=logging.INFO)

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


class TinkiBot(commands.Bot):
    async def setup_hook(self):
        for cog in COGS:
            await self.load_extension(cog)
        logging.info("setup_hook: loaded cogs = %s", list(self.cogs.keys()))

def build_bot_intents():
    intents = discord.Intents.none()
    intents.guilds = True
    intents.members = True
    intents.messages = True
    intents.reactions = True
    intents.message_content = True
    intents.emojis_and_stickers = True
    return intents


intents = build_bot_intents()
bot = TinkiBot(command_prefix='!', intents=intents)


@bot.event
async def on_ready():
    logging.info("on_ready: cogs loaded = %s", list(bot.cogs.keys()))
    await bot.change_presence(activity=discord.Game(name="!commands"))
    admin_cog = bot.cogs.get('Admin')
    logging.info("on_ready: admin_cog = %s", admin_cog)
    if admin_cog:
        asyncio.create_task(admin_cog.run_startup_tests())


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
