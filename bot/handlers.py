from aiogram import Router, F, Bot
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton, Document
from aiogram.filters import Command
from aiogram.exceptions import TelegramBadRequest
from aiogram.fsm.state import StatesGroup, State
from aiogram.fsm.context import FSMContext
from typing import Optional, List, Dict

def escape_md(text: str) -> str:
    """Escape special characters for Markdown v2."""
    escape_chars = r'_*[]()~`>#+-=|{}.!'
    return re.sub(r'([{}])'.format(re.escape(escape_chars)), r'\\\1', text)

from db import add_pending_user, list_pending_users, list_all_users, update_user_status, get_user_by_telegram_id, ban_toggle_user, delete_user, add_meeting, update_meeting_short_url, update_meeting_short_url_by_join_url, list_meetings, list_meetings_with_shortlinks, sync_meetings_from_zoom, update_expired_meetings, update_meeting_status, update_meeting_details, update_meeting_recording_status, get_meeting_recording_status, update_meeting_live_status, get_meeting_live_status, sync_meeting_live_status_from_zoom, backup_database, backup_shorteners, create_backup_zip, restore_database, restore_shorteners, extract_backup_zip, search_users, update_command_status, check_timeout_commands, get_meeting_agent_id
from bot.keyboards import pending_user_buttons, pending_user_owner_buttons, user_action_buttons, manage_users_buttons, role_selection_buttons, status_selection_buttons, list_meetings_buttons, shortener_provider_buttons, shortener_provider_selection_buttons, shortener_custom_choice_buttons, back_to_main_buttons, back_to_main_new_buttons, main_menu_keyboard, meetings_menu_keyboard, users_menu_keyboard, backup_menu_keyboard, info_menu_keyboard, shortener_menu_keyboard
from config import settings
from bot.auth import is_allowed_to_create, is_owner_or_admin
from zoom import zoom_client
import logging

import re
import aiosqlite
from datetime import datetime, date, time, timedelta, timezone
from urllib.parse import urlparse
import uuid
from shortener import make_short
import shlex
import os
import shutil
import tempfile
import html
import json

router = Router()
# in-memory temp mapping token -> original url (short-lived)
TEMP_MEETINGS: dict = {}

logger = logging.getLogger(__name__)


# ==========================================
# Helper Functions for Agent Control
# ==========================================

def _is_agent_control_enabled() -> bool:
    """Check if agent control is enabled via ZOOM_CONTROL_MODE."""
    return settings.zoom_control_mode.lower() == "agent"


def is_agent_control_enabled() -> bool:
    """Public helper used across handlers to check agent mode."""
    return _is_agent_control_enabled()


def _agent_api_enabled() -> bool:
    """Check if agent API is enabled (backward compatibility wrapper)."""
    return _is_agent_control_enabled()


async def _agent_api_disabled_response(callback: CallbackQuery) -> None:
    """Send response when agent API is disabled."""
    await callback.answer(
        "❌ Agent control is disabled (ZOOM_CONTROL_MODE != agent). "
        "Using Zoom cloud recording instead.",
        show_alert=True
    )


# ==========================================
# FSM States
# ==========================================
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


class UserSearchStates(StatesGroup):
    waiting_for_query = State()


# ==========================================
# Helper Functions - Parsing & Extraction
# ==========================================

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








# ==========================================
# Command Handlers
# ==========================================

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
        f"Your Telegram ID: <code>{uid}</code>\n"
        f"Your username: <code>{username or '-'}</code>\n"
        f"Is owner: <code>{is_owner}</code>"
    )
    await msg.reply(text, parse_mode="HTML")


# ==========================================
# Zoom Meeting Management - FSM States
# ==========================================

class ZoomManageStates(StatesGroup):
    choosing = State()
    confirm_stop = State()
    confirm_delete = State()
    controlling_meeting = State()


class ZoomEditStates(StatesGroup):
    waiting_for_topic = State()
    waiting_for_date = State()
    waiting_for_time = State()


@router.callback_query(lambda c: c.data and c.data.startswith('control_zoom:'))
async def cb_control_zoom(c: CallbackQuery):
    """Show Zoom control interface for a meeting using Zoom API."""
    if c.from_user is None:
        await c.answer("Informasi pengguna tidak tersedia")
        return

    user = await get_user_by_telegram_id(c.from_user.id)
    if not is_owner_or_admin(user):
        await c.answer("Menu ini hanya untuk Admin/Owner.")
        return

    meeting_id = c.data.split(':', 1)[1]

    # Find meeting
    meetings = await list_meetings()
    meeting = next((m for m in meetings if m.get('zoom_meeting_id') == str(meeting_id)), None)
    if not meeting:
        await c.answer("Meeting tidak ditemukan")
        return

    topic = meeting.get('topic', 'No Topic')
    join_url = meeting.get('join_url', '')

    # Get meeting status from Zoom API
    try:
        zoom_meeting_details = await zoom_client.get_meeting(meeting_id)
        meeting_status = zoom_meeting_details.get('status', 'unknown')
        participant_count = zoom_meeting_details.get('participants_count', 0)
        start_url = zoom_meeting_details.get('start_url', '')
        join_url = zoom_meeting_details.get('join_url', '')
    except Exception as e:
        logger.error(f"Failed to get Zoom meeting details: {e}")
        meeting_status = 'unknown'
        participant_count = 0
        start_url = ''
        join_url = ''
    
    # Get recording status from DB only (Zoom API doesn't provide real-time recording status)
    current_recording_status = await get_meeting_recording_status(meeting_id) or 'stopped'

    text = (
        f"🎥 <b>Kontrol Zoom Meeting</b>\n\n"
        f"<b>{topic}</b>\n"
        f"🆔 Meeting ID: <code>{meeting_id}</code>\n"
        f"📊 Status: {meeting_status.title()}\n"
        f"👥 Participants: {participant_count}\n"
        f"🎥 Recording: {current_recording_status.title()}\n"
        f"🔗 {join_url}\n\n"
        "Pilih aksi kontrol:"
    )

    # current_recording_status from DB
    
    # Create control buttons based on meeting status
    kb_rows = []

    if meeting_status == 'started':
        kb_rows.append([InlineKeyboardButton(text="⏹️ End Meeting", callback_data=f"end_zoom_meeting:{meeting_id}")])
        
        # Dynamic recording controls based on status
        if current_recording_status == 'stopped':
            # Show Start Recording only
            kb_rows.append([InlineKeyboardButton(text="⏺️ Start Recording", callback_data=f"cloud_start_record:{meeting_id}")])
            # Check if there's a completed recording available for download
            try:
                recording_info = await zoom_client.get_meeting_recording_status(meeting_id)
                if recording_info and recording_info.get('recording_files'):
                    # Add download link to Zoom cloud recordings
                    kb_rows.append([InlineKeyboardButton(text="📥 Download Hasil Recording", url=f"https://zoom.us/recording")])
            except Exception as e:
                logger.debug(f"Could not check recording files: {e}")
        elif current_recording_status == 'recording':
            # Show Pause and Stop
            kb_rows.append([
                InlineKeyboardButton(text="⏸️ Pause Recording", callback_data=f"cloud_pause_record:{meeting_id}"),
                InlineKeyboardButton(text="⏹️ Stop Recording", callback_data=f"cloud_stop_record:{meeting_id}")
            ])
        elif current_recording_status == 'paused':
            # Show Resume and Stop
            kb_rows.append([
                InlineKeyboardButton(text="▶️ Resume Recording", callback_data=f"cloud_resume_record:{meeting_id}"),
                InlineKeyboardButton(text="⏹️ Stop Recording", callback_data=f"cloud_stop_record:{meeting_id}")
            ])
        
        if is_agent_control_enabled():
            kb_rows.append([InlineKeyboardButton(text="🔇 Mute All", callback_data=f"mute_all_participants:{meeting_id}")])
    else:
        # Cloud mode: expose start_url for one-click host launch when available
        if start_url:
            kb_rows.append([InlineKeyboardButton(text="🚀 Mulai sebagai Host", url=start_url)])
        # Fallback to API start if URL missing or user prefers inline action
        kb_rows.append([InlineKeyboardButton(text="▶️ Start Meeting", callback_data=f"start_zoom_meeting:{meeting_id}")])

    # Always available actions
    kb_rows.extend([
        [InlineKeyboardButton(text="🔄️ Refresh Status", callback_data=f"control_zoom:{meeting_id}")],
        [InlineKeyboardButton(text="📊 Meeting Details", callback_data=f"zoom_meeting_details:{meeting_id}")],
        [InlineKeyboardButton(text="⬅️ Kembali ke Daftar", callback_data="list_meetings")]
    ])

    kb = InlineKeyboardMarkup(inline_keyboard=kb_rows)

    await _safe_edit_or_fallback(c, text, reply_markup=kb, parse_mode="HTML")
    await c.answer()


# ==========================================
# Zoom Control Handlers - Cloud Mode API
# ==========================================

@router.callback_query(lambda c: c.data and c.data.startswith('start_zoom_meeting:'))
async def cb_start_zoom_meeting(c: CallbackQuery):
    """Start a Zoom meeting via Zoom API and provide start URL for host."""
    if c.from_user is None:
        await c.answer("Informasi pengguna tidak tersedia")
        return

    user = await get_user_by_telegram_id(c.from_user.id)
    if not is_owner_or_admin(user):
        await c.answer("Aksi ini hanya untuk Admin/Owner.")
        return

    meeting_id = c.data.split(':', 1)[1]

    await c.answer("Memulai meeting...")

    try:
        # Get meeting details first to retrieve start_url
        meeting_details = await zoom_client.get_meeting(meeting_id)
        
        if not meeting_details:
            text = "❌ Meeting tidak ditemukan atau sudah dihapus."
            kb = InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="📋 Daftar Meeting", callback_data="list_meetings")]
            ])
            await _safe_edit_or_fallback(c, text, reply_markup=kb, parse_mode="HTML")
            return
        
        # Start the meeting via Zoom API
        await zoom_client.start_meeting(meeting_id)
        
        # Extract URLs from meeting details
        start_url = meeting_details.get('start_url', '')
        join_url = meeting_details.get('join_url', '')
        topic = meeting_details.get('topic', 'Meeting')
        
        if start_url:
            text = (
                "✅ <b>Meeting Siap Dimulai!</b>\n\n"
                f"📌 <b>Topic:</b> {topic}\n"
                f"🔗 <b>Join URL:</b> <code>{join_url}</code>\n\n"
                "Klik tombol <b>🚀 Mulai sebagai Host</b> di bawah ini untuk:\n"
                "• Membuka Zoom di browser/aplikasi Anda\n"
                "• Join otomatis sebagai Host\n"
                "• Kontrol penuh atas meeting\n\n"
                "<i>💡 Anda akan dibawa ke Zoom tanpa perlu login manual!</i>"
            )
            
            kb = InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="🚀 Mulai sebagai Host", url=start_url)],
                [InlineKeyboardButton(text="📋 Join URL (Copy)", url=join_url)],
                [InlineKeyboardButton(text="🎥 Kembali ke Kontrol", callback_data=f"control_zoom:{meeting_id}")],
                [InlineKeyboardButton(text="📋 Daftar Meeting", callback_data="list_meetings")]
            ])
        else:
            text = "❌ Gagal memulai meeting. Start URL tidak tersedia."
            kb = InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="🎥 Kembali ke Kontrol", callback_data=f"control_zoom:{meeting_id}")],
                [InlineKeyboardButton(text="📋 Daftar Meeting", callback_data="list_meetings")]
            ])

    except Exception as e:
        logger.error(f"Failed to start Zoom meeting {meeting_id}: {e}")
        text = f"❌ <b>Error:</b> {str(e)}"
        kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🎥 Kembali ke Kontrol", callback_data=f"control_zoom:{meeting_id}")],
            [InlineKeyboardButton(text="📋 Daftar Meeting", callback_data="list_meetings")]
        ])

    await _safe_edit_or_fallback(c, text, reply_markup=kb, parse_mode="HTML")


