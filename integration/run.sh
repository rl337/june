#!/usr/bin/env bash
# Build and run the June integration suite in a container.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

MODE="${1:-offline}" # offline | live | all

# Host bind for container /artifacts (gitignored; inspect after the run).
mkdir -p "$ROOT/artifacts"

BUILD_ARGS=(docker compose -f docker-compose.yml -f integration/docker-compose.yml build integration)
RUN_BASE=(docker compose -f docker-compose.yml -f integration/docker-compose.yml run --rm)

case "$MODE" in
  offline)
    "${BUILD_ARGS[@]}"
    "${RUN_BASE[@]}" integration \
      pytest -q tests/integration -o addopts= -m "integration and not junespark_live"
    ;;
  live)
    if [[ -z "${JUNESPARK_BASE_URL:-}" ]]; then
      echo "JUNESPARK_BASE_URL is required for live mode" >&2
      exit 2
    fi
    "${BUILD_ARGS[@]}"
    "${RUN_BASE[@]}" \
      -e "JUNESPARK_BASE_URL=${JUNESPARK_BASE_URL}" \
      -e "JUNESPARK_API_KEY=${JUNESPARK_API_KEY:-junespark}" \
      -e "JUNESPARK_MODEL=${JUNESPARK_MODEL:-}" \
      integration \
      pytest -q tests/integration -o addopts= -m "integration and junespark_live"
    ;;
  all)
    "${BUILD_ARGS[@]}"
    "${RUN_BASE[@]}" \
      -e "JUNESPARK_BASE_URL=${JUNESPARK_BASE_URL:-}" \
      -e "JUNESPARK_API_KEY=${JUNESPARK_API_KEY:-junespark}" \
      -e "JUNESPARK_MODEL=${JUNESPARK_MODEL:-}" \
      integration \
      pytest -q tests/integration -o addopts= -m integration
    ;;
  *)
    echo "usage: $0 [offline|live|all]" >&2
    exit 2
    ;;
esac
