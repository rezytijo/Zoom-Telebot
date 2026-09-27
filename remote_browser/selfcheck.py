"""Self-check for the Zoom browser host's non-browser logic.

Run: python remote_browser/selfcheck.py

Covers the guards that only fail against live Zoom, so they are cheap to test
here: path parsing, the Zoom-link allowlist, host exclusivity, the
failure-reason classifier, and the auth boundary. No Chromium, no network.
"""

from __future__ import annotations

import asyncio
import json
import os
import sys
import time
from pathlib import Path

from aiohttp import web
from aiohttp.test_utils import TestClient, TestServer

sys.path.insert(0, str(Path(__file__).resolve().parent))

import server  # noqa: E402

TOKEN = "selfcheck-token"


def _app_without_browser() -> web.Application:
    """make_app() as-is.

    There is no lifespan to stub any more: the host defers Chromium to the
    first launch(), so building the app never starts a browser. Only routing
    and the guards are under test here.
    """
    return server.make_app()


class FakeRequest:
    """Minimal stand-in for the only request attribute the helpers read."""

    def __init__(self, path: str) -> None:
        self.path = path


class _Locator:
    def __init__(self, count: int) -> None:
        self._count = count

    async def count(self) -> int:
        return self._count

    @property
    def first(self) -> "_Locator":
        return self


class FakePage:
    """Stubs the page surface _await_joined and _failure_reason actually touch."""

    def __init__(self, body: str = "", joined: bool = False) -> None:
        self._body = body
        self._joined = joined

    async def inner_text(self, _selector: str) -> str:
        return self._body

    async def wait_for_timeout(self, _ms: int) -> None:
        return None

    def locator(self, _selector: str) -> _Locator:
        return _Locator(1 if self._joined else 0)


def test_meeting_id_parsing() -> None:
    assert server._meeting_id(FakeRequest("/meetings/123/launch"), "launch") == "123"
    assert server._meeting_id(FakeRequest("/meetings/123/stop"), "stop") == "123"

    # Malformed paths return None so the handler 400s instead of crashing.
    assert server._meeting_id(FakeRequest("/meetings/123"), "launch") is None
    assert server._meeting_id(FakeRequest("/meetings//launch"), "launch") is None
    assert server._meeting_id(FakeRequest("/health"), "launch") is None
    assert server._meeting_id(FakeRequest("/meetings/123/launch/extra"), "launch") is None
    print("meeting_id parsing OK")


async def test_failure_reasons() -> None:
    host = server.host
    cases = {
        "Please wait, we're waiting for the host to start this meeting": "waiting_room_not_admitted",
        "The passcode you entered is incorrect. Please try again": "bad_passcode",
        "Sign in to join this meeting": "session_expired",
        "This meeting ID is not valid": "meeting_id_invalid",
    }
    for body, expected in cases.items():
        got = await host._failure_reason(FakePage(body, joined=False))
        assert got == expected, f"{body!r} -> {got!r}, expected {expected!r}"

    # A clean page is not an error; the poll loop must keep waiting.
    assert await host._failure_reason(FakePage("waiting", joined=False)) is None
    print("failure classification OK")


async def test_joined_detection() -> None:
    host = server.host
    assert await host._in_meeting(FakePage(joined=True)) is True
    assert await host._in_meeting(FakePage(joined=False)) is False
    print("joined detection OK")


async def test_host_exclusivity() -> None:
    """A second meeting must not steal the browser mid-call."""
    host = server.host
    host._held_by = "111"
    host._held_at = time.time()
    try:
        try:
            await host.stop("222")
        except server.HostBusyError:
            pass
        else:
            raise AssertionError("stop() must refuse a meeting that does not own the host")

        # A hold older than the TTL is abandoned, never a permanent lock.
        host._held_at = time.time() - (server.STATE_TTL + 1)
        assert host._fresh() is False
    finally:
        host._held_by = None
        host._held_at = 0.0
    print("host exclusivity + TTL OK")


