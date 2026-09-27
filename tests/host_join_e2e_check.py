"""End-to-end host-join probe against the LIVE remote controller.

Unlike the offline self-checks, this talks to the real zoom-remote container
over HTTP and to the real Zoom API. It proves the full chain works:

    bot -> controller /status -> controller /meetings/{id}/launch
        -> xdg-open start_url in Kasm -> Zoom reports started

Run: python tests/host_join_e2e_check.py
       (or from inside the container: docker compose exec -T zoom-telebot \
            python tests/host_join_e2e_check.py)

Must run inside the Docker network: ZOOM_REMOTE_BASE_URL points at the
`zoom-remote` service name, which does not resolve from the Windows host.
Exits non-zero on failure.
"""
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import aiohttp

from config import settings
from db import (
    get_remote_launch_state,
    set_remote_launch_state,
    list_meetings_pending_launch,
)
from zoom import zoom_client
from zoom.remote import remote_zoom_client

CONTROLLER = settings.zoom_remote_base_url.rstrip("/")


async def fetch_recent_meeting():
    """Return a real, not-yet-ended meeting id, normalised to str.

    Zoom returns the id as a JSON number, but every DB column is TEXT. Comparing
    the raw int against a SQLite TEXT value is always False, so coerce first.
    """
    data = await zoom_client.list_upcoming_meetings(user_id="me")
    items = data.get("meetings", []) if isinstance(data, dict) else (data or [])
    return str(items[0]["id"]) if items else None


async def main():
    token = settings.zoom_remote_api_token
    assert token, "ZOOM_REMOTE_API_TOKEN kosong"
    headers = {"Authorization": f"Bearer {token}"}

    # 1. Controller reachable and accepting the token.
    async with aiohttp.ClientSession() as s:
        async with s.get(f"{CONTROLLER}/health") as r:
            print(f"[1] /health            -> {r.status} {await r.json()}")
            assert r.status == 200, "controller tidak merespons"

        async with s.get(f"{CONTROLLER}/status", headers=headers) as r:
            print(f"[2] /status (auth)     -> {r.status} {await r.json()}")
            assert r.status == 200, (
                f"auth ditolak ({r.status}); token .env tidak sinkron dengan container"
            )

        # 3. A wrong token MUST be rejected, otherwise the guard is broken.
        async with s.get(
            f"{CONTROLLER}/status", headers={"Authorization": "Bearer salah"}
        ) as r:
            print(f"[3] /status (bad token)-> {r.status}")
            assert r.status == 401, f"token salah diterima ({r.status})"

    # 4. Find a real meeting to host.
    mid = await fetch_recent_meeting()
    if not mid:
        print("[4] SKIP: tidak ada meeting waiting/scheduled di Zoom")
        return
    print(f"[5] target meeting     -> {mid}")

    # 5. The bot's own prepare step (this is what yields start_url).
    prepared = await zoom_client.prepare_remote_meeting(mid)
    start_url = prepared.get("start_url") if isinstance(prepared, dict) else None
    assert start_url, f"prepare_remote_meeting tidak mengembalikan start_url: {prepared}"
    print("[6] prepare_remote_meeting -> start_url OK (tidak ditampilkan)")

    # 6. Mark launch_requested exactly like the handler does.
    await set_remote_launch_state(mid, "e2e-probe", 1)
    state = await get_remote_launch_state(mid)
    print(f"[7] db live_status     -> {state['live_status']}")
    assert state["live_status"] == "launch_requested"

    # 7. The confirmation poller must see this row.
    pending = await list_meetings_pending_launch()
    assert any(r["zoom_meeting_id"] == mid for r in pending), (
        "poller tidak melihat launch_requested; loop tidak akan pernah bekerja"
    )
    print(f"[8] poller melihat    -> {len(pending)} pending launch")

    # 8. Fire the real launch at the controller.
    try:
        result = await remote_zoom_client.launch_meeting(mid, start_url, 1)
        print(f"[9] controller /launch -> {result}")
    except Exception as e:
        print(f"[9] controller /launch GAGAL: {type(e).__name__}: {e}")
        raise

    # 9. Wait for the confirmation poller to resolve it.
    budget = settings.zoom_remote_host_confirm_timeout + 30
    print(f"[10] menunggu konfirmasi (maks {budget}s)...")
    for i in range(budget // 5):
        await asyncio.sleep(5)
        st = await get_remote_launch_state(mid)
        zoom_status = (await zoom_client.get_meeting(mid) or {}).get("status")
        print(f"      t+{(i + 1) * 5:>3}s  db={st['live_status']:<16} zoom={zoom_status}")
        if st["live_status"] in ("started", "failed"):
            print(f"[11] SELESAI -> {st['live_status']}  err={st.get('last_remote_error')}")
            if st["live_status"] == "failed":
                print("      Tidak terkonfirmasi. Cek sesi VNC 6901:")
                print("      - sudah login ke Zoom di container?")
                print("      - start_url masih valid?")
            return

    print("[11] TIMEOUT - poller tidak menyelesaikan status")


if __name__ == "__main__":
    asyncio.run(main())
