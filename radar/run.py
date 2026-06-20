#!/usr/bin/env python3
import argparse
import logging
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import requests

from radar.core.config import Config
from radar.core.models import Opportunity, RawHit, SourceMeta
from radar.core.storage import Database

logger = logging.getLogger("wisdomcrow")

ADAPTERS = {}
DETECTORS = []


def _import_modules():
    global ADAPTERS, DETECTORS
    from radar.adapters import (
        rss,
        sitemap,
        github_search,
        github_org,
        reddit,
        html_watch,
    )

    ADAPTERS = {
        "rss": rss,
        "sitemap": sitemap,
        "github": github_search,
        "github_org": github_org,
        "reddit": reddit,
        "html_watch": html_watch,
    }

    from radar.detectors import (
        ctf,
        bug_bounty,
        hackathon,
        free_cert,
        early_bird,
        arcade,
        open_source,
    )

    DETECTORS = [
        ctf,
        bug_bounty,
        hackathon,
        free_cert,
        early_bird,
        arcade,
        open_source,
    ]


def setup_logging(data_dir: str) -> None:
    log_dir = Path(data_dir) / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        handlers=[
            logging.FileHandler(log_dir / "radar.log"),
            logging.StreamHandler(sys.stdout),
        ],
    )


def ping_healthcheck(url: str, status: str = "") -> None:
    if not url:
        return
    try:
        endpoint = url.rstrip("/")
        if status == "fail":
            endpoint += "/fail"
        requests.get(endpoint, timeout=10)
    except requests.RequestException as e:
        logger.warning(f"Healthcheck ping failed: {e}")


def run_source(source_row: dict[str, Any], db: Database) -> list[RawHit]:
    source_type = source_row["type"]
    adapter = ADAPTERS.get(source_type)
    if not adapter:
        logger.warning(f"No adapter for source type: {source_type}")
        return []

    sm = SourceMeta(
        name=source_row["name"],
        source_type=source_row["type"],
        url=source_row["url"],
        cadence=source_row.get("cadence", "daily"),
        detector_hint=source_row.get("detector_hint", ""),
        watch_patterns=source_row.get("watch_patterns", []),
        enabled=source_row.get("enabled", True),
    )

    try:
        kwargs = {"source": sm, "is_seen_fn": db.is_seen}
        if source_type == "html_watch":
            hits = adapter.fetch(**kwargs, db=db)
        else:
            hits = adapter.fetch(**kwargs)

        db.update_source_status(sm.name, "ok", 0, 0)
        db.log_source_run(sm.name, "success", len(hits))
        return hits
    except Exception as e:
        logger.error(f"Source {sm.name} failed: {e}", exc_info=True)
        db.update_source_status(sm.name, "error", 1, 0)
        db.log_source_run(sm.name, "error", 0, str(e)[:500])
        return []


def detect_hit(hit: RawHit) -> Opportunity | None:
    for det in DETECTORS:
        result = det.detect(hit)
        if result.matched:
            opp = Opportunity(
                title=hit.title,
                url=hit.url,
                category=result.category,
                confidence=result.confidence,
                snippet=hit.snippet,
                tags=result.tags,
                canonical_key=hit.content_hash,
            )
            opp.apply_cross_cut_tags()
            return opp
    return None


def cmd_scan(config: Config, cadence: str) -> None:
    hc_url = config.healthcheck_url
    ping_healthcheck(hc_url, "start")
    start_time = time.time()

    with Database(config.database_url) as db:
        db.cleanup_old_raw_hits()

        sources = db.get_active_sources()
        cadence_sources = [s for s in sources if s.get("cadence", "daily") == cadence]

        if not cadence_sources:
            logger.info(f"No active sources for cadence '{cadence}'")
            ping_healthcheck(hc_url)
            return

        logger.info(f"Scanning {len(cadence_sources)} sources at cadence '{cadence}'")

        total_hits = 0
        total_opps = 0

        for src in cadence_sources:
            hits = run_source(src, db)
            total_hits += len(hits)

            for hit in hits:
                raw_id = db.insert_raw_hit(hit)
                if raw_id is None:
                    continue

                opp = detect_hit(hit)
                if opp is not None:
                    opp_id = db.insert_opportunity(opp)
                    if opp_id is not None:
                        total_opps += 1
                        db.mark_hit_processed(raw_id)
                    else:
                        existing = db.opportunity_exists(opp.canonical_key)
                        if existing:
                            db.update_last_seen(opp.canonical_key)
                            db.mark_hit_processed(raw_id)

        logger.info(f"Scan complete: {total_hits} hits, {total_opps} new opportunities")

        from radar.notify.discord import send_discord_alerts

        webhooks = {
            "ctf": config.get_webhook_for_channel("ctf"),
            "bounty": config.get_webhook_for_channel("bounty"),
            "freebies": config.get_webhook_for_channel("freebies"),
            "hackathons": config.get_webhook_for_channel("hackathons"),
            "all-raw": config.get_webhook_for_channel("all-raw"),
        }

        sent = send_discord_alerts(
            db,
            webhooks,
            max_per_run=config.max_alerts_per_run,
            max_per_category=config.max_alerts_per_category,
        )

        from radar.notify.report import generate_report

        if cadence in ("daily", "weekly") or sent:
            report_opps = db.get_opportunities_for_report(days_back=1)
            generate_report(
                report_opps,
                Path(config.data_dir) / "reports",
                report_type=cadence,
            )

    elapsed = time.time() - start_time
    logger.info(f"Run finished in {elapsed:.1f}s")
    ping_healthcheck(hc_url)


