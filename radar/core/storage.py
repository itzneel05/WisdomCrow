from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

import psycopg2
import psycopg2.extras
from psycopg2.extras import RealDictCursor

from .models import Opportunity, RawHit, SourceMeta

logger = logging.getLogger(__name__)

_SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS sources (
    id                TEXT PRIMARY KEY,
    name              TEXT NOT NULL,
    type              TEXT NOT NULL,
    url               TEXT,
    detector_hint     TEXT,
    enabled           BOOLEAN DEFAULT TRUE,
    cadence           TEXT DEFAULT 'daily',
    last_checked_at   TIMESTAMPTZ,
    last_status       TEXT,
    error_count       INTEGER DEFAULT 0,
    consecutive_empty INTEGER DEFAULT 0,
    total_hits        INTEGER DEFAULT 0,
    false_positives   INTEGER DEFAULT 0,
    interested        INTEGER DEFAULT 0,
    applied           INTEGER DEFAULT 0,
    signal_score      FLOAT DEFAULT NULL,
    extra             TEXT DEFAULT ''
);

CREATE TABLE IF NOT EXISTS raw_hits (
    id              SERIAL PRIMARY KEY,
    source_id       TEXT NOT NULL REFERENCES sources(id),
    title           TEXT,
    url             TEXT,
    canonical_url   TEXT,
    snippet         TEXT DEFAULT '',
    content_hash    TEXT,
    published_at    TIMESTAMPTZ,
    fetched_at      TIMESTAMPTZ DEFAULT NOW(),
    is_processed    BOOLEAN DEFAULT FALSE
);

CREATE TABLE IF NOT EXISTS opportunities (
    id              SERIAL PRIMARY KEY,
    canonical_key   TEXT UNIQUE NOT NULL,
    title           TEXT NOT NULL,
    url             TEXT NOT NULL,
    category        TEXT NOT NULL,
    confidence      TEXT DEFAULT 'medium',
    status          TEXT DEFAULT 'new',
    snippet         TEXT DEFAULT '',
    tags            TEXT[] DEFAULT '{}',
    reasons         TEXT[] DEFAULT '{}',
    event_date      DATE,
    deadline_date   DATE,
    is_past         BOOLEAN DEFAULT FALSE,
    first_seen_at   TIMESTAMPTZ DEFAULT NOW(),
    last_seen_at    TIMESTAMPTZ DEFAULT NOW(),
    alerted         BOOLEAN DEFAULT FALSE,
    notes           TEXT DEFAULT ''
);

CREATE TABLE IF NOT EXISTS alerts (
    id              SERIAL PRIMARY KEY,
    opportunity_id  INTEGER NOT NULL REFERENCES opportunities(id),
    channel         TEXT,
    message_id      TEXT,
    sent_at         TIMESTAMPTZ DEFAULT NOW(),
    message_preview TEXT
);

