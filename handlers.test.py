from aiogram import Router, F
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.filters import Command
from aiogram.exceptions import TelegramBadRequest
from aiogram.fsm.state import StatesGroup, State
from aiogram.fsm.context import FSMContext
from db import add_pending_user, list_pending_users, list_all_users, update_user_status, get_user_by_telegram_id, ban_toggle_user, delete_user, add_meeting, update_meeting_short_url, update_meeting_short_url_by_join_url, list_meetings, sync_meetings_from_zoom
from keyboards import pending_user_buttons, pending_user_owner_buttons, user_action_buttons, all_users_buttons, role_selection_buttons, status_selection_buttons, list_meetings_buttons
from config import settings
from auth import is_allowed_to_create
from zoom import zoom_client
import logging

import re
from datetime import datetime, date, time, timedelta, timezone
import uuid
from shortener import make_short
import shlex

router = Router()
# in-memory temp mapping token -> original url (short-lived)
TEMP_MEETINGS: dict = {}

logger = logging.getLogger(__name__)


def _get_user_info_text(user: dict) -> str:
    """Helper to format user info text."""
    return f"ID: {user['telegram_id']}\nUsername: {user['username'] or '-'}\nStatus: {user['status']}\nRole: {user['role']}"


async def _get_username_from_telegram_id(telegram_id: str) -> str:
    """Helper to get username from telegram_id for meeting creator display."""
    if telegram_id == 'CreatedFromZoomApp':
        return 'Dibuat dari Zoom App'
    
    try:
        # Convert to int if it's a string representation of int
        tid = int(telegram_id)
        user = await get_user_by_telegram_id(tid)
        if user and user.get('username'):
            return f"@{user['username']}"
        else:
            return f"User {telegram_id}"
    except (ValueError, TypeError):
        return f"User {telegram_id}"


def _format_meeting_time(start_time_str: str) -> str:
    """Helper to format meeting time in Indonesian format."""
    if not start_time_str:
        return "Waktu tidak tersedia"
    
    try:
        # Parse ISO datetime (e.g., "2025-10-30T07:30:00Z")
        if start_time_str.endswith('Z'):
            dt = datetime.fromisoformat(start_time_str[:-1])
        else:
            dt = datetime.fromisoformat(start_time_str)
        
        # Convert to WIB timezone (+7 hours from UTC)
        wib_tz = timezone(timedelta(hours=7))
        dt_wib = dt.replace(tzinfo=timezone.utc).astimezone(wib_tz)
        
        # Indonesian day names
        days_id = {
            0: 'Senin', 1: 'Selasa', 2: 'Rabu', 3: 'Kamis',
            4: 'Jumat', 5: 'Sabtu', 6: 'Minggu'
        }
        
        # Indonesian month names
        months_id = {
            1: 'Januari', 2: 'Februari', 3: 'Maret', 4: 'April', 5: 'Mei', 6: 'Juni',
            7: 'Juli', 8: 'Agustus', 9: 'September', 10: 'Oktober', 11: 'November', 12: 'Desember'
        }
        
        day_name = days_id[dt_wib.weekday()]
        day = dt_wib.day
        month_name = months_id[dt_wib.month]
        year = dt_wib.year
        time_str = dt_wib.strftime("%H:%M")
        
        return f"{day_name}, {day} {month_name} {year}\n🕐 {time_str}"
        
    except (ValueError, TypeError) as e:
        logger.warning("Failed to parse meeting time '%s': %s", start_time_str, e)
        return f"Waktu: {start_time_str}"


@router.message(Command("whoami"))
async def cmd_whoami(msg: Message):
    """Diagnostic command: show sender id, username, configured owner_id and whether they match."""
    if msg.from_user is None:
        await msg.reply("Informasi pengguna tidak tersedia")
        return
    uid = getattr(msg.from_user, 'id', None)
    username = getattr(msg.from_user, 'username', None)
    owner = settings.owner_id
    is_owner = (owner is not None and uid == owner)
    logger.info("whoami called by %s (owner_config=%s) -> is_owner=%s", uid, owner, is_owner)
    text = (
        f"Your Telegram ID: {uid}\n"
        f"Your username: {username or '-'}\n"
        f"Configured INITIAL_OWNER_ID: {owner or '-'}\n"
        f"Is owner: {is_owner}"
    )
    await msg.reply(text)


@router.message(Command("help"))
async def cmd_help(msg: Message):
    """Show available commands and features."""
    if msg.from_user is None:
        await msg.reply("Informasi pengguna tidak tersedia")
        return

    user = await get_user_by_telegram_id(msg.from_user.id)
    is_admin = user and is_allowed_to_create(user)

    help_text = (
        "🤖 <b>Bot Telegram SOC - Bantuan</b>\n\n"
        "<b>Perintah Umum:</b>\n"
        "<code>/start</code> - Mulai bot dan tampilkan menu utama\n"
        "<code>/help</code> - Tampilkan bantuan ini\n"
        "<code>/about</code> - Tampilkan informasi tentang bot\n"
        "<code>/zoom &lt;topic&gt; &lt;date&gt; &lt;time&gt;</code> - Buat meeting Zoom cepat\n"
        "🔹 Support batch: kirim multiple baris untuk membuat banyak meeting sekaligus\n\n"
        "<code>/whoami</code> - Tampilkan informasi akun Telegram Anda\n\n"
    )

    if is_admin:
        help_text += (
            "<b>Perintah Admin (khusus Owner/Admin):</b>\n"
            "<code>/register_list</code> - Lihat daftar user yang menunggu persetujuan\n"
            "<code>/all_users</code> - Kelola semua user (ubah role, status, hapus)\n"
            "<code>/sync_meetings</code> - Sinkronkan meetings dari Zoom ke database (menandai yang dihapus)\n\n"
        )

    help_text += (
        "<b>Fitur Utama:</b>\n"
        "🔹 <b>Registrasi User:</b> User baru akan didaftarkan otomatis saat pertama kali menggunakan bot\n"
        "🔹 <b>Buat Meeting Zoom:</b> Klik tombol 'Create Meeting' untuk membuat meeting baru dengan panduan langkah demi langkah\n"
        "🔹 <b>Short URL:</b> Setelah meeting dibuat, dapat membuat short URL untuk link meeting\n"
    )

    if is_admin:
        help_text += "🔹 <b>Manajemen User:</b> Admin dapat menyetujui, menolak, mengubah role/status, atau menghapus user\n\n"
    else:
        help_text += "\n"

    help_text += (
        "<b>Catatan:</b>\n"
        "- Pastikan Anda sudah terdaftar dan disetujui untuk menggunakan fitur meeting\n"
        "- Hubungi admin jika ada masalah\n"
    )

    await msg.reply(help_text, parse_mode="HTML")


