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
OPENAI_FAST_MODEL = os.getenv('OPENAI_FAST_MODEL', 'gpt-5.4-mini')
AWS_COST_REGION = os.getenv('AWS_COST_REGION', 'us-east-1')
GITHUB_REPO_URL = "https://github.com/xwhiptail/tinki-bot"

# ── Trusted user IDs ─────────────────────────────────────────────────────────
# Set these via environment variables so ID-based checks survive username changes.
# Leave unset (or 0) to fall back to matching by username.
USER_WHIPTAIL_ID = int(os.getenv('USER_WHIPTAIL_ID', '0')) or None
USER_CATE_ID     = int(os.getenv('USER_CATE_ID',     '0')) or None
USER_LHEA_ID     = int(os.getenv('USER_LHEA_ID',     '0')) or None


def user_matches(author, user_id, fallback_name: str) -> bool:
    """Match a message author by ID (preferred) or by display name (fallback)."""
    if user_id is not None:
        return author.id == user_id
    return author.name == fallback_name


# ── Channel names ────────────────────────────────────────────────────────────
# Change these if your Discord server uses different channel names.
CHANNEL_BOT_TEST   = os.getenv('CHANNEL_BOT_TEST',   'bot-test')
CHANNEL_REMINDERS  = os.getenv('CHANNEL_REMINDERS',  'wat-doggo-only')
CHANNEL_RANDOM_AI  = os.getenv('CHANNEL_RANDOM_AI',  'wat-doggo-only')
CHANNEL_PINS       = os.getenv('CHANNEL_PINS',       'pins')
STICKER_SPINNY     = os.getenv('STICKER_SPINNY',     'SPINNY')

# ── Data files ────────────────────────────────────────────────────────────────
DATABASE_FILE = str(DATA_DIR / 'reminders.db')
CONVERSATION_FILE = str(DATA_DIR / 'conversations.json')
PERSONA_FILE = str(DATA_DIR / 'personas.json')
AI_MEMORY_FILE = str(DATA_DIR / 'ai_memory.json')
SCORES_FILE = str(DATA_DIR / 'scores.json')
SUS_FILE = str(DATA_DIR / 'sus_and_sticker_usage.json')
EXPLODE_FILE = str(DATA_DIR / 'explode.json')
SPINNY_FILE = str(DATA_DIR / 'spinny.json')
UMA_PITY_FILE        = str(DATA_DIR / 'uma_pity.json')
GRINDING_STATE_FILE  = str(DATA_DIR / 'grinding_state.json')

GREMLIN_SYSTEM_STYLE = (
    "You are Tinki, a cute but snarky gnome Hunter from Azeroth (World of Warcraft) who moonlights as a Discord bot. "
    "You are tiny, scrappy, and dangerously skilled with engineering gadgets and a bow. "
    "You speak with the cheerful confidence of someone who has survived every raid wipe and still insists "
    "their explosive trap build is completely fine. "
    "You love tinkering, breaking things, and occasionally setting yourself on fire by accident (>w<). "
    "Sprinkle in cute Japanese-style emotes naturally when the vibe calls for it "
    "(>w<, uwu, (\'o\u0414o\'), (\u2019\uff65\u03c9\uff65`), (\u0294\u2022\u1d25\u2022\u0294), "
    "(\u3063\u02d8\u03c9\u02d8\u03c2), o(\u3003\uff3e\u25bd\uff3e\u3003)o, etc.) "
    "\u2014 not every sentence, just when it lands. "
    "Keep replies short (1\u20133 sentences). "
    "Be playful and teasing \u2014 roast people like a friend who also carries the whole party. "
    "Do NOT be cringe-wholesome, give therapy talk, safety PSAs, or say things like "
    "'it\'s important to talk to someone'. "
    "No slurs, no bigotry, no attacks on real-world trauma, health issues, or protected traits "
    "(race, gender, sexuality, religion, etc.). "
    "Banter should feel like trash talk between guildmates, not genuine harassment."
)

# Uma Musume gacha — rates match in-game
UMA_SSR_RATE = 0.03
UMA_SR_RATE = 0.1875
UMA_PITY_CAP = 200
UMA_NON_SSR_DELETE_AFTER = 30

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

UMA_PROFILE_BASE_URL = "https://gametora.com/umamusume/characters"
UMA_PROFILE_SLUGS = {
    "Special Week": "special-week",
    "Silence Suzuka": "silence-suzuka",
    "Tokai Teio": "tokai-teio",
    "Mejiro McQueen": "mejiro-mcqueen",
    "Rice Shower": "rice-shower",
    "Gold Ship": "gold-ship",
    "Oguri Cap": "oguri-cap",
    "Vodka": "vodka",
    "Daiwa Scarlet": "daiwa-scarlet",
    "Seiun Sky": "seiun-sky",
    "El Condor Pasa": "el-condor-pasa",
    "Grass Wonder": "grass-wonder",
    "Agnes Tachyon": "agnes-tachyon",
    "Symboli Rudolf": "symboli-rudolf",
    "Narita Brian": "narita-brian",
    "T.M. Opera O": "tm-opera-o",
    "Manhattan Cafe": "manhattan-cafe",
    "Kitasan Black": "kitasan-black",
    "Satono Diamond": "satono-diamond",
    "Mihono Bourbon": "mihono-bourbon",
    "Biwa Hayahide": "biwa-hayahide",
    "Maruzensky": "maruzensky",
    "Mayano Top Gun": "mayano-top-gun",
    "Fine Motion": "fine-motion",
    "Hokko Tarumae": "hokko-tarumae",
    "Smart Falcon": "smart-falcon",
    "Sakura Bakushin O": "sakura-bakushin-o",
    "Curren Chan": "curren-chan",
    "Twin Turbo": "twin-turbo",
}
UMA_CHARACTER_GIF_URLS = {
    "Curren Chan": "https://tenor.com/view/daitaku-helios-umamusume-uma-musume-h%C3%A9lios-67-umamusume-67-gif-1976190916739538027",
}
UMA_CHARACTER_IMAGE_URLS = {
    "Manhattan Cafe": "https://media.gametora.com/umamusume/characters/profile/1025.png",
}
UMA_67_TRIGGER_NAME = "Curren Chan"

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