@router.callback_query(lambda c: c.data and c.data.startswith('end_zoom_meeting:'))
async def cb_end_zoom_meeting(c: CallbackQuery):
    """End a Zoom meeting via Zoom API."""
    if c.from_user is None:
        await c.answer("Informasi pengguna tidak tersedia")
        return

    user = await get_user_by_telegram_id(c.from_user.id)
    if not is_owner_or_admin(user):
        await c.answer("Aksi ini hanya untuk Admin/Owner.")
        return

    meeting_id = c.data.split(':', 1)[1]

    await c.answer("Mengakhiri meeting...")

    try:
        # End the meeting via Zoom API
        result = await zoom_client.end_meeting(meeting_id)
        text = "✅ <b>Meeting berhasil diakhiri.</b>"

    except Exception as e:
        logger.error(f"Failed to end Zoom meeting {meeting_id}: {e}")
        text = f"❌ Error: {str(e)}"

    # Return to control interface
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🎥 Kembali ke Kontrol", callback_data=f"control_zoom:{meeting_id}")],
        [InlineKeyboardButton(text="📋 Daftar Meeting", callback_data="list_meetings")]
    ])

    await _safe_edit_or_fallback(c, text, reply_markup=kb, parse_mode="HTML")


@router.callback_query(lambda c: c.data and c.data.startswith('mute_all_participants:'))
async def cb_mute_all_participants(c: CallbackQuery):
    """Mute all participants in Zoom meeting."""
    if c.from_user is None:
        await c.answer("Informasi pengguna tidak tersedia")
        return

    user = await get_user_by_telegram_id(c.from_user.id)
    if not is_owner_or_admin(user):
        await c.answer("Aksi ini hanya untuk Admin/Owner.")
        return

    if not is_agent_control_enabled():
        text = (
            "🔇 <b>Mute All</b> hanya tersedia di Zoom Control Mode = <b>agent</b>.<br>"
            "Set ZOOM_CONTROL_MODE=agent dan jalankan Agent untuk menggunakan fitur ini."
        )
        kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🎥 Kembali ke Kontrol", callback_data=f"control_zoom:{c.data.split(':', 1)[1]}")],
            [InlineKeyboardButton(text="📋 Daftar Meeting", callback_data="list_meetings")]
        ])
        await _safe_edit_or_fallback(c, text, reply_markup=kb, parse_mode="HTML")
        return

    meeting_id = c.data.split(':', 1)[1]

    await c.answer("Mute all participants...")

    try:
        # Mute all participants via Zoom API
        result = await zoom_client.mute_all_participants(meeting_id)
        text = "✅ <b>Semua participants berhasil di-mute.</b>"

    except Exception as e:
        logger.error(f"Failed to mute all participants in meeting {meeting_id}: {e}")
        text = f"❌ Error: {str(e)}"

    # Return to control interface
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🎥 Kembali ke Kontrol", callback_data=f"control_zoom:{meeting_id}")],
        [InlineKeyboardButton(text="📋 Daftar Meeting", callback_data="list_meetings")]
    ])

    await _safe_edit_or_fallback(c, text, reply_markup=kb, parse_mode="HTML")


@router.callback_query(lambda c: c.data and c.data.startswith('zoom_meeting_details:'))
async def cb_zoom_meeting_details(c: CallbackQuery):
    """Get detailed information about Zoom meeting."""
    if c.from_user is None:
        await c.answer("Informasi pengguna tidak tersedia")
        return

    user = await get_user_by_telegram_id(c.from_user.id)
    if not is_owner_or_admin(user):
        await c.answer("Aksi ini hanya untuk Admin/Owner.")
        return

    meeting_id = c.data.split(':', 1)[1]

    await c.answer("Mengambil detail meeting...")

    try:
        # Get meeting details via Zoom API
        details = await zoom_client.get_meeting(meeting_id)

        text = "📊 <b>Meeting Details</b>\n\n"
        text += f"🆔 <b>ID:</b> {meeting_id}\n"
        text += f"📝 <b>Topic:</b> {details.get('topic', 'N/A')}\n"
        text += f"👤 <b>Host:</b> {details.get('host_email', 'N/A')}\n"
        text += f"📊 <b>Status:</b> {details.get('status', 'N/A')}\n"
        text += f"🕛 <b>Start Time:</b> {details.get('start_time', 'N/A')}\n"
        text += f"⏱️ <b>Duration:</b> {details.get('duration', 'N/A')} minutes\n"
        text += f"🎥 <b>Recording:</b> {details.get('recording_enabled', False)}\n"
        text += f"🔗 <b>Join URL:</b> {details.get('join_url', 'N/A')}\n"
        
        # Add Start URL if available
        start_url = details.get('start_url')
        if start_url:
            text += f"▶️ <b>Start URL:</b> {start_url}\n"

        if details.get('settings'):
            settings = details['settings']
            text += f"\n⚙️ <b>Settings:</b>\n"
            text += f"  🔒 Waiting Room: {settings.get('waiting_room', False)}\n"
            text += f"  🔇 Auto Mute: {settings.get('auto_mute', False)}\n"
            text += f"  🎥 Auto Record: {settings.get('auto_recording', 'none')}\n"

    except Exception as e:
        logger.error(f"Failed to get Zoom meeting details for {meeting_id}: {e}")
        text = f"❌ Error getting meeting details: {str(e)}"

    # Return to control interface
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🎥 Kembali ke Kontrol", callback_data=f"control_zoom:{meeting_id}")],
        [InlineKeyboardButton(text="📋 Daftar Meeting", callback_data="list_meetings")]
    ])

    await _safe_edit_or_fallback(c, text, reply_markup=kb, parse_mode="HTML")


# ==========================================
# Meeting Management - Agent & Control Flow
# ==========================================

@router.callback_query(lambda c: c.data and c.data.startswith('manage_meeting:'))
async def cb_manage_meeting(c: CallbackQuery):
    """Show management options for a specific meeting."""
    if c.from_user is None:
        await c.answer("Informasi pengguna tidak tersedia")
        return

    meeting_id = c.data.split(':', 1)[1]
    # find meeting in DB
    meetings = await list_meetings()
    meeting = next((m for m in meetings if m.get('zoom_meeting_id') == str(meeting_id)), None)
    if not meeting:
        await c.answer("Meeting tidak ditemukan")
        return

    topic = meeting.get('topic', 'No Topic')
    join_url = meeting.get('join_url', '')
    start_time = meeting.get('start_time', '')
    created_by = meeting.get('created_by', 'Unknown')
    
    # Get creator username
    creator_username = await _get_username_from_telegram_id(created_by)
    
    # Format time with day name and full date
    formatted_time = start_time
    try:
        if start_time:
            # Try to parse as ISO format first
            dt = datetime.fromisoformat(start_time.replace('Z', '+00:00'))
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
            
            formatted_time = f"{day_name}, {day} {month_name} {year} pada pukul {time_str}"
    except Exception:
        pass  # Keep original start_time if parsing fails

    text = (
        f"⚙️ Manage Meeting <b>{topic}</b>\n\n"
        f"🆔 <b>Meeting ID:</b> <code>{meeting_id}</code>\n"
        f"👤 <b>Creator:</b> {creator_username}\n"
        f"🕛 <b>Waktu:</b> {formatted_time}\n"
        f"🔗 <b>Zoom Link:</b> {join_url}\n\n"
        "Pilih tindakan di bawah ini:"
    )

    if not _agent_api_enabled():
        kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🗑️ Delete Meeting", callback_data=f"confirm_delete:{meeting_id}" )],
            [InlineKeyboardButton(text="✏️ Edit Meeting", callback_data=f"edit_meeting:{meeting_id}" )],
            [InlineKeyboardButton(text="🏠 Kembali", callback_data="list_meetings")]
        ])
        text += "\n\n🔒 Agent API dimatikan (AGENT_API_ENABLED=false). Rekaman akan memakai auto recording Zoom."
    else:
        # Check live status to determine button text
        # First sync with Zoom API to get accurate status
        live_status = await sync_meeting_live_status_from_zoom(zoom_client, meeting_id)
        if live_status == 'started':
            start_button_text = "🎛️ Control Meeting"
            start_callback = f"control_meeting:{meeting_id}"
        else:
            start_button_text = "▶️ Start Meeting on Agent"
            start_callback = f"start_on_agent:{meeting_id}"

        kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text=start_button_text, callback_data=start_callback)],
            [InlineKeyboardButton(text="🗑️ Delete Meeting", callback_data=f"confirm_delete:{meeting_id}" )],
            [InlineKeyboardButton(text="✏️ Edit Meeting", callback_data=f"edit_meeting:{meeting_id}" )],
            [InlineKeyboardButton(text="🏠 Kembali", callback_data="list_meetings")]
        ])

    await _safe_edit_or_fallback(c, text, reply_markup=kb, parse_mode="HTML")
    await c.answer()


@router.callback_query(lambda c: c.data and c.data.startswith('start_on_agent:'))
async def cb_start_on_agent(c: CallbackQuery):
    """Show agent selection to start/open meeting on a specific agent host."""
    if not _agent_api_enabled():
        await _agent_api_disabled_response(c)
        return
    meeting_id = c.data.split(':', 1)[1]
    agents = _filter_online_agents(await list_agents())
    if not agents:
        await _safe_edit_or_fallback(c, "Tidak ada agent yang sedang online. Pastikan agent sudah terhubung dan polling ke server.")
        await c.answer()
        return

    kb_rows = []
    for a in agents:
        kb_rows.append([InlineKeyboardButton(text=f"{a['name']} ({a.get('os_type') or 'unknown'})", callback_data=f"agent_start:{meeting_id}:{a['id']}")])
    kb_rows.append([InlineKeyboardButton(text="❌ Batal", callback_data=f"manage_meeting:{meeting_id}")])
    kb = InlineKeyboardMarkup(inline_keyboard=kb_rows)
    await _safe_edit_or_fallback(c, "Pilih agent untuk membuka meeting pada host tersebut:", reply_markup=kb)
    await c.answer()