@router.message(Command("about"))
async def cmd_about(msg: Message):
    """Show a brief about the bot."""
    about_text = (
        "🤖 <b>Bot Telegram SOC</b>\n\n"
        "Bot ini dirancang untuk membantu Tim Keamanan Siber (SOC) dalam mengelola meeting Zoom dan user dengan efisien. "
        "Fitur utama meliputi pembuatan meeting Zoom otomatis, manajemen user (khusus admin), dan pembuatan short URL untuk kemudahan akses. "
        "Bot ini memastikan proses operasional yang cepat dan aman, dengan integrasi penuh ke Zoom API. "
        "Dibuat untuk meningkatkan produktivitas tim SOC dalam menangani insiden keamanan.\n\n"
        "<i>Versi 1.0 - Oktober 2025</i>"
    )
    await msg.reply(about_text, parse_mode="HTML")


@router.message(Command("zoom"))
async def cmd_zoom(msg: Message):
    """Quick create Zoom meeting(s): /zoom <topic> <date> <time>
    
    Support batch creation with multiple lines:
    /zoom "Meeting 1" "25 Oktober 2025" "14:30"
    "Meeting 2" "26 Oktober 2025" "15:00"
    "Meeting 3" "27 Oktober 2025" "16:00"
    """
    if msg.from_user is None or not msg.text:
        await msg.reply("Informasi tidak lengkap")
        return

    user = await get_user_by_telegram_id(msg.from_user.id)
    if not is_allowed_to_create(user):
        await msg.reply("Anda belum diizinkan membuat meeting.")
        return

    # Split message into lines and process each line as a separate meeting
    lines = [line.strip() for line in msg.text.split('\n') if line.strip()]
    
    if not lines:
        await msg.reply("Tidak ada data meeting yang ditemukan.")
        return
    
    # Remove the command from first line
    first_line = lines[0]
    if first_line.startswith('/zoom'):
        first_line = first_line[5:].strip()  # Remove "/zoom" prefix
        lines[0] = first_line
    
    # Filter out empty lines after processing
    lines = [line for line in lines if line]
    
    if not lines:
        await msg.reply("Format: /zoom <topic> <date> <time>\n\nContoh:\n/zoom \"Rapat Mingguan\" \"31-12-2025\" \"14:30\"\n\nAtau untuk batch:\n/zoom \"Meeting 1\" \"25 Oktober 2025\" \"14:30\"\n\"Meeting 2\" \"26 Oktober 2025\" \"15:00\"")
        return

    await msg.reply(f"🔄 Memproses {len(lines)} meeting(s)... Mohon tunggu.")

    results = []
    successful = 0
    failed = 0
    successful_meetings = []  # Store successful meeting data

    for i, line in enumerate(lines, 1):
        try:
            # Parse each line using shlex
            args = shlex.split(line)
            if len(args) != 3:
                results.append(f"❌ Meeting {i}: Format salah. Gunakan: \"topic\" \"date\" \"time\"")
                failed += 1
                continue
            
            topic, date_str, time_str = args
            
            # Parse date
            d = _parse_indonesia_date(date_str)
            if not d:
                results.append(f"❌ Meeting {i} ({topic}): Format tanggal tidak dikenal '{date_str}'. Gunakan DD-MM-YYYY atau '31 Desember 2025'.")
                failed += 1
                continue

            # Parse time
            t = _parse_time_24h(time_str)
            if not t:
                results.append(f"❌ Meeting {i} ({topic}): Format waktu tidak valid '{time_str}'. Gunakan HH:MM (24 jam).")
                failed += 1
                continue

            # At this point d and t are guaranteed not None
            if d is None or t is None:
                results.append(f"❌ Meeting {i} ({topic}): Error internal parsing.")
                failed += 1
                continue

            # Combine date and time
            dt = datetime.combine(d, t)
            tz = timezone(timedelta(hours=7))
            dt = dt.replace(tzinfo=tz)
            start_time_iso = dt.isoformat()

            # Create meeting
            user_id = 'me'
            meeting = await zoom_client.create_meeting(user_id=str(user_id), topic=topic, start_time=start_time_iso)
            logger.info("Meeting created via /zoom batch: %s", meeting.get('id') or meeting)
            
            # Save to DB
            zoom_id = meeting.get('id')
            join_url = meeting.get('join_url') or meeting.get('start_url') or ''
            if zoom_id:
                await add_meeting(str(zoom_id), topic, start_time_iso, join_url, msg.from_user.id)
            
            results.append(f"✅ Meeting {i} ({topic}): Berhasil dibuat")
            successful += 1
            
            # Store successful meeting data
            successful_meetings.append({
                'topic': topic,
                'date_str': date_str,
                'time_str': time_str,
                'join_url': join_url,
                'zoom_id': zoom_id,
                'start_time_iso': start_time_iso
            })
            
        except Exception as e:
            logger.exception("Failed to create meeting %d: %s", i, e)
            results.append(f"❌ Meeting {i}: Gagal - {e}")
            failed += 1

    # Send summary
    summary = f"📊 <b>Hasil Batch Creation:</b>\n✅ Berhasil: {successful}\n❌ Gagal: {failed}\n\n"
    summary += "\n".join(results[:10])  # Limit to first 10 results
    if len(results) > 10:
        summary += f"\n... dan {len(results) - 10} hasil lainnya"
    
    await msg.reply(summary, parse_mode="HTML")
    
    # If there were successful creations, show all meetings in one message with greeting format
    if successful > 0:
        # Get current time for greeting
        now_wib = datetime.now(timezone(timedelta(hours=7)))
        h = now_wib.hour
        if 4 <= h < 10:
            greeting = 'Selamat pagi'
        elif 10 <= h < 15:
            greeting = 'Selamat siang'
        elif 15 <= h < 18:
            greeting = 'Selamat sore'
        else:
            greeting = 'Selamat malam'

        # Create one message with all meetings
        text = ""
        keyboard_buttons = []
        
        for i, meeting in enumerate(successful_meetings, 1):
            topic = meeting['topic']
            date_str = meeting['date_str']
            time_str = meeting['time_str']
            join_url = meeting['join_url']

            # Parse date and time for display
            d = _parse_indonesia_date(date_str)
            t = _parse_time_24h(time_str)
            if d and t:
                dt = datetime.combine(d, t)
                tz = timezone(timedelta(hours=7))
                dt = dt.replace(tzinfo=tz)

                # Format display
                DAYS_ID = ['Senin','Selasa','Rabu','Kamis','Jumat','Sabtu','Minggu']
                MONTHS_ID_DISPLAY = {1:'Januari',2:'Februari',3:'Maret',4:'April',5:'Mei',6:'Juni',7:'Juli',8:'Agustus',9:'September',10:'Oktober',11:'November',12:'Desember'}
                day_name = DAYS_ID[dt.weekday()]
                disp_date = f"{day_name}, {dt.day} {MONTHS_ID_DISPLAY.get(dt.month, dt.month)} {dt.year}"
                disp_time = f"{dt.hour:02d}:{dt.minute:02d}"

                # Add meeting to text with greeting format
                text += f"```\n{greeting} Bapak/Ibu/Rekan-rekan\nBerikut disampaikan Kegiatan {topic} pada:\n\n📆  {disp_date}\n⏰  {disp_time} WIB – selesai\n🔗  {join_url}\n\nDemikian disampaikan, terimakasih.\n```"
                
                # Add separator between meetings (except for the last one)
                if i < len(successful_meetings):
                    text += "\n\n" + "="*50 + "\n\n"
                
                # Add short URL button for this meeting
                token = f"{meeting['zoom_id']}_{uuid.uuid4().hex[:8]}"
                globals().setdefault('TEMP_MEETINGS', {})
                globals()['TEMP_MEETINGS'][token] = join_url
                keyboard_buttons.append([
                    InlineKeyboardButton(text=f"🔗 Buat Short URL - {topic}", callback_data=f"shorten:{token}")
                ])
        
        # Create keyboard
        kb = InlineKeyboardMarkup(inline_keyboard=keyboard_buttons) if keyboard_buttons else None
        
        await msg.reply(text, reply_markup=kb, parse_mode="Markdown")
