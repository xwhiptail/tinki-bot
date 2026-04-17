import re
from collections import Counter
from pathlib import Path
from typing import Dict, Iterable, List, Sequence, Tuple


STOPWORDS = {
    "a", "about", "an", "and", "are", "as", "at", "be", "bot", "can", "do", "for",
    "from", "get", "give", "help", "how", "i", "in", "is", "it", "me", "my", "of",
    "on", "or", "please", "reply", "server", "tell", "that", "the", "this", "to",
    "use", "what", "when", "where", "which", "who", "why", "with", "you", "your",
}

FACT_PATTERNS = (
    re.compile(r"\bmy name is ([a-z0-9 _-]{2,40})", re.IGNORECASE),
    re.compile(r"\bi am ([a-z0-9 _-]{2,40})", re.IGNORECASE),
    re.compile(r"\bi'm ([a-z0-9 _-]{2,40})", re.IGNORECASE),
    re.compile(r"\bmy favorite ([a-z0-9 _-]{2,20}) is ([a-z0-9 _-]{2,40})", re.IGNORECASE),
    re.compile(r"\bi like ([a-z0-9 ,_'/-]{2,60})", re.IGNORECASE),
    re.compile(r"\bi play ([a-z0-9 ,_'/-]{2,60})", re.IGNORECASE),
    re.compile(r"\bi work on ([a-z0-9 ,_'/-]{2,60})", re.IGNORECASE),
)


def normalize_text(text: str) -> str:
    return " ".join(text.lower().strip().split())


def extract_keywords(text: str) -> List[str]:
    words = re.findall(r"[a-z0-9][a-z0-9_-]{2,}", normalize_text(text))
    return [word for word in words if word not in STOPWORDS]


def classify_intent(text: str) -> str:
    lowered = normalize_text(text)
    if not lowered:
        return "chat"
    if any(token in lowered for token in ("!help", "!commands", "command", "how do i use !", "what command")):
        return "command_help"
    if any(token in lowered for token in ("gpt", "model", "repo", "github", "deploy", "host", "ec2", "service", "bot work", "architecture")):
        return "bot_repo"
    if any(token in lowered for token in ("uma", "gacha", "horse girl", "pity", "ssr")):
        return "uma"
    if any(token in lowered for token in ("remind", "reminder", "remindme")):
        return "reminder"
    if lowered.endswith("?") or lowered.startswith(("what ", "why ", "how ", "when ", "where ", "who ", "which ", "can ", "could ")):
        return "question_answer"
    if any(token in lowered for token in ("joke", "roast", "meme", "shitpost")):
        return "banter"
    return "chat"


def extract_user_facts(text: str) -> List[str]:
    facts: List[str] = []
    for pattern in FACT_PATTERNS:
        match = pattern.search(text)
        if not match:
            continue
        parts = [part.strip(" .,!?:;") for part in match.groups() if part.strip(" .,!?:;")]
        if parts:
            facts.append(" ".join(parts))
    return facts[:3]


def update_fact_memory(existing: Sequence[Dict[str, object]], new_facts: Sequence[str], limit: int = 12) -> List[Dict[str, object]]:
    merged: Dict[str, Dict[str, object]] = {
        str(entry.get("fact")): {"fact": str(entry.get("fact")), "weight": int(entry.get("weight", 1))}
        for entry in existing
        if entry.get("fact")
    }
    for fact in new_facts:
        entry = merged.setdefault(fact, {"fact": fact, "weight": 0})
        entry["weight"] = int(entry["weight"]) + 1
    ranked = sorted(merged.values(), key=lambda item: (-int(item["weight"]), str(item["fact"])))
    return ranked[:limit]


def score_overlap(query: str, text: str) -> int:
    query_terms = Counter(extract_keywords(query))
    text_terms = Counter(extract_keywords(text))
    return sum(min(query_terms[word], text_terms[word]) for word in query_terms)


def summarize_topics(existing: Dict[str, int], text: str, limit: int = 8) -> Dict[str, int]:
    updated = dict(existing)
    for keyword in extract_keywords(text):
        updated[keyword] = updated.get(keyword, 0) + 1
    ranked = sorted(updated.items(), key=lambda item: (-item[1], item[0]))
    return dict(ranked[:limit])


def relevant_facts(facts: Sequence[Dict[str, object]], query: str, limit: int = 3) -> List[str]:
    ranked = sorted(
        (
            (score_overlap(query, str(item.get("fact", ""))), int(item.get("weight", 1)), str(item.get("fact", "")))
            for item in facts
            if item.get("fact")
        ),
        key=lambda item: (-item[0], -item[1], item[2]),
    )
    return [fact for score, _, fact in ranked if score > 0][:limit] or [str(item.get("fact")) for item in facts[:limit]]