@router.callback_query(lambda c: c.data and c.data.startswith('control_meeting:'))
async def cb_control_meeting(c: CallbackQuery, state: FSMContext):
    """Show control interface for an already started meeting."""
    meeting_id = c.data.split(':', 1)[1]
    
    # find meeting
    meetings = await list_meetings()
    meeting = next((m for m in meetings if m.get('zoom_meeting_id') == str(meeting_id)), None)
    if not meeting:
        await c.answer("Meeting tidak ditemukan")
        return

    # Check if meeting is actually started
    live_status = await get_meeting_live_status(meeting_id)
    if live_status != 'started':
        await _safe_edit_or_fallback(c, "Meeting belum dimulai. Gunakan 'Start Meeting on Agent' terlebih dahulu.")
        await c.answer()
        return

    # Get current recording status and check if recording has ever been started
    recording_status = await get_meeting_recording_status(meeting_id) or 'stopped'
    
    # Get agent_id for this meeting
    agent_id = await get_meeting_agent_id(meeting_id)
    
    # Check if recording has ever been started (has recording history)
    async with aiosqlite.connect(settings.db_path) as db:
        cursor = await db.execute("SELECT recording_started_at FROM meeting_live_status WHERE zoom_meeting_id = ?", (meeting_id,))
        row = await cursor.fetchone()
        has_recording_history = row is not None and row[0] is not None
    
    # Set state to controlling
    await state.set_state(ZoomManageStates.controlling_meeting)
    await state.update_data(meeting_id=meeting_id, agent_id=agent_id)

    text = (
        f"🎛️ <b>Control Meeting {meeting.get('topic', 'Unknown Meeting')}</b>\n\n"
        f"Status: Sedang Berlangsung\n"
        f"Recording: {recording_status.title()}\n"
    )
    
    # Add agent info if available
    if agent_id:
        try:
            agent = await get_agent(agent_id)
            if agent:
                text += f"Agent: {agent['name']}\n"
        except Exception as e:
            logger.error("Failed to get agent info: %s", e)
    
    text += "\nGunakan kontrol di bawah ini:"

    # Build keyboard based on recording status
    kb_rows = [
        [InlineKeyboardButton(text="🛑 Stop Meeting", callback_data=f"stop_meeting:{meeting_id}")]
    ]
    
    # Recording controls
    if recording_status == 'recording':
        record_button = InlineKeyboardButton(text="⏹️ Stop Recording", callback_data=f"toggle_record:{meeting_id}")
        pause_button = InlineKeyboardButton(text="⏸️ Pause Recording", callback_data=f"pause_record:{meeting_id}")
    elif recording_status == 'paused':
        record_button = InlineKeyboardButton(text="⏹️ Stop Recording", callback_data=f"toggle_record:{meeting_id}")
        pause_button = InlineKeyboardButton(text="▶️ Resume Recording", callback_data=f"pause_record:{meeting_id}")
    else:  # stopped
        record_button = InlineKeyboardButton(text="⏺️ Start Recording", callback_data=f"toggle_record:{meeting_id}")
        # Resume button is not shown when stopped - only when paused
        pause_button = None
    
    if pause_button:
        kb_rows.append([record_button, pause_button])
    else:
        kb_rows.append([record_button])
    
    kb_rows.append([InlineKeyboardButton(text="🏠 Kembali ke Manage", callback_data=f"manage_meeting:{meeting_id}")])
    
    kb = InlineKeyboardMarkup(inline_keyboard=kb_rows)

    await _safe_edit_or_fallback(c, text, reply_markup=kb, parse_mode="HTML")
    await c.answer()


@router.callback_query(lambda c: c.data and c.data.startswith('agent_start:'))
async def cb_agent_start(c: CallbackQuery, state: FSMContext):
    # callback data: agent_start:<meeting_id>:<agent_id>
    parts = c.data.split(':')
    if len(parts) < 3:
        await c.answer("Data agent tidak lengkap")
        return
    meeting_id = parts[1]
    agent_id = int(parts[2])
    agent = await get_agent(agent_id)
    if not agent:
        await _safe_edit_or_fallback(c, "Agent tidak ditemukan")
        await c.answer()
        return

    # find meeting join_url
    meetings = await list_meetings()
    meeting = next((m for m in meetings if m.get('zoom_meeting_id') == str(meeting_id)), None)
    if not meeting:
        await _safe_edit_or_fallback(c, "Meeting tidak ditemukan")
        await c.answer()
        return

    join_url = meeting.get('join_url')
    if not join_url:
        await _safe_edit_or_fallback(c, "Meeting tidak memiliki join_url")
        await c.answer()
        return

    # queue command for agent to pick up via polling
    try:
        # Create JSON payload for start_zoom action
        payload_data = {
            "action": "start_zoom",
            "url": join_url,
            "meeting_id": meeting_id,
            "topic": meeting.get('topic', 'Unknown Meeting'),
            "timeout": 60  # 60 seconds timeout
        }
        payload_json = json.dumps(payload_data)
        
        cid = await add_command(agent_id, 'start_zoom', payload_json)
        
        # Store meeting info in FSM state
        await state.update_data(
            meeting_id=meeting_id,
            agent_id=agent_id,
            agent_name=agent['name'],
            command_id=cid,
            topic=meeting.get('topic', 'Unknown Meeting')
        )
        
        # Transition to controlling meeting state
        await state.set_state(ZoomManageStates.controlling_meeting)
        
        # Update live status to started with agent_id
        await update_meeting_live_status(meeting_id, 'started', agent_id)
        
        # Show meeting control interface
        text = (
            f"🎥 <b>Meeting Control</b>\n\n"
            f"Meeting: <b>{meeting.get('topic', 'Unknown Meeting')}</b>\n"
            f"Agent: <b>{agent['name']}</b>\n"
            f"Command ID: {cid}\n\n"
            "Meeting telah diantrikan untuk dibuka di agent. Gunakan kontrol di bawah ini:"
        )
        
        kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🛑 Stop Meeting", callback_data=f"stop_meeting:{meeting_id}")],
            [InlineKeyboardButton(text="⏺️ Start/Stop Recording", callback_data=f"toggle_record:{meeting_id}"), 
             InlineKeyboardButton(text="⏸️ Pause/Resume Recording", callback_data=f"pause_record:{meeting_id}")],
            [InlineKeyboardButton(text="🏠 Kembali ke Manage", callback_data=f"manage_meeting:{meeting_id}")]
        ])
        
        await _safe_edit_or_fallback(c, text, reply_markup=kb, parse_mode="HTML")
        
    except Exception as e:
        logger.exception("Failed to queue command for agent %s: %s", agent_id, e)
        await _safe_edit_or_fallback(c, f"❌ Gagal mengantri perintah untuk agent: {e}")

    await c.answer()





@router.callback_query(lambda c: c.data and c.data.startswith('start_meeting:'))
async def cb_start_meeting(c: CallbackQuery):
    """Provide link to open Zoom and show Stop/recording controls (local instruction).

    Note: bots cannot send keyboard events to a user's local machine. This flow provides
    instructions and server-side fallbacks (end meeting via Zoom API) where possible.
    """
    meeting_id = c.data.split(':', 1)[1]
    meetings = await list_meetings()
    meeting = next((m for m in meetings if m.get('zoom_meeting_id') == str(meeting_id)), None)
    if not meeting:
        await c.answer("Meeting tidak ditemukan")
        return

    join_url = meeting.get('join_url', '')

    # store local manage state
    globals().setdefault('MEETING_MANAGE_STATE', {})
    globals()['MEETING_MANAGE_STATE'].setdefault(str(meeting_id), {'started': True, 'recording': False, 'paused': False})

    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Open in Zoom (Client)", url=join_url)],
        [InlineKeyboardButton(text="🛑 Stop Meeting (Server-side)", callback_data=f"confirm_stop:{meeting_id}" )],
        [InlineKeyboardButton(text="⏺️ Start/Stop Local Recording (Alt+R)", callback_data=f"toggle_record:{meeting_id}"), InlineKeyboardButton(text="⏸️ Pause/Resume Recording (Alt+P)", callback_data=f"pause_record:{meeting_id}")],
        [InlineKeyboardButton(text="🏠 Kembali", callback_data=f"manage_meeting:{meeting_id}")]
    ])

    text = (
        "🔗 Klik tombol di bawah untuk membuka Zoom (apabila link diarahkan ke aplikasi Zoom client, sistem akan membuka aplikasi).\n\n"
        "Jika Anda berada di host dan ingin mengakhiri meeting dari sini, gunakan tombol Stop Meeting (server-side).\n"
        "Untuk kontrol rekaman lokal, gunakan tombol yang memberi instruksi keyboard (Alt+R / Alt+P) pada mesin yang menjalankan Zoom client.\n\n"
        f"Link meeting: {join_url}"
    )

    await _safe_edit_or_fallback(c, text, reply_markup=kb, parse_mode="HTML")
    await c.answer()


@router.callback_query(lambda c: c.data and c.data.startswith('confirm_stop:'))
async def cb_confirm_stop(c: CallbackQuery):
    meeting_id = c.data.split(':', 1)[1]
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ Ya, End Meeting (Server)", callback_data=f"stop_meeting:{meeting_id}"), InlineKeyboardButton(text="❌ Batal", callback_data=f"manage_meeting:{meeting_id}")]
    ])
    await _safe_edit_or_fallback(c, f"Apakah Anda yakin ingin mengakhiri meeting <code>{meeting_id}</code>?", reply_markup=kb, parse_mode="HTML")
    await c.answer()


@router.callback_query(lambda c: c.data and c.data.startswith('stop_meeting:'), ZoomManageStates.controlling_meeting)
async def cb_stop_meeting(c: CallbackQuery, state: FSMContext):
    meeting_id = c.data.split(':', 1)[1]
    await c.answer("Mengakhiri meeting...")
    
    # Get meeting data from FSM state
    data = await state.get_data()
    topic = data.get('topic', 'Unknown Meeting')
    
    try:
        ok = await zoom_client.end_meeting(meeting_id)
        if ok:
            # update DB status
            await update_meeting_status(meeting_id, 'deleted')
            # Update live status to ended
            await update_meeting_live_status(meeting_id, 'ended')
            
            # Clear FSM state
            await state.clear()
            
            text = (
                f"✅ Meeting berhasil diakhiri (server-side).\n\n"
                f"Meeting: <b>{topic}</b>\n"
                f"Meeting ID: <code>{meeting_id}</code>\n\n"
                "Meeting telah dihapus dari Zoom."
            )
            
            kb = InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="🏠 Kembali ke Daftar Meeting", callback_data="list_meetings")]
            ])
            
            await _safe_edit_or_fallback(c, text, reply_markup=kb, parse_mode="HTML")
        else:
            text = (
                f"❌ Gagal mengakhiri meeting {meeting_id} via API.\n\n"
                f"Meeting: <b>{topic}</b>\n\n"
                "Coba hapus meeting secara manual atau cek status di Zoom."
            )
            
            # Keep the control interface for retry
            kb = InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="🛑 Coba Lagi Stop Meeting", callback_data=f"stop_meeting:{meeting_id}")],
                [InlineKeyboardButton(text="⏺️ Start/Stop Recording", callback_data=f"toggle_record:{meeting_id}"), 
                 InlineKeyboardButton(text="⏸️ Pause/Resume Recording", callback_data=f"pause_record:{meeting_id}")],
                [InlineKeyboardButton(text="🏠 Kembali ke Manage", callback_data=f"manage_meeting:{meeting_id}")]
            ])
            
            await _safe_edit_or_fallback(c, text, reply_markup=kb, parse_mode="HTML")
            
    except Exception as e:
        logger.exception("Failed to end meeting %s: %s", meeting_id, e)
        
        text = (
            f"❌ Error saat mengakhiri meeting.\n\n"
            f"Meeting: <b>{topic}</b>\n"
            f"Error: {e}\n\n"
            "Coba lagi atau hubungi administrator."
        )
        
        # Keep the control interface for retry
        kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🛑 Coba Lagi Stop Meeting", callback_data=f"stop_meeting:{meeting_id}")],
            [InlineKeyboardButton(text="⏺️ Start/Stop Recording", callback_data=f"toggle_record:{meeting_id}"), 
             InlineKeyboardButton(text="⏸️ Pause/Resume Recording", callback_data=f"pause_record:{meeting_id}")],
            [InlineKeyboardButton(text="🏠 Kembali ke Manage", callback_data=f"manage_meeting:{meeting_id}")]
        ])
        
        await _safe_edit_or_fallback(c, text, reply_markup=kb, parse_mode="HTML")


@router.callback_query(lambda c: c.data and c.data.startswith('manage_meeting:'), ZoomManageStates.controlling_meeting)
async def cb_back_to_manage_from_control(c: CallbackQuery, state: FSMContext):
    """Handle back to manage from meeting control FSM state."""
    # Clear the FSM state
    await state.clear()
    
    # Continue with normal manage_meeting handler
    await cb_manage_meeting(c)


@router.callback_query(lambda c: c.data and c.data.startswith('confirm_delete:'))
async def cb_confirm_delete(c: CallbackQuery):
    meeting_id = c.data.split(':', 1)[1]
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ Ya, Hapus Meeting", callback_data=f"delete_meeting:{meeting_id}"), InlineKeyboardButton(text="❌ Batal", callback_data=f"manage_meeting:{meeting_id}")]
    ])
    await _safe_edit_or_fallback(c, f"Konfirmasi: hapus meeting <code>{meeting_id}</code>? Ini akan menghapus meeting dari Zoom.", reply_markup=kb, parse_mode="HTML")
    await c.answer()


