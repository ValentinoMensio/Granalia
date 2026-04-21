#!/bin/sh
set -eu

: "${POSTGRES_DB:?POSTGRES_DB is required}"
: "${POSTGRES_USER:?POSTGRES_USER is required}"
: "${POSTGRES_PASSWORD:?POSTGRES_PASSWORD is required}"

BACKUP_DIR="${GRANALIA_BACKUP_DIR:-./backups}"
RETENTION_DAYS="${GRANALIA_BACKUP_RETENTION_DAYS:-14}"
TIMESTAMP="$(date -u +%Y%m%dT%H%M%SZ)"
FILE="$BACKUP_DIR/granalia-$TIMESTAMP.sql.gz"

mkdir -p "$BACKUP_DIR"

PGPASSWORD="$POSTGRES_PASSWORD" pg_dump \
  --host "${POSTGRES_HOST:-127.0.0.1}" \
  --port "${POSTGRES_PORT:-5432}" \
  --username "$POSTGRES_USER" \
  --dbname "$POSTGRES_DB" \
  --clean \
  --if-exists | gzip > "$FILE"

find "$BACKUP_DIR" -type f -name 'granalia-*.sql.gz' -mtime +"$RETENTION_DAYS" -delete

printf 'backup created: %s\n' "$FILE"
