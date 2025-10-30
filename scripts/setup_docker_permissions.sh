#!/bin/bash
# Docker Setup Script for June Agent

echo "🔧 Setting up Docker for June Agent..."

# Check if user is already in docker group
if groups | grep -q docker; then
    echo "✅ User is already in docker group"
else
    echo "⚠️  Adding user to docker group..."
    
    # Try to add user to docker group
    if command -v usermod &> /dev/null; then
        echo "Adding user $USER to docker group..."
        sudo usermod -aG docker $USER
        echo "✅ User added to docker group"
        echo "⚠️  You may need to log out and back in, or run: newgrp docker"
    else
        echo "❌ usermod command not found"
        exit 1
    fi
fi

# Check Docker daemon status
if systemctl is-active --quiet docker; then
    echo "✅ Docker daemon is running"
else
    echo "⚠️  Starting Docker daemon..."
    sudo systemctl start docker
fi

# Test Docker access
echo "Testing Docker access..."
if docker ps >/dev/null 2>&1; then
    echo "✅ Docker access is working"
    echo ""
    echo "🚀 Ready to deploy June Agent services!"
    echo "Run: ./scripts/deploy_audio_services.sh"
else
    echo "❌ Docker access still denied"
    echo "Try running: newgrp docker"
    echo "Or log out and log back in"
fi