@router.callback_query(lambda c: c.data and c.data.startswith('delete_meeting:'))
async def cb_delete_meeting(c: CallbackQuery):
    meeting_id = c.data.split(':', 1)[1]
    await c.answer("Menghapus meeting dari Zoom...")
    try:
        ok = await zoom_client.delete_meeting(meeting_id)
        if ok:
            await update_meeting_status(meeting_id, 'deleted')
            await _safe_edit_or_fallback(c, f"✅ Meeting <code>{meeting_id}</code> dihapus dari Zoom dan ditandai di DB.", parse_mode="HTML")
        else:
            await _safe_edit_or_fallback(c, f"❌ Gagal menghapus meeting {meeting_id} via API.")
    except Exception as e:
        logger.exception("Failed to delete meeting %s: %s", meeting_id, e)
        await _safe_edit_or_fallback(c, f"❌ Error saat menghapus meeting: {e}")


@router.callback_query(lambda c: c.data and c.data.startswith('edit_meeting:'))
async def cb_edit_meeting(c: CallbackQuery, state: FSMContext):
    meeting_id = c.data.split(':', 1)[1]
    
    # Get current meeting data and store in state
    meetings = await list_meetings()
    meeting = next((m for m in meetings if m.get('zoom_meeting_id') == str(meeting_id)), None)
    if not meeting:
        await _safe_edit_or_fallback(c, "Meeting tidak ditemukan")
        return
    
    # Store current values in state
    current_topic = meeting.get('topic', '')
    current_start_time = meeting.get('start_time', '')
    
    # Parse current date and time
    current_date = None
    current_time = None
    if current_start_time:
        try:
            dt = datetime.fromisoformat(current_start_time.replace('Z', '+00:00'))
            current_date = str(dt.date())
            current_time = dt.time()
        except:
            pass
    
    await state.update_data(
        edit_meeting_id=meeting_id,
        current_topic=current_topic,
        current_date=current_date,
        current_time=current_time,
        # Initialize new values as None (will be set when user inputs or skips)
        new_topic=None,
        new_date=None,
        new_time=None
    )
    
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="⏭️ Skip Topic", callback_data="skip_topic")]
    ])

    current_topic_display = current_topic if current_topic else "Tidak ada topik"
    text = (
        f"✏️ <b>Edit Meeting - Topik</b>\n\n"
        f"📝 <b>Topik Saat Ini:</b> {current_topic_display}\n\n"
        f"📝 <b>Topik Baru:</b>\n"
        f"Kirimkan topik meeting yang baru, atau klik tombol di bawah untuk melewati langkah ini."
    )

    await _safe_edit_or_fallback(c, text, reply_markup=kb, parse_mode="HTML")
    await state.set_state(ZoomEditStates.waiting_for_topic)
    await c.answer()


@router.message(ZoomEditStates.waiting_for_topic)
async def edit_meeting_topic(msg: Message, state: FSMContext):
    if not msg.text:
        await msg.reply("Silakan kirim topik meeting sebagai teks.")
        return
    await state.update_data(new_topic=msg.text.strip())
    
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="⏭️ Skip Tanggal", callback_data="skip_date")],
        [InlineKeyboardButton(text="🏠 Kembali", callback_data="list_meetings")]
    ])
    
    await msg.reply("Silakan kirim <b>tanggal</b> baru (format: DD-MM-YYYY atau '31 Desember 2025').", parse_mode="HTML", reply_markup=kb)
    await state.set_state(ZoomEditStates.waiting_for_date)


@router.message(ZoomEditStates.waiting_for_date)
async def edit_meeting_date(msg: Message, state: FSMContext):
    d = _parse_indonesia_date(msg.text)
    if not d:
        await msg.reply("Format tanggal tidak dikenal. Gunakan DD-MM-YYYY atau '31 Desember 2025'.")
        return
    await state.update_data(new_date=str(d))
    
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="⏭️ Skip Waktu", callback_data="skip_time")],
        [InlineKeyboardButton(text="🏠 Kembali", callback_data="list_meetings")]
    ])
    
    await msg.reply("Silakan kirim <b>waktu</b> baru (format 24-jam, contoh: 14:30).", parse_mode="HTML", reply_markup=kb)
    await state.set_state(ZoomEditStates.waiting_for_time)


@router.message(ZoomEditStates.waiting_for_time)
async def edit_meeting_time(msg: Message, state: FSMContext):
    t = _parse_time_24h(msg.text)
    if not t:
        await msg.reply("Format waktu tidak valid. Gunakan HH:MM (24 jam).")
        return

    # Store the new time
    await state.update_data(new_time=t)

    data = await state.get_data()
    meeting_id = data.get('edit_meeting_id')
    topic = data.get('new_topic') or data.get('current_topic', '')
    date_str = data.get('new_date') or data.get('current_date')
    
    if not (meeting_id and topic and date_str):
        await msg.reply("Data edit tidak lengkap. Mulai lagi.")
        await state.clear()
        return

    # Combine date and time into ISO with WIB timezone
    d = datetime.fromisoformat(date_str)
    dt = datetime.combine(d.date(), t)
    tz = timezone(timedelta(hours=7))
    dt = dt.replace(tzinfo=tz)
    start_time_iso = dt.isoformat()

    await msg.reply("Memperbarui meeting... Mohon tunggu.")
    try:
        # Call Zoom API to update
        resp = await zoom_client.update_meeting(meeting_id, topic=topic, start_time=start_time_iso)
        # Update local DB
        await update_meeting_details(meeting_id, topic=topic, start_time=start_time_iso)
        # Show success message with auto-return option
        kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="📅 Kembali ke Daftar Meeting", callback_data="list_meetings")]
        ])
        await msg.reply(f"✅ Meeting berhasil diperbarui! (meeting_id={meeting_id})", reply_markup=kb)
    except Exception as e:
        logger.exception("Failed to update meeting %s: %s", meeting_id, e)
        await msg.reply(f"❌ Gagal memperbarui meeting: {e}")

    await state.clear()


@router.callback_query(lambda c: c.data == 'skip_topic')
async def cb_skip_topic(c: CallbackQuery, state: FSMContext):
    """Skip topic editing and proceed to date editing."""
    data = await state.get_data()
    
    # Use current topic if no new topic was set
    if not data.get('new_topic'):
        await state.update_data(new_topic=data.get('current_topic', ''))
    
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="⏭️ Skip Tanggal", callback_data="skip_date")],
        [InlineKeyboardButton(text="🏠 Kembali", callback_data="list_meetings")]
    ])
    
    await _safe_edit_or_fallback(c, "Silakan kirim <b>tanggal</b> baru (format: DD-MM-YYYY atau '31 Desember 2025').", parse_mode="HTML", reply_markup=kb)
    await state.set_state(ZoomEditStates.waiting_for_date)
    await c.answer()


@router.callback_query(lambda c: c.data == 'skip_date')
async def cb_skip_date(c: CallbackQuery, state: FSMContext):
    """Skip date editing and proceed to time editing."""
    data = await state.get_data()
    
    # Use current date if no new date was set
    if not data.get('new_date'):
        await state.update_data(new_date=data.get('current_date'))
    
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="⏭️ Skip Waktu", callback_data="skip_time")],
        [InlineKeyboardButton(text="🏠 Kembali", callback_data="list_meetings")]
    ])
    
    await _safe_edit_or_fallback(c, "Silakan kirim <b>waktu</b> baru (format 24-jam, contoh: 14:30).", parse_mode="HTML", reply_markup=kb)
    await state.set_state(ZoomEditStates.waiting_for_time)
    await c.answer()


@router.callback_query(lambda c: c.data == 'skip_time')
async def cb_skip_time(c: CallbackQuery, state: FSMContext):
    """Skip time editing and proceed to update meeting."""
    data = await state.get_data()
    meeting_id = data.get('edit_meeting_id')
    topic = data.get('new_topic') or data.get('current_topic', '')
    date_str = data.get('new_date') or data.get('current_date')
    
    if not (meeting_id and topic and date_str):
        await _safe_edit_or_fallback(c, "Data edit tidak lengkap. Mulai lagi.")
        await state.clear()
        return

    # Use current time if time was skipped, otherwise use the stored current_time
    time_obj = data.get('current_time')
    if not time_obj:
        time_obj = datetime.now().time()
    
    # Combine date and time into ISO with WIB timezone
    d = datetime.fromisoformat(date_str)
    dt = datetime.combine(d.date(), time_obj)
    tz = timezone(timedelta(hours=7))
    dt = dt.replace(tzinfo=tz)
    start_time_iso = dt.isoformat()

    await _safe_edit_or_fallback(c, "Memperbarui meeting... Mohon tunggu.")
    try:
        # Call Zoom API to update
        resp = await zoom_client.update_meeting(meeting_id, topic=topic, start_time=start_time_iso)
        # Update local DB
        await update_meeting_details(meeting_id, topic=topic, start_time=start_time_iso)
        # Auto-return to meeting list
        await cb_list_meetings(c)
    except Exception as e:
        logger.exception("Failed to update meeting %s: %s", meeting_id, e)
        await _safe_edit_or_fallback(c, f"❌ Gagal memperbarui meeting: {e}")

    await state.clear()
    await c.answer()


@router.callback_query(lambda c: c.data and c.data.startswith('toggle_record:'), ZoomManageStates.controlling_meeting)
async def cb_toggle_record(c: CallbackQuery, state: FSMContext):
    meeting_id = c.data.split(':', 1)[1]
    
    # Get current recording status from database
    current_status = await get_meeting_recording_status(meeting_id)
    if current_status is None:
        current_status = 'stopped'
    
    # Get meeting data from FSM state
    data = await state.get_data()
    topic = data.get('topic', 'Unknown Meeting')
    agent_id = data.get('agent_id')
    
    # Toggle recording status
    if current_status == 'stopped':
        new_status = 'recording'
        status_text = "🔴 Recording started"
        action = "start-record"
    elif current_status == 'recording':
        new_status = 'stopped'
        status_text = "⏹️ Recording stopped"
        action = "stop-record"
    else:  # paused
        new_status = 'recording'
        status_text = "▶️ Recording resumed"
        action = "resume-record"
    
    # Send hotkey command to agent if agent_id is available
    if agent_id:
        try:
            payload = json.dumps({})  # Empty payload since action is now in the action field
            await add_command(agent_id, action, payload)
            logger.info("Sent %s command to agent %s for meeting %s", action, agent_id, meeting_id)
        except Exception as e:
            logger.error("Failed to send command to agent %s: %s", agent_id, e)
            # Continue with database update even if command fails
    
    # Update database
    await update_meeting_recording_status(meeting_id, new_status)
    
    # Refresh the control interface
    await cb_control_meeting(c, state)


