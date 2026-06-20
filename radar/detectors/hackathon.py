import re

from radar.core.models import RawHit, DetectorResult, Category, Confidence

_CONFERENCE_NAMES = [
    "def con",
    "black hat",
    "bsides",
    "nullcon",
    "c0c0n",
    "hitb",
    "hack in the box",
    "cyber summit",
    "security conference",
]

_HIGH_KEYWORDS = [
    r"\bhackathon\b",
    r"\bhack.?a.?thon\b",
    r"\bcodefest\b",
    r"\bbuildathon\b",
]

_MEDIUM_KEYWORDS = [
    r"\bcfp\b",
    r"call.?for.?papers",
    r"call.?for.?speakers",
    r"student.?pass",
    r"volunteer.?pass",
    r"travel.?grant",
    r"\bscholarship\b",
    r"financial.?aid",
    r"diversity.?scholarship",
    r"\bworkshop\b",
    r"\btraining\b",
]

_CFP_PATTERN = re.compile(
    r"(cfp|call.?for|submissions?\s*(due|close|deadline))", re.IGNORECASE
)
_DATE_PATTERN = re.compile(
    r"(january|february|march|april|may|june|july|august|september|october|november|december)\s+\d{1,2}.*\d{4}"
)


def detect(hit: RawHit) -> DetectorResult:
    text = f"{hit.title} {hit.snippet}".lower()

    if hit.detector_hint == "hackathon":
        return DetectorResult(
            matched=True,
            confidence=Confidence.HIGH,
            category=Category.HACKATHON,
            tags=["hackathon"],
            why_found=["source detector_hint: hackathon"],
        )

    title_lower = hit.title.lower()
    for pattern in _HIGH_KEYWORDS:
        if re.search(pattern, title_lower):
            tags = ["hackathon"]
            if _CFP_PATTERN.search(text):
                tags.append("cfp")
            return DetectorResult(
                matched=True,
                confidence=Confidence.HIGH,
                category=Category.HACKATHON,
                tags=tags,
                why_found=[f"Title matches: {pattern}"],
            )

    for conf_name in _CONFERENCE_NAMES:
        if conf_name in text:
            tags = ["hackathon", "conference"]
            if _CFP_PATTERN.search(text):
                tags.append("cfp")
            return DetectorResult(
                matched=True,
                confidence=Confidence.HIGH,
                category=Category.HACKATHON,
                tags=tags,
                why_found=[f"Conference: {conf_name}"],
            )

    medium_matches = [kw for kw in _MEDIUM_KEYWORDS if re.search(kw, text)]
    if len(medium_matches) >= 2:
        return DetectorResult(
            matched=True,
            confidence=Confidence.MEDIUM,
            category=Category.HACKATHON,
            tags=medium_matches,
            why_found=[f"Keywords: {', '.join(medium_matches[:3])}"],
        )

    return DetectorResult(matched=False)
