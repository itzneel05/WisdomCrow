from radar.core.models import RawHit, DetectorResult, Category, Confidence

_SECURITY_TOPICS = [
    "security",
    "cybersecurity",
    "penetration-testing",
    "penetration testing",
    "vulnerability-scanner",
    "vulnerability scanner",
    "osint",
    "exploit",
    "malware-analysis",
    "malware analysis",
    "forensics",
    "reverse-engineering",
    "reverse engineering",
    "ctf",
]

_SECURITY_NAMES = [
    "vuln",
    "exploit",
    "scanner",
    "audit",
    "fuzz",
    "recon",
    "payload",
    "sploit",
    "hack",
    "crack",
]

_DESCRIPTION_KEYWORDS = [
    "security tool",
    "hacking tool",
    "vulnerable",
    "ctf platform",
    "lab",
    "challenge",
    "practice",
    "training",
    "educational",
]

_SECURITY_LANGUAGES = {
    "python",
    "go",
    "rust",
    "c",
    "c++",
    "assembly",
    "bash",
    "powershell",
}

_MIN_STARS = 3


def detect(hit: RawHit) -> DetectorResult:
    text = f"{hit.title} {hit.snippet}".lower()
    stars = hit.extra.get("stars", 0)
    topics = hit.extra.get("topics", [])
    language = hit.extra.get("language", "")

    if hit.detector_hint == "open_source":
        return DetectorResult(
            matched=True,
            confidence=Confidence.HIGH,
            category=Category.OPEN_SOURCE,
            tags=["open_source"],
            why_found=["source detector_hint: open_source"],
        )

    if stars < _MIN_STARS:
        return DetectorResult(matched=False)

    matched_topics = [
        t for t in _SECURITY_TOPICS if t in topics or t.replace("-", " ") in text
    ]
    matched_names = [n for n in _SECURITY_NAMES if n in hit.title.lower()]
    matched_desc = [dk for dk in _DESCRIPTION_KEYWORDS if dk in text]

    if matched_topics:
        tags = ["open_source"]
        if stars >= 10:
            tags.append("trending")
        return DetectorResult(
            matched=True,
            confidence=Confidence.HIGH,
            category=Category.OPEN_SOURCE,
            tags=tags,
            why_found=[f"Security topics: {', '.join(matched_topics[:3])}"],
        )

    if matched_names:
        return DetectorResult(
            matched=True,
            confidence=Confidence.MEDIUM,
            category=Category.OPEN_SOURCE,
            tags=["open_source"],
            why_found=[f"Name pattern: {', '.join(matched_names[:3])}"],
        )

    if matched_desc:
        return DetectorResult(
            matched=True,
            confidence=Confidence.MEDIUM,
            category=Category.OPEN_SOURCE,
            tags=["open_source", "educational"],
            why_found=[f"Description: {', '.join(matched_desc[:3])}"],
        )

    if language and language.lower() in _SECURITY_LANGUAGES and stars >= 10:
        return DetectorResult(
            matched=True,
            confidence=Confidence.LOW,
            category=Category.OPEN_SOURCE,
            tags=["open_source"],
            why_found=[f"Security-adjacent language: {language}"],
        )

    return DetectorResult(matched=False)