@router.message(Command("sync_meetings"))
async def cmd_sync_meetings(msg: Message):
    """Manually sync meetings from Zoom to database (owner only)."""
    if msg.from_user is None:
        return

    # Only owner can run sync
    if settings.owner_id is None or msg.from_user.id != settings.owner_id:
        await msg.reply("Hanya owner yang dapat menjalankan sync meetings.")
        return

    await msg.reply("🔄 Memulai sinkronisasi meetings dari Zoom...")
    
    try:
        stats = await sync_meetings_from_zoom(zoom_client)
        text = (
            "✅ <b>Sinkronisasi selesai!</b>\n\n"
            f"📊 <b>Statistik:</b>\n"
            f"➕ Ditambahkan: {stats['added']}\n"
            f"🔄 Diupdate: {stats['updated']}\n"
            f"🗑️ Ditandai Dihapus: {stats['deleted']}\n"
            f"❌ Error: {stats['errors']}\n\n"
            "<i>Sistem otomatis mensinkronkan setiap 30 menit dan saat startup.</i>"
        )
        await msg.reply(text, parse_mode="HTML")
    except Exception as e:
        logger.exception("Manual sync failed: %s", e)
        await msg.reply(f"❌ <b>Gagal melakukan sinkronisasi:</b> {e}", parse_mode="HTML")


