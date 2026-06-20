import re

from radar.core.models import RawHit, DetectorResult, Category, Confidence

_PLATFORMS = [
    "hackerone",
    "bugcrowd",
    "intigriti",
    "immunefi",
    "hackenproof",
    "yeswehack",
    "synack",
]

_HIGH_KEYWORDS = [
    r"\bbug.?bounty\b",
    r"\bbugbounty\b",
    r"vulnerability.?disclosure",
    r"\bvdp\b",
    r"vdp.?program",
]

_MEDIUM_KEYWORDS = [
    r"\bbounty\b",
    r"\breward\b",
    r"\bpayout\b",
    r"\bvulnerabilit",
    r"security.?research",
    r"responsible.?disclosure",
    r"hall.?of.?fame",
    r"\bscope\b",
    r"web.?application",
    r"mobile.?app",
    r"smart.?contract",
    r"\bblockchain\b",
    r"\bapi\b",
    r"security.?audit",
]

_AUDIT_KEYWORDS = [
    "audit contest",
    "audit competition",
    "code4rena",
    "sherlock",
    "cantina",
    "immunefi",
]

_PRIZE_PATTERN = re.compile(r"\$[0-9,]+")


def detect(hit: RawHit) -> DetectorResult:
    text = f"{hit.title} {hit.snippet}".lower()

    if hit.detector_hint == "bug_bounty":
        tags = ["bug_bounty"]
        if _PRIZE_PATTERN.search(text):
            tags.append("cash_prize")
        return DetectorResult(
            matched=True,
            confidence=Confidence.HIGH,
            category=Category.BUG_BOUNTY,
            tags=tags,
            why_found=["source detector_hint: bug_bounty"],
        )

    title_lower = hit.title.lower()
    for pattern in _HIGH_KEYWORDS:
        if re.search(pattern, title_lower):
            tags = ["bug_bounty"]
            if _PRIZE_PATTERN.search(text):
                tags.append("cash_prize")
            return DetectorResult(
                matched=True,
                confidence=Confidence.HIGH,
                category=Category.BUG_BOUNTY,
                tags=tags,
                why_found=[f"Title matches: {pattern}"],
            )

    for platform in _PLATFORMS:
        if platform in text:
            tags = ["bug_bounty"]
            if _PRIZE_PATTERN.search(text):
                tags.append("cash_prize")
            return DetectorResult(
                matched=True,
                confidence=Confidence.HIGH,
                category=Category.BUG_BOUNTY,
                tags=tags,
                why_found=[f"Platform: {platform}"],
            )

    for keyword in _AUDIT_KEYWORDS:
        if keyword in text:
            tags = ["bug_bounty", "audit_contest"]
            if _PRIZE_PATTERN.search(text):
                tags.append("cash_prize")
            return DetectorResult(
                matched=True,
                confidence=Confidence.HIGH,
                category=Category.BUG_BOUNTY,
                tags=tags,
                why_found=[f"Audit contest: {keyword}"],
            )

    medium_matches = [kw for kw in _MEDIUM_KEYWORDS if re.search(kw, text)]
    if len(medium_matches) >= 2:
        return DetectorResult(
            matched=True,
            confidence=Confidence.MEDIUM,
            category=Category.BUG_BOUNTY,
            tags=["bug_bounty"],
            why_found=[f"Keywords: {', '.join(medium_matches[:3])}"],
        )

    return DetectorResult(matched=False)
