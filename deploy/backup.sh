#!/usr/bin/env bash
# Базанын күнүмдүк резервдик көчүрмөсү: ~/backups/auto_YYYY-MM-DD.sql.gz.
# 14 күндөн эски автоматтык көчүрмөлөр өчүрүлөт (кол менен жасалгандарга тийбейт).
# Иштетүү: deploy/crontab.example
set -euo pipefail

cd "$(dirname "$0")/.."
mkdir -p ~/backups

DB_USER=$(grep -E "^DB_USER=" .env | cut -d= -f2 | tr -d '\r')
DB_NAME=$(grep -E "^DB_NAME=" .env | cut -d= -f2 | tr -d '\r')
FILE=~/backups/auto_$(date +%F).sql.gz

docker compose exec -T db pg_dump -U "${DB_USER:-postgres}" "${DB_NAME:-school}" | gzip > "$FILE.tmp"
mv "$FILE.tmp" "$FILE"

find ~/backups -name 'auto_*.sql.gz' -mtime +14 -delete
echo "$(date '+%F %T') backup ok: $FILE"
