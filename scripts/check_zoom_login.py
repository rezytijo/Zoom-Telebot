"""Check whether the Kasm Zoom container has a signed-in account.

The host-join flow needs a logged-in Zoom client. `zak` (the host key) makes the
bot the *host* at the API level, but the desktop client still needs its own
session, and that session is the thing this script checks for.

Read-only. Safe to run any time.

Usage:
    python scripts/check_zoom_login.py
    python scripts/check_zoom_login.py --json
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from datetime import datetime, timezone

CONTAINER = "zoom-remote"
PROFILE_DB = "/home/kasm-user/.zoom/data/zoomus.enc.v2.db"

# Xvnc runs with -sslOnly, so plain http:// on 6901 is refused outright. It also
# sits behind Basic auth, hence the user:password@ form.
VNC_URL = "https://localhost:6901/vnc.html?autoconnect=1&resize=remote"


def sh(cmd: list[str], timeout: int = 20) -> tuple[int, str]:
    try:
        p = subprocess.run(
            ["docker", "compose", "exec", "-T", CONTAINER] + cmd,
            capture_output=True, text=True, encoding="utf-8",
            errors="replace", timeout=timeout,
        )
        return p.returncode, (p.stdout or "").strip()
    except Exception as exc:
        return 1, f"{type(exc).__name__}: {exc}"


def profile_stats() -> dict:
    """Size and mtime of the profile DBs that only exist after a real sign-in."""
    rc, out = sh(["sh", "-c",
                  f"ls -la {PROFILE_DB} /home/kasm-user/.zoom/data/zoomus.zmdb.kvs.enc.db 2>&1"])
    if rc != 0 or not out:
        return {"error": out or "could not read profile"}
    info = {}
    for line in out.splitlines():
        parts = line.split()
        if len(parts) >= 9 and parts[0].startswith("-"):
            info[parts[-1]] = {"size_bytes": int(parts[4])}
    return info


def zoom_processes() -> list[str]:
    rc, out = sh(["sh", "-c", "pgrep -a -x zoom | head -3"])
    return out.splitlines() if rc == 0 and out else []


def main() -> int:
    ap = argparse.ArgumentParser(description="Check Zoom container login state")
    ap.add_argument("--json", action="store_true", help="machine-readable output")
    args = ap.parse_args()

    rc, health = sh(["sh", "-c",
                     "curl -s http://localhost:8080/health 2>&1 || echo UNREACHABLE"])
    up = rc == 0 and "ok" in health

    report = {
        "checked_at": datetime.now(timezone.utc).isoformat(),
        "container_up": up,
        "container_health": health,
        "zoom_running": bool(zoom_processes()),
        "zoom_processes": zoom_processes(),
        "profile": profile_stats(),
    }

    # A fresh, never-signed-in profile keeps these small; a real session grows
    # them well past the template size. Not a proof of login on its own, but a
    # reliable "definitely not logged in yet" signal.
    p = report["profile"]
    signed_in_hint = any(
        isinstance(v, dict) and v.get("size_bytes", 0) > 100_000
        for v in p.values()
    )
    report["looks_signed_in"] = signed_in_hint

    if args.json:
        print(json.dumps(report, indent=2, ensure_ascii=False))
    else:
        print("=== Zoom remote login check ===")
        print(f"container      : {'UP' if up else 'DOWN'}  {report['container_health']}")
        print(f"zoom running   : {report['zoom_running']}")
        for name, meta in p.items():
            size = meta.get("size_bytes", "?") if isinstance(meta, dict) else "?"
            print(f"  {name:<34} {size:>10} bytes")
        print(f"looks signed in: {report['looks_signed_in']}")
        if not report["looks_signed_in"]:
            print()
            print("Next step - sign in ONCE, then never again:")
            print(f"  1. Open  {VNC_URL}")
            print("     (https is required - Xvnc runs with -sslOnly)")
            print("  2. Browser asks for credentials:")
            print("     user     = kasm_user")
            print("     password = ZOOM_REMOTE_VNC_PASSWORD in your .env")
            print("  3. In the remote desktop, log in to Zoom")
            print("  4. Leave Zoom running. The profile lives in the")
            print("     zoom_remote_profile volume and survives restarts.")
            print()
            print("Then re-run:  python scripts/check_zoom_login.py")

    return 0


if __name__ == "__main__":
    sys.exit(main())
