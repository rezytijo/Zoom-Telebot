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

# Check if required environment variables are set
echo "🔍 Checking environment variables..."
required_vars="TELEGRAM_TOKEN INITIAL_OWNER_ID ZOOM_CLIENT_ID ZOOM_CLIENT_SECRET"
missing_vars=""

for var in $required_vars; do
    if [ -z "${!var}" ]; then
        missing_vars="$missing_vars $var"
    fi
done

if [ -n "$missing_vars" ]; then
    echo "❌ Required environment variables are missing:$missing_vars"
    echo "   Please set these environment variables in your Docker configuration"
    echo "   Example: -e TELEGRAM_TOKEN=your_token -e INITIAL_OWNER_ID=your_id"
    exit 1
fi

echo "✅ All required environment variables are set"

# Create .env file from environment variables for compatibility (optional)
if [ ! -f /app/.env ]; then
    echo "📝 Creating .env file from environment variables..."
    echo "# Generated from Docker environment variables" > /app/.env
    for var in $required_vars SID_ID SID_KEY BITLY_TOKEN ZOOM_ACCOUNT_ID INITIAL_OWNER_USERNAME DEFAULT_MODE LOG_LEVEL DATABASE_URL; do
        if [ -n "${!var}" ]; then
            echo "$var=${!var}" >> /app/.env
        fi
    done
    echo "✅ .env file created from environment variables"
else
    echo "✅ .env file already exists"
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