@router.message(Command("start"))
async def cmd_start(msg: Message):
    """Show the main UI or register the user if missing.

    This duplicates a subset of `handle_any_message` behaviour so `/start`
    always responds even if the generic message handler is filtered.
    """
    if msg.from_user is None:
        await msg.reply("Informasi pengguna tidak tersedia")
        return

    user = await get_user_by_telegram_id(msg.from_user.id)
    if not user:
        # If this is the configured owner, automatically add as owner/whitelisted
        if settings.owner_id is not None and msg.from_user.id == settings.owner_id:
            logger.info("Auto-whitelisting configured owner %s (via /start)", msg.from_user.id)
            await add_pending_user(msg.from_user.id, msg.from_user.username)
            await update_user_status(msg.from_user.id, 'whitelisted', 'owner')
            user = await get_user_by_telegram_id(msg.from_user.id)
        else:
            await add_pending_user(msg.from_user.id, msg.from_user.username)
            text = (
                "Anda belum terdaftar, kirim data ini ke admin untuk dilakukan whitelist :\n"
                f"Username Telegram : {msg.from_user.username or '-'}\n"
                f"User ID Telegram : {msg.from_user.id}"
            )
            await msg.reply(text)
            return

    if is_allowed_to_create(user):
        # Personalized greeting with username
        username = msg.from_user.username or msg.from_user.first_name or "Pengguna"
        role = (user.get('role', 'user') if user else 'user').capitalize()
        greeting_text = (
            f"🤖 Halo, {username}! 👋\n\n"
            f"Anda adalah <b>{role}</b> di bot ini.\n\n"
            "Selamat datang di <b>Bot Telegram SOC</b>. Saya di sini untuk membantu Anda mengelola rapat Zoom langsung dari Telegram.\n\n"
            "Saya bisa membantu untuk:\n"
            "🔹 Menjadwalkan rapat baru\n"
            "🔹 Mengelola user (khusus admin)\n"
            "🔹 Mendapatkan short URL untuk link meeting\n"
            "🔹 Melihat daftar user pending/aktif\n\n"
            "Untuk memulai, silakan klik tombol di bawah ini.\n\n"
            "Jika Anda butuh bantuan, kapan saja bisa ketik /help."
        )
        await msg.answer(greeting_text, reply_markup=user_action_buttons(), parse_mode="HTML")
    elif user and user.get('status') == 'banned':
        await msg.reply("*Anda dibanned dari menggunakan bot ini.*", parse_mode="Markdown")
    else:
        await msg.reply("*Permintaan Anda sedang menunggu persetujuan.*", parse_mode="Markdown")


async def _safe_edit_or_fallback(c: CallbackQuery, text: str, reply_markup=None, parse_mode=None) -> None:
    """Try to edit the original message. If that's not available, reply to the message or answer the callback.

    This avoids runtime/type-checker errors when CallbackQuery.message is None or doesn't expose edit_text.
    """
    m = getattr(c, 'message', None)
    # If we have a real Message object from aiogram, call its coroutine methods directly
    from aiogram.types import Message as AiMessage

    if isinstance(m, AiMessage):
        # Prefer editing the original message. If editing fails (message too old, etc.),
        # fall back to replying to the message.
        try:
            await m.edit_text(text, reply_markup=reply_markup, parse_mode=parse_mode)
            return
        except TelegramBadRequest:
            # couldn't edit (maybe too old or protected), try to reply instead
            try:
                await m.reply(text, reply_markup=reply_markup, parse_mode=parse_mode)
                return
            except Exception:
                # fall through to answering the callback below
                logger.debug("_edit_or_fallback: reply() failed, falling back to callback answer")

    # fallback to answering the callback (no edit available)
    try:
        await c.answer(text)
    except Exception:
        # avoid raising during callback handling; just log the issue
        logger.debug("_safe_edit_or_fallback: c.answer() failed for callback with data=%s", getattr(c, 'data', None))


class MeetingStates(StatesGroup):
    topic = State()
    date = State()
    time = State()
    confirm = State()


@router.message(F.state == None)
async def handle_any_message(msg: Message):
    # guard: ensure from_user exists
    if msg.from_user is None:
        # cannot proceed without sender info
        return

    logger.debug("Received message from %s: %s", getattr(msg.from_user, 'id', None), getattr(msg, 'text', None))
    # if user not in DB, add as pending and reply with template
    user = await get_user_by_telegram_id(msg.from_user.id)
    if not user:
        # If this is the configured owner, automatically add as owner/whitelisted
        if settings.owner_id is not None and msg.from_user.id == settings.owner_id:
            logger.info("Auto-whitelisting configured owner %s", msg.from_user.id)
            # ensure a row exists
            await add_pending_user(msg.from_user.id, msg.from_user.username)
            # set status and role to owner
            await update_user_status(msg.from_user.id, 'whitelisted', 'owner')
            # re-read user
            user = await get_user_by_telegram_id(msg.from_user.id)
        else:
            logger.info("Registering pending user %s", msg.from_user.id)
            await add_pending_user(msg.from_user.id, msg.from_user.username)
            text = (
                "Anda belum terdaftar, kirim data ini ke admin untuk dilakukan whitelist :\n"
                f"Username Telegram : {msg.from_user.username or '-'}\n"
                f"User ID Telegram : {msg.from_user.id}"
            )
            await msg.reply(text)
            return

    # If whitelisted or owner, show UI (centralized check)
    if is_allowed_to_create(user):
        logger.debug("User %s allowed actions (status=%s)", msg.from_user.id, (user.get('status') if user else None))
        await msg.answer("Pilih aksi:", reply_markup=user_action_buttons())
    elif user and user.get('status') == 'banned':
        await msg.reply("Anda dibanned dari menggunakan bot ini.")
    else:
        await msg.reply("Permintaan Anda sedang menunggu persetujuan.")

@router.message(F.text == '/register_list')
async def cmd_register_list(msg: Message):
    # only owner or admin can call
    if msg.from_user is None:
        return

    if settings.owner_id and msg.from_user.id != settings.owner_id:
        await msg.reply("Hanya owner yang dapat mengakses daftar registrasi.")
        return

    pendings = await list_pending_users()
    # send one message per pending user and include owner action buttons
    for u in pendings:
        logger.debug("register_list pending entry: %s", u)
        text = f"ID: {u['telegram_id']}\nUsername: {u['username'] or '-'}\nStatus: {u['status']}\nRole: {u['role']}"
        kb = pending_user_owner_buttons(u['telegram_id'], is_banned=(u['status']=='banned'))
        await msg.reply(text, reply_markup=kb)


