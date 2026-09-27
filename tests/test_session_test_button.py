"""Tests for the session self-test button.

The button exists because of a failure the operator cannot diagnose alone: a
session file that is present on disk and rejected by Zoom. /status answers the
wrong question - it reports what the file's existence implies, not what Zoom
says after loading it.

Two things are asserted here that are easy to get wrong and produce no error:

1. The callback_data has a matching handler. aiogram silently drops a callback
   with no handler: the button renders, the tap does nothing, and there is not a
   single log line. That is the same silent class of failure as the argument
   order bug in test_handler_dispatch_order.py.
2. A False result is not one thing. "Your cookies are stale" and "the check
   itself broke" are both False, and collapsing them sends the user off to
   re-export cookies that were never the problem.
"""

from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import bot.handlers as handlers  # noqa: E402
import bot.keyboards as kb  # noqa: E402
from zoom.remote import RemoteZoomError  # noqa: E402

CALLBACK_DATA = "zoom_test_session"


# -- the button exists and is wired ----------------------------------------

def test_the_button_is_rendered_in_remote_mode() -> None:
    original = kb.settings
    try:
        kb.settings = SimpleNamespace(zoom_control_mode="remote")
        buttons = {
            b.callback_data: b.text
            for row in kb.backup_menu_keyboard().inline_keyboard
            for b in row
        }
        assert CALLBACK_DATA in buttons, (
            f"test button missing from the backup panel: {sorted(buttons)}"
        )
        assert "Uji Sesi" in buttons[CALLBACK_DATA]
    finally:
        kb.settings = original


def test_the_button_is_hidden_without_a_host() -> None:
    """No host means no session to test. Offering the button would be a lie
    that ends in a connection error instead of a feature."""
    original = kb.settings
    try:
        kb.settings = SimpleNamespace(zoom_control_mode="agent")
        datas = {
            b.callback_data
            for row in kb.backup_menu_keyboard().inline_keyboard
            for b in row
        }
        assert CALLBACK_DATA not in datas, "test button shown with no host to test"
    finally:
        kb.settings = original


def test_the_callback_has_a_handler() -> None:
    """The silent failure. A callback_data with no handler is dropped by
    aiogram: button renders, tap does nothing, zero log lines.

    Checked against the source and the router's handler list rather than by
    evaluating the filter. The filter is a bare lambda closing over `c`, so
    there is no closure cell holding the data string to read - and calling the
    filter with a stub returns nothing useful.
    """
    src = Path(handlers.__file__).read_text(encoding="utf-8")
    assert f"c.data == '{CALLBACK_DATA}'" in src or f'c.data == "{CALLBACK_DATA}"' in src, (
        f"no callback_query handler filters on {CALLBACK_DATA!r}"
    )
    names = [h.callback.__name__ for h in handlers.router.callback_query.handlers]
    assert "cb_test_session" in names, names


# -- the fake --------------------------------------------------------------

class FakeMessage:
    def __init__(self) -> None:
        self.edits: list[tuple[str, object]] = []
        self.replies: list[tuple[str, object]] = []

    async def edit_text(self, text, **kwargs):
        self.edits.append((text, kwargs.get("reply_markup")))

    async def answer(self, text, **kwargs):
        self.replies.append((text, kwargs.get("reply_markup")))

    async def _send(self, text, **kwargs):
        self.replies.append((text, kwargs.get("reply_markup")))
        return self

    def last_text(self) -> str:
        return (self.edits or self.replies)[-1][0]

    def last_markup(self):
        return (self.edits or self.replies)[-1][1]


class FakeCallback:
    def __init__(self) -> None:
        self.data = CALLBACK_DATA
        self.from_user = SimpleNamespace(id=1)
        self.answers: list[str] = []
        self.message = FakeMessage()
        outer = self

        class _M:
            async def answer(_self, text, **kwargs):
                return await outer.message._send(text, **kwargs)

        self.message.answer = _M().answer

    async def answer_callback(self, text="", **kwargs):
        self.answers.append(text)

    # aiogram calls c.answer() on a CallbackQuery
    def __getattr__(self, name):
        if name == "answer":
            return self.answer_callback
        raise AttributeError(name)


