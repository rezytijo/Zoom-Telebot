"""Self-check for the Telegram-side Zoom session import.

The host half of this feature is covered by remote_browser/selfcheck.py and is
proven against a real Zoom login. This covers the half that only fails in
production: the bot-side flow. Existing tests in tests/ all need live Telegram
credentials and a real session, so none of them can assert what happens when a
user attaches a 5 MB file, or when a non-admin message lands in a state an admin
armed.

Everything here is fake. No network, no Telegram, no Zoom.

    pytest tests/test_bot_session_import.py     # or plain: python tests\\...py

The filename matters. It used to be `bot_session_import_selfcheck.py`, which
`pytest tests/` never collected because it did not start with `test_` - eleven
assertions that ran only when someone remembered to invoke the file by hand.
Green but untriggered is the failure mode this file exists to rule out.
"""

from __future__ import annotations

import asyncio
import os
import sys
from contextlib import contextmanager
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
os.environ.setdefault("ZOOM_CONTROL_MODE", "remote")

import bot.session_handlers as sh  # noqa: E402


# -- fakes -----------------------------------------------------------------


class FakeFile:
    def __init__(self, payload: bytes) -> None:
        self._payload = payload

    async def download(self) -> bytes:
        return self._payload


class FakeBot:
    """Only the one call the handler makes, which the real Bot also signs."""

    def __init__(self, payload: bytes) -> None:
        self.payload = payload
        self.requested_ids: list[str] = []

    async def get_file(self, file_id: str) -> FakeFile:
        self.requested_ids.append(file_id)
        return FakeFile(self.payload)


class FakeMessage:
    def __init__(self, text: str = "", file_id: str = "", file_size: int = 0) -> None:
        self.text = text
        self.from_user = SimpleNamespace(id=1)
        self.document = (
            SimpleNamespace(file_id=file_id, file_size=file_size) if file_id else None
        )
        self.answers: list[str] = []

    async def answer(self, text: str, **kwargs) -> "FakeMessage":
        """The real Bot.answer returns the sent Message. The handler relies on
        that: it sends a placeholder, then edits that same object."""
        self.answers.append(text)
        return self

    async def edit_text(self, text: str, **kwargs) -> None:
        self.answers.append(text)

    def sent(self) -> str:
        return "\n".join(self.answers)


class FakeState:
    def __init__(self) -> None:
        self.current = None
        self.cleared = False

    async def set_state(self, state) -> None:
        self.current = state

    async def get_state(self) -> None:
        return self.current

    async def clear(self) -> None:
        self.cleared = True
        self.current = None

class FakeCallbackQuery:
    """A tap on the button. Handlers reach for three things: c.answer() with
    an optional alert, c.from_user.id, and c.message.edit_text (falling back to
    c.message.reply when the panel is already showing that text)."""

    def __init__(self, from_user_id: int = 1) -> None:
        self.data = "zoom_import_session"
        self.from_user = SimpleNamespace(id=from_user_id)
        self.answers: list[str] = []
        self.state = FakeState()
        self.message = SimpleNamespace(edits=[], replies=[])

        outer = self

        class _Msg:
            async def edit_text(_self, text, **kwargs):
                outer.message.edits.append(text)

            async def reply(_self, text, **kwargs):
                outer.message.replies.append(text)

        self.message.edit_text = _Msg().edit_text
        self.message.reply = _Msg().reply

    async def answer(self, text: str = "", **kwargs) -> None:
        self.answers.append(text)


