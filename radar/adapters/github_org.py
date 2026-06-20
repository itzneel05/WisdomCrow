import logging
from datetime import datetime, timezone, timedelta
from typing import Any

import requests

from radar.core.models import RawHit, SourceMeta

logger = logging.getLogger(__name__)

USER_AGENT = "WisdomCrow/1.0"
REQUEST_TIMEOUT = 30
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

    path = source.url.rstrip("/")
    if "/" not in path.split("//")[-1]:
        path = f"{path}/repos"

    try:
        resp = requests.get(path, headers=headers, timeout=REQUEST_TIMEOUT)
        if resp.status_code == 403 and "rate limit" in resp.text.lower():
            logger.warning(f"GitHub API rate limited for {source.name}")
            return hits
        resp.raise_for_status()
    except requests.RequestException as e:
        logger.warning(f"GitHub org fetch failed for {source.name}: {e}")
        return hits

    data = resp.json()
    if isinstance(data, dict) and "message" in data:
        logger.warning(f"GitHub API error for {source.name}: {data['message']}")
        return hits

    items = data if isinstance(data, list) else []
    cutoff = datetime.now(timezone.utc) - timedelta(days=MAX_AGE_DAYS)

    for item in items:
        name = item.get("full_name", "")
        html_url = item.get("html_url", "")
        description = item.get("description") or ""
        pushed_at = item.get("pushed_at", "")
        stars = item.get("stargazers_count", 0)
        topics = item.get("topics", [])
        language = item.get("language") or ""

        if not name or not html_url:
            continue

        if pushed_at:
            try:
                pushed_dt = datetime.fromisoformat(pushed_at.replace("Z", "+00:00"))
                if pushed_dt < cutoff:
                    continue
            except ValueError:
                pass

        hit = RawHit(
            source_id=source.name,
            source_name=source.name,
            title=name,
            url=html_url,
            snippet=description[:500] if description else "",
            published_at=pushed_at,
            detector_hint=source.detector_hint,
            extra={
                "stars": stars,
                "topics": topics,
                "language": language,
                "type": item.get("fork") and "fork" or "repo",
            },
        )

        if is_seen_fn and is_seen_fn(hit.content_hash):
            continue

        hits.append(hit)

    logger.info(
        f"GitHub Org {source.name}: {len(hits)} new repos from {len(items)} results"
    )
    return hits
