import ast
import json
import operator
import random
import re
import sqlite3
import time
import asyncio
import aiohttp
import cv2
import discord
import matplotlib.dates as mdates
import matplotlib.pyplot as plt
import numpy as np
import pyfiglet
import seaborn as sns
import subprocess
import requests
import io
import logging
import os
import seventv  # https://github.com/probablyjassin/seventv.py
import pytz

from pathlib import Path
from discord.ext import commands
from discord.ext import menus
from discord.ext import tasks
from discord.utils import get
from fuzzywuzzy import process
from scipy.stats import linregress
from datetime import datetime, timezone, timedelta
from decimal import Decimal, InvalidOperation
from math import ceil
from openai import OpenAI
from PIL import Image, ImageSequence
from typing import Optional, Set  # put this with your other imports at the top

intents = discord.Intents.all()
BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = Path(os.getenv('TINKI_DATA_DIR', BASE_DIR / 'data'))
DATA_DIR.mkdir(parents=True, exist_ok=True)

DATABASE_FILE = str(DATA_DIR / 'reminders.db')
CONVERSATION_FILE = str(DATA_DIR / 'conversations.json')
PERSONA_FILE = str(DATA_DIR / 'personas.json')

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s:%(levelname)s:%(message)s')

TOKEN = os.getenv('DISCORD')
GIPHY_API_KEY = os.getenv('GIPHY')
OPENAI_MODEL = os.getenv('OPENAI_MODEL', 'gpt-5.4')
GITHUB_REPO_URL = "https://github.com/xwhiptail/tinki-bot"
SCORES_FILE = str(DATA_DIR / 'scores.json')
SUS_FILE = str(DATA_DIR / 'sus_and_sticker_usage.json')
EXPLODE_FILE = str(DATA_DIR / 'explode.json')
SPINNY_FILE = str(DATA_DIR / 'spinny.json')

bot = commands.Bot(command_prefix='!', intents=discord.Intents.all())

RANDOM_AI_ENABLED = False
RANDOM_AI_MESSAGE_IDS: Set[int] = set()

# patterns for url correction
URL_PATTERN = re.compile(r'https?://(?:[-\w.]|(?:%[\da-fA-F]{2}))+')
X_COM_PATTERN = re.compile(r'https?://x\.com')
TWITTER_COM_PATTERN = re.compile(r'https?://(www\.)?twitter\.com/(\w+)/(\w+)')
INSTAGRAM_COM_PATTERN = re.compile(r'https?://(www\.)?instagram\.com')
TIKTOK_COM_PATTERN = re.compile(r'https?://(www\.)?tiktok\.com')
REDDIT_COM_PATTERN = re.compile(r'https?://(www\.)?reddit\.com')
TWITCH_CLIP_PATTERN = re.compile(r'(https?://(?:www\.)?(?:clips\.)?twitch\.tv/[\w-]+/clip/[\w-]+)')
youtube_url_pattern = re.compile(r'(https?://)?(www\.)?(youtube\.com/watch\?v=|youtu\.be/|youtube\.com/shorts/)([a-zA-Z0-9_-]+)')

GREMLIN_SYSTEM_STYLE = (
    "You are Tinki, a chaotic gremlin shitposter Discord bot. "
    "You roast people, use sarcasm, and sound like an unhinged goblin in voice chat. "
    "Keep replies short (1–2 sentences). "
    "Be playful, teasing, and meme-y. "
    "Do NOT be wholesome or give serious advice. "
    "Avoid therapy talk, safety PSAs, or saying things like 'it's important to talk to someone'. "
    "No slurs, no bigotry, no attacks on real-world trauma, health issues, or protected traits "
    "(race, gender, sexuality, religion, etc.). "
    "Insults should feel like banter between friends in a Discord server, not genuine harassment."
)


def get_openai_client() -> OpenAI:
    return OpenAI()


async def gpt_wrap_fact(fact: str, user_text: str, system_prompt) -> str:
    """Call GPT to deliver a pre-computed factual answer in Tinki's personality."""
    client = get_openai_client()
    system = (
        GREMLIN_SYSTEM_STYLE + " "
        f"Your name is @Tinki-bot. "
        f"Use this persona description as extra flavor: {system_prompt} "
        f"The correct answer to the user's question is: {fact}. "
        f"You MUST include this exact answer in your reply. Keep it short (1–2 sentences)."
    )
    completion = client.chat.completions.create(
        model=OPENAI_MODEL,
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": user_text},
        ],
    )
    return completion.choices[0].message.content if completion.choices else fact


CALCULATION_OPERATORS = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
}


SERVER_FEATURE_REMOVED_MESSAGE = (
    "Minecraft and SkyFactory server controls have been retired. "
    "These commands are placeholders and no longer manage any live servers."
)


async def send_server_feature_removed(ctx):
    await ctx.send(SERVER_FEATURE_REMOVED_MESSAGE)


def _evaluate_decimal_expression(node):
    if isinstance(node, ast.Expression):
        return _evaluate_decimal_expression(node.body)

    if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)):
        return Decimal(str(node.value))

    if isinstance(node, ast.UnaryOp) and isinstance(node.op, (ast.UAdd, ast.USub)):
        operand = _evaluate_decimal_expression(node.operand)
        return operand if isinstance(node.op, ast.UAdd) else -operand

    if isinstance(node, ast.BinOp) and type(node.op) in CALCULATION_OPERATORS:
        left = _evaluate_decimal_expression(node.left)
        right = _evaluate_decimal_expression(node.right)
        return CALCULATION_OPERATORS[type(node.op)](left, right)

    raise ValueError("Unsupported expression")


def _format_decimal_result(value: Decimal) -> str:
    normalized = format(value.normalize(), 'f')
    if '.' in normalized:
        integer_part, fractional_part = normalized.split('.', 1)
        fractional_part = fractional_part.rstrip('0')
        if fractional_part:
            return f"{int(integer_part):,}.{fractional_part}"
    return f"{int(Decimal(normalized)):,}"


def maybe_count_letter_reply(text: str) -> Optional[str]:
    lowered = text.strip().lower().rstrip(' ?!.')
    match = re.search(
        r'how many\s+(?:letter\s+)?([a-z])(?:\'s|s)?\s+(?:are\s+)?in\s+(?:the word\s+)?([a-z]+)',
        lowered,
    )
    if not match:
        return None

    target_letter, target_word = match.groups()
    count = target_word.count(target_letter)
    times = "time" if count == 1 else "times"
    return f"'{target_letter}' appears {count} {times} in '{target_word}'"


def maybe_calculate_reply(text: str) -> Optional[str]:
    candidate = text.strip().lower()
    candidate = re.sub(r'^(what(?:\'s| is)|calculate|compute|solve)\s+', '', candidate)
    candidate = candidate.rstrip(' ?!.')
    candidate = re.sub(r'(?<=\d)\s*[x×]\s*(?=\d)', '*', candidate)
    candidate = re.sub(r'(?<=\d)\s*[÷]\s*(?=\d)', '/', candidate)

    if not candidate or not re.fullmatch(r'[\d\s\.\+\-\*\/\(\)]+', candidate):
        return None

    try:
        parsed = ast.parse(candidate, mode='eval')
        result = _evaluate_decimal_expression(parsed)
        formatted = _format_decimal_result(result)
        return formatted
    except (SyntaxError, ValueError, InvalidOperation, ZeroDivisionError):
        return None

def rewrite_social_urls(content: str) -> str:
    """
    Apply the same URL-rewrite rules used in on_message for
    Twitter/X/Instagram/TikTok/Reddit and return the rewritten text.
    """
    new_message = content

    # Twitter -> vxtwitter
    if TWITTER_COM_PATTERN.search(new_message):
        new_message = TWITTER_COM_PATTERN.sub(r'https://vxtwitter.com/\2/\3', new_message)

    # X.com -> fixvx
    if X_COM_PATTERN.search(new_message):
        new_message = X_COM_PATTERN.sub('https://fixvx.com', new_message)

    # Instagram -> eeinstagram
    if INSTAGRAM_COM_PATTERN.search(new_message):
        new_message = INSTAGRAM_COM_PATTERN.sub('https://eeinstagram.com', new_message)

    # TikTok -> tnktok
    if TIKTOK_COM_PATTERN.search(new_message):
        new_message = TIKTOK_COM_PATTERN.sub('https://tnktok.com', new_message)

    # Reddit -> rxddit
    if REDDIT_COM_PATTERN.search(new_message):
        new_message = REDDIT_COM_PATTERN.sub('https://rxddit.com', new_message)

    return new_message


# bowling score variables
SCORE_PATTERN = re.compile(r'^(?:[6-9][0-9]|1[0-9]{2}|200)$')
TIMEZONE_OFFSET = -5  # Change this to your timezone offset from UTC

# dbs for different data
scores = []
sus_and_sticker_usage = []
conversations = {}
personas = {}
explode = []
spinny = []
sticker_users = {}


# used for bowling scores
def load_scores():
    global scores
    try:
        with open(SCORES_FILE, 'r') as f:
            scores_data = json.load(f)
            scores = [(int(score), discord.utils.parse_time(timestamp)) for score, timestamp in scores_data]
    except FileNotFoundError:
        scores = []


# used for bowling scores
def save_scores():
    global scores

    # Convert all datetime objects to offset-aware (UTC) datetimes
    for i in range(len(scores)):
        score, timestamp = scores[i]
        # If the datetime is naive (no timezone), make it aware (assuming UTC)
        if timestamp.tzinfo is None or timestamp.tzinfo.utcoffset(timestamp) is None:
            scores[i] = (score, timestamp.replace(tzinfo=timezone.utc))

    # Remove duplicates by converting the list to a set and then back to a list
    unique_scores = list({(s[0], s[1].isoformat()): s for s in scores}.values())

    # Now sort the scores based on timestamp for better readability
    unique_scores.sort(key=lambda x: x[1])

    with open(SCORES_FILE, 'w') as f:
        json_scores = [(score, timestamp.isoformat()) for score, timestamp in unique_scores]
        json.dump(json_scores, f)


def save_sus_and_sticker_usage():
    with open(SUS_FILE, 'w') as f:
        json.dump(sus_and_sticker_usage, f, indent=4, default=str)  # Using default=str to handle datetime


def load_sus_and_sticker_usage():
    global sus_and_sticker_usage
    try:
        with open(SUS_FILE, 'r') as f:
            sus_and_sticker_usage = json.load(f)
    except FileNotFoundError:
        sus_and_sticker_usage = []


def save_explode():
    with open(EXPLODE_FILE, 'w') as f:
        json.dump(explode, f, indent=4, default=str)  # Using default=str to handle datetime