@router.message(Command("all_users"))
async def cmd_all_users(msg: Message):
    """Show all registered users (owner only)."""
    if msg.from_user is None:
        return

    # only owner may call this
    if settings.owner_id is not None and msg.from_user.id != settings.owner_id:
        await msg.reply("Hanya owner yang dapat mengakses daftar user.")
        return

    users = await list_all_users()
    if not users:
        await msg.reply("Tidak ada user terdaftar.")
        return

    # send one message per user with action buttons
    for u in users:
        text = f"ID: {u['telegram_id']}\nUsername: {u['username'] or '-'}\nStatus: {u['status']}\nRole: {u['role']}"
        kb = all_users_buttons(u['telegram_id'])
        await msg.reply(text, reply_markup=kb)


@router.callback_query(lambda c: c.data and c.data.startswith('accept:'))
async def cb_accept(c: CallbackQuery):
    data = c.data or ""
    if not data:
        await c.answer()
        return

    _, tid = data.split(':', 1)
    telegram_id = int(tid)
    await update_user_status(telegram_id, 'whitelisted', 'user')
    await _safe_edit_or_fallback(c, f"User {telegram_id} diterima (whitelisted)")
    await c.answer("User diterima")


@router.callback_query(lambda c: c.data and c.data.startswith('reject:'))
async def cb_reject(c: CallbackQuery):
    data = c.data or ""
    if not data:
        await c.answer()
        return

    _, tid = data.split(':', 1)
    telegram_id = int(tid)
    # Owner rejected the registration: delete the user row entirely
    try:
        await delete_user(telegram_id)
        await _safe_edit_or_fallback(c, f"User {telegram_id} ditolak dan dihapus dari daftar")
        await c.answer("User ditolak dan dihapus")
    except Exception as e:
        logger.exception("Failed to delete user %s: %s", telegram_id, e)
        await c.answer("Gagal menghapus user")


@router.callback_query(lambda c: c.data and c.data.startswith('ban_toggle:'))
async def cb_ban_toggle(c: CallbackQuery):
    data = c.data or ""
    if not data:
        await c.answer()
        return

    _, tid = data.split(':', 1)
    telegram_id = int(tid)
    user = await get_user_by_telegram_id(telegram_id)
    if not user:
        await c.answer("User tidak ditemukan")
        return
    is_banned = user['status'] == 'banned'
    await ban_toggle_user(telegram_id, not is_banned)
    new_status = 'whitelisted' if is_banned else 'banned'
    await _safe_edit_or_fallback(c, f"User {telegram_id} status sekarang: {new_status}")
    await c.answer("Status diubah")


@router.callback_query(lambda c: c.data and c.data.startswith('ban:'))
async def cb_ban(c: CallbackQuery):
    data = c.data or ""
    if not data:
        await c.answer()
        return

    _, tid = data.split(':', 1)
    telegram_id = int(tid)
    await ban_toggle_user(telegram_id, True)
    await _safe_edit_or_fallback(c, f"User {telegram_id} dibanned")
    await c.answer("User dibanned")


@router.callback_query(lambda c: c.data and c.data.startswith('delete_user:'))
async def cb_delete_user(c: CallbackQuery):
    data = c.data or ""
    if not data:
        await c.answer()
        return

    _, tid = data.split(':', 1)
    telegram_id = int(tid)
    # Delete the user row
    try:
        await delete_user(telegram_id)
        await _safe_edit_or_fallback(c, f"User {telegram_id} dihapus dari daftar")
        await c.answer("User dihapus")
    except Exception as e:
        logger.exception("Failed to delete user %s: %s", telegram_id, e)
        await c.answer("Gagal menghapus user")


@router.callback_query(lambda c: c.data and c.data.startswith('change_role:'))
async def cb_change_role(c: CallbackQuery):
    data = c.data or ""
    if not data:
        await c.answer()
        return

    _, tid = data.split(':', 1)
    telegram_id = int(tid)
    # Send role selection keyboard
    kb = role_selection_buttons(telegram_id)
    await _safe_edit_or_fallback(c, f"Pilih role baru untuk user {telegram_id}:", reply_markup=kb)
    await c.answer()


@router.callback_query(lambda c: c.data and c.data.startswith('change_status:'))
async def cb_change_status(c: CallbackQuery):
    data = c.data or ""
    if not data:
        await c.answer()
        return

    _, tid = data.split(':', 1)
    telegram_id = int(tid)
    # Send status selection keyboard
    kb = status_selection_buttons(telegram_id)
    await _safe_edit_or_fallback(c, f"Pilih status baru untuk user {telegram_id}:", reply_markup=kb)
    await c.answer()


@router.callback_query(lambda c: c.data and c.data.startswith('set_role:'))
async def cb_set_role(c: CallbackQuery):
    data = c.data or ""
    if not data:
        await c.answer()
        return

    _, tid, role = data.split(':', 2)
    telegram_id = int(tid)
    # Update role, keep status the same
    user = await get_user_by_telegram_id(telegram_id)
    if not user:
        await c.answer("User tidak ditemukan")
        return
    current_status = user['status']
    await update_user_status(telegram_id, current_status, role)
    # Re-fetch user and update message
    updated_user = await get_user_by_telegram_id(telegram_id)
    if updated_user:
        text = _get_user_info_text(updated_user)
        kb = all_users_buttons(telegram_id)
        await _safe_edit_or_fallback(c, text, reply_markup=kb)
    await c.answer("Role diubah")


@router.callback_query(lambda c: c.data and c.data.startswith('set_status:'))
async def cb_set_status(c: CallbackQuery):
    data = c.data or ""
    if not data:
        await c.answer()
        return

    _, tid, status = data.split(':', 2)
    telegram_id = int(tid)
    # Update status, keep role the same
    user = await get_user_by_telegram_id(telegram_id)
    if not user:
        await c.answer("User tidak ditemukan")
        return
    current_role = user['role']
    await update_user_status(telegram_id, status, current_role)
    # Re-fetch user and update message
    updated_user = await get_user_by_telegram_id(telegram_id)
    if updated_user:
        text = _get_user_info_text(updated_user)
        kb = all_users_buttons(telegram_id)
        await _safe_edit_or_fallback(c, text, reply_markup=kb)
    await c.answer("Status diubah")


