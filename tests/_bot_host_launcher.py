"""Test-only launcher: run the bot against the host-reachable controller.

Why this exists instead of an env var:

  config/config.py calls `load_dotenv(override=True)` at import time, so any
  ZOOM_REMOTE_BASE_URL in the parent environment is unconditionally replaced by
  the value in .env - which is the compose hostname `zoom-remote:8080`. That name
  only resolves inside the Docker network, so the local bot under test always
  got a ClientConnectorDNSError regardless of what the test set.

  Patching the loaded settings object (rather than the environment) sidesteps
  that entirely, and keeps production code untouched.

Usage:  python tests/_bot_host_launcher.py [--port 8080]
"""
import os
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

PORT = os.getenv("ZOOM_REMOTE_HOST_PORT", "8080")

# Import order matters: config first (populates settings), then the client
# singleton whose base_url every handler and background task already holds.
from config import settings  # noqa: E402

settings.zoom_remote_base_url = f"http://127.0.0.1:{PORT}"

from zoom.remote import remote_zoom_client  # noqa: E402

remote_zoom_client.base_url = settings.zoom_remote_base_url

print(f"[launcher] remote controller -> {remote_zoom_client.base_url}")

from run import main  # noqa: E402

if __name__ == "__main__":
    main()
