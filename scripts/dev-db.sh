#!/usr/bin/env bash
# Development PostgreSQL in Docker (127.0.0.1:${KIVI_PG_PORT:-5433}).
#   scripts/dev-db.sh start | stop | status | psql [args] | reset
set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")/.."

case "${1:-start}" in
  start)
    docker compose up -d --wait db
    ;;
  stop) docker compose stop db ;;
  status) docker compose ps db ;;
  psql) shift; exec docker compose exec -T db psql -U kivi -d kivi "$@" ;;
  reset)
    docker compose down -v
    docker compose up -d --wait db
    ;;
  *) echo "usage: $0 start|stop|status|psql|reset" >&2; exit 2 ;;
esac
