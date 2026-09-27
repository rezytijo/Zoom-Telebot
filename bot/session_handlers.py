"""Import a Zoom Web session into the host, from inside Telegram.

The alternative was running scripts/zoom_web_login.py on the operator's PC and
copying the file into a Docker volume by hand. That needs a display, a shell,
and knowledge of which container to copy into - none of which help the person
who is actually stuck staring at a bot that cannot host a meeting. Here they
just attach a file.

Accepts what Cookie Editor exports: a bare JSON array of cookie objects. The
shape conversion lives in the host (remote_browser/server.py), not here, because
the host owns the file this data becomes; the bot's job is auth, size limits
and an honest error message.

A cookie export is a live Zoom login. It is stored, not echoed, and no reply
ever quotes a cookie value.
"""

from __future__ import annotations

import logging

from aiogram import Bot, F, Router
from aiogram.exceptions import TelegramBadRequest
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message

from bot.auth import is_owner_or_admin
from config import settings
from db import get_user_by_telegram_id
from zoom import remote_zoom_client, RemoteZoomError

logger = logging.getLogger(__name__)

router = Router(name="zoom_session")

# Telegram's own document ceiling is 20 MB for bots. A real export of every
# site in a browser is a few hundred KB, so this is a sanity bound that keeps a
# wrong-file upload from being downloaded and buffered for nothing.
MAX_UPLOAD_BYTES = 4 * 1024 * 1024

INSTRUCTIONS = (
    "🔐 <b>Import Sesi Zoom</b>\n\n"
    "Kirim file JSON hasil <i>export cookie</i> dari <b>Cookie Editor</b> "
    "(ekstensi Chrome/Firefox) untuk akun <b>host</b>.\n\n"
    "<b>Cara mendapatkannya:</b>\n"
    "1. Buka <code>zoom.us</code> di browser, login sudah aktif.\n"
    "2. Klik ikon Cookie Editor → tab <i>Export</i>.\n"
    "3. Klik <i>Export</i>, lalu <i>Download JSON</i>.\n"
    "4. Kirim file JSON itu ke sini.\n\n"
    "⚠️ File ini berisi login aktif akun Zoom Anda. Hanya Admin/Owner yang bisa "
    "mengimpor, dan file-nya disimpan di volume host — jangan dibagikan.\n\n"
    "Kirim <code>/cancel</code> untuk batal."
)


class SessionImportStates(StatesGroup):
    waiting_for_file = State()


def _back_button() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="⬅️ Kembali ke Menu Utama", callback_data="back_to_main")],
    ])


async def _finish(status: Message, text: str) -> None:
    """Report on the placeholder message, or send fresh if editing is refused."""
    try:
        await status.edit_text(text, parse_mode="HTML", reply_markup=_back_button())
    except TelegramBadRequest:
        await status.answer(text, parse_mode="HTML", reply_markup=_back_button())


@router.callback_query(lambda c: c.data == "zoom_import_session")
async def cb_import_session(c: CallbackQuery, state: FSMContext) -> None:
    """Explain the export steps and wait for the file."""
    if c.from_user is None:
        await c.answer("Informasi pengguna tidak tersedia")
        return
    if not is_owner_or_admin(await get_user_by_telegram_id(c.from_user.id)):
        await c.answer("Aksi ini hanya untuk Admin/Owner.", show_alert=True)
        return

    await c.answer()
    await state.set_state(SessionImportStates.waiting_for_file)
    try:
        await c.message.edit_text(INSTRUCTIONS, reply_markup=_back_button())
    except TelegramBadRequest:
        # Includes "message is not modified" when the panel is already open.
        await c.message.reply(INSTRUCTIONS, reply_markup=_back_button())


@router.message(SessionImportStates.waiting_for_file, F.text == "/cancel")
async def cancel_import(msg: Message, state: FSMContext) -> None:
    await state.clear()
    await msg.answer("Import sesi dibatalkan.", reply_markup=_back_button())


@router.message(SessionImportStates.waiting_for_file, F.text)
async def wrong_text(msg: Message) -> None:
    """A stray message must not silently end the flow or import garbage."""
    await msg.answer("Yang saya butuh cuma file JSON-nya. Kirim file, atau /cancel untuk batal.")


