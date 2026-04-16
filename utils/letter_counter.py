import re
from typing import Optional


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