@router.callback_query(lambda c: c.data and c.data.startswith('cancel_change:'))
async def cb_cancel_change(c: CallbackQuery):
    data = c.data or ""
    if not data:
        await c.answer()
        return

    _, tid = data.split(':', 1)
    telegram_id = int(tid)
    # Re-fetch user and show original info with buttons
    user = await get_user_by_telegram_id(telegram_id)
    if user:
        text = _get_user_info_text(user)
        kb = all_users_buttons(telegram_id)
        await _safe_edit_or_fallback(c, text, reply_markup=kb)
    await c.answer("Dibatalkan")


@router.callback_query(lambda c: c.data and c.data == 'create_meeting')
async def cb_create_meeting(c: CallbackQuery, state: FSMContext):
    # only for whitelisted users
    if c.from_user is None:
        await c.answer("Informasi pengguna tidak tersedia")
        return

    user = await get_user_by_telegram_id(c.from_user.id)
    # allow whitelisted users or owners (centralized check)
    if not is_allowed_to_create(user):
        await c.answer("Anda belum diizinkan membuat meeting.")
        return

    logger.info("Starting meeting creation flow for user %s", c.from_user.id)
    await _safe_edit_or_fallback(c, "**Buat Meeting - Step 1/3**\n_Silakan kirim Topic Meeting:_", parse_mode="Markdown")
    await state.set_state(MeetingStates.topic)
    await c.answer()


@router.callback_query(lambda c: c.data == 'list_meetings')
async def cb_list_meetings(c: CallbackQuery):
    if c.from_user is None:
        await c.answer("Informasi pengguna tidak tersedia")
        return

    user = await get_user_by_telegram_id(c.from_user.id)
    if not is_allowed_to_create(user):
        await c.answer("Anda belum diizinkan melihat meetings.")
        return

    await c.answer("Mengambil daftar meeting...")
    try:
        all_meetings = await list_meetings()
        # Filter only active meetings
        meetings = [m for m in all_meetings if m.get('status') == 'active']
        
        if not meetings:
            text = "📅 <b>Tidak ada meeting aktif yang tersimpan.</b>"
            await _safe_edit_or_fallback(c, text, parse_mode="HTML", reply_markup=list_meetings_buttons())
            return

        text = "📅 <b>Daftar Zoom Meeting Aktif:</b>\n\n"
        
        for i, m in enumerate(meetings, 1):
            topic = m.get('topic', 'No Topic')
            start_time = m.get('start_time', '')
            join_url = m.get('join_url', '')
            short_url = m.get('short_url', '')
            created_by = m.get('created_by', 'Unknown')
            
            # Get creator username
            creator_username = await _get_username_from_telegram_id(created_by)
            
            # Format time
            formatted_time = _format_meeting_time(start_time)
            
            text += f"<b>{i}. {topic}</b>\n"
            text += f"👤 Dibuat oleh: {creator_username}\n"
            text += f"🕛 {formatted_time}\n"
            text += f"🔗 Link Zoom: {join_url}\n"
            if short_url:
                text += f"🔗 Shortlink: {short_url}\n"
            text += "\n"
        
        await _safe_edit_or_fallback(c, text, parse_mode="HTML", reply_markup=list_meetings_buttons())
    except Exception as e:
        logger.exception("Failed to list meetings: %s", e)
        await _safe_edit_or_fallback(c, f"❌ <b>Gagal mengambil daftar meeting:</b> {e}", parse_mode="HTML", reply_markup=list_meetings_buttons())


@router.callback_query(F.data == "back_to_main")
async def cb_back_to_main(c: CallbackQuery):
    if c.from_user is None:
        await c.answer("Informasi pengguna tidak tersedia")
        return

    user = await get_user_by_telegram_id(c.from_user.id)
    if not user:
        await c.answer("User tidak ditemukan")
        return

    await c.answer()
    text = f"👋 Selamat datang, {user['username'] or 'User'}!\n\nPilih aksi yang ingin dilakukan:"
    await _safe_edit_or_fallback(c, text, reply_markup=user_action_buttons())


@router.message(MeetingStates.topic)
async def meeting_topic(msg: Message, state: FSMContext):
    if not msg.text:
        await msg.reply("Silakan kirim topik meeting sebagai teks.")
        return

    logger.debug("meeting_topic received: %s", msg.text)
    await state.update_data(topic=msg.text.strip())
    await msg.reply("**Step 2/3**\n_Kapan diadakan?_\nFormat: `DD-MM-YYYY` atau '`31-12-2025`' atau tulis seperti '`31 Desember 2025`' (Bulan dalam bahasa Indonesia).", parse_mode="Markdown")
    await state.set_state(MeetingStates.date)


_MONTHS_ID = {
    'januari':1,'februari':2,'maret':3,'april':4,'mei':5,'juni':6,
    'juli':7,'agustus':8,'september':9,'oktober':10,'november':11,'desember':12
}


def _parse_indonesia_date(s: str) -> date | None:
    s = s.strip().lower()
    # try DD-MM-YYYY
    m = re.match(r"^(\d{1,2})-(\d{1,2})-(\d{4})$", s)
    if m:
        d, mo, y = map(int, m.groups())
        try:
            return date(y, mo, d)
        except Exception:
            return None

    # try '31 desember 2025' or '31 desember'
    m = re.match(r"^(\d{1,2})\s+([a-z]+)\s*(\d{4})?$", s)
    if m:
        d = int(m.group(1))
        mon = m.group(2)
        y = int(m.group(3)) if m.group(3) else datetime.now().year
        mo = _MONTHS_ID.get(mon)
        if not mo:
            return None
        try:
            return date(y, mo, d)
        except Exception:
            return None
    return None


