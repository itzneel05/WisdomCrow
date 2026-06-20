import logging
from datetime import datetime, timezone, timedelta
from typing import Any

import requests

from radar.core.models import RawHit, SourceMeta

logger = logging.getLogger(__name__)

USER_AGENT = "WisdomCrow/1.0"
REQUEST_TIMEOUT = 30
MAX_RESULTS_PER_QUERY = 100
MIN_STARS = 3
MAX_AGE_DAYS = 30


def fetch(source: SourceMeta, is_seen_fn: Any = None) -> list[RawHit]:
    hits: list[RawHit] = []

    headers = {
        "User-Agent": USER_AGENT,
        "Accept": "application/vnd.github.v3+json",
    }

    github_token = getattr(source, "_github_token", None)
    if github_token:
        headers["Authorization"] = f"token {github_token}"

    try:
        resp = requests.get(
            source.url,
            headers=headers,
            timeout=REQUEST_TIMEOUT,
        )
        if resp.status_code == 403 and "rate limit" in resp.text.lower():
            logger.warning(f"GitHub API rate limited for {source.name}")
            return hits
        resp.raise_for_status()
    except requests.RequestException as e:
        logger.warning(f"GitHub search failed for {source.name}: {e}")
        return hits

    data = resp.json()
    items = data.get("items", [])
    cutoff = datetime.now(timezone.utc) - timedelta(days=MAX_AGE_DAYS)

    for item in items:
        name = item.get("full_name", "")
        html_url = item.get("html_url", "")
        description = item.get("description") or ""
        created_at_str = item.get("created_at", "")
        stars = item.get("stargazers_count", 0)
        topics = item.get("topics", [])

        if not name or not html_url:
            continue

        if stars < MIN_STARS:
            continue

        if created_at_str:
            try:
                created_dt = datetime.fromisoformat(
                    created_at_str.replace("Z", "+00:00")
                )
                if created_dt < cutoff:
                    continue
            except ValueError:
                pass

        hit = RawHit(
            source_id=source.name,
            source_name=source.name,
            title=name,
            url=html_url,
            snippet=description[:500] if description else "",
            published_at=created_at_str,
            detector_hint=source.detector_hint,
            extra={"stars": stars, "topics": topics, "language": item.get("language")},
        )

        if is_seen_fn and is_seen_fn(hit.content_hash):
            continue

        hits.append(hit)

    logger.info(f"GitHub {source.name}: {len(hits)} new hits from {len(items)} results")
    return hits
