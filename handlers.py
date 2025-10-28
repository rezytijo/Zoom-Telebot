from aiogram import Router, F, Bot
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton, Document
from aiogram.filters import Command
from aiogram.exceptions import TelegramBadRequest
from aiogram.fsm.state import StatesGroup, State
from aiogram.fsm.context import FSMContext
from typing import Optional
from db import add_pending_user, list_pending_users, list_all_users, update_user_status, get_user_by_telegram_id, ban_toggle_user, delete_user, add_meeting, update_meeting_short_url, update_meeting_short_url_by_join_url, list_meetings, list_meetings_with_shortlinks, sync_meetings_from_zoom, update_expired_meetings, update_meeting_status, backup_database, backup_shorteners, create_backup_zip, restore_database, restore_shorteners, extract_backup_zip
from keyboards import pending_user_buttons, pending_user_owner_buttons, user_action_buttons, all_users_buttons, role_selection_buttons, status_selection_buttons, list_meetings_buttons, shortener_provider_buttons, shortener_provider_selection_buttons, shortener_custom_choice_buttons, back_to_main_buttons, back_to_main_new_buttons
from config import settings
from auth import is_allowed_to_create
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


@router.message(Command("register_list"))
async def cmd_register_list(msg: Message):
    """Show list of pending users for approval (admin/owner only)."""
    if msg.from_user is None:
        return

    # Check if user is admin/owner
    user = await get_user_by_telegram_id(msg.from_user.id)
    if not user or not is_allowed_to_create(user):
        await msg.reply("❌ Hanya admin/owner yang dapat melihat daftar registrasi.")
        return

    try:
        pending_users = await list_pending_users()

        if not pending_users:
            text = (
                "📋 <b>Daftar Registrasi User</b>\n\n"
                "✅ <b>Tidak ada user yang menunggu persetujuan.</b>\n\n"
                "<i>Semua user sudah diproses.</i>"
            )
            await msg.reply(text, reply_markup=back_to_main_buttons(), parse_mode="HTML")
            return

        # Pagination settings
        users_per_page = 5
        total_users = len(pending_users)
        total_pages = (total_users + users_per_page - 1) // users_per_page  # Ceiling division
        page = 0  # Start from first page

        # Get users for current page
        start_idx = page * users_per_page
        end_idx = min(start_idx + users_per_page, total_users)
        page_users = pending_users[start_idx:end_idx]

        text = (
            "📋 <b>Daftar Registrasi User</b>\n"
            f"📊 <b>Total menunggu:</b> {total_users}\n"
            f"📄 <b>Halaman:</b> {page + 1}/{total_pages}\n\n"
        )

        keyboard_buttons = []

        for user_data in page_users:
            telegram_id = user_data['telegram_id']
            username = user_data['username'] or '-'
            created_at = user_data.get('created_at', 'Unknown')

            # Format created_at if it's a string
            if isinstance(created_at, str) and 'T' in created_at:
                try:
                    dt = datetime.fromisoformat(created_at.replace('Z', '+00:00'))
                    wib_tz = timezone(timedelta(hours=7))
                    dt_wib = dt.astimezone(wib_tz)
                    formatted_date = dt_wib.strftime("%d/%m/%Y %H:%M")
                except:
                    formatted_date = created_at[:19]  # Fallback to first 19 chars
            else:
                formatted_date = str(created_at)

            text += (
                f"👤 <b>@{username}</b> (ID: <code>{telegram_id}</code>)\n"
                f"📅 Daftar: {formatted_date}\n\n"
            )

            # Add action buttons for this user
            if user.get('role') == 'owner':
                keyboard_buttons.append([
                    InlineKeyboardButton(text=f"✅ Terima @{username}", callback_data=f"accept:{telegram_id}"),
                    InlineKeyboardButton(text=f"❌ Tolak @{username}", callback_data=f"reject:{telegram_id}")
                ])
                keyboard_buttons.append([
                    InlineKeyboardButton(text=f"🚫 Ban @{username}", callback_data=f"ban:{telegram_id}")
                ])
            else:
                # Regular admin buttons
                keyboard_buttons.append([
                    InlineKeyboardButton(text=f"✅ Terima @{username}", callback_data=f"accept:{telegram_id}"),
                    InlineKeyboardButton(text=f"❌ Tolak @{username}", callback_data=f"reject:{telegram_id}")
                ])

        # Add navigation buttons if there are multiple pages
        if total_pages > 1:
            nav_buttons = []

            # Previous page button (disabled on first page)
            if page > 0:
                nav_buttons.append(InlineKeyboardButton(text="◀️ Sebelumnya", callback_data=f"register_list:{page - 1}"))

            # Page indicator
            nav_buttons.append(InlineKeyboardButton(text=f"📄 {page + 1}/{total_pages}", callback_data="noop"))

            # Next page button
            if page < total_pages - 1:
                nav_buttons.append(InlineKeyboardButton(text="▶️ Selanjutnya", callback_data=f"register_list:{page + 1}"))

            keyboard_buttons.append(nav_buttons)

        # Add refresh and back buttons
        keyboard_buttons.append([
            InlineKeyboardButton(text="🔄 Refresh", callback_data="register_list:0"),
            InlineKeyboardButton(text="🏠 Kembali ke Menu", callback_data="back_to_main")
        ])

        kb = InlineKeyboardMarkup(inline_keyboard=keyboard_buttons)
        await msg.reply(text, reply_markup=kb, parse_mode="HTML")

    except Exception as e:
        logger.exception("Failed to show register list: %s", e)
        await msg.reply(f"❌ <b>Gagal mengambil daftar registrasi:</b> {e}", reply_markup=back_to_main_buttons(), parse_mode="HTML")


@router.message(Command("all_users"))
async def cmd_all_users(msg: Message):
    """Show list of all active/banned users with management options (admin/owner only)."""
    if msg.from_user is None:
        return

    # Check if user is admin/owner
    user = await get_user_by_telegram_id(msg.from_user.id)
    if not user or not is_allowed_to_create(user):
        await msg.reply("❌ Hanya admin/owner yang dapat melihat daftar semua user.")
        return

    try:
        all_users = await list_all_users()

        # Filter out pending users - only show whitelisted and banned users
        active_users = [u for u in all_users if u['status'] == 'whitelisted']
        banned_users = [u for u in all_users if u['status'] == 'banned']
        filtered_users = active_users + banned_users

        # Calculate statistics
        total_active = len(active_users)
        total_banned = len(banned_users)
        total_users = len(all_users)  # Including pending users

        if not filtered_users:
            text = (
                "👥 <b>Daftar Semua User</b>\n\n"
                f"📊 <b>Total user Aktif:</b> {total_active}\n"
                f"📊 <b>Total User di banned:</b> {total_banned}\n"
                f"📊 <b>Total user:</b> {total_users}\n\n"
                "❌ <b>Tidak ada user aktif atau banned.</b>\n\n"
                "<i>Semua user masih dalam status pending.</i>"
            )
            await msg.reply(text, reply_markup=back_to_main_buttons(), parse_mode="HTML")
            return

        # Pagination settings
        users_per_page = 5
        total_filtered = len(filtered_users)
        total_pages = (total_filtered + users_per_page - 1) // users_per_page  # Ceiling division
        page = 0  # Start from first page

        # Get users for current page
        start_idx = page * users_per_page
        end_idx = min(start_idx + users_per_page, total_filtered)
        page_users = filtered_users[start_idx:end_idx]

        text = (
            "👥 <b>Daftar Semua User</b>\n"
            f"📊 <b>Total user Aktif:</b> {total_active}\n"
            f"📊 <b>Total User di banned:</b> {total_banned}\n"
            f"📊 <b>Total user:</b> {total_users}\n"
            f"📄 <b>Halaman:</b> {page + 1}/{total_pages}\n\n"
        )

        keyboard_buttons = []

        for user_data in page_users:
            telegram_id = user_data['telegram_id']
            username = user_data['username'] or '-'
            role = user_data.get('role', 'user').capitalize()
            status = user_data['status']

            if status == 'whitelisted':
                text += f"✅ <b>@{username}</b>\n"
                text += f"   ├ Role: {role}\n"
                text += f"   └ ID: <code>{telegram_id}</code>\n\n"
                # Add management buttons for active users
                keyboard_buttons.append([
                    InlineKeyboardButton(text=f"⚙️ Kelola @{username}", callback_data=f"manage_user:{telegram_id}")
                ])
            elif status == 'banned':
                text += f"🚫 <b>@{username}</b>\n"
                text += f"   ├ Role: {role}\n"
                text += f"   └ ID: <code>{telegram_id}</code>\n\n"
                # Add unban button for banned users
                keyboard_buttons.append([
                    InlineKeyboardButton(text=f"✅ Unban @{username}", callback_data=f"unban:{telegram_id}")
                ])

        # Add navigation buttons if there are multiple pages
        if total_pages > 1:
            nav_buttons = []

            # Previous page button (disabled on first page)
            if page > 0:
                nav_buttons.append(InlineKeyboardButton(text="◀️ Sebelumnya", callback_data=f"all_users:{page - 1}"))

            # Page indicator
            nav_buttons.append(InlineKeyboardButton(text=f"📄 {page + 1}/{total_pages}", callback_data="noop"))

            # Next page button
            if page < total_pages - 1:
                nav_buttons.append(InlineKeyboardButton(text="▶️ Selanjutnya", callback_data=f"all_users:{page + 1}"))

            keyboard_buttons.append(nav_buttons)

        # Add refresh and back buttons
        keyboard_buttons.append([
            InlineKeyboardButton(text="🔄 Refresh", callback_data="all_users:0"),
            InlineKeyboardButton(text="🏠 Kembali ke Menu", callback_data="back_to_main")
        ])

        kb = InlineKeyboardMarkup(inline_keyboard=keyboard_buttons)
        await msg.reply(text, reply_markup=kb, parse_mode="HTML")

    except Exception as e:
        logger.exception("Failed to show all users list: %s", e)
        await msg.reply(f"❌ <b>Gagal mengambil daftar user:</b> {e}", reply_markup=back_to_main_buttons(), parse_mode="HTML")


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





@router.callback_query(lambda c: c.data and c.data.startswith('accept:'))
async def cb_accept(c: CallbackQuery):
    data = c.data or ""
    if not data:
        await c.answer()
        return

    _, tid = data.split(':', 1)
    telegram_id = int(tid)
    await update_user_status(telegram_id, 'whitelisted', 'user')

    # Instead of showing a simple message, refresh the register list
    # Create a mock callback with register_list:0 to refresh to first page
    mock_callback = type('MockCallback', (), {
        'data': 'register_list:0',
        'from_user': c.from_user,
        'message': c.message,
        'answer': c.answer
    })()

    await cb_register_list(mock_callback)


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
        # Instead of showing a simple message, refresh the register list
        mock_callback = type('MockCallback', (), {
            'data': 'register_list:0',
            'from_user': c.from_user,
            'message': c.message,
            'answer': c.answer
        })()
        await cb_register_list(mock_callback)
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

    # Instead of showing a simple message, refresh the all users list
    mock_callback = type('MockCallback', (), {
        'data': 'all_users:0',
        'from_user': c.from_user,
        'message': c.message,
        'answer': c.answer
    })()
    await cb_all_users(mock_callback)