def _patch(*, admin: bool = True, mode: str = "remote", import_result=None, raises=None):
    """Swap the four things the handler reaches for. Returns a restore fn."""
    originals = {
        "is_owner_or_admin": sh.is_owner_or_admin,
        "get_user_by_telegram_id": sh.get_user_by_telegram_id,
        "settings": sh.settings,
        "remote_zoom_client": sh.remote_zoom_client,
    }
    seen: dict = {"payloads": []}

    class FakeSettings:
        zoom_control_mode = mode

    class FakeRemote:
        async def import_session(self, payload: bytes):
            seen["payloads"].append(payload)
            if raises is not None:
                raise raises
            return import_result

    # NOT async. The handler calls is_owner_or_admin(...) and checks the result
    # with `if not ...`, exactly as it does the real one. An async fake would
    # return a coroutine, which is always truthy, so every permission check in
    # these tests would silently pass.
    def fake_check(user):
        return bool(user and user.get("role") in ("admin", "owner"))

    async def fake_lookup(_telegram_id):
        return {"role": "owner" if admin else "user"}

    sh.is_owner_or_admin = fake_check
    sh.get_user_by_telegram_id = fake_lookup
    sh.settings = FakeSettings()
    sh.remote_zoom_client = FakeRemote()

    def restore():
        for name, value in originals.items():
            setattr(sh, name, value)

    return restore, seen


# -- tests -----------------------------------------------------------------


def test_button_only_in_remote_mode() -> None:
    import bot.keyboards as kb

    original = kb.settings
    try:
        # kb imports settings directly, so patching session_handlers' reference
        # would not reach it - this is the trap that made the first run fail.
        kb.settings = SimpleNamespace(zoom_control_mode="remote")
        labels = [b.text for row in kb.backup_menu_keyboard().inline_keyboard for b in row]
        assert any("Import Sesi" in t for t in labels), f"button missing in remote mode: {labels}"

        # In agent mode there is no remote host to import into, so the button
        # would be a lie. It must not appear.
        kb.settings = SimpleNamespace(zoom_control_mode="agent")
        labels = [b.text for row in kb.backup_menu_keyboard().inline_keyboard for b in row]
        assert not any("Import Sesi" in t for t in labels), f"button shown without a host: {labels}"
    finally:
        kb.settings = original
    print("button gated on remote mode OK")


def test_router_registered_before_catch_all() -> None:
    """bot/handlers.py ends with a catch-all matching any "/..." message.

    If the session router is registered after it, /cancel is consumed there and
    a pending import cannot be abandoned. This is a load-order property, so it
    is asserted on the source rather than hoped for.
    """
    src = (Path(__file__).resolve().parents[1] / "bot" / "main.py").read_text(encoding="utf-8")
    import_pos = src.index("include_router(session_router)")
    main_pos = src.index("include_router(router)")
    assert import_pos < main_pos, "session_router must be included before the catch-all router"
    print("router ordering OK")


async def test_verified_import_reports_success() -> None:
    payload = b'[{"name":"cred","domain":".zoom.us"}]'
    restore, seen = _patch(import_result={"imported": True, "cookies": 12, "signed_in": True})
    try:
        msg = FakeMessage(file_id="F1", file_size=len(payload))
        state = FakeState()
        await sh.receive_session_file(msg, FakeBot(payload), state)
    finally:
        restore()
    reply = msg.sent()
    assert seen["payloads"] == [payload], "file bytes must reach the host undecoded"
    assert "berhasil" in reply.lower(), reply
    assert "12" in reply, "the operator should be told how many cookies landed"
    assert state.cleared, "state must be released after a handled upload"
    print("verified import reports success OK")


async def test_unverified_import_warns_instead_of_claiming_success() -> None:
    """A stored-but-rejected session is the dangerous case: reporting plain
    success sends the operator off to test a host that cannot join."""
    restore, _ = _patch(
        import_result={
            "imported": True, "cookies": 3, "signed_in": False,
            "reload_error": "cookie ditolak Zoom",
        }
    )
    try:
        msg = FakeMessage(file_id="F1", file_size=10)
        await sh.receive_session_file(msg, FakeBot(b"[]"), FakeState())
    finally:
        restore()
    reply = msg.sent()
    assert "belum terverifikasi" in reply.lower(), reply
    assert "cookie ditolak Zoom" in reply, "the host's reason must be passed through"
    print("unverified import warns OK")