async def test_zoom_link_allowlist() -> None:
    """Only Zoom-hosted links may be opened by the signed-in browser."""
    allowed = [
        "https://zoom.us/j/123",
        "https://us05web.zoom.us/s/123?zak=abc",
        "https://acme.zoom.us/j/123",
    ]
    refused = [
        "http://zoom.us/j/123",          # not https
        "https://evil.example.com/steal",
        "https://zoom.us.evil.com/j/123",  # suffix trap
        "https://notzoom.us/j/123",
        "javascript:alert(1)",
    ]
    for url in allowed:
        assert server._is_zoom_link(url), f"{url} should be allowed"
    for url in refused:
        assert not server._is_zoom_link(url), f"{url} should be refused"
    print("Zoom link allowlist OK")


async def test_zak_start_url_accepted() -> None:
    """A start_url carrying a zak host key is the primary launch path."""
    async with TestClient(TestServer(_app_without_browser())) as client:
        response = await client.post(
            "/meetings/123/launch",
            json={
                "start_url": "https://us05web.zoom.us/s/85895463055?zak=abc123",
                "join_url": "https://us05web.zoom.us/j/85895463055?pwd=bdY3n4",
                "passcode": "bdY3n4",
            },
            headers={"Authorization": f"Bearer {TOKEN}"},
        )
        # 500 means validation passed and host.launch ran; it fails only because
        # the self-check runs without a browser.
        assert response.status == 500, f"start_url returned {response.status}"
        assert "desktop-only" not in await response.text()
    print("zak start_url accepted OK")

async def test_non_zoom_url_rejected() -> None:
    """An off-domain start_url must be refused before the browser navigates."""
    async with TestClient(TestServer(_app_without_browser())) as client:
        response = await client.post(
            "/meetings/123/launch",
            json={"start_url": "https://evil.example.com/steal"},
            headers={"Authorization": f"Bearer {TOKEN}"},
        )
        assert response.status == 400, f"off-domain returned {response.status}"
        assert "non-Zoom" in await response.text()
    print("off-domain URL rejected OK")

async def test_missing_urls_rejected() -> None:
    """No link at all is a 400, not a blank-page navigation."""
    async with TestClient(TestServer(_app_without_browser())) as client:
        response = await client.post(
            "/meetings/123/launch",
            json={"passcode": "bdY3n4"},
            headers={"Authorization": f"Bearer {TOKEN}"},
        )
        assert response.status == 400
        assert "no start_url or join_url" in await response.text()
    print("missing URL rejected OK")

async def test_auth_boundary() -> None:
    """The bearer token is the only thing standing between a caller and a
    signed-in Zoom session, so every route but /health must demand it."""
    async with TestClient(TestServer(_app_without_browser())) as client:
        unauthed = await client.get("/status")
        assert unauthed.status == 401, f"/status without token returned {unauthed.status}"
        authed = await client.get("/status", headers={"Authorization": f"Bearer {TOKEN}"})
        assert authed.status == 200, f"/status with token returned {authed.status}"
        health = await client.get("/health")
        assert health.status == 200, "/health must stay open for the compose healthcheck"
    print("auth boundary OK")

async def test_browser_stays_off_until_needed() -> None:
    """Chromium must not exist between meetings - that is the whole point of
    deferring its start, and it is invisible to every other test here."""
    host = server.host
    assert host._context is None, "a browser is already running at rest"
    assert host.snapshot()["browser_running"] is False

    # Point SESSION_FILE at a path that does not exist instead of relying on
    # the ambient one being absent. Inside the host container the real
    # /data/zoom_web_session.json *does* exist, and "no session file on a dev
    # box" is exactly the kind of assumption that only ever holds on the
    # machine where the assertion was written.
    original = server.SESSION_FILE
    missing = str(Path(original).parent / "definitely_absent_session.json")
    server.SESSION_FILE = missing
    try:
        # A status probe must not silently boot a browser either.
        assert await host.session_ready() is False, "expected a missing session file"
        assert host._context is None, "session_ready() must not boot a browser"
    finally:
        server.SESSION_FILE = original

    # /health must answer with no browser and no session at all.
    async with TestClient(TestServer(_app_without_browser())) as client:
        health = await client.get("/health")
        assert health.status == 200
        assert (await health.json())["zoom_running"] is False
    print("lazy browser start OK")