@router.callback_query(lambda c: c.data and c.data.startswith('ban:'))
async def cb_ban(c: CallbackQuery):
    data = c.data or ""
    if not data:
        await c.answer()
        return

    _, tid = data.split(':', 1)
    telegram_id = int(tid)
    await ban_toggle_user(telegram_id, True)

    # Instead of showing a simple message, refresh the register list
    mock_callback = type('MockCallback', (), {
        'data': 'register_list:0',
        'from_user': c.from_user,
        'message': c.message,
        'answer': c.answer
    })()
    await cb_register_list(mock_callback)


@router.callback_query(lambda c: c.data and c.data.startswith('unban:'))
async def cb_unban(c: CallbackQuery):
    data = c.data or ""
    if not data:
        await c.answer()
        return

    _, tid = data.split(':', 1)
    telegram_id = int(tid)
    await ban_toggle_user(telegram_id, False)  # False = unban

    # Instead of showing a simple message, refresh the all users list
    mock_callback = type('MockCallback', (), {
        'data': 'all_users:0',
        'from_user': c.from_user,
        'message': c.message,
        'answer': c.answer
    })()
    await cb_all_users(mock_callback)


@router.callback_query(lambda c: c.data and c.data.startswith('manage_user:'))
async def cb_manage_user(c: CallbackQuery):
    data = c.data or ""
    if not data:
        await c.answer()
        return

    _, tid = data.split(':', 1)
    telegram_id = int(tid)

    # Get user info
    user = await get_user_by_telegram_id(telegram_id)
    if not user:
        await c.answer("User tidak ditemukan")
        return

    # Show user management options
    text = _get_user_info_text(user)
    kb = all_users_buttons(telegram_id)
    await _safe_edit_or_fallback(c, text, reply_markup=kb)
    await c.answer()


@router.callback_query(lambda c: c.data and (c.data == 'register_list' or c.data.startswith('register_list:')))
async def cb_register_list(c: CallbackQuery):
    """Refresh register list with pagination support."""
    if c.from_user is None:
        await c.answer("Informasi pengguna tidak tersedia")
        return

    # Check if user is admin/owner
    user = await get_user_by_telegram_id(c.from_user.id)
    if not user or not is_allowed_to_create(user):
        await c.answer("Akses ditolak")
        return

    # Parse page number from callback data
    data = c.data or ""
    page = 0  # Default page
    if ':' in data:
        try:
            _, page_str = data.split(':', 1)
            page = int(page_str)
        except (ValueError, IndexError):
            page = 0

    try:
        pending_users = await list_pending_users()

        if not pending_users:
            text = (
                "📋 <b>Daftar Registrasi User</b>\n\n"
                "✅ <b>Tidak ada user yang menunggu persetujuan.</b>\n\n"
                "<i>Semua user sudah diproses.</i>"
            )
            await _safe_edit_or_fallback(c, text, reply_markup=back_to_main_buttons())
            return

        # Pagination settings
        users_per_page = 5
        total_users = len(pending_users)
        total_pages = (total_users + users_per_page - 1) // users_per_page  # Ceiling division

        # Ensure page is within bounds
        if page < 0:
            page = 0
        if page >= total_pages:
            page = total_pages - 1

        # Get users for current page
        start_idx = page * users_per_page
        end_idx = min(start_idx + users_per_page, total_users)
        page_users = pending_users[start_idx:end_idx]

        text = (
            "📋 <b>Daftar Registrasi User</b>\n"
            f"📊 <b>Total menunggu:</b> {total_users}\n"
            f"📄 <b>Halaman:</b> {page + 1}/{total_pages}\n\n"
        )

        keyboard_buttons = []

        for user_data in page_users:
            telegram_id = user_data['telegram_id']
            username = user_data['username'] or '-'
            created_at = user_data.get('created_at', 'Unknown')

            # Format created_at if it's a string
            if isinstance(created_at, str) and 'T' in created_at:
                try:
                    dt = datetime.fromisoformat(created_at.replace('Z', '+00:00'))
                    wib_tz = timezone(timedelta(hours=7))
                    dt_wib = dt.astimezone(wib_tz)
                    formatted_date = dt_wib.strftime("%d/%m/%Y %H:%M")
                except:
                    formatted_date = created_at[:19]  # Fallback to first 19 chars
            else:
                formatted_date = str(created_at)

            text += (
                f"👤 <b>@{username}</b> (ID: <code>{telegram_id}</code>)\n"
                f"📅 Daftar: {formatted_date}\n\n"
            )

            # Add action buttons for this user
            if user.get('role') == 'owner':
                keyboard_buttons.append([
                    InlineKeyboardButton(text=f"✅ Terima @{username}", callback_data=f"accept:{telegram_id}"),
                    InlineKeyboardButton(text=f"❌ Tolak @{username}", callback_data=f"reject:{telegram_id}")
                ])
                keyboard_buttons.append([
                    InlineKeyboardButton(text=f"🚫 Ban @{username}", callback_data=f"ban:{telegram_id}")
                ])
            else:
                # Regular admin buttons
                keyboard_buttons.append([
                    InlineKeyboardButton(text=f"✅ Terima @{username}", callback_data=f"accept:{telegram_id}"),
                    InlineKeyboardButton(text=f"❌ Tolak @{username}", callback_data=f"reject:{telegram_id}")
                ])

        # Add navigation buttons if there are multiple pages
        if total_pages > 1:
            nav_buttons = []

            # Previous page button (disabled on first page)
            if page > 0:
                nav_buttons.append(InlineKeyboardButton(text="◀️ Sebelumnya", callback_data=f"register_list:{page - 1}"))

            # Page indicator
            nav_buttons.append(InlineKeyboardButton(text=f"📄 {page + 1}/{total_pages}", callback_data="noop"))

            # Next page button
            if page < total_pages - 1:
                nav_buttons.append(InlineKeyboardButton(text="▶️ Selanjutnya", callback_data=f"register_list:{page + 1}"))

            keyboard_buttons.append(nav_buttons)

        # Add refresh and back buttons
        keyboard_buttons.append([
            InlineKeyboardButton(text="🔄 Refresh", callback_data="register_list:0"),
            InlineKeyboardButton(text="🏠 Kembali ke Menu", callback_data="back_to_main")
        ])

        kb = InlineKeyboardMarkup(inline_keyboard=keyboard_buttons)
        await _safe_edit_or_fallback(c, text, reply_markup=kb, parse_mode="HTML")

    except Exception as e:
        logger.exception("Failed to refresh register list: %s", e)
        await _safe_edit_or_fallback(c, f"❌ <b>Gagal refresh daftar registrasi:</b> {e}", reply_markup=back_to_main_buttons(), parse_mode="HTML")


@router.callback_query(lambda c: c.data == 'noop')
async def cb_noop(c: CallbackQuery):
    """No operation callback - just answer to remove loading state."""
    await c.answer()


@router.callback_query(lambda c: c.data and (c.data == 'all_users' or c.data.startswith('all_users:')))
async def cb_all_users(c: CallbackQuery):
    """Refresh all users list with pagination support (excludes pending users)."""
    if c.from_user is None:
        await c.answer("Informasi pengguna tidak tersedia")
        return

    # Check if user is admin/owner
    user = await get_user_by_telegram_id(c.from_user.id)
    if not user or not is_allowed_to_create(user):
        await c.answer("Akses ditolak")
        return

    # Parse page number from callback data
    data = c.data or ""
    page = 0  # Default page
    if ':' in data:
        try:
            _, page_str = data.split(':', 1)
            page = int(page_str)
        except (ValueError, IndexError):
            page = 0

    try:
        all_users = await list_all_users()

        # Filter out pending users - only show whitelisted and banned users
        active_users = [u for u in all_users if u['status'] == 'whitelisted']
        banned_users = [u for u in all_users if u['status'] == 'banned']
        filtered_users = active_users + banned_users

        # Calculate statistics
        total_active = len(active_users)
        total_banned = len(banned_users)
        total_users = len(all_users)  # Including pending users

        if not filtered_users:
            text = (
                "👥 <b>Daftar Semua User</b>\n\n"
                f"📊 <b>Total user Aktif:</b> {total_active}\n"
                f"📊 <b>Total User di banned:</b> {total_banned}\n"
                f"📊 <b>Total user:</b> {total_users}\n\n"
                "❌ <b>Tidak ada user aktif atau banned.</b>\n\n"
                "<i>Semua user masih dalam status pending.</i>"
            )
            await _safe_edit_or_fallback(c, text, reply_markup=back_to_main_buttons())
            return

        # Pagination settings
        users_per_page = 5
        total_filtered = len(filtered_users)
        total_pages = (total_filtered + users_per_page - 1) // users_per_page  # Ceiling division
        page = 0  # Start from first page

        # Get users for current page
        start_idx = page * users_per_page
        end_idx = min(start_idx + users_per_page, total_filtered)
        page_users = filtered_users[start_idx:end_idx]

        text = (
            "👥 <b>Daftar Semua User</b>\n"
            f"📊 <b>Total user Aktif:</b> {total_active}\n"
            f"📊 <b>Total User di banned:</b> {total_banned}\n"
            f"📊 <b>Total user:</b> {total_users}\n"
            f"📄 <b>Halaman:</b> {page + 1}/{total_pages}\n\n"
        )

        keyboard_buttons = []

        for user_data in page_users:
            telegram_id = user_data['telegram_id']
            username = user_data['username'] or '-'
            role = user_data.get('role', 'user').capitalize()
            status = user_data['status']

            if status == 'whitelisted':
                text += f"✅ <b>@{username}</b>\n"
                text += f"   ├ Role: {role}\n"
                text += f"   └ ID: <code>{telegram_id}</code>\n\n"
                # Add management buttons for active users
                keyboard_buttons.append([
                    InlineKeyboardButton(text=f"⚙️ Kelola @{username}", callback_data=f"manage_user:{telegram_id}")
                ])
            elif status == 'banned':
                text += f"🚫 <b>@{username}</b>\n"
                text += f"   ├ Role: {role}\n"
                text += f"   └ ID: <code>{telegram_id}</code>\n\n"
                # Add unban button for banned users
                keyboard_buttons.append([
                    InlineKeyboardButton(text=f"✅ Unban @{username}", callback_data=f"unban:{telegram_id}")
                ])

        # Add navigation buttons if there are multiple pages
        if total_pages > 1:
            nav_buttons = []

            # Previous page button (disabled on first page)
            if page > 0:
                nav_buttons.append(InlineKeyboardButton(text="◀️ Sebelumnya", callback_data=f"all_users:{page - 1}"))

            # Page indicator
            nav_buttons.append(InlineKeyboardButton(text=f"📄 {page + 1}/{total_pages}", callback_data="noop"))

            # Next page button
            if page < total_pages - 1:
                nav_buttons.append(InlineKeyboardButton(text="▶️ Selanjutnya", callback_data=f"all_users:{page + 1}"))

            keyboard_buttons.append(nav_buttons)

        # Add refresh and back buttons
        keyboard_buttons.append([
            InlineKeyboardButton(text="🔄 Refresh", callback_data="all_users:0"),
            InlineKeyboardButton(text="🏠 Kembali ke Menu", callback_data="back_to_main")
        ])

        kb = InlineKeyboardMarkup(inline_keyboard=keyboard_buttons)
        await _safe_edit_or_fallback(c, text, reply_markup=kb, parse_mode="HTML")

    except Exception as e:
        logger.exception("Failed to show all users list: %s", e)
        await _safe_edit_or_fallback(c, f"❌ <b>Gagal mengambil daftar user:</b> {e}", reply_markup=back_to_main_buttons(), parse_mode="HTML")


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