@router.callback_query(lambda c: c.data and c.data.startswith('pause_record:'), ZoomManageStates.controlling_meeting)
async def cb_pause_record(c: CallbackQuery, state: FSMContext):
    meeting_id = c.data.split(':', 1)[1]
    
    # Get current recording status from database
    current_status = await get_meeting_recording_status(meeting_id)
    if current_status is None:
        current_status = 'stopped'
    
    # Get meeting data from FSM state
    data = await state.get_data()
    topic = data.get('topic', 'Unknown Meeting')
    agent_id = data.get('agent_id')
    
    # Check if recording is active
    if current_status == 'stopped':
        text = (
            f"🎥 <b>Meeting Control</b>\n\n"
            f"Meeting: <b>{topic}</b>\n\n"
            "⚠️ Rekaman belum aktif. Gunakan Start/Stop Recording terlebih dahulu."
        )
        
        kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🛑 Stop Meeting", callback_data=f"stop_meeting:{meeting_id}")],
            [InlineKeyboardButton(text="⏺️ Start Recording", callback_data=f"toggle_record:{meeting_id}")],
            [InlineKeyboardButton(text="🏠 Kembali ke Manage", callback_data=f"manage_meeting:{meeting_id}")]
        ])
        
        await _safe_edit_or_fallback(c, text, reply_markup=kb, parse_mode="HTML")
        await c.answer()
        return
    
    # Toggle pause status
    if current_status == 'recording':
        new_status = 'paused'
        status_text = "⏸️ Recording paused"
        action = "pause-record"
    else:  # paused
        new_status = 'recording'
        status_text = "▶️ Recording resumed"
        action = "resume-record"
    
    # Send hotkey command to agent if agent_id is available
    if agent_id:
        try:
            payload = json.dumps({})  # Empty payload since action is now in the action field
            await add_command(agent_id, action, payload)
            logger.info("Sent %s command to agent %s for meeting %s", action, agent_id, meeting_id)
        except Exception as e:
            logger.error("Failed to send command to agent %s: %s", agent_id, e)
            # Continue with database update even if command fails
    
    # Update database
    await update_meeting_recording_status(meeting_id, new_status)
    
    # Refresh the control interface
    await cb_control_meeting(c, state)



@router.message(Command("help"))
async def cmd_help(msg: Message):
    """Show available commands and features."""
    if msg.from_user is None:
        await msg.reply("Informasi pengguna tidak tersedia")
        return

    user = await get_user_by_telegram_id(msg.from_user.id)
    is_admin = user and is_allowed_to_create(user)

    help_text = (
        "🤖 <b>Bot Telegram ZOOM - Bantuan</b>\n\n"
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
            "<code>/all_users</code> - Lihat semua user dengan pagination\n"
            "<code>/agents</code> - Kelola agent (reinstall, remove, refresh status)\n"
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
        help_text += "🔹 <b>Manajemen User:</b> Admin dapat menyetujui, menolak, mengubah role/status, atau menghapus user\n"
        help_text += "🔹 <b>Manajemen Agent:</b> Admin dapat menambahkan, melihat, dan mengelola agent untuk remote control\n\n"
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
        "🤖 <b>Bot Telegram ZOOM</b>\n\n"
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
                text += f"<b>{i}. Zoom Meeting {topic}</b>\n\n<pre>{greeting} Bapak/Ibu/Rekan-rekan\nBerikut disampaikan Kegiatan {topic} pada:\n\n📆  {disp_date}\n⏰  {disp_time} WIB – selesai\n🔗  {join_url}\n\nDemikian disampaikan, terimakasih.</pre>"
                
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
        
        await msg.reply(text, reply_markup=kb, parse_mode="HTML")
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
                f"Username Telegram : <code>{msg.from_user.username or '-'}</code>\n"
                f"User ID Telegram : <code>{msg.from_user.id}</code>\n"
            )
            await msg.reply(text, parse_mode="HTML")
            return

    if is_allowed_to_create(user):
        # Personalized greeting with username
        username = msg.from_user.username or msg.from_user.first_name or "Pengguna"
        role = (user.get('role', 'user') if user else 'user').capitalize()
        greeting_text = (
            f"🤖 <b>ZOOM TELEBOT SOC</b>\n\n"
            f"👋 Halo, <b>{username}</b>!\n"
            f"🎭 Role Anda: <b>{role}</b>\n\n"
            "Selamat datang di <b>Bot Telegram ZOOM</b> untuk manajemen rapat Zoom.\n\n"
            "Pilih kategori menu di bawah ini untuk mengakses fitur yang tersedia:"
        )

        # Get main menu keyboard based on user role
        kb = main_menu_keyboard(user.get('role', 'user'))

        await msg.answer(greeting_text, reply_markup=kb, parse_mode="HTML")
    elif user and user.get('status') == 'banned':
        await msg.reply("<i>Anda dibanned dari menggunakan bot ini.</i>", parse_mode="HTML")
    else:
        await msg.reply("<i>Permintaan Anda sedang menunggu persetujuan.</i>", parse_mode="HTML")


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
        except TelegramBadRequest as e:
            # If message content identical, avoid sending a new message
            if 'message is not modified' in str(e).lower():
                try:
                    await c.answer("Status sudah up-to-date")
                except Exception:
                    pass
                return
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
    await _safe_edit_or_fallback(c, "<b>Buat Meeting - Step 1/3</b>\n<i>Silakan kirim Topic Meeting:</i>", parse_mode="HTML")
    await state.set_state(MeetingStates.topic)
    await c.answer()


@router.message(MeetingStates.topic)
async def meeting_topic(msg: Message, state: FSMContext):
    if not msg.text:
        await msg.reply("Silakan kirim topik meeting sebagai teks.")
        return

    logger.debug("meeting_topic received: %s", msg.text)
    await state.update_data(topic=msg.text.strip())
    await msg.reply("<b>Step 2/3</b>\n<i>Kapan diadakan?</i>\nFormat: <code>DD-MM-YYYY</code> atau '<code>31-12-2025</code>' atau tulis seperti '<code>31 Desember 2025</code>' (Bulan dalam bahasa Indonesia).", parse_mode="HTML")
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
    await msg.reply("<b>Step 3/3</b>\n<i>Masukkan waktu (format 24-jam WIB) contohnya:</i> <code>14:30</code>", parse_mode="HTML")
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
        "<b>Konfirmasi pembuatan meeting:</b>\n"
        f"📃 <b>Topik:</b> {topic}\n"
        f"⏰ <b>Waktu (WIB):</b> {disp}\n\n"
        "Tekan <b>Konfirmasi</b> untuk membuat meeting di Zoom, atau <b>Batal</b> untuk membatalkan."
    )
    # reply with keyboard and set confirm state
    await msg.reply(text, reply_markup=kb, parse_mode="HTML")
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
    await _safe_edit_or_fallback(c, "<b>Membuat meeting... Mohon tunggu.</b>", parse_mode="HTML")

    # create meeting via Zoom API
    user_id = 'me'  # default to 'me' if no specific user configured
    logger.debug("Creating meeting: chosen zoom user_id=%s (zoom_account_id=%s)", user_id, settings.zoom_account_id)
    try:
        meeting = await zoom_client.create_meeting(user_id=str(user_id), topic=topic, start_time=start_time_iso)
        logger.info("Meeting created: %s", meeting.get('id') or meeting)
    except Exception as e:
        logger.exception("Failed to create meeting: %s", e)
        await _safe_edit_or_fallback(c, f"<b>❌ Gagal membuat meeting:</b> {e}", parse_mode="HTML")
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
    await _safe_edit_or_fallback(c, "<b>❌ Pembuatan meeting dibatalkan.</b>", reply_markup=kb, parse_mode="HTML")
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
        
        # Build an inline keyboard with control buttons per meeting
        kb_rows = []
        for m_rec in meetings:
            mid = m_rec.get('zoom_meeting_id') or ''
            topic_short = (m_rec.get('topic') or 'No Topic')[:25]
            if mid:
                # Create row with 3 control buttons for each meeting
                kb_rows.append([
                    InlineKeyboardButton(text=f"🎥 {topic_short}", callback_data=f"control_zoom:{mid}"),
                    InlineKeyboardButton(text="✏️ Edit", callback_data=f"edit_meeting:{mid}"),
                    InlineKeyboardButton(text="🗑️ Delete", callback_data=f"confirm_delete:{mid}")
                ])

        # add navigation / back buttons
        kb_rows.append([InlineKeyboardButton(text="🔄 Refresh", callback_data="list_meetings"), InlineKeyboardButton(text="🏠 Kembali ke Menu Utama", callback_data="back_to_main")])
        kb = InlineKeyboardMarkup(inline_keyboard=kb_rows)

        # Try to edit the message directly for refresh, if fails, don't send new message
        from aiogram.types import Message as AiMessage
        m = getattr(c, 'message', None)
        if isinstance(m, AiMessage):
            try:
                await m.edit_text(text, parse_mode="HTML", reply_markup=kb)
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


@router.callback_query(lambda c: c.data == 'search_user')
async def cb_search_user(c: CallbackQuery, state: FSMContext):
    """Handle user search button."""
    if c.from_user is None:
        await c.answer("Informasi pengguna tidak tersedia")
        return

    user = await get_user_by_telegram_id(c.from_user.id)
    if not is_owner_or_admin(user):
        await c.answer("Anda tidak diizinkan untuk mencari user.", show_alert=True)
        return

    await c.answer()
    text = """🔎 <b>Pencarian User</b>
Silakan masukkan username atau Telegram ID yang ingin Anda cari:"""
    await _safe_edit_or_fallback(c, text, parse_mode="HTML")
    await state.set_state(UserSearchStates.waiting_for_query)


@router.message(UserSearchStates.waiting_for_query)
async def process_user_search_query(msg: Message, state: FSMContext):
    """Process the user's search query and return results."""
    if not msg.text:
        await msg.reply("Mohon masukkan query pencarian.")
        return

    query = msg.text.strip()
    await state.clear()

    # Search for users
    users = await search_users(query)
    if not users:
        text = f"❌ **Tidak ada hasil** untuk pencarian: `{escape_md(query)}`"
        await msg.reply(text, reply_markup=back_to_main_new_buttons(), parse_mode="MarkdownV2")
        return

    # Limit to 10 users to prevent message too long
    users = users[:10]
    if len(users) == 10:
        # Check if there are more
        all_users = await search_users(query)
        if len(all_users) > 10:
            text = f"✅ **Hasil Pencarian untuk:** `{escape_md(query)}` \\(Menampilkan 10 hasil pertama dari {len(all_users)} total\\)\n\n"
        else:
            text = f"✅ **Hasil Pencarian untuk:** `{escape_md(query)}`\n\n"
    else:
        text = f"✅ **Hasil Pencarian untuk:** `{escape_md(query)}`\n\n"
    buttons = []
    for u in users:
        username = u.get('username') or f"ID_{u.get('telegram_id')}"
        role = u.get('role', 'guest')
        status = u.get('status', 'pending')
        telegram_id = u.get('telegram_id')
        text += f"👤 @{escape_md(username)}\n"
        text += f"   ├─ ID: `{escape_md(str(telegram_id))}`\n"
        text += f"   ├─ Role: {escape_md(role.capitalize())}\n"
        text += f"   └─ Status: {escape_md(status.capitalize())}\n\n"
        buttons.append([
            InlineKeyboardButton(
                text=f"⚙️ Kelola @{username}",
                callback_data=f"manage_user:{telegram_id}"
            )
        ])

    buttons.append([InlineKeyboardButton(text="🏠 Kembali ke Menu Utama", callback_data="back_to_main_new")])
    keyboard = InlineKeyboardMarkup(inline_keyboard=buttons)

    await msg.reply(text, reply_markup=keyboard, parse_mode="MarkdownV2")

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
    text = "<b>🔗 Short URL Generator - Step 1/4</b>\n\nKirim URL yang ingin Anda persingkat:\n(contoh: https://example.com)"
    await _safe_edit_or_fallback(c, text, parse_mode="HTML")
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
        text = f"<b>🔗 Short URL Generator - Step 3/4</b>\n\nURL: <code>{url}</code>\nProvider: {provider_config.get('name', provider)}\n\nApakah Anda ingin menggunakan custom URL?"
        await _safe_edit_or_fallback(c, text, reply_markup=shortener_custom_choice_buttons(), parse_mode="HTML")
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
        await c.answer(f'❌ Gagal membuat short URL: {e}', show_alert=True)


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
        
        await c.answer(f'❌ Gagal membuat short URL: {e}', show_alert=True)
        return

    # append short url to message and remove button
    m = getattr(c, 'message', None)
    m_text = getattr(m, 'text', None) if m is not None else None
    if isinstance(m_text, str):
        new_text = (m_text or '') + f"\n\n🔗 <b>Short URL ({provider}):</b> {short}"
        await _safe_edit_or_fallback(c, new_text, parse_mode="HTML")
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
    
    await _safe_edit_or_fallback(c, "<b>❌ Pembuatan Short URL dibatalkan.</b>", parse_mode="HTML")
    await c.answer()


