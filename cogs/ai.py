import asyncio
import random
from typing import Set

import discord
from discord.ext import commands

from config import GREMLIN_SYSTEM_STYLE, OPENAI_MODEL
from utils.openai_helpers import get_openai_client, gpt_wrap_fact
from utils.calculator import maybe_calculate_reply
from utils.letter_counter import maybe_count_letter_reply


class AI(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.random_ai_enabled = False
        self.random_ai_message_ids: Set[int] = set()

    async def cog_load(self):
        self.bot.loop.create_task(self._random_ai_post_task())

    async def _random_ai_post_task(self):
        await self.bot.wait_until_ready()
        channel = discord.utils.get(self.bot.get_all_channels(), name="wat-doggo-only")
        while not self.bot.is_closed():
            wait_minutes = random.randint(60, 180)
            await asyncio.sleep(wait_minutes * 60)
            if self.random_ai_enabled and channel:
                thought = await self._generate_random_thought()
                msg = await channel.send(thought)
                self.random_ai_message_ids.add(msg.id)

    async def _generate_random_thought(self) -> str:
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

    async def _generate_reaction_reply(self, original_text: str, username: str, emoji: str) -> str:
        client = get_openai_client()
        response = client.chat.completions.create(
            model=OPENAI_MODEL,
            messages=[
                {
                    "role": "system",
                    "content": (
                        GREMLIN_SYSTEM_STYLE + " "
                        "You are reacting to someone reacting to your message. "
                        "Make a short roast or snarky remark about their reaction or vibe. 1–2 sentences max."
                    ),
                },
                {
                    "role": "user",
                    "content": (
                        f'Your original message was:\n"{original_text}"\n\n'
                        f"The user '{username}' reacted with '{emoji}'. "
                        f"Write a short, playful roast/snarky reply. Do NOT be wholesome or reassuring."
                    ),
                },
            ],
            max_tokens=60,
            temperature=1.1,
        )
        return response.choices[0].message.content.strip()

    async def _generate_reply_to_reply(self, original_text: str, user: discord.User, user_text: str) -> str:
        client = get_openai_client()
        response = client.chat.completions.create(
            model=OPENAI_MODEL,
            messages=[
                {
                    "role": "system",
                    "content": (
                        GREMLIN_SYSTEM_STYLE + " "
                        "You are replying to someone who replied to your earlier message. "
                        "Make it sound like a gremlin roasting their take. 1–2 sentences. No serious advice."
                    ),
                },
                {
                    "role": "user",
                    "content": (
                        f'Your original message was:\n"{original_text}"\n\n'
                        f"The user '{user.display_name}' replied with:\n\"{user_text}\"\n\n"
                        f"Write a short, playful roast/snarky answer."
                    ),
                },
            ],
            max_tokens=60,
            temperature=1.1,
        )
        return response.choices[0].message.content.strip()

    @commands.Cog.listener()
    async def on_message(self, message):
        if message.author.bot:
            return

        # Random AI thread: reply to replies in tracked AI threads
        if message.reference is not None and not message.content.startswith('!'):
            try:
                replied_to = await message.channel.fetch_message(message.reference.message_id)
            except discord.NotFound:
                replied_to = None
            if replied_to and replied_to.id in self.random_ai_message_ids:
                reply = await self._generate_reply_to_reply(
                    original_text=replied_to.content or "(no text)",
                    user=message.author,
                    user_text=message.content,
                )
                bot_reply = await message.channel.send(f"{message.author.mention} {reply}")
                self.random_ai_message_ids.add(bot_reply.id)
                return

        # Bot mention handler
        if message.reference is None and self.bot.user in message.mentions:
            text = (
                message.content
                .replace(f'<@!{self.bot.user.id}>', '')
                .replace(f'<@{self.bot.user.id}>', '')
                .strip()
            )
            if not text:
                return

            personas_cog = self.bot.cogs.get('Personas')
            current_persona = personas_cog.current_persona if personas_cog else None
            system_prompt = (personas_cog.personas.get(current_persona, []) if personas_cog else [])
            user_id = str(message.author.id)
            persona_key = current_persona or 'default'

            user_convos = (personas_cog.conversations.setdefault(user_id, {}) if personas_cog else {})
            persona_history = user_convos.setdefault(persona_key, [])
            history = " ".join(m["content"] for m in persona_history)

            try:
                letter_fact = maybe_count_letter_reply(text)
                if letter_fact:
                    reply = await gpt_wrap_fact(letter_fact, text, system_prompt)
                    await message.channel.send(f'{message.author.mention} {reply}')
                    if personas_cog:
                        persona_history.append({"role": "user", "content": text})
                        persona_history.append({"role": "assistant", "content": reply})
                        user_convos[persona_key] = persona_history[-20:]
                        personas_cog.save_conversations()
                    return

                calc_fact = maybe_calculate_reply(text)
                if calc_fact:
                    reply = await gpt_wrap_fact(calc_fact, text, system_prompt)
                    await message.channel.send(f'{message.author.mention} {reply}')
                    if personas_cog:
                        persona_history.append({"role": "user", "content": text})
                        persona_history.append({"role": "assistant", "content": reply})
                        user_convos[persona_key] = persona_history[-20:]
                        personas_cog.save_conversations()
                    return

                client = get_openai_client()
                combined_system = (
                    GREMLIN_SYSTEM_STYLE + " "
                    f"Your name is @Tinki-bot. "
                    f"Use this persona description as extra flavor: {system_prompt} "
                    f"Use the past history only as loose context: {history}"
                )
                completion = client.chat.completions.create(
                    model=OPENAI_MODEL,
                    messages=[
                        {"role": "system", "content": combined_system},
                        {"role": "user", "content": text},
                    ]
                )
                bot_response = completion.choices[0].message.content if completion.choices else "No response generated."
                if not bot_response.strip():
                    await message.channel.send(f'{message.author.mention} I am unable to generate a response at the moment.')
                    return

                mention = f'{message.author.mention} '
                limit = 2000
                max_chunk = limit - len(mention) - 30
                if len(bot_response) > limit:
                    chunks = [bot_response[i:i + max_chunk] for i in range(0, len(bot_response), max_chunk)]
                    for i, chunk in enumerate(chunks):
                        part = f" (Part {i+1} of {len(chunks)})" if len(chunks) > 1 else ""
                        await message.channel.send(f'{mention}{chunk}{part}')
                        await asyncio.sleep(1)
                else:
                    await message.channel.send(f'{mention}{bot_response}')

                if personas_cog:
                    persona_history.append({"role": "user", "content": text})
                    persona_history.append({"role": "assistant", "content": bot_response})
                    user_convos[persona_key] = persona_history[-20:]
                    personas_cog.save_conversations()

            except Exception as e:
                await message.channel.send(f'{message.author.mention} Sorry, I encountered an issue: {e}')

    @commands.Cog.listener()
    async def on_raw_reaction_add(self, payload):
        if payload.user_id == self.bot.user.id:
            return
        if payload.message_id not in self.random_ai_message_ids:
            return

        channel = self.bot.get_channel(payload.channel_id)
        if not channel:
            return
        try:
            message = await channel.fetch_message(payload.message_id)
        except discord.NotFound:
            return

        user = payload.member or await self.bot.fetch_user(payload.user_id)
        reply = await self._generate_reaction_reply(message.content, user.display_name, str(payload.emoji))
        bot_reply = await channel.send(f"{user.mention} {reply}")
        self.random_ai_message_ids.add(bot_reply.id)

    @commands.command(name="randomai")
    @commands.has_permissions(administrator=True)
    async def randomai(self, ctx, mode: str = "status"):
        mode = mode.lower()
        if mode in ("on", "enable", "start"):
            self.random_ai_enabled = True
            await ctx.send("🔊 **Random AI posting enabled.** Tinki may speak at any time.")
            await self.bot.change_presence(
                status=discord.Status.do_not_disturb,
                activity=discord.Game(name="Generating thoughts...")
            )
            thought = await self._generate_random_thought()
            msg = await ctx.channel.send(thought)
            self.random_ai_message_ids.add(msg.id)
        elif mode in ("off", "disable", "stop"):
            self.random_ai_enabled = False
            await ctx.send("🔇 **Random AI posting disabled.** Tinki will stay silent unless invoked.")
            await self.bot.change_presence(
                status=discord.Status.online,
                activity=discord.Game(name="Ready to help!")
            )
        else:
            status = "ON" if self.random_ai_enabled else "OFF"
            emoji = "🟢" if self.random_ai_enabled else "🔴"
            await ctx.send(f"{emoji} **Random AI posting is currently {status}.**")


async def setup(bot):
    await bot.add_cog(AI(bot))
