"""One-time Zoom Web sign-in, producing the session file the browser host reuses.

Run this on a machine with a display (the operator's own PC), not in the
container: the Playwright image has no way to show a window, and a login form
is exactly the kind of thing that must be driven by a human once.

    python scripts/zoom_web_login.py
    python scripts/zoom_web_login.py --out ./zoom_web_session.json

Then copy the resulting file into the host's state volume so
remote_browser/server.py picks it up on start.

Why a stored session and not email/password: Zoom accounts are typically behind
MFA or SSO, neither of which can be automated safely or durably. A one-time
manual login that produces a cookie jar sidesteps both, exactly like the Kasm
image's "sign in once over VNC" flow did.

The saved file is a live credential: it carries the Zoom session cookie. Treat
it like a password and keep it out of git.
"""

from __future__ import annotations

import argparse
import asyncio
import os
import sys
from pathlib import Path

from playwright.async_api import async_playwright

# Zoom's sign-in page. The script waits for the app shell to appear, which only
# happens once a real session exists.
SIGNIN_URL = "https://zoom.us/signin"
PROFILE_MARKER = "/profile"


async def capture_session(out_path: Path, timeout_minutes: int) -> int:
    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=False)
        context = await browser.new_context()
        page = await context.new_page()

        print(f"Opening {SIGNIN_URL} in a browser window.")
        print("Log in as the HOST account (the one that should own meetings).")
        print("Complete MFA / SSO if prompted. The script watches for the app shell.\n")

        await page.goto(SIGNIN_URL, wait_until="domcontentloaded")
        deadline = asyncio.get_event_loop().time() + timeout_minutes * 60

        while asyncio.get_event_loop().time() < deadline:
            url = page.url or ""
            if PROFILE_MARKER in url and "signin" not in url.lower():
                print(f"\nSigned in (landed on {url}).")
                break
            await page.wait_for_timeout(2000)
        else:
            print("\nTimed out waiting for a completed sign-in; nothing saved.")
            await browser.close()
            return 1

        # storage_state captures cookies + localStorage, which is what Zoom's
        # session check reads on every launch.
        out_path.parent.mkdir(parents=True, exist_ok=True)
        await context.storage_state(path=str(out_path))
        await browser.close()

    print(f"Saved session to {out_path} ({out_path.stat().st_size} bytes).")
    print("Copy it into the zoom-browser container's state volume, then restart that container.")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--out",
        default=os.getenv("ZOOM_WEB_SESSION_FILE", "zoom_web_session.json"),
        help="Where to write the Playwright storage_state JSON.",
    )
    parser.add_argument(
        "--timeout",
        type=int,
        default=15,
        help="Minutes to wait for the operator to finish signing in.",
    )
    args = parser.parse_args()

    out = Path(args.out).resolve()
    if out.exists():
        # Overwriting silently would lock the operator out of the only working
        # session they have.
        answer = input(f"{out} exists. Overwrite? [y/N] ").strip().lower()
        if answer != "y":
            print("Aborted; existing session kept.")
            return 1

    return asyncio.run(capture_session(out, args.timeout))


if __name__ == "__main__":
    sys.exit(main())