def load_explode():
    global explode
    try:
        with open(EXPLODE_FILE, 'r') as f:
            explode = json.load(f)
    except FileNotFoundError:
        explode = []


def save_spinny():
    with open(SPINNY_FILE, 'w') as f:
        json.dump(spinny, f, indent=4, default=str)  # Using default=str to handle datetime


def load_spinny():
    global spinny
    try:
        with open(SPINNY_FILE, 'r') as f:
            spinny = json.load(f)
    except FileNotFoundError:
        spinny = []


# Function to load conversations from a file
def load_conversations():
    global conversations
    try:
        with open(CONVERSATION_FILE, 'r') as f:
            conversations = json.load(f)
    except FileNotFoundError:
        conversations = {}


# Save conversations to a file
def save_conversations():
    global conversations
    with open(CONVERSATION_FILE, 'w') as f:
        json.dump(conversations, f, ensure_ascii=False, indent=4)


def update_conversation(user_id, current_persona, user_message, bot_response):
    global conversations
    user_conversations = conversations.setdefault(user_id, {})
    persona_history = user_conversations.setdefault(current_persona, [])

    # Append new messages
    persona_history.append({'role': 'user', 'content': user_message})
    persona_history.append({'role': 'assistant', 'content': bot_response})

    # Optionally, limit the history length to avoid excessively large files
    user_conversations[current_persona] = persona_history[-10:]

    # Save the updated conversations
    save_conversations()


# persona data handling
def load_personas():
    global personas, current_persona
    try:
        with open(PERSONA_FILE, 'r') as file:
            personas = json.load(file)
            print("Personas loaded:", personas)  # Debug print

        if 'cute' in personas:
            current_persona = 'cute'
            print("Current persona set to 'cute'")  # Debug print
    except FileNotFoundError:
        personas = {}
        print("personas.json not found, initializing with empty dictionary")  # Debug print


def save_personas():
    global personas
    with open(PERSONA_FILE, 'w') as file:
        json.dump(personas, file, ensure_ascii=False, indent=4)


# ignored $emote commands
ignored_commands = [
    'pb', 'avg', 'all', 'delete', 'graph', 'distribution', 'distgraph',
    'commands', 'add', 'median', 'purge', 'gif', 'random', 'remindme',
    'deletereminder', 'time'
]


