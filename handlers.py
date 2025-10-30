from aiogram import Router, F, Bot
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton, Document
from aiogram.filters import Command
from aiogram.exceptions import TelegramBadRequest
from aiogram.fsm.state import StatesGroup, State
from aiogram.fsm.context import FSMContext
from typing import Optional
from db import add_pending_user, list_pending_users, list_all_users, update_user_status, get_user_by_telegram_id, ban_toggle_user, delete_user, add_meeting, update_meeting_short_url, update_meeting_short_url_by_join_url, list_meetings_with_shortlinks, sync_meetings_from_zoom, update_expired_meetings, update_meeting_status, backup_database, backup_shorteners, create_backup_zip, restore_database, restore_shorteners, extract_backup_zip
from keyboards import pending_user_buttons, pending_user_owner_buttons, user_action_buttons, all_users_buttons, role_selection_buttons, status_selection_buttons, list_meetings_buttons, shortener_provider_buttons, shortener_provider_selection_buttons, shortener_custom_choice_buttons, back_to_main_buttons, back_to_main_new_buttons
from config import settings
from auth import is_allowed_to_create, is_owner_or_admin
from zoom import zoom_client
import logging

import re
from datetime import datetime, date, time, timedelta, timezone
import uuid
from shortener import make_short
import shlex
import os
import shutil
import tempfile

router = Router()
# in-memory temp mapping token -> original url (short-lived)
TEMP_MEETINGS: dict = {}

logger = logging.getLogger(__name__)

# FSM States
class MeetingStates(StatesGroup):
    topic = State()
    date = State()
    time = State()
    confirm = State()


class ShortenerStates(StatesGroup):
    waiting_for_url = State()
    waiting_for_provider = State()
    waiting_for_custom_choice = State()
    waiting_for_custom_url = State()


class RestoreStates(StatesGroup):
    waiting_for_file = State()


def extract_zoom_meeting_id(url: str) -> Optional[str]:
    """Extract zoom meeting ID from Zoom URL.
    
    URL format: https://us02web.zoom.us/j/<meeting_id>?pwd=...
    Returns meeting_id or None if not found.
    """
    if not url:
        return None
    
    # Match zoom.us/j/ followed by digits until ? or end
    match = re.search(r'zoom\.us/j/(\d+)', url)
    if match:
        return match.group(1)
    
    return None

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

def _parse_indonesia_date(date_str: str) -> Optional[date]:
    """Parse Indonesian date formats into date object.
    
    Supported formats:
    - DD-MM-YYYY (e.g., "31-12-2025")
    - DD/MM/YYYY (e.g., "31/12/2025") 
    - "DD Month YYYY" (e.g., "31 Desember 2025")
    - "DD MonthName YYYY" (e.g., "31 December 2025")
    """
    if not date_str:
        return None
    
    date_str = date_str.strip()
    
    # Indonesian month names mapping
    months_id = {
        'januari': 1, 'februari': 2, 'maret': 3, 'april': 4, 'mei': 5, 'juni': 6,
        'juli': 7, 'agustus': 8, 'september': 9, 'oktober': 10, 'november': 11, 'desember': 12,
        # English month names for compatibility
        'january': 1, 'february': 2, 'march': 3, 'april': 4, 'may': 5, 'june': 6,
        'july': 7, 'august': 8, 'september': 9, 'october': 10, 'november': 11, 'december': 12
    }
    
    try:
        # Try DD-MM-YYYY or DD/MM/YYYY format first
        if re.match(r'^\d{1,2}[-/]\d{1,2}[-/]\d{4}$', date_str):
            parts = re.split(r'[-/]', date_str)
            day, month, year = int(parts[0]), int(parts[1]), int(parts[2])
            return date(year, month, day)
        
        # Try "DD Month YYYY" format
        match = re.match(r'^(\d{1,2})\s+(\w+)\s+(\d{4})$', date_str, re.IGNORECASE)
        if match:
            day = int(match.group(1))
            month_name = match.group(2).lower()
            year = int(match.group(3))
            
            month = months_id.get(month_name)
            if month:
                return date(year, month, day)
        
        # If no format matches, return None
        return None
        
    except (ValueError, IndexError):
        return None


def _parse_time_24h(time_str: str) -> Optional[time]:
    """Parse 24-hour time format HH:MM into time object.
    
    Supported formats:
    - HH:MM (e.g., "14:30")
    - H:MM (e.g., "9:30")
    - HHMM (e.g., "1430")
    """
    if not time_str:
        return None
    
    time_str = time_str.strip()
    
    try:
        # Try HH:MM format
        match = re.match(r'^(\d{1,2}):(\d{2})$', time_str)
        if match:
            hour = int(match.group(1))
            minute = int(match.group(2))
            if 0 <= hour <= 23 and 0 <= minute <= 59:
                return time(hour, minute)
        
        # Try HHMM format (no colon)
        match = re.match(r'^(\d{2})(\d{2})$', time_str)
        if match:
            hour = int(match.group(1))
            minute = int(match.group(2))
            if 0 <= hour <= 23 and 0 <= minute <= 59:
                return time(hour, minute)
        
        return None
        
    except (ValueError, IndexError):
        return None


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
        f"Your Telegram ID: `{uid}`\n"
        f"Your username: `{username or '-'}`\n"
        f"Is owner: `{is_owner}`"
    )
    await msg.reply(text, parse_mode="Markdown")


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
        "<code>/meet &lt;topic&gt; &lt;date&gt; &lt;time&gt;</code> - Buat meeting Zoom cepat\n"
        "🔹 Support batch: kirim multiple baris untuk membuat banyak meeting sekaligus\n"
        "<code>/zoom_del &lt;zoom_meeting_id&gt;</code> - Hapus meeting Zoom cepat\n"
        "🔹 Support batch: kirim multiple baris untuk menghapus banyak meeting sekaligus\n\n"
        "<code>/whoami</code> - Tampilkan informasi akun Telegram Anda\n\n"
    )

    if is_admin:
        help_text += (
            "<b>Perintah Admin (khusus Owner/Admin):</b>\n"
            "<code>/register_list</code> - Lihat daftar user yang menunggu persetujuan\n"
            "<code>/all_users</code> - Kelola semua user (ubah role, status, hapus)\n"
            "<code>/sync_meetings</code> - Sinkronkan meetings dari Zoom ke database (menandai yang dihapus & expired)\n"
            "<code>/check_expired</code> - Periksa dan tandai meeting yang sudah lewat waktu mulai\n"
            "<code>/backup</code> - Buat backup database dan konfigurasi shorteners\n"
            "<code>/restore</code> - Restore dari file backup ZIP\n\n"
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

    await msg.reply(help_text, reply_markup=back_to_main_new_buttons(), parse_mode="HTML")


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
    await msg.reply(about_text, reply_markup=back_to_main_new_buttons(), parse_mode="HTML")


@router.message(Command("meet"))
async def cmd_zoom(msg: Message):
    """Quick create Zoom meeting(s): /meet <topic> <date> <time>
    
    Support batch creation with multiple lines:
    /meet "Meeting 1" "25 Oktober 2025" "14:30"
    "Meeting 2" "26 Oktober 2025" "15:00"
    "Meeting 3" "27 Oktober 2025" "16:00"   
    """
    if msg.from_user is None or not msg.text:
        await msg.reply("Informasi tidak lengkap")
        return

    user = await get_user_by_telegram_id(msg.from_user.id)
    if not is_allowed_to_create(user):
        await msg.reply("Anda belum diizinkan membuat meeting.", reply_markup=back_to_main_new_buttons())
        return

    # Split message into lines and process each line as a separate meeting
    lines = [line.strip() for line in msg.text.split('\n') if line.strip()]
    
    if not lines:
        await msg.reply("Tidak ada data meeting yang ditemukan.",reply_markup=back_to_main_new_buttons())
        return
    
    # Remove the command from first line
    first_line = lines[0]
    if first_line.startswith('/meet'):
        first_line = first_line[5:].strip()  # Remove "/meet" prefix
        lines[0] = first_line
    
    # Filter out empty lines after processing
    lines = [line for line in lines if line]
    
    if not lines:
        await msg.reply("Format: /meet <topic> <date> <time>\n\nContoh:\n/meet \"Rapat Mingguan\" \"31-12-2025\" \"14:30\"\n\nAtau untuk batch:\n/meet \"Meeting 1\" \"25 Oktober 2025\" \"14:30\"\n\"Meeting 2\" \"26 Oktober 2025\" \"15:00\"")
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
            logger.info("Meeting created via /meet batch: %s", meeting.get('id') or meeting)
            
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

    await msg.reply(summary, reply_markup=back_to_main_new_buttons(), parse_mode="HTML")

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
                text += f"**{i}. Zoom Meeting {topic}**\n\n```\n{greeting} Bapak/Ibu/Rekan-rekan\nBerikut disampaikan Kegiatan {topic} pada:\n\n📆  {disp_date}\n⏰  {disp_time} WIB – selesai\n🔗  {join_url}\n\nDemikian disampaikan, terimakasih.\n```"
                
                # Add separator between meetings (except for the last one)
                if i < len(successful_meetings):
                    text += "\n\n" + "="*50 + "\n\n"
                
                # Add short URL button for this meeting
                token = f"{meeting['zoom_id']}_{uuid.uuid4().hex[:8]}"
                globals().setdefault('TEMP_MEETINGS', {})
                # Store complete meeting info for consistent UX with FSM meeting creation
                globals()['TEMP_MEETINGS'][token] = {
                    'url': join_url,
                    'topic': topic,
                    'disp_date': disp_date,
                    'disp_time': disp_time,
                    'meeting_id': meeting['zoom_id'],
                    'greeting': greeting
                }
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
            f"⏰ Ditandai Expired: {stats.get('expired', 0)}\n"
            f"❌ Error: {stats['errors']}\n\n"
            "<i>Sistem otomatis mensinkronkan setiap 30 menit dan saat startup.</i>"
        )
        await msg.reply(text, reply_markup=back_to_main_buttons(), parse_mode="HTML")
    except Exception as e:
        logger.exception("Manual sync failed: %s", e)
        await msg.reply(f"❌ <b>Gagal melakukan sinkronisasi:</b> {e}", reply_markup=back_to_main_buttons(), parse_mode="HTML")


