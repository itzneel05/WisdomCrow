import hashlib
import json
import logging
from typing import Any

import requests
from bs4 import BeautifulSoup

from radar.core.models import RawHit, SourceMeta

logger = logging.getLogger(__name__)

USER_AGENT = "WisdomCrow/1.0"
REQUEST_TIMEOUT = 30
MAX_PAGE_SIZE = 1024 * 1024  # 1MB
MIN_CHANGE_INTERVAL_HOURS = 24


def _extract_text(html: str) -> str:
    soup = BeautifulSoup(html, "lxml")
    for tag in soup(["script", "style", "nav", "footer", "header", "aside"]):
        tag.decompose()
    text = soup.get_text(separator=" ", strip=True)
    return text


def _hash_content(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()


def _get_stored_hash(source_name: str, db: Any = None) -> str | None:
    if db is None:
        return None
    row = db._fetchone(
        "SELECT extra FROM sources WHERE id = %s",
        (source_name,),
    )
    if row and row.get("extra"):
        try:
            extra = json.loads(row["extra"])
            return extra.get("content_hash")
        except (json.JSONDecodeError, TypeError):
            return None
    return None


def _update_stored_hash(source_name: str, content_hash: str, db: Any = None) -> None:
    if db is None:
        return
    extra = json.dumps({"content_hash": content_hash})
    db._execute(
        "UPDATE sources SET extra = %s WHERE id = %s",
        (extra, source_name),
    )
    db.conn.commit()


def fetch(source: SourceMeta, is_seen_fn: Any = None, db: Any = None) -> list[RawHit]:
    hits: list[RawHit] = []

    try:
        resp = requests.get(
            source.url,
            headers={"User-Agent": USER_AGENT},
            timeout=REQUEST_TIMEOUT,
        )
        resp.raise_for_status()
    except requests.RequestException as e:
        logger.warning(f"HTML watch fetch failed for {source.name}: {e}")
        return hits

    if len(resp.content) > MAX_PAGE_SIZE:
        logger.warning(f"Page too large for {source.name}: {len(resp.content)} bytes")
        return hits

    clean_text = _extract_text(resp.text)
    new_hash = _hash_content(clean_text)
    stored_hash = _get_stored_hash(source.name, db)

    if stored_hash and stored_hash == new_hash:
        logger.info(f"HTML watch {source.name}: no change detected")
        return hits

    first_500 = clean_text[:500]

    hit = RawHit(
        source_id=source.name,
        source_name=source.name,
        title=f"Page changed: {source.name}",
        url=source.url,
        snippet=first_500,
        published_at="",
        detector_hint=source.detector_hint,
        extra={"previous_hash": stored_hash, "new_hash": new_hash},
    )

    if is_seen_fn and is_seen_fn(hit.content_hash):
        return hits

    hits.append(hit)

    _update_stored_hash(source.name, new_hash, db)
    logger.info(
        f"HTML watch {source.name}: change detected, new hash {new_hash[:12]}..."
    )
    return hits
