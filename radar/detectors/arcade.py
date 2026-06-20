import re

from radar.core.models import RawHit, DetectorResult, Category, Confidence

_PLATFORM_SIGNALS = {
    "google arcade": {
        "keywords": [
            "arcade",
            "google cloud skills boost",
            "skill badge",
            "google cloud arcade",
        ],
        "rewards": ["badge", "swag", "cloud_credits"],
    },
    "hackthebox": {
        "keywords": [
            "cyber apocalypse",
            "global benchmark",
            "htb season",
            "university ctf",
            "business ctf",
        ],
        "rewards": ["badge", "swag", "tshirt", "hoodie"],
    },
    "tryhackme": {
        "keywords": ["advent of cyber", "industrial intrusion", "thm season"],
        "rewards": ["badge", "swag"],
    },
    "microsoft learn": {
        "keywords": [
            "cloud skills challenge",
            "microsoft learn",
            "learn.microsoft.com",
        ],
        "rewards": ["badge", "exam_voucher", "cloud_credits"],
    },
    "aws skill builder": {
        "keywords": ["aws skill builder", "aws jam", "aws cloud quest"],
        "rewards": ["badge", "cloud_credits"],
    },
}

_HIGH_KEYWORDS = [
    r"\barcade\b",
    r"\bseason\b",
    r"\bquest\b",
    r"challenge.?series",
]

_MEDIUM_KEYWORDS = [
    r"\bbadge\b",
    r"\bachievement\b",
    r"\bleaderboard\b",
    r"\bxp\b",
    r"level.?up",
    r"season.?pass",
    r"earn.?badge",
    r"rank.?up",
    r"monthly.?challenge",
    r"complete.?challenge",
]


def detect(hit: RawHit) -> DetectorResult:
    text = f"{hit.title} {hit.snippet}".lower()
    url_lower = hit.url.lower()

    if hit.detector_hint == "arcade":
        return DetectorResult(
            matched=True,
            confidence=Confidence.HIGH,
            category=Category.ARCADE,
            tags=["arcade", "participation_reward"],
            why_found=["source detector_hint: arcade"],
        )

    for platform, signals in _PLATFORM_SIGNALS.items():
        for kw in signals["keywords"]:
            if kw in text or kw in url_lower:
                tags = ["arcade"] + signals["rewards"]
                return DetectorResult(
                    matched=True,
                    confidence=Confidence.HIGH,
                    category=Category.ARCADE,
                    tags=tags,
                    why_found=[f"Platform event: {platform} ({kw})"],
                )

    title_lower = hit.title.lower()
    for pattern in _HIGH_KEYWORDS:
        if re.search(pattern, title_lower):
            return DetectorResult(
                matched=True,
                confidence=Confidence.MEDIUM,
                category=Category.ARCADE,
                tags=["arcade"],
                why_found=[f"Title matches: {pattern}"],
            )

    medium_matches = [kw for kw in _MEDIUM_KEYWORDS if re.search(kw, text)]
    if len(medium_matches) >= 2:
        return DetectorResult(
            matched=True,
            confidence=Confidence.MEDIUM,
            category=Category.ARCADE,
            tags=["arcade"],
            why_found=[f"Keywords: {', '.join(medium_matches[:3])}"],
        )

    return DetectorResult(matched=False)
