import json
from discord.ext import commands

from config import PERSONA_FILE, CONVERSATION_FILE


class Personas(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.personas = {}
        self.current_persona = None
        self.conversations = {}
        self._load_personas()
        self._load_conversations()

    def _load_personas(self):
        try:
            with open(PERSONA_FILE, 'r') as f:
                self.personas = json.load(f)
            if 'cute' in self.personas:
                self.current_persona = 'cute'
        except FileNotFoundError:
            self.personas = {}

    def save_personas(self):
        with open(PERSONA_FILE, 'w') as f:
            json.dump(self.personas, f, ensure_ascii=False, indent=4)

    def _load_conversations(self):
        try:
            with open(CONVERSATION_FILE, 'r') as f:
                self.conversations = json.load(f)
        except FileNotFoundError:
            self.conversations = {}

    def save_conversations(self):
        with open(CONVERSATION_FILE, 'w') as f:
            json.dump(self.conversations, f, ensure_ascii=False, indent=4)

    def update_conversation(self, user_id, persona, user_message, bot_response):
        user_convos = self.conversations.setdefault(str(user_id), {})
        history = user_convos.setdefault(persona, [])
        history.append({'role': 'user', 'content': user_message})
        history.append({'role': 'assistant', 'content': bot_response})
        user_convos[persona] = history[-10:]
        self.save_conversations()


async def setup(bot):
    await bot.add_cog(Personas(bot))
