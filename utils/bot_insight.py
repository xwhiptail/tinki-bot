from typing import Optional

from config import GITHUB_REPO_URL, OPENAI_MODEL


def maybe_bot_insight_reply(text: str) -> Optional[str]:
    lowered = " ".join(text.lower().strip().split())

    if any(
        phrase in lowered
        for phrase in (
            "what gpt model",
            "which gpt model",
            "what model do you use",
            "which model do you use",
            "what openai model",
            "which openai model",
            "what model are you on",
            "what model are you using",
        )
    ):
        return (
            f"I run on {OPENAI_MODEL}. Math, letter-count, and bot self-knowledge questions go through "
            "deterministic helpers before the model gets a turn."
        )

    if any(
        phrase in lowered
        for phrase in (
            "how do you work",
            "how do you actually work",
            "how are you built",
            "how are you made",
            "how does the bot work",
            "how do you function",
            "what is your architecture",
        )
    ):
        return (
            "I am a Discord bot with a thin entrypoint plus feature cogs for AI, reminders, emotes, bowling, "
            "tracking, admin, URL filtering, utility commands, personas, and Uma. Persistent state lives in "
            "JSON and SQLite under the data directory."
        )

    if any(
        phrase in lowered
        for phrase in (
            "what commands do you have",
            "what commands do you know",
            "what can you do",
            "what features do you have",
            "what are your commands",
        )
    ):
        return (
            "My commands are split across bowling, personas, reminders, emotes, tracking, utility, admin, "
            "Uma, and URL features. Use !commands for the full list or !github for the source."
        )

    if any(
        phrase in lowered
        for phrase in (
            "how are you hosted",
            "where are you hosted",
            "how do you deploy",
            "how are you deployed",
            "where do you run",
            "what server are you on",
        )
    ):
        return (
            "I run on a single EC2 instance under systemd as tinki-bot.service. Code lives in "
            "/opt/apps/tinki-bot/repo, runtime data stays in /opt/apps/tinki-bot/data, and deploys track "
            "the current GitHub commit in .deploy-commit."
        )

    if any(
        phrase in lowered
        for phrase in (
            "where is your github",
            "what is your github",
            "what github repo",
            "source code",
            "repo link",
        )
    ):
        return f"My source repo is {GITHUB_REPO_URL}."

    return None