# -- session import ---------------------------------------------------------

# A trimmed but structurally faithful Cookie Editor export: real cookie names,
# real domains, both expiration styles, plus the two field spellings that differ
# from Playwright's (expirationDate vs expires, hostOnly, storeId).
COOKIE_EDITOR_EXPORT = [
    {"domain": ".zoom.us", "expirationDate": 1822034460.010744, "hostOnly": False,
     "httpOnly": True, "name": "_zm_multi_ac", "path": "/", "sameSite": None,
     "secure": True, "session": False, "storeId": None, "value": "MULTI-AC-VALUE"},
    {"domain": ".zoom.us", "hostOnly": False, "httpOnly": False, "name": "_zm_page_auth",
     "path": "/", "sameSite": "no_restriction", "secure": True, "session": True,
     "storeId": None, "value": "aw1_c_RtD1H9wzSuOxIn3vN8rXZg"},
    {"domain": "us06web.zoom.us", "hostOnly": True, "httpOnly": True, "name": "cred",
     "path": "/", "sameSite": None, "secure": True, "session": True,
     "storeId": None, "value": "42ED75554C71714A0DB1A0755E941E3D"},
    # Session cookie: no expirationDate at all. Dropping these would drop the
    # live login, because Playwright reads a missing expires as expired.
    {"domain": ".zoom.us", "hostOnly": False, "httpOnly": False, "name": "zm_haid",
     "path": "/", "sameSite": None, "secure": True, "session": True,
     "storeId": None, "value": "713"},
    {"domain": ".zoom.us", "expirationDate": 1798274460.010849, "hostOnly": False,
     "httpOnly": True, "name": "_zm_kms", "path": "/", "sameSite": None,
     "secure": True, "session": False, "storeId": None, "value": "us06_c_b3pnMVQ0"},
    {"domain": ".zoom.us", "expirationDate": 1790499029.898531, "hostOnly": False,
     "httpOnly": True, "name": "zm_oauth_back_params", "path": "/", "sameSite": None,
     "secure": True, "session": False, "storeId": None, "value": "eyJiYXNlX3VybCI6"},
    # Not Zoom: must never reach the session file.
    {"domain": ".example.com", "hostOnly": False, "httpOnly": False, "name": "_tracking",
     "path": "/", "sameSite": "lax", "secure": True, "session": False,
     "storeId": None, "value": "UNRELATED"},
    # Suffix trap: zoom.us.evil.com is not Zoom.
    {"domain": "zoom.us.evil.com", "hostOnly": False, "httpOnly": True, "name": "steal",
     "path": "/", "sameSite": None, "secure": True, "session": False,
     "storeId": None, "value": "NOPE"},
]


def test_cookie_editor_conversion() -> None:
    """A Cookie Editor array must become a storage_state Playwright accepts."""
    state = server.cookies_to_storage_state(COOKIE_EDITOR_EXPORT)
    assert list(state) == ["cookies", "origins"], "storage_state needs both keys"
    assert state["origins"] == [], "no localStorage was uploaded, so none is invented"

    by_name = {c["name"]: c for c in state["cookies"]}
    # 6 Zoom cookies kept, the unrelated and the suffix-trap one dropped.
    assert len(state["cookies"]) == 6, f"kept {len(state['cookies'])} cookies"
    assert "steal" not in by_name and "_tracking" not in by_name

    # Every field Playwright requires, and none it forbids.
    for cookie in state["cookies"]:
        assert set(cookie) == {"name", "value", "domain", "path", "expires",
                               "httpOnly", "secure", "sameSite"}, sorted(cookie)
        assert cookie["sameSite"] in ("None", "Lax", "Strict"), cookie["sameSite"]
        assert isinstance(cookie["expires"], float), type(cookie["expires"])
        assert not cookie["domain"].startswith("."), "leading dot confuses the host match"

    # expirationDate -> expires, in seconds.
    assert by_name["_zm_multi_ac"]["expires"] == 1822034460.010744
    # A session cookie must become the -1 sentinel, not be dropped.
    assert by_name["_zm_page_auth"]["expires"] == -1
    assert by_name["zm_haid"]["expires"] == -1
    # no_restriction is a Cookie Editor spelling, not a Playwright one.
    assert by_name["_zm_page_auth"]["sameSite"] == "None"
    assert by_name["_zm_kms"]["sameSite"] == "Lax"
    print("Cookie Editor conversion OK")