async def test_rejection_reason_surfaces() -> None:
    from zoom import RemoteZoomError

    restore, _ = _patch(raises=RemoteZoomError("tidak ada cookie sesi Zoom"))
    try:
        msg = FakeMessage(file_id="F1", file_size=10)
        await sh.receive_session_file(msg, FakeBot(b"[]"), FakeState())
    finally:
        restore()
    reply = msg.sent()
    assert "ditolak" in reply.lower(), reply
    assert "tidak ada cookie sesi Zoom" in reply, "the converter's own reason is the useful part"
    print("rejection reason surfaces OK")


async def test_non_admin_cannot_import() -> None:
    """The state is set by an admin, but in a shared chat anyone can post into
    it. Permission is re-checked at the point of use."""
    restore, seen = _patch(admin=False, import_result={"cookies": 1, "signed_in": True})
    try:
        msg = FakeMessage(file_id="F1", file_size=10)
        await sh.receive_session_file(msg, FakeBot(b"[]"), FakeState())
    finally:
        restore()
    assert seen["payloads"] == [], "a rejected uploader's bytes must never be sent"
    assert "Admin" in msg.sent()
    print("non-admin blocked OK")


async def test_wrong_control_mode_is_refused() -> None:
    restore, seen = _patch(mode="agent", import_result={"cookies": 1, "signed_in": True})
    try:
        msg = FakeMessage(file_id="F1", file_size=10)
        await sh.receive_session_file(msg, FakeBot(b"[]"), FakeState())
    finally:
        restore()
    assert seen["payloads"] == [], "nothing should be sent outside remote mode"
    assert "remote" in msg.sent().lower()
    print("wrong control mode refused OK")


async def test_oversized_file_is_refused_before_download() -> None:
    restore, seen = _patch(import_result={"cookies": 1, "signed_in": True})
    try:
        bot = FakeBot(b"[]")
        msg = FakeMessage(file_id="F1", file_size=sh.MAX_UPLOAD_BYTES + 1)
        await sh.receive_session_file(msg, bot, FakeState())
    finally:
        restore()
    assert bot.requested_ids == [], "an oversized file must not be downloaded at all"
    assert "terlalu besar" in msg.sent().lower()
    print("oversized file refused early OK")


async def test_cancel_clears_state() -> None:
    msg = FakeMessage(text="/cancel")
    state = FakeState()
    await sh.cancel_import(msg, state)
    assert state.cleared and "batal" in msg.sent().lower()
    print("cancel clears state OK")


async def test_stray_text_does_not_import() -> None:
    """A chatty user typing instead of attaching must not end the flow or,
    worse, get treated as the payload."""
    restore, seen = _patch(import_result={"cookies": 1, "signed_in": True})
    try:
        await sh.wrong_text(FakeMessage(text="halo bot"))
    finally:
        restore()
    assert seen["payloads"] == [], "plain text must never be forwarded as a session"
    print("stray text ignored OK")


def test_no_cookie_values_in_source() -> None:
    """The module must never print a cookie back. Guards against a future
    'helpful' debug line quoting the payload."""
    src = Path(sh.__file__).read_text(encoding="utf-8")
    for token in ("payload.decode", "payload[:", "cookies}", "cookie["):
        assert token not in src, f"session_handlers must not surface {token}"
    print("no cookie echo in source OK")

# -- the button itself ------------------------------------------------------
# The symptom this file exists for was "I cannot see the Import Session
# button". Everything below closes that hole from the code side. It cannot
# prove the *running container* has the code - only a rebuild and a real
# message can - but it proves the workspace does, and it turns every
# plausible way of losing the button into a red test.

def _find_button(markup, callback_data: str):
    for row in markup.inline_keyboard:
        for button in row:
            if button.callback_data == callback_data:
                return button
    return None

@contextmanager
def _remote_mode():
    """keyboards.py imports settings directly from config, so patching the
    handler module's reference would never reach it. That mismatch cost a
    debugging round once; the direct import is the reason this helper exists."""
    import bot.keyboards as kb
    original = kb.settings
    kb.settings = SimpleNamespace(zoom_control_mode="remote")
    try:
        yield kb
    finally:
        kb.settings = original

