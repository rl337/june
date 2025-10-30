#!/bin/bash
# Docker Setup Script for June Agent

echo "🔧 Setting up Docker permissions for June Agent..."

# Check if user is in docker group
if groups | grep -q docker; then
    echo "✅ User is already in docker group"
else
    echo "⚠️  User needs to be added to docker group"
    echo "Run the following commands:"
    echo "  sudo usermod -aG docker $USER"
    echo "  newgrp docker"
    echo "  # Then log out and log back in, or run: newgrp docker"
fi

# Check Docker daemon status
if systemctl is-active --quiet docker; then
    echo "✅ Docker daemon is running"
else
    echo "⚠️  Docker daemon is not running"
    echo "Run: sudo systemctl start docker"
fi

# Test Docker access
if docker ps >/dev/null 2>&1; then
    echo "✅ Docker access is working"
else
    echo "❌ Docker access denied"
    echo "You may need to:"
    echo "  1. Add user to docker group: sudo usermod -aG docker $USER"
    echo "  2. Start new shell session: newgrp docker"
    echo "  3. Or restart your session"
fi

echo ""
echo "🚀 Once Docker is working, you can:"
echo "  docker compose --profile tools up -d cli-tools"
echo "  docker exec -it june-cli-tools bash"