def test_import_shapes_accepted() -> None:
    """Accept a bare array, an already-wrapped object, or a real storage_state."""
    as_array = server.cookies_to_storage_state(COOKIE_EDITOR_EXPORT)
    as_wrapped = server.cookies_to_storage_state({"cookies": COOKIE_EDITOR_EXPORT})
    as_state = server.cookies_to_storage_state(
        {"cookies": COOKIE_EDITOR_EXPORT, "origins": []})
    assert as_array == as_wrapped == as_state, "all three shapes must normalize alike"

    # Malformed input must say why, not raise something opaque.
    for bad, needle in [
        ("[]", "tidak ada cookie"),
        ('{"nothing": 1}', "bukan JSON array"),
        ('"just a string"', "bukan JSON array"),
    ]:
        try:
            server.cookies_to_storage_state(json.loads(bad))
        except server.SessionImportError as exc:
            assert needle in str(exc), f"{bad} -> {exc}"
        else:
            raise AssertionError(f"{bad} should have been rejected")

    # An anonymous visitor's cookies are refused rather than silently saved:
    # doing so would replace a working session with a useless one.
    anonymous = [{"domain": ".zoom.us", "name": "_zm_lang", "value": "en-US",
                  "path": "/", "expirationDate": 1822034468.0}]
    try:
        server.cookies_to_storage_state(anonymous)
    except server.SessionImportError as exc:
        assert "cookie sesi Zoom" in str(exc)
    else:
        raise AssertionError("a cookie export with no session marker must be refused")
    print("import shapes + rejection reasons OK")


async def test_session_import_endpoint() -> None:
    """The upload must land on disk, keep the old file on failure, and never
    disturb a running meeting."""
    host = server.host
    import os as _os
    original = server.SESSION_FILE
    tmpdir = Path(_os.environ.get("TEMP") or _os.getcwd()) / "zoom_browser_selfcheck"
    tmpdir.mkdir(parents=True, exist_ok=True)
    server.SESSION_FILE = str(tmpdir / "zoom_web_session.json")
    try:
        payload = json.dumps(COOKIE_EDITOR_EXPORT).encode()

        # 1. A good upload is stored in storage_state form. The response must
        #    never claim success it cannot back up, and - the rule that matters
        #    - an unverified import must always carry a reason. A False with an
        #    empty reload_error tells the operator nothing: they cannot tell a
        #    rejected cookie from a broken host, and those need different fixes.
        async with TestClient(TestServer(_app_without_browser())) as client:
            response = await client.post(
                "/zoom/session",
                data=payload,
                headers={"Authorization": f"Bearer {TOKEN}",
                         "Content-Type": "application/json"},
            )
            assert response.status == 200, f"import returned {response.status}: {await response.text()}"
            body = await response.json()
            assert body["imported"] is True
            assert body["cookies"] == 6, body
            assert isinstance(body["signed_in"], bool)
            if not body["signed_in"]:
                assert body["reload_error"], \
                    "signed_in=false with an empty reason is an unactionable report"

        stored = json.loads(Path(server.SESSION_FILE).read_text(encoding="utf-8"))
        assert "cookies" in stored and "origins" in stored
        assert {c["name"] for c in stored["cookies"]} >= {"_zm_page_auth", "cred"}

        # 2. A broken upload must leave the good session exactly as it was.
        before = Path(server.SESSION_FILE).read_text(encoding="utf-8")
        async with TestClient(TestServer(_app_without_browser())) as client:
            response = await client.post(
                "/zoom/session",
                data=b"{not json",
                headers={"Authorization": f"Bearer {TOKEN}",
                         "Content-Type": "application/json"},
            )
            assert response.status == 400, f"broken JSON returned {response.status}"
        assert Path(server.SESSION_FILE).read_text(encoding="utf-8") == before, \
            "a failed import must not damage the existing session"

        # 3. An oversized body is refused rather than buffered.
        async with TestClient(TestServer(_app_without_browser(), max_size=1024)) as client:
            response = await client.post(
                "/zoom/session",
                data=b"x" * 2048,
                headers={"Authorization": f"Bearer {TOKEN}",
                         "Content-Type": "application/json"},
            )
            assert response.status in (400, 413), f"oversized returned {response.status}"

        # 4. Auth is still required - this route writes the Zoom login.
        async with TestClient(TestServer(_app_without_browser())) as client:
            response = await client.post(
                "/zoom/session",
                data=payload,
                headers={"Content-Type": "application/json"},
            )
            assert response.status == 401, f"unauthed import returned {response.status}"

        # 5. A live meeting must block the import, because reloading the context
        #    would drop the browser that meeting is sitting in.
        host._held_by = "999"
        host._held_at = time.time()
        try:
            async with TestClient(TestServer(_app_without_browser())) as client:
                response = await client.post(
                    "/zoom/session",
                    data=payload,
                    headers={"Authorization": f"Bearer {TOKEN}",
                             "Content-Type": "application/json"},
                )
                assert response.status == 409, f"import during meeting returned {response.status}"
        finally:
            host._held_by = None
            host._held_at = 0.0
    finally:
        server.SESSION_FILE = original
    print("session import endpoint OK")