@router.callback_query(lambda c: c.data and c.data.startswith('accept:'))
async def cb_accept(c: CallbackQuery):
    data = c.data or ""
    if not data:
        await c.answer()
        return

    _, tid = data.split(':', 1)
    telegram_id = int(tid)
    await update_user_status(telegram_id, 'whitelisted', 'user')

    # Instead of showing a simple message, refresh the register list
    # Create a mock callback with register_list:0 to refresh to first page
    mock_callback = type('MockCallback', (), {
        'data': 'register_list:0',
        'from_user': c.from_user,
        'message': c.message,
        'answer': c.answer
    })()

    await cb_register_list(mock_callback)


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
        # Instead of showing a simple message, refresh the register list
        mock_callback = type('MockCallback', (), {
            'data': 'register_list:0',
            'from_user': c.from_user,
            'message': c.message,
            'answer': c.answer
        })()
        await cb_register_list(mock_callback)
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

    # Instead of showing a simple message, refresh the all users list
    mock_callback = type('MockCallback', (), {
        'data': 'all_users:0',
        'from_user': c.from_user,
        'message': c.message,
        'answer': c.answer
    })()
    await cb_all_users(mock_callback)


@router.callback_query(lambda c: c.data and c.data.startswith('ban:'))
async def cb_ban(c: CallbackQuery):
    data = c.data or ""
    if not data:
        await c.answer()
        return

    _, tid = data.split(':', 1)
    telegram_id = int(tid)
    await ban_toggle_user(telegram_id, True)

    # Instead of showing a simple message, refresh the register list
    mock_callback = type('MockCallback', (), {
        'data': 'register_list:0',
        'from_user': c.from_user,
        'message': c.message,
        'answer': c.answer
    })()
    await cb_register_list(mock_callback)


@router.callback_query(lambda c: c.data and c.data.startswith('unban:'))
async def cb_unban(c: CallbackQuery):
    data = c.data or ""
    if not data:
        await c.answer()
        return

    _, tid = data.split(':', 1)
    telegram_id = int(tid)
    await ban_toggle_user(telegram_id, False)  # False = unban

    # Instead of showing a simple message, refresh the all users list
    mock_callback = type('MockCallback', (), {
        'data': 'all_users:0',
        'from_user': c.from_user,
        'message': c.message,
        'answer': c.answer
    })()
    await cb_all_users(mock_callback)


@router.callback_query(lambda c: c.data and c.data.startswith('manage_user:'))
async def cb_manage_user(c: CallbackQuery):
    data = c.data or ""
    if not data:
        await c.answer()
        return

    _, tid = data.split(':', 1)
    telegram_id = int(tid)

    # Get user info
    user = await get_user_by_telegram_id(telegram_id)
    if not user:
        await c.answer("User tidak ditemukan")
        return

    # Show user management options
    text = _get_user_info_text(user)
    kb = all_users_buttons(telegram_id)
    await _safe_edit_or_fallback(c, text, reply_markup=kb)
    await c.answer()


@router.callback_query(lambda c: c.data and (c.data == 'register_list' or c.data.startswith('register_list:')))
async def cb_register_list(c: CallbackQuery):
    """Refresh register list with pagination support."""
    if c.from_user is None:
        await c.answer("Informasi pengguna tidak tersedia")
        return

    # Check if user is admin/owner
    user = await get_user_by_telegram_id(c.from_user.id)
    if not user or not is_allowed_to_create(user):
        await c.answer("Akses ditolak")
        return

    # Parse page number from callback data
    data = c.data or ""
    page = 0  # Default page
    if ':' in data:
        try:
            _, page_str = data.split(':', 1)
            page = int(page_str)
        except (ValueError, IndexError):
            page = 0

    try:
        pending_users = await list_pending_users()

        if not pending_users:
            text = (
                "📋 <b>Daftar Registrasi User</b>\n\n"
                "✅ <b>Tidak ada user yang menunggu persetujuan.</b>\n\n"
                "<i>Semua user sudah diproses.</i>"
            )
            await _safe_edit_or_fallback(c, text, reply_markup=back_to_main_buttons())
            return

        # Pagination settings
        users_per_page = 5
        total_users = len(pending_users)
        total_pages = (total_users + users_per_page - 1) // users_per_page  # Ceiling division

        # Ensure page is within bounds
        if page < 0:
            page = 0
        if page >= total_pages:
            page = total_pages - 1

        # Get users for current page
        start_idx = page * users_per_page
        end_idx = min(start_idx + users_per_page, total_users)
        page_users = pending_users[start_idx:end_idx]

        text = (
            "📋 <b>Daftar Registrasi User</b>\n"
            f"📊 <b>Total menunggu:</b> {total_users}\n"
            f"📄 <b>Halaman:</b> {page + 1}/{total_pages}\n\n"
        )

        keyboard_buttons = []

        for user_data in page_users:
            telegram_id = user_data['telegram_id']
            username = user_data['username'] or '-'
            created_at = user_data.get('created_at', 'Unknown')

            # Format created_at if it's a string
            if isinstance(created_at, str) and 'T' in created_at:
                try:
                    dt = datetime.fromisoformat(created_at.replace('Z', '+00:00'))
                    wib_tz = timezone(timedelta(hours=7))
                    dt_wib = dt.astimezone(wib_tz)
                    formatted_date = dt_wib.strftime("%d/%m/%Y %H:%M")
                except:
                    formatted_date = created_at[:19]  # Fallback to first 19 chars
            else:
                formatted_date = str(created_at)

            text += (
                f"👤 <b>@{username}</b> (ID: <code>{telegram_id}</code>)\n"
                f"📅 Daftar: {formatted_date}\n\n"
            )

            # Add action buttons for this user
            if user.get('role') == 'owner':
                keyboard_buttons.append([
                    InlineKeyboardButton(text=f"✅ Terima @{username}", callback_data=f"accept:{telegram_id}"),
                    InlineKeyboardButton(text=f"❌ Tolak @{username}", callback_data=f"reject:{telegram_id}")
                ])
                keyboard_buttons.append([
                    InlineKeyboardButton(text=f"🚫 Ban @{username}", callback_data=f"ban:{telegram_id}")
                ])
            else:
                # Regular admin buttons
                keyboard_buttons.append([
                    InlineKeyboardButton(text=f"✅ Terima @{username}", callback_data=f"accept:{telegram_id}"),
                    InlineKeyboardButton(text=f"❌ Tolak @{username}", callback_data=f"reject:{telegram_id}")
                ])

        # Add navigation buttons if there are multiple pages
        if total_pages > 1:
            nav_buttons = []

            # Previous page button (disabled on first page)
            if page > 0:
                nav_buttons.append(InlineKeyboardButton(text="◀️ Sebelumnya", callback_data=f"register_list:{page - 1}"))

            # Page indicator
            nav_buttons.append(InlineKeyboardButton(text=f"📄 {page + 1}/{total_pages}", callback_data="noop"))

            # Next page button
            if page < total_pages - 1:
                nav_buttons.append(InlineKeyboardButton(text="▶️ Selanjutnya", callback_data=f"register_list:{page + 1}"))

            keyboard_buttons.append(nav_buttons)

        # Add refresh and back buttons
        keyboard_buttons.append([
            InlineKeyboardButton(text="🔄 Refresh", callback_data="register_list:0"),
            InlineKeyboardButton(text="🏠 Kembali ke Menu", callback_data="back_to_main")
        ])

        kb = InlineKeyboardMarkup(inline_keyboard=keyboard_buttons)
        await _safe_edit_or_fallback(c, text, reply_markup=kb, parse_mode="HTML")

    except Exception as e:
        logger.exception("Failed to refresh register list: %s", e)
        await _safe_edit_or_fallback(c, f"❌ <b>Gagal refresh daftar registrasi:</b> {e}", reply_markup=back_to_main_buttons(), parse_mode="HTML")


@router.callback_query(lambda c: c.data == 'noop')
async def cb_noop(c: CallbackQuery):
    """No operation callback - just answer to remove loading state."""
    await c.answer()