@router.message(Command("zoom_del", "meet_del"))
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


# ----------------------------------------------------------------
# --- KODE BARU UNTUK /ALL_USER DITAMBAHKAN DI SINI ---
# ----------------------------------------------------------------

async def build_all_users_message(page: int = 0):
    """
    Helper function untuk membuat teks dan keyboard untuk /all_users.
    """
    USERS_PER_PAGE = 5
    
    # 1. Ambil semua user dan filter yang BUKAN 'pending'
    all_users = await list_all_users()
    users = [u for u in all_users if u.get('status') != 'pending']
    
    # 2. Hitung statistik
    total_users = len(users)
    total_aktif = sum(1 for u in users if u.get('status') == 'whitelisted')
    total_banned = sum(1 for u in users if u.get('status') == 'banned')
    
    # 3. Pengaturan Halaman (Pagination)
    # math.ceil(total_users / USERS_PER_PAGE)
    total_pages = max(1, (total_users + USERS_PER_PAGE - 1) // USERS_PER_PAGE)
    # Konversi dari 0-based index (page) ke 1-based index (current_page)
    current_page = page + 1
    
    start_index = page * USERS_PER_PAGE
    end_index = start_index + USERS_PER_PAGE
    users_on_page = users[start_index:end_index]
    
    # 4. Buat Teks Pesan
    text = f"👥 Daftar Semua User\n"
    text += f"🟢 Total user Aktif: {total_aktif}\n"
    text += f"⛔ Total User di banned: {total_banned}\n"
    text += f"📊 Total user: {total_users}\n"
    
    buttons = []
    
    if not users_on_page:
        text += "\nBelum ada user (selain pending) yang terdaftar."
    
    # 5. Buat daftar user untuk halaman ini
    for u in users_on_page:
        username = u.get('username') or f"ID_{u.get('telegram_id')}"
        role = u.get('role', 'guest')
        telegram_id = u.get('telegram_id')
        
        text += f"\n✅ @{username}\n"
        text += f"   ├ Role: {role}\n"
        text += f"   └ ID: {telegram_id}\n"
        
        # Tambahkan tombol kelola untuk user ini
        buttons.append([
            InlineKeyboardButton(
                text=f"⚙️ Kelola @{username}",
                # Asumsi Anda memiliki handler untuk "manage_user:<id>"
                callback_data=f"manage_user:{telegram_id}"
            )
        ])
        
    # 6. Buat Tombol Navigasi
    nav_row = []
    
    # Tombol Back (◀️)
    # Nonaktif jika di halaman pertama (page 0)
    nav_row.append(
        InlineKeyboardButton(
            text="◀️",
            callback_data=f"all_users:{page - 1}" if page > 0 else "noop"
        )
    )
    
    # Tombol Halaman (📄) - 'noop' berarti tidak melakukan apa-apa saat diklik
    nav_row.append(
        InlineKeyboardButton(
            text=f"📄 {current_page}/{total_pages}",
            callback_data="noop" # Atau ganti dengan logika 'pilih halaman' jika ada
        )
    )
    
    # Tombol Next (▶️)
    # Nonaktif jika di halaman terakhir
    nav_row.append(
        InlineKeyboardButton(
            text="▶️",
            callback_data=f"all_users:{page + 1}" if current_page < total_pages else "noop"
        )
    )
    buttons.append(nav_row)
    
    # 7. Tombol Kembali ke Menu
    buttons.append([
        InlineKeyboardButton(
            text="🏠 Kembali ke Menu Utama",
            callback_data="back_to_main" # Menggunakan callback 'back_to_main' yang sudah ada
        )
    ])
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=buttons)
    
    return text, keyboard

@router.message(Command("all_user", "all_users"))
async def cmd_all_user(msg: Message):
    """
    Handler untuk command /all_user.
    Menampilkan daftar semua user yang tidak 'pending' dengan paginasi.
    """
    if msg.from_user is None:
        return

    # Periksa apakah user adalah admin atau owner
    user = await get_user_by_telegram_id(msg.from_user.id)
    if not is_owner_or_admin(user):
        await msg.reply("Anda tidak memiliki izin untuk menggunakan perintah ini.")
        return
        
    # Buat pesan untuk halaman pertama (page 0)
    try:
        text, keyboard = await build_all_users_message(page=0)
        await msg.reply(text, reply_markup=keyboard, parse_mode="HTML") # Menggunakan HTML agar emoji render
    except Exception as e:
        logger.exception("Failed to build /all_users list: %s", e)
        await msg.reply(f"Terjadi kesalahan saat mengambil daftar user: {e}")

@router.callback_query(lambda c: c.data and c.data.startswith('all_users:'))
async def cb_all_users(c: CallbackQuery):
    """
    Callback handler untuk paginasi /all_users.
    """
    if c.from_user is None:
        await c.answer("Informasi user tidak ditemukan.")
        return

    # Periksa izin
    user = await get_user_by_telegram_id(c.from_user.id)
    if not is_owner_or_admin(user):
        await c.answer("Anda tidak memiliki izin.", show_alert=True)
        return
        
    # Ambil nomor halaman (page index) dari callback data
    try:
        page = int(c.data.split(':')[1])
    except (IndexError, ValueError):
        await c.answer("Halaman tidak valid.", show_alert=True)
        return
        
    # Buat ulang pesan untuk halaman yang diminta
    try:
        text, keyboard = await build_all_users_message(page=page)
        
        # Gunakan _safe_edit_or_fallback untuk mengedit pesan
        await _safe_edit_or_fallback(c, text, reply_markup=keyboard, parse_mode="HTML")
        await c.answer() # Menjawab callback (menghilangkan loading)
    except Exception as e:
        logger.exception("Failed to update /all_users page: %s", e)
        await c.answer("Gagal memuat halaman.", show_alert=True)

async def _show_manage_user_screen(c: CallbackQuery, managed_user_id: int):
    """Menampilkan layar manajemen untuk user tertentu."""
    managed_user = await get_user_by_telegram_id(managed_user_id)
    if not managed_user:
        await c.answer("User tidak ditemukan.", show_alert=True)
        return
        
    username = html.escape(managed_user.get('username') or f"ID_{managed_user_id}")
    role = html.escape(managed_user.get('role', 'guest').capitalize())
    status = html.escape(managed_user.get('status', 'pending').capitalize())
    
    text = f"👤 <b>Kelola User: @{username}</b>\n\n"
    text += f"<b>ID:</b> <code>{managed_user_id}</code>\n"
    text += f"<b>Role:</b> {role}\n"
    text += f"<b>Status:</b> {status}\n\n"
    text += "Pilih tindakan yang ingin Anda lakukan:"
    
    keyboard = manage_users_buttons(managed_user_id)
    await _safe_edit_or_fallback(c, text, reply_markup=keyboard, parse_mode="HTML")

@router.callback_query(lambda c: c.data and c.data.startswith('manage_user:'))
async def cb_manage_user(c: CallbackQuery):
    """
    Menampilkan informasi detail seorang user dan tombol-tombol manajemen.
    """
    if c.from_user is None:
        await c.answer("Informasi user tidak ditemukan.")
        return

    # Periksa izin
    user = await get_user_by_telegram_id(c.from_user.id)
    if not is_owner_or_admin(user):
        await c.answer("Anda tidak memiliki izin.", show_alert=True)
        return
        
    # Ambil ID user yang akan dikelola dari callback data
    try:
        managed_user_id = int(c.data.split(':')[1])
    except (IndexError, ValueError):
        await c.answer("ID user tidak valid.", show_alert=True)
        return
        
    await _show_manage_user_screen(c, managed_user_id)
    await c.answer()

@router.callback_query(lambda c: c.data and c.data.startswith('delete_user:'))
async def cb_delete_user(c: CallbackQuery):
    """
    Menampilkan konfirmasi sebelum menghapus user.
    """
    if c.from_user is None:
        await c.answer("Informasi user tidak ditemukan.")
        return

    # Periksa izin
    user = await get_user_by_telegram_id(c.from_user.id)
    if not is_owner_or_admin(user):
        await c.answer("Anda tidak memiliki izin.", show_alert=True)
        return
        
    # Ambil ID user yang akan dihapus
    try:
        managed_user_id = int(c.data.split(':')[1])
    except (IndexError, ValueError):
        await c.answer("ID user tidak valid.", show_alert=True)
        return

    # Jangan biarkan admin menghapus dirinya sendiri
    if managed_user_id == c.from_user.id:
        await c.answer("Anda tidak dapat menghapus diri sendiri.", show_alert=True)
        return

    # Ambil info user untuk pesan konfirmasi
    managed_user = await get_user_by_telegram_id(managed_user_id)
    if not managed_user:
        await c.answer("User tidak ditemukan.", show_alert=True)
        return

    username = html.escape(managed_user.get('username') or f"ID_{managed_user_id}")

    text = f"⚠️ <b>Peringatan</b> ⚠️\n\nApakah Anda benar-benar yakin ingin menghapus user <b>@{username}</b>? Tindakan ini tidak dapat dibatalkan."
    
    # Buat tombol konfirmasi
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="✅ Ya, Hapus", callback_data=f"confirm_delete:{managed_user_id}"),
            InlineKeyboardButton(text="❌ Tidak, Batal", callback_data=f"manage_user:{managed_user_id}")
        ]
    ])
    
    await _safe_edit_or_fallback(c, text, reply_markup=keyboard, parse_mode="HTML")
    await c.answer()


@router.callback_query(lambda c: c.data and c.data.startswith('confirm_delete:'))
async def cb_confirm_delete(c: CallbackQuery):
    """
    Menghapus user setelah konfirmasi.
    """
    if c.from_user is None:
        await c.answer("Informasi user tidak ditemukan.")
        return

    # Periksa izin
    user = await get_user_by_telegram_id(c.from_user.id)
    if not is_owner_or_admin(user):
        await c.answer("Anda tidak memiliki izin.", show_alert=True)
        return
        
    # Ambil ID user yang akan dihapus
    try:
        managed_user_id = int(c.data.split(':')[1])
    except (IndexError, ValueError):
        await c.answer("ID user tidak valid.", show_alert=True)
        return

    # Hapus user
    await delete_user(managed_user_id)
    await c.answer("✅ User berhasil dihapus!", show_alert=True)
    
    # Refresh daftar user ke halaman pertama
    try:
        text, keyboard = await build_all_users_message(page=0)
        await _safe_edit_or_fallback(c, text, reply_markup=keyboard, parse_mode="HTML")
    except Exception as e:
        logger.exception("Gagal me-refresh daftar user setelah penghapusan: %s", e)
        await _safe_edit_or_fallback(c, "Gagal me-refresh daftar user.")


@router.callback_query(lambda c: c.data and c.data.startswith('change_role:'))
async def cb_change_role(c: CallbackQuery):
    """
    Menampilkan pilihan role untuk user.
    """
    if c.from_user is None:
        await c.answer("Informasi user tidak ditemukan.")
        return

    # Periksa izin
    user = await get_user_by_telegram_id(c.from_user.id)
    if not is_owner_or_admin(user):
        await c.answer("Anda tidak memiliki izin.", show_alert=True)
        return
        
    # Ambil ID user
    try:
        managed_user_id = int(c.data.split(':')[1])
    except (IndexError, ValueError):
        await c.answer("ID user tidak valid.", show_alert=True)
        return
        
    text = "Pilih role baru untuk user:"
    keyboard = role_selection_buttons(managed_user_id)
    await _safe_edit_or_fallback(c, text, reply_markup=keyboard)
    await c.answer()