def test_backup_panel_renders_the_import_button() -> None:
    """The exact callback_data matters, not just that a button exists: a
    typo in callback_data renders a good-looking button that Telegram
    delivers to nobody."""
    with _remote_mode() as kb:
        markup = kb.backup_menu_keyboard()
        button = _find_button(markup, "zoom_import_session")
        rendered = [b.callback_data for r in markup.inline_keyboard for b in r]
        assert button is not None, f"zoom_import_session absent: {rendered}"
        assert "Import Sesi" in button.text, button.text

def test_import_button_is_reachable_from_the_main_menu() -> None:
    """A button on an unreachable panel is not a feature. Assert the whole
    click path an admin walks: main menu -> Backup & Restore -> import."""
    with _remote_mode() as kb:
        main = kb.main_menu_keyboard(user_role="admin")
        assert _find_button(main, "menu_backup") is not None, \
            "admin menu no longer offers Backup & Restore"
        assert _find_button(kb.backup_menu_keyboard(), "zoom_import_session") is not None

def test_import_button_unreachable_for_a_regular_user() -> None:
    """The panel is admin-only; the main menu is the gate that keeps a plain
    user from ever being offered the path."""
    with _remote_mode() as kb:
        main = kb.main_menu_keyboard(user_role="user")
        assert _find_button(main, "menu_backup") is None, \
            "a non-admin must not be offered the backup menu"

def test_button_callback_has_a_handler() -> None:
    """A callback_data with no matching callback_query handler is dropped
    silently by aiogram: the button renders, the tap does nothing, and no log
    line explains it. Closest static proxy for the reported symptom."""
    src = Path(sh.__file__).read_text(encoding="utf-8")
    assert 'c.data == "zoom_import_session"' in src, \
        "no callback_query handler filters on 'zoom_import_session'"
    names = [h.callback.__name__ for h in sh.router.callback_query.handlers]
    assert "cb_import_session" in names, names

async def test_callback_rejects_a_non_admin_before_arming_the_state() -> None:
    """The tap is the only place the state gets set. If a non-admin can arm
    it, they then post a file into a state an admin opened."""
    with _remote_mode():
        restore, _ = _patch(admin=False, import_result={"cookies": 1, "signed_in": True})
        try:
            cb = FakeCallbackQuery(from_user_id=2)
            state = FakeState()
            await sh.cb_import_session(cb, state)
        finally:
            restore()
    assert not state.current, "a rejected tap must not arm the import state"
    assert any("Admin" in a for a in cb.answers), cb.answers

async def test_callback_arms_the_state_for_an_admin() -> None:
    """The positive half: a legitimate tap must actually open the flow, and
    the export steps must be shown so the user knows what to attach."""
    with _remote_mode():
        restore, _ = _patch(admin=True, import_result={"cookies": 1, "signed_in": True})
        try:
            cb = FakeCallbackQuery(from_user_id=1)
            state = FakeState()
            await sh.cb_import_session(cb, state)
        finally:
            restore()
    assert state.current is sh.SessionImportStates.waiting_for_file, \
        f"state not armed: {state.current!r}"
    assert cb.message.edits, "the panel should be replaced with the export steps"
    assert any("JSON" in e for e in cb.message.edits), cb.message.edits


async def main() -> None:
    test_button_only_in_remote_mode()
    test_router_registered_before_catch_all()
    await test_verified_import_reports_success()
    await test_unverified_import_warns_instead_of_claiming_success()
    await test_rejection_reason_surfaces()
    await test_non_admin_cannot_import()
    await test_wrong_control_mode_is_refused()
    await test_oversized_file_is_refused_before_download()
    await test_cancel_clears_state()
    await test_stray_text_does_not_import()
    test_no_cookie_values_in_source()
    print("\nbot_session_import selfcheck: all assertions passed")


if __name__ == "__main__":
    asyncio.run(main())