@router.message(Command("check_expired"))
async def cmd_check_expired(msg: Message):
    """Manually check and update expired meetings (owner only)."""
    if msg.from_user is None:
        return

    # Only owner can run expiry check
    if settings.owner_id is None or msg.from_user.id != settings.owner_id:
        await msg.reply("Hanya owner yang dapat menjalankan check expired meetings.")
        return

    await msg.reply("🔍 Memeriksa meeting yang sudah expired...")

    try:
        stats = await update_expired_meetings()
        text = (
            "✅ <b>Pemeriksaan expired selesai!</b>\n\n"
            f"📊 <b>Statistik:</b>\n"
            f"⏰ Meeting ditandai expired: {stats['expired']}\n"
            f"❌ Error: {stats['errors']}\n\n"
            "<i>Meeting yang sudah lewat waktu mulai akan ditandai sebagai expired.</i>"
        )
        await msg.reply(text, reply_markup=back_to_main_buttons(), parse_mode="HTML")
    except Exception as e:
        logger.exception("Manual expiry check failed: %s", e)
        await msg.reply(f"❌ <b>Gagal memeriksa expired meetings:</b> {e}", reply_markup=back_to_main_buttons(), parse_mode="HTML")


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
                f"Username Telegram : ```{msg.from_user.username or '-'}```\n"
                f"User ID Telegram : ```{msg.from_user.id}```\n"
            )
            await msg.reply(text, parse_mode="Markdown")
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


class ShortenerStates(StatesGroup):
    waiting_for_url = State()
    waiting_for_provider = State()
    waiting_for_custom_choice = State()
    waiting_for_custom_url = State()


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


@router.message(MeetingStates.topic)
async def meeting_topic(msg: Message, state: FSMContext):
    if not msg.text:
        await msg.reply("Silakan kirim topik meeting sebagai teks.")
        return

    logger.debug("meeting_topic received: %s", msg.text)
    await state.update_data(topic=msg.text.strip())
    await msg.reply("**Step 2/3**\n_Kapan diadakan?_\nFormat: `DD-MM-YYYY` atau '`31-12-2025`' atau tulis seperti '`31 Desember 2025`' (Bulan dalam bahasa Indonesia).", parse_mode="Markdown")
    await state.set_state(MeetingStates.date)


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
        [InlineKeyboardButton(text="✅ Konfirmasi", callback_data="confirm_create")],
        [InlineKeyboardButton(text="❌ Batal", callback_data="cancel_create")]
    ])

    # display summary in Indonesian month format
    MONTHS_ID_DISPLAY = {1:'Januari',2:'Februari',3:'Maret',4:'April',5:'Mei',6:'Juni',7:'Juli',8:'Agustus',9:'September',10:'Oktober',11:'November',12:'Desember'}
    disp = f"{dt.day} {MONTHS_ID_DISPLAY.get(dt.month, dt.month)} {dt.year} {dt.hour:02d}:{dt.minute:02d}"

    text = (
        "**Konfirmasi pembuatan meeting:**\n"
        f"📃 **Topik:** {topic}\n"
        f"⏰ **Waktu (WIB):** {disp}\n\n"
        "Tekan **Konfirmasi** untuk membuat meeting di Zoom, atau **Batal** untuk membatalkan."
    )
    # reply with keyboard and set confirm state
    await msg.reply(text, reply_markup=kb, parse_mode="Markdown")
    await state.set_state(MeetingStates.confirm)


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
    # Store complete meeting info for better UX when shortening
    globals()['TEMP_MEETINGS'][token] = {
        'url': join,
        'topic': topic,
        'disp_date': disp_date,
        'disp_time': disp_time,
        'meeting_id': zoom_id,
        'greeting': greeting
    }
    logger.debug("Stored temp meeting token=%s with complete info", token)

    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔗 Buat Short URL", callback_data=f"shorten:{token}")]
    ])

    await _safe_edit_or_fallback(c, text, reply_markup=kb, parse_mode="Markdown")

    await state.clear()
    await c.answer("Meeting dibuat")