def relevant_topics(topic_counts: Dict[str, int], query: str, limit: int = 4) -> List[str]:
    query_terms = set(extract_keywords(query))
    ranked = sorted(
        topic_counts.items(),
        key=lambda item: (0 if item[0] in query_terms else 1, -item[1], item[0]),
    )
    return [topic for topic, _ in ranked[:limit]]


def load_repo_documents(base_dir: Path) -> Dict[str, str]:
    docs: Dict[str, str] = {}
    for relative_path in ("README.md", "CLAUDE.md", "AGENTS.md"):
        path = base_dir / relative_path
        try:
            docs[relative_path] = path.read_text(encoding="utf-8")
        except FileNotFoundError:
            continue
    return docs


def retrieve_repo_context(query: str, documents: Dict[str, str], limit: int = 3) -> List[str]:
    scored_chunks: List[Tuple[int, str]] = []
    for name, text in documents.items():
        lines = [line.rstrip() for line in text.splitlines() if line.strip()]
        for start in range(0, len(lines), 8):
            chunk = "\n".join(lines[start:start + 8])
            score = score_overlap(query, chunk)
            if score > 0:
                scored_chunks.append((score, f"[{name}]\n{chunk}"))
    scored_chunks.sort(key=lambda item: (-item[0], item[1]))
    return [chunk for _, chunk in scored_chunks[:limit]]


def build_memory_context(memory_state: Dict[str, object], user_id: str, guild_id: str, query: str) -> Dict[str, List[str]]:
    users = memory_state.get("users", {})
    guilds = memory_state.get("guilds", {})
    user_state = users.get(user_id, {}) if isinstance(users, dict) else {}
    guild_state = guilds.get(guild_id, {}) if isinstance(guilds, dict) else {}
    facts = relevant_facts(user_state.get("facts", []), query)
    topics = relevant_topics(user_state.get("topics", {}), query)
    preferences = list(guild_state.get("preferences", []))[:3]
    return {
        "facts": facts,
        "topics": topics,
        "preferences": preferences,
    }


def update_memory_state(memory_state: Dict[str, object], user_id: str, guild_id: str, text: str) -> Dict[str, object]:
    updated = {
        "users": dict(memory_state.get("users", {})),
        "guilds": dict(memory_state.get("guilds", {})),
    }
    users = updated["users"]
    guilds = updated["guilds"]
    user_state = dict(users.get(user_id, {}))
    user_state["facts"] = update_fact_memory(user_state.get("facts", []), extract_user_facts(text))
    user_state["topics"] = summarize_topics(user_state.get("topics", {}), text)
    users[user_id] = user_state

    guild_state = dict(guilds.get(guild_id, {}))
    if "short replies" in normalize_text(text):
        preferences = list(guild_state.get("preferences", []))
        if "keep replies short" not in preferences:
            preferences.append("keep replies short")
        guild_state["preferences"] = preferences[-5:]
    if guild_state:
        guilds[guild_id] = guild_state
    return updated


def build_system_prompt(
    base_personality: str,
    persona_description: str,
    intent: str,
    memory_context: Dict[str, List[str]],
    repo_context: Sequence[str],
) -> str:
    sections = [
        base_personality.strip(),
        "Behavior rules: answer directly, stay grounded, and do not invent bot commands or repo facts.",
        f"Intent: {intent}.",
    ]
    if persona_description:
        sections.append(f"Persona flavor: {persona_description}")
    if memory_context.get("facts"):
        sections.append("Relevant user facts: " + "; ".join(memory_context["facts"]))
    if memory_context.get("topics"):
        sections.append("Recent user topics: " + ", ".join(memory_context["topics"]))
    if memory_context.get("preferences"):
        sections.append("Server preferences: " + "; ".join(memory_context["preferences"]))
    if repo_context:
        sections.append("Grounding context:\n" + "\n\n".join(repo_context))
    return "\n\n".join(section for section in sections if section)


def validate_grounded_reply(reply: str, known_commands: Iterable[str], intent: str, repo_context: Sequence[str]) -> Tuple[bool, str]:
    if not reply.strip():
        return False, "empty reply"
    if intent not in {"command_help", "bot_repo", "question_answer"}:
        return True, ""

    known = {f"!{name}" for name in known_commands}
    mentioned_commands = set(re.findall(r"![a-z0-9_]+", reply.lower()))
    invalid = sorted(command for command in mentioned_commands if command not in {cmd.lower() for cmd in known})
    if invalid:
        return False, f"unknown commands mentioned: {', '.join(invalid)}"
    if intent in {"command_help", "bot_repo"} and not repo_context:
        return False, "missing repo context"
    return True, ""

