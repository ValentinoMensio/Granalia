#!/usr/bin/env bash
set -euo pipefail

BACKUP_DIR="${GRANALIA_BACKUP_DIR:-$HOME/backups/granalia}"
CONTAINER="${GRANALIA_POSTGRES_CONTAINER:-deploy-postgres-1}"
DB_NAME="${POSTGRES_DB:-granalia}"
DB_USER="${POSTGRES_USER:-granalia}"
KEEP_DAYS="${GRANALIA_BACKUP_KEEP_DAYS:-30}"

mkdir -p "$BACKUP_DIR"

timestamp="$(date +%Y-%m-%d_%H-%M-%S)"
backup_file="$BACKUP_DIR/granalia-$timestamp.dump"

docker exec "$CONTAINER" pg_dump -U "$DB_USER" -d "$DB_NAME" -F c > "$backup_file"

find "$BACKUP_DIR" -name "granalia-*.dump" -type f -mtime +"$KEEP_DAYS" -delete

printf 'Backup creado: %s\n' "$backup_file"