@router.callback_query(lambda c: c.data and c.data == 'cancel_create')
async def cb_cancel_create(c: CallbackQuery, state: FSMContext):

    # show inline buttons: back to main or create new meeting
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🏠 Kembali ke Menu Utama", callback_data="back_to_main_new")],
        [InlineKeyboardButton(text="➕ Create New Meeting", callback_data="create_meeting")],
    ])

    # Only allow the user who started the flow to cancel (FSM is per-user but double-check)
    logger.info("User %s cancelled meeting creation", getattr(c.from_user, 'id', None))
    await _safe_edit_or_fallback(c, "**❌ Pembuatan meeting dibatalkan.**", reply_markup=kb, parse_mode="Markdown")
    await state.clear()
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
        all_meetings = await list_meetings_with_shortlinks()
        # Filter only active meetings (already filtered in query)
        meetings = all_meetings or []

        # Sort meetings by start_time ascending (earliest first).
        # We normalize parsed datetimes to UTC for consistent ordering.
        def _parse_start_time_to_utc(st: str):
            try:
                if not st:
                    return datetime.max.replace(tzinfo=timezone.utc)
                # handle UTC 'Z' suffix
                if isinstance(st, str) and st.endswith('Z'):
                    dt = datetime.fromisoformat(st[:-1]).replace(tzinfo=timezone.utc)
                else:
                    dt = datetime.fromisoformat(st)

                if dt.tzinfo is None:
                    # assume UTC when no tz provided
                    dt = dt.replace(tzinfo=timezone.utc)

                # return in UTC
                return dt.astimezone(timezone.utc)
            except Exception:
                # push unparsable times to the end
                return datetime.max.replace(tzinfo=timezone.utc)

        meetings = sorted(meetings, key=lambda mm: _parse_start_time_to_utc(mm.get('start_time', '')))
        
        if not meetings:
            text = "📅 <b>Tidak ada meeting aktif yang tersimpan.</b>"
            # Try to edit the message directly for refresh
            from aiogram.types import Message as AiMessage
            m = getattr(c, 'message', None)
            if isinstance(m, AiMessage):
                try:
                    await m.edit_text(text, parse_mode="HTML", reply_markup=list_meetings_buttons())
                except Exception:
                    await c.answer("Tidak ada meeting aktif")
            else:
                await c.answer("Tidak ada meeting aktif")
            return

        text = "📅 <b>Daftar Zoom Meeting Aktif:</b>\n\n"
        
        for i, m in enumerate(meetings, 1):
            topic = m.get('topic', 'No Topic')
            start_time = m.get('start_time', '')
            join_url = m.get('join_url', '')
            shortlinks = m.get('shortlinks', [])
            created_by = m.get('created_by', 'Unknown')
            
            # Get creator username
            creator_username = await _get_username_from_telegram_id(created_by)
            
            # Include Meeting ID (try common keys) and Format time for custom display
            meeting_id = m.get('zoom_meeting_id') or 'N/A'
            try:
                # Parse datetime dengan handling berbagai format
                if start_time.endswith('Z'):
                    # Format UTC dengan Z, parse sebagai UTC
                    dt = datetime.fromisoformat(start_time[:-1]).replace(tzinfo=timezone.utc)
                else:
                    # Format ISO dengan timezone atau tanpa timezone
                    dt = datetime.fromisoformat(start_time)

                # Jika datetime sudah memiliki timezone info, gunakan langsung
                # Jika tidak, anggap sebagai UTC dan konversi ke WIB
                if dt.tzinfo is None:
                    # Tidak ada timezone info, anggap UTC
                    wib_tz = timezone(timedelta(hours=7))
                    dt_wib = dt.replace(tzinfo=timezone.utc).astimezone(wib_tz)
                else:
                    # Sudah memiliki timezone info, konversi ke WIB jika perlu
                    wib_tz = timezone(timedelta(hours=7))
                    dt_wib = dt.astimezone(wib_tz)
                
                days_id = {
                    0: 'Senin', 1: 'Selasa', 2: 'Rabu', 3: 'Kamis',
                    4: 'Jumat', 5: 'Sabtu', 6: 'Minggu'
                }
                
                months_id = {
                    1: 'Januari', 2: 'Februari', 3: 'Maret', 4: 'April', 5: 'Mei', 6: 'Juni',
                    7: 'Juli', 8: 'Agustus', 9: 'September', 10: 'Oktober', 11: 'November', 12: 'Desember'
                }
                
                day_name = days_id[dt_wib.weekday()]
                day = dt_wib.day
                month_name = months_id[dt_wib.month]
                year = dt_wib.year
                time_str = dt_wib.strftime("%H:%M")
                
                formatted_time_custom = f"{day_name}, {day} {month_name} {year} pada pukul {time_str}"
                
            except Exception:
                formatted_time_custom = "Waktu tidak tersedia"
            
            text += f"<b>{i}. {topic}</b>\n"
            text += f"🆔 Meeting ID: {meeting_id}\n"
            text += f"👤 Dibuat oleh: {creator_username}\n"
            text += f"🕛 {formatted_time_custom}\n"
            text += f"🔗 Link Zoom: {join_url}\n"
            
            # Display shortlinks with detailed info
            if shortlinks:
                text += f"🔗 <b>Shortlinks ({len(shortlinks)}):</b>\n"
                for j, sl in enumerate(shortlinks, 1):
                    provider_name = sl.get('provider', 'Unknown').upper()
                    short_url = sl.get('short_url', 'N/A')
                    custom_alias = sl.get('custom_alias')
                    created_at = sl.get('created_at', '')
                    
                    # Format creation time
                    try:
                        if created_at:
                            created_dt = datetime.fromisoformat(created_at.replace('Z', '+00:00'))
                            created_wib = created_dt.astimezone(timezone(timedelta(hours=7)))
                            created_str = created_wib.strftime("%d/%m/%y %H:%M")
                        else:
                            created_str = "N/A"
                    except:
                        created_str = "N/A"
                    
                    text += f"  {j}. {provider_name}: {short_url}"
                    if custom_alias:
                        text += f" (custom: {custom_alias})"
                    text += f" - {created_str}\n"
            
            text += "\n"
        
        # Try to edit the message directly for refresh, if fails, don't send new message
        from aiogram.types import Message as AiMessage
        m = getattr(c, 'message', None)
        if isinstance(m, AiMessage):
            try:
                await m.edit_text(text, parse_mode="HTML", reply_markup=list_meetings_buttons())
            except Exception:
                await c.answer("Gagal refresh daftar meeting, coba lagi")
        else:
            await c.answer("Tidak dapat mengakses pesan untuk refresh")
    except Exception as e:
        logger.exception("Failed to list meetings: %s", e)
        # Try to edit the message directly, if fails, don't send new message
        from aiogram.types import Message as AiMessage
        m = getattr(c, 'message', None)
        if isinstance(m, AiMessage):
            try:
                await m.edit_text(f"❌ <b>Gagal mengambil daftar meeting:</b> {e}", parse_mode="HTML", reply_markup=list_meetings_buttons())
            except Exception:
                await c.answer("Gagal refresh daftar meeting")
        else:
            await c.answer("Gagal mengambil daftar meeting")


@router.callback_query(lambda c: c.data == 'short_url')
async def cb_short_url(c: CallbackQuery, state: FSMContext):
    logger.info("cb_short_url called")
    if c.from_user is None:
        await c.answer("Informasi pengguna tidak tersedia")
        return

    user = await get_user_by_telegram_id(c.from_user.id)
    if not is_allowed_to_create(user):
        await c.answer("Anda belum diizinkan menggunakan fitur Short URL.")
        return

    await c.answer()
    text = "**🔗 Short URL Generator - Step 1/4**\n\nKirim URL yang ingin Anda persingkat:\n(contoh: https://example.com)"
    await _safe_edit_or_fallback(c, text, parse_mode="Markdown")
    await state.set_state(ShortenerStates.waiting_for_url)
    logger.info("State set to waiting_for_url")


@router.callback_query(lambda c: c.data and c.data.startswith('shorten:'))
async def cb_shorten_meeting(c: CallbackQuery, state: FSMContext):
    """Handle shorten button for Zoom meeting URLs - directly select provider since URL is known."""
    logger.info("cb_shorten_meeting called")
    if c.from_user is None:
        await c.answer("Informasi pengguna tidak tersedia")
        return

    user = await get_user_by_telegram_id(c.from_user.id)
    if not is_allowed_to_create(user):
        await c.answer("Anda belum diizinkan menggunakan fitur Short URL.")
        return

    # Extract token from callback data
    data = c.data or ""
    if not data:
        await c.answer("Data tidak valid")
        return

    _, token = data.split(':', 1)
    if not token:
        await c.answer("Token tidak valid")
        return

    # Get meeting info from temp storage
    meeting_info = TEMP_MEETINGS.get(token)
    if not meeting_info:
        await c.answer("Informasi meeting tidak ditemukan. Mungkin sudah kedaluwarsa.")
        return
    
    # Extract URL and store complete info in state
    join_url = meeting_info.get('url') if isinstance(meeting_info, dict) else meeting_info
    topic = meeting_info.get('topic', 'Meeting') if isinstance(meeting_info, dict) else 'Meeting'
    await state.update_data(url=join_url, meeting_info=meeting_info if isinstance(meeting_info, dict) else None)

    # Send new message with meeting topic and provider selection
    kb = shortener_provider_selection_buttons()
    text = f"**🔗 Kegiatan {topic} akan di short**\n\nPilih provider shortener:"
    if c.message:
        await c.message.reply(text, reply_markup=kb, parse_mode="Markdown")
    await state.set_state(ShortenerStates.waiting_for_provider)
    logger.info("State set to waiting_for_provider for meeting URL")

    await c.answer()


