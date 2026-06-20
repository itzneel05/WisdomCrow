import logging
from datetime import datetime, timezone, timedelta
from typing import Any
from xml.etree import ElementTree as ET

import requests
from bs4 import BeautifulSoup

from radar.core.models import RawHit, SourceMeta

logger = logging.getLogger(__name__)

USER_AGENT = "WisdomCrow/1.0"
REQUEST_TIMEOUT = 30
MAX_SITEMAP_SIZE = 5 * 1024 * 1024

CADENCE_MAX_AGE = {
    "fast": timedelta(days=7),
    "daily": timedelta(days=30),
    "weekly": timedelta(days=90),
}

SITEMAP_NS = "http://www.sitemaps.org/schemas/sitemap/0.9"


def _parse_date(date_str: str | None) -> datetime | None:
    if not date_str:
        return None
    for fmt in ("%Y-%m-%dT%H:%M:%S%z", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d"):
        try:
            return datetime.strptime(date_str.strip(), fmt).replace(tzinfo=timezone.utc)
        except ValueError:
            continue
    return None


def _matches_watch_patterns(url: str, patterns: list[str]) -> bool:
    if not patterns:
        return True
    url_lower = url.lower()
    return any(p.lower() in url_lower for p in patterns)


def _fetch_sitemap_urls(url: str) -> list[str]:
    try:
        resp = requests.get(
            url, headers={"User-Agent": USER_AGENT}, timeout=REQUEST_TIMEOUT
        )
        resp.raise_for_status()
        if len(resp.content) > MAX_SITEMAP_SIZE:
            logger.warning(f"Sitemap too large ({len(resp.content)} bytes): {url}")
            return []
    except requests.RequestException as e:
        logger.warning(f"Sitemap fetch failed for {url}: {e}")
        return []

    urls: list[str] = []
    try:
        root = ET.fromstring(resp.content)
    except ET.ParseError as e:
        logger.warning(f"Failed to parse sitemap XML {url}: {e}")
        return []

    sitemap_entries = root.findall(f"{{{SITEMAP_NS}}}sitemap/{{{SITEMAP_NS}}}loc")
    if sitemap_entries:
        for loc in sitemap_entries:
            child_urls = _fetch_sitemap_urls(loc.text.strip())
            urls.extend(child_urls)
    else:
        for url_elem in root.findall(f"{{{SITEMAP_NS}}}url"):
            loc_elem = url_elem.find(f"{{{SITEMAP_NS}}}loc")
            if loc_elem is not None:
                urls.append(loc_elem.text.strip())

    return urls


def fetch(source: SourceMeta, is_seen_fn: Any = None) -> list[RawHit]:
    hits: list[RawHit] = []
    all_urls = _fetch_sitemap_urls(source.url)

    if not all_urls:
        logger.info(f"No URLs found in sitemap {source.name}")
        return hits

    max_age = CADENCE_MAX_AGE.get(source.cadence.value, timedelta(days=30))
    cutoff = datetime.now(timezone.utc) - max_age

    for url in all_urls:
        if not _matches_watch_patterns(url, source.watch_patterns):
            continue

        title = (
            url.rstrip("/").split("/")[-1].replace("-", " ").replace("_", " ").title()
        )
        if not title:
            continue

        hit = RawHit(
            source_id=source.name,
            source_name=source.name,
            title=title,
            url=url,
            snippet="",
            published_at="",
            detector_hint=source.detector_hint,
        )

        if is_seen_fn and is_seen_fn(hit.content_hash):
            continue

        hits.append(hit)

    logger.info(
        f"Sitemap {source.name}: {len(hits)} new hits from {len(all_urls)} URLs"
    )
    return hits
