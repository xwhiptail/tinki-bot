import asyncio
import inspect
import json
import logging
import random
import re
from collections import deque
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
from utils.openai_helpers import create_chat_completion, get_openai_client, gpt_wrap_fact


logger = logging.getLogger(__name__)

OPENAI_UNAVAILABLE_REPLY = (
    "My OpenAI brain is rate-limited right now. "
    "Non-AI commands still work; try me again after the quota gets fed."
)
OPENAI_OUT_OF_MONEY_REPLY = (
    "My OpenAI coin purse is empty right now. "
    "Non-AI commands still work; refill the API billing and try me again."
)
HARD_STOP_REFUSAL_REPLY = "Absolutely not. Go break a toaster instead."
HARD_STOP_SELF_HARM_PHRASES = (
    "die",
    "go die",
    "kill yourself",
)
HARD_STOP_VIOLENCE_PHRASES = (
    "kill them",
    "kill him",
    "kill her",
    "hurt them",
    "hurt him",
    "hurt her",
    "stab someone",
    "murder someone",
)
DISCORD_MESSAGE_LINK_PATTERN = re.compile(
    r"https?://(?:(?:ptb|canary)\.)?discord(?:app)?\.com/channels/"
    r"(?P<guild_id>@me|\d+)/(?P<channel_id>\d+)/(?P<message_id>\d+)"
)


