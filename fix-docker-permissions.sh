#!/bin/bash
# Fix Docker container permission issues
# Run with: sudo ./fix-docker-permissions.sh

set -e

USER_NAME="${SUDO_USER:-$(whoami)}"
USER_ID=$(id -u "$USER_NAME")
GROUP_ID=$(id -g "$USER_NAME")

echo "Fixing Docker container data directory permissions for user: $USER_NAME ($USER_ID:$GROUP_ID)..."

# Change ownership of all subdirectories to the regular user
echo "Fixing ownership of /var/data/june subdirectories..."
chown -R "$USER_ID:$GROUP_ID" /var/data/june/* 2>/dev/null || true

echo "Fixing ownership of /var/log/june subdirectories..."
chown -R "$USER_ID:$GROUP_ID" /var/log/june/* 2>/dev/null || true

# Set permissions
echo "Setting permissions..."
chmod -R 755 /var/data/june
chmod -R 755 /var/log/june

echo "Permissions fixed! Restarting containers..."
cd /home/rlee/dev/home_infra
docker compose restart grafana prometheus loki nats nginx

echo "Done! Containers should now be able to write to the directories."