CREATE TABLE IF NOT EXISTS feedback (
    id              SERIAL PRIMARY KEY,
    opportunity_id  INTEGER NOT NULL REFERENCES opportunities(id),
    rating          INTEGER,
    label           TEXT,
    comment         TEXT DEFAULT '',
    source          TEXT DEFAULT 'cli',
    created_at      TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS source_runs (
    id              SERIAL PRIMARY KEY,
    source_id       TEXT NOT NULL REFERENCES sources(id),
    started_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    finished_at     TIMESTAMPTZ,
    status          TEXT,
    hits_found      INTEGER DEFAULT 0,
    error_message   TEXT DEFAULT ''
);
"""

_INDEXES_SQL = """
CREATE INDEX IF NOT EXISTS idx_raw_hits_hash ON raw_hits(content_hash);
CREATE INDEX IF NOT EXISTS idx_raw_hits_processed ON raw_hits(is_processed);
CREATE INDEX IF NOT EXISTS idx_opportunities_key ON opportunities(canonical_key);
CREATE INDEX IF NOT EXISTS idx_opportunities_category ON opportunities(category);
CREATE INDEX IF NOT EXISTS idx_opportunities_status ON opportunities(status);
CREATE INDEX IF NOT EXISTS idx_opportunities_alerted ON opportunities(alerted);
CREATE INDEX IF NOT EXISTS idx_opportunities_tags ON opportunities USING GIN(tags);
CREATE INDEX IF NOT EXISTS idx_feedback_opportunity ON feedback(opportunity_id);
CREATE INDEX IF NOT EXISTS idx_source_runs_source ON source_runs(source_id);
"""

_RAW_HITS_CLEANUP_SQL = """
DELETE FROM raw_hits WHERE fetched_at < NOW() - INTERVAL '180 days';
"""


class Database:
    def __init__(self, dsn: str) -> None:
        self.dsn = dsn
        self.conn: psycopg2.extensions.connection | None = None

    def __enter__(self) -> Database:
        self.connect()
        return self

    def __exit__(self, *args: Any) -> None:
        self.close()

    def connect(self) -> None:
        self.conn = psycopg2.connect(self.dsn, cursor_factory=RealDictCursor)
        self.conn.autocommit = False

    def close(self) -> None:
        if self.conn:
            self.conn.commit()
            self.conn.close()
            self.conn = None

    def _execute(self, sql: str, params: tuple | None = None) -> RealDictCursor | None:
        if not self.conn:
            raise RuntimeError("Database not connected")
        cur = self.conn.cursor()
        try:
            cur.execute(sql, params)
            return cur
        except Exception:
            self.conn.rollback()
            raise

    def _fetchone(self, sql: str, params: tuple | None = None) -> dict[str, Any] | None:
        cur = self._execute(sql, params)
        if cur is None:
            return None
        row = cur.fetchone()
        cur.close()
        return dict(row) if row else None

    def _fetchall(self, sql: str, params: tuple | None = None) -> list[dict[str, Any]]:
        cur = self._execute(sql, params)
        if cur is None:
            return []
        rows = cur.fetchall()
        cur.close()
        return [dict(r) for r in rows]

    def init_schema(self) -> None:
        self._execute(_SCHEMA_SQL)
        self._execute(_INDEXES_SQL)
        self.conn.commit()
        logger.info("Database schema initialized")

    def cleanup_old_raw_hits(self) -> int:
        cur = self._execute(_RAW_HITS_CLEANUP_SQL)
        deleted = cur.rowcount if cur else 0
        self.conn.commit()
        if deleted > 0:
            logger.info(f"Cleaned up {deleted} old raw_hits")
        return deleted

    def sync_sources(self, source_metas: list[SourceMeta]) -> None:
        existing = {
            r["id"]: r for r in self._fetchall("SELECT id, enabled FROM sources")
        }
        for sm in source_metas:
            if sm.name in existing:
                if not sm.enabled and existing[sm.name]["enabled"]:
                    self._execute(
                        "UPDATE sources SET enabled = FALSE WHERE id = %s", (sm.name,)
                    )
            else:
                self._execute(
                    """INSERT INTO sources (id, name, type, url, detector_hint, enabled, cadence)
                       VALUES (%s, %s, %s, %s, %s, %s, %s)
                       ON CONFLICT (id) DO NOTHING""",
                    (
                        sm.name,
                        sm.name,
                        sm.source_type.value,
                        sm.url,
                        sm.detector_hint,
                        sm.enabled,
                        sm.cadence.value,
                    ),
                )
        defined_names = {sm.name for sm in source_metas}
        for sid, row in existing.items():
            if sid not in defined_names and row["enabled"]:
                self._execute(
                    "UPDATE sources SET enabled = FALSE WHERE id = %s", (sid,)
                )
        self.conn.commit()

    def get_active_sources(self) -> list[dict[str, Any]]:
        return self._fetchall(
            "SELECT * FROM sources WHERE enabled = TRUE ORDER BY name"
        )

    def update_source_status(
        self, source_id: str, status: str, error_count: int, consecutive_empty: int
    ) -> None:
        self._execute(
            """UPDATE sources
               SET last_checked_at = NOW(), last_status = %s,
                   error_count = %s, consecutive_empty = %s
               WHERE id = %s""",
            (status, error_count, consecutive_empty, source_id),
        )
        if error_count >= 5:
            self._execute(
                "UPDATE sources SET enabled = FALSE WHERE id = %s", (source_id,)
            )
            logger.warning(
                f"Auto-disabled source {source_id} after {error_count} errors"
            )
        self.conn.commit()

    def log_source_run(
        self, source_id: str, status: str, hits_found: int, error_message: str = ""
    ) -> None:
        self._execute(
            """INSERT INTO source_runs (source_id, finished_at, status, hits_found, error_message)
               VALUES (%s, NOW(), %s, %s, %s)""",
            (source_id, status, hits_found, error_message),
        )
        self.conn.commit()

    def is_seen(self, content_hash: str) -> bool:
        row = self._fetchone(
            "SELECT 1 FROM raw_hits WHERE content_hash = %s LIMIT 1", (content_hash,)
        )
        return row is not None

    def insert_raw_hit(self, hit: RawHit) -> int | None:
        if self.is_seen(hit.content_hash):
            return None
        cur = self._execute(
            """INSERT INTO raw_hits (source_id, title, url, canonical_url, snippet, content_hash, published_at)
               VALUES (%s, %s, %s, %s, %s, %s, %s)
               RETURNING id""",
            (
                hit.source_id,
                hit.title,
                hit.url,
                hit.canonical_url,
                hit.snippet,
                hit.content_hash,
                hit.published_at or None,
            ),
        )
        self._execute(
            "UPDATE sources SET total_hits = total_hits + 1 WHERE id = %s",
            (hit.source_id,),
        )
        self.conn.commit()
        row = cur.fetchone() if cur else None
        return row["id"] if row else None

    def get_unprocessed_hits(self) -> list[dict[str, Any]]:
        return self._fetchall(
            "SELECT * FROM raw_hits WHERE is_processed = FALSE ORDER BY fetched_at ASC LIMIT 500"
        )

    def mark_hit_processed(self, hit_id: int) -> None:
        self._execute(
            "UPDATE raw_hits SET is_processed = TRUE WHERE id = %s", (hit_id,)
        )
        self.conn.commit()

    def opportunity_exists(self, canonical_key: str) -> bool:
        row = self._fetchone(
            "SELECT 1 FROM opportunities WHERE canonical_key = %s LIMIT 1",
            (canonical_key,),
        )
        return row is not None

    def insert_opportunity(self, opp: Opportunity) -> int | None:
        cur = self._execute(
            """INSERT INTO opportunities
               (canonical_key, title, url, category, confidence, snippet, tags, event_date, deadline_date, is_past)
               VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
               ON CONFLICT (canonical_key) DO NOTHING
               RETURNING id""",
            (
                opp.canonical_key,
                opp.title,
                opp.url,
                opp.category.value,
                opp.confidence.value,
                opp.snippet,
                opp.tags,
                opp.event_date or None,
                opp.deadline_date or None,
                opp.is_past,
            ),
        )
        self.conn.commit()
        if cur is None:
            return None
        row = cur.fetchone()
        return row["id"] if row else None

    def update_last_seen(self, canonical_key: str) -> None:
        self._execute(
            "UPDATE opportunities SET last_seen_at = NOW() WHERE canonical_key = %s",
            (canonical_key,),
        )
        self.conn.commit()

    def get_unalerted_opportunities(self) -> list[dict[str, Any]]:
        return self._fetchall(
            "SELECT * FROM opportunities WHERE alerted = FALSE AND is_past = FALSE ORDER BY first_seen_at ASC"
        )

    def mark_alerted(self, opp_ids: list[int]) -> None:
        if not opp_ids:
            return
        self._execute(
            "UPDATE opportunities SET alerted = TRUE WHERE id = ANY(%s)",
            (opp_ids,),
        )
        self.conn.commit()

    def log_alert(
        self, opportunity_id: int, channel: str, message_id: str, preview: str
    ) -> None:
        self._execute(
            """INSERT INTO alerts (opportunity_id, channel, message_id, message_preview)
               VALUES (%s, %s, %s, %s)""",
            (opportunity_id, channel, message_id, preview),
        )
        self.conn.commit()

    def insert_feedback(
        self, opportunity_id: int, label: str, comment: str = "", source: str = "cli"
    ) -> None:
        self._execute(
            """INSERT INTO feedback (opportunity_id, label, comment, source)
               VALUES (%s, %s, %s, %s)""",
            (opportunity_id, label, comment, source),
        )
        status_map = {
            "good": "interested",
            "false_positive": "false_positive",
            "missed": "missed",
            "duplicate": "ignored",
        }
        new_status = status_map.get(label)
        if new_status:
            self._execute(
                "UPDATE opportunities SET status = %s WHERE id = %s",
                (new_status, opportunity_id),
            )
        self.conn.commit()
        self._recalculate_signal_score(opportunity_id)

    def _recalculate_signal_score(self, opportunity_id: int) -> None:
        row = self._fetchone(
            "SELECT source_id FROM raw_hits WHERE id = (SELECT MIN(raw_hits.id) FROM raw_hits JOIN opportunities ON ...)"
        )
        if not row:
            return
        source_id = row["source_id"]
        self._execute(
            """UPDATE sources SET
               false_positives = (SELECT COUNT(*) FROM feedback JOIN opportunities ON feedback.opportunity_id = opportunities.id WHERE opportunities.canonical_key IN (SELECT canonical_key FROM opportunities WHERE id IN (SELECT opportunity_id FROM feedback WHERE label = 'false_positive'))),
               interested = (SELECT COUNT(*) FROM feedback WHERE label = 'good'),
               signal_score = CASE WHEN total_hits > 0
                   THEN (interested + applied)::FLOAT / total_hits
                   ELSE NULL END
               WHERE id = %s""",
            (source_id,),
        )
        self.conn.commit()

    def get_opportunities_for_report(self, days_back: int = 1) -> list[dict[str, Any]]:
        return self._fetchall(
            """SELECT * FROM opportunities
               WHERE first_seen_at >= NOW() - INTERVAL '%s days'
               AND status NOT IN ('false_positive', 'ignored')
               ORDER BY category, first_seen_at DESC""",
            (days_back,),
        )

    def get_stats(self) -> dict[str, Any]:
        total_opps = self._fetchone("SELECT COUNT(*) as count FROM opportunities")
        by_category = self._fetchall(
            "SELECT category, COUNT(*) as count FROM opportunities GROUP BY category ORDER BY count DESC"
        )
        by_status = self._fetchall(
            "SELECT status, COUNT(*) as count FROM opportunities GROUP BY status ORDER BY count DESC"
        )
        today_alerts = self._fetchone(
            "SELECT COUNT(*) as count FROM alerts WHERE sent_at >= NOW() - INTERVAL '24 hours'"
        )
        return {
            "total_opportunities": total_opps["count"] if total_opps else 0,
            "by_category": {r["category"]: r["count"] for r in by_category},
            "by_status": {r["status"]: r["count"] for r in by_status},
            "alerts_today": today_alerts["count"] if today_alerts else 0,
        }

    def get_feedback_pending(self) -> list[dict[str, Any]]:
        return self._fetchall(
            """SELECT o.id, o.title, o.category, o.confidence, o.tags
               FROM opportunities o
               LEFT JOIN feedback f ON f.opportunity_id = o.id
               WHERE f.id IS NULL AND o.alerted = TRUE
               ORDER BY o.last_seen_at DESC
               LIMIT 50"""
        )
