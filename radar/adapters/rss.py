import logging
from datetime import datetime, timezone, timedelta
from typing import Any

import feedparser
import requests

from radar.core.models import RawHit, SourceMeta

logger = logging.getLogger(__name__)

USER_AGENT = "WisdomCrow/1.0"
REQUEST_TIMEOUT = 30

CADENCE_MAX_AGE = {
    "fast": timedelta(days=7),
    "daily": timedelta(days=30),
    "weekly": timedelta(days=90),
}


def fetch(source: SourceMeta, is_seen_fn: Any = None) -> list[RawHit]:
    hits: list[RawHit] = []
    try:
        resp = requests.get(
            source.url,
            headers={"User-Agent": USER_AGENT},
            timeout=REQUEST_TIMEOUT,
        )
        resp.raise_for_status()
    except requests.RequestException as e:
        logger.warning(f"RSS fetch failed for {source.name}: {e}")
        return hits

    feed = feedparser.parse(resp.content)
    if not feed.entries:
        logger.info(f"No entries in RSS feed {source.name}")
        return hits

    max_age = CADENCE_MAX_AGE.get(source.cadence, timedelta(days=7))
    cutoff = datetime.now(timezone.utc) - max_age

    for entry in feed.entries:
        title = entry.get("title", "")
        link = entry.get("link", "")
        summary = entry.get("summary", "") or entry.get("description", "")
        published = entry.get("published_parsed")

        if not title or not link:
            continue

        published_at = ""
        if published:
            try:
                dt = datetime(*published[:6], tzinfo=timezone.utc)
                published_at = dt.isoformat()
                if dt < cutoff:
                    continue
            except Exception:
                pass

        hit = RawHit(
            source_id=source.name,
            source_name=source.name,
            title=title,
            url=link,
            snippet=summary[:500] if summary else "",
            published_at=published_at,
            detector_hint=source.detector_hint,
        )

        if is_seen_fn and is_seen_fn(hit.content_hash):
            continue

        if not hit.is_valid():
            continue

        hits.append(hit)

    logger.info(
        f"RSS {source.name}: {len(hits)} new hits from {len(feed.entries)} entries"
    )
    return hits
