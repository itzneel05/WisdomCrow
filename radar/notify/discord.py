import logging
import re
from datetime import datetime, timezone
from typing import Any

import requests
from bs4 import BeautifulSoup

from radar.core.models import Category, Confidence

logger = logging.getLogger(__name__)

REQUEST_TIMEOUT = 15

CHANNEL_MAP: dict[str, str] = {
    "ctf": "ctf",
    "bug_bounty": "bounty",
    "free_cert": "freebies",
    "hackathon": "hackathons",
    "early_bird": "freebies",
    "arcade": "ctf",
    "open_source": "all-raw",
    "unknown": "all-raw",
    "needs_review": "all-raw",
}

CATEGORY_EMOJIS = {
    "ctf": "\U0001f3f0",
    "bug_bounty": "\U0001f4b0",
    "free_cert": "\U0001f393",
    "hackathon": "\U0001f3c6",
    "early_bird": "\U0001f426",
    "arcade": "\U0001f3ae",
    "open_source": "\U0001f4e6",
    "unknown": "\u2753",
    "needs_review": "\U0001f50d",
}

CONFIDENCE_COLORS = {
    "high": 0x2ECC71,
    "medium": 0xF1C40F,
    "low": 0x95A5A6,
}


def _build_embed(row: dict[str, Any]) -> dict[str, Any]:
    category_raw = row.get("category", "unknown")
    category_label = category_raw.replace("_", " ").title()
    cat_emoji = CATEGORY_EMOJIS.get(category_raw, "")
    color = CONFIDENCE_COLORS.get(row.get("confidence", "low"), 0x95A5A6)
    title = row.get("title", "")[:256]
    url = row.get("url", "")
    snippet = row.get("snippet", "")
    if snippet:
        snippet = BeautifulSoup(snippet, "html.parser").get_text()
        snippet = re.sub(r"\s+", " ", snippet).strip()
    tags = row.get("tags") or []
    event_date = row.get("event_date") or ""
    deadline = row.get("deadline_date") or ""

    embed: dict[str, Any] = {
        "title": f"{cat_emoji} {category_label} | {title}",
        "url": url,
        "color": color,
        "description": (snippet[:400] + "\u2026")
        if len(snippet) > 400
        else (snippet or None),
        "fields": [
            {
                "name": "Category",
                "value": f"{cat_emoji} {category_label}",
                "inline": True,
            },
        ],
        "footer": {"text": "WisdomCrow \u2022 Cyber Opportunity Radar"},
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }

    if tags:
        tags_str = ", ".join(f"`{t}`" for t in tags[:8])
        embed["fields"].append(
            {"name": "Tags", "value": tags_str[:100], "inline": False}
        )

    if event_date:
        embed["fields"].append(
            {"name": ":calendar: Event Date", "value": str(event_date), "inline": True}
        )

    if deadline:
        embed["fields"].append(
            {"name": ":alarm_clock: Deadline", "value": str(deadline), "inline": True}
        )

    embed["fields"].append(
        {
            "name": "Confidence",
            "value": row.get("confidence", "low").upper(),
            "inline": True,
        }
    )

    return embed


def _send_webhook(webhook_url: str, embed: dict[str, Any], opp_id: int) -> str | None:
    url = f"{webhook_url}?wait=true"
    payload = {"embeds": [embed]}

    try:
        resp = requests.post(url, json=payload, timeout=REQUEST_TIMEOUT)
        resp.raise_for_status()
        data = resp.json()
        message_id = str(data.get("id", ""))
        if message_id:
            logger.info(f"Sent alert for opp:{opp_id} \u2014 Discord msg {message_id}")
        return message_id
    except requests.RequestException as e:
        logger.warning(f"Discord webhook failed for opp:{opp_id}: {e}")
        return None


def send_discord_alerts(
    db: Any,
    webhook_urls: dict[str, str],
    max_per_run: int = 20,
    max_per_category: int = 10,
) -> list[int]:
    rows = db.get_unalerted_opportunities()
    if not rows:
        logger.info("No unalerted opportunities to send")
        return []

    rows.sort(
        key=lambda r: list(CONFIDENCE_COLORS.keys()).index(r.get("confidence", "low"))
    )

    sent_ids: list[int] = []
    category_counts: dict[str, int] = {}

    for row in rows[:max_per_run]:
        category_key = row.get("category", "unknown")
        channel = CHANNEL_MAP.get(category_key, "all-raw")
        webhook_url = webhook_urls.get(channel)
        if not webhook_url:
            logger.warning(
                f"No webhook configured for channel {channel} (category {category_key})"
            )
            continue

        if category_counts.get(channel, 0) >= max_per_category:
            logger.info(
                f"Max per category reached for {channel}, skipping opp:{row.get('id')}"
            )
            continue

        embed = _build_embed(row)
        opp_id = row["id"]
        message_id = _send_webhook(webhook_url, embed, opp_id)

        if message_id:
            db.log_alert(opp_id, channel, message_id, str(row.get("title", ""))[:80])
            sent_ids.append(opp_id)
            category_counts[channel] = category_counts.get(channel, 0) + 1

    if sent_ids:
        db.mark_alerted(sent_ids)
        logger.info(f"Alerted {len(sent_ids)} opportunities")

    return sent_ids


def send_system_alert(webhook_url: str, message: str) -> bool:
    payload = {
        "content": f"\u2139\ufe0f **WisdomCrow System Alert**\n{message}",
    }

    try:
        resp = requests.post(
            f"{webhook_url}?wait=true",
            json=payload,
            timeout=REQUEST_TIMEOUT,
        )
        resp.raise_for_status()
        logger.info(f"System alert sent: {message[:80]}")
        return True
    except requests.RequestException as e:
        logger.warning(f"System alert failed: {e}")
        return False
