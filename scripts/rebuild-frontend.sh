#!/usr/bin/env bash
# rebuild-frontend.sh — stop, clean, rebuild and restart the Artha frontend.
#
# Usage:
#   ./scripts/rebuild-frontend.sh              # rebuild frontend only (fast)
#   ./scripts/rebuild-frontend.sh --all        # rebuild all services
#   ./scripts/rebuild-frontend.sh --no-cache   # force full layer-cache purge
#   ./scripts/rebuild-frontend.sh --all --no-cache
#
# Run from the repository root (where CLAUDE.md lives).

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
COMPOSE_FILE="$REPO_ROOT/infra/docker-compose.yml"
COMPOSE="docker compose -f $COMPOSE_FILE"

# ── Parse flags ────────────────────────────────────────────────────────────────
REBUILD_ALL=false
NO_CACHE=""

for arg in "$@"; do
  case "$arg" in
    --all)       REBUILD_ALL=true ;;
    --no-cache)  NO_CACHE="--no-cache" ;;
    *)
      echo "Unknown flag: $arg"
      echo "Usage: $0 [--all] [--no-cache]"
      exit 1
      ;;
  esac
done

# ── Colour helpers ─────────────────────────────────────────────────────────────
GREEN='\033[0;32m'; YELLOW='\033[1;33m'; RED='\033[0;31m'; NC='\033[0m'
info()    { echo -e "${GREEN}[rebuild]${NC} $*"; }
warn()    { echo -e "${YELLOW}[rebuild]${NC} $*"; }
section() { echo; echo -e "${GREEN}━━━ $* ━━━${NC}"; echo; }

cd "$REPO_ROOT"

# ── 1. Determine which services to rebuild ─────────────────────────────────────
if $REBUILD_ALL; then
  SERVICES=(api cashflow_agent investment_agent tax_agent risk_agent goal_agent frontend)
  IMAGES=(artha-api artha-cashflow-agent artha-investment-agent artha-tax-agent artha-risk-agent artha-goal-agent artha-frontend)
else
  SERVICES=(frontend)
  IMAGES=(artha-frontend)
fi

section "Artha rebuild: ${SERVICES[*]}"

# ── 2. Stop targeted containers ────────────────────────────────────────────────
info "Stopping containers: ${SERVICES[*]}"
$COMPOSE stop "${SERVICES[@]}" 2>/dev/null || true

# ── 3. Remove targeted containers ─────────────────────────────────────────────
info "Removing containers: ${SERVICES[*]}"
$COMPOSE rm -f "${SERVICES[@]}" 2>/dev/null || true

# ── 4. Remove old images so Docker doesn't serve stale layers ─────────────────
info "Removing old images: ${IMAGES[*]}"
for img in "${IMAGES[@]}"; do
  if docker image inspect "${img}:latest" &>/dev/null; then
    docker rmi "${img}:latest" && echo "  removed ${img}:latest"
  else
    warn "  ${img}:latest not found — skipping"
  fi
done

# ── 5. Build fresh images ──────────────────────────────────────────────────────
section "Building images"
$COMPOSE build $NO_CACHE "${SERVICES[@]}"

# ── 6. Start the rebuilt containers (infrastructure must already be up) ────────
section "Starting containers"
if $REBUILD_ALL; then
  # Full stack — bring everything up in dependency order
  info "Starting full stack (infra + services)…"
  $COMPOSE up -d
else
  # Infrastructure health-check: postgres and redis must be healthy before
  # the frontend can talk to the API.
  info "Ensuring infrastructure is healthy…"
  $COMPOSE up -d postgres redis jaeger 2>/dev/null || true

  # Wait for postgres
  echo -n "  Waiting for postgres"
  until $COMPOSE exec -T postgres pg_isready -U artha -q 2>/dev/null; do
    echo -n "."
    sleep 1
  done
  echo " ready"

  # Bring API up (agents may already be running)
  info "Starting api…"
  $COMPOSE up -d api

  # Wait for API health check
  echo -n "  Waiting for api"
  for _ in $(seq 1 30); do
    if curl -sf http://localhost:8000/health &>/dev/null; then
      echo " ready"
      break
    fi
    echo -n "."
    sleep 2
  done

  # Finally start frontend
  info "Starting frontend…"
  $COMPOSE up -d frontend
fi

# ── 7. Tail logs until user presses Ctrl-C ─────────────────────────────────────
section "Startup complete"
echo -e "  ${GREEN}Frontend:${NC}  http://localhost:3000"
echo -e "  ${GREEN}API:${NC}       http://localhost:8000"
echo -e "  ${GREEN}API docs:${NC}  http://localhost:8000/docs"
echo -e "  ${GREEN}Jaeger:${NC}    http://localhost:16686"
echo
info "Tailing frontend logs (Ctrl-C to exit — containers keep running)"
$COMPOSE logs -f frontend