@router.message(SessionImportStates.waiting_for_file, F.photo | F.sticker | F.voice)
async def wrong_media(msg: Message) -> None:
    await msg.answer("Kirim <b>file JSON</b>-nya, bukan foto atau stiker. /cancel untuk batal.")


@router.message(SessionImportStates.waiting_for_file, F.document)
async def receive_session_file(msg: Message, bot: Bot, state: FSMContext) -> None:
    """Download the attachment, hand the bytes to the host, report the result.

    The event comes first on purpose. aiogram invokes handlers as
    ``callback(event, **kwargs)`` - Handler.call does
    ``partial(self.callback, *args, **kwargs)`` with the event positional. A
    ``bot: Bot`` first parameter therefore binds the event to the bot slot and
    the real ``bot`` kwarg collides with it:
    ``TypeError: receive_session_file() got multiple values for argument
    'bot'``. Every upload failed at the last step with that traceback.
    """
    await state.clear()
    # The state was set by an admin, but in a shared chat a non-admin's message
    # reaches the same state, so permission is re-checked at the point of use.
    if not is_owner_or_admin(await get_user_by_telegram_id(msg.from_user.id)):
        await msg.answer("Aksi ini hanya untuk Admin/Owner.", reply_markup=_back_button())
        return

    if settings.zoom_control_mode.lower() != "remote":
        await msg.answer(
            "❌ Import sesi hanya dipakai pada mode remote "
            f"(<code>ZOOM_CONTROL_MODE</code> saat ini <code>{settings.zoom_control_mode}</code>).",
            reply_markup=_back_button(),
        )
        return

    document = msg.document
    if document.file_size and document.file_size > MAX_UPLOAD_BYTES:
        await msg.answer(
            f"❌ File terlalu besar ({document.file_size // 1024} KB). "
            f"Batas {MAX_UPLOAD_BYTES // 1024 // 1024} MB.",
            reply_markup=_back_button(),
        )
        return

    status = await msg.answer("⏳ Mengimpor sesi Zoom...")
    try:
        # get_file only hands back a URL; the bytes still have to be fetched, and
        # it must go through this same Bot so the request carries no credentials
        # of its own.
        handle = await bot.get_file(document.file_id)
        payload = await handle.download()
    except Exception as exc:  # noqa: BLE001 - Telegram/network surprises
        logger.exception("Session file download failed")
        await _finish(status, f"❌ Gagal mengunduh file: {exc}")
        return

    try:
        result = await remote_zoom_client.import_session(payload)
    except RemoteZoomError as exc:
        # The host answers with the converter's own reason, which is far more
        # useful than a generic failure: it names the missing cookie.
        await _finish(status, f"❌ <b>Import ditolak</b>\n\n{exc}")
        return
    except Exception as exc:  # noqa: BLE001 - network/HTTP surprises
        logger.exception("Session import failed")
        await _finish(status, f"❌ Error saat import: {exc}")
        return

    count = result.get("cookies", 0)
    if result.get("signed_in"):
        text = (
            "✅ <b>Sesi Zoom berhasil diimpor</b>\n\n"
            f"🔐 {count} cookie tersimpan\n"
            "✔️ Zoom mengonfirmasi sesi masih login\n\n"
            "Host siap menjalankan meeting."
        )
    else:
        # The file is on disk but Zoom rejected it. Reporting plain success here
        # would send the operator off to test a host that cannot join.
        detail = result.get("reload_error") or "Zoom tidak mengonfirmasi sesi masih login"
        text = (
            "⚠️ <b>Sesi tersimpan, tapi belum terverifikasi</b>\n\n"
            f"🔐 {count} cookie tersimpan\n"
            f"❌ {detail}\n\n"
            "Kemungkinan file-nya kedaluwarsa. Ambil ulang dari browser yang "
            "<b>sedang login</b>, lalu kirim lagi."
        )
    await _finish(status, text)


@router.message(SessionImportStates.waiting_for_file)
async def anything_else(msg: Message) -> None:
    """Anything unexpected: keep the state armed so the real file can still arrive."""
    await msg.answer("Kirim file JSON-nya ya. /cancel untuk batal.")