@router.callback_query(lambda c: c.data and (c.data == 'all_users' or c.data.startswith('all_users:')))
async def cb_all_users(c: CallbackQuery):
    """Refresh all users list with pagination support (excludes pending users)."""
    if c.from_user is None:
        await c.answer("Informasi pengguna tidak tersedia")
        return

    # Check if user is admin/owner
    user = await get_user_by_telegram_id(c.from_user.id)
    if not user or not is_allowed_to_create(user):
        await c.answer("Akses ditolak")
        return

    # Parse page number from callback data
    data = c.data or ""
    page = 0  # Default page
    if ':' in data:
        try:
            _, page_str = data.split(':', 1)
            page = int(page_str)
        except (ValueError, IndexError):
            page = 0

    try:
        all_users = await list_all_users()

        # Filter out pending users - only show whitelisted and banned users
        active_users = [u for u in all_users if u['status'] == 'whitelisted']
        banned_users = [u for u in all_users if u['status'] == 'banned']
        filtered_users = active_users + banned_users

        # Calculate statistics
        total_active = len(active_users)
        total_banned = len(banned_users)
        total_users = len(all_users)  # Including pending users

        if not filtered_users:
            text = (
                "👥 <b>Daftar Semua User</b>\n\n"
                f"📊 <b>Total user Aktif:</b> {total_active}\n"
                f"📊 <b>Total User di banned:</b> {total_banned}\n"
                f"📊 <b>Total user:</b> {total_users}\n\n"
                "❌ <b>Tidak ada user aktif atau banned.</b>\n\n"
                "<i>Semua user masih dalam status pending.</i>"
            )
            await _safe_edit_or_fallback(c, text, reply_markup=back_to_main_buttons())
            return

        # Pagination settings
        users_per_page = 5
        total_filtered = len(filtered_users)
        total_pages = (total_filtered + users_per_page - 1) // users_per_page  # Ceiling division
        page = 0  # Start from first page

        # Get users for current page
        start_idx = page * users_per_page
        end_idx = min(start_idx + users_per_page, total_filtered)
        page_users = filtered_users[start_idx:end_idx]

        text = (
            "👥 <b>Daftar Semua User</b>\n"
            f"📊 <b>Total user Aktif:</b> {total_active}\n"
            f"📊 <b>Total User di banned:</b> {total_banned}\n"
            f"📊 <b>Total user:</b> {total_users}\n"
            f"📄 <b>Halaman:</b> {page + 1}/{total_pages}\n\n"
        )

        keyboard_buttons = []

        for user_data in page_users:
            telegram_id = user_data['telegram_id']
            username = user_data['username'] or '-'
            role = user_data.get('role', 'user').capitalize()
            status = user_data['status']

            if status == 'whitelisted':
                text += f"✅ <b>@{username}</b>\n"
                text += f"   ├ Role: {role}\n"
                text += f"   └ ID: <code>{telegram_id}</code>\n\n"
                # Add management buttons for active users
                keyboard_buttons.append([
                    InlineKeyboardButton(text=f"⚙️ Kelola @{username}", callback_data=f"manage_user:{telegram_id}")
                ])
            elif status == 'banned':
                text += f"🚫 <b>@{username}</b>\n"
                text += f"   ├ Role: {role}\n"
                text += f"   └ ID: <code>{telegram_id}</code>\n\n"
                # Add unban button for banned users
                keyboard_buttons.append([
                    InlineKeyboardButton(text=f"✅ Unban @{username}", callback_data=f"unban:{telegram_id}")
                ])

        # Add navigation buttons if there are multiple pages
        if total_pages > 1:
            nav_buttons = []

            # Previous page button (disabled on first page)
            if page > 0:
                nav_buttons.append(InlineKeyboardButton(text="◀️ Sebelumnya", callback_data=f"all_users:{page - 1}"))

            # Page indicator
            nav_buttons.append(InlineKeyboardButton(text=f"📄 {page + 1}/{total_pages}", callback_data="noop"))

            # Next page button
            if page < total_pages - 1:
                nav_buttons.append(InlineKeyboardButton(text="▶️ Selanjutnya", callback_data=f"all_users:{page + 1}"))

            keyboard_buttons.append(nav_buttons)

        # Add refresh and back buttons
        keyboard_buttons.append([
            InlineKeyboardButton(text="🔄 Refresh", callback_data="all_users:0"),
            InlineKeyboardButton(text="🏠 Kembali ke Menu", callback_data="back_to_main")
        ])

        kb = InlineKeyboardMarkup(inline_keyboard=keyboard_buttons)
        await _safe_edit_or_fallback(c, text, reply_markup=kb, parse_mode="HTML")

    except Exception as e:
        logger.exception("Failed to show all users list: %s", e)
        await _safe_edit_or_fallback(c, f"❌ <b>Gagal mengambil daftar user:</b> {e}", reply_markup=back_to_main_buttons(), parse_mode="HTML")


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





@router.callback_query(lambda c: c.data and c.data.startswith('accept:'))
async def cb_accept(c: CallbackQuery):
    data = c.data or ""
    if not data:
        await c.answer()
        return

    _, tid = data.split(':', 1)
    telegram_id = int(tid)
    await update_user_status(telegram_id, 'whitelisted', 'user')

    # Instead of showing a simple message, refresh the register list
    # Create a mock callback with register_list:0 to refresh to first page
    mock_callback = type('MockCallback', (), {
        'data': 'register_list:0',
        'from_user': c.from_user,
        'message': c.message,
        'answer': c.answer
    })()

    await cb_register_list(mock_callback)


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
        # Instead of showing a simple message, refresh the register list
        mock_callback = type('MockCallback', (), {
            'data': 'register_list:0',
            'from_user': c.from_user,
            'message': c.message,
            'answer': c.answer
        })()
        await cb_register_list(mock_callback)
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

    # Instead of showing a simple message, refresh the all users list
    mock_callback = type('MockCallback', (), {
        'data': 'all_users:0',
        'from_user': c.from_user,
        'message': c.message,
        'answer': c.answer
    })()
    await cb_all_users(mock_callback)


@router.callback_query(lambda c: c.data and c.data.startswith('ban:'))
async def cb_ban(c: CallbackQuery):
    data = c.data or ""
    if not data:
        await c.answer()
        return

    _, tid = data.split(':', 1)
    telegram_id = int(tid)
    await ban_toggle_user(telegram_id, True)

    # Instead of showing a simple message, refresh the register list
    mock_callback = type('MockCallback', (), {
        'data': 'register_list:0',
        'from_user': c.from_user,
        'message': c.message,
        'answer': c.answer
    })()
    await cb_register_list(mock_callback)


@router.callback_query(lambda c: c.data and c.data.startswith('unban:'))
async def cb_unban(c: CallbackQuery):
    data = c.data or ""
    if not data:
        await c.answer()
        return

    _, tid = data.split(':', 1)
    telegram_id = int(tid)
    await ban_toggle_user(telegram_id, False)  # False = unban

    # Instead of showing a simple message, refresh the all users list
    mock_callback = type('MockCallback', (), {
        'data': 'all_users:0',
        'from_user': c.from_user,
        'message': c.message,
        'answer': c.answer
    })()
    await cb_all_users(mock_callback)


@router.callback_query(lambda c: c.data and c.data.startswith('manage_user:'))
async def cb_manage_user(c: CallbackQuery):
    data = c.data or ""
    if not data:
        await c.answer()
        return

    _, tid = data.split(':', 1)
    telegram_id = int(tid)

    # Get user info
    user = await get_user_by_telegram_id(telegram_id)
    if not user:
        await c.answer("User tidak ditemukan")
        return

    # Show user management options
    text = _get_user_info_text(user)
    kb = all_users_buttons(telegram_id)
    await _safe_edit_or_fallback(c, text, reply_markup=kb)
    await c.answer()


@router.callback_query(lambda c: c.data and (c.data == 'register_list' or c.data.startswith('register_list:')))
async def cb_register_list(c: CallbackQuery):
    """Refresh register list with pagination support."""
    if c.from_user is None:
        await c.answer("Informasi pengguna tidak tersedia")
        return

    # Check if user is admin/owner
    user = await get_user_by_telegram_id(c.from_user.id)
    if not user or not is_allowed_to_create(user):
        await c.answer("Akses ditolak")
        return

    # Parse page number from callback data
    data = c.data or ""
    page = 0  # Default page
    if ':' in data:
        try:
            _, page_str = data.split(':', 1)
            page = int(page_str)
        except (ValueError, IndexError):
            page = 0

    try:
        pending_users = await list_pending_users()

        if not pending_users:
            text = (
                "📋 <b>Daftar Registrasi User</b>\n\n"
                "✅ <b>Tidak ada user yang menunggu persetujuan.</b>\n\n"
                "<i>Semua user sudah diproses.</i>"
            )
            await _safe_edit_or_fallback(c, text, reply_markup=back_to_main_buttons())
            return

        # Pagination settings
        users_per_page = 5
        total_users = len(pending_users)
        total_pages = (total_users + users_per_page - 1) // users_per_page  # Ceiling division

        # Ensure page is within bounds
        if page < 0:
            page = 0
        if page >= total_pages:
            page = total_pages - 1

        # Get users for current page
        start_idx = page * users_per_page
        end_idx = min(start_idx + users_per_page, total_users)
        page_users = pending_users[start_idx:end_idx]

        text = (
            "📋 <b>Daftar Registrasi User</b>\n"
            f"📊 <b>Total menunggu:</b> {total_users}\n"
            f"📄 <b>Halaman:</b> {page + 1}/{total_pages}\n\n"
        )

        keyboard_buttons = []

        for user_data in page_users:
            telegram_id = user_data['telegram_id']
            username = user_data['username'] or '-'
            created_at = user_data.get('created_at', 'Unknown')

            # Format created_at if it's a string
            if isinstance(created_at, str) and 'T' in created_at:
                try:
                    dt = datetime.fromisoformat(created_at.replace('Z', '+00:00'))
                    wib_tz = timezone(timedelta(hours=7))
                    dt_wib = dt.astimezone(wib_tz)
                    formatted_date = dt_wib.strftime("%d/%m/%Y %H:%M")
                except:
                    formatted_date = created_at[:19]  # Fallback to first 19 chars
            else:
                formatted_date = str(created_at)

            text += (
                f"👤 <b>@{username}</b> (ID: <code>{telegram_id}</code>)\n"
                f"📅 Daftar: {formatted_date}\n\n"
            )

            # Add action buttons for this user
            if user.get('role') == 'owner':
                keyboard_buttons.append([
                    InlineKeyboardButton(text=f"✅ Terima @{username}", callback_data=f"accept:{telegram_id}"),
                    InlineKeyboardButton(text=f"❌ Tolak @{username}", callback_data=f"reject:{telegram_id}")
                ])
                keyboard_buttons.append([
                    InlineKeyboardButton(text=f"🚫 Ban @{username}", callback_data=f"ban:{telegram_id}")
                ])
            else:
                # Regular admin buttons
                keyboard_buttons.append([
                    InlineKeyboardButton(text=f"✅ Terima @{username}", callback_data=f"accept:{telegram_id}"),
                    InlineKeyboardButton(text=f"❌ Tolak @{username}", callback_data=f"reject:{telegram_id}")
                ])

        # Add navigation buttons if there are multiple pages
        if total_pages > 1:
            nav_buttons = []

            # Previous page button (disabled on first page)
            if page > 0:
                nav_buttons.append(InlineKeyboardButton(text="◀️ Sebelumnya", callback_data=f"register_list:{page - 1}"))

            # Page indicator
            nav_buttons.append(InlineKeyboardButton(text=f"📄 {page + 1}/{total_pages}", callback_data="noop"))

            # Next page button
            if page < total_pages - 1:
                nav_buttons.append(InlineKeyboardButton(text="▶️ Selanjutnya", callback_data=f"register_list:{page + 1}"))

            keyboard_buttons.append(nav_buttons)

        # Add refresh and back buttons
        keyboard_buttons.append([
            InlineKeyboardButton(text="🔄 Refresh", callback_data="register_list:0"),
            InlineKeyboardButton(text="🏠 Kembali ke Menu", callback_data="back_to_main")
        ])

        kb = InlineKeyboardMarkup(inline_keyboard=keyboard_buttons)
        await _safe_edit_or_fallback(c, text, reply_markup=kb, parse_mode="HTML")

    except Exception as e:
        logger.exception("Failed to refresh register list: %s", e)
        await _safe_edit_or_fallback(c, f"❌ <b>Gagal refresh daftar registrasi:</b> {e}", reply_markup=back_to_main_buttons(), parse_mode="HTML")