# contains emote handling, bowling scores, url correction, tinki-bot
@bot.event
async def on_message(message):
    global conversations

    if message.author == bot.user:
        return

    if re.match(r'\$\d+', message.content):
        return

    # If this is a reply inside a random-AI thread, respond and keep the thread alive
    if message.reference is not None and not message.author.bot:
        try:
            replied_to = await message.channel.fetch_message(message.reference.message_id)
        except discord.NotFound:
            replied_to = None

        # Only trigger if the replied-to message is part of the random AI thread
        if (
            replied_to
            and replied_to.id in RANDOM_AI_MESSAGE_IDS
            and not message.content.startswith('!')
        ):
            original_text = replied_to.content or "(original message had no text)"

            reply = await generate_reply_to_reply(
                original_text=original_text,
                user=message.author,
                user_text=message.content,
            )

            bot_reply = await message.channel.send(f"{message.author.mention} {reply}")

            # Track Tinki's reply so replies to THIS message also count
            RANDOM_AI_MESSAGE_IDS.add(bot_reply.id)
            return

    ############################################################################

    # Check if the message is a command to activate the sticker functionality
    if message.content.startswith('!spinny'):
        # Split the message content to extract the mention
        parts = message.content.split()
        if len(parts) < 2:
            await message.channel.send("Please mention a user to activate the grinding.")
            return

        # Get the user from the mention
        user_mention = parts[1]
        user_id = user_mention.strip('<@!>')  # Stripping to get just the user ID
        user = message.guild.get_member(int(user_id))

        if user is not None:
            # Add the user to the sticker_users dictionary
            sticker_users[user_id] = True
            await message.channel.send(f"Grinding activated for {user.mention}!", silent=True)
        else:
            await message.channel.send("Could not find the user you mentioned.")

    # Check if the message is a command to deactivate the sticker functionality
    elif message.content.startswith('!stopspinny'):
        parts = message.content.split()
        if len(parts) < 2:
            await message.channel.send("Please specify a user to deactivate the grinding.")
            return

        user_mention_or_name = parts[1]

        # Check if it's a mention
        if user_mention_or_name.startswith('<@') and user_mention_or_name.endswith('>'):
            user_id = user_mention_or_name.strip('<@!>')
        else:
            # Handle by username
            user_id = await get_user_id_from_username(message.guild, user_mention_or_name)

        if user_id and user_id in sticker_users:
            sticker_users.pop(user_id, None)
            await message.channel.send(f"Grinding deactivated.", silent=True)
        else:
            await message.channel.send("Could not find the user you mentioned.")

    elif message.content.startswith('!silentspinny'):
        # Check if the author is "whiptail"
        if message.author.name == "whiptail":
            parts = message.content.split()
            if len(parts) < 2:
                await message.channel.send("Please specify a user to activate the grinding.")
                return

            username = parts[1]

            # Get user ID from username
            user_id = await get_user_id_from_username(message.guild, username)

            if user_id:
                # Add the user to the sticker_users dictionary using their ID
                sticker_users[user_id] = True
                await message.channel.send(f"Grinding activated for {username}!", silent=True)
            else:
                await message.channel.send("Could not find the user you mentioned.")
        else:
            await message.channel.send("You do not have permission to use this command.", silent=True)

    # Check if the message is from a user with an active sticker functionality
    elif str(message.author.id) in sticker_users:
        # Find the sticker named "SPINNY" in the guild
        sticker = discord.utils.get(message.guild.stickers, name="SPINNY")
        if sticker:
            await message.channel.send(stickers=[sticker], silent=True)
        else:
            await message.channel.send("Sticker 'SPINNY' not found.")

    # Emote functionality for specific commands
    if message.content.startswith('$'):
        content_parts = message.content[1:].split(' ')
        emote_name = content_parts[0]
        if emote_name == "randomemote":
            try:
                repeat_times = int(content_parts[1]) if len(content_parts) > 1 else 1
            except ValueError:
                repeat_times = 1  # Default to 1 if conversion fails

            # Validate the number of times to repeat the emote
            if repeat_times < 1 or repeat_times > 24:
                await message.channel.send("Error: The number of emotes must be between 1 and 24.")
                return
            # You might want to consider all available emotes not just from message.guild
            available_emotes = [emote for guild in bot.guilds for emote in guild.emojis if emote.available]
            if available_emotes:
                # Send a message with the first emote to start the "slot machine"
                slot_message = await message.channel.send(str(available_emotes[0]))

                # Cycle through emotes for about 5 seconds
                start_time = time.time()
                while time.time() - start_time < 5:
                    random_emote = random.choice(available_emotes)
                    await slot_message.edit(content=str(random_emote))
                    # Sleep for a short period to simulate the slot machine effect
                    await asyncio.sleep(0.5)  # Edit this to make the cycle faster or slower

                # Send the final emote after cycling
                random_emote = random.choice(available_emotes)
                emote_str = str(random_emote) * repeat_times
                await slot_message.edit(content=str(emote_str))
            else:
                await message.channel.send("No emotes found on any server.")
        else:
            # Attempt to parse the optional number of times to post the emote
            try:
                repeat_times = int(content_parts[1]) if len(content_parts) > 1 else 1
            except ValueError:
                repeat_times = 1  # Default to 1 if conversion fails

            # Validate the number of times to repeat the emote
            if repeat_times < 1 or repeat_times > 24:
                await message.channel.send("Error: The number of emotes must be between 1 and 24.")
                return
            # Searching in the current server first
            emote = discord.utils.get(message.guild.emojis, name=emote_name)
            if emote:
                emote_str = str(emote) * repeat_times  # Repeat the emote string
                await message.channel.send(emote_str[:2000], silent=True)  # Ensure message does not exceed Discord limit
            else:
                # Search across all accessible servers
                all_emotes = [emote for guild in bot.guilds for emote in guild.emojis if emote.available]
                emote = discord.utils.find(lambda e: e.name == emote_name, all_emotes)
                if emote:
                    emote_str = str(emote) * repeat_times  # Repeat the emote string
                    await message.channel.send(emote_str[:2000], silent=True)  # Ensure message does not exceed Discord limit
                else:
                    # Gather all emote names for matching
                    all_emote_names = [e.name for e in all_emotes]
                    closest_matches = process.extract(emote_name, all_emote_names, limit=5)
                    if closest_matches:
                        suggestion_message = await message.channel.send(
                            "Did you mean...? (React with the correct emote or ❌ to dismiss)"
                        )
                        for match, score in closest_matches:
                            match_emote = discord.utils.get(all_emotes, name=match)
                            if match_emote:
                                await suggestion_message.add_reaction(match_emote)
                        # Add the X reaction to dismiss the suggestions
                        await suggestion_message.add_reaction('❌')

                        def check(reaction, user):
                            return (
                                user == message.author
                                and reaction.message.id == suggestion_message.id
                                and (str(reaction.emoji) in [str(discord.utils.get(all_emotes, name=match[0])) for
                                                             match in closest_matches] or str(
                                        reaction.emoji) == '❌')
                            )

                        try:
                            reaction, user = await bot.wait_for('reaction_add', timeout=60.0, check=check)
                        except asyncio.TimeoutError:
                            await suggestion_message.delete()
                            await message.channel.send("Suggestion timeout. Please try the command again.")
                        else:
                            if str(reaction.emoji) == '❌':
                                await suggestion_message.delete()
                                await message.delete()  # This deletes the user's command message
                                await message.channel.send("None selected... cleaning up...", delete_after=5.0)
                            else:
                                emote_str = str(reaction.emoji) * repeat_times  # Repeat the emote string
                                await message.channel.send(emote_str[:2000],
                                                           silent=True)  # Ensure message does not exceed Discord limit
                                await suggestion_message.delete()

                    else:
                        await message.channel.send(f'No emote found with the name "{emote_name}".')

        return

    # URL corrections for Twitter/X/Instagram/TikTok/Reddit
    if any(p.search(message.content) for p in [
        TWITTER_COM_PATTERN,
        X_COM_PATTERN,
        INSTAGRAM_COM_PATTERN,
        TIKTOK_COM_PATTERN,
        REDDIT_COM_PATTERN,
    ]):
        new_message = rewrite_social_urls(message.content)
        if new_message != message.content:
            await message.channel.send(
                f"{message.author.mention} originally posted: {new_message}",
                silent=True
            )
            await message.delete()
            await asyncio.sleep(3)

    # Check if the message contains a Twitch clip URL
    if TWITCH_CLIP_PATTERN.search(message.content):
        # Check if the original message already has a video embed
        if any(embed.type == 'video' for embed in message.embeds):
            # If there's already a video embed, do nothing
            return

        base_url = TWITCH_CLIP_PATTERN.search(message.content).group(1)

        # Try appending '#' and then 'a' through 'e' if embed doesn't work
        for suffix in ['#', '?a', '?b', '?c', '?d', '?e']:
            modified_url = f"{base_url}{suffix}"
            sent_message = await message.channel.send(f"{message.author.mention} originally posted: {modified_url}",
                                                      silent=True)
            await asyncio.sleep(3)  # Wait to see if embed appears

            # Re-fetch the message to check for embeds
            sent_message = await message.channel.fetch_message(sent_message.id)

            # Check if any embed is of type 'video'
            if any(embed.type == 'video' for embed in sent_message.embeds):
                break  # Video embed created, exit the loop
            else:
                await sent_message.delete()  # Delete and try next suffix

        await message.delete()  # Delete the original message

    # Detect and add bowling scores posted by _cate
    if message.author.name == "_cate" and SCORE_PATTERN.match(message.content):
        score_value = int(message.content)
        score_timestamp = message.created_at
        score_entry = (score_value, score_timestamp)

        if score_entry not in scores:
            scores.append(score_entry)
            save_scores()

            # Calculate average score to praise or shame _cate
            avg_score = sum([score[0] for score in scores]) / len(scores)
            if score_value > avg_score:
                await message.channel.send(
                    f"Score of {score_value} on {score_timestamp.strftime('%Y-%m-%d %H:%M:%S')}UTC recorded for Jun! Great job, that's above your average of {avg_score:.2f}!")
            else:
                await message.channel.send(
                    f"Score of {score_value} on {score_timestamp.strftime('%Y-%m-%d %H:%M:%S')}UTC recorded for Jun. Your average is {avg_score:.2f}.")

            # React with bowling emoji for all _cate's bowling scores
            bowling_emoji = "🎳"
            await message.add_reaction(bowling_emoji)
        return
    # Continue processing other bot commands
    else:
        await bot.process_commands(message)

    # tracking explode
    if message.author.name == "whiptail":
        if message.content.startswith('!'):
            return
        elif ":explode:" in message.content.lower():
            entry = {
                'user_id': message.author.id,
                'timestamp': message.created_at.isoformat(),  # Convert datetime to string
                'message_id': message.id
            }
            explode.append(entry)
            save_explode()

    # tracking SPINNY
    if message.content.startswith('!'):
        return
    elif any(sticker.name == "SPINNY" for sticker in message.stickers):
        entry = {
            'user_id': message.author.id,
            'timestamp': message.created_at.isoformat(),  # Convert datetime to string
            'message_id': message.id
        }
        spinny.append(entry)
        save_spinny()

    ##########################################################################
    ##########TINKI BOT##################################################

    # Check if the message is not a reply and the bot is mentioned
    if message.reference is None and bot.user in message.mentions:
        text = message.content.replace(f'<@!{bot.user.id}>', '').replace(f'<@{bot.user.id}>', '').strip()
        user_id = str(message.author.id)
        system_prompt = personas.get(current_persona, [])

        # Retrieve the specific history for the current persona and user
        user_conversations = conversations.setdefault(user_id, {})
        persona_history = user_conversations.setdefault(current_persona, [])
        history = " ".join([msg["content"] for msg in persona_history])

        if text:
            try:
                letter_count_fact = maybe_count_letter_reply(text)
                if letter_count_fact:
                    letter_count_reply = await gpt_wrap_fact(letter_count_fact, text, system_prompt)
                    await message.channel.send(f'{message.author.mention} {letter_count_reply}')
                    persona_history.append({"role": "user", "content": text})
                    persona_history.append({"role": "assistant", "content": letter_count_reply})
                    user_conversations[current_persona] = persona_history[-20:]
                    save_conversations()
                    return

                calc_fact = maybe_calculate_reply(text)
                if calc_fact:
                    calculation_reply = await gpt_wrap_fact(calc_fact, text, system_prompt)
                    await message.channel.send(f'{message.author.mention} {calculation_reply}')
                    persona_history.append({"role": "user", "content": text})
                    persona_history.append({"role": "assistant", "content": calculation_reply})
                    user_conversations[current_persona] = persona_history[-20:]
                    save_conversations()
                    return

                client = get_openai_client()
                combined_system_message = (
                        GREMLIN_SYSTEM_STYLE + " "
                                               f"Your name is @Tinki-bot. "
                                               f"Use this persona description as extra flavor: {system_prompt} "
                                               f"Use the past history only as loose context: {history}"
                )

                completion = client.chat.completions.create(
                    model=OPENAI_MODEL,
                    messages=[
                        {'role': "system", "content": combined_system_message},
                        {"role": "user", "content": text}
                    ]
                )

                bot_response = completion.choices[0].message.content if completion.choices else "No response generated."

                if not bot_response.strip():
                    await message.channel.send(
                        f'{message.author.mention} I am unable to generate a response at the moment.')
                    return

                # Check if the response exceeds Discord's character limit
                discord_char_limit = 2000
                mention = f'{message.author.mention} '
                max_chunk_length = discord_char_limit - len(mention) - 30  # Extra buffer for part indicator

                if len(bot_response) > discord_char_limit:
                    num_chunks = -(-len(bot_response) // max_chunk_length)  # Ceiling division

                    for i in range(num_chunks):
                        start_index = i * max_chunk_length
                        end_index = start_index + max_chunk_length
                        message_chunk = bot_response[start_index:end_index]

                        # Adding part indicator
                        part_indicator = f" (Part {i + 1} of {num_chunks})" if num_chunks > 1 else ""
                        full_message = f'{mention}{message_chunk}{part_indicator}'

                        try:
                            await message.channel.send(full_message)
                            await asyncio.sleep(1)  # Delay to prevent rate limiting
                        except Exception as e:
                            error_message = str(e)
                            print(f"Error sending message chunk {i + 1} of {num_chunks}: {error_message}")
                            await message.channel.send(
                                f'{message.author.mention} Sorry, I encountered an issue while sending part of the message: {error_message}')
                            break
                else:
                    try:
                        await message.channel.send(f'{mention}{bot_response}')
                    except Exception as e:
                        error_message = str(e)
                        print(f"Error in generating response: {error_message}")
                        await message.channel.send(
                            f'{message.author.mention} Sorry, I encountered an issue: {error_message}')

                # Update the specific history for this persona
                persona_history.append({"role": "user", "content": text})
                persona_history.append({"role": "assistant", "content": bot_response})
                user_conversations[current_persona] = persona_history[-20:]  # Limit the history length

                # Save the updated conversations to the file
                save_conversations()

            except Exception as e:
                error_message = str(e)
                print(f"Error in generating response: {error_message}")
                await message.channel.send(f'{message.author.mention} Sorry, I encountered an issue: {error_message}')
                return

    # tracking sussy
    if message.author.name == "lhea.":
        if message.content.startswith('!'):
            return

        # Define patterns to search for
        sus_pattern = re.compile(r'\bsus\b', re.IGNORECASE)
        sussy_pattern = re.compile(r'\bsussy\b', re.IGNORECASE)

        # Count occurrences of 'sus' and 'sussy'
        sus_count = len(sus_pattern.findall(message.content))
        sussy_count = len(sussy_pattern.findall(message.content))

        # Check for 'sussydoge' and 'SUS' stickers
        sticker_count = sum(sticker.name.lower() in ["sussydoge", "sus"] for sticker in message.stickers)

        # Check for 'sus' in emoji names
        emoji_count = sum(
            "sus" in emoji.name.lower() for emoji in message.guild.emojis if str(emoji) in message.content)

        total_sus_count = sus_count + sussy_count + sticker_count + emoji_count

        if total_sus_count > 0:
            for _ in range(total_sus_count):
                entry = {
                    'user_id': message.author.id,
                    'timestamp': message.created_at.isoformat(),  # Convert datetime to string
                    'message_id': message.id
                }
                sus_and_sticker_usage.append(entry)
            save_sus_and_sticker_usage()


async def get_user_id_from_username(guild, username):
    user = discord.utils.get(guild.members, name=username)
    return str(user.id) if user else None


async def _run_command_test(ctx, command_name, *args, **kwargs) -> str:
    """
    Helper to invoke a bot command and return a short pass/fail string.
    Used by the !runtests command to exercise options safely.
    """
    cmd = bot.get_command(command_name)
    if cmd is None:
        return f"{command_name}: ⚠️ command not found"

    try:
        await ctx.invoke(cmd, *args, **kwargs)
        return f"{command_name}: ✅ passed"
    except Exception as e:
        return f"{command_name}: ❌ {type(e).__name__}: {e}"


# persona handling
@bot.command(name='createpersona')
async def create_persona(ctx, name: str, *, persona_description: str):
    global personas
    personas[name] = persona_description
    save_personas()
    await ctx.send(f"Persona '{name}' created.")


@bot.command(name='switchpersona')
async def switch_persona(ctx, name: str):
    global current_persona
    if name in personas:
        current_persona = name
        await ctx.send(f"Switched to persona '{current_persona}'.")
    else:
        await ctx.send("Persona not found.")


@bot.command(name='listpersonas')
async def list_personas(ctx):
    global personas
    if personas:
        persona_list = '\n'.join(personas.keys())
        await ctx.send(f"Available Personas:\n{persona_list}")
    else:
        await ctx.send("No personas available.")


@bot.command(name='currentpersona')
async def current_persona_cmd(ctx):
    global current_persona
    if current_persona in personas:
        await ctx.send(f"The current persona is '{current_persona}'.")
    else:
        await ctx.send("No specific persona is currently active.")


@bot.command(name='deletepersona')
async def delete_persona(ctx, name: str):
    global personas
    if name in personas:
        del personas[name]
        save_personas()
        await ctx.send(f"Persona '{name}' has been deleted.")
    else:
        await ctx.send(f"No persona found with the name '{name}'.")


@bot.command(name='erasememory')
async def erase_memory(ctx, number_of_interactions: int = None):
    user_id = str(ctx.author.id)
    global current_persona

    if user_id in conversations and current_persona in conversations[user_id]:
        if number_of_interactions is None:
            conversations[user_id][current_persona] = []
            message = f"All memory of our conversations as '{current_persona}' has been erased."
        else:
            number_of_messages_to_remove = min(
                number_of_interactions * 2, len(conversations[user_id][current_persona])
            )
            conversations[user_id][current_persona] = conversations[user_id][current_persona][
                                                      :-number_of_messages_to_remove]
            message = f"Erased the last {number_of_interactions} interactions."

        save_conversations()
        await ctx.send(message)
    else:
        await ctx.send("No conversation history found for you.")


# Bowling score-related commands
@bot.command(name='pb')
async def personal_best(ctx):
    if not scores:
        await ctx.send("No scores found for Jun.")
        return
    pb = max(score[0] for score in scores)
    await ctx.send(f"Jun's personal best score is: {pb}")


@bot.command(name='avg')
async def average_score(ctx):
    if not scores:
        await ctx.send("No scores found for Jun.")
        return
    avg = sum(score[0] for score in scores) / len(scores)
    await ctx.send(f"Jun's average score is: {avg:.2f}")


@bot.command(name='median')
async def median_score(ctx):
    if not scores:
        await ctx.send("No scores found for Jun.")
        return

    sorted_scores = sorted([score[0] for score in scores])
    length = len(sorted_scores)
    if length % 2 == 0:
        median = (sorted_scores[length // 2 - 1] + sorted_scores[length // 2]) / 2
    else:
        median = sorted_scores[length // 2]

    await ctx.send(f"Jun's median score is: {median:.2f}")


@bot.command(name='all')
async def all_scores(ctx):
    try:
        if not scores:
            await ctx.send("No scores found for Jun.")
            return

        unique_timestamps = set()
        unique_scores = []
        for score, timestamp in scores:
            if timestamp not in unique_timestamps:
                unique_scores.append((score, timestamp))
                unique_timestamps.add(timestamp)

        response = "Jun's scores:\n"
        for score, timestamp in sorted(unique_scores, key=lambda x: x[1]):
            line = f"Score: {score} on {timestamp.strftime('%Y-%m-%d %H:%M:%S')}\n"

            if len(response) + len(line) > 2000:
                await ctx.send(response)
                response = "Jun's scores (contd.):\n"

            response += line

        await ctx.send(response)
        logging.info("Processed !all command successfully.")
    except Exception as e:
        logging.error(f"Error in !all command: {e}")
        await ctx.send("An error occurred while processing the command.")


@bot.command(name='delete')
async def delete_score(ctx, *, timestamp_str):
    try:
        target_timestamp = datetime.strptime(timestamp_str, '%Y-%m-%d %H:%M:%S')
        matching_scores = [(score, timestamp) for score, timestamp in scores if
                           timestamp.date() == target_timestamp.date()
                           and timestamp.time().hour == target_timestamp.time().hour
                           and timestamp.time().minute == target_timestamp.time().minute]

        if len(matching_scores) == 0:
            await ctx.send("Score with the given timestamp not found.")
            return

        if len(matching_scores) == 1:
            scores.remove(matching_scores[0])
            save_scores()
            await ctx.send(f"Score from {matching_scores[0][1].strftime('%Y-%m-%d %H:%M:%S')} has been deleted.")
        else:
            response = "Multiple scores found for the given minute. Please specify which one you'd like to delete:\n"
            for i, (score, timestamp) in enumerate(matching_scores):
                response += f"{i + 1}. Score: {score} on {timestamp.strftime('%Y-%m-%d %H:%M:%S')}\n"
            await ctx.send(response)

    except ValueError:
        await ctx.send("Invalid timestamp format. Please ensure you're using the format %Y-%m-%d %H:%M:%S.")


@bot.command(name='bowlinggraph')
async def graph_scores(ctx):
    try:
        dates = [score[1] for score in scores]
        score_values = [score[0] for score in scores]

        plt.scatter(dates, score_values, color='blue', label='Scores')

        x = np.array([date.timestamp() for date in dates])
        y = np.array(score_values)
        slope, intercept, r_value, p_value, std_err = linregress(x, y)
        plt.plot(dates, intercept + slope * x, color='red', label=f'Trendline (R={r_value:.2f})')

        plt.title('Jun\'s Bowling Scores Over Time')
        plt.xlabel('Date (MM-DD-YY)')
        plt.ylabel('Score')
        plt.legend()
        plt.tight_layout()

        plt.gca().xaxis.set_major_formatter(mdates.DateFormatter('%m-%d-%Y'))
        plt.gca().xaxis.set_major_locator(mdates.MonthLocator())
        plt.gcf().autofmt_xdate()

        plt.savefig(str(DATA_DIR / "scores_graph.png"))
        await ctx.send(file=discord.File(str(DATA_DIR / "scores_graph.png")))
        plt.close()

    except Exception as e:
        await ctx.send(f"Error generating graph: {e}")


@bot.command(name='bowlingdistgraph')
async def distribution_graph(ctx):
    score_values = [score[0] for score in scores]

    plt.figure(figsize=(10, 6))
    sns.histplot(score_values, bins=30, kde=True, color='blue')
    plt.title('Distribution of Jun\'s Bowling Scores')
    plt.xlabel('Score')
    plt.ylabel('Frequency')
    plt.tight_layout()

    file_name = str(DATA_DIR / "distribution_graph.png")
    plt.savefig(file_name)
    plt.close()

    await ctx.send(file=discord.File(file_name))


@bot.command(name='add')
async def add_score(ctx, score: int, *, timestamp_str: str):
    try:
        timestamp = datetime.strptime(timestamp_str, '%Y-%m-%d %H:%M:%S')
        scores.append((score, timestamp))
        save_scores()

        await ctx.send(f"Added score {score} on {timestamp.strftime('%Y-%m-%d %H:%M:%S')}.")
    except ValueError:
        await ctx.send("Invalid timestamp format. Please use the format %Y-%m-%d %H:%M:%S.")


# purge bot messages, limited to whiptail username
@bot.command(name='purge')
async def purge_bot_messages(ctx):
    if ctx.author.name != 'whiptail':
        await ctx.send("You do not have permission to use this command.")
        return

    command_pattern = re.compile(r'^\$\w+')

    def is_bot_mention_or_command(m):
        return (
            m.author == bot.user
            or m.content.startswith('!')
            or command_pattern.match(m.content)
            or bot.user in m.mentions
        )

    deleted = await ctx.channel.purge(limit=100, check=is_bot_mention_or_command)
    await ctx.send(f"Deleted {len(deleted)} messages.", delete_after=5)


@bot.command(name='sussygraph')
async def sussy_graph(ctx):
    try:
        with open(SUS_FILE, 'r') as f:
            usage_data = json.load(f)

        usage_data_sorted = sorted(usage_data, key=lambda x: x['timestamp'])
        timestamps = [datetime.fromisoformat(entry['timestamp']) for entry in usage_data_sorted]

        filtered_timestamps = [timestamps[0]]
        filtered_counts = [0]
        for i in range(1, len(timestamps)):
            if timestamps[i] >= filtered_timestamps[-1]:
                filtered_timestamps.append(timestamps[i])
                filtered_counts.append(i)

        plt.figure(figsize=(15, 6))
        plt.scatter(filtered_timestamps, filtered_counts)
        plt.gca().xaxis.set_major_formatter(mdates.DateFormatter('%Y-%m'))
        plt.gca().xaxis.set_major_locator(mdates.MonthLocator())
        plt.xlim([datetime(2020, 1, 1), max(filtered_timestamps) + timedelta(days=30)])
        plt.grid(False)
        plt.gcf().autofmt_xdate()
        plt.xlabel('Date')
        plt.ylabel('Cumulative Count')
        plt.title('Lhea "sus" Usage Over Time')

        plt.savefig(str(DATA_DIR / 'sussy_usage_graph.png'))
        await ctx.send(file=discord.File(str(DATA_DIR / 'sussy_usage_graph.png')))
        plt.close()

    except Exception as e:
        await ctx.send(f"Error: {e}")


@bot.command(name='sussy')
async def sussy_count(ctx):
    try:
        with open(SUS_FILE, 'r') as f:
            usage_data = json.load(f)

        total_count = len(usage_data)
        await ctx.send(f"Lhea has used 'sus' a total of {total_count} times.")
    except Exception as e:
        await ctx.send(f"Error: {e}")


@bot.command(name='explode')
async def explode_count(ctx):
    try:
        with open(EXPLODE_FILE, 'r') as f:
            usage_data = json.load(f)

        emote_name = 'explode'
        emote = discord.utils.get(ctx.guild.emojis, name=emote_name)
        if not emote:
            all_emotes = [emote for guild in bot.guilds for emote in guild.emojis if emote.available]
            emote = discord.utils.find(lambda e: e.name == emote_name, all_emotes)
        emote_str = str(emote) if emote else ''

        total_count = len(usage_data)
        await ctx.send(f"Whiptail has {emote_str} a total of {total_count} times.")
    except Exception as e:
        await ctx.send(f"Error: {e}")


@bot.command(name='explodegraph')
async def explode_graph(ctx):
    try:
        with open(EXPLODE_FILE, 'r') as f:
            usage_data = json.load(f)

        usage_data_sorted = sorted(usage_data, key=lambda x: x['timestamp'])
        timestamps = [datetime.fromisoformat(entry['timestamp']) for entry in usage_data_sorted]

        filtered_timestamps = [timestamps[0]]
        filtered_counts = [0]
        for i in range(1, len(timestamps)):
            if timestamps[i] >= filtered_timestamps[-1]:
                filtered_timestamps.append(timestamps[i])
                filtered_counts.append(i)

        plt.figure(figsize=(15, 6))
        plt.scatter(filtered_timestamps, filtered_counts)
        plt.gca().xaxis.set_major_formatter(mdates.DateFormatter('%Y-%m'))
        plt.gca().xaxis.set_major_locator(mdates.MonthLocator())
        plt.xlim([datetime(2022, 4, 1), max(filtered_timestamps) + timedelta(days=30)])
        plt.grid(False)
        plt.gcf().autofmt_xdate()
        plt.xlabel('Date')
        plt.ylabel('Cumulative Count')
        plt.title("Whiptail's Explosions Over Time")

        plt.savefig(str(DATA_DIR / 'explode_usage_graph.png'))
        await ctx.send(file=discord.File(str(DATA_DIR / 'explode_usage_graph.png')))
        plt.close()

    except Exception as e:
        await ctx.send(f"Error: {e}")


@bot.command(name='grindgraph')
async def spinny_graph(ctx):
    try:
        with open(SPINNY_FILE, 'r') as f:
            usage_data = json.load(f)

        usage_data_sorted = sorted(usage_data, key=lambda x: x['timestamp'])
        timestamps = [datetime.fromisoformat(entry['timestamp']) for entry in usage_data_sorted]

        filtered_timestamps = [timestamps[0]]
        filtered_counts = [0]
        for i in range(1, len(timestamps)):
            if timestamps[i] >= filtered_timestamps[-1]:
                filtered_timestamps.append(timestamps[i])
                filtered_counts.append(i)

        plt.figure(figsize=(15, 6))
        plt.scatter(filtered_timestamps, filtered_counts)
        plt.gca().xaxis.set_major_formatter(mdates.DateFormatter('%Y-%m'))
        plt.gca().xaxis.set_major_locator(mdates.MonthLocator())
        plt.xlim([datetime(2021, 10, 1), max(filtered_timestamps) + timedelta(days=30)])
        plt.grid(False)
        plt.gcf().autofmt_xdate()
        plt.xlabel('Date')
        plt.ylabel('Cumulative Count')
        plt.title('Grinding Usage Over Time')

        plt.savefig(str(DATA_DIR / 'spinny_usage_graph.png'))
        await ctx.send(file=discord.File(str(DATA_DIR / 'spinny_usage_graph.png')))
        plt.close()

    except Exception as e:
        await ctx.send(f"Error: {e}")


@bot.command(name='grindcount')
async def spinny_count(ctx):
    try:
        with open(SPINNY_FILE, 'r') as f:
            usage_data = json.load(f)

        total_count = len(usage_data)
        await ctx.send(f"Grinding has occurred {total_count} times.")
    except Exception as e:
        await ctx.send(f"Error: {e}")


# sends a random bowling gif
@bot.command(name='gif')
async def send_gif(ctx):
    try:
        async with aiohttp.ClientSession() as session:
            response = await session.get(
                f"https://api.giphy.com/v1/gifs/random?api_key={GIPHY_API_KEY}&tag=bowling&rating=g")
            json_response = await response.json()
            if 'data' in json_response and 'images' in json_response['data'] and 'original' in json_response['data'][
                'images'] and 'url' in json_response['data']['images']['original']:
                gif_url = json_response['data']['images']['original']['url']
                await ctx.send(gif_url)
            else:
                await ctx.send(f"Unexpected API response structure.")
    except Exception as e:
        await ctx.send(f"Error fetching GIF: {e}")


@bot.command(name='random')
async def random_cmd(ctx):
    try:
        pinned_messages = await ctx.channel.pins()

        if not pinned_messages:
            await ctx.send("There are no pinned messages in this channel.")
            return

        random_message = random.choice(pinned_messages)

        author_info = f"Message by {random_message.author.display_name} [Jump to message]({random_message.jump_url})"

        if random_message.content:
            await ctx.send(f"{author_info}\n\n{random_message.content}")
        else:
            await ctx.send(author_info)

        if random_message.attachments:
            attachment_url = random_message.attachments[0].url
            await ctx.send(attachment_url)

    except Exception as e:
        await ctx.send(f"An error occurred: {e}")
        print(f"Error: {e}")


# Connect to SQLite database
def connect_db():
    return sqlite3.connect(DATABASE_FILE)


def create_table():
    with connect_db() as conn:
        c = conn.cursor()
        c.execute('''CREATE TABLE IF NOT EXISTS reminders
                    (reminder_id INTEGER PRIMARY KEY, user_id TEXT, channel_id TEXT, reminder_time TEXT, message TEXT, sent INTEGER DEFAULT 0)''')
        conn.commit()


create_table()


@bot.command()
async def remind(ctx, *, args=None, unit=None, quantity=None):
    await ctx.send(f"Please follow this format: !remindme in X seconds/minutes/hours/days.")


@bot.command()
async def remindme(ctx, *, args=None):
    try:
        delete_expired_reminders()
        with connect_db() as conn:
            c = conn.cursor()
            if args is None:
                c.execute('SELECT reminder_id, reminder_time, message FROM reminders WHERE user_id=?',
                          (str(ctx.author.id),))
                reminders = c.fetchall()

                if not reminders:
                    await ctx.send(f"{ctx.author.mention}, you have no reminders set.")
                    return

                current_time = datetime.utcnow()
                upcoming_reminders = [r for r in reminders if
                                      datetime.strptime(r[1], '%Y-%m-%d %H:%M:%S') > current_time]
                missed_reminders = [r for r in reminders if r not in upcoming_reminders]

                if upcoming_reminders:
                    reminder_list = "\n".join([
                        f"ID {r[0]} - At {r[1]} ({ceil((datetime.strptime(r[1], '%Y-%m-%d %H:%M:%S') - current_time).total_seconds() / 60)} minutes left): {r[2]}"
                        for r in upcoming_reminders])
                    await ctx.send(f"{ctx.author.mention}, your upcoming reminders are:\n{reminder_list}")

                if missed_reminders:
                    missed_list = "\n".join([
                        f"ID {r[0]} - At {r[1]} (Past reminder from {ceil((current_time - datetime.strptime(r[1], '%Y-%m-%d %H:%M:%S')).total_seconds() / 60)} minutes ago): {r[2]}"
                        for r in missed_reminders])
                    await ctx.send(f"{ctx.author.mention}, your past reminders are:\n{missed_list}")

                return

            message_link = f"https://discord.com/channels/{ctx.guild.id}/{ctx.channel.id}/{ctx.message.reference.message_id if ctx.message.reference else ctx.message.id}"

            if re.match(r'in (\d+ [a-z]+(, )?)+', args):
                match = re.findall(r'(\d+) ([a-z]+)', args)
                if match:
                    time_units = {
                        'second': 'seconds', 'sec': 'seconds',
                        'minute': 'minutes', 'min': 'minutes',
                        'hour': 'hours', 'hr': "hours",
                        'day': 'days',
                        'week': 'weeks',
                        'month': 'days',
                        'year': 'days'
                    }

                    delta_args = {}
                    for qty, unit in match:
                        unit = unit.lower().rstrip('s')
                        if unit in time_units:
                            key = time_units[unit]
                            factor = 30 if unit == "month" else (365 if unit == "year" else 1)
                            if key in delta_args:
                                delta_args[key] += int(qty) * factor
                            else:
                                delta_args[key] = int(qty) * factor
                        else:
                            await ctx.send(
                                f"{ctx.author.mention}, couldn't understand the time unit '{unit}'. Please try again.")
                            return

                    reminder_time = datetime.utcnow() + timedelta(**delta_args)
                else:
                    await ctx.send(f"{ctx.author.mention}, couldn't understand the format. Please try again.")
                    return
            else:
                for date_format in ["%I:%M%p %Y-%m-%d", "%I:%M%p %m-%d-%Y", "%I:%M %Y-%m-%d"]:
                    try:
                        split_args = args.split(' at ')
                        if len(split_args) > 1:
                            reminder_time = datetime.strptime(split_args[1], date_format)
                            reminder_time = reminder_time.replace(tzinfo=pytz.utc)
                            break
                        else:
                            await ctx.send(
                                f"{ctx.author.mention} Please follow this format: !remindme in X seconds/minutes/hours/days.")
                            return
                    except ValueError:
                        continue
                else:
                    await ctx.send(
                        f"{ctx.author.mention} Please follow this format: !remindme in X seconds/minutes/hours/days.")
                    return

            reminder_time_utc = reminder_time.strftime('%Y-%m-%d %H:%M:%S')
            c.execute(
                'INSERT INTO reminders (user_id, channel_id, reminder_time, message, sent) VALUES (?, ?, ?, ?, 0)',
                (str(ctx.author.id), str(ctx.channel.id), reminder_time_utc,
                 f'Reminder! [Link]({message_link})'))
            conn.commit()
            reminder_id = c.lastrowid
            await ctx.send(f"{ctx.author.mention}, reminder set for {reminder_time_utc} with ID `{reminder_id}`!")

    except Exception as e:
        await ctx.send(f"An error occurred: {e}")


@bot.command()
async def deletereminder(ctx, reminder_id: int):
    with connect_db() as conn:
        c = conn.cursor()
        c.execute('SELECT reminder_id FROM reminders WHERE reminder_id=? AND user_id=?',
                  (reminder_id, str(ctx.author.id)))
        reminder = c.fetchone()
        if reminder:
            c.execute('DELETE FROM reminders WHERE reminder_id=?', (reminder_id,))
            conn.commit()
            await ctx.send(f"{ctx.author.mention}, reminder with ID `{reminder_id}` has been deleted!")
        else:
            await ctx.send(
                f"{ctx.author.mention}, no reminder found with ID `{reminder_id}` or you don't have permission to delete it.")


@tasks.loop(seconds=10)
async def check_reminders():
    with connect_db() as conn:
        c = conn.cursor()
        print("Checking reminders...")
        now = datetime.now()
        c.execute('SELECT user_id, message FROM reminders WHERE reminder_time<=? AND sent=0',
                  (now.strftime('%Y-%m-%d %H:%M:%S'),))
        reminders = c.fetchall()

        for reminder in reminders:
            user = await bot.fetch_user(reminder[0])
            channel = discord.utils.get(bot.get_all_channels(), name="wat-doggo-only")
            if channel:
                await channel.send(f"{user.mention}, {reminder[1]}")
                c.execute('UPDATE reminders SET sent=1 WHERE user_id=? AND message=?', (reminder[0], reminder[1]))
                conn.commit()

        print(f"{len(reminders)} reminders checked and sent")


@bot.command()
async def currenttime(ctx):
    await ctx.send(datetime.now().strftime('%Y-%m-%d %H:%M:%S'))


@bot.event
async def on_command_error(ctx, error):
    if isinstance(error, commands.CommandNotFound):
        return
    raise error


def add_sent_column():
    with connect_db() as conn:
        c = conn.cursor()
        c.execute('''ALTER TABLE reminders ADD COLUMN sent INTEGER DEFAULT 0''')
        conn.commit()


def delete_expired_reminders():
    with connect_db() as conn:
        c = conn.cursor()
        current_time = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        c.execute('DELETE FROM reminders WHERE reminder_time < ? AND sent = 1', (current_time,))
        conn.commit()


class EmoteListSource(menus.ListPageSource):
    async def format_page(self, menu, items):
        embed = discord.Embed(title="Available Emotes", description='\n'.join(items), color=0x55a7f7)
        embed.set_footer(text=f"Page {menu.current_page + 1}/{self.get_max_pages()}")
        return embed


class EmotesMenu(menus.MenuPages):
    pass


@bot.command(name='allemotes')
async def all_emotes(ctx):
    emotes = ctx.guild.emojis
    if not emotes:
        await ctx.send("No emotes found on the server.")
        return

    emotes_list = [f"{emote} :`:{emote.name}:`" for emote in emotes]
    pages = EmotesMenu(source=EmoteListSource(emotes_list, per_page=10))
    await pages.start(ctx)


@bot.command()
async def roulette(ctx):
    try:
        async with aiohttp.ClientSession() as session:
            response = await session.get(f"https://api.giphy.com/v1/gifs/random?api_key={GIPHY_API_KEY}")
            json_response = await response.json()
            if 'data' in json_response and 'images' in json_response['data'] and 'original' in json_response['data'][
                'images'] and 'url' in json_response['data']['images']['original']:
                gif_url = json_response['data']['images']['original']['url']
                await ctx.send(gif_url)
            else:
                await ctx.send("Unexpected API response structure.")
    except Exception as e:
        await ctx.send(f"Error fetching GIF: {str(e)}")


@bot.command()
async def cat(ctx):
    async with aiohttp.ClientSession() as session:
        try:
            data = await fetch_url(session, 'https://api.thecatapi.com/v1/images/search')
            if data:
                embed = discord.Embed()
                embed.set_image(url=data[0]['url'])
                await ctx.send(embed=embed)
            else:
                await ctx.send("Error fetching cat image.")
        except Exception as e:
            await ctx.send(f"Error fetching cat image: {e}")


async def fetch_url(session, url):
    async with session.get(url) as response:
        return await response.json()


@bot.command()
async def dog(ctx):
    async with aiohttp.ClientSession() as session:
        try:
            data = await fetch_url(session, 'https://dog.ceo/api/breeds/image/random')
            if data and data['status'] == 'success':
                embed = discord.Embed()
                embed.set_image(url=data['message'])
                await ctx.send(embed=embed)
            else:
                await ctx.send(f"Dog API responded with a non-200 status. Response: {data}")
        except Exception as e:
            await ctx.send(f"Error fetching dog image: {e}")


bark_variations = [
    "Bark", "Arf", "Woof", "Bork", "Boof", "Yap", "Yip", "Bow-wow", "Ruff", "Wuff", "Borf", "Baroo"
]


@bot.command()
async def dogbark(ctx):
    bark_choice = random.choice(bark_variations)
    ascii_art = pyfiglet.figlet_format(bark_choice)
    await ctx.send(f"```\n{ascii_art}\n```")


@bot.command()
async def startminecraft(ctx):
    await send_server_feature_removed(ctx)


@bot.command()
async def stopminecraft(ctx):
    await send_server_feature_removed(ctx)


@bot.command()
async def minecraftstatus(ctx):
    await send_server_feature_removed(ctx)


@bot.command(name='minecraftserver')
async def fetch_server_ip(ctx):
    await send_server_feature_removed(ctx)


@bot.command()
async def startskyfactory(ctx):
    await send_server_feature_removed(ctx)


@bot.command()
async def stopskyfactory(ctx):
    await send_server_feature_removed(ctx)


@bot.command()
async def skyfactorystatus(ctx):
    await send_server_feature_removed(ctx)


@bot.command(name='skyfactoryserver')
async def fetch_skyfactory_ip(ctx):
    await send_server_feature_removed(ctx)


@bot.command(name='uptime')
async def uptime(ctx):
    await send_server_feature_removed(ctx)


@bot.command()
async def emote(ctx, emote_name: str, size: int = 2):
    if size not in [1, 2, 3, 4]:
        await ctx.send("Invalid size. Please choose a size between 1 and 4.")
        return

    back_button_emoji = '⬅️'
    first_page_emoji = '🔙'
    random_pick_emoji = '🎲'
    next_page_emoji = '➡️'
    no_selection_emoji = '❌'
    number_emojis = ['1️⃣', '2️⃣', '3️⃣', '4️⃣', '5️⃣']
    page_number = 1
    emotes_per_page = 5
    max_retries = 3
    retry_count = 0
    backoff_factor = 1

    while True:
        messages = []
        session = aiohttp.ClientSession()
        mySevenTvSession = seventv.seventv()
        try:
            if retry_count == 0:
                emotes = await mySevenTvSession.emote_search(
                    emote_name, limit=emotes_per_page, page=page_number,
                    case_sensitive=False, exact_match=True
                )
                if not emotes:
                    if page_number == 1:
                        await ctx.send("No emotes found.")
                        break
                    else:
                        await ctx.send("No more emotes, returning to the beginning.")
                        page_number = 1
                        continue

                for i, emote in enumerate(emotes):
                    emote_url = f"https:{emote.host_url}/2x.webp"
                    async with session.get(emote_url) as resp:
                        if resp.status == 200:
                            image_data = await resp.read()
                            image = Image.open(io.BytesIO(image_data))
                            file_extension = 'gif' if getattr(image, "is_animated",
                                                              False) and image.n_frames > 1 else 'png'

                    direct_link = f"https:{emote.host_url}/2x.{file_extension}"
                    message = await ctx.send(direct_link, silent=True)
                    messages.append(message)
                    await message.add_reaction(number_emojis[i])

                if page_number > 1:
                    await messages[-1].add_reaction(back_button_emoji)
                await messages[-1].add_reaction(first_page_emoji)
                await messages[-1].add_reaction(random_pick_emoji)
                if len(emotes) == emotes_per_page:
                    await messages[-1].add_reaction(next_page_emoji)
                await messages[-1].add_reaction(no_selection_emoji)

                def check(reaction, user):
                    return user == ctx.author and (
                        str(reaction.emoji) in number_emojis[:len(emotes)] + [next_page_emoji,
                                                                              back_button_emoji,
                                                                              first_page_emoji,
                                                                              random_pick_emoji,
                                                                              no_selection_emoji]
                        and reaction.message.id in [m.id for m in messages]
                    )

                try:
                    reaction, user = await bot.wait_for('reaction_add', timeout=60.0, check=check)
                except asyncio.TimeoutError:
                    await ctx.send('🚫 No reaction received in time.')
                    for message in messages:
                        try:
                            await message.delete()
                        except discord.NotFound:
                            pass
                    return

                try:
                    for message in messages:
                        await message.delete()
                except discord.NotFound:
                    pass

                if not emotes and str(reaction.emoji) == next_page_emoji:
                    await ctx.send("No more emotes, returning to the beginning.")
                    page_number = 1
                    continue

                if str(reaction.emoji) == next_page_emoji:
                    logging.info("Next page emoji pressed")
                    try:
                        next_page_emotes = await mySevenTvSession.emote_search(
                            emote_name, limit=emotes_per_page, page=page_number + 1,
                            case_sensitive=False, exact_match=True
                        )
                    except Exception as e:
                        logging.error(f"An error occurred: {e}")
                        if "No Items Found" in str(e):
                            await ctx.send("No more emotes, going back to the beginning.")
                            page_number = 1
                            continue
                        elif "Rate Limit Reached" in str(e):
                            if retry_count < max_retries:
                                wait_time = backoff_factor * (2 ** retry_count)
                                await ctx.send(f"Rate limit reached, retrying in {wait_time} second(s)...")
                                await asyncio.sleep(wait_time)
                                retry_count += 1
                                continue
                            else:
                                await ctx.send("Rate limit reached. Please try again later.")
                                break
                        else:
                            await ctx.send(f"An error occurred: {str(e)}")
                            break

                    if next_page_emotes:
                        page_number += 1

                    try:
                        for message in messages:
                            await message.delete()
                    except discord.NotFound:
                        pass

                    continue

                elif str(reaction.emoji) == back_button_emoji:
                    try:
                        page_number = max(1, page_number - 1)
                        continue
                    except Exception as e:
                        if "Rate Limit Reached" in str(e):
                            if retry_count < max_retries:
                                wait_time = backoff_factor * (2 ** retry_count)
                                await ctx.send(f"Rate limit reached, retrying in {wait_time} second(s)...")
                                await asyncio.sleep(wait_time)
                                retry_count += 1
                                continue
                            else:
                                await ctx.send("Rate limit reached. Please try again later.")
                                break
                        else:
                            await ctx.send(f"An error occurred: {str(e)}")
                            break
                elif str(reaction.emoji) == first_page_emoji:
                    try:
                        page_number = 1
                        continue
                    except Exception as e:
                        if "Rate Limit Reached" in str(e):
                            if retry_count < max_retries:
                                wait_time = backoff_factor * (2 ** retry_count)
                                await ctx.send(f"Rate limit reached, retrying in {wait_time} second(s)...",
                                               delete_after=wait_time)
                                await asyncio.sleep(wait_time)
                                retry_count += 1
                                continue
                            else:
                                await ctx.send("Rate limit reached. Please try again later.")
                                break
                        else:
                            await ctx.send(f"An error occurred: {str(e)}")
                            break
                elif str(reaction.emoji) == random_pick_emoji:
                    chosen_emote = random.choice(emotes)
                    chosen_emote_url = f"https:{chosen_emote.host_url}/4x.webp"
                    async with session.get(chosen_emote_url) as resp:
                        if resp.status == 200:
                            chosen_image_data = await resp.read()
                            chosen_image = Image.open(io.BytesIO(chosen_image_data))
                            chosen_file_extension = 'gif' if getattr(chosen_image, "is_animated",
                                                                     False) and chosen_image.n_frames > 1 else 'png'

                    chosen_direct_link = f"https:{chosen_emote.host_url}/{size}x.{chosen_file_extension}"
                    await ctx.send(chosen_direct_link)
                    break
                elif str(reaction.emoji) == no_selection_emoji:
                    await ctx.send("None selected... cleaning up...", delete_after=5.0)
                    for message in messages:
                        try:
                            await message.delete()
                        except discord.NotFound:
                            pass
                    await ctx.message.delete()
                    return
                else:
                    relative_index = number_emojis.index(str(reaction.emoji))
                    if relative_index < len(emotes):
                        chosen_emote = emotes[relative_index]
                        chosen_emote_url = f"https:{chosen_emote.host_url}/4x.webp"
                        async with session.get(chosen_emote_url) as resp:
                            if resp.status == 200:
                                chosen_image_data = await resp.read()
                                chosen_image = Image.open(io.BytesIO(chosen_image_data))
                                chosen_file_extension = 'gif' if getattr(chosen_image, "is_animated",
                                                                         False) and chosen_image.n_frames > 1 else 'png'

                        chosen_direct_link = f"https:{chosen_emote.host_url}/{size}x.{chosen_file_extension}"
                        await ctx.send(chosen_direct_link)
                        break
                    else:
                        await ctx.send(f"An error occurred")
                        continue

        except Exception as e:
            logging.error(f"An error occurred: {e}")
            if "Rate Limit Reached" in str(e):
                if retry_count < max_retries:
                    wait_time = backoff_factor * (2 ** retry_count)
                    await ctx.send(f"Rate limit reached, retrying in {wait_time} second(s)...",
                                   delete_after=wait_time)
                    await asyncio.sleep(wait_time)
                    retry_count += 1
                    continue
                else:
                    await ctx.send("Rate limit reached. Please try again later.")
                    break
            elif "Search returned no results" in str(e):
                if page_number > 1:
                    await ctx.send("No more emotes, returning to the beginning.")
                    page_number = 1
                    continue
                else:
                    await ctx.send("No emotes found.")
                    break
            elif "Server disconnected" in str(e):
                if retry_count < max_retries:
                    wait_time = backoff_factor * (2 ** retry_count)
                    await ctx.send(f"Retrying in {wait_time} second(s)...", delete_after=wait_time)
                    await asyncio.sleep(wait_time)
                    retry_count += 1
                    continue
                else:
                    await ctx.send("Error: server disconnected. Please try again later.")
                    break
            else:
                await ctx.send(f"An error occurred: {str(e)}")
                break

        finally:
            await session.close()
            await mySevenTvSession.close()

        retry_count = 0


@bot.command()
async def ss(ctx):
    await ctx.send(
        "https://cdn.discordapp.com/attachments/616874355821117483/1210844596263854120/redirect.jpg?ex=65ec09e8&is=65d994e8&hm=f8337efba567168da864124a7d3364381e322e436fb5ff02821219b65e649d19&"
    )


@bot.command(name='github')
async def github_repo(ctx):
    await ctx.send(f"Tinki-bot source: {GITHUB_REPO_URL}")


@bot.command(name='commands')
async def show_commands(ctx):
    commands_list_1 = """
**Bot Commands List - Part 1**

`!pb` - Shows Jun's personal best score.
`!avg` - Shows Jun's average score.
`!all` - Displays all of Jun's scores with timestamps.
`!delete [timestamp]` - Deletes a score with the specified timestamp.
`!bowlinggraph` - Generates a scatterplot of Jun's scores over time.
`!distribution` - Generates a distribution graph of Jun's scores over time.
`!bowlingdistgraph` - Generates a KDE plot of Jun's scores over time.
`!commands` - Shows this list of available commands.
`!add [score] '%Y-%m-%d %H:%M:%S'` - Allows you to add a bowling score.
`!median` - Shows Jun's median score.
`!purge` - Purges messages sent by the bot. Only usable by whiptail.
`!gif` - Posts a random bowling gif.
`!random` - Posts a random pinned message to the chat.
`!remindme in [x]` - Sets a reminder with a link to the message.
`!remindme` - Lists upcoming reminders.
`!deletereminder [ID]` - Deletes a reminder with the specified ID.
`!github` - Links to the bot source repository.
    """

    commands_list_2 = """
**Bot Commands List - Part 2**

`$[emotename] [number]` - Sends the emote as the bot the number of times (optional).
`$randomemote [number]` - Sends a random emote as the bot the number of times (optional).
`!allemotes` - Lists all available emotes to send.
`!roulette` - Sends a random gif.
`!cat` - Sends a random cat.
`!dog` - Sends a random dog.
`!dogbark` - Sends a random bark word in block letters.
`!startminecraft` - retired command; server hosting was removed
`!stopminecraft` - retired command; server hosting was removed
`!minecraftstatus` - retired command; server hosting was removed
`!minecraftserver` - retired command; server hosting was removed
`!uptime` - retired command; server hosting was removed
`!listpersonas` - lists available personas
`!createpersona [name] [prompt]` - creates a persona with the given name with description
`!switchpersona [name]` - switches to named persona
`!currentpersona` - shows the current used persona
`!deletepersona [name]` - deletes the named persona
`!erasememory [number]` - deletes past X interactions saved in memory
`!erasememory` - deletes memory as the current persona with the user
`!emote [name] [1-4]` - displays the top 5 emotes corresponding from 7tv api with the size selected
`!spinny @[user]` - grinding activated for @user
`!stopspinny @[user]` - grinding deactivated for @user
`!sussy` - shows how sussy lhea is
`!sussygraph` - graphs lhea's sussy
`!explode` - shows how many times Whiptail exploded
`!explodegraph` - graph of explode
    """

    commands_list_3 = """
**Bot Commands List - Part 3**
`!grindcount` - shows how many times grinding happened
`!grindgraph` - graph of grinding over time
`!startskyfactory` - retired command; server hosting was removed
`!stopskyfactory` - retired command; server hosting was removed
`!skyfactorystatus` - retired command; server hosting was removed
`!skyfactoryserver` - retired command; server hosting was removed
`!randomai on | off | status` - turns on random posting for Tinki
`!testurls` - tests the urls
`!runtests` - unit tests for the commands
    """

    try:
        await ctx.author.send(commands_list_1)
        await ctx.author.send(commands_list_2)
        await ctx.author.send(commands_list_3)
        await ctx.send(f"{ctx.author.mention}, I've sent you a DM with the list of commands!")
    except discord.Forbidden:
        await ctx.send(f"{ctx.author.mention}, I couldn't send you a DM. Please check your privacy settings.")


def get_test_channel():
    for channel in bot.get_all_channels():
        if str(channel).lower() == "bot-test":
            return channel
    return None


@bot.command(name="runtests")
@commands.has_permissions(administrator=True)
async def runtests(ctx):
    await ctx.send("Starting command self-tests…")
    results = await run_command_selftests(ctx)
    total = len(results)
    passed = sum(1 for _, ok, _ in results if ok)
    await ctx.send(f"Command tests complete: {passed}/{total} passed.")


@bot.command(name="testurls")
@commands.has_permissions(administrator=True)
async def testurls(ctx):
    await ctx.send("Starting URL rewrite tests…")
    results = run_url_selftests()
    for name, ok, reason in results:
        if ok:
            await ctx.send(f"{name}: ✅ passed")
        else:
            await ctx.send(f"{name}: ❌ {reason}")
    total = len(results)
    passed = sum(1 for _, ok, _ in results if ok)
    await ctx.send(f"URL tests complete: {passed}/{total} passed.")


async def run_startup_tests():
    await bot.wait_until_ready()

    test_channel = discord.utils.get(bot.get_all_channels(), name="bot-test")
    if not test_channel:
        print("No #bot-test channel found; skipping startup tests.")
        return

    cmd_results = await run_command_selftests(ctx=None)
    url_results = run_url_selftests()
    calc_results = run_calculate_selftests()
    letter_results = run_letter_count_selftests()

    cmd_total = len(cmd_results)
    cmd_passed = sum(1 for (_, ok, _) in cmd_results if ok)

    url_total = len(url_results)
    url_passed = sum(1 for (_, ok, _) in url_results if ok)

    calc_total = len(calc_results)
    calc_passed = sum(1 for (_, ok, _) in calc_results if ok)

    letter_total = len(letter_results)
    letter_passed = sum(1 for (_, ok, _) in letter_results if ok)

    failures = [
        f"{name}: {reason}"
        for (name, ok, reason) in cmd_results + url_results + calc_results + letter_results
        if not ok
    ]

    summary = (
        "🤖 **Bot restarted — running startup diagnostics…**\n"
        "```ini\n"
        "[BOOT SEQUENCE COMPLETED]\n"
        "```\n"
        f"🧪 **Command grid:** {cmd_passed}/{cmd_total} tests passed\n"
        f"🌐 **URL filter matrix:** {url_passed}/{url_total} tests passed\n"
        f"🔢 **Calculator gnome:** {calc_passed}/{calc_total} tests passed\n"
        f"🔤 **Letter gnome:** {letter_passed}/{letter_total} tests passed\n"
    )

    if failures:
        summary += "\n⚠️ **Anomalies detected:**\n"
        for f in failures:
            summary += f"• {f}\n"
    else:
        summary += "\n✨ **All systems fully operational.**"

    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    txt_output = []
    txt_output.append(f"Startup Diagnostic Results — {timestamp}\n")
    txt_output.append("============================================================\n")

    txt_output.append(f"\nCommand Tests: {cmd_passed}/{cmd_total} passed\n")
    for name, ok, reason in cmd_results:
        if ok:
            txt_output.append(f"  [PASS] {name}\n")
        else:
            txt_output.append(f"  [FAIL] {name} — {reason}\n")

    txt_output.append(f"\nURL Tests: {url_passed}/{url_total} passed\n")
    for name, ok, reason in url_results:
        if ok:
            txt_output.append(f"  [PASS] {name}\n")
        else:
            txt_output.append(f"  [FAIL] {name} — {reason}\n")

    txt_output.append(f"\nCalculator Tests: {calc_passed}/{calc_total} passed\n")
    for name, ok, reason in calc_results:
        if ok:
            txt_output.append(f"  [PASS] {name}\n")
        else:
            txt_output.append(f"  [FAIL] {name} — {reason}\n")

    txt_output.append(f"\nLetter Count Tests: {letter_passed}/{letter_total} passed\n")
    for name, ok, reason in letter_results:
        if ok:
            txt_output.append(f"  [PASS] {name}\n")
        else:
            txt_output.append(f"  [FAIL] {name} — {reason}\n")

    if failures:
        txt_output.append("\n=== FAILURES SUMMARY ===\n")
        for f in failures:
            txt_output.append(f"  {f}\n")

    txt_string = "".join(txt_output)

    file_buffer = io.BytesIO(txt_string.encode("utf-8"))
    discord_file = discord.File(file_buffer, filename="startup_test_results.txt")

    await test_channel.send(content=summary, file=discord_file)


async def run_command_selftests(ctx=None):
    tests = [
        ("pb", ()),
        ("avg", ()),
        ("median", ()),
        ("all", ()),
        ("bowlinggraph", ()),
        ("bowlingdistgraph", ()),

        ("gif", ()),
        ("random", ()),
        ("github", ()),
        ("allemotes", ()),
        ("roulette", ()),
        ("cat", ()),
        ("dog", ()),
        ("dogbark", ()),

        ("remindme", ()),
        ("listpersonas", ()),
        ("currentpersona", ()),

        ("sussy", ()),
        ("sussygraph", ()),
        ("explode", ()),
        ("explodegraph", ()),
        ("grindcount", ()),
        ("grindgraph", ()),

        ("minecraftstatus", ()),
        ("minecraftserver", ()),
        ("uptime", ()),
        ("skyfactorystatus", ()),
        ("skyfactoryserver", ()),
    ]

    results = []

    for name, args in tests:
        cmd = bot.get_command(name)
        if cmd is None:
            reason = "command not found"
            results.append((name, False, reason))
            if ctx:
                await ctx.send(f"{name}: ❌ {reason}")
            continue

        try:
            if ctx:
                await ctx.invoke(cmd, *args)
                await ctx.send(f"{name}: ✅ passed")

            results.append((name, True, None))
        except Exception as e:
            reason = f"{type(e).__name__}: {e}"
            results.append((name, False, reason))
            if ctx:
                await ctx.send(f"{name}: ❌ {reason}")

    return results


def run_url_selftests():
    test_cases = [
        (
            "twitter basic",
            "check this https://twitter.com/foo/bar",
            "check this https://vxtwitter.com/foo/bar",
        ),
        (
            "twitter www",
            "link: https://www.twitter.com/foo/bar",
            "link: https://vxtwitter.com/foo/bar",
        ),
        (
            "x.com",
            "post: https://x.com/foo/status/12345",
            "post: https://fixvx.com/foo/status/12345",
        ),
        (
            "instagram",
            "pic: https://www.instagram.com/p/ABC123",
            "pic: https://eeinstagram.com/p/ABC123",
        ),
        (
            "tiktok",
            "vid: https://www.tiktok.com/@user/video/987654321",
            "vid: https://tnktok.com/@user/video/987654321",
        ),
        (
            "reddit",
            "thread: https://www.reddit.com/r/test/comments/abc123/slug",
            "thread: https://rxddit.com/r/test/comments/abc123/slug",
        ),
        (
            "no-change",
            "hello there",
            "hello there",
        ),
    ]

    results = []
    for name, original, expected in test_cases:
        got = rewrite_social_urls(original)
        if got == expected:
            results.append((name, True, None))
        else:
            reason = f"expected `{expected}` but got `{got}`"
            results.append((name, False, reason))
    return results


def run_calculate_selftests():
    cases = [
        ("calc addition",       "2 + 2",          "4"),
        ("calc what-is prefix", "what is 10 + 5", "15"),
        ("calc x-multiply",     "3x4",             "12"),
        ("calc division",       "10 / 4",          "2.5"),
        ("calc large number",   "1000000 + 1",     "1,000,001"),
        ("calc non-expression", "hello world",      None),
        ("calc div-by-zero",    "5 / 0",            None),
    ]
    results = []
    for name, inp, expected in cases:
        got = maybe_calculate_reply(inp)
        if expected is None:
            ok = got is None
            reason = None if ok else f"expected None but got `{got}`"
        else:
            ok = got is not None and expected in got
            reason = None if ok else f"expected `{expected}` in result but got `{got}`"
        results.append((name, ok, reason))
    return results


def run_letter_count_selftests():
    cases = [
        ("letter r in strawberry",  "how many r's in strawberry",  "3"),
        ("letter s in mississippi", "how many s's in mississippi", "4"),
        ("letter e in cheese",      "how many e's in cheese?",     "3"),
        ("letter zero count",       "how many z's in apple",       "0"),
        ("letter no match",         "what time is it",              None),
    ]
    results = []
    for name, inp, expected in cases:
        got = maybe_count_letter_reply(inp)
        if expected is None:
            ok = got is None
            reason = None if ok else f"expected None but got `{got}`"
        else:
            ok = got is not None and expected in got
            reason = None if ok else f"expected `{expected}` in result but got `{got}`"
        results.append((name, ok, reason))
    return results


####################################################### AI STUFF ############################################################
async def generate_random_ai_thought():
    client = get_openai_client()

    response = client.chat.completions.create(
        model=OPENAI_MODEL,
        messages=[
            {
                "role": "system",
                "content": (
                    GREMLIN_SYSTEM_STYLE + " "
                    "Generate ONE shitpost-style thought you might randomly drop in Discord. "
                    "It should read like a joke or roast about gamers, Discord culture, or daily chaos. "
                    "No disclaimers, no greetings, no hashtags. Just the line itself."
                ),
            },
            {"role": "user", "content": "Give me one chaotic gremlin thought."},
        ],
        max_tokens=50,
        temperature=1.2,
    )

    return response.choices[0].message.content.strip()



async def random_ai_post_task():
    await bot.wait_until_ready()

    channel = discord.utils.get(bot.get_all_channels(), name="wat-doggo-only")

    while not bot.is_closed():
        wait_minutes = random.randint(60, 180)
        await asyncio.sleep(wait_minutes * 60)

        if RANDOM_AI_ENABLED and channel:
            thought = await generate_random_ai_thought()
            msg = await channel.send(thought)
            RANDOM_AI_MESSAGE_IDS.add(msg.id)


@bot.command(name="randomai")
@commands.has_permissions(administrator=True)
async def randomai(ctx, mode: str = "status"):
    """
    Toggle random AI posting on/off.
    Usage: !randomai on | off | status
    """
    global RANDOM_AI_ENABLED
    mode = mode.lower()

    # Turn ON
    if mode in ("on", "enable", "start"):
        RANDOM_AI_ENABLED = True
        await ctx.send("🔊 **Random AI posting enabled.** Tinki may speak at any time.")

        # Change status to busy
        await bot.change_presence(
            status=discord.Status.do_not_disturb,
            activity=discord.Game(name="Generating thoughts...")
        )

        # Immediately post one AI message
        channel = ctx.channel
        thought = await generate_random_ai_thought()
        msg = await channel.send(thought)
        RANDOM_AI_MESSAGE_IDS.add(msg.id)
        return

    # Turn OFF
    elif mode in ("off", "disable", "stop"):
        RANDOM_AI_ENABLED = False
        await ctx.send("🔇 **Random AI posting disabled.** Tinki will stay silent unless invoked.")

        # Change status back to normal
        await bot.change_presence(
            status=discord.Status.online,
            activity=discord.Game(name="Ready to help!")
        )
        return

    # Status
    else:
        status = "ON" if RANDOM_AI_ENABLED else "OFF"
        emoji = "🟢" if RANDOM_AI_ENABLED else "🔴"
        await ctx.send(f"{emoji} **Random AI posting is currently {status}.**")



async def generate_reaction_reply(original_text: str, username: str, emoji: str) -> str:
    client = get_openai_client()

    system_prompt = (
        GREMLIN_SYSTEM_STYLE + " "
        "You are reacting to someone reacting to your message. "
        "Make a short roast or snarky remark about their reaction or vibe. "
        "1–2 sentences max."
    )

    user_prompt = (
        f"Your original message was:\n"
        f"\"{original_text}\"\n\n"
        f"The user '{username}' reacted with '{emoji}'. "
        f"Write a short, playful roast/snarky reply. "
        f"Do NOT be wholesome or reassuring."
    )

    response = client.chat.completions.create(
        model=OPENAI_MODEL,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        max_tokens=60,
        temperature=1.1,
    )

    return response.choices[0].message.content.strip()



async def generate_reply_to_reply(original_text: str, user: discord.User, user_text: str) -> str:
    client = get_openai_client()

    response = client.chat.completions.create(
        model=OPENAI_MODEL,
        messages=[
            {
                "role": "system",
                "content": (
                    GREMLIN_SYSTEM_STYLE + " "
                    "You are replying to someone who replied to your earlier message. "
                    "Make it sound like a gremlin roasting their take. "
                    "1–2 sentences. No serious advice, no therapy talk."
                ),
            },
            {
                "role": "user",
                "content": (
                    f"Your original message was:\n"
                    f"\"{original_text}\"\n\n"
                    f"The user '{user.display_name}' replied with:\n"
                    f"\"{user_text}\"\n\n"
                    f"Write a short, playful roast/snarky answer."
                ),
            },
        ],
        max_tokens=60,
        temperature=1.1,
    )

    return response.choices[0].message.content.strip()



@bot.event
async def on_raw_reaction_add(payload):
    # Ignore Tinki’s own reactions
    if payload.user_id == bot.user.id:
        return

    channel = bot.get_channel(payload.channel_id)
    if channel is None:
        return

    try:
        message = await channel.fetch_message(payload.message_id)
    except discord.NotFound:
        return

    # 1) 📌 Pin handling
    if str(payload.emoji) == '📌':
        pins_channel = discord.utils.get(message.guild.channels, name='pins', type=discord.ChannelType.text)

        if pins_channel:
            embed = discord.Embed(
                title="Pinned Message",
                description=message.content,
                color=0x00ff00
            )
            embed.add_field(name="Original Author", value=message.author.display_name, inline=False)
            embed.add_field(
                name="Timestamp",
                value=message.created_at.strftime("%Y-%m-%d %H:%M:%S"),
                inline=False
            )

            if message.attachments:
                attachment = message.attachments[0]
                embed.set_image(url=attachment.url)

            embed.add_field(
                name="Link",
                value=f"[Jump to message]({message.jump_url})",
                inline=False
            )
            await pins_channel.send(embed=embed, silent=True)

            await message.add_reaction('✅')

            if payload.member is not None:
                user = payload.member
            else:
                user = await message.guild.fetch_member(payload.user_id)
            await message.remove_reaction(payload.emoji, user)
        else:
            await message.add_reaction('❌')

        return

    # 2) Random AI reaction handling
    if payload.message_id in RANDOM_AI_MESSAGE_IDS:
        user = payload.member or await bot.fetch_user(payload.user_id)
        emoji = str(payload.emoji)

        reply = await generate_reaction_reply(message.content, user.display_name, emoji)
        bot_reply = await channel.send(f"{user.mention} {reply}")

        # Track this new AI message so replies to it are part of the AI thread
        RANDOM_AI_MESSAGE_IDS.add(bot_reply.id)
        return

async def generate_reply_to_random_message(message: discord.Message) -> str:
    client = get_openai_client()

    response = client.chat.completions.create(
        model=OPENAI_MODEL,
        messages=[
            {
                "role": "system",
                "content": (
                    GREMLIN_SYSTEM_STYLE + " "
                    "You are randomly butting into a conversation like an annoying little goblin. "
                    "You read their message and drop in with a roast, sarcastic comment, or chaotic observation. "
                    "1–2 sentences max."
                ),
            },
            {
                "role": "user",
                "content": (
                    f"The user's message was:\n"
                    f"\"{message.content}\"\n\n"
                    f"Write a short gremlin-style roast/snarky reply to this."
                ),
            },
        ],
        max_tokens=60,
        temperature=1.1,
    )

    return response.choices[0].message.content.strip()


@bot.event
async def on_ready():
    load_scores()
    load_conversations()
    load_personas()
    check_reminders.start()
    load_sus_and_sticker_usage()
    load_explode()
    load_spinny()
    await bot.change_presence(activity=discord.Game(name="!commands"))
    bot.loop.create_task(run_startup_tests())
    bot.loop.create_task(random_ai_post_task())


bot.run(TOKEN)