@router.callback_query(lambda c: c.data and c.data.startswith('set_role:'))
async def cb_set_role(c: CallbackQuery):
    """
    Mengatur role baru untuk user.
    """
    if c.from_user is None:
        await c.answer("Informasi user tidak ditemukan.")
        return

    # Periksa izin
    user = await get_user_by_telegram_id(c.from_user.id)
    if not is_owner_or_admin(user):
        await c.answer("Anda tidak memiliki izin.", show_alert=True)
        return
        
    # Ambil ID user dan role baru
    try:
        _, managed_user_id_str, new_role = c.data.split(':')
        managed_user_id = int(managed_user_id_str)
    except (IndexError, ValueError):
        await c.answer("Data callback tidak valid.", show_alert=True)
        return

    # Ambil data user untuk mendapatkan status saat ini
    managed_user = await get_user_by_telegram_id(managed_user_id)
    if not managed_user:
        await c.answer("User tidak ditemukan untuk pembaruan.", show_alert=True)
        return

    current_status = managed_user.get('status')

    # Update role dengan menyertakan status yang ada
    await update_user_status(managed_user_id, current_status, new_role)
    await c.answer(f"✅ Role berhasil diubah menjadi {new_role.capitalize()}!", show_alert=True)
    
    # Kembali ke menu manage_user
    await _show_manage_user_screen(c, managed_user_id)


@router.callback_query(lambda c: c.data and c.data.startswith('change_status:'))
async def cb_change_status(c: CallbackQuery):
    """
    Menampilkan pilihan status untuk user.
    """
    if c.from_user is None:
        await c.answer("Informasi user tidak ditemukan.")
        return

    # Periksa izin
    user = await get_user_by_telegram_id(c.from_user.id)
    if not is_owner_or_admin(user):
        await c.answer("Anda tidak memiliki izin.", show_alert=True)
        return
        
    # Ambil ID user
    try:
        managed_user_id = int(c.data.split(':')[1])
    except (IndexError, ValueError):
        await c.answer("ID user tidak valid.", show_alert=True)
        return
        
    text = "Pilih status baru untuk user:"
    keyboard = status_selection_buttons(managed_user_id)
    await _safe_edit_or_fallback(c, text, reply_markup=keyboard)
    await c.answer()


@router.callback_query(lambda c: c.data and c.data.startswith('set_status:'))
async def cb_set_status(c: CallbackQuery):
    """
    Mengatur status baru untuk user.
    """
    if c.from_user is None:
        await c.answer("Informasi user tidak ditemukan.")
        return

    # Periksa izin
    user = await get_user_by_telegram_id(c.from_user.id)
    if not is_owner_or_admin(user):
        await c.answer("Anda tidak memiliki izin.", show_alert=True)
        return
        
    # Ambil ID user dan status baru
    try:
        _, managed_user_id_str, new_status = c.data.split(':')
        managed_user_id = int(managed_user_id_str)
    except (IndexError, ValueError):
        await c.answer("Data callback tidak valid.", show_alert=True)
        return

    # Ambil data user untuk mendapatkan role saat ini
    managed_user = await get_user_by_telegram_id(managed_user_id)
    if not managed_user:
        await c.answer("User tidak ditemukan untuk pembaruan.", show_alert=True)
        return

    current_role = managed_user.get('role')

    # Update status dengan menyertakan role yang ada
    await update_user_status(managed_user_id, new_status, current_role)
    await c.answer(f"✅ Status berhasil diubah menjadi {new_status.capitalize()}!", show_alert=True)
    
    # Kembali ke menu manage_user
    await _show_manage_user_screen(c, managed_user_id)


@router.callback_query(lambda c: c.data and c.data.startswith('cancel_change:'))
async def cb_cancel_change(c: CallbackQuery):
    """
    Membatalkan aksi perubahan role/status dan kembali ke menu manage_user.
    """
    if c.from_user is None:
        await c.answer("Informasi user tidak ditemukan.")
        return
        
    try:
        managed_user_id = int(c.data.split(':')[1])
    except (IndexError, ValueError):
        await c.answer("ID user tidak valid.", show_alert=True)
        return

    await c.answer("Dibatalkan.")
    await _show_manage_user_screen(c, managed_user_id)


# ----------------------------------------------------------------
# --- AKHIR DARI FUNGSI manage_user Markdown ---
# ----------------------------------------------------------------

# ----------------------------------------------------------------
# --- KODE BARU UNTUK /REGISTER_LIST DITAMBAHKAN DI SINI ---
# ----------------------------------------------------------------
@router.message(Command("register_list", "register_lists"))
async def cmd_register_list(msg: Message):
    """
    Handler for the /register_list command.
    Displays a list of users with 'pending' status for registration.
    """
    if msg.from_user is None:
        return

    # Check if the user is an admin or owner
    user = await get_user_by_telegram_id(msg.from_user.id)
    if not is_owner_or_admin(user):
        await msg.reply("Anda tidak memiliki izin untuk menggunakan perintah ini.")
        return

    # Get all users with 'pending' status
    pending_users = await list_pending_users()

    if not pending_users:
        await msg.reply("Tidak ada user yang menunggu pendaftaran.")
        return

    await msg.reply(f"Menampilkan {len(pending_users)} user yang menunggu pendaftaran:")

    # Display the list of users who are registering
    for user_to_approve in pending_users:
        user_id = user_to_approve.get('telegram_id')
        username = user_to_approve.get('username', 'Unknown')
        role = user_to_approve.get('role', 'guest').capitalize()

        
        # user_list_text = f"- Username: @{username}\n- ID: `{user_id}`"
        user_list_text = f"👤 <b>Username:</b> @{username}\n"
        user_list_text += f"    ├ <b>Role:</b> <code>{role}</code>\n"
        user_list_text += f"    └ <b>ID:</b> <code>{user_id}</code>\n"

        # Use pending_user_buttons from keyboards.py
        keyboard = pending_user_buttons(user_id)
        
        await msg.answer(user_list_text, reply_markup=keyboard, parse_mode="HTML")


@router.callback_query(F.data.startswith("accept:"))
async def cb_accept_user(c: CallbackQuery, bot: Bot):
    """
    Accepts a user, changing their status to 'whitelisted' and role to 'user'.
    """
    if c.from_user is None:
        return

    admin_user = await get_user_by_telegram_id(c.from_user.id)
    if not is_owner_or_admin(admin_user):
        await c.answer("Anda tidak memiliki izin untuk melakukan tindakan ini.", show_alert=True)
        return

    try:
        user_id_to_accept = int(c.data.split(":")[1])
    except (IndexError, ValueError):
        await c.answer("Callback data tidak valid.", show_alert=True)
        return

    await update_user_status(user_id_to_accept, 'whitelisted', 'user')
    
    # Edit the original message to show the user is accepted
    if c.message and c.message.text:
        original_text = c.message.text
        admin_username = c.from_user.username or f"Admin ({c.from_user.id})"
        new_text = f"{original_text}\n\n✅ Diterima oleh @{admin_username}"
        await c.message.edit_text(new_text, reply_markup=None, parse_mode="HTML")

    await c.answer(f"User {user_id_to_accept} telah diterima.", show_alert=True)
    
    # Notify the user
    try:
        await bot.send_message(user_id_to_accept, "Selamat! Pendaftaran Anda telah diterima. Anda sekarang dapat menggunakan fitur bot.")
    except Exception as e:
        logger.error(f"Gagal mengirim notifikasi ke user {user_id_to_accept}: {e}")

@router.callback_query(F.data.startswith("reject:"))
async def cb_reject_user(c: CallbackQuery, bot: Bot):
    """
    Rejects a user by deleting them from the database.
    """
    if c.from_user is None:
        return

    admin_user = await get_user_by_telegram_id(c.from_user.id)
    if not is_owner_or_admin(admin_user):
        await c.answer("Anda tidak memiliki izin untuk melakukan tindakan ini.", show_alert=True)
        return

    try:
        user_id_to_reject = int(c.data.split(":")[1])
    except (IndexError, ValueError):
        await c.answer("Callback data tidak valid.", show_alert=True)
        return

    await delete_user(user_id_to_reject)

    if c.message and c.message.text:
        original_text = c.message.text
        admin_username = c.from_user.username or f"Admin ({c.from_user.id})"
        new_text = f"{original_text}\n\n❌ Ditolak oleh @{admin_username}"
        await c.message.edit_text(new_text, reply_markup=None, parse_mode="HTML")

    await c.answer(f"User {user_id_to_reject} telah ditolak dan dihapus.", show_alert=True)
    
    # Notify the user
    try:
        await bot.send_message(user_id_to_reject, "Mohon maaf, pendaftaran Anda ditolak.")
    except Exception as e:
        logger.error(f"Gagal mengirim notifikasi ke user {user_id_to_reject}: {e}")


@router.callback_query(F.data.startswith("ban:"))
async def cb_ban_user(c: CallbackQuery, bot: Bot):
    """
    Bans a user, changing their status to 'banned'.
    """
    if c.from_user is None:
        return

    admin_user = await get_user_by_telegram_id(c.from_user.id)
    if not is_owner_or_admin(admin_user):
        await c.answer("Anda tidak memiliki izin untuk melakukan tindakan ini.", show_alert=True)
        return

    try:
        user_id_to_ban = int(c.data.split(":")[1])
    except (IndexError, ValueError):
        await c.answer("Callback data tidak valid.", show_alert=True)
        return

    await update_user_status(user_id_to_ban, 'banned', 'guest')

    if c.message and c.message.text:
        original_text = c.message.text
        admin_username = c.from_user.username or f"Admin ({c.from_user.id})"
        new_text = f"{original_text}\n\n🚫 Dibanned oleh @{admin_username}"
        await c.message.edit_text(new_text, reply_markup=None, parse_mode="HTML")

    await c.answer(f"User {user_id_to_ban} telah dibanned.", show_alert=True)
    
    # Notify the user
    try:
        await bot.send_message(user_id_to_ban, "Anda telah dibanned dari bot ini.")
    except Exception as e:
        logger.error(f"Gagal mengirim notifikasi ke user {user_id_to_ban}: {e}")

# ===== MENU NAVIGATION HANDLERS =====

@router.callback_query(lambda c: c.data == 'menu_meetings')
async def cb_menu_meetings(c: CallbackQuery):
    """Show meetings management submenu."""
    if c.from_user is None:
        await c.answer("Informasi pengguna tidak tersedia")
        return

    user = await get_user_by_telegram_id(c.from_user.id)
    if not is_allowed_to_create(user):
        await c.answer("Anda belum diizinkan mengakses menu ini.")
        return

    text = "📅 <b>Manajemen Meeting</b>\n\nPilih aksi yang ingin dilakukan:"
    await _safe_edit_or_fallback(c, text, reply_markup=meetings_menu_keyboard(), parse_mode="HTML")
    await c.answer()


@router.callback_query(lambda c: c.data == 'menu_users')
async def cb_menu_users(c: CallbackQuery):
    """Show user management submenu (admin/owner only)."""
    if c.from_user is None:
        await c.answer("Informasi pengguna tidak tersedia")
        return

    user = await get_user_by_telegram_id(c.from_user.id)
    if not is_owner_or_admin(user):
        await c.answer("Menu ini hanya untuk Admin/Owner.")
        return

    text = "👥 <b>Manajemen User</b>\n\nKelola user dan permission:"
    await _safe_edit_or_fallback(c, text, reply_markup=users_menu_keyboard(), parse_mode="HTML")
    await c.answer()