@router.callback_query(lambda c: c.data == 'noop')
async def cb_noop(c: CallbackQuery):
    """No operation callback - just answer to remove loading state."""
    await c.answer()


@router.callback_query(lambda c: c.data and (c.data == 'all_users' or c.data.startswith('all_users:')))
async def cb_all_users(c: CallbackQuery):
    """Refresh all users list with pagination support (excludes pending users)."""
    if c.from_user is None:
        await c.answer("Informasi pengguna tidak tersedia")
        return

    # Check if user is admin/owner
    user = await get_user_by_telegram_id(c.from_user.id)
    if not user or not is_allowed_to_create(user):
        await c.answer("Akses ditolak")
        return

    # Parse page number from callback data
    data = c.data or ""
    page = 0  # Default page
    if ':' in data:
        try:
            _, page_str = data.split(':', 1)
            page = int(page_str)
        except (ValueError, IndexError):
            page = 0

    try:
        all_users = await list_all_users()

        # Filter out pending users - only show whitelisted and banned users
        active_users = [u for u in all_users if u['status'] == 'whitelisted']
        banned_users = [u for u in all_users if u['status'] == 'banned']
        filtered_users = active_users + banned_users

        # Calculate statistics
        total_active = len(active_users)
        total_banned = len(banned_users)
        total_users = len(all_users)  # Including pending users

        if not filtered_users:
            text = (
                "👥 <b>Daftar Semua User</b>\n\n"
                f"📊 <b>Total user Aktif:</b> {total_active}\n"
                f"📊 <b>Total User di banned:</b> {total_banned}\n"
                f"📊 <b>Total user:</b> {total_users}\n\n"
                "❌ <b>Tidak ada user aktif atau banned.</b>\n\n"
                "<i>Semua user masih dalam status pending.</i>"
            )
            await _safe_edit_or_fallback(c, text, reply_markup=back_to_main_buttons())
            return

        # Pagination settings
        users_per_page = 5
        total_filtered = len(filtered_users)
        total_pages = (total_filtered + users_per_page - 1) // users_per_page  # Ceiling division
        page = 0  # Start from first page

        # Get users for current page
        start_idx = page * users_per_page
        end_idx = min(start_idx + users_per_page, total_filtered)
        page_users = filtered_users[start_idx:end_idx]

        text = (
            "👥 <b>Daftar Semua User</b>\n"
            f"📊 <b>Total user Aktif:</b> {total_active}\n"
            f"📊 <b>Total User di banned:</b> {total_banned}\n"
            f"📊 <b>Total user:</b> {total_users}\n"
            f"📄 <b>Halaman:</b> {page + 1}/{total_pages}\n\n"
        )

        keyboard_buttons = []

        for user_data in page_users:
            telegram_id = user_data['telegram_id']
            username = user_data['username'] or '-'
            role = user_data.get('role', 'user').capitalize()
            status = user_data['status']

            if status == 'whitelisted':
                text += f"✅ <b>@{username}</b>\n"
                text += f"   ├ Role: {role}\n"
                text += f"   └ ID: <code>{telegram_id}</code>\n\n"
                # Add management buttons for active users
                keyboard_buttons.append([
                    InlineKeyboardButton(text=f"⚙️ Kelola @{username}", callback_data=f"manage_user:{telegram_id}")
                ])
            elif status == 'banned':
                text += f"🚫 <b>@{username}</b>\n"
                text += f"   ├ Role: {role}\n"
                text += f"   └ ID: <code>{telegram_id}</code>\n\n"
                # Add unban button for banned users
                keyboard_buttons.append([
                    InlineKeyboardButton(text=f"✅ Unban @{username}", callback_data=f"unban:{telegram_id}")
                ])

        # Add navigation buttons if there are multiple pages
        if total_pages > 1:
            nav_buttons = []

            # Previous page button (disabled on first page)
            if page > 0:
                nav_buttons.append(InlineKeyboardButton(text="◀️ Sebelumnya", callback_data=f"all_users:{page - 1}"))

            # Page indicator
            nav_buttons.append(InlineKeyboardButton(text=f"📄 {page + 1}/{total_pages}", callback_data="noop"))

            # Next page button
            if page < total_pages - 1:
                nav_buttons.append(InlineKeyboardButton(text="▶️ Selanjutnya", callback_data=f"all_users:{page + 1}"))

            keyboard_buttons.append(nav_buttons)

        # Add refresh and back buttons
        keyboard_buttons.append([
            InlineKeyboardButton(text="🔄 Refresh", callback_data="all_users:0"),
            InlineKeyboardButton(text="🏠 Kembali ke Menu", callback_data="back_to_main")
        ])

        kb = InlineKeyboardMarkup(inline_keyboard=keyboard_buttons)
        await _safe_edit_or_fallback(c, text, reply_markup=kb, parse_mode="HTML")

    except Exception as e:
        logger.exception("Failed to show all users list: %s", e)
        await _safe_edit_or_fallback(c, f"❌ <b>Gagal mengambil daftar user:</b> {e}", reply_markup=back_to_main_buttons(), parse_mode="HTML")


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





@router.callback_query(lambda c: c.data and c.data.startswith('accept:'))
async def cb_accept(c: CallbackQuery):
    data = c.data or ""
    if not data:
        await c.answer()
        return

    _, tid = data.split(':', 1)
    telegram_id = int(tid)
    await update_user_status(telegram_id, 'whitelisted', 'user')

    # Instead of showing a simple message, refresh the register list
    # Create a mock callback with register_list:0 to refresh to first page
    mock_callback = type('MockCallback', (), {
        'data': 'register_list:0',
        'from_user': c.from_user,
        'message': c.message,
        'answer': c.answer
    })()

    await cb_register_list(mock_callback)


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
        # Instead of showing a simple message, refresh the register list
        mock_callback = type('MockCallback', (), {
            'data': 'register_list:0',
            'from_user': c.from_user,
            'message': c.message,
            'answer': c.answer
        })()
        await cb_register_list(mock_callback)
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

    # Instead of showing a simple message, refresh the all users list
    mock_callback = type('MockCallback', (), {
        'data': 'all_users:0',
        'from_user': c.from_user,
        'message': c.message,
        'answer': c.answer
    })()
    await cb_all_users(mock_callback)


@router.callback_query(lambda c: c.data and c.data.startswith('ban:'))
async def cb_ban(c: CallbackQuery):
    data = c.data or ""
    if not data:
        await c.answer()
        return

    _, tid = data.split(':', 1)
    telegram_id = int(tid)
    await ban_toggle_user(telegram_id, True)

    # Instead of showing a simple message, refresh the register list
    mock_callback = type('MockCallback', (), {
        'data': 'register_list:0',
        'from_user': c.from_user,
        'message': c.message,
        'answer': c.answer
    })()
    await cb_register_list(mock_callback)


@router.callback_query(lambda c: c.data and c.data.startswith('unban:'))
async def cb_unban(c: CallbackQuery):
    data = c.data or ""
    if not data:
        await c.answer()
        return

    _, tid = data.split(':', 1)
    telegram_id = int(tid)
    await ban_toggle_user(telegram_id, False)  # False = unban

    # Instead of showing a simple message, refresh the all users list
    mock_callback = type('MockCallback', (), {
        'data': 'all_users:0',
        'from_user': c.from_user,
        'message': c.message,
        'answer': c.answer
    })()
    await cb_all_users(mock_callback)


@router.callback_query(lambda c: c.data and c.data.startswith('manage_user:'))
async def cb_manage_user(c: CallbackQuery):
    data = c.data or ""
    if not data:
        await c.answer()
        return

    _, tid = data.split(':', 1)
    telegram_id = int(tid)

    # Get user info
    user = await get_user_by_telegram_id(telegram_id)
    if not user:
        await c.answer("User tidak ditemukan")
        return

    # Show user management options
    text = _get_user_info_text(user)
    kb = all_users_buttons(telegram_id)
    await _safe_edit_or_fallback(c, text, reply_markup=kb)
    await c.answer()


@router.callback_query(lambda c: c.data and (c.data == 'register_list' or c.data.startswith('register_list:')))
async def cb_register_list(c: CallbackQuery):
    """Refresh register list with pagination support."""
    if c.from_user is None:
        await c.answer("Informasi pengguna tidak tersedia")
        return

    # Check if user is admin/owner
    user = await get_user_by_telegram_id(c.from_user.id)
    if not user or not is_allowed_to_create(user):
        await c.answer("Akses ditolak")
        return

    # Parse page number from callback data
    data = c.data or ""
    page = 0  # Default page
    if ':' in data:
        try:
            _, page_str = data.split(':', 1)
            page = int(page_str)
        except (ValueError, IndexError):
            page = 0

    try:
        pending_users = await list_pending_users()

        if not pending_users:
            text = (
                "📋 <b>Daftar Registrasi User</b>\n\n"
                "✅ <b>Tidak ada user yang menunggu persetujuan.</b>\n\n"
                "<i>Semua user sudah diproses.</i>"
            )
            await _safe_edit_or_fallback(c, text, reply_markup=back_to_main_buttons())
            return

        # Pagination settings
        users_per_page = 5
        total_users = len(pending_users)
        total_pages = (total_users + users_per_page - 1) // users_per_page  # Ceiling division

        # Ensure page is within bounds
        if page < 0:
            page = 0
        if page >= total_pages:
            page = total_pages - 1

        # Get users for current page
        start_idx = page * users_per_page
        end_idx = min(start_idx + users_per_page, total_users)
        page_users = pending_users[start_idx:end_idx]

        text = (
            "📋 <b>Daftar Registrasi User</b>\n"
            f"📊 <b>Total menunggu:</b> {total_users}\n"
            f"📄 <b>Halaman:</b> {page + 1}/{total_pages}\n\n"
        )

        keyboard_buttons = []

        for user_data in page_users:
            telegram_id = user_data['telegram_id']
            username = user_data['username'] or '-'
            created_at = user_data.get('created_at', 'Unknown')

            # Format created_at if it's a string
            if isinstance(created_at, str) and 'T' in created_at:
                try:
                    dt = datetime.fromisoformat(created_at.replace('Z', '+00:00'))
                    wib_tz = timezone(timedelta(hours=7))
                    dt_wib = dt.astimezone(wib_tz)
                    formatted_date = dt_wib.strftime("%d/%m/%Y %H:%M")
                except:
                    formatted_date = created_at[:19]  # Fallback to first 19 chars
            else:
                formatted_date = str(created_at)

            text += (
                f"👤 <b>@{username}</b> (ID: <code>{telegram_id}</code>)\n"
                f"📅 Daftar: {formatted_date}\n\n"
            )

            # Add action buttons for this user
            if user.get('role') == 'owner':
                keyboard_buttons.append([
                    InlineKeyboardButton(text=f"✅ Terima @{username}", callback_data=f"accept:{telegram_id}"),
                    InlineKeyboardButton(text=f"❌ Tolak @{username}", callback_data=f"reject:{telegram_id}")
                ])
                keyboard_buttons.append([
                    InlineKeyboardButton(text=f"🚫 Ban @{username}", callback_data=f"ban:{telegram_id}")
                ])
            else:
                # Regular admin buttons
                keyboard_buttons.append([
                    InlineKeyboardButton(text=f"✅ Terima @{username}", callback_data=f"accept:{telegram_id}"),
                    InlineKeyboardButton(text=f"❌ Tolak @{username}", callback_data=f"reject:{telegram_id}")
                ])

        # Add navigation buttons if there are multiple pages
        if total_pages > 1:
            nav_buttons = []

            # Previous page button (disabled on first page)
            if page > 0:
                nav_buttons.append(InlineKeyboardButton(text="◀️ Sebelumnya", callback_data=f"register_list:{page - 1}"))

            # Page indicator
            nav_buttons.append(InlineKeyboardButton(text=f"📄 {page + 1}/{total_pages}", callback_data="noop"))

            # Next page button
            if page < total_pages - 1:
                nav_buttons.append(InlineKeyboardButton(text="▶️ Selanjutnya", callback_data=f"register_list:{page + 1}"))

            keyboard_buttons.append(nav_buttons)

        # Add refresh and back buttons
        keyboard_buttons.append([
            InlineKeyboardButton(text="🔄 Refresh", callback_data="register_list:0"),
            InlineKeyboardButton(text="🏠 Kembali ke Menu", callback_data="back_to_main")
        ])

        kb = InlineKeyboardMarkup(inline_keyboard=keyboard_buttons)
        await _safe_edit_or_fallback(c, text, reply_markup=kb, parse_mode="HTML")

    except Exception as e:
        logger.exception("Failed to refresh register list: %s", e)
        await _safe_edit_or_fallback(c, f"❌ <b>Gagal refresh daftar registrasi:</b> {e}", reply_markup=back_to_main_buttons(), parse_mode="HTML")