@router.callback_query(lambda c: c.data and c.data.startswith('select_provider:'))
async def cb_select_provider(c: CallbackQuery, state: FSMContext):
    data = c.data or ""
    if not data:
        await c.answer()
        return

    _, provider = data.split(':', 1)
    logger.info("cb_select_provider called with provider: %s", provider)
    
    # Get current state data
    state_data = await state.get_data()
    logger.info("State data before update: %s", state_data)
    url = state_data.get('url')
    
    if not url:
        logger.error("URL not found in state data")
        await c.answer("URL tidak ditemukan. Silakan mulai ulang.")
        await state.clear()
        return

    # Store provider in state
    await state.update_data(provider=provider)
    logger.info("State updated with provider: %s", provider)
    
    # Check if provider supports custom aliases
    from shortener import DynamicShortener
    shortener = DynamicShortener()
    provider_config = shortener.providers.get(provider, {})
    supports_custom = provider_config.get('supports_custom', False)
    logger.info("Provider %s supports custom: %s", provider, supports_custom)
    
    if supports_custom:
        text = f"**🔗 Short URL Generator - Step 3/4**\n\nURL: `{url}`\nProvider: {provider_config.get('name', provider)}\n\nApakah Anda ingin menggunakan custom URL?"
        await _safe_edit_or_fallback(c, text, reply_markup=shortener_custom_choice_buttons(), parse_mode="Markdown")
        await state.set_state(ShortenerStates.waiting_for_custom_choice)
        logger.info("State set to waiting_for_custom_choice")
    else:
        # Provider doesn't support custom, proceed directly
        await c.answer(f'Membuat short URL dengan {provider_config.get("name", provider)}...')
        await create_short_url(c, state, provider, None)
    
    await c.answer()


@router.callback_query(lambda c: c.data and c.data.startswith('set_custom_url:'))
async def cb_set_custom_url(c: CallbackQuery, state: FSMContext):
    data = c.data or ""
    if not data:
        await c.answer()
        return

    _, token, custom_url = data.split(':', 2)
    url = globals().get('TEMP_MEETINGS', {}).get(token)
    if not url:
        await c.answer('URL tidak ditemukan atau sudah kadaluarsa', show_alert=True)
        return

    await c.answer(f'Membuat short URL dengan custom alias "{custom_url}"...')
    try:
        # Get provider from state data
        state_data = await state.get_data()
        provider = state_data.get('provider')
        if not provider:
            await c.answer("Provider tidak ditemukan. Silakan mulai ulang.")
            return

        await create_short_url(c, state, provider, custom_url)
    except Exception as e:
        logger.exception("Failed to create short URL with custom alias: %s", e)
        await c.answer(f'**❌ Gagal membuat short URL:** {e}', show_alert=True, parse_mode="Markdown")


async def create_short_url(update_obj, state: FSMContext, provider: str, custom: Optional[str] = None):
    """Helper function to create short URL and handle the result"""
    state_data = await state.get_data()
    url = state_data.get('url')
    
    if not url:
        if hasattr(update_obj, 'answer'):
            await update_obj.answer("URL tidak ditemukan.")
        return

    # Get user ID
    user_id = None
    if hasattr(update_obj, 'from_user') and update_obj.from_user:
        user_id = update_obj.from_user.id
    elif hasattr(update_obj, 'message') and update_obj.message and hasattr(update_obj.message, 'from_user') and update_obj.message.from_user:
        user_id = update_obj.message.from_user.id

    # Create initial shortlink record
    from db import add_shortlink
    zoom_meeting_id = extract_zoom_meeting_id(url)
    shortlink_id = await add_shortlink(
        original_url=url,
        short_url=None,
        provider=provider,
        custom_alias=custom,
        zoom_meeting_id=zoom_meeting_id,
        created_by=user_id
    )

    try:
        logger.info("Creating short URL for %s with provider %s, custom=%s", url, provider, custom)
        short = await make_short(url, provider=provider, custom=custom)
        logger.info("Short URL created: %s", short)
        
        # Update shortlink record with success
        from db import update_shortlink_status
        await update_shortlink_status(shortlink_id, 'active', short_url=short)
        
        # Clear state
        await state.clear()
        
        # Check if this shortening came from meeting creation
        meeting_info = state_data.get('meeting_info')
        if meeting_info and isinstance(meeting_info, dict):
            # This is from meeting creation - show complete meeting info with short URL
            from shortener import DynamicShortener
            shortener = DynamicShortener()
            provider_config = shortener.providers.get(provider, {})
            provider_name = provider_config.get('name', provider)
            
            topic = meeting_info.get('topic', 'Meeting')
            disp_date = meeting_info.get('disp_date', '')
            disp_time = meeting_info.get('disp_time', '')
            greeting = meeting_info.get('greeting', 'Selamat')
            
            text = (
                f"**{greeting} Bapak/Ibu/Rekan-rekan**\n"
                f"**Berikut disampaikan Kegiatan {topic} pada:**\n\n"
                f"📆  {disp_date}\n"
                f"⏰  {disp_time} WIB – selesai\n"
                f"🔗  {short}\n\n"
                "**Demikian disampaikan, terimakasih.**"
            )
            
            # Add buttons for additional actions
            kb = InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="🔗 Buat Short URL Lain", callback_data="short_url")],
                [InlineKeyboardButton(text="🏠 Kembali ke Menu Utama", callback_data="back_to_main_new")],
            ])
            reply_markup = kb
        else:
            # Regular shortening - show standard success message
            from shortener import DynamicShortener
            shortener = DynamicShortener()
            provider_config = shortener.providers.get(provider, {})
            provider_name = provider_config.get('name', provider)
            
            text = f"✅ **Short URL Berhasil Dibuat!**\n\n🔗 **URL Asli:** `{url}`\n🔗 **Short URL:** `{short}`\n🔗 **Provider:** {provider_name}"
            if custom:
                text += f"\n🔗 **Custom Alias:** `{custom}`"
            
            reply_markup = back_to_main_new_buttons()
        
        # Handle different update types - send new message instead of editing
        if hasattr(update_obj, 'message') and update_obj.message:
            # It's a CallbackQuery - reply to the message
            await update_obj.message.reply(text, reply_markup=reply_markup, parse_mode="Markdown")
        else:
            # It's a Message - reply to it
            await update_obj.reply(text, reply_markup=reply_markup, parse_mode="Markdown")
        
    except Exception as e:
        logger.exception("Failed to create short URL: %s", e)
        
        # Update shortlink record with failure
        from db import update_shortlink_status
        await update_shortlink_status(shortlink_id, 'failed', error_message=str(e))
        
        error_msg = f'❌ Gagal membuat short URL: {e}'
        if hasattr(update_obj, 'answer'):
            await update_obj.answer(error_msg, show_alert=True)
        else:
            await update_obj.reply(error_msg)


@router.callback_query(lambda c: c.data == 'custom_yes')
async def cb_custom_yes(c: CallbackQuery, state: FSMContext):
    logger.info("cb_custom_yes called with callback data: %s", c.data)
    state_data = await state.get_data()
    logger.info("Current state data: %s", state_data)
    url = state_data.get('url')
    provider = state_data.get('provider')
    
    if not url or not provider:
        logger.error("Missing url or provider in state data")
        await c.answer("Data tidak lengkap. Silakan mulai ulang.")
        await state.clear()
        return

    from shortener import DynamicShortener
    shortener = DynamicShortener()
    provider_config = shortener.providers.get(provider, {})
    provider_name = provider_config.get('name', provider)
    
    text = f"**🔗 Short URL Generator - Step 4/4**\n\nURL: `{url}`\nProvider: {provider_name}\n\n✅ **Custom URL dipilih!**\n\nSilahkan masukkan custom URL yang diinginkan:\n\nℹ️ **Aturan:**\n• Hanya huruf, angka, underscore (_), dash (-), titik (.)\n• Minimal 3 karakter, maksimal 50 karakter\n• Contoh: `my-link`, `test_123`, `example.site`"
    
    await _safe_edit_or_fallback(c, text, parse_mode="Markdown")
    await state.set_state(ShortenerStates.waiting_for_custom_url)
    logger.info("State set to waiting_for_custom_url")
    await c.answer()


@router.callback_query(lambda c: c.data == 'custom_no')
async def cb_custom_no(c: CallbackQuery, state: FSMContext):
    state_data = await state.get_data()
    provider = state_data.get('provider')
    
    if not provider:
        await c.answer("Provider tidak ditemukan. Silakan mulai ulang.")
        await state.clear()
        return

    await c.answer('Membuat short URL tanpa custom alias...')
    await create_short_url(c, state, provider, None)


