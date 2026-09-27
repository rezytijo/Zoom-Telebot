"""Headless Zoom host driver.

Replaces the Kasm/Zoom desktop host, which could open the Zoom client but never
completed the join: the container renders with llvmpipe and the client's join
dialog never paints.

Launches the meeting through the host's start_url, which Zoom's meeting object
(GET /v2/meetings/{meetingId}) documents as
`https://us05web.zoom.us/s/<id>?zak=<host key>` - the /s/ path plus the zak
query parameter are what make it a host link rather than a participant one.
join_url (`/j/<id>?pwd=`) is kept only as a fallback, since it yields whatever
role Zoom assigns from the waiting room, not the host role.

The HTTP surface intentionally mirrors remote/main.go so zoom/remote.py and the
bot need no changes: swap ZOOM_REMOTE_BASE_URL to switch hosts.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import secrets
import time
from typing import Any, Dict, Optional, Tuple
from urllib.parse import urlparse

from aiohttp import web
from playwright.async_api import Error as PlaywrightError
from playwright.async_api import TimeoutError as PlaywrightTimeout
from playwright.async_api import async_playwright

logger = logging.getLogger("zoom_browser")
logging.basicConfig(
    level=os.getenv("LOG_LEVEL", "INFO"),
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
)

API_PORT = int(os.getenv("BROWSER_API_PORT", "8080"))
API_TOKEN = os.getenv("BROWSER_API_TOKEN", "")
STATE_DIR = os.getenv("BROWSER_STATE_DIR", "/data")
SESSION_FILE = os.path.join(STATE_DIR, "zoom_web_session.json")

# Chromium flags for a container with no display and no GPU.
LAUNCH_ARGS = [
    "--no-sandbox",
    "--disable-dev-shm-usage",
    "--disable-gpu",
    "--disable-setuid-sandbox",
]

# One host can only be in one meeting, so a single browser context is the
# ceiling by design. Parallel launches would fight over the same signed-in
# session; the state machine rejects them with 409 instead.
STATE_TTL = int(os.getenv("BROWSER_STATE_TTL", "600"))


class HostBusyError(RuntimeError):
    """Another meeting owns the browser right now."""


class LaunchError(RuntimeError):
    """The join did not reach a joined state."""

class SessionImportError(ValueError):
    """The uploaded cookie export could not become a usable session."""


class ZoomBrowserHost:
    """Owns the Playwright browser and drives Zoom Web join/leave."""

    def __init__(self) -> None:
        self._pw = None
        self._browser = None
        self._context = None
        self._lock = asyncio.Lock()
        self._held_by: Optional[str] = None
        self._held_at: float = 0.0
        self._page = None
        # Why the last session check came back negative. Empty means "no verdict
        # yet"; check_session() turns it into an operator-facing reason.
        self._last_session_detail: str = ""

    # -- lifecycle ---------------------------------------------------------

    async def _ensure_started(self) -> None:
        """Start Chromium on first use rather than at container boot.

        Chromium is the expensive part; the aiohttp server wrapped around it is
        not. Deferring the launch means an idle host costs a few dozen MB, and
        the ~2s cold start disappears inside the caller's launch timeout.
        """
        if self._context:
            return
        self._pw = await async_playwright().start()
        self._browser = await self._pw.chromium.launch(headless=True, args=LAUNCH_ARGS)
        self._context = await self._new_context()
        logger.info("Chromium %s started", self._browser.version)

    async def _release(self) -> None:
        """Tear Chromium down, returning the process to a bare HTTP server.

        Only safe when no meeting is held: closing the page leaves the meeting.
        """
        if self._context:
            await self._context.close()
            self._context = None
        if self._browser:
            await self._browser.close()
            self._browser = None
        if self._pw:
            await self._pw.stop()
            self._pw = None
        self._page = None
        logger.info("Chromium released")

    async def _release_if_idle(self) -> None:
        """Drop Chromium once no meeting owns the browser.

        Every caller is a point where nothing should be held: a finished
        launch, a failed one, a stop, or a status probe. Tying the release to
        _held_by rather than to elapsed time means the browser's lifetime
        matches the meeting's instead of a timer guessing at it.
        """
        if self._held_by is None:
            await self._release()

    async def stop(self) -> None:
        await self._release()

    async def _new_context(self):
        """Restore the signed-in session so the host is not asked to log in."""
        context_kwargs: Dict[str, Any] = {
            "viewport": {"width": 1280, "height": 800},
            "ignore_https_errors": True,
        }
        if os.path.exists(SESSION_FILE):
            context_kwargs["storage_state"] = SESSION_FILE
        return await self._browser.new_context(**context_kwargs)

    # -- session health ----------------------------------------------------

    async def check_session(self) -> Tuple[bool, str]:
        """Verify the stored session and explain a negative result.

        session_ready() collapses "not signed in" and "the check itself blew
        up" into a single False, which is fine for a boolean status field but
        useless to a caller that has to tell the operator whether their upload
        was bad or the host was. Both outcomes are False here, but only one of
        them is the user's problem.
        """
        signed_in, detail = await self.session_ready(), ""
        if not signed_in:
            detail = self._last_session_detail or "tidak tertaut ke Zoom"
        return signed_in, detail

    async def session_ready(self) -> bool:
        """True when the stored session is still signed in to Zoom Web.

        Starts Chromium on demand, so an idle host never holds a browser. A
        signed-in Zoom Web redirects /profile to the dashboard; logged out it
        stays on the sign-in page, so the URL is the cheap check.
        """
        self._last_session_detail = ""
        if not os.path.exists(SESSION_FILE):
            # Reachable during an import only if the write vanished between the
            # save and the check. Say so rather than leaving the caller with a
            # False and no explanation.
            self._last_session_detail = "berkas sesi hilang setelah ditulis"
            return False
        # The lock keeps this from racing launch(): two concurrent _ensure_started
        # calls would launch two Chromium instances and leak the first one.
        async with self._lock:
            await self._ensure_started()
            page = await self._context.new_page()
        try:
            await page.goto("https://zoom.us/profile", wait_until="domcontentloaded", timeout=30_000)
            if "signin" in (page.url or "").lower():
                self._last_session_detail = "cookie ditolak Zoom (kemungkinan kedaluwarsa)"
                return False
            return True
        except PlaywrightError as exc:
            logger.warning("Session check failed: %s", exc)
            self._last_session_detail = f"cek sesi gagal: {type(exc).__name__}"
            return False
        finally:
            await page.close()

    # -- meeting control ---------------------------------------------------

    async def launch(self, meeting_id: str, launch_url: str, passcode: str) -> Dict[str, Any]:
        async with self._lock:
            if self._held_by and self._held_by != meeting_id and self._fresh():
                raise HostBusyError("another meeting is assigned to this host")

            await self._ensure_started()
            await self._reset_page()
            self._held_by = meeting_id
            self._held_at = time.time()
            try:
                await self._join(meeting_id, launch_url, passcode)
            except Exception:
                self._held_by = None
                await self._release_if_idle()
                raise
            return {"accepted": True, "state": "opened", "meeting_id": meeting_id}

    def _fresh(self) -> bool:
        """A hold older than STATE_TTL is abandoned, never a permanent lock."""
        return (time.time() - self._held_at) < STATE_TTL

    async def _join(self, meeting_id: str, launch_url: str, passcode: str) -> None:
        page = await self._context.new_page()
        self._page = page
        await page.goto(launch_url, wait_until="domcontentloaded", timeout=60_000)

        # Zoom Web shows the passcode inline when the link lacks pwd. A start_url
        # carries the zak host key instead of pwd, so this is the only way the
        # passcode reaches the form on that path.
        if passcode:
            field = page.locator("input#password, input[type='password']").first
            try:
                if await field.count() and await field.is_visible():
                    await field.fill(passcode)
                    await page.keyboard.press("Enter")
            except PlaywrightError as exc:
                logger.debug("Passcode field not usable for %s: %s", meeting_id, exc)

        await self._await_joined(page, meeting_id)
        logger.info(
            "Meeting %s joined via Zoom Web (%s)",
            meeting_id,
            "start_url" if "zak=" in launch_url else "join_url",
        )

    async def _await_joined(self, page, meeting_id: str) -> None:
        """Wait until Zoom reports the host is inside the meeting.

        A successful host join is the 'Join Meeting' dialog disappearing and
        the in-meeting toolbar appearing. Everything else (waiting room
        approval, passcode retry, error banner) is a failure, so each one has an
        explicit reason to store in the DB.
        """
        deadline = time.time() + 90
        while time.time() < deadline:
            try:
                if await self._in_meeting(page):
                    return
                reason = await self._failure_reason(page)
                if reason:
                    raise LaunchError(reason)
            except PlaywrightTimeout:
                pass
            await page.wait_for_timeout(1000)

        raise LaunchError("join_timeout: dialog still open after 90s")

    async def _in_meeting(self, page) -> bool:
        toolbar = page.locator(
            "#foot-bar, .footer-button__text, button[class*='leave']"
        ).first
        return bool(await toolbar.count())

    # Zoom's copy varies by locale and client version, so each check matches a
    # short distinctive fragment rather than a full sentence. "passcode you
    # entered is incorrect" is what the web client actually renders; "incorrect
    # password" is the older Workplace wording and is kept as a fallback.
    PASSCODE_HINTS = ("passcode you entered is incorrect", "incorrect password", "invalid passcode")
    WAITING_HINTS = ("waiting for the host", "waiting for your host")
    SIGNOUT_HINTS = ("sign in to join", "log in to join")
    INVALID_ID_HINTS = ("meeting id is not valid", "invalid meeting id")

    async def _failure_reason(self, page) -> Optional[str]:
        try:
            body = (await page.inner_text("body"))[:2000].lower()
        except PlaywrightError:
            return None
        if any(h in body for h in self.PASSCODE_HINTS):
            return "bad_passcode"
        if any(h in body for h in self.WAITING_HINTS):
            return "waiting_room_not_admitted"
        if any(h in body for h in self.INVALID_ID_HINTS):
            return "meeting_id_invalid"
        if any(h in body for h in self.SIGNOUT_HINTS):
            return "session_expired"
        return None

    async def _reset_page(self) -> None:
        if self._page:
            try:
                await self._page.close()
            except PlaywrightError:
                pass
            self._page = None

    async def stop(self, meeting_id: str) -> Dict[str, Any]:
        async with self._lock:
            if self._held_by and self._held_by != meeting_id:
                raise HostBusyError("meeting does not own host")
            await self._reset_page()
            self._held_by = None
            await self._release_if_idle()
            return {"stopped": True}

    async def restart(self) -> Dict[str, Any]:
        async with self._lock:
            # _release(), not a bare context.close(): it also nulls the handles
            # and stops Playwright. Closing the context alone leaves
            # self._context pointing at a dead object, so the next
            # _ensure_started() sees a truthy handle, skips the launch, and the
            # following new_page() dies with TargetClosedError. That only
            # surfaced on the *second* restart - the first one happens to work
            # when lazy Chromium means there is nothing running yet.
            await self._release()
            self._held_by = None
            # A restart exists to re-read the session file, so it must leave a
            # live browser behind rather than wait for the next launch.
            await self._ensure_started()
            return {"restarted": True}

    def snapshot(self) -> Dict[str, Any]:
        return {
            "status": "opened" if self._held_by else "idle",
            "meeting_id": self._held_by or "",
            "zoom_running": bool(self._page),
            "browser_running": self._context is not None,
            "session_ready": os.path.exists(SESSION_FILE),
        }


host = ZoomBrowserHost()


# -- HTTP surface (mirrors remote/main.go) ----------------------------------


def _auth(request: web.Request) -> Optional[str]:
    token = os.getenv("BROWSER_API_TOKEN", "")
    if not token:
        return "BROWSER_API_TOKEN belum dikonfigurasi"
    header = request.headers.get("Authorization", "")
    if secrets.compare_digest(header, f"Bearer {token}"):
        return None
    return "unauthorized"


def _json(payload: Any, status: int = 200) -> web.Response:
    return web.json_response(payload, status=status)


def _meeting_id(request: web.Request, action: str) -> Optional[str]:
    """Extract the meeting id from /meetings/<id>/<action>, or None if malformed."""
    parts = request.path.strip("/").split("/")
    if len(parts) != 3 or parts[0] != "meetings" or parts[2] != action:
        return None
    return parts[1] or None


def _is_zoom_link(url: str) -> bool:
    """True for a Zoom-hosted join/start link.

    The bot forwards Zoom's own start_url here, but this endpoint is reachable
    by anything holding the bearer token, so a start_url is still
    user-controlled input. Without this check a caller could point the headless
    browser at an arbitrary site and have the signed-in Zoom session loaded
    there.
    """
    if not url.startswith("https://"):
        return False
    hostname = urlparse(url).hostname or ""
    return hostname == "zoom.us" or hostname.endswith(".zoom.us")

# -- session import ---------------------------------------------------------

# Cookies that only prove *a* browser touched Zoom. Without one of these the
# export is an anonymous visitor's, and saving it would replace a good session
# with a useless one. These are the names Zoom's web client actually sets on a
# completed sign-in; the check is a floor, not proof - the real proof is
# session_ready() hitting /profile afterwards.
SESSION_MARKER_COOKIES = ("_zm_page_auth", "_zm_multi_ac", "zm_haid", "cred")

# An export of a few hundred cookies is normal; one with tens of thousands is
# someone handing us a data dump. The cap is a guard against a decompression
# bomb, not a policy decision.
MAX_IMPORT_COOKIES = 2000

# A real export of every site in a browser is a few hundred KB. 4 MB leaves
# generous headroom for a full-profile export while still bounding what a
# bearer-token holder can make the service buffer.
MAX_SESSION_UPLOAD_BYTES = 4 * 1024 * 1024


# Playwright accepts only these three spellings. Cookie Editor uses
# no_restriction / lax / strict plus arbitrary casing, so anything unrecognised
# becomes Lax: a too-strict sameSite would stop the cookie being sent at all.
SAME_SITE = {"no_restriction": "None", "lax": "Lax", "strict": "Strict", "none": "None"}


def cookies_to_storage_state(raw: Any) -> Dict[str, Any]:
    """Turn a Cookie Editor export into Playwright's storage_state shape.

    Cookie Editor emits a bare JSON *array* of cookie objects, with its own
    field spellings (expirationDate, hostOnly, storeId). Playwright's
    new_context(storage_state=...) wants
    {"cookies": [...], "origins": [...]}, and each cookie needs
    expires as a *float in seconds*, -1 for a session cookie.

    Accepts the array directly, or an already-wrapped {"cookies": [...]} /
    a Playwright storage_state, so the operator can paste whatever they have.

    Session cookies need the -1 sentinel: Playwright treats a missing expires
    as "already expired" and would silently drop every cookie that has none,
    which is exactly the set that carries the live login.
    """
    if isinstance(raw, dict):
        cookies = raw.get("cookies")
    else:
        cookies = raw
    if not isinstance(cookies, list):
        raise SessionImportError("bukan JSON array cookie, dan bukan objek {'cookies': [...]}")

    kept: list[Dict[str, Any]] = []
    seen_markers: set[str] = set()
    for item in cookies:
        if not isinstance(item, dict):
            continue
        name = str(item.get("name") or "").strip()
        value = item.get("value")
        if not name or not isinstance(value, str):
            continue

        domain = str(item.get("domain") or "").strip().lstrip(".")
        if not domain or not (domain == "zoom.us" or domain.endswith(".zoom.us")):
            continue

        expires = item.get("expirationDate")
        # Cookie Editor omits expirationDate for session cookies; 0 also means
        # "already gone". Both become the -1 sentinel rather than being dropped,
        # because the Zoom login cookies are usually session-scoped. The literal
        # is -1.0 rather than -1 so every expires value in the file is a float:
        # mixing int and float here is legal but makes the output harder to
        # reason about, and the sentinel is the one value compared by eye.
        try:
            expires_at = -1.0 if not expires else float(expires)
        except (TypeError, ValueError):
            expires_at = -1.0
        if expires_at == 0:
            expires_at = -1.0

        kept.append({
            "name": name,
            "value": value,
            "domain": domain,
            "path": str(item.get("path") or "/"),
            "expires": expires_at,
            "httpOnly": bool(item.get("httpOnly", False)),
            "secure": bool(item.get("secure", False)),
            "sameSite": SAME_SITE.get(str(item.get("sameSite") or "lax").lower(), "Lax"),
        })
        if name in SESSION_MARKER_COOKIES:
            seen_markers.add(name)

    if not kept:
        raise SessionImportError("tidak ada cookie .zoom.us yang bisa dipakai di JSON ini")
    if not seen_markers:
        raise SessionImportError(
            "tidak ada cookie sesi Zoom (" + ", ".join(SESSION_MARKER_COOKIES) + "); "
            "ini mungkin cookie browser yang belum login, bukan akun host"
        )
    if len(kept) > MAX_IMPORT_COOKIES:
        raise SessionImportError(f"{len(kept)} cookie, melebihi batas {MAX_IMPORT_COOKIES}")

    # origins: Zoom's session check reads cookies, not localStorage, so an empty
    # list is correct and honest rather than inventing origins we never saw.
    return {"cookies": kept, "origins": []}


def save_session_file(state: Dict[str, Any]) -> int:
    """Replace SESSION_FILE atomically, keeping the old one if anything fails.

    A half-written session file locks the host out, and the operator's previous
    session is the only working copy they have. os.replace is atomic within a
    filesystem, so a crash mid-write leaves the old file intact rather than an
    empty one that would look like a successful import.
    """
    payload = json.dumps(state, separators=(",", ":"))
    tmp = SESSION_FILE + ".tmp"
    with open(tmp, "w", encoding="utf-8") as handle:
        handle.write(payload)
        handle.flush()
        os.fsync(handle.fileno())
    os.chmod(tmp, 0o600)
    os.replace(tmp, SESSION_FILE)
    return len(state.get("cookies") or [])


def _parse_uploaded_session(body: bytes) -> Dict[str, Any]:
    """Decode a multipart file upload into a storage_state dict.

    Only the .zoom.us cookies are kept, so a full-browser export (which carries
    every site the operator ever visited) does not become a Zoom session file
    that also holds unrelated credentials.
    """
    try:
        text = body.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise SessionImportError("file bukan teks UTF-8") from exc
    try:
        raw = json.loads(text)
    except json.JSONDecodeError as exc:
        raise SessionImportError(f"JSON tidak valid: {exc.msg} (baris {exc.lineno})") from exc
    return cookies_to_storage_state(raw)

def make_app() -> web.Application:
    app = web.Application()
    app["host"] = host

    async def health(_request: web.Request) -> web.Response:
        return _json({"ok": True, "zoom_running": bool(host._page)})

    async def status(request: web.Request) -> web.Response:
        # session_ready is a live check because the session file can exist and
        # still be expired on Zoom's side; the operator needs to see that
        # difference from a running browser.
        payload = host.snapshot()
        payload["session_ready"] = await host.session_ready()
        return _json(payload)

    async def launch(request: web.Request) -> web.Response:
        meeting_id = _meeting_id(request, "launch")
        if not meeting_id:
            raise web.HTTPBadRequest(text="invalid path")
        body = await request.json()
        # Zoom's meeting object (GET /v2/meetings/{id}) exposes two links:
        #   start_url  "https://us05web.zoom.us/s/<id>?zak=<host key>"  -> host
        #   join_url   "https://us05web.zoom.us/j/<id>?pwd=<passcode>"  -> participant
        # start_url is preferred because it carries the host key, so the
        # browser becomes the host rather than the first person to arrive.
        # join_url stays as a fallback for accounts where the zak scope is not
        # granted, and for meetings whose start_url Zoom did not return.
        start_url = body.get("start_url") or ""
        join_url = body.get("join_url") or ""
        if start_url:
            target = start_url
        elif join_url:
            target = join_url
        else:
            raise web.HTTPBadRequest(text="no start_url or join_url in request")

        if not _is_zoom_link(target):
            raise web.HTTPBadRequest(
                text=f"refusing non-Zoom launch URL: {target[:32]}...",
            )
        try:
            result = await host.launch(meeting_id, target, body.get("passcode", ""))
            return _json(result)
        except HostBusyError as exc:
            raise web.HTTPConflict(text=str(exc)) from exc
        except (LaunchError, PlaywrightError) as exc:
            raise web.HTTPInternalServerError(text=f"{type(exc).__name__}: {exc}") from exc

    async def stop(request: web.Request) -> web.Response:
        meeting_id = _meeting_id(request, "stop")
        if not meeting_id:
            raise web.HTTPBadRequest(text="invalid path")
        try:
            return _json(await host.stop(meeting_id))
        except HostBusyError as exc:
            raise web.HTTPConflict(text=str(exc)) from exc

    async def restart(_request: web.Request) -> web.Response:
        return _json(await host.restart())

    async def check_session_status(request: web.Request) -> web.Response:
        """Verify the stored session against Zoom and report why it failed.

        /status already answers this, but only as a bool. A bool cannot tell
        the operator the one thing they need: whether their cookies are stale
        or the check itself failed. Both are False, and only the first one is
        the operator's fault - so the other one is a wasted re-upload.

        check_session() exists precisely to separate those two outcomes and
        was never wired to a route. This is that wiring.

        Slower than /status: it starts Chromium and hits zoom.us, up to 30s. The
        bot answers the callback first, so the user is not left staring at a
        spinner on a dead button.
        """
        signed_in, detail = await host.check_session()
        return _json({
            "session_ready": signed_in,
            "detail": detail,
            "stored": os.path.exists(SESSION_FILE),
        })

    async def import_session(request: web.Request) -> web.Response:
        """Accept a Cookie Editor export and make it the live Zoom session.

        The operator uploads a JSON file from Telegram; nothing here is a Zoom
        credential this service has to be trusted with beyond the bearer token
        it already holds.

        The body is the raw cookie JSON, not a multipart form. Telegram hands
        the bot a file_id, and the bot streams those bytes straight through, so
        a multipart envelope would be a second encoding of the same thing.
        """
        body = await request.read()
        if len(body) > MAX_SESSION_UPLOAD_BYTES:
            raise web.HTTPRequestEntityTooLarge(
                max_size=MAX_SESSION_UPLOAD_BYTES, actual_size=len(body),
            )
        try:
            state = _parse_uploaded_session(body)
        except SessionImportError as exc:
            raise web.HTTPBadRequest(text=str(exc)) from exc

        # Reloading drops the browser the running meeting is sitting in, so an
        # import during a live meeting would silently end someone's call. The
        # operator has to end the meeting first and retry.
        if host._held_by and host._fresh():
            raise web.HTTPConflict(
                text=f"meeting {host._held_by} sedang berjalan; akhiri dulu sebelum import sesi",
            )

        count = save_session_file(state)
        logger.info("Session imported (%d cookies)", count)

        # Reload the browser context against the new file, otherwise the running
        # context keeps the old cookies and the import looks like it did nothing.
        # The write is what matters; reloading only makes it take effect, so a
        # failure here is reported rather than raised. Faking a 500 would tell
        # the operator their upload was lost when it is sitting on disk.
        # restart() already dropped the stale context, so the next launch()
        # re-reads the new file on its own.
        reload_error = ""
        try:
            await host.restart()
            live, detail = await host.check_session()
        except Exception as exc:  # noqa: BLE001 - any failure is just "unverified"
            live = False
            reload_error = f"{type(exc).__name__}: {exc}"
            logger.warning("Session saved but not verified: %s", reload_error)
        else:
            # An unverified import must always carry a reason. A False with an
            # empty string tells the operator nothing: they cannot tell a
            # rejected cookie from a broken host, and those need different fixes.
            if not live:
                reload_error = detail
            logger.info("Session import verified against Zoom: signed_in=%s", live)
        return _json({
            "imported": True,
            "cookies": count,
            "signed_in": live,
            "reload_error": reload_error,
        })

    def guarded(handler):
        async def wrapper(request: web.Request) -> web.Response:
            if error := _auth(request):
                raise web.HTTPUnauthorized(text=error)
            return await handler(request)

        return wrapper

    # /health stays unauthenticated, matching the Kasm controller.
    app.router.add_get("/health", health)
    app.router.add_get("/status", guarded(status))
    app.router.add_post("/meetings/{meeting_id}/launch", guarded(launch))
    app.router.add_post("/meetings/{meeting_id}/stop", guarded(stop))
    app.router.add_post("/zoom/restart", guarded(restart))
    app.router.add_post("/zoom/session", guarded(import_session))
    app.router.add_post("/zoom/session/check", guarded(check_session_status))

    # No Chromium at boot: launch() and session_ready() start it on demand, and
    # stop() releases it. See ZoomBrowserHost._ensure_started.
    return app


async def main() -> None:
    app = make_app()
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "0.0.0.0", API_PORT)
    await site.start()
    logger.info("Zoom browser host listening on :%s (Chromium starts on first launch)", API_PORT)
    try:
        await asyncio.Event().wait()
    finally:
        await host.stop()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