@router.callback_query(lambda c: c.data == 'noop')
async def cb_noop(c: CallbackQuery):
    """No operation callback - just answer to remove loading state."""
    await c.answer()


@router.callback_query(lambda c: c.data and (c.data == 'all_users' or c.data.startswith('all_users:')))
async def cb_all_users(c: CallbackQuery):
    """Refresh all users list with pagination support (excludes pending users)."""
    if c.from_user is None:
        await c.answer("Informasi pengguna tidak tersedia")
        return

    # Check if user is admin/owner
    user = await get_user_by_telegram_id(c.from_user.id)
    if not user or not is_allowed_to_create(user):
        await c.answer("Akses ditolak")
        return

    # Parse page number from callback data
    data = c.data or ""
    page = 0  # Default page
    if ':' in data:
        try:
            _, page_str = data.split(':', 1)
            page = int(page_str)
        except (ValueError, IndexError):
            page = 0

    try:
        all_users = await list_all_users()

        # Filter out pending users - only show whitelisted and banned users
        active_users = [u for u in all_users if u['status'] == 'whitelisted']
        banned_users = [u for u in all_users if u['status'] == 'banned']
        filtered_users = active_users + banned_users

        # Calculate statistics
        total_active = len(active_users)
        total_banned = len(banned_users)
        total_users = len(all_users)  # Including pending users

        if not filtered_users:
            text = (
                "👥 <b>Daftar Semua User</b>\n\n"
                f"📊 <b>Total user Aktif:</b> {total_active}\n"
                f"📊 <b>Total User di banned:</b> {total_banned}\n"
                f"📊 <b>Total user:</b> {total_users}\n\n"
                "❌ <b>Tidak ada user aktif atau banned.</b>\n\n"
                "<i>Semua user masih dalam status pending.</i>"
            )
            await _safe_edit_or_fallback(c, text, reply_markup=back_to_main_buttons())
            return

        # Pagination settings
        users_per_page = 5
        total_filtered = len(filtered_users)
        total_pages = (total_filtered + users_per_page - 1) // users_per_page  # Ceiling division
        page = 0  # Start from first page

        # Get users for current page
        start_idx = page * users_per_page
        end_idx = min(start_idx + users_per_page, total_filtered)
        page_users = filtered_users[start_idx:end_idx]

        text = (
            "👥 <b>Daftar Semua User</b>\n"
            f"📊 <b>Total user Aktif:</b> {total_active}\n"
            f"📊 <b>Total User di banned:</b> {total_banned}\n"
            f"📊 <b>Total user:</b> {total_users}\n"
            f"📄 <b>Halaman:</b> {page + 1}/{total_pages}\n\n"
        )

        keyboard_buttons = []

        for user_data in page_users:
            telegram_id = user_data['telegram_id']
            username = user_data['username'] or '-'
            role = user_data.get('role', 'user').capitalize()
            status = user_data['status']

            if status == 'whitelisted':
                text += f"✅ <b>@{username}</b>\n"
                text += f"   ├ Role: {role}\n"
                text += f"   └ ID: <code>{telegram_id}</code>\n\n"
                # Add management buttons for active users
                keyboard_buttons.append([
                    InlineKeyboardButton(text=f"⚙️ Kelola @{username}", callback_data=f"manage_user:{telegram_id}")
                ])
            elif status == 'banned':
                text += f"🚫 <b>@{username}</b>\n"
                text += f"   ├ Role: {role}\n"
                text += f"   └ ID: <code>{telegram_id}</code>\n\n"
                # Add unban button for banned users
                keyboard_buttons.append([
                    InlineKeyboardButton(text=f"✅ Unban @{username}", callback_data=f"unban:{telegram_id}")
                ])

        # Add navigation buttons if there are multiple pages
        if total_pages > 1:
            nav_buttons = []

            # Previous page button (disabled on first page)
            if page > 0:
                nav_buttons.append(InlineKeyboardButton(text="◀️ Sebelumnya", callback_data=f"all_users:{page - 1}"))

            # Page indicator
            nav_buttons.append(InlineKeyboardButton(text=f"📄 {page + 1}/{total_pages}", callback_data="noop"))

            # Next page button
            if page < total_pages - 1:
                nav_buttons.append(InlineKeyboardButton(text="▶️ Selanjutnya", callback_data=f"all_users:{page + 1}"))

            keyboard_buttons.append(nav_buttons)

        # Add refresh and back buttons
        keyboard_buttons.append([
            InlineKeyboardButton(text="🔄 Refresh", callback_data="all_users:0"),
            InlineKeyboardButton(text="🏠 Kembali ke Menu", callback_data="back_to_main")
        ])

        kb = InlineKeyboardMarkup(inline_keyboard=keyboard_buttons)
        await _safe_edit_or_fallback(c, text, reply_markup=kb, parse_mode="HTML")

    except Exception as e:
        logger.exception("Failed to show all users list: %s", e)
        await _safe_edit_or_fallback(c, f"❌ <b>Gagal mengambil daftar user:</b> {e}", reply_markup=back_to_main_buttons(), parse_mode="HTML")


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





@router.callback_query(lambda c: c.data and c.data.startswith('accept:'))
async def cb_accept(c: CallbackQuery):
    data = c.data or ""
    if not data:
        await c.answer()
        return

    _, tid = data.split(':', 1)
    telegram_id = int(tid)
    await update_user_status(telegram_id, 'whitelisted', 'user')

    # Instead of showing a simple message, refresh the register list
    # Create a mock callback with register_list:0 to refresh to first page
    mock_callback = type('MockCallback', (), {
        'data': 'register_list:0',
        'from_user': c.from_user,
        'message': c.message,
        'answer': c.answer
    })()

    await cb_register_list(mock_callback)


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
        # Instead of showing a simple message, refresh the register list
        mock_callback = type('MockCallback', (), {
            'data': 'register_list:0',
            'from_user': c.from_user,
            'message': c.message,
            'answer': c.answer
        })()
        await cb_register_list(mock_callback)
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

    # Instead of showing a simple message, refresh the all users list
    mock_callback = type('MockCallback', (), {
        'data': 'all_users:0',
        'from_user': c.from_user,
        'message': c.message,
        'answer': c.answer
    })()
    await cb_all_users(mock_callback)


@router.callback_query(lambda c: c.data and c.data.startswith('ban:'))
async def cb_ban(c: CallbackQuery):
    data = c.data or ""
    if not data:
        await c.answer()
        return

    _, tid = data.split(':', 1)
    telegram_id = int(tid)
    await ban_toggle_user(telegram_id, True)

    # Instead of showing a simple message, refresh the register list
    mock_callback = type('MockCallback', (), {
        'data': 'register_list:0',
        'from_user': c.from_user,
        'message': c.message,
        'answer': c.answer
    })()
    await cb_register_list(mock_callback)


@router.callback_query(lambda c: c.data and c.data.startswith('unban:'))
async def cb_unban(c: CallbackQuery):
    data = c.data or ""
    if not data:
        await c.answer()
        return

    _, tid = data.split(':', 1)
    telegram_id = int(tid)
    await ban_toggle_user(telegram_id, False)  # False = unban

    # Instead of showing a simple message, refresh the all users list
    mock_callback = type('MockCallback', (), {
        'data': 'all_users:0',
        'from_user': c.from_user,
        'message': c.message,
        'answer': c.answer
    })()
    await cb_all_users(mock_callback)


@router.callback_query(lambda c: c.data and c.data.startswith('manage_user:'))
async def cb_manage_user(c: CallbackQuery):
    data = c.data or ""
    if not data:
        await c.answer()
        return

    _, tid = data.split(':', 1)
    telegram_id = int(tid)

    # Get user info
    user = await get_user_by_telegram_id(telegram_id)
    if not user:
        await c.answer("User tidak ditemukan")
        return

    # Show user management options
    text = _get_user_info_text(user)
    kb = all_users_buttons(telegram_id)
    await _safe_edit_or_fallback(c, text, reply_markup=kb)
    await c.answer()


