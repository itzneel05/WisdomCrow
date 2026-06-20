import re
from datetime import datetime, timezone

from radar.core.models import RawHit, DetectorResult, Category, Confidence

_HIGH_KEYWORDS = [
    r"\bctf\b",
    r"capture.?the.?flag",
]

_MEDIUM_KEYWORDS = [
    r"\bchallenge",
    r"\bflag\b",
    r"\bexploit\b",
    r"\bpwn\b",
    r"\breverse\b",
    r"\bcrypto\b",
    r"\bforensics\b",
    r"\bweb\b",
    r"\bjail\b",
    r"\bpuzzle\b",
    r"hacking.?competition",
    r"\bjeopardy\b",
    r"attack.?defense",
    r"king.?of.?the.?hill",
]

_PLATFORM_NAMES = [
    "hackthebox",
    "tryhackme",
    "ctftime",
    "picoctf",
    "csaw",
    "angstrom",
    "hsctf",
    "wolvctf",
    "google ctf",
]

_RECURRING_EVENTS = {
    "huntress": (10, "Huntress CTF"),
    "google ctf": (6, "Google CTF"),
    "cyber apocalypse": (3, "HTB Cyber Apocalypse"),
    "advent of cyber": (12, "Advent of Cyber"),
    "picoctf": (3, "picoCTF"),
}

_NEGATIVE_KEYWORDS = [
    "football",
    "sports",
    "paintball",
    "minecraft",
    "roblox",
    "flag football",
    "capture the flag game",
]


def detect(hit: RawHit) -> DetectorResult:
    text = f"{hit.title} {hit.snippet}".lower()

    for nk in _NEGATIVE_KEYWORDS:
        if nk in text:
            return DetectorResult(matched=False)

    if hit.detector_hint == "ctf":
        return DetectorResult(
            matched=True,
            confidence=Confidence.HIGH,
            category=Category.CTF,
            tags=["ctf"],
            why_found=["source detector_hint: ctf"],
        )

    title_lower = hit.title.lower()
    for pattern in _HIGH_KEYWORDS:
        if re.search(pattern, title_lower):
            return DetectorResult(
                matched=True,
                confidence=Confidence.HIGH,
                category=Category.CTF,
                tags=["ctf"],
                why_found=[f"Title matches: {pattern}"],
            )

    medium_matches = []
    for pattern in _MEDIUM_KEYWORDS:
        if re.search(pattern, text):
            medium_matches.append(pattern)

    for platform in _PLATFORM_NAMES:
        if platform in text:
            medium_matches.append(platform)

    if len(medium_matches) >= 2:
        return DetectorResult(
            matched=True,
            confidence=Confidence.MEDIUM,
            category=Category.CTF,
            tags=["ctf"],
            why_found=[f"Keywords: {', '.join(medium_matches[:3])}"],
        )

    for event_name, (month, display_name) in _RECURRING_EVENTS.items():
        if event_name in title_lower:
            now = datetime.now(timezone.utc)
            if now.month <= month or (
                now.month >= month - 2 and now.month <= month + 1
            ):
                return DetectorResult(
                    matched=True,
                    confidence=Confidence.MEDIUM,
                    category=Category.CTF,
                    tags=["ctf", "recurring"],
                    why_found=[f"Recurring event: {display_name}"],
                )

    return DetectorResult(matched=False)
