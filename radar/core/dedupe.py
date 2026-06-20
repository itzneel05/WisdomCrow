import hashlib
import re
from urllib.parse import urlencode, urlparse, urlunparse, parse_qs

from rapidfuzz import fuzz

from .models import make_canonical_key, normalize_title, normalize_url
from .storage import Database

_TRACKING_PARAMS = {
    "utm_source",
    "utm_medium",
    "utm_campaign",
    "utm_term",
    "utm_content",
    "fbclid",
    "gclid",
    "mc_cid",
    "mc_eid",
    "ref",
    "source",
}


def normalize_url(url: str) -> str:
    if not url:
        return url
    parsed = urlparse(url.lower())
    scheme = parsed.scheme
    netloc = parsed.netloc.replace("www.", "")
    path = parsed.path.rstrip("/")
    query = parse_qs(parsed.query, keep_blank_values=True)
    for param in _TRACKING_PARAMS:
        query.pop(param, None)
    sorted_query = urlencode(sorted(query.items()), doseq=True)
    result = urlunparse((scheme, netloc, path, parsed.params, sorted_query, ""))
    return result


def normalize_title(title: str) -> str:
    title = title.strip()
    title = re.sub(r"\s+", " ", title)
    title = title.lower()
    title = re.sub(r"\s*[|—–-]\s*.*$", "", title)
    return title.strip()


def is_duplicate(
    db: Database,
    title: str,
    url: str,
    threshold: int = 85,
    window_days: int = 30,
) -> bool:
    canonical_url = normalize_url(url)
    normalized_title = normalize_title(title)
    canonical_key = hashlib.sha256(
        f"{normalized_title}|{canonical_url}".encode()
    ).hexdigest()

    if db.opportunity_exists(canonical_key):
        db.update_last_seen(canonical_key)
        return True

    existing = db._fetchall(
        """SELECT canonical_key, title FROM opportunities
           WHERE last_seen_at >= NOW() - INTERVAL '%s days'""",
        (window_days,),
    )

    for row in existing:
        ratio = fuzz.token_sort_ratio(normalized_title, normalize_title(row["title"]))
        if ratio >= threshold:
            db.update_last_seen(row["canonical_key"])
            return True

    return False
