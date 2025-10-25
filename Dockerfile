# Dockerfile for Zoom-Telebot SOC
FROM python:3.11-slim as base

# Set environment variables
ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONHASHSEED=random
ENV PIP_NO_CACHE_DIR=1
ENV PIP_DISABLE_PIP_VERSION_CHECK=1

# Install system dependencies
RUN apt-get update && apt-get install -y \
    gcc \
    curl \
    gosu \
    && rm -rf /var/lib/apt/lists/*

# Create app user
RUN groupadd -r botuser && useradd -r -g botuser botuser

# Set work directory
WORKDIR /app

# Copy requirements first for better caching
COPY requirements.txt .

# Install Python dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Production stage
FROM base as production

# Copy application code
COPY . .

# Create necessary directories
RUN mkdir -p /app/data /app/logs

# Set permissions
RUN chown -R botuser:botuser /app

# Copy entrypoint script
COPY docker-entrypoint.sh /usr/local/bin/
RUN chmod +x /usr/local/bin/docker-entrypoint.sh

# Set entrypoint (runs as root initially)
ENTRYPOINT ["/usr/local/bin/docker-entrypoint.sh"]

# Switch to non-root user (this will be done in entrypoint)
# USER botuser

# Development stage (optional)
FROM base as development

# Install additional dev dependencies
RUN pip install --no-cache-dir \
    watchdog \
    pytest \
    pytest-asyncio

# Copy application code
COPY . .

# Create necessary directories
RUN mkdir -p /app/data /app/logs

# Set permissions
RUN chown -R botuser:botuser /app

# Switch to non-root user
USER botuser

# Development command
CMD ["python", "dev.py", "run"]