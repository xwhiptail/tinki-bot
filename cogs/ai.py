import asyncio
import json
import random
from pathlib import Path
from typing import List, Set

import discord
from discord.ext import commands

from config import AI_MEMORY_FILE, CHANNEL_RANDOM_AI, GREMLIN_SYSTEM_STYLE, OPENAI_FAST_MODEL, OPENAI_MODEL
from utils.ai_brain import (
    build_memory_context,
    build_system_prompt,
    classify_intent,
    extract_keywords,
    load_repo_documents,
    parse_natural_command,
    retrieve_repo_context,
    score_overlap,
    update_memory_state,
    validate_grounded_reply,
)
from utils.bot_insight import maybe_bot_insight_reply
from utils.calculator import maybe_calculate_reply
from utils.letter_counter import maybe_count_letter_reply
from utils.openai_helpers import get_openai_client, gpt_wrap_fact


class AI(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.random_ai_enabled = False
        self.random_ai_message_ids: Set[int] = set()
        self._ai_task_started = False
        self.memory_file = Path(AI_MEMORY_FILE)
        self.ai_memory = self._load_ai_memory()
        self.repo_documents = load_repo_documents(Path(__file__).resolve().parent.parent)

    def _load_ai_memory(self):
        try:
            with self.memory_file.open('r', encoding='utf-8') as handle:
                loaded = json.load(handle)
                return {
                    "users": loaded.get("users", {}),
                    "guilds": loaded.get("guilds", {}),
                }
        except FileNotFoundError:
            return {"users": {}, "guilds": {}}
        except json.JSONDecodeError:
            return {"users": {}, "guilds": {}}

    def _save_ai_memory(self):
        with self.memory_file.open('w', encoding='utf-8') as handle:
            json.dump(self.ai_memory, handle, ensure_ascii=False, indent=2)

    def _persona_state(self):
        personas_cog = self.bot.cogs.get('Personas')
        current_persona = personas_cog.current_persona if personas_cog else None
        persona_description = personas_cog.personas.get(current_persona, "") if personas_cog else ""
        persona_key = current_persona or 'default'
        return personas_cog, persona_key, persona_description

    def _conversation_history(self, personas_cog, user_id: str, persona_key: str):
        if not personas_cog:
            return []
        user_convos = personas_cog.conversations.setdefault(user_id, {})
        return user_convos.setdefault(persona_key, [])

    def _update_conversation_history(self, personas_cog, user_id: str, persona_key: str, user_text: str, bot_text: str):
        if not personas_cog:
            return
        user_convos = personas_cog.conversations.setdefault(user_id, {})
        history = user_convos.setdefault(persona_key, [])
        history.append({"role": "user", "content": user_text})
        history.append({"role": "assistant", "content": bot_text})
        user_convos[persona_key] = history[-20:]
        personas_cog.save_conversations()

    def _relevant_history(self, history, query: str, limit: int = 6) -> List[str]:
        ranked = []
        for index, entry in enumerate(history):
            content = str(entry.get("content", ""))
            score = score_overlap(query, content)
            ranked.append((score, index, content))
        ranked.sort(key=lambda item: (-item[0], -item[1]))
        chosen = [content for score, _, content in ranked[:limit] if score > 0]
        if chosen:
            return list(reversed(chosen))
        fallback = [str(entry.get("content", "")) for entry in history[-limit:]]
        return [item for item in fallback if item]

    def _command_context(self, query: str) -> List[str]:
        commands_available = sorted(f"!{command.name}" for command in self.bot.commands if command.enabled)
        lowered = query.lower()
        if "what commands" in lowered or "!commands" in lowered or "what can you do" in lowered:
            return ["Known commands: " + ", ".join(commands_available)]

        keywords = extract_keywords(query)
        matches = [
            command for command in commands_available
            if any(keyword in command.lower() for keyword in keywords)
        ]
        if matches:
            return ["Commands that match the question: " + ", ".join(matches[:12])]
        return []

    def _fallback_grounded_reply(self, intent: str, repo_context: List[str]) -> str:
        if repo_context:
            first_block = repo_context[0].splitlines()
            summary = " ".join(first_block[:3]).strip()
            return summary[:350]
        if intent in {"command_help", "bot_repo", "question_answer"}:
            return "I do not have enough grounded repo context for that one. Use !commands or !github if you want the source of truth."
        return "I do not have a solid answer for that one right now."

    def _select_reply_model(self, intent: str, text: str, repo_context: List[str], history_context: List[str]) -> str:
        if intent == "bot_repo":
            return OPENAI_MODEL
        if len(text) > 350 or len(repo_context) > 2 or len(history_context) > 4:
            return OPENAI_MODEL
        return OPENAI_FAST_MODEL

    async def _execute_natural_command(self, message, command_spec) -> bool:
        command_name = command_spec["command"]
        args = command_spec.get("args")
        original_content = message.content
        synthetic = f"!{command_name}"
        if args:
            synthetic = f"{synthetic} {args}"

        try:
            message.content = synthetic
            await self.bot.process_commands(message)
            return True
        finally:
            message.content = original_content

    async def _generate_random_thought(self) -> str:
        client = get_openai_client()
        response = client.chat.completions.create(
            model=OPENAI_FAST_MODEL,
            messages=[
                {
                    "role": "system",
                    "content": (
                        GREMLIN_SYSTEM_STYLE + " "
                        "Generate ONE unprompted thought you might randomly blurt out in Discord. "
                        "Could be a hot take about Azeroth, a tinkering disaster, a Hunter complaint, "
                        "a roast of gamers, or pure chaotic gnome energy. "
                        "No disclaimers, no greetings, no hashtags. Just the line itself."
                    ),
                },
                {"role": "user", "content": "Give me one gnome hunter thought."},
            ],
            max_tokens=50,
            temperature=1.2,
        )
        return response.choices[0].message.content.strip()

    async def _generate_reaction_reply(self, original_text: str, username: str, emoji: str) -> str:
        client = get_openai_client()
        response = client.chat.completions.create(
            model=OPENAI_FAST_MODEL,
            messages=[
                {
                    "role": "system",
                    "content": (
                        GREMLIN_SYSTEM_STYLE + " "
                        "You are reacting to someone reacting to your message. "
                        "Make a short roast or snarky remark about their reaction or vibe. 1-2 sentences max."
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
            model=OPENAI_FAST_MODEL,
            messages=[
                {
                    "role": "system",
                    "content": (
                        GREMLIN_SYSTEM_STYLE + " "
                        "You are replying to someone who replied to your earlier message. "
                        "Make it sound like a feral gnome roasting their take. 1-2 sentences. No serious advice."
                    ),
                },
                {
                    "role": "user",
                    "content": (
                        f'Your original message was:\n"{original_text}"\n\n'
                        f'The user "{user.display_name}" replied with:\n"{user_text}"\n\n'
                        "Write a short, playful roast/snarky answer."
                    ),
                },
            ],
            max_tokens=60,
            temperature=1.1,
        )
        return response.choices[0].message.content.strip()

    async def _generate_grounded_reply(
        self,
        text: str,
        intent: str,
        persona_description: str,
        memory_context,
        history_context: List[str],
        repo_context: List[str],
    ) -> str:
        client = get_openai_client()
        model = self._select_reply_model(intent, text, repo_context, history_context)
        system_prompt = build_system_prompt(
            GREMLIN_SYSTEM_STYLE,
            persona_description,
            intent,
            memory_context,
            repo_context,
        )
        user_prompt = (
            f"User message:\n{text}\n\n"
            f"Recent relevant history:\n{chr(10).join(history_context) if history_context else '(none)'}\n\n"
            "Instructions:\n"
            "- Answer in 1-3 short sentences.\n"
            "- If repo or command context is provided, only use that factual context.\n"
            "- If the context is insufficient, say so briefly instead of guessing.\n"
        )
        completion = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
        )
        reply = completion.choices[0].message.content.strip() if completion.choices else ""
        valid, reason = validate_grounded_reply(
            reply,
            [command.name for command in self.bot.commands],
            intent,
            repo_context,
        )
        if valid:
            return reply

        if repo_context:
            correction = client.chat.completions.create(
                model=OPENAI_MODEL,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {
                        "role": "user",
                        "content": (
                            user_prompt +
                            f"\nPrevious draft failed validation: {reason}.\n"
                            "Rewrite it so it only uses grounded repo facts and known commands."
                        ),
                    },
                ],
            )
            corrected = correction.choices[0].message.content.strip() if correction.choices else ""
            valid, _ = validate_grounded_reply(
                corrected,
                [command.name for command in self.bot.commands],
                intent,
                repo_context,
            )
            if valid:
                return corrected

        return self._fallback_grounded_reply(intent, repo_context)

    async def _send_reply_chunks(self, channel, mention: str, text: str):
        limit = 2000
        max_chunk = limit - len(mention) - 30
        if len(text) <= limit:
            await channel.send(f'{mention}{text}')
            return

        chunks = [text[i:i + max_chunk] for i in range(0, len(text), max_chunk)]
        for index, chunk in enumerate(chunks):
            suffix = f" (Part {index + 1} of {len(chunks)})" if len(chunks) > 1 else ""
            await channel.send(f'{mention}{chunk}{suffix}')
            await asyncio.sleep(1)

    async def _handle_mention(self, message, text: str):
        personas_cog, persona_key, persona_description = self._persona_state()
        user_id = str(message.author.id)
        guild_id = str(message.guild.id) if message.guild else "dm"
        history = self._conversation_history(personas_cog, user_id, persona_key)
        intent = classify_intent(text)
        command_spec = parse_natural_command(text)
        if command_spec:
            executed = await self._execute_natural_command(message, command_spec)
            if executed:
                self._update_conversation_history(
                    personas_cog,
                    user_id,
                    persona_key,
                    text,
                    f"[natural command executed: !{command_spec['command']}]",
                )
                self.ai_memory = update_memory_state(self.ai_memory, user_id, guild_id, text)
                self._save_ai_memory()
                return

        deterministic_fact = maybe_count_letter_reply(text)
        if deterministic_fact:
            reply = await gpt_wrap_fact(deterministic_fact, text, persona_description, model=OPENAI_FAST_MODEL)
            await self._send_reply_chunks(message.channel, f'{message.author.mention} ', reply)
            self._update_conversation_history(personas_cog, user_id, persona_key, text, reply)
            self.ai_memory = update_memory_state(self.ai_memory, user_id, guild_id, text)
            self._save_ai_memory()
            return

        deterministic_fact = maybe_calculate_reply(text)
        if deterministic_fact:
            reply = await gpt_wrap_fact(deterministic_fact, text, persona_description, model=OPENAI_FAST_MODEL)
            await self._send_reply_chunks(message.channel, f'{message.author.mention} ', reply)
            self._update_conversation_history(personas_cog, user_id, persona_key, text, reply)
            self.ai_memory = update_memory_state(self.ai_memory, user_id, guild_id, text)
            self._save_ai_memory()
            return

        deterministic_fact = maybe_bot_insight_reply(text)
        if deterministic_fact:
            reply = await gpt_wrap_fact(deterministic_fact, text, persona_description, model=OPENAI_FAST_MODEL)
            await self._send_reply_chunks(message.channel, f'{message.author.mention} ', reply)
            self._update_conversation_history(personas_cog, user_id, persona_key, text, reply)
            self.ai_memory = update_memory_state(self.ai_memory, user_id, guild_id, text)
            self._save_ai_memory()
            return

        memory_context = build_memory_context(self.ai_memory, user_id, guild_id, text)
        history_context = self._relevant_history(history, text)
        repo_context = []
        if intent in {"command_help", "bot_repo", "question_answer"}:
            repo_context = self._command_context(text) + retrieve_repo_context(text, self.repo_documents)

        reply = await self._generate_grounded_reply(
            text,
            intent,
            persona_description,
            memory_context,
            history_context,
            repo_context,
        )
        await self._send_reply_chunks(message.channel, f'{message.author.mention} ', reply)

        self._update_conversation_history(personas_cog, user_id, persona_key, text, reply)
        self.ai_memory = update_memory_state(self.ai_memory, user_id, guild_id, text)
        self._save_ai_memory()

    @commands.Cog.listener()
    async def on_ready(self):
        if not self._ai_task_started:
            self._ai_task_started = True
            asyncio.create_task(self._random_ai_post_task())

    async def _random_ai_post_task(self):
        await self.bot.wait_until_ready()
        channel = discord.utils.get(self.bot.get_all_channels(), name=CHANNEL_RANDOM_AI)
        while not self.bot.is_closed():
            wait_minutes = random.randint(60, 180)
            await asyncio.sleep(wait_minutes * 60)
            if self.random_ai_enabled and channel:
                thought = await self._generate_random_thought()
                msg = await channel.send(thought)
                self.random_ai_message_ids.add(msg.id)

    @commands.Cog.listener()
    async def on_message(self, message):
        if message.author.bot:
            return

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

        if message.reference is None and self.bot.user in message.mentions:
            text = (
                message.content
                .replace(f'<@!{self.bot.user.id}>', '')
                .replace(f'<@{self.bot.user.id}>', '')
                .strip()
            )
            if not text:
                return
            text = text[:1000]  # hard cap — prevents novel-pasting from blowing up token budget
            try:
                await self._handle_mention(message, text)
            except Exception as error:
                await message.channel.send(f'{message.author.mention} Sorry, I encountered an issue: {error}')

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


async def setup(bot):
    await bot.add_cog(AI(bot))
