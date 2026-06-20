import re
from datetime import datetime, timezone

from radar.core.models import RawHit, DetectorResult, Category, Confidence

_HIGH_KEYWORDS = [
    r"early.?bird",
    r"\bearlybird\b",
]

_PROMO_CODE = re.compile(r"[A-Z]{4,12}[0-9]{2,4}")

_CODE_TRIGGERS = [
    r"promo.?code",
    r"discount.?code",
    r"coupon.?code",
    r"offer.?code",
]

_MEDIUM_KEYWORDS = [
    r"limited.?time",
    r"limited.?offer",
    r"\bexpires\b",
    r"valid.?until",
    r"\bhurry\b",
    r"register.?before",
    r"early.?registration",
    r"early.?pricing",
]

_PERCENT_PATTERN = re.compile(r"[0-9]{1,3}\s*%?\s*off", re.IGNORECASE)
_DEADLINE_PATTERN = re.compile(
    r"(deadline|apply by|expires|valid until)\s*:?\s*(.*)", re.IGNORECASE
)


def detect(hit: RawHit) -> DetectorResult:
    text = f"{hit.title} {hit.snippet}"

    if hit.detector_hint == "early_bird":
        return DetectorResult(
            matched=True,
            confidence=Confidence.HIGH,
            category=Category.EARLY_BIRD,
            tags=["early_bird"],
            why_found=["source detector_hint: early_bird"],
        )

    title_lower = hit.title.lower()
    for pattern in _HIGH_KEYWORDS:
        if re.search(pattern, title_lower):
            return DetectorResult(
                matched=True,
                confidence=Confidence.HIGH,
                category=Category.EARLY_BIRD,
                tags=["early_bird"],
                why_found=[f"Title matches: {pattern}"],
            )

    has_code = bool(_PROMO_CODE.search(text))
    has_code_trigger = any(re.search(trig, text.lower()) for trig in _CODE_TRIGGERS)
    has_percent = bool(_PERCENT_PATTERN.search(text))

    if has_code and has_code_trigger:
        code_match = _PROMO_CODE.search(text)
        tags = ["early_bird", "promo_code"]
        return DetectorResult(
            matched=True,
            confidence=Confidence.HIGH,
            category=Category.EARLY_BIRD,
            tags=tags,
            why_found=[f"Promo code detected: {code_match.group()}"],
        )

    medium_matches = [kw for kw in _MEDIUM_KEYWORDS if re.search(kw, text.lower())]
    signals = len(medium_matches) + (1 if has_code else 0) + (1 if has_percent else 0)

    if signals >= 2:
        return DetectorResult(
            matched=True,
            confidence=Confidence.MEDIUM,
            category=Category.EARLY_BIRD,
            tags=["early_bird"],
            why_found=[f"Signals: {', '.join(medium_matches[:3])}"],
        )

    return DetectorResult(matched=False)