@router.message(MeetingStates.date)
async def meeting_date(msg: Message, state: FSMContext):
    if not msg.text:
        await msg.reply("Silakan kirim tanggal meeting sebagai teks.")
        return

    d = _parse_indonesia_date(msg.text)
    if not d:
        await msg.reply("Format tanggal tidak dikenal. Gunakan DD-MM-YYYY atau '31 Desember 2025'. Silakan coba lagi.")
        return
    logger.debug("meeting_date parsed: %s -> %s", msg.text, d)
    await state.update_data(date=str(d))
    await msg.reply("**Step 3/3**\n_Masukkan waktu (format 24-jam WIB) contohnya:_ `14:30`", parse_mode="Markdown")
    await state.set_state(MeetingStates.time)


def _parse_time_24h(s: str) -> time | None:
    s = s.strip()
    m = re.match(r"^(\d{1,2}):(\d{2})$", s)
    if not m:
        return None
    hh = int(m.group(1))
    mm = int(m.group(2))
    if hh < 0 or hh > 23 or mm < 0 or mm > 59:
        return None
    return time(hh, mm)


@router.message(MeetingStates.time)
async def meeting_time(msg: Message, state: FSMContext):
    if not msg.text:
        await msg.reply("Silakan kirim waktu meeting sebagai teks (contoh: 14:30).")
        return

    t = _parse_time_24h(msg.text)
    if not t:
        await msg.reply("Format waktu tidak valid. Gunakan HH:MM (24 jam). Contoh: 09:30 atau 14:00")
        return

    data = await state.get_data()
    topic = data.get('topic')
    date_str = data.get('date')
    if not (topic and date_str):
        await msg.reply("Terjadi kesalahan state. Silakan mulai lagi dengan tombol Create Meeting.")
        await state.clear()
        return

    # combine date and time into ISO8601 with WIB timezone (UTC+7)
    d = datetime.fromisoformat(date_str)
    dt = datetime.combine(d.date(), t)
    # WIB is UTC+7
    tz = timezone(timedelta(hours=7))
    dt = dt.replace(tzinfo=tz)
    start_time_iso = dt.isoformat()

    # store details in state and ask for confirmation
    logger.debug("meeting_time combined start_time_iso=%s", start_time_iso)
    await state.update_data(start_time_iso=start_time_iso, _dt_display=dt.isoformat())

    # prepare confirmation keyboard
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Konfirmasi", callback_data="confirm_create")],
        [InlineKeyboardButton(text="Batal", callback_data="cancel_create")]
    ])

    # display summary in Indonesian month format
    MONTHS_ID_DISPLAY = {1:'Januari',2:'Februari',3:'Maret',4:'April',5:'Mei',6:'Juni',7:'Juli',8:'Agustus',9:'September',10:'Oktober',11:'November',12:'Desember'}
    disp = f"{dt.day} {MONTHS_ID_DISPLAY.get(dt.month, dt.month)} {dt.year} {dt.hour:02d}:{dt.minute:02d}"

    text = (
        "**Konfirmasi pembuatan meeting:**\n"
        f"📅 **Topik:** {topic}\n"
        f"⏰ **Waktu (WIB):** {disp}\n\n"
        "Tekan **Konfirmasi** untuk membuat meeting di Zoom, atau **Batal** untuk membatalkan."
    )
    # reply with keyboard and set confirm state
    await msg.reply(text, reply_markup=kb, parse_mode="Markdown")
    await state.set_state(MeetingStates.confirm)


@router.callback_query(lambda c: c.data and c.data == 'cancel_create')
async def cb_cancel_create(c: CallbackQuery, state: FSMContext):
    # Only allow the user who started the flow to cancel (FSM is per-user but double-check)
    logger.info("User %s cancelled meeting creation", getattr(c.from_user, 'id', None))
    await _safe_edit_or_fallback(c, "**Pembuatan meeting dibatalkan.**", parse_mode="Markdown")
    await state.clear()
    await c.answer("Dibatalkan")