@router.callback_query(lambda c: c.data and (c.data == 'register_list' or c.data.startswith('register_list:')))
async def cb_register_list(c: CallbackQuery):
    """Refresh register list with pagination support."""
    if c.from_user is None:
        await c.answer("Informasi pengguna tidak tersedia")
        return

    # Check if user is admin/owner
    user = await get_user_by_telegram_id(c.from_user.id)
    if not user or not is_allowed_to_create(user):
        await c.answer("Akses ditolak")
        return

    # Parse page number from callback data
    data = c.data or ""
    page = 0  # Default page
    if ':' in data:
        try:
            _, page_str = data.split(':', 1)
            page = int(page_str)
        except (ValueError, IndexError):
            page = 0

    try:
        pending_users = await list_pending_users()

        if not pending_users:
            text = (
                "📋 <b>Daftar Registrasi User</b>\n\n"
                "✅ <b>Tidak ada user yang menunggu persetujuan.</b>\n\n"
                "<i>Semua user sudah diproses.</i>"
            )
            await _safe_edit_or_fallback(c, text, reply_markup=back_to_main_buttons())
            return

        # Pagination settings
        users_per_page = 5
        total_users = len(pending_users)
        total_pages = (total_users + users_per_page - 1) // users_per_page  # Ceiling division

        # Ensure page is within bounds
        if page < 0:
            page = 0
        if page >= total_pages:
            page = total_pages - 1

        # Get users for current page
        start_idx = page * users_per_page
        end_idx = min(start_idx + users_per_page, total_users)
        page_users = pending_users[start_idx:end_idx]

        text = (
            "📋 <b>Daftar Registrasi User</b>\n"
            f"📊 <b>Total menunggu:</b> {total_users}\n"
            f"📄 <b>Halaman:</b> {page + 1}/{total_pages}\n\n"
        )

        keyboard_buttons = []

        for user_data in page_users:
            telegram_id = user_data['telegram_id']
            username = user_data['username'] or '-'
            created_at = user_data.get('created_at', 'Unknown')

            # Format created_at if it's a string
            if isinstance(created_at, str) and 'T' in created_at:
                try:
                    dt = datetime.fromisoformat(created_at.replace('Z', '+00:00'))
                    wib_tz = timezone(timedelta(hours=7))
                    dt_wib = dt.astimezone(wib_tz)
                    formatted_date = dt_wib.strftime("%d/%m/%Y %H:%M")
                except:
                    formatted_date = created_at[:19]  # Fallback to first 19 chars
            else:
                formatted_date = str(created_at)

            text += (
                f"👤 <b>@{username}</b> (ID: <code>{telegram_id}</code>)\n"
                f"📅 Daftar: {formatted_date}\n\n"
            )

            # Add action buttons for this user
            if user.get('role') == 'owner':
                keyboard_buttons.append([
                    InlineKeyboardButton(text=f"✅ Terima @{username}", callback_data=f"accept:{telegram_id}"),
                    InlineKeyboardButton(text=f"❌ Tolak @{username}", callback_data=f"reject:{telegram_id}")
                ])
                keyboard_buttons.append([
                    InlineKeyboardButton(text=f"🚫 Ban @{username}", callback_data=f"ban:{telegram_id}")
                ])
            else:
                # Regular admin buttons
                keyboard_buttons.append([
                    InlineKeyboardButton(text=f"✅ Terima @{username}", callback_data=f"accept:{telegram_id}"),
                    InlineKeyboardButton(text=f"❌ Tolak @{username}", callback_data=f"reject:{telegram_id}")
                ])

        # Add navigation buttons if there are multiple pages
        if total_pages > 1:
            nav_buttons = []

            # Previous page button (disabled on first page)
            if page > 0:
                nav_buttons.append(InlineKeyboardButton(text="◀️ Sebelumnya", callback_data=f"register_list:{page - 1}"))

            # Page indicator
            nav_buttons.append(InlineKeyboardButton(text=f"📄 {page + 1}/{total_pages}", callback_data="noop"))

            # Next page button
            if page < total_pages - 1:
                nav_buttons.append(InlineKeyboardButton(text="▶️ Selanjutnya", callback_data=f"register_list:{page + 1}"))

            keyboard_buttons.append(nav_buttons)

        # Add refresh and back buttons
        keyboard_buttons.append([
            InlineKeyboardButton(text="🔄 Refresh", callback_data="register_list:0"),
            InlineKeyboardButton(text="🏠 Kembali ke Menu", callback_data="back_to_main")
        ])

        kb = InlineKeyboardMarkup(inline_keyboard=keyboard_buttons)
        await _safe_edit_or_fallback(c, text, reply_markup=kb, parse_mode="HTML")

    except Exception as e:
        logger.exception("Failed to refresh register list: %s", e)
        await _safe_edit_or_fallback(c, f"❌ <b>Gagal refresh daftar registrasi:</b> {e}", reply_markup=back_to_main_buttons(), parse_mode="HTML")


@router.callback_query(lambda c: c.data == 'noop')
async def cb_noop(c: CallbackQuery):
    """No operation callback - just answer to remove loading state."""
    await c.answer()


@router.callback_query(lambda c: c.data and (c.data == 'all_users' or c.data.startswith('all_users:')))
async def cb_all_users(c: CallbackQuery):
    """Refresh all users list with pagination support (excludes pending users)."""
    if c.from_user is None:
        await c.answer("Informasi pengguna tidak tersedia")
        return

    # Check if user is admin/owner
    user = await get_user_by_telegram_id(c.from_user.id)
    if not user or not is_allowed_to_create(user):
        await c.answer("Akses ditolak")
        return

    # Parse page number from callback data
    data = c.data or ""
    page = 0  # Default page
    if ':' in data:
        try:
            _, page_str = data.split(':', 1)
            page = int(page_str)
        except (ValueError, IndexError):
            page = 0

    try:
        all_users = await list_all_users()

        # Filter out pending users - only show whitelisted and banned users
        active_users = [u for u in all_users if u['status'] == 'whitelisted']
        banned_users = [u for u in all_users if u['status'] == 'banned']
        filtered_users = active_users + banned_users

        # Calculate statistics
        total_active = len(active_users)
        total_banned = len(banned_users)
        total_users = len(all_users)  # Including pending users

        if not filtered_users:
            text = (
                "👥 <b>Daftar Semua User</b>\n\n"
                f"📊 <b>Total user Aktif:</b> {total_active}\n"
                f"📊 <b>Total User di banned:</b> {total_banned}\n"
                f"📊 <b>Total user:</b> {total_users}\n\n"
                "❌ <b>Tidak ada user aktif atau banned.</b>\n\n"
                "<i>Semua user masih dalam status pending.</i>"
            )
            await _safe_edit_or_fallback(c, text, reply_markup=back_to_main_buttons())
            return

        # Pagination settings
        users_per_page = 5
        total_filtered = len(filtered_users)
        total_pages = (total_filtered + users_per_page - 1) // users_per_page  # Ceiling division
        page = 0  # Start from first page

        # Get users for current page
        start_idx = page * users_per_page
        end_idx = min(start_idx + users_per_page, total_filtered)
        page_users = filtered_users[start_idx:end_idx]

        text = (
            "👥 <b>Daftar Semua User</b>\n"
            f"📊 <b>Total user Aktif:</b> {total_active}\n"
            f"📊 <b>Total User di banned:</b> {total_banned}\n"
            f"📊 <b>Total user:</b> {total_users}\n"
            f"📄 <b>Halaman:</b> {page + 1}/{total_pages}\n\n"
        )

        keyboard_buttons = []

        for user_data in page_users:
            telegram_id = user_data['telegram_id']
            username = user_data['username'] or '-'
            role = user_data.get('role', 'user').capitalize()
            status = user_data['status']

            if status == 'whitelisted':
                text += f"✅ <b>@{username}</b>\n"
                text += f"   ├ Role: {role}\n"
                text += f"   └ ID: <code>{telegram_id}</code>\n\n"
                # Add management buttons for active users
                keyboard_buttons.append([
                    InlineKeyboardButton(text=f"⚙️ Kelola @{username}", callback_data=f"manage_user:{telegram_id}")
                ])
            elif status == 'banned':
                text += f"🚫 <b>@{username}</b>\n"
                text += f"   ├ Role: {role}\n"
                text += f"   └ ID: <code>{telegram_id}</code>\n\n"
                # Add unban button for banned users
                keyboard_buttons.append([
                    InlineKeyboardButton(text=f"✅ Unban @{username}", callback_data=f"unban:{telegram_id}")
                ])

        # Add navigation buttons if there are multiple pages
        if total_pages > 1:
            nav_buttons = []

            # Previous page button (disabled on first page)
            if page > 0:
                nav_buttons.append(InlineKeyboardButton(text="◀️ Sebelumnya", callback_data=f"all_users:{page - 1}"))

            # Page indicator
            nav_buttons.append(InlineKeyboardButton(text=f"📄 {page + 1}/{total_pages}", callback_data="noop"))

            # Next page button
            if page < total_pages - 1:
                nav_buttons.append(InlineKeyboardButton(text="▶️ Selanjutnya", callback_data=f"all_users:{page + 1}"))

            keyboard_buttons.append(nav_buttons)

        # Add refresh and back buttons
        keyboard_buttons.append([
            InlineKeyboardButton(text="🔄 Refresh", callback_data="all_users:0"),
            InlineKeyboardButton(text="🏠 Kembali ke Menu", callback_data="back_to_main")
        ])

        kb = InlineKeyboardMarkup(inline_keyboard=keyboard_buttons)
        await _safe_edit_or_fallback(c, text, reply_markup=kb, parse_mode="HTML")

    except Exception as e:
        logger.exception("Failed to show all users list: %s", e)
        await _safe_edit_or_fallback(c, f"❌ <b>Gagal mengambil daftar user:</b> {e}", reply_markup=back_to_main_buttons(), parse_mode="HTML")


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





@router.callback_query(lambda c: c.data and c.data.startswith('accept:'))
async def cb_accept(c: CallbackQuery):
    data = c.data or ""
    if not data:
        await c.answer()
        return

    _, tid = data.split(':', 1)
    telegram_id = int(tid)
    await update_user_status(telegram_id, 'whitelisted', 'user')

    # Instead of showing a simple message, refresh the register list
    # Create a mock callback with register_list:0 to refresh to first page
    mock_callback = type('MockCallback', (), {
        'data': 'register_list:0',
        'from_user': c.from_user,
        'message': c.message,
        'answer': c.answer
    })()

    await cb_register_list(mock_callback)


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
        # Instead of showing a simple message, refresh the register list
        mock_callback = type('MockCallback', (), {
            'data': 'register_list:0',
            'from_user': c.from_user,
            'message': c.message,
            'answer': c.answer
        })()
        await cb_register_list(mock_callback)
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

    # Instead of showing a simple message, refresh the all users list
    mock_callback = type('MockCallback', (), {
        'data': 'all_users:0',
        'from_user': c.from_user,
        'message': c.message,
        'answer': c.answer
    })()
    await cb_all_users(mock_callback)


@router.callback_query(lambda c: c.data and c.data.startswith('ban:'))
async def cb_ban(c: CallbackQuery):
    data = c.data or ""
    if not data:
        await c.answer()
        return

    _, tid = data.split(':', 1)
    telegram_id = int(tid)
    await ban_toggle_user(telegram_id, True)

    # Instead of showing a simple message, refresh the register list
    mock_callback = type('MockCallback', (), {
        'data': 'register_list:0',
        'from_user': c.from_user,
        'message': c.message,
        'answer': c.answer
    })()
    await cb_register_list(mock_callback)