def cmd_init_db(config: Config) -> None:
    with Database(config.database_url) as db:
        db.init_schema()
    print("Database schema initialized successfully")


def cmd_feedback(config: Config, opp_id: int, label: str, comment: str) -> None:
    valid_labels = {"good", "false_positive", "missed", "duplicate"}
    if label not in valid_labels:
        print(f"Invalid label. Choose from: {', '.join(sorted(valid_labels))}")
        sys.exit(1)
    with Database(config.database_url) as db:
        db.insert_feedback(opp_id, label, comment)
    print(f"Feedback recorded for opportunity {opp_id}: {label}")


def cmd_feedback_review(config: Config) -> None:
    with Database(config.database_url) as db:
        items = db.get_feedback_pending()
    if not items:
        print("No pending feedback items")
        return
    print(f"{'ID':<6} {'Title':<50} {'Category':<15} {'Confidence':<10}")
    print("-" * 85)
    for item in items:
        title = item["title"][:48] + ".." if len(item["title"]) > 48 else item["title"]
        print(
            f"{item['id']:<6} {title:<50} {item['category']:<15} {item['confidence']:<10}"
        )


def cmd_version(config: Config) -> None:
    print(f"WisdomCrow v{config.app_version}")


def cmd_sources(config: Config) -> None:
    with Database(config.database_url) as db:
        sources = db.get_active_sources()
    if not sources:
        print("No active sources configured")
        return
    print(f"{'Name':<30} {'Type':<12} {'Cadence':<10} {'Status':<10} {'Errors':<8}")
    print("-" * 75)
    for s in sources:
        status = s.get("last_status", "never")
        errors = s.get("error_count", 0)
        print(
            f"{s['name']:<30} {s['type']:<12} {s.get('cadence', 'daily'):<10} {status:<10} {errors:<8}"
        )


def cmd_sync_sources(config: Config) -> None:
    source_metas = [SourceMeta.from_dict(s) for s in config.get_sources()]
    with Database(config.database_url) as db:
        db.sync_sources(source_metas)
    print(f"Synced {len(source_metas)} sources to database")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="WisdomCrow - Cyber Opportunity Radar")
    parser.add_argument(
        "--cadence",
        choices=["fast", "daily", "weekly"],
        default="fast",
        help="Scan cadence",
    )
    parser.add_argument(
        "--init-db", action="store_true", help="Initialize database schema"
    )
    parser.add_argument("--version", action="store_true", help="Show version")
    parser.add_argument(
        "--sources", action="store_true", help="List configured sources"
    )

    sub = parser.add_subparsers(dest="command")
    feedback = sub.add_parser("feedback", help="Record feedback for opportunity")
    feedback.add_argument("--id", type=int, required=True, help="Opportunity ID")
    feedback.add_argument(
        "--label",
        choices=["good", "false_positive", "missed", "duplicate"],
        required=True,
        help="Feedback label",
    )
    feedback.add_argument("--comment", default="", help="Optional comment")
    feedback.add_argument(
        "--review", action="store_true", help="Show pending feedback items"
    )

    return parser


def main() -> None:
    _import_modules()

    config = Config(
        Path(__file__).parent.parent / "config" / "settings.yaml",
        Path(__file__).parent.parent / "config" / "sources.yaml",
    )
    setup_logging(config.data_dir)
    parser = build_parser()
    args = parser.parse_args()

    if args.init_db:
        cmd_init_db(config)
        return

    if args.version:
        cmd_version(config)
        return

    if args.sources:
        cmd_sources(config)
        return

    if args.command == "feedback":
        if args.review:
            cmd_feedback_review(config)
        else:
            cmd_feedback(config, args.id, args.label, args.comment)
        return

    cmd_sync_sources(config)
    cmd_scan(config, args.cadence)


if __name__ == "__main__":
    main()
