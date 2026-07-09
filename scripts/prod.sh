#!/usr/bin/env sh
set -eu

ENV_FILE="${ENV_FILE:-.env.production}"
COMPOSE_FILE="${COMPOSE_FILE:-docker-compose.prod.yml}"

if [ ! -f "$ENV_FILE" ]; then
  echo "Missing $ENV_FILE. Copy .env.production.example and set production secrets first." >&2
  exit 1
fi

compose() {
  docker compose --env-file "$ENV_FILE" -f "$COMPOSE_FILE" "$@"
}

env_value() {
  key="$1"
  sed -n "s/^${key}=//p" "$ENV_FILE" | tail -n 1
}

case "${1:-help}" in
  up)
    compose up -d
    ;;
  build)
    compose build
    ;;
  restart)
    if [ "$#" -gt 1 ]; then
      compose restart "$2"
    else
      compose restart
    fi
    ;;
  down)
    compose down
    ;;
  ps)
    compose ps
    ;;
  logs-api)
    compose logs api --tail "${2:-120}"
    ;;
  logs-web)
    compose logs web --tail "${2:-80}"
    ;;
  migrate)
    compose exec api python -m alembic upgrade head
    ;;
  validate-db)
    compose exec postgres psql -U verigraph -d verigraph -c "SELECT current_user, current_database();"
    compose exec postgres psql -U verigraph -d verigraph -c "SELECT tablename FROM pg_tables WHERE schemaname='public' ORDER BY tablename;"
    ;;
  validate-api)
    curl -i http://127.0.0.1:8000/api/v1/health
    ;;
  login)
    if [ "$#" -lt 3 ]; then
      echo "Usage: $0 login EMAIL PASSWORD" >&2
      exit 1
    fi
    curl -i -X POST "http://127.0.0.1:8000/api/v1/auth/login" \
      -H "Content-Type: application/json" \
      --data-raw "{\"email\":\"$2\",\"password\":\"$3\"}"
    ;;
  sync-postgres-password)
    postgres_password="$(env_value POSTGRES_PASSWORD)"
    if [ -z "$postgres_password" ]; then
      echo "POSTGRES_PASSWORD is empty in $ENV_FILE." >&2
      exit 1
    fi
    compose exec postgres psql -U verigraph -d verigraph \
      -v new_password="$postgres_password" \
      -c "ALTER USER verigraph WITH PASSWORD :'new_password';"
    compose restart api
    ;;
  help|*)
    cat <<EOF
Usage: $0 COMMAND

Commands:
  up                       Start production stack with $ENV_FILE
  build                    Build production images
  restart [service]         Restart all services or one service
  down                     Stop production stack
  ps                       Show service status
  logs-api [lines]          Show API logs
  logs-web [lines]          Show web logs
  migrate                  Run Alembic migrations
  validate-db              Check Postgres user/database and table list
  validate-api             Check API health endpoint
  login EMAIL PASSWORD     Test login endpoint
  sync-postgres-password   Set DB user password from POSTGRES_PASSWORD and restart API
EOF
    ;;
esac
