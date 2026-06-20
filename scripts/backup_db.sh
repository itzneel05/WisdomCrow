#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/.."

BACKUP_DIR="data/backups"
TIMESTAMP=$(date +%Y%m%d_%H%M%S)
mkdir -p "$BACKUP_DIR"

PG_DUMP_URL="${DATABASE_URL}"

if [ -z "$PG_DUMP_URL" ]; then
    echo "ERROR: DATABASE_URL not set"
    exit 1
fi

pg_dump "$PG_DUMP_URL" --no-owner --no-acl \
    --file="$BACKUP_DIR/wisdomcrow_$TIMESTAMP.sql"

gzip "$BACKUP_DIR/wisdomcrow_$TIMESTAMP.sql"

echo "Backup saved: $BACKUP_DIR/wisdomcrow_$TIMESTAMP.sql.gz"

find "$BACKUP_DIR" -name "*.sql.gz" -mtime +30 -delete
