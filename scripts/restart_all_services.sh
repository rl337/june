#!/bin/bash
# Restart all June and Home Infrastructure services after reboot
# Usage: ./restart_all_services.sh

set -euo pipefail

echo "Starting Home Infrastructure services..."
cd /home/rlee/dev/home_infra
docker compose up -d

echo ""
echo "Starting June services..."
cd /home/rlee/dev/june
docker compose up -d

echo ""
echo "Checking service status..."
docker ps --format "table {{.Names}}\t{{.Status}}"

echo ""
echo "All services started. Check logs with:"
echo "  docker compose -f /home/rlee/dev/home_infra/docker-compose.yml logs"
echo "  docker compose -f /home/rlee/dev/june/docker-compose.yml logs"