@router.callback_query(lambda c: c.data == 'menu_backup')
async def cb_menu_backup(c: CallbackQuery):
    """Show backup and restore submenu (admin/owner only)."""
    if c.from_user is None:
        await c.answer("Informasi pengguna tidak tersedia")
        return

    user = await get_user_by_telegram_id(c.from_user.id)
    if not is_owner_or_admin(user):
        await c.answer("Menu ini hanya untuk Admin/Owner.")
        return

    text = "💾 <b>Backup & Restore</b>\n\nKelola backup database:"
    await _safe_edit_or_fallback(c, text, reply_markup=backup_menu_keyboard(), parse_mode="HTML")
    await c.answer()


@router.callback_query(lambda c: c.data == 'menu_shortener')
async def cb_menu_shortener(c: CallbackQuery):
    """Show URL shortener submenu."""
    if c.from_user is None:
        await c.answer("Informasi pengguna tidak tersedia")
        return

    user = await get_user_by_telegram_id(c.from_user.id)
    if not is_allowed_to_create(user):
        await c.answer("Anda belum diizinkan mengakses menu ini.")
        return

    text = "🔗 <b>URL Shortener</b>\n\nBuat short URL untuk link meeting:"
    await _safe_edit_or_fallback(c, text, reply_markup=shortener_menu_keyboard(), parse_mode="HTML")
    await c.answer()


@router.callback_query(lambda c: c.data == 'menu_info')
async def cb_menu_info(c: CallbackQuery):
    """Show information and help submenu."""
    if c.from_user is None:
        await c.answer("Informasi pengguna tidak tersedia")
        return

    text = "ℹ️ <b>Informasi & Bantuan</b>\n\nPilih informasi yang dibutuhkan:"
    await _safe_edit_or_fallback(c, text, reply_markup=info_menu_keyboard(), parse_mode="HTML")
    await c.answer()


@router.callback_query(lambda c: c.data == 'sync_meetings')
async def cb_sync_meetings(c: CallbackQuery):
    """Sync meetings from Zoom to database (owner only)."""
    if c.from_user is None:
        await c.answer("Informasi pengguna tidak tersedia")
        return

    # Only owner can run sync
    if settings.owner_id is None or c.from_user.id != settings.owner_id:
        await c.answer("Hanya owner yang dapat menjalankan sync meetings.")
        return

    await c.answer("🔄 Memulai sinkronisasi...")
    
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
        await _safe_edit_or_fallback(c, text, reply_markup=back_to_main_buttons(), parse_mode="HTML")
    except Exception as e:
        logger.exception("Manual sync failed: %s", e)
        await _safe_edit_or_fallback(c, f"❌ <b>Gagal melakukan sinkronisasi:</b> {e}", reply_markup=back_to_main_buttons(), parse_mode="HTML")


@router.callback_query(lambda c: c.data == 'check_expired')
async def cb_check_expired(c: CallbackQuery):
    """Check and update expired meetings (owner only)."""
    if c.from_user is None:
        await c.answer("Informasi pengguna tidak tersedia")
        return

    # Only owner can run expiry check
    if settings.owner_id is None or c.from_user.id != settings.owner_id:
        await c.answer("Hanya owner yang dapat menjalankan check expired meetings.")
        return

    await c.answer("🔍 Memeriksa meeting yang sudah expired...")

    try:
        stats = await update_expired_meetings()
        text = (
            "✅ <b>Pemeriksaan expired selesai!</b>\n\n"
            f"📊 <b>Statistik:</b>\n"
            f"⏰ Meeting ditandai expired: {stats['expired']}\n"
            f"❌ Error: {stats['errors']}\n\n"
            "<i>Meeting yang sudah lewat waktu mulai akan ditandai sebagai expired.</i>"
        )
        await _safe_edit_or_fallback(c, text, reply_markup=back_to_main_buttons(), parse_mode="HTML")
    except Exception as e:
        logger.exception("Manual expiry check failed: %s", e)
        await _safe_edit_or_fallback(c, f"❌ <b>Gagal memeriksa expired meetings:</b> {e}", reply_markup=back_to_main_buttons(), parse_mode="HTML")


@router.callback_query(lambda c: c.data == 'show_help')
async def cb_show_help(c: CallbackQuery):
    """Show help information."""
    help_text = """
❓ <b>BANTUAN - ZOOM TELEBOT SOC</b>

<b>📋 DAFTAR PERINTAH:</b>

<b>🔹 Meeting Management:</b>
• /meet - Buat meeting baru
• /sync_meetings - Sync dari Zoom
• /check_expired - Cek meeting expired

<b>🔹 User Management (Admin only):</b>
• /all_users - List semua user
• /register_list - List user pending

<b>🔹 Agent Management (Admin only):</b>
• /agents - List semua agent
• /all_users - Lihat semua user

<b>🔹 Utility:</b>
• /backup - Backup database
• /restore - Restore database
• /short - Shorten URL

<b>🔹 Info:</b>
• /help - Bantuan ini
• /about - Tentang bot
• /whoami - Info user Anda

<b>💡 TIPS:</b>
• Gunakan menu utama untuk navigasi mudah
• Semua fitur tersedia via inline keyboard
• Admin memiliki akses menu tambahan

<b>📞 Support:</b> Hubungi admin jika ada masalah.
"""
    await _safe_edit_or_fallback(c, help_text, reply_markup=back_to_main_buttons(), parse_mode="HTML")
    await c.answer()


@router.callback_query(lambda c: c.data == 'show_about')
async def cb_show_about(c: CallbackQuery):
    """Show about information."""
    about_text = """
ℹ️ <b>TENTANG ZOOM TELEBOT SOC</b>

<b>🤖 Bot Telegram untuk Zoom Meeting Management</b>

<b>🎯 Fitur Utama:</b>
• ✅ Manajemen meeting Zoom
• ✅ Sistem user role-based
• ✅ Remote control via agent
• ✅ URL shortener terintegrasi
• ✅ Backup & restore database
• ✅ Real-time sync dengan Zoom API

<b>👥 Role System:</b>
• 👑 <b>Owner</b> - Full access semua fitur
• 👨‍💼 <b>Admin</b> - Manajemen user & agent
• 👤 <b>User</b> - Meeting management
• 👤 <b>Guest</b> - Limited access

<b>🔧 Tech Stack:</b>
• Python 3.11+ dengan aiogram
• SQLite database dengan aiosqlite
• Zoom API Server-to-Server OAuth
• Docker containerization

<b>📊 Status:</b> Production Ready
<b>🛡️ Security:</b> Role-based access control

<i>Dikembangkan untuk Tim SOC - Security Operations Center</i>
"""
    await _safe_edit_or_fallback(c, about_text, reply_markup=back_to_main_buttons(), parse_mode="HTML")
    await c.answer()


@router.callback_query(lambda c: c.data == 'whoami')
async def cb_whoami(c: CallbackQuery):
    """Show user information: Telegram ID, Username, and Role."""
    if c.from_user is None:
        await c.answer("Informasi pengguna tidak tersedia")
        return

    # Get user info from database
    user = await get_user_by_telegram_id(c.from_user.id)
    
    telegram_id = c.from_user.id
    username = c.from_user.username or "Tidak ada username"
    role = (user.get('role', 'user') if user else 'user').capitalize() if user else 'Tidak terdaftar'
    
    info_text = f"""
👤 <b>INFORMASI AKUN ANDA</b>

🆔 <b>Telegram ID:</b> <code>{telegram_id}</code>
👤 <b>Username:</b> @{username}
🎭 <b>Role:</b> {role}

<i>Informasi ini bersifat pribadi dan hanya ditampilkan kepada Anda.</i>
"""
    
    await _safe_edit_or_fallback(c, info_text, reply_markup=back_to_main_buttons(), parse_mode="HTML")
    await c.answer()


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
            f"🤖 <b>ZOOM TELEBOT SOC</b>\n\n"
            f"👋 Halo, <b>{username}</b>!\n"
            f"🎭 Role Anda: <b>{role}</b>\n\n"
            "Selamat datang di <b>Bot Telegram ZOOM</b> untuk manajemen rapat Zoom.\n\n"
            "Pilih kategori menu di bawah ini untuk mengakses fitur yang tersedia:"
        )
        # Update the current message
        # Update the current message with main menu
        kb = main_menu_keyboard(user.get('role', 'user'))
        await _safe_edit_or_fallback(c, greeting_text, reply_markup=kb, parse_mode="HTML")
    elif user and user.get('status') == 'banned':
        await _safe_edit_or_fallback(c, "<i>Anda dibanned dari menggunakan bot ini.</i>", parse_mode="HTML")
    else:
        await _safe_edit_or_fallback(c, "<i>Permintaan Anda sedang menunggu persetujuan.</i>", parse_mode="HTML")


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
            "Selamat datang di <b>Bot Telegram ZOOM</b>. Saya di sini untuk membantu Anda mengelola rapat Zoom langsung dari Telegram.\n\n"
            "Saya bisa membantu untuk:\n"
            "🔹 Menjadwalkan rapat baru\n"
            "🔹 Mengelola user (khusus admin)\n"
            "🔹 Mendapatkan short URL untuk link meeting\n"
            "🔹 Melihat daftar user pending/aktif\n\n"
            "Untuk memulai, silakan klik tombol di bawah ini.\n\n"
            "Jika Anda butuh bantuan, kapan saja bisa ketik /help."
        )
        # Send a new message
        # Send a new message with main menu
        kb = main_menu_keyboard(user.get('role', 'user'))
        await c.message.reply(greeting_text, reply_markup=kb, parse_mode="HTML")
    elif user and user.get('status') == 'banned':
        await c.message.reply("<i>Anda dibanned dari menggunakan bot ini.</i>", parse_mode="HTML")
    else:
        await c.message.reply("<i>Permintaan Anda sedang menunggu persetujuan.</i>", parse_mode="HTML")


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
            "Selamat datang di <b>Bot Telegram ZOOM</b>. Saya di sini untuk membantu Anda mengelola rapat Zoom langsung dari Telegram.\n\n"
            "Saya bisa membantu untuk:\n"
            "🔹 Menjadwalkan rapat baru\n"
            "🔹 Mengelola user (khusus admin)\n"
            "🔹 Mendapatkan short URL untuk link meeting\n"
            "🔹 Melihat daftar user pending/aktif\n\n"
            "Untuk memulai, silakan klik tombol di bawah ini.\n\n"
            "Jika Anda butuh bantuan, kapan saja bisa ketik /help."
        )
        # Update the current message
        # Update the current message with main menu
        kb = main_menu_keyboard(user.get('role', 'user'))
        await _safe_edit_or_fallback(c, greeting_text, reply_markup=kb, parse_mode="HTML")
    elif user and user.get('status') == 'banned':
        await _safe_edit_or_fallback(c, "<i>Anda dibanned dari menggunakan bot ini.</i>", parse_mode="HTML")
    else:
        await _safe_edit_or_fallback(c, "<i>Permintaan Anda sedang menunggu persetujuan.</i>", parse_mode="HTML")


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
            "Selamat datang di <b>Bot Telegram ZOOM</b>. Saya di sini untuk membantu Anda mengelola rapat Zoom langsung dari Telegram.\n\n"
            "Saya bisa membantu untuk:\n"
            "🔹 Menjadwalkan rapat baru\n"
            "🔹 Mengelola user (khusus admin)\n"
            "🔹 Mendapatkan short URL untuk link meeting\n"
            "🔹 Melihat daftar user pending/aktif\n\n"
            "Untuk memulai, silakan klik tombol di bawah ini.\n\n"
            "Jika Anda butuh bantuan, kapan saja bisa ketik /help."
        )
        # Send a new message
        # Send a new message with main menu
        kb = main_menu_keyboard(user.get('role', 'user'))
        await c.message.reply(greeting_text, reply_markup=kb, parse_mode="HTML")
    elif user and user.get('status') == 'banned':
        await c.message.reply("<i>Anda dibanned dari menggunakan bot ini.</i>", parse_mode="HTML")
    else:
        await c.message.reply("<i>Permintaan Anda sedang menunggu persetujuan.</i>", parse_mode="HTML")


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

