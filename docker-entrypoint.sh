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

# Check environment configuration
if [ ! -f /app/.env ]; then
    echo "⚠️  .env file not found!"

    # Check if required environment variables are set
    required_vars="TELEGRAM_TOKEN INITIAL_OWNER_ID ZOOM_CLIENT_ID ZOOM_CLIENT_SECRET DATABASE_URL"
    missing_vars=""

    for var in $required_vars; do
        if [ -z "${!var}" ]; then
            missing_vars="$missing_vars $var"
        fi
    done

    if [ -n "$missing_vars" ]; then
        echo "❌ Required environment variables are missing:$missing_vars"
        echo "   Please either:"
        echo "   1. Mount your .env file: -v \$(pwd)/.env:/app/.env"
        echo "   2. Set environment variables in your Docker configuration"
        exit 1
    else
        echo "✅ Using environment variables from Docker configuration"
        # Create a minimal .env file from environment variables for compatibility
        echo "# Generated from Docker environment variables" > /app/.env
        for var in $required_vars SID_ID SID_KEY BITLY_TOKEN ZOOM_ACCOUNT_ID INITIAL_OWNER_USERNAME DEFAULT_MODE LOG_LEVEL; do
            if [ -n "${!var}" ]; then
                echo "$var=${!var}" >> /app/.env
            fi
        done
        echo "✅ Temporary .env file created from environment variables"
    fi
else
    echo "✅ .env file found"
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
echo "🚀 Starting bot..."

# For debugging, try running as root first
echo "Running as root for testing..."
if [ $# -eq 0 ]; then
    echo "No arguments provided, using default command: python main.py"
    exec python main.py
else
    echo "Using provided arguments: $@"
    exec "$@"
fi