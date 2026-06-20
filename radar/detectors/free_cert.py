import re

from radar.core.models import RawHit, DetectorResult, Category, Confidence

_PROVIDERS = [
    "fortinet nse",
    "cisco",
    "isc2",
    "microsoft learn",
    "aws skill builder",
    "google cloud skills boost",
    "sans",
    "ec-council",
]

_HIGH_KEYWORDS = [
    r"free.?certification",
    r"free.?exam",
    r"free.?voucher",
    r"free.?course",
    r"free.?training",
    r"free.?cert",
    r"\$0\b",
    r"100%?\s*off",
    r"no cost",
]

_MEDIUM_KEYWORDS = [
    r"exam.?voucher",
    r"certification.?voucher",
    r"discount.?code",
    r"promo.?code",
    r"limited.?time",
    r"free.?access",
    r"enroll now",
    r"start learning",
]

_SCHOLARSHIP_KEYWORDS = [
    r"\bscholarship\b",
    r"\bgrant\b",
    r"financial.?assistance",
    r"tuition.?waiver",
    r"women.?in.?cyber",
    r"minority.?scholarship",
    r"diversity.?in.?tech",
    r"wicys",
    r"women.?in.?cybersecurity",
]


def detect(hit: RawHit) -> DetectorResult:
    text = f"{hit.title} {hit.snippet}".lower()

    if hit.detector_hint == "free_cert":
        return DetectorResult(
            matched=True,
            confidence=Confidence.HIGH,
            category=Category.FREE_CERT,
            tags=["free_cert", "free_training"],
            why_found=["source detector_hint: free_cert"],
        )

    title_lower = hit.title.lower()
    for pattern in _HIGH_KEYWORDS:
        if re.search(pattern, title_lower):
            tags = ["free_cert"]
            if "cert" in title_lower or "certification" in title_lower:
                tags.append("certificate")
            return DetectorResult(
                matched=True,
                confidence=Confidence.HIGH,
                category=Category.FREE_CERT,
                tags=tags,
                why_found=[f"Title matches: {pattern}"],
            )

    for provider in _PROVIDERS:
        if provider in text:
            tags = ["free_cert", "free_training"]
            if "voucher" in text or "exam" in text:
                tags.append("exam_voucher")
            if "scholarship" in text or "grant" in text:
                tags.append("scholarship")
            if "cert" in text or "certification" in text:
                tags.append("certificate")
            return DetectorResult(
                matched=True,
                confidence=Confidence.HIGH,
                category=Category.FREE_CERT,
                tags=tags,
                why_found=[f"Provider: {provider}"],
            )

    medium_matches = [kw for kw in _MEDIUM_KEYWORDS if re.search(kw, text)]
    if len(medium_matches) >= 2:
        tags = ["free_cert"]
        if "voucher" in text or "exam" in text:
            tags.append("exam_voucher")
        return DetectorResult(
            matched=True,
            confidence=Confidence.MEDIUM,
            category=Category.FREE_CERT,
            tags=tags,
            why_found=[f"Keywords: {', '.join(medium_matches[:3])}"],
        )

    scholarship_matches = [kw for kw in _SCHOLARSHIP_KEYWORDS if re.search(kw, text)]
    if len(scholarship_matches) >= 2:
        return DetectorResult(
            matched=True,
            confidence=Confidence.MEDIUM,
            category=Category.FREE_CERT,
            tags=["free_cert", "scholarship"],
            why_found=[f"Scholarship: {', '.join(scholarship_matches[:3])}"],
        )

    return DetectorResult(matched=False)