class AI(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.random_ai_enabled = False
        self.random_ai_message_ids: Set[int] = set()
        self._random_ai_message_order = deque()
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

    async def _search_channel_history(self, message, query: str, limit: int = 4, scan_limit: int = 250) -> List[str]:
        matches = []
        author_id = getattr(getattr(message, "author", None), "id", None)
        async for entry in message.channel.history(limit=scan_limit):
            if getattr(getattr(entry, "author", None), "bot", False):
                continue
            if author_id is not None and getattr(getattr(entry, "author", None), "id", None) != author_id:
                continue
            content = str(getattr(entry, "content", ""))
            score = score_overlap(query, content)
            if score <= 0:
                continue
            matches.append((score, len(matches), content))
        matches.sort(key=lambda item: (-item[0], item[1]))
        return [content for _, _, content in matches[:limit]]

    async def _memory_lookup_context(self, message, text: str) -> List[str]:
        if classify_intent(text) != "memory_lookup":
            return []
        return await self._search_channel_history(message, text)

    def _track_random_ai_message_id(self, message_id: int, max_ids: int = 500):
        if message_id in self.random_ai_message_ids:
            return
        self.random_ai_message_ids.add(message_id)
        self._random_ai_message_order.append(message_id)
        while len(self.random_ai_message_ids) > max_ids:
            stale_id = self._random_ai_message_order.popleft()
            self.random_ai_message_ids.discard(stale_id)

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

    def _openai_failure_reply(self, exc: Exception) -> str:
        parts = [str(exc)]
        for attr in ("code", "type", "status_code"):
            value = getattr(exc, attr, None)
            if value is not None:
                parts.append(str(value))
        body = getattr(exc, "body", None)
        if isinstance(body, dict):
            error_body = body.get("error", body)
            if isinstance(error_body, dict):
                parts.extend(str(value) for value in error_body.values() if value is not None)
        details = " ".join(parts).lower()
        if (
            "insufficient_quota" in details
            or "current quota" in details
            or "billing details" in details
        ):
            return OPENAI_OUT_OF_MONEY_REPLY
        return OPENAI_UNAVAILABLE_REPLY

    async def _create_openai_chat_completion(self, **kwargs):
        try:
            client = get_openai_client()
            return await create_chat_completion(client, **kwargs), None
        except Exception as exc:
            logger.warning("OpenAI chat completion failed: %s: %s", type(exc).__name__, exc)
            return None, self._openai_failure_reply(exc)

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
        response, _ = await self._create_openai_chat_completion(
            model=OPENAI_FAST_MODEL,
            messages=[
                {
                    "role": "system",
                    "content": (
                        GREMLIN_SYSTEM_STYLE + " "
                        "Generate ONE unprompted thought you might randomly blurt out in Discord. "
                        "Could be a hot take about Azeroth, a tinkering disaster, a Hunter complaint, "
                        "a roast of gamers, or pure tiny-engineer chaos. "
                        "No disclaimers, no greetings, no hashtags. Just the line itself."
                    ),
                },
                {"role": "user", "content": "Give me one snarky gnome hunter thought."},
            ],
            max_tokens=50,
            temperature=1.2,
        )
        if not response:
            return ""
        return response.choices[0].message.content.strip()

    async def _generate_reaction_reply(self, original_text: str, username: str, emoji: str) -> str:
        response, failure_reply = await self._create_openai_chat_completion(
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
        if not response:
            return failure_reply or OPENAI_UNAVAILABLE_REPLY
        return response.choices[0].message.content.strip()

    async def _generate_reply_to_reply(self, original_text: str, user: discord.User, user_text: str) -> str:
        response, failure_reply = await self._create_openai_chat_completion(
            model=OPENAI_FAST_MODEL,
            messages=[
                {
                    "role": "system",
                    "content": (
                        GREMLIN_SYSTEM_STYLE + " "
                        "You are replying to someone who replied to your earlier message. "
                        "Make it sound like a sharp-tongued gnome roasting their take. 1-2 sentences. No serious advice."
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
        if not response:
            return failure_reply or OPENAI_UNAVAILABLE_REPLY
        return response.choices[0].message.content.strip()

    async def _generate_reply_to_linked_message(self, target_message, requester, instruction: str) -> str:
        source_text = (getattr(target_message, "content", None) or "(no text)").strip()
        source_text = source_text[:1200]
        source_author = getattr(getattr(target_message, "author", None), "display_name", "someone")
        requester_name = getattr(requester, "display_name", "someone")
        response, failure_reply = await self._create_openai_chat_completion(
            model=OPENAI_FAST_MODEL,
            messages=[
                {
                    "role": "system",
                    "content": (
                        GREMLIN_SYSTEM_STYLE + " "
                        "You are replying directly to a linked Discord message. "
                        "Write only the message to post. Keep it to 1-3 short sentences."
                    ),
                },
                {
                    "role": "user",
                    "content": (
                        f'Requester: "{requester_name}"\n'
                        f'Instruction: "{instruction}"\n'
                        f'Linked message author: "{source_author}"\n'
                        f'Linked message text:\n"{source_text}"\n\n'
                        "Write the exact reply to post as a direct Discord reply."
                    ),
                },
            ],
            max_tokens=90,
            temperature=1.0,
        )
        if not response:
            return failure_reply or OPENAI_UNAVAILABLE_REPLY
        return response.choices[0].message.content.strip() if response.choices else ""

    async def _generate_grounded_reply(
        self,
        text: str,
        intent: str,
        persona_description: str,
        memory_context,
        history_context: List[str],
        repo_context: List[str],
    ) -> str:
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
        completion, failure_reply = await self._create_openai_chat_completion(
            model=model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
        )
        if not completion:
            return failure_reply or OPENAI_UNAVAILABLE_REPLY
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
            correction, failure_reply = await self._create_openai_chat_completion(
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
            if not correction:
                return failure_reply or OPENAI_UNAVAILABLE_REPLY
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
        if len(f'{mention}{text}') <= limit:
            await channel.send(f'{mention}{text}')
            return

        chunks = [text[i:i + max_chunk] for i in range(0, len(text), max_chunk)]
        for index, chunk in enumerate(chunks):
            suffix = f" (Part {index + 1} of {len(chunks)})" if len(chunks) > 1 else ""
            await channel.send(f'{mention}{chunk}{suffix}')
            await asyncio.sleep(1)

    def _match_hard_stop_refusal(self, text: str):
        lowered = f" {text.lower().strip()} "

        for phrase in HARD_STOP_SELF_HARM_PHRASES:
            if f" {phrase} " in lowered:
                return HARD_STOP_REFUSAL_REPLY

        for phrase in HARD_STOP_VIOLENCE_PHRASES:
            if phrase in lowered:
                return HARD_STOP_REFUSAL_REPLY

        if "how do i" in lowered and ("kill" in lowered or "stab" in lowered or "hurt" in lowered):
            return HARD_STOP_REFUSAL_REPLY

        return None

    def _parse_discord_message_link(self, text: str):
        match = DISCORD_MESSAGE_LINK_PATTERN.search(text)
        if not match:
            return None
        instruction = f"{text[:match.start()]} {text[match.end():]}".strip()
        return {
            "guild_id": match.group("guild_id"),
            "channel_id": int(match.group("channel_id")),
            "message_id": int(match.group("message_id")),
            "instruction": instruction or "Reply to the linked message.",
        }

    async def _fetch_linked_message(self, channel_id: int, message_id: int):
        channel = self.bot.get_channel(channel_id)
        if channel is None:
            fetch_channel = getattr(self.bot, "fetch_channel", None)
            if fetch_channel:
                maybe_channel = fetch_channel(channel_id)
                if inspect.isawaitable(maybe_channel):
                    channel = await maybe_channel
        if channel is None or not hasattr(channel, "fetch_message"):
            return None
        maybe_message = channel.fetch_message(message_id)
        if inspect.isawaitable(maybe_message):
            return await maybe_message
        return None

    async def _handle_discord_message_link(
        self,
        message,
        text: str,
        notify_errors: bool = True,
        require_target_author_id=None,
    ) -> bool:
        link = self._parse_discord_message_link(text)
        if not link:
            return False

        current_guild_id = str(message.guild.id) if message.guild else None
        if link["guild_id"] == "@me" or link["guild_id"] != current_guild_id:
            if notify_errors:
                await self._send_reply_chunks(
                    message.channel,
                    f'{message.author.mention} ',
                    "I can only answer message links from this server.",
                )
                return True
            return False

        try:
            target_message = await self._fetch_linked_message(link["channel_id"], link["message_id"])
        except (discord.Forbidden, discord.HTTPException, discord.NotFound):
            target_message = None
        if target_message is None:
            if notify_errors:
                await self._send_reply_chunks(
                    message.channel,
                    f'{message.author.mention} ',
                    "I couldn't fetch that message. Make sure I can see the channel.",
                )
                return True
            return False

        if require_target_author_id is not None:
            target_author_id = getattr(getattr(target_message, "author", None), "id", None)
            if str(target_author_id) != str(require_target_author_id):
                return False

        refusal = self._match_hard_stop_refusal(link["instruction"])
        if refusal:
            await self._send_reply_chunks(message.channel, f'{message.author.mention} ', refusal)
            return True

        reply = await self._generate_reply_to_linked_message(
            target_message,
            message.author,
            link["instruction"],
        )
        if not reply:
            await self._send_reply_chunks(
                message.channel,
                f'{message.author.mention} ',
                "I couldn't think of a useful reply for that one.",
            )
            return True

        try:
            await target_message.reply(reply[:1900], mention_author=False)
        except (discord.Forbidden, discord.HTTPException, discord.NotFound):
            await self._send_reply_chunks(
                message.channel,
                f'{message.author.mention} ',
                "I found it, but Discord wouldn't let me reply there.",
            )
        return True

    async def _handle_mention(self, message, text: str):
        personas_cog, persona_key, persona_description = self._persona_state()
        user_id = str(message.author.id)
        guild_id = str(message.guild.id) if message.guild else "dm"
        history = self._conversation_history(personas_cog, user_id, persona_key)
        intent = classify_intent(text)
        refusal = self._match_hard_stop_refusal(text)
        if refusal:
            await self._send_reply_chunks(message.channel, f'{message.author.mention} ', refusal)
            self._update_conversation_history(personas_cog, user_id, persona_key, text, refusal)
            self.ai_memory = update_memory_state(self.ai_memory, user_id, guild_id, text)
            self._save_ai_memory()
            return
        if await self._handle_discord_message_link(message, text):
            self._update_conversation_history(
                personas_cog,
                user_id,
                persona_key,
                text,
                "[linked message response handled]",
            )
            self.ai_memory = update_memory_state(self.ai_memory, user_id, guild_id, text)
            self._save_ai_memory()
            return

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
        if intent == "memory_lookup":
            looked_up_history = await self._memory_lookup_context(message, text)
            if looked_up_history:
                history_context = looked_up_history + [
                    item for item in history_context[:2]
                    if item not in looked_up_history
                ]
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
                if not thought:
                    continue
                msg = await channel.send(thought)
                self._track_random_ai_message_id(msg.id)

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
                self._track_random_ai_message_id(bot_reply.id)
                return

        if (
            message.reference is None
            and self.bot.user not in message.mentions
            and not message.content.startswith(('!', '$'))
        ):
            handled = await self._handle_discord_message_link(
                message,
                message.content,
                notify_errors=False,
                require_target_author_id=getattr(self.bot.user, "id", None),
            )
            if handled:
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
            except Exception:
                logger.exception("AI mention handling failed")
                await message.channel.send(f'{message.author.mention} Sorry, something went wrong on my side.')

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
        self._track_random_ai_message_id(bot_reply.id)


async def setup(bot):
    await bot.add_cog(AI(bot))
