import re
from typing import Optional


WEEKDAY_NAMES = (
    "Monday",
    "Tuesday",
    "Wednesday",
    "Thursday",
    "Friday",
    "Saturday",
    "Sunday",
)

MONTH_NAMES = (
    "January",
    "February",
    "March",
    "April",
    "May",
    "June",
    "July",
    "August",
    "September",
    "October",
    "November",
    "December",
)

NAMED_LISTS = (
    {
        "aliases": ("days of the week",),
        "label": "days of the week",
        "scope": "of the week",
        "singular": "day",
        "plural": "days",
        "items": WEEKDAY_NAMES,
    },
    {
        "aliases": ("months of the year",),
        "label": "months of the year",
        "scope": "of the year",
        "singular": "month",
        "plural": "months",
        "items": MONTH_NAMES,
    },
)


def _format_english_list(items):
    if len(items) == 1:
        return items[0]
    if len(items) == 2:
        return f"{items[0]} and {items[1]}"
    return f"{', '.join(items[:-1])}, and {items[-1]}"


def _named_list_letter_from_query(lowered: str):
    patterns = (
        r"\b(?:contain|contains|have|has|include|includes)\s+"
        r"(?:the\s+)?letter\s+['\"]?([a-z])['\"]?\b",
        r"\b(?:contain|contains|have|has|include|includes)\s+"
        r"(?:an?\s+)?['\"]?([a-z])['\"]?(?:\s+in\s+them)?\b",
    )
    for pattern in patterns:
        match = re.search(pattern, lowered)
        if match:
            return match.group(1)
    return None


def _named_list_from_query(lowered: str):
    for named_list in NAMED_LISTS:
        if any(alias in lowered for alias in named_list["aliases"]):
            return named_list
    return None


def _asks_for_missing_items(lowered: str) -> bool:
    return bool(re.search(
        r"\b(?:do|does)\s+not\s+(?:contain|have|include)\b"
        r"|"
        r"\b(?:don't|dont|doesn't|doesnt)\s+(?:contain|have|include)\b"
        r"|"
        r"\bmissing\s+(?:the\s+)?letter\b",
        lowered,
    ))


def _named_list_letter_reply(named_list, target_letter: str, *, wants_missing: bool = False) -> str:
    label = named_list["label"]
    scope = named_list["scope"]
    singular = named_list["singular"]
    plural = named_list["plural"]
    items = named_list["items"]
    matching_items = [
        item for item in items
        if target_letter in item.lower()
    ]
    missing_items = [
        item for item in items
        if target_letter not in item.lower()
    ]

    if wants_missing:
        if not missing_items:
            return (
                f"0 {plural} {scope} do not contain "
                f"'{target_letter}'. All {len(matching_items)} contain it: "
                f"{_format_english_list(matching_items)}."
            )
        count_word = singular if len(missing_items) == 1 else plural
        reply = (
            f"{len(missing_items)} {count_word} {scope} "
            f"do not contain '{target_letter}': {_format_english_list(missing_items)}."
        )
        if matching_items:
            reply += f" {_format_english_list(matching_items)} contain it."
        return reply

    if not matching_items:
        return f"No {label} contain '{target_letter}'."
    if not missing_items:
        return (
            f"All {len(matching_items)} {label} contain "
            f"'{target_letter}': {_format_english_list(matching_items)}."
        )

    item_word = singular if len(matching_items) == 1 else plural
    verb = "contains" if len(matching_items) == 1 else "contain"
    reply = (
        f"{len(matching_items)} {item_word} {scope} {verb} "
        f"'{target_letter}': {_format_english_list(matching_items)}."
    )

    if len(missing_items) == 1:
        return f"{reply} Only {missing_items[0]} does not."
    return f"{reply} {_format_english_list(missing_items)} do not."


def _word_letter_from_query(lowered: str) -> Optional[tuple[str, str]]:
    letter_then_word_patterns = (
        r"\bhow many\s+(?:letter\s+)?([a-z])(?:'s|s)?\s+"
        r"(?:(?:are\s+there|are)\s+)?in\s+(?:the word\s+)?([a-z]+)\b",
        r"\bhow many\s+(?:letter\s+)?([a-z])(?:'s|s)?\s+"
        r"(?:does|do)\s+(?:the word\s+)?([a-z]+)\s+"
        r"(?:have|contain|include)\b",
        r"\b(?:got\s+)?many\s+(?:letter\s+)?([a-z])(?:'s|s)?\s+"
        r"in\s+(?:the word\s+)?([a-z]+)\b",
        r"\b(?:count|counting|counted)\s+(?:letter\s+)?([a-z])(?:'s|s)?\s+"
        r"in\s+(?:the word\s+)?([a-z]+)\b",
    )
    for pattern in letter_then_word_patterns:
        match = re.search(pattern, lowered)
        if match:
            return match.groups()

    word_then_letter_patterns = (
        r"\b(?:the word\s+)?([a-z]+)\s+"
        r"(?:has|have|contains|contain|includes|include)\s+"
        r"(?:(?:zero|one|two|three|four|five|six|seven|eight|nine|ten|\d+)\s+)?"
        r"(?:letter\s+)?([a-z])(?:'s|s)?\b",
    )
    for pattern in word_then_letter_patterns:
        match = re.search(pattern, lowered)
        if match:
            word, target_letter = match.groups()
            return target_letter, word
    return None


def _word_letter_reply(target_letter: str, target_word: str) -> str:
    count = target_word.count(target_letter)
    times = "time" if count == 1 else "times"
    return f"'{target_letter}' appears {count} {times} in '{target_word}'"


def maybe_count_letter_reply(text: str) -> Optional[str]:
    lowered = text.strip().lower().rstrip(' ?!.')
    named_list = _named_list_from_query(lowered)
    if named_list:
        named_list_letter = _named_list_letter_from_query(lowered)
        if named_list_letter:
            return _named_list_letter_reply(
                named_list,
                named_list_letter,
                wants_missing=_asks_for_missing_items(lowered),
            )

    word_letter = _word_letter_from_query(lowered)
    if not word_letter:
        return None
    target_letter, target_word = word_letter
    return _word_letter_reply(target_letter, target_word)
