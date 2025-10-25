#!/bin/bash
# Docker entrypoint script for Zoom-Telebot SOC
# Handles initial setup and environment preparation

set -e

echo "🤖 Zoom-Telebot SOC Docker Container Starting..."

# Fix permissions for mounted volumes (we're running as root)
echo "🔧 Fixing permissions for mounted volumes..."
mkdir -p /app/data /app/logs
chown -R botuser:botuser /app/data /app/logs

# Make shorteners.json writable for credential updates
if [ -f /app/shorteners.json ]; then
    # Copy to data directory if it doesn't exist there
    if [ ! -f /app/data/shorteners.json ]; then
        cp /app/shorteners.json /app/data/shorteners.json
        echo "✅ shorteners.json copied to data directory"
    fi
    chmod 664 /app/data/shorteners.json
    chown botuser:botuser /app/data/shorteners.json
    echo "✅ shorteners.json permissions fixed"
fi

echo "✅ Permissions fixed"

# Check if .env file exists
if [ ! -f /app/.env ]; then
    echo "⚠️  .env file not found!"
    echo "   Please mount your .env file as volume or set environment variables"
    echo "   Example: docker run -v \$(pwd)/.env:/app/.env zoom-telebot"
    exit 1
fi

# Validate environment (optional - can be disabled)
if [ "${SKIP_ENV_VALIDATION}" != "true" ]; then
    echo "🔍 Validating environment..."
    if ! python setup.py; then
        echo "❌ Environment validation failed!"
        echo "   Check your .env file and try again"
        exit 1
    fi
fi

echo "✅ Environment ready!"

# Switch to botuser and execute the main command
echo "🚀 Starting bot as botuser..."
exec su-exec botuser "$@"