@router.callback_query(lambda c: c.data == 'cancel_shortener_flow')
async def cb_cancel_shortener_flow(c: CallbackQuery, state: FSMContext):
    await state.clear()
    await c.answer("Dibatalkan")
    text = "❌ **Short URL dibatalkan**\n\nPilih aksi:"
    await _safe_edit_or_fallback(c, text, reply_markup=user_action_buttons(), parse_mode="Markdown")


@router.message(ShortenerStates.waiting_for_custom_url)
async def shortener_receive_custom_url(msg: Message, state: FSMContext):
    if not msg.text:
        await msg.reply("Silakan kirim custom URL yang valid.")
        return

    custom_url = msg.text.strip()
    
    # Validate custom URL
    import re
    if not re.match(r'^[a-zA-Z0-9._-]+$', custom_url):
        await msg.reply("❌ **Custom URL tidak valid!**\n\nHanya boleh menggunakan:\n• Huruf (a-z, A-Z)\n• Angka (0-9)\n• Underscore (_)\n• Dash (-)\n• Titik (.)\n\nKirim ulang custom URL yang benar:")
        return
    
    if len(custom_url) < 3:
        await msg.reply("❌ **Custom URL terlalu pendek!**\n\nMinimal 3 karakter. Kirim ulang:")
        return
    
    if len(custom_url) > 50:
        await msg.reply("❌ **Custom URL terlalu panjang!**\n\nMaksimal 50 karakter. Kirim ulang:")
        return

    # Get state data
    state_data = await state.get_data()
    provider = state_data.get('provider')
    
    if not provider:
        await msg.reply("❌ Terjadi kesalahan. Silakan mulai ulang dari menu Short URL.")
        await state.clear()
        return

    await msg.reply(f'🔄 Membuat short URL dengan custom alias "{custom_url}"...')
    await create_short_url(msg, state, provider, custom_url)


@router.callback_query(lambda c: c.data and c.data.startswith('shorten_provider:'))
async def cb_shorten_provider(c: CallbackQuery):
    data = c.data or ""
    if not data:
        await c.answer()
        return

    _, token, provider = data.split(':', 2)
    url = globals().get('TEMP_MEETINGS', {}).get(token)
    if not url:
        await c.answer('URL tidak ditemukan atau sudah kadaluarsa', show_alert=True)
        return

    # Extract zoom_meeting_id from URL
    zoom_meeting_id = extract_zoom_meeting_id(url)

    # Get user ID
    user_id = c.from_user.id if c.from_user else None

    # Create initial shortlink record
    from db import add_shortlink
    shortlink_id = await add_shortlink(
        original_url=url,
        short_url=None,
        provider=provider,
        custom_alias=None,
        zoom_meeting_id=zoom_meeting_id,
        created_by=user_id
    )

    await c.answer(f'Membuat short URL dengan {provider}...')
    try:
        logger.info("Generating short URL for token=%s with provider=%s", token, provider)
        short = await make_short(url, provider=provider)
        logger.info("Short URL created: %s", short)
        
        # Update shortlink record with success
        from db import update_shortlink_status
        await update_shortlink_status(shortlink_id, 'active', short_url=short)
        
        # Update meeting DB with short URL
        await update_meeting_short_url_by_join_url(url, short)
    except Exception as e:
        logger.exception("Failed to create short URL: %s", e)
        
        # Update shortlink record with failure
        from db import update_shortlink_status
        await update_shortlink_status(shortlink_id, 'failed', error_message=str(e))
        
        await c.answer(f'**❌ Gagal membuat short URL:** {e}', show_alert=True, parse_mode="Markdown")
        return

    # append short url to message and remove button
    m = getattr(c, 'message', None)
    m_text = getattr(m, 'text', None) if m is not None else None
    if isinstance(m_text, str):
        new_text = (m_text or '') + f"\n\n🔗 **Short URL ({provider}):** {short}"
        await _safe_edit_or_fallback(c, new_text, parse_mode="Markdown")
    else:
        # fallback: answer the callback with the short url
        await c.answer(f"Short URL ({provider}): {short}")

    # remove mapping
    try:
        globals().get('TEMP_MEETINGS', {}).pop(token, None)
    except Exception:
        pass


@router.callback_query(lambda c: c.data and c.data.startswith('cancel_shorten:'))
async def cb_cancel_shorten(c: CallbackQuery):
    data = c.data or ""
    if not data:
        await c.answer()
        return

    _, token = data.split(':', 1)
    # Remove the temporary mapping
    try:
        globals().get('TEMP_MEETINGS', {}).pop(token, None)
    except Exception:
        pass
    
    await _safe_edit_or_fallback(c, "**❌ Pembuatan Short URL dibatalkan.**", parse_mode="Markdown")
    await c.answer()


@router.message(Command("zoom_del"))
async def cmd_zoom_del(msg: Message):
    """Quick delete Zoom meeting(s): /zoom_del <zoom_meeting_id>
    
    Support batch deletion with multiple lines:
    /zoom_del <zoom_meeting_id>
    <zoom_meeting_id_1>
    <zoom_meeting_id_2>
    etc.
    """
    if msg.from_user is None or not msg.text:
        await msg.reply("Informasi tidak lengkap")
        return

    user = await get_user_by_telegram_id(msg.from_user.id)
    if not is_allowed_to_create(user):
        await msg.reply("Anda belum diizinkan menghapus meeting.")
        return

    # Split message into lines and process each line as a separate meeting ID
    lines = [line.strip() for line in msg.text.split('\n') if line.strip()]
    
    if not lines:
        await msg.reply("Tidak ada data meeting ID yang ditemukan.")
        return
    
    # Remove the command from first line
    first_line = lines[0]
    if first_line.startswith('/zoom_del'):
        first_line = first_line[9:].strip()  # Remove "/zoom_del" prefix
        lines[0] = first_line
    
    # Filter out empty lines after processing
    lines = [line for line in lines if line]
    
    if not lines:
        await msg.reply("Format: /zoom_del <zoom_meeting_id>\n\nAtau untuk batch:\n/zoom_del <zoom_meeting_id>\n<zoom_meeting_id_1>\n<zoom_meeting_id_2>")
        return

    await msg.reply(f"🔄 Memproses penghapusan {len(lines)} meeting(s)... Mohon tunggu.")

    results = []
    successful = 0
    failed = 0

    for i, line in enumerate(lines, 1):
        zoom_id = line.strip()
        if not zoom_id:
            results.append(f"❌ Meeting {i}: ID kosong")
            failed += 1
            continue
        
        try:
            # Delete from Zoom API
            deleted = await zoom_client.delete_meeting(zoom_id)
            if deleted:
                # Update status in database to 'deleted'
                await update_meeting_status(zoom_id, 'deleted')
                results.append(f"✅ Meeting {i} ({zoom_id}): Berhasil dihapus")
                successful += 1
            else:
                results.append(f"❌ Meeting {i} ({zoom_id}): Gagal dihapus dari Zoom")
                failed += 1
        except Exception as e:
            logger.exception("Failed to delete meeting %d (%s): %s", i, zoom_id, e)
            results.append(f"❌ Meeting {i} ({zoom_id}): Gagal - {e}")
            failed += 1

    # Send summary
    summary = f"📊 <b>Hasil Batch Deletion:</b>\n✅ Berhasil: {successful}\n❌ Gagal: {failed}\n\n"
    summary += "\n".join(results[:10])  # Limit to first 10 results
    if len(results) > 10:
        summary += f"\n... dan {len(results) - 10} hasil lainnya"
    
    await msg.reply(summary, parse_mode="HTML")