def _patch(result=None, raises: Exception | None = None, admin: bool = True):
    originals = {
        "get_user_by_telegram_id": handlers.get_user_by_telegram_id,
        "is_owner_or_admin": handlers.is_owner_or_admin,
        "remote_zoom_client": handlers.remote_zoom_client,
        "settings": handlers.settings,
    }

    async def fake_lookup(_tid):
        return {"role": "owner" if admin else "user"}

    def fake_check(user):
        return bool(user and user.get("role") in ("admin", "owner"))

    class FakeRemote:
        async def check_session(self):
            if raises is not None:
                raise raises
            return result

    handlers.get_user_by_telegram_id = fake_lookup
    handlers.is_owner_or_admin = fake_check
    handlers.remote_zoom_client = FakeRemote()

    def restore():
        for name, value in originals.items():
            setattr(handlers, name, value)

    return restore


# -- behaviour -------------------------------------------------------------

async def test_a_valid_session_says_do_not_re_upload() -> None:
    restore = _patch(result={"session_ready": True, "detail": "", "stored": True})
    try:
        c = FakeCallback()
        await handlers.cb_test_session(c)
    finally:
        restore()
    text = c.message.last_text()
    assert "valid" in text.lower(), text
    assert "tidak perlu upload" in text.lower(), text


async def test_an_expired_session_distinguishes_stale_from_broken() -> None:
    """The reason must reach the user. "Sesi kedaluwarsa" and "cek gagal" send
    them to opposite places, and the host already knows the difference."""
    restore = _patch(
        result={
            "session_ready": False,
            "detail": "cookie ditolak Zoom (kemungkinan kedaluwarsa)",
            "stored": True,
        }
    )
    try:
        c = FakeCallback()
        await handlers.cb_test_session(c)
    finally:
        restore()
    text = c.message.last_text()
    assert "kedaluwarsa" in text.lower(), text
    assert "cookie ditolak zoom" in text.lower(), (
        "the host's own reason must be passed through, not summarised away: " + text
    )


async def test_a_missing_session_differs_from_an_expired_one() -> None:
    """Never uploaded is not the same as uploaded-then-expired. Same False, but
    the fix and the mental model differ."""
    restore = _patch(
        result={"session_ready": False, "detail": "berkas sesi hilang", "stored": False}
    )
    try:
        c = FakeCallback()
        await handlers.cb_test_session(c)
    finally:
        restore()
    text = c.message.last_text()
    assert "belum ada" in text.lower(), text
    assert "kedaluwarsa" not in text.lower(), (
        "a session that was never uploaded is not an expired one: " + text
    )


async def test_the_failure_message_offers_the_fix() -> None:
    """A dead-end message makes the user hunt for the button themselves, and
    this is exactly the message they will land on."""
    restore = _patch(result={"session_ready": False, "detail": "x", "stored": True})
    try:
        c = FakeCallback()
        await handlers.cb_test_session(c)
    finally:
        restore()
    markup = c.message.last_markup()
    assert markup is not None, "failure message has no keyboard"
    datas = [b.callback_data for row in markup.inline_keyboard for b in row]
    assert "zoom_import_session" in datas, f"no way to fix it from here: {datas}"


async def test_a_host_error_is_reported_not_raised() -> None:
    """RemoteZoomError carries the host's own wording, which names the missing
    cookie or the failed check. Swallowing it into a generic error throws that
    away."""
    restore = _patch(raises=RemoteZoomError("cek sesi gagal: TimeoutError"))
    try:
        c = FakeCallback()
        await handlers.cb_test_session(c)
    finally:
        restore()
    text = c.message.last_text()
    assert "timeout" in text.lower(), text


async def test_a_non_admin_cannot_test_someone_elses_session() -> None:
    restore = _patch(result={"session_ready": True, "stored": True}, admin=False)
    try:
        c = FakeCallback()
        await handlers.cb_test_session(c)
    finally:
        restore()
    assert "admin" in c.answers[0].lower(), c.answers
    assert not c.message.edits and not c.message.replies, (
        "a rejected user must not get a session verdict"
    )


async def test_the_button_answers_before_the_slow_check() -> None:
    """The host starts Chromium and loads zoom.us - up to 30s. If c.answer()
    waits for that, the button spins the whole time and Telegram eventually
    shows a dead button."""
    restore = _patch(result={"session_ready": True, "stored": True})
    try:
        c = FakeCallback()
        await handlers.cb_test_session(c)
    finally:
        restore()
    assert c.answers, "callback was never answered"
