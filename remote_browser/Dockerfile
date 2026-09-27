# syntax=docker/dockerfile:1.7

# Headless Zoom Web host. Replaces the Kasm + Zoom desktop image, which could
# open the Zoom client but never completed the join (llvmpipe software
# rendering left the join dialog unpainted).
#
# The HTTP surface mirrors remote/main.go exactly, so switching hosts is only
# a ZOOM_REMOTE_BASE_URL change in the bot's .env.
FROM mcr.microsoft.com/playwright/python:v1.63.0-noble

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    BROWSER_API_PORT=8080 \
    BROWSER_STATE_DIR=/data

# The Playwright base image ships the *browser binaries* and the Node CLI, but
# NOT the Python package - `import playwright` fails on a stock image. Both
# pins are required: the Python package drives Chromium, and the image tag
# decides which Chromium build that package expects. Mismatched versions are
# the usual cause of "Executable doesn't exist" at launch time.
RUN pip install --no-cache-dir "playwright==1.63.0" "aiohttp==3.14.3"

# Non-root: the Playwright image ships a `pwuser`, and Chromium refuses to
# start as root without --no-sandbox, which is already passed in code.
RUN mkdir -p /data && chown pwuser:pwuser /data

USER pwuser
WORKDIR /app

COPY --chown=pwuser:pwuser remote_browser/server.py /app/server.py

EXPOSE 8080

HEALTHCHECK --interval=15s --timeout=5s --start-period=30s --retries=5 \
    CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8080/health',timeout=4).status==200 else 1)"

CMD ["python", "/app/server.py"]
