#!/bin/sh
# Nightly Postgres dump. Keeps 14 days.
set -eu
cd "$(dirname "$0")/.."
mkdir -p /var/backups/smart-docs
docker compose exec -T db pg_dump -U "${POSTGRES_USER:-sd}" "${POSTGRES_DB:-sd}" | gzip > "/var/backups/smart-docs/$(date +%F).sql.gz"
find /var/backups/smart-docs -name '*.sql.gz' -mtime +14 -delete