@router.callback_query(lambda c: c.data and c.data == 'confirm_create')
async def cb_confirm_create(c: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    topic = data.get('topic')
    start_time_iso = data.get('start_time_iso')
    if not (topic and start_time_iso):
        await c.answer("Data tidak lengkap, mulai lagi.")
        await state.clear()
        return

    # edit message to show progress
    logger.info("User %s confirmed meeting creation", getattr(c.from_user, 'id', None))
    await _safe_edit_or_fallback(c, "**Membuat meeting... Mohon tunggu.**", parse_mode="Markdown")

    # create meeting via Zoom API
    user_id = 'me'  # default to 'me' if no specific user configured
    logger.debug("Creating meeting: chosen zoom user_id=%s (zoom_account_id=%s)", user_id, settings.zoom_account_id)
    try:
        meeting = await zoom_client.create_meeting(user_id=str(user_id), topic=topic, start_time=start_time_iso)
        logger.info("Meeting created: %s", meeting.get('id') or meeting)
    except Exception as e:
        logger.exception("Failed to create meeting: %s", e)
        await _safe_edit_or_fallback(c, f"**❌ Gagal membuat meeting:** {e}", parse_mode="Markdown")
        await state.clear()
        await c.answer("Gagal membuat meeting")
        return

    join = meeting.get('join_url') or meeting.get('start_url') or ''

    # Save to DB
    zoom_id = meeting.get('id')
    if zoom_id:
        await add_meeting(str(zoom_id), topic, start_time_iso, join, c.from_user.id)
    dt_iso = data.get('_dt_display')
    if not isinstance(dt_iso, str):
        await _safe_edit_or_fallback(c, "Terjadi kesalahan internal: waktu tidak tersedia.")
        await c.answer("Gagal")
        return

    dt = datetime.fromisoformat(dt_iso)
    DAYS_ID = ['Senin','Selasa','Rabu','Kamis','Jumat','Sabtu','Minggu']
    MONTHS_ID_DISPLAY = {1:'Januari',2:'Februari',3:'Maret',4:'April',5:'Mei',6:'Juni',7:'Juli',8:'Agustus',9:'September',10:'Oktober',11:'November',12:'Desember'}
    day_name = DAYS_ID[dt.weekday()]
    disp_date = f"{day_name}, {dt.day} {MONTHS_ID_DISPLAY.get(dt.month, dt.month)} {dt.year}"
    disp_time = f"{dt.hour:02d}:{dt.minute:02d}"

    # greeting depends on current WIB time when command made
    now_wib = datetime.now(timezone(timedelta(hours=7)))
    h = now_wib.hour
    if 4 <= h < 10:
        greeting = 'Selamat pagi'
    elif 10 <= h < 15:
        greeting = 'Selamat siang'
    elif 15 <= h < 18:
        greeting = 'Selamat sore'
    else:
        greeting = 'Selamat malam'

    text = (
        f"**{greeting} Bapak/Ibu/Rekan-rekan**\n"
        f"**Berikut disampaikan Kegiatan {topic} pada:**\n\n"
        f"📆  {disp_date}\n"
        f"⏰  {disp_time} WIB – selesai\n"
        f"🔗  {join}\n\n"
        "**Demikian disampaikan, terimakasih.**"
    )

    # prepare Short URL button using a temporary token
    token = uuid.uuid4().hex
    # store mapping in-memory (module-level)
    # store mapping in-memory (module-level)
    globals().setdefault('TEMP_MEETINGS', {})
    globals()['TEMP_MEETINGS'][token] = join
    logger.debug("Stored temp meeting token=%s -> %s", token, join)

    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔗 Buat Short URL", callback_data=f"shorten:{token}")]
    ])

    await _safe_edit_or_fallback(c, text, reply_markup=kb, parse_mode="Markdown")

    await state.clear()
    await c.answer("Meeting dibuat")



@router.callback_query(lambda c: c.data and c.data.startswith('shorten:'))
async def cb_shorten(c: CallbackQuery):
    data = c.data or ""
    if not data:
        await c.answer()
        return

    _, token = data.split(':', 1)
    url = globals().get('TEMP_MEETINGS', {}).get(token)
    if not url:
        await c.answer('URL tidak ditemukan atau sudah kadaluarsa', show_alert=True)
        return

    await c.answer('Membuat short URL...')
    try:
        logger.info("Generating short URL for token=%s", token)
        short = await make_short(url)
        logger.info("Short URL created: %s", short)
        # Update DB with short URL
        # Find meeting by join_url? But we have token, need to map.
        # Since TEMP_MEETINGS has url -> token, but to find zoom_id, perhaps store zoom_id in TEMP_MEETINGS or find another way.
        # For now, since we have url, but to update DB, we need zoom_id.
        # Perhaps modify TEMP_MEETINGS to store zoom_id as well.
        # But for simplicity, since we have the url, and meetings table has join_url, we can update by join_url.
        await update_meeting_short_url_by_join_url(url, short)
    except Exception as e:
        logger.exception("Failed to create short URL: %s", e)
        await c.answer(f'**❌ Gagal membuat short URL:** {e}', show_alert=True, parse_mode="Markdown")
        return

    # append short url to message and remove button
    # append short url to message and remove button
    m = getattr(c, 'message', None)
    m_text = getattr(m, 'text', None) if m is not None else None
    if isinstance(m_text, str):
        new_text = (m_text or '') + f"\n\nShort URL: {short}"
        await _safe_edit_or_fallback(c, new_text)
    else:
        # fallback: answer the callback with the short url
        await c.answer(f"Short URL: {short}")

    # optionally remove mapping
    try:
        globals().get('TEMP_MEETINGS', {}).pop(token, None)
    except Exception:
        pass
    await c.answer('Short URL dibuat')


# Generic loggers placed at end so they don't prevent specific handlers from being
# registered earlier in this module. These log incoming commands and callback data
# for easier debugging but do not answer/edit messages themselves.
@router.message(lambda m: m.text and m.text.startswith('/'))
async def _log_incoming_command(msg: Message):
    try:
        cmd = (msg.text or '').split()[0]
    except Exception:
        cmd = msg.text or '<unknown>'
    # use DEBUG to reduce noise; middleware will provide guaranteed pre-processing logs
    logger.debug("Processing command %s from user=%s chat_id=%s username=%s",
                 cmd,
                 getattr(msg.from_user, 'id', None),
                 getattr(getattr(msg, 'chat', None), 'id', None),
                 getattr(getattr(msg, 'from_user', None), 'username', None))


@router.callback_query()
async def _log_incoming_callback(c: CallbackQuery):
    try:
        data = getattr(c, 'data', None)
        user_id = getattr(c.from_user, 'id', None) if c.from_user is not None else None
        username = getattr(c.from_user, 'username', None) if c.from_user is not None else None
        msg_obj = getattr(c, 'message', None)
        msg_id = getattr(msg_obj, 'message_id', None) if msg_obj is not None else None
        chat_id = getattr(getattr(msg_obj, 'chat', None), 'id', None) if msg_obj is not None else None
        # DEBUG level to reduce log noise; include chat id and username for richer context
        logger.debug("Processing callback data=%s from user=%s username=%s chat_id=%s message_id=%s",
                     data, user_id, username, chat_id, msg_id)
    except Exception:
        logger.exception("Failed to log incoming callback")

