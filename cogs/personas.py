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

    @commands.command(name='listpersonas')
    async def list_personas(self, ctx):
        if self.personas:
            await ctx.send(f"Available Personas:\n{chr(10).join(self.personas.keys())}")
        else:
            await ctx.send("No personas available.")

    @commands.command(name='erasememory')
    async def erase_memory(self, ctx, number_of_interactions: int = None):
        user_id = str(ctx.author.id)
        if user_id in self.conversations and self.current_persona in self.conversations[user_id]:
            if number_of_interactions is None:
                self.conversations[user_id][self.current_persona] = []
                message = f"All memory of our conversations as '{self.current_persona}' has been erased."
            else:
                n = min(number_of_interactions * 2, len(self.conversations[user_id][self.current_persona]))
                self.conversations[user_id][self.current_persona] = self.conversations[user_id][self.current_persona][:-n]
                message = f"Erased the last {number_of_interactions} interactions."
            self.save_conversations()
            await ctx.send(message)
        else:
            await ctx.send("No conversation history found for you.")


def setup(bot):
    bot.add_cog(Personas(bot))