@router.callback_query(lambda c: c.data and c.data.startswith('unban:'))
async def cb_unban(c: CallbackQuery):
    data = c.data or ""
    if not data:
        await c.answer()
        return

    _, tid = data.split(':', 1)
    telegram_id = int(tid)
    await ban_toggle_user(telegram_id, False)  # False = unban

    # Instead of showing a simple message, refresh the all users list
    mock_callback = type('MockCallback', (), {
        'data': 'all_users:0',
        'from_user': c.from_user,
        'message': c.message,
        'answer': c.answer
    })()
    await cb_all_users(mock_callback)


@router.callback_query(lambda c: c.data and c.data.startswith('manage_user:'))
async def cb_manage_user(c: CallbackQuery):
    data = c.data or ""
    if not data:
        await c.answer()
        return

    _, tid = data.split(':', 1)
    telegram_id = int(tid)

    # Get user info
    user = await get_user_by_telegram_id(telegram_id)
    if not user:
        await c.answer("User tidak ditemukan")
        return

    # Show user management options
    text = _get_user_info_text(user)
    kb = all_users_buttons(telegram_id)
    await _safe_edit_or_fallback(c, text, reply_markup=kb)
    await c.answer()


@router.callback_query(lambda c: c.data and (c.data == 'register_list' or c.data.startswith('register_list:')))
async def cb_register_list(c: CallbackQuery):
    """Refresh register list with pagination support."""
    if c.from_user is None:
        await c.answer("Informasi pengguna tidak tersedia")
        return

    # Check if user is admin/owner
    user = await get_user_by_telegram_id(c.from_user.id)
    if not user or not is_allowed_to_create(user):
        await c.answer("Akses ditolak")
        return

    # Parse page number from callback data
    data = c.data or ""
    page = 0  # Default page
    if ':' in data:
        try:
            _, page_str = data.split(':', 1)
            page = int(page_str)
        except (ValueError, IndexError):
            page = 0

    try:
        pending_users = await list_pending_users()

        if not pending_users:
            text = (
                "📋 <b>Daftar Registrasi User</b>\n\n"
                "✅ <b>Tidak ada user yang menunggu persetujuan.</b>\n\n"
                "<i>Semua user sudah diproses.</i>"
            )
            await _safe_edit_or_fallback(c, text, reply_markup=back_to_main_buttons())
            return

        # Pagination settings
        users_per_page = 5
        total_users = len(pending_users)
        total_pages = (total_users + users_per_page - 1) // users_per_page  # Ceiling division

        # Ensure page is within bounds
        if page < 0:
            page = 0
        if page >= total_pages:
            page = total_pages - 1

        # Get users for current page
        start_idx = page * users_per_page
        end_idx = min(start_idx + users_per_page, total_users)
        page_users = pending_users[start_idx:end_idx]

        text = (
            "📋 <b>Daftar Registrasi User</b>\n"
            f"📊 <b>Total menunggu:</b> {total_users}\n"
            f"📄 <b>Halaman:</b> {page + 1}/{total_pages}\n\n"
        )

        keyboard_buttons = []

        for user_data in page_users:
            telegram_id = user_data['telegram_id']
            username = user_data['username'] or '-'
            created_at = user_data.get('created_at', 'Unknown')

            # Format created_at if it's a string
           
            if isinstance(created_at, str) and 'T' in created_at:
                try:
                    dt = datetime.fromisoformat(created_at.replace('Z', '+00:00'))
                    wib_tz = timezone(timedelta(hours=7))
                    dt_wib = dt.astimezone(wib_tz)
                    formatted_date = dt_wib.strftime("%d/%m/%Y %H:%M")
                except:
                    formatted_date = created_at[:19]  # Fallback to first 19 chars
            else:
                formatted_date = str(created_at)

            text += (
                f"👤 <b>@{username}</b> (ID: <code>{telegram_id}</code>)\n"
                f"📅 Daftar: {formatted_date}\n\n"
            )

            # Add action buttons for this user
            if user.get('role') == 'owner':
                keyboard_buttons.append([
                    InlineKeyboardButton(text=f"✅ Terima @{username}", callback_data=f"accept:{telegram_id}"),
                    InlineKeyboardButton(text=f"❌ Tolak @{username}", callback_data=f"reject:{telegram_id}")
                ])
                keyboard_buttons.append([
                    InlineKeyboardButton(text=f"🚫 Ban @{username}", callback_data=f"ban:{telegram_id}")
                ])
            else:
                # Regular admin buttons
                keyboard_buttons.append([
                    InlineKeyboardButton(text=f"✅ Terima @{username}", callback_data=f"accept:{telegram_id}"),
                    InlineKeyboardButton(text=f"❌ Tolak @{username}", callback_data=f"reject:{telegram_id}")
                ])

        # Add navigation buttons if there are multiple pages
        if total_pages > 1:
            nav_buttons = []

            # Previous page button (disabled on first page)
            if page > 0:
                nav_buttons.append(InlineKeyboardButton(text="◀️ Sebelumnya", callback_data=f"register_list:{page - 1}"))

            # Page indicator
            nav_buttons.append(InlineKeyboardButton(text=f"📄 {page + 1}/{total_pages}", callback_data="noop"))

            # Next page button
            if page < total_pages - 1:
                nav_buttons.append(InlineKeyboardButton(text="▶️ Selanjutnya", callback_data=f"register_list:{page + 1}"))

            keyboard_buttons.append(nav_buttons)

        # Add refresh and back buttons
        keyboard_buttons.append([
            InlineKeyboardButton(text="🔄 Refresh", callback_data="register_list:0"),
            InlineKeyboardButton(text="🏠 Kembali ke Menu", callback_data="back_to_main")
        ])

        kb = InlineKeyboardMarkup(inline_keyboard=keyboard_buttons)
        await _safe_edit_or_fallback(c, text, reply_markup=kb, parse_mode="HTML")

    except Exception as e:
        logger.exception("Failed to refresh register list: %s", e)
        await _safe_edit_or_fallback(c, f"❌ <b>Gagal refresh daftar registrasi:</b> {e}", reply_markup=back_to_main_buttons(), parse_mode="HTML")


@router.callback_query(lambda c: c.data == 'noop')
async def cb_noop(c: CallbackQuery):
    """No operation callback - just answer to remove loading state."""
    await c.answer()


@router.callback_query(lambda c: c.data and (c.data == 'all_users' or c.data.startswith('all_users:')))
async def cb_all_users(c: CallbackQuery):
    """Refresh all users list with pagination support (excludes pending users)."""
    if c.from_user is None:
        await c.answer("Informasi pengguna tidak tersedia")
        return

    # Check if user is admin/owner
    user = await get_user_by_telegram_id(c.from_user.id)
    if not user or not is_allowed_to_create(user):
        await c.answer("Akses ditolak")
        return

    # Parse page number from callback data
    data = c.data or ""
    page = 0  # Default page
    if ':' in data:
        try:
            _, page_str = data.split(':', 1)
            page = int(page_str)
        except (ValueError, IndexError):
            page = 0

    try:
        all_users = await list_all_users()

        # Filter out pending users - only show whitelisted and banned users
        active_users = [u for u in all_users if u['status'] == 'whitelisted']
        banned_users = [u for u in all_users if u['status'] == 'banned']
        filtered_users = active_users + banned_users

        # Calculate statistics
        total_active = len(active_users)
        total_banned = len(banned_users)
        total_users = len(all_users)  # Including pending users

        if not filtered_users:
            text = (
                "👥 <b>Daftar Semua User</b>\n\n"
                f"📊 <b>Total user Aktif:</b> {total_active}\n"
                f"📊 <b>Total User di banned:</b> {total_banned}\n"
                f"📊 <b>Total user:</b> {total_users}\n\n"
                "❌ <b>Tidak ada user aktif atau banned.</b>\n\n"
                "<i>Semua user masih dalam status pending.</i>"
            )
            await _safe_edit_or_fallback(c, text, reply_markup=back_to_main_buttons())
            return

        # Pagination settings
        users_per_page = 5
        total_filtered = len(filtered_users)
        total_pages = (total_filtered + users_per_page - 1) // users_per_page  # Ceiling division
        page = 0  # Start from first page

        # Get users for current page
        start_idx = page * users_per_page
        end_idx = min(start_idx + users_per_page, total_filtered)
        page_users = filtered_users[start_idx:end_idx]

        text = (
            "👥 <b>Daftar Semua User</b>\n"
            f"📊 <b>Total user Aktif:</b> {total_active}\n"
            f"📊 <b>Total User di banned:</b> {total_banned}\n"
            f"📊 <b>Total user:</b> {total_users}\n"
            f"📄 <b>Halaman:</b> {page + 1}/{total_pages}\n\n"
        )

        keyboard_buttons = []

        for user_data in page_users:
            telegram_id = user_data['telegram_id']
            username = user_data['username'] or '-'
            role = user_data.get('role', 'user').capitalize()
            status = user_data['status']

            if status == 'whitelisted':
                text += f"✅ <b>@{username}</b>\n"
                text += f"   ├ Role: {role}\n"
                text += f"   └ ID: <code>{telegram_id}</code>\n\n"
                # Add management buttons for active users
                keyboard_buttons.append([
                    InlineKeyboardButton(text=f"⚙️ Kelola @{username}", callback_data=f"manage_user:{telegram_id}")
                ])
            elif status == 'banned':
                text += f"🚫 <b>@{username}</b>\n"
                text += f"   ├ Role: {role}\n"
                text += f"   └ ID: <code>{telegram_id}</code>\n\n"
                # Add unban button for banned users
                keyboard_buttons.append([
                    InlineKeyboardButton(text=f"✅ Unban @{username}", callback_data=f"unban:{telegram_id}")
                ])

        # Add navigation buttons if there are multiple pages
        if total_pages > 1:
            nav_buttons = []

            # Previous page button (disabled on first page)
            if page > 0:
                nav_buttons.append(InlineKeyboardButton(text="◀️ Sebelumnya", callback_data=f"all_users:{page - 1}"))

            # Page indicator
            nav_buttons.append(InlineKeyboardButton(text=f"📄 {page + 1}/{total_pages}", callback_data="noop"))

            # Next page button
            if page < total_pages - 1:
                nav_buttons.append(InlineKeyboardButton(text="▶️ Selanjutnya", callback_data=f"all_users:{page + 1}"))

            keyboard_buttons.append(nav_buttons)

        # Add refresh and back buttons
        keyboard_buttons.append([
            InlineKeyboardButton(text="🔄 Refresh", callback_data="all_users:0"),
            InlineKeyboardButton(text="🏠 Kembali ke Menu", callback_data="back_to_main")
        ])

        kb = InlineKeyboardMarkup(inline_keyboard=keyboard_buttons)
        await _safe_edit_or_fallback(c, text, reply_markup=kb, parse_mode="HTML")

    except Exception as e:
        logger.exception("Failed to show all users list: %s", e)
        await _safe_edit_or_fallback(c, f"❌ <b>Gagal mengambil daftar user:</b> {e}", reply_markup=back_to_main_buttons(), parse_mode="HTML")