@router.message(Command("backup"))
async def cmd_backup(msg: Message, bot: Bot):
    """Create backup of database and shorteners configuration (owner/admin only)."""
    if msg.from_user is None:
        return

    # Only owner can backup
    if settings.owner_id is None or msg.from_user.id != settings.owner_id:
        await msg.reply("❌ Hanya owner yang dapat membuat backup.")
        return

    await msg.reply("🔄 Membuat backup database dan konfigurasi... Mohon tunggu.")

    try:
          # Create backup
          zip_path = create_backup_zip(await backup_database(), backup_shorteners())

          # Send the backup file
          from aiogram.types import FSInputFile
          backup_file = FSInputFile(zip_path)
          await msg.reply_document(
              document=backup_file,
              filename=os.path.basename(zip_path),
              caption="✅ Backup berhasil dibuat!\n\nFile berisi:\n• Database SQL dump\n• Konfigurasi shorteners\n• Metadata backup"
          )

          # Clean up after a short delay to ensure file is sent
          import asyncio
          await asyncio.sleep(1)  # Wait 1 second for file to be sent
          os.unlink(zip_path)
          logger.info("Backup sent successfully to owner")

    except Exception as e:
        logger.exception("Failed to create backup: %s", e)
        await msg.reply(f"❌ Gagal membuat backup: {e}")
@router.message(Command("restore"))
async def cmd_restore(msg: Message, state: FSMContext):
    """Restore database and shorteners from backup file (owner/admin only)."""
    if msg.from_user is None:
        return

    # Only owner can restore
    if settings.owner_id is None or msg.from_user.id != settings.owner_id:
        await msg.reply("❌ Hanya owner yang dapat melakukan restore.")
        return

    await msg.reply(
        "📦 **Mode Restore Backup**\n\n"
        "Kirim file ZIP backup yang ingin direstore.\n\n"
        "⚠️ **PERINGATAN:** Ini akan menggantikan database dan konfigurasi yang ada!\n\n"
        "Pastikan file backup valid dan dari sumber terpercaya.",
        parse_mode="Markdown"
    )

    await state.set_state(RestoreStates.waiting_for_file)


@router.message(RestoreStates.waiting_for_file)
async def handle_restore_file(msg: Message, state: FSMContext, bot: Bot):
    """Handle the uploaded backup file for restore."""
    if msg.from_user is None:
        return

    # Double-check owner permission
    if settings.owner_id is None or msg.from_user.id != settings.owner_id:
        await state.clear()
        return

    if not msg.document:
        await msg.reply("❌ Silakan kirim file ZIP backup yang valid.")
        return

    # Check if it's a ZIP file
    if not msg.document.file_name or not msg.document.file_name.lower().endswith('.zip'):
        await msg.reply("❌ File harus berformat ZIP.")
        return

    await msg.reply("🔄 Memproses file backup... Mohon tunggu.")

    try:
        # Download the file
        file_info = await bot.get_file(msg.document.file_id)
        if not file_info.file_path:
            await msg.reply("❌ Gagal mendapatkan path file.")
            await state.clear()
            return

        temp_zip = tempfile.NamedTemporaryFile(suffix='.zip', delete=False)
        await bot.download_file(file_info.file_path, temp_zip.name)
        temp_zip.close()

        # Extract and validate backup
        extracted_files = extract_backup_zip(temp_zip.name)

        required_files = ['database_backup.sql', 'shorteners_backup.json']
        missing_files = [f for f in required_files if f not in extracted_files]

        if missing_files:
            await msg.reply(f"❌ File backup tidak valid. File yang hilang: {', '.join(missing_files)}")
            # Clean up
            os.unlink(temp_zip.name)
            for f in extracted_files.values():
                if os.path.exists(f):
                    os.unlink(f)
            await state.clear()
            return

        # Perform restore
        await msg.reply("🔄 Memulihkan database...")
        db_stats = await restore_database(extracted_files['database_backup.sql'])

        await msg.reply("🔄 Memulihkan konfigurasi shorteners...")
        shorteners_success = restore_shorteners(extracted_files['shorteners_backup.json'])

        # Clean up
        os.unlink(temp_zip.name)
        for f in extracted_files.values():
            if os.path.exists(f):
                os.unlink(f)

        await state.clear()

        # Send success message
        success_msg = (
            "✅ **Restore Berhasil!**\n\n"
            f"📊 **Database:** {db_stats.get('tables_created', 0)} tabel dibuat, {db_stats.get('rows_inserted', 0)} baris dimasukkan\n"
            f"🔗 **Shorteners:** {'Berhasil' if shorteners_success else 'Gagal'}\n\n"
            "⚠️ Bot akan restart untuk menerapkan perubahan."
        )

        await msg.reply(success_msg, parse_mode="Markdown")

        logger.info("Restore completed successfully by owner")

    except Exception as e:
        logger.exception("Failed to restore backup: %s", e)
        await msg.reply(f"❌ Gagal melakukan restore: {e}")
        await state.clear()


# Generic loggers placed at end so they don't prevent specific handlers from being
# registered earlier in this module. These log incoming commands and callback data
# for easier debugging but do not answer/edit messages themselves.
@router.callback_query(lambda c: c.data == 'back_to_main')
async def cb_back_to_main(c: CallbackQuery):
    """Handle back to main menu - updates the current message."""
    if c.from_user is None:
        await c.answer("Informasi pengguna tidak tersedia")
        return

    user = await get_user_by_telegram_id(c.from_user.id)
    if not user:
        await c.answer("User tidak ditemukan")
        return

    if is_allowed_to_create(user):
        # Personalized greeting with username
        username = c.from_user.username or c.from_user.first_name or "Pengguna"
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
        # Update the current message
        await _safe_edit_or_fallback(c, greeting_text, reply_markup=user_action_buttons(), parse_mode="HTML")
    elif user and user.get('status') == 'banned':
        await _safe_edit_or_fallback(c, "*Anda dibanned dari menggunakan bot ini.*", parse_mode="Markdown")
    else:
        await _safe_edit_or_fallback(c, "*Permintaan Anda sedang menunggu persetujuan.*", parse_mode="Markdown")


@router.callback_query(lambda c: c.data == 'back_to_main_new')
async def cb_back_to_main_new(c: CallbackQuery):
    """Handle back to main menu - sends a new message."""
    if c.from_user is None:
        await c.answer("Informasi pengguna tidak tersedia")
        return

    if c.message is None:
        await c.answer("Pesan tidak dapat diakses")
        return

    user = await get_user_by_telegram_id(c.from_user.id)
    if not user:
        await c.answer("User tidak ditemukan")
        return

    await c.answer()

    if is_allowed_to_create(user):
        # Personalized greeting with username
        username = c.from_user.username or c.from_user.first_name or "Pengguna"
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
        # Send a new message
        await c.message.reply(greeting_text, reply_markup=user_action_buttons(), parse_mode="HTML")
    elif user and user.get('status') == 'banned':
        await c.message.reply("*Anda dibanned dari menggunakan bot ini.*", parse_mode="Markdown")
    else:
        await c.message.reply("*Permintaan Anda sedang menunggu persetujuan.*", parse_mode="Markdown")


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


@router.message(ShortenerStates.waiting_for_url)
async def shortener_receive_url(msg: Message, state: FSMContext):
    logger.info("shortener_receive_url called with: %s", msg.text)
    if not msg.text:
        await msg.reply("Silakan kirim URL yang valid.")
        return

    url = msg.text.strip()
    
    # Validate URL
    if not re.match(r'https?://[^\s]+', url):
        await msg.reply("URL tidak valid. Pastikan dimulai dengan http:// atau https://")
        return

    # Store URL in state
    await state.update_data(url=url)
    logger.info("URL stored in state: %s", url)
    
    # Show provider selection
    text = f"**🔗 Short URL Generator - Step 2/4**\n\nURL: `{url}`\n\nPilih provider yang ingin digunakan:"
    await msg.reply(text, reply_markup=shortener_provider_selection_buttons(), parse_mode="Markdown")
    await state.set_state(ShortenerStates.waiting_for_provider)
    logger.info("State set to waiting_for_provider")




@router.callback_query(lambda c: c.data == 'noop')
async def cb_noop(c: CallbackQuery):
    """No operation callback - just answer to remove loading state."""
    await c.answer()


