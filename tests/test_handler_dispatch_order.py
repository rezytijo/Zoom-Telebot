"""Regression test for the aiogram dependency-injection order bug.

Production traceback, from a real upload attempt:

    TypeError: receive_session_file() got multiple values for argument 'bot'
    ...
      File "/app/bot/session_handlers.py", line 112, in receive_session_file

Every file upload failed at the last step. The user saw nothing at all - not
even the "Import ditolak" error the code was written to give them.

Why no test caught it: every other test in this repo calls handlers
*directly*, as ``await sh.receive_session_file(msg, bot, state)``. That always
works, no matter how the parameters are ordered. The bug only exists in how
aiogram invokes a handler, so a test that skips aiogram's own machinery cannot
see it.

So this file goes through the real mechanism: a real aiogram Handler wrapping
the real callback, invoked the way the dispatcher invokes it -
``callback(event, **kwargs)`` with the event positional and bot/state as
kwargs. That is exactly what Handler.call does:

    wrapped = partial(self.callback, *args, **self._prepare_kwargs(kwargs))
"""

from __future__ import annotations

import inspect
import sys
from pathlib import Path

import pytest
from aiogram.dispatcher.event.handler import HandlerObject

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import bot.session_handlers as sh  # noqa: E402

# -- the bug ---------------------------------------------------------------

async def test_the_callback_survives_how_aiogram_actually_calls_it() -> None:
    """The regression itself.

    Event positional, bot and state as keywords - the exact shape
    ``Dispatcher._listen_update`` produces. A ``bot: Bot`` first parameter
    binds the event to the bot slot, and the real ``bot`` kwarg then collides.
    """
    sent: dict = {}

    async def receive_session_file(msg, bot, state):
        sent["msg"] = msg
        sent["bot"] = bot
        sent["state"] = state

    handler = HandlerObject(callback=receive_session_file)

    event, bot, state = object(), object(), object()
    await handler.call(event, bot=bot, state=state)

    assert sent == {"msg": event, "bot": bot, "state": state}


def test_the_real_handler_takes_the_event_first() -> None:
    """Guards the actual shipped function, not a copy of it.

    Checking the first positional parameter is enough: aiogram passes the event
    positionally, so whatever the first parameter is, it receives the event. A
    dependency like ``bot`` in that slot is always a bug.
    """
    params = list(inspect.signature(sh.receive_session_file).parameters)
    assert params[0] == "msg", (
        f"receive_session_file's first parameter is {params[0]!r}, not 'msg'. "
        "aiogram passes the event positionally, so the first parameter must be "
        "the message. See the docstring for the failure this causes."
    )


# -- the same class of bug, everywhere -------------------------------------

def _registered_handlers() -> list[tuple[str, str, str]]:
    """Every handler actually registered on a router, and its first parameter.

    Read from the router rather than from the module namespace. The modules
    re-export a lot of plain helper functions - add_meeting, get_user_by_telegram_id
    and friends are imported from db.db and have nothing to do with Telegram
    dispatch. Only a function the router has wrapped is a handler.
    """
    import bot.cloud_recording_handlers as cloud
    import bot.handlers as handlers
    import bot.session_handlers as session_handlers

    found = []
    for module in (handlers, session_handlers, cloud):
        router = getattr(module, "router", None)
        if router is None:
            continue
        for observer_name in dir(router):
            observer = getattr(router, observer_name)
            for handler in getattr(observer, "handlers", ()) or ():
                callback = handler.callback
                try:
                    params = list(inspect.signature(callback).parameters)
                except (TypeError, ValueError):
                    continue
                if not params:
                    continue
                found.append((f"{module.__name__}.{callback.__name__}", observer_name, params[0]))
    return found


# aiogram's own event names, so "first parameter is not an event" is decidable
# without guessing at every parameter name in the codebase.
_EVENT_FIRST = {
    "msg", "message", "c", "callback", "query", "event", "update", "callback_query",
}


def test_no_handler_puts_a_dependency_in_the_event_slot() -> None:
    """Sweep every registered handler, not just the one that broke.

    The failure mode is silent and identical everywhere: the route registers,
    the filter matches, and the handler raises TypeError on the first real
    message. A test that only checks the handler we happen to know about will
    miss the next one.
    """
    offenders = [
        (fn, kind, first)
        for fn, kind, first in _registered_handlers()
        if first not in _EVENT_FIRST
    ]
    assert not offenders, (
        "aiogram passes the event as the first positional argument, so a handler "
        "whose first parameter is a DI dependency raises "
        "'got multiple values for argument <name>' on every message:\n"
        + "\n".join(f"  {fn} ({kind}): first param is {first!r}" for fn, kind, first in offenders)
    )


def test_the_sweep_actually_finds_the_handlers() -> None:
    """A sweep that finds nothing is indistinguishable from a sweep that is
    broken. Pin the expected size so it cannot quietly pass on an empty or
    mis-imported list."""
    handlers_found = _registered_handlers()
    assert len(handlers_found) > 90, (
        f"sweep looks broken: only {len(handlers_found)} handlers found, "
        "expected the full router registration"
    )
    # And the one that actually broke must be in the sweep, or the sweep is
    # looking at the wrong objects.
    names = {fn for fn, _kind, _first in handlers_found}
    assert "bot.session_handlers.receive_session_file" in names, (
        "receive_session_file is not in the sweep - the fixture that broke in "
        "production is not being inspected, so the sweep proves nothing"
    )
