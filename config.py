import logging
import os
import re
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = Path(os.getenv('TINKI_DATA_DIR', BASE_DIR / 'data'))
DATA_DIR.mkdir(parents=True, exist_ok=True)

logging.basicConfig(level=logging.INFO, format='%(asctime)s:%(levelname)s:%(message)s')

TOKEN = os.getenv('DISCORD')
GIPHY_API_KEY = os.getenv('GIPHY')
OPENAI_MODEL = os.getenv('OPENAI_MODEL', 'gpt-5.4')
GITHUB_REPO_URL = "https://github.com/xwhiptail/tinki-bot"

DATABASE_FILE = str(DATA_DIR / 'reminders.db')
CONVERSATION_FILE = str(DATA_DIR / 'conversations.json')
PERSONA_FILE = str(DATA_DIR / 'personas.json')
SCORES_FILE = str(DATA_DIR / 'scores.json')
SUS_FILE = str(DATA_DIR / 'sus_and_sticker_usage.json')
EXPLODE_FILE = str(DATA_DIR / 'explode.json')
SPINNY_FILE = str(DATA_DIR / 'spinny.json')
UMA_PITY_FILE = str(DATA_DIR / 'uma_pity.json')

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

# Uma Musume gacha — rates match in-game
UMA_SSR_RATE = 0.03
UMA_SR_RATE = 0.1875
UMA_PITY_CAP = 200

UMA_SSR = [
    "Special Week", "Silence Suzuka", "Tokai Teio", "Mejiro McQueen",
    "Rice Shower", "Gold Ship", "Oguri Cap", "Vodka", "Daiwa Scarlet",
    "Seiun Sky", "El Condor Pasa", "Grass Wonder", "Agnes Tachyon",
    "Symboli Rudolf", "Narita Brian", "T.M. Opera O", "Manhattan Cafe",
    "Kitasan Black", "Satono Diamond", "Mihono Bourbon", "Biwa Hayahide",
    "Maruzensky", "Mayano Top Gun", "Fine Motion", "Hokko Tarumae",
    "Smart Falcon", "Sakura Bakushin O", "Curren Chan", "Twin Turbo",
]
UMA_SR = [
    "Nice Nature", "Winning Ticket", "Air Groove", "Super Creek",
    "Meisho Doto", "Narita Top Road", "Taiki Shuttle", "Eishin Flash",
    "Copano Rickey", "Ikuno Dictus", "Nishino Flower", "Haru Urara",
    "Bamboo Memory", "Agnes Digital", "Sakura Chiyono O", "Sweep Tosho",
]
UMA_R = [
    "Mejiro Dober", "Daiichi Ruby", "Mejiro Ardan", "Matikanefukukitaru",
    "Shinko Windy", "Marvelous Sunday", "Biko Pegasus", "Yamanin Zephyr",
]

SCORE_PATTERN = re.compile(r'^(?:[6-9][0-9]|1[0-9]{2}|200)$')

# URL patterns used by the URL filter and rewriter
X_COM_PATTERN = re.compile(r'https?://x\.com')
TWITTER_COM_PATTERN = re.compile(r'https?://(www\.)?twitter\.com/(\w+)/(\w+)')
INSTAGRAM_COM_PATTERN = re.compile(r'https?://(www\.)?instagram\.com')
TIKTOK_COM_PATTERN = re.compile(r'https?://(www\.)?tiktok\.com')
REDDIT_COM_PATTERN = re.compile(r'https?://(www\.)?reddit\.com')
TWITCH_CLIP_PATTERN = re.compile(r'(https?://(?:www\.)?(?:clips\.)?twitch\.tv/[\w-]+/clip/[\w-]+)')

SERVER_FEATURE_REMOVED_MESSAGE = (
    "Minecraft and SkyFactory server controls have been retired. "
    "These commands are placeholders and no longer manage any live servers."
)