@router.message(Command("backup"))
async def cmd_backup(msg: Message, bot: Bot):
    """Create backup of database and shorteners configuration (owner/admin only)."""
    if msg.from_user is None:
        return

    # Only owner can backup
    if settings.owner_id is None or msg.from_user.id != settings.owner_id:
        await msg.reply("❌ Hanya owner yang dapat membuat backup.")
        return

    await msg.reply("🔄 Membuat backup database dan konfigurasi... Mohon tunggu.")

    try:
          # Create backup
          zip_path = create_backup_zip(await backup_database(), backup_shorteners())

          # Send the backup file
          from aiogram.types import FSInputFile
          backup_file = FSInputFile(zip_path)
          await msg.reply_document(
              document=backup_file,
              filename=os.path.basename(zip_path),
              caption="✅ Backup berhasil dibuat!\n\nFile berisi:\n• Database SQL dump\n• Konfigurasi shorteners\n• Metadata backup"
          )

          # Clean up after a short delay to ensure file is sent
          import asyncio
          await asyncio.sleep(1)  # Wait 1 second for file to be sent
          os.unlink(zip_path)
          logger.info("Backup sent successfully to owner")

    except Exception as e:
        logger.exception("Failed to create backup: %s", e)
        await msg.reply(f"❌ Gagal membuat backup: {e}")

@router.message(Command("restore"))
async def cmd_restore(msg: Message, state: FSMContext):
    """Restore database and shorteners from backup file (owner/admin only)."""
    if msg.from_user is None:
        return

    # Only owner can restore
    if settings.owner_id is None or msg.from_user.id != settings.owner_id:
        await msg.reply("❌ Hanya owner yang dapat melakukan restore.")
        return

    await msg.reply(
        "📦 **Mode Restore Backup**\n\n"
        "Kirim file ZIP backup yang ingin direstore.\n\n"
        "⚠️ **PERINGATAN:** Ini akan menggantikan database dan konfigurasi yang ada!\n\n"
        "Pastikan file backup valid dan dari sumber terpercaya.",
        parse_mode="Markdown"
    )

    await state.set_state(RestoreStates.waiting_for_file)


@router.message(RestoreStates.waiting_for_file)
async def handle_restore_file(msg: Message, state: FSMContext, bot: Bot):
    """Handle the uploaded backup file for restore."""
    if msg.from_user is None:
        return

    # Double-check owner permission
    if settings.owner_id is None or msg.from_user.id != settings.owner_id:
        await state.clear()
        return

    if not msg.document:
        await msg.reply("❌ Silakan kirim file ZIP backup yang valid.")
        return

    # Check if it's a ZIP file
    if not msg.document.file_name or not msg.document.file_name.lower().endswith('.zip'):
        await msg.reply("❌ File harus berformat ZIP.")
        return

    await msg.reply("🔄 Memproses file backup... Mohon tunggu.")

    try:
        # Download the file
        file_info = await bot.get_file(msg.document.file_id)
        if not file_info.file_path:
            await msg.reply("❌ Gagal mendapatkan path file.")
            await state.clear()
            return

        temp_zip = tempfile.NamedTemporaryFile(suffix='.zip', delete=False)
        await bot.download_file(file_info.file_path, temp_zip.name)
        temp_zip.close()

        # Extract and validate backup
        extracted_files = extract_backup_zip(temp_zip.name)

        required_files = ['database_backup.sql', 'shorteners_backup.json']
        missing_files = [f for f in required_files if f not in extracted_files]

        if missing_files:
            await msg.reply(f"❌ File backup tidak valid. File yang hilang: {', '.join(missing_files)}")
            # Clean up
            os.unlink(temp_zip.name)
            for f in extracted_files.values():
                if os.path.exists(f):
                    os.unlink(f)
            await state.clear()
            return

        # Perform restore
        await msg.reply("🔄 Memulihkan database...")
        db_stats = await restore_database(extracted_files['database_backup.sql'])

        await msg.reply("🔄 Memulihkan konfigurasi shorteners...")
        shorteners_success = restore_shorteners(extracted_files['shorteners_backup.json'])

        # Clean up
        os.unlink(temp_zip.name)
        for f in extracted_files.values():
            if os.path.exists(f):
                os.unlink(f)

        await state.clear()

        # Send success message
        success_msg = (
            "✅ **Restore Berhasil!**\n\n"
            f"📊 **Database:** {db_stats.get('tables_created', 0)} tabel dibuat, {db_stats.get('rows_inserted', 0)} baris dimasukkan\n"
            f"🔗 **Shorteners:** {'Berhasil' if shorteners_success else 'Gagal'}\n\n"
            "⚠️ Bot akan restart untuk menerapkan perubahan."
        )

        await msg.reply(success_msg, parse_mode="Markdown")

        logger.info("Restore completed successfully by owner")

    except Exception as e:
        logger.exception("Failed to restore backup: %s", e)
        await msg.reply(f"❌ Gagal melakukan restore: {e}")
        await state.clear()
        await msg.reply(
            "📦 **Mode Restore Backup**\n\n"
            "Kirim file ZIP backup yang ingin direstore.\n\n"
            "⚠️ **PERINGATAN:** Ini akan menggantikan database dan konfigurasi yang ada!\n\n"
            "Pastikan file backup valid dan dari sumber terpercaya.",
            parse_mode="Markdown"
    )

    await state.set_state(RestoreStates.waiting_for_file)


@router.message(RestoreStates.waiting_for_file)
async def handle_restore_file(msg: Message, state: FSMContext, bot: Bot):
    """Handle the uploaded backup file for restore."""
    if msg.from_user is None:
        return

    # Double-check owner permission
    if settings.owner_id is None or msg.from_user.id != settings.owner_id:
        await state.clear()
        return

    if not msg.document:
        await msg.reply("❌ Silakan kirim file ZIP backup yang valid.")
        return

    # Check if it's a ZIP file
    if not msg.document.file_name or not msg.document.file_name.lower().endswith('.zip'):
        await msg.reply("❌ File harus berformat ZIP.")
        return

    await msg.reply("🔄 Memproses file backup... Mohon tunggu.")

    try:
        # Download the file
        file_info = await bot.get_file(msg.document.file_id)
        if not file_info.file_path:
            await msg.reply("❌ Gagal mendapatkan path file.")
            await state.clear()
            return

        temp_zip = tempfile.NamedTemporaryFile(suffix='.zip', delete=False)
        await bot.download_file(file_info.file_path, temp_zip.name)
        temp_zip.close()

        # Extract and validate backup
        extracted_files = extract_backup_zip(temp_zip.name)

        required_files = ['database_backup.sql', 'shorteners_backup.json']
        missing_files = [f for f in required_files if f not in extracted_files]

        if missing_files:
            await msg.reply(f"❌ File backup tidak valid. File yang hilang: {', '.join(missing_files)}")
            # Clean up
            os.unlink(temp_zip.name)
            for f in extracted_files.values():
                if os.path.exists(f):
                    os.unlink(f)
            await state.clear()
            return

        # Perform restore
        await msg.reply("🔄 Memulihkan database...")
        db_stats = await restore_database(extracted_files['database_backup.sql'])

        await msg.reply("🔄 Memulihkan konfigurasi shorteners...")
        shorteners_success = restore_shorteners(extracted_files['shorteners_backup.json'])

        # Clean up
        os.unlink(temp_zip.name)
        for f in extracted_files.values():
            if os.path.exists(f):
                os.unlink(f)

        await state.clear()

        # Send success message
        success_msg = (
            "✅ **Restore Berhasil!**\n\n"
            f"📊 **Database:** {db_stats.get('tables_created', 0)} tabel dibuat, {db_stats.get('rows_inserted', 0)} baris dimasukkan\n"
            f"🔗 **Shorteners:** {'Berhasil' if shorteners_success else 'Gagal'}\n\n"
            "⚠️ Bot akan restart untuk menerapkan perubahan."
        )

        await msg.reply(success_msg, parse_mode="Markdown")

        logger.info("Restore completed successfully by owner")

    except Exception as e:
        logger.exception("Failed to restore backup: %s", e)
        await msg.reply(f"❌ Gagal melakukan restore: {e}")
        await state.clear()