async def test_restart_survives_repeated_calls() -> None:
    """restart() twice must still yield a usable browser.

    The live import is the only thing that calls restart() in a loop, and it
    found a real bug the HTTP tests above structurally cannot: those run with
    Chromium stubbed out, so a handle left pointing at a closed context never
    got dereferenced. The first restart happened to work only because lazy
    Chromium meant nothing was running yet - the second one hit
    TargetClosedError on new_page().

    Uses a blank storage_state rather than the real session: this asserts the
    restart bookkeeping, not Zoom's login state.

    Skipped when the Playwright browser binary is absent, which is the normal
    state of a dev machine - the binaries only ship inside the host image.
    Run it there to get real coverage: `docker compose exec zoom-browser
    python remote_browser/selfcheck.py`.
    """
    host = server.host
    original = server.SESSION_FILE
    import os as _os
    tmpdir = Path(_os.environ.get("TEMP") or _os.getcwd()) / "zoom_browser_restart_check"
    tmpdir.mkdir(parents=True, exist_ok=True)
    server.SESSION_FILE = str(tmpdir / "zoom_web_session.json")
    Path(server.SESSION_FILE).write_text(
        json.dumps({"cookies": [], "origins": []}), encoding="utf-8"
    )
    try:
        try:
            await host.restart()
        except Exception as exc:  # noqa: BLE001
            if "Executable doesn't exist" in str(exc):
                print("repeated restart SKIPPED (no Playwright browser binary)")
                return
            raise
        assert host._context is not None, "restart left no context"
        await host._context.close()
        for attempt in (2, 3):
            await host.restart()
            assert host._context is not None, f"restart #{attempt} left no context"
            # Dereference the handle the way session_ready() does. A stale
            # handle survives the assert above and only dies here.
            page = await host._context.new_page()
            await page.close()
        assert host._held_by is None, "restart must drop the meeting claim"
    finally:
        await host._release()
        server.SESSION_FILE = original
    print("repeated restart OK")

async def main() -> None:
    # _auth() refuses every protected route while the token is unset, so the
    # HTTP tests would assert 401 instead of reaching the guards they test.
    os.environ["BROWSER_API_TOKEN"] = TOKEN
    test_meeting_id_parsing()
    await test_failure_reasons()
    await test_joined_detection()
    await test_host_exclusivity()
    await test_zoom_link_allowlist()
    await test_browser_stays_off_until_needed()
    await test_zak_start_url_accepted()
    await test_non_zoom_url_rejected()
    await test_missing_urls_rejected()
    await test_auth_boundary()
    test_cookie_editor_conversion()
    test_import_shapes_accepted()
    await test_session_import_endpoint()
    await test_restart_survives_repeated_calls()
    print("\nzoom_browser selfcheck: all assertions passed")


if __name__ == "__main__":
    asyncio.run(main())
