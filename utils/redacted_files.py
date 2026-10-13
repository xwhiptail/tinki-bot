"""Render an overtly fictional TINKILEAKS document; never fetch real records."""
import io
import re

from PIL import Image, ImageDraw, ImageFont


def clean_cameo_name(name: str) -> str:
    """Keep user-controlled names on one line and out of Discord formatting."""
    name = re.sub(r"[\x00-\x1f\x7f]", " ", name)
    name = re.sub(r"\s+", " ", name).strip()
    return name[:48] or "Unnamed guildmate"


def cameo_annotations(names: list[str]) -> list[str]:
    """User-requested running jokes, explicitly fictional and fully redacted."""
    normalized = {clean_cameo_name(name).casefold().rstrip('.') for name in names}
    labels = []
    if normalized & {'jun', 'cate'}:
        group = '/'.join(name.upper() for name in ('jun', 'cate') if name in normalized)
        labels.extend(f"{group} / {label}" for label in (
            "SOAPLAND ITINERARY", "FUTA FOLDER", "PORN-GAME BACKLOG", "BIG BUTTS DEPARTMENT",
        ))
    if 'lhea' in normalized:
        labels.extend(("LHEA / ZELDA SPEEDRUN SPLITS", "LHEA / FFXIV GLAMOUR BUDGET"))
    if normalized & {'whiptail', 'whippy'}:
        labels.extend(("WHIPTAIL / BIG TITS DEPARTMENT", "WHIPTAIL / GOTH GIRLS", "WHIPTAIL / GOON CAVE BLUEPRINTS"))
    return labels


def render_redacted_files(names: list[str]) -> io.BytesIO:
    page = Image.new("RGB", (1000, 1280), "#f3efdf")
    draw = ImageDraw.Draw(page)
    title = ImageFont.load_default(size=46)
    heading = ImageFont.load_default(size=28)
    body = ImageFont.load_default(size=24)
    small = ImageFont.load_default(size=20)
    ink = "#22211f"
    red = "#9d3027"
    draw.rectangle((30, 30, 970, 1250), outline=ink, width=2)
    draw.text((70, 65), "TINKILEAKS", font=title, fill=ink)
    draw.text((70, 126), "THE REDACTED EPSTEIN FILES", font=heading, fill=ink)
    draw.rectangle((70, 182, 930, 272), outline=red, width=4)
    draw.text((95, 194), "DEPARTMENT OF REDACTION", font=heading, fill=red)
    draw.text((95, 235), "CLEARANCE LEVEL: TINY BOOTS ONLY", font=small, fill=red)
    draw.text((70, 305), "DISCORD CAMEOS", font=small, fill=ink)
    for index, name in enumerate(names[:3] or ["[REDACTED]"]):
        name = clean_cameo_name(name)
        name_font = heading
        for size in range(28, 11, -1):
            name_font = ImageFont.load_default(size=size)
            if draw.textlength(name, font=name_font) <= 860:
                break
        draw.text((70, 344 + index * 38), name, font=name_font, fill=ink)
    draw.line((70, 485, 930, 485), fill=ink, width=2)
    labels = cameo_annotations(names) or ["ENTRY", "DETAILS", "MORE DETAILS", "EVEN THESE DETAILS"]
    row_height = min(110, 440 // len(labels))
    for index, label in enumerate(labels):
        y = 515 + index * row_height
        draw.text((70, y), label, font=small, fill=ink)
        draw.rectangle((70, y + 30, 870 - index * 30, y + 48), fill=ink)
        draw.rectangle((70, y + 54, 670 + index * 30, y + 64), fill=ink)
    draw.text((70, 1010), "Evidence recovered: 0 bytes. Ink wasted: unlimited.", font=body, fill=ink)
    draw.text((70, 1060), "Even the redactions have been redacted.", font=body, fill=ink)
    draw.rectangle((70, 1125, 930, 1205), outline=red, width=3)
    draw.text((95, 1140), "GNOME INTELLIGENCE AGENCY", font=heading, fill=red)
    draw.text((95, 1177), "Page 001 of [REDACTED] / tiny eyes only", font=small, fill=red)
    output = io.BytesIO()
    page.save(output, format="PNG")
    output.seek(0)
    return output