# Generic loggers placed at end so they don't prevent specific handlers from being
# registered earlier in this module. These log incoming commands and callback data
# for easier debugging but do not answer/edit messages themselves.
@router.callback_query(lambda c: c.data == 'back_to_main')
async def cb_back_to_main(c: CallbackQuery):
    """Handle back to main menu - updates the current message."""
    if c.from_user is None:
        await c.answer("Informasi pengguna tidak tersedia")
        return

    user = await get_user_by_telegram_id(c.from_user.id)
    if not user:
        await c.answer("User tidak ditemukan")
        return

    if is_allowed_to_create(user):
        # Personalized greeting with username
        username = c.from_user.username or c.from_user.first_name or "Pengguna"
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
        # Update the current message
        await _safe_edit_or_fallback(c, greeting_text, reply_markup=user_action_buttons(), parse_mode="HTML")
    elif user and user.get('status') == 'banned':
        await _safe_edit_or_fallback(c, "*Anda dibanned dari menggunakan bot ini.*", parse_mode="Markdown")
    else:
        await _safe_edit_or_fallback(c, "*Permintaan Anda sedang menunggu persetujuan.*", parse_mode="Markdown")


@router.callback_query(lambda c: c.data == 'back_to_main_new')
async def cb_back_to_main_new(c: CallbackQuery):
    """Handle back to main menu - sends a new message."""
    if c.from_user is None:
        await c.answer("Informasi pengguna tidak tersedia")
        return

    if c.message is None:
        await c.answer("Pesan tidak dapat diakses")
        return

    user = await get_user_by_telegram_id(c.from_user.id)
    if not user:
        await c.answer("User tidak ditemukan")
        return

    await c.answer()

    if is_allowed_to_create(user):
        # Personalized greeting with username
        username = c.from_user.username or c.from_user.first_name or "Pengguna"
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
        # Send a new message
        await c.message.reply(greeting_text, reply_markup=user_action_buttons(), parse_mode="HTML")
    elif user and user.get('status') == 'banned':
        await c.message.reply("*Anda dibanned dari menggunakan bot ini.*", parse_mode="Markdown")
    else:
        await c.message.reply("*Permintaan Anda sedang menunggu persetujuan.*", parse_mode="Markdown")


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
    await c.answer()


@router.message(ShortenerStates.waiting_for_url)
async def shortener_receive_url(msg: Message, state: FSMContext):
    logger.info("shortener_receive_url called with: %s", msg.text)
    if not msg.text:
        await msg.reply("Silakan kirim URL yang valid.")
        return

    url = msg.text.strip()
    
    # Validate URL
    if not re.match(r'https?://[^\s]+', url):
        await msg.reply("URL tidak valid. Pastikan dimulai dengan http:// atau https://")
        return

    # Store URL in state
    await state.update_data(url=url)
    logger.info("URL stored in state: %s", url)
    
    # Show provider selection
    text = f"**🔗 Short URL Generator - Step 2/4**\n\nURL: `{url}`\n\nPilih provider yang ingin digunakan:"
    await msg.reply(text, reply_markup=shortener_provider_selection_buttons(), parse_mode="Markdown")
    await state.set_state(ShortenerStates.waiting_for_provider)
    logger.info("State set to waiting_for_provider")



@router.callback_query(lambda c: c.data == 'noop')
async def cb_noop(c: CallbackQuery):
    """No operation callback - just answer to remove loading state."""
    await c.answer()


@router.message(Command("backup"))
async def cmd_backup(msg: Message, bot: Bot):
    """Create backup of database and shorteners configuration (owner/admin only)."""
    if msg.from_user is None:
        return

    # Only owner can backup
    if settings.owner_id is None or msg.from_user.id != settings.owner_id:
        await msg.reply("❌ Hanya owner yang dapat membuat backup.")
        return

    await msg.reply("🔄 Membuat backup database dan konfigurasi... Mohon tunggu.")

    try:
          # Create backup
          zip_path = create_backup_zip(await backup_database(), backup_shorteners())

          # Send the backup file
          from aiogram.types import FSInputFile
          backup_file = FSInputFile(zip_path)
          await msg.reply_document(
              document=backup_file,
              filename=os.path.basename(zip_path),
              caption="✅ Backup berhasil dibuat!\n\nFile berisi:\n• Database SQL dump\n• Konfigurasi shorteners\n• Metadata backup"
          )

          # Clean up after a short delay to ensure file is sent
          import asyncio
          await asyncio.sleep(1)  # Wait 1 second for file to be sent
          os.unlink(zip_path)
          logger.info("Backup sent successfully to owner")

    except Exception as e:
        logger.exception("Failed to create backup: %s", e)
        await msg.reply(f"❌ Gagal membuat backup: {e}")

@router.message(Command("restore"))
async def cmd_restore(msg: Message, state: FSMContext):
    """Restore database and shorteners from backup file (owner/admin only)."""
    if msg.from_user is None:
        return

    # Only owner can restore
    if settings.owner_id is None or msg.from_user.id != settings.owner_id:
        await msg.reply("❌ Hanya owner yang dapat melakukan restore.")
        return

    await msg.reply(
        "📦 **Mode Restore Backup**\n\n"
        "Kirim file ZIP backup yang ingin direstore.\n\n"
        "⚠️ **PERINGATAN:** Ini akan menggantikan database dan konfigurasi yang ada!\n\n"
        "Pastikan file backup valid dan dari sumber terpercaya.",
        parse_mode="Markdown"
    )

    await state.set_state(RestoreStates.waiting_for_file)


@router.message(RestoreStates.waiting_for_file)
async def handle_restore_file(msg: Message, state: FSMContext, bot: Bot):
    """Handle the uploaded backup file for restore."""
    if msg.from_user is None:
        return

    # Double-check owner permission
    if settings.owner_id is None or msg.from_user.id != settings.owner_id:
        await state.clear()
        return

    if not msg.document:
        await msg.reply("❌ Silakan kirim file ZIP backup yang valid.")
        return

    # Check if it's a ZIP file
    if not msg.document.file_name or not msg.document.file_name.lower().endswith('.zip'):
        await msg.reply("❌ File harus berformat ZIP.")
        return

    await msg.reply("🔄 Memproses file backup... Mohon tunggu.")

    try:
        # Download the file
        file_info = await bot.get_file(msg.document.file_id)
        if not file_info.file_path:
            await msg.reply("❌ Gagal mendapatkan path file.")
            await state.clear()
            return

        temp_zip = tempfile.NamedTemporaryFile(suffix='.zip', delete=False)
        await bot.download_file(file_info.file_path, temp_zip.name)
        temp_zip.close()

        # Extract and validate backup
        extracted_files = extract_backup_zip(temp_zip.name)

        required_files = ['database_backup.sql', 'shorteners_backup.json']
        missing_files = [f for f in required_files if f not in extracted_files]

        if missing_files:
            await msg.reply(f"❌ File backup tidak valid. File yang hilang: {', '.join(missing_files)}")
            # Clean up
            os.unlink(temp_zip.name)
            for f in extracted_files.values():
                if os.path.exists(f):
                    os.unlink(f)
            await state.clear()
            return

        # Perform restore
        await msg.reply("🔄 Memulihkan database...")
        db_stats = await restore_database(extracted_files['database_backup.sql'])

        await msg.reply("🔄 Memulihkan konfigurasi shorteners...")
        shorteners_success = restore_shorteners(extracted_files['shorteners_backup.json'])

        # Clean up
        os.unlink(temp_zip.name)
        for f in extracted_files.values():
            if os.path.exists(f):
                os.unlink(f)

        await state.clear()

        # Send success message
        success_msg = (
            "✅ **Restore Berhasil!**\n\n"
            f"📊 **Database:** {db_stats.get('tables_created', 0)} tabel dibuat, {db_stats.get('rows_inserted', 0)} baris dimasukkan\n"
            f"🔗 **Shorteners:** {'Berhasil' if shorteners_success else 'Gagal'}\n\n"
            "⚠️ Bot akan restart untuk menerapkan perubahan."
        )

        await msg.reply(success_msg, parse_mode="Markdown")

        logger.info("Restore completed successfully by owner")

    except Exception as e:
        logger.exception("Failed to restore backup: %s", e)
        await msg.reply(f"❌ Gagal melakukan restore: {e}")
        await state.clear()
