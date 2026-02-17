# Cloud Recording Control Handlers
# These handlers use Zoom's live_meetings/events API for cloud recording control

from aiogram import Router
from aiogram.types import CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from zoom import zoom_client
from bot.auth import is_owner_or_admin, is_registered_user
from db import get_user_by_telegram_id, get_meeting_recording_status, update_meeting_recording_status, list_meetings, get_meeting_cloud_recording_data, update_meeting_cloud_recording_data
import logging
import logging
import asyncio
from bot.utils.loading import LoadingContext

logger = logging.getLogger(__name__)
router = Router()


async def _safe_edit_or_fallback(c: CallbackQuery, text: str, reply_markup=None, parse_mode=None) -> None:
    """Try to edit the original message. If that's not available, reply to the message or answer the callback."""
    from aiogram.types import Message as AiMessage
    from aiogram.exceptions import TelegramBadRequest
    
    m = getattr(c, 'message', None)
    
    if isinstance(m, AiMessage):
        kwargs = {'reply_markup': reply_markup}
        if parse_mode is not None:
            kwargs['parse_mode'] = parse_mode
        try:
            await m.edit_text(text, **kwargs)
            return
        except TelegramBadRequest:
            try:
                await m.reply(text, **kwargs)
                return
            except Exception:
                logger.debug("_edit_or_fallback: reply() failed, falling back to callback answer")
    
    try:
        await c.answer(text)
    except Exception:
        logger.debug("_safe_edit_or_fallback: c.answer() failed for callback with data=%s", getattr(c, 'data', None))


async def _refresh_control_zoom_ui(c: CallbackQuery, meeting_id: str) -> None:
    """Refresh the control zoom UI with updated recording status."""
    from config import settings
    
    try:
        # Get meeting details
        meetings = await list_meetings()
        meeting = next((m for m in meetings if m.get('zoom_meeting_id') == str(meeting_id)), None)
        if not meeting:
            logger.warning(f"Meeting {meeting_id} not found for refresh")
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
            meeting_settings = zoom_meeting_details.get('settings') or {}
            auto_recording_mode = (meeting_settings.get('auto_recording') or 'unknown').lower()
            if auto_recording_mode == 'cloud':
                recording_label = "Cloud (auto)"
            elif auto_recording_mode == 'local':
                recording_label = "Local (agent host)"
            else:
                recording_label = "Unknown"
        except Exception as e:
            logger.error(f"Failed to get Zoom meeting details: {e}")
            meeting_status = 'unknown'
            participant_count = 0
            start_url = ''
            join_url = ''
            recording_label = "Unknown"

        # Get recording status from DB only (Zoom API doesn't provide real-time recording status)
        current_recording_status = await get_meeting_recording_status(meeting_id) or 'stopped'
        logger.debug(f"Current recording status from DB: {current_recording_status}")

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
        
        # Create control buttons based on meeting status
        kb_rows = []

        if meeting_status == 'started':
            kb_rows.append([InlineKeyboardButton(text="⏹️ End Meeting", callback_data=f"end_zoom_meeting:{meeting_id}")])
            
            # Dynamic recording controls based on status
            if current_recording_status == 'stopped':
                # Show Start Recording only
                kb_rows.append([InlineKeyboardButton(text="⏺️ Start Recording", callback_data=f"cloud_start_record:{meeting_id}")])
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
            
            # Check if agent control enabled
            if settings.zoom_control_mode.lower() == "agent":
                kb_rows.append([InlineKeyboardButton(text="🔇 Mute All", callback_data=f"mute_all_participants:{meeting_id}")])
        else:
            # Cloud mode: expose start_url for one-click host launch when available
            if start_url:
                kb_rows.append([InlineKeyboardButton(text="🚀 Mulai sebagai Host", url=start_url)])
            # Fallback to API start if URL missing or user prefers inline action
            kb_rows.append([InlineKeyboardButton(text="▶️ Start Meeting", callback_data=f"start_zoom_meeting:{meeting_id}")])

        # Always available actions
        kb_rows.extend([
            [InlineKeyboardButton(text="☁️ View Cloud Recordings", callback_data=f"view_cloud_recordings:{meeting_id}")],
            [InlineKeyboardButton(text="🔄️ Refresh Status", callback_data=f"control_zoom:{meeting_id}")],
            [InlineKeyboardButton(text="📊 Meeting Details", callback_data=f"zoom_meeting_details:{meeting_id}")],
            [InlineKeyboardButton(text="⬅️ Kembali ke Daftar", callback_data="list_meetings")]
        ])

        kb = InlineKeyboardMarkup(inline_keyboard=kb_rows)
        await _safe_edit_or_fallback(c, text, reply_markup=kb)

    except Exception as e:
        logger.error(f"Failed to refresh control zoom UI: {e}")


@router.callback_query(lambda c: c.data and c.data.startswith('cloud_start_record:'))
async def cb_cloud_start_record(c: CallbackQuery):
    """Start cloud recording for a live meeting.
    
    Since we don't know the actual recording status on first open:
    - Send BOTH start AND resume payloads
    - If stopped → start succeeds, resume fails/ignored
    - If paused → resume succeeds, start fails/ignored
    - Either way we cover both cases
    """
    logger.debug("cb_cloud_start_record: Handler called")
    
    if c.from_user is None:
        logger.warning("cb_cloud_start_record: No user info")
        await c.answer("Informasi pengguna tidak tersedia")
        return

    logger.debug("cb_cloud_start_record: User ID %s", c.from_user.id)
    user = await get_user_by_telegram_id(c.from_user.id)
    logger.debug("cb_cloud_start_record: User data: %s", user)
    
    if not is_registered_user(user):
        logger.warning("cb_cloud_start_record: User not registered")
        await c.answer("Anda belum terdaftar atau dibanned.")
        return

    meeting_id = c.data.split(':', 1)[1]
    logger.debug("cb_cloud_start_record: Meeting ID extracted: %s", meeting_id)
    await c.answer("Memulai cloud recording...")

    try:
        # Show loading feedback
        loading_msg = await c.message.reply("⏳ Memulai cloud recording...")
        
        logger.debug("cb_cloud_start_record: Sending START payload")
        success_start = await zoom_client.control_live_meeting_recording(meeting_id, "start")
        logger.debug("cb_cloud_start_record: START returned success=%s", success_start)
        
        logger.debug("cb_cloud_start_record: Sending RESUME payload (in case paused)")
        success_resume = await zoom_client.control_live_meeting_recording(meeting_id, "resume")
        logger.debug("cb_cloud_start_record: RESUME returned success=%s", success_resume)
        
        # If either start or resume succeeded, consider it success
        success = success_start or success_resume
        logger.debug("cb_cloud_start_record: Overall result: start=%s, resume=%s, success=%s", 
                    success_start, success_resume, success)
        
        if success:
            logger.debug("cb_cloud_start_record: Updating DB status")
            # Update database status to recording
            await update_meeting_recording_status(meeting_id, 'recording')
            logger.debug("cb_cloud_start_record: DB updated, waiting for Zoom API to sync...")
            # Wait for Zoom API to update status
            await asyncio.sleep(1.5)
            logger.debug("cb_cloud_start_record: Refreshing UI")
            
            # Refresh control UI to show new buttons
            await _refresh_control_zoom_ui(c, meeting_id)
            logger.debug("cb_cloud_start_record: UI refreshed")
            
            # Delete loading message
            await loading_msg.delete()
            return
        else:
            text = "❌ <b>Gagal memulai cloud recording.</b> Pastikan meeting sedang berlangsung."
            logger.warning("cb_cloud_start_record: Both start and resume failed")
            await loading_msg.delete()

    except Exception as e:
        logger.exception("cb_cloud_start_record: Exception occurred")
        text = f"❌ Error: {str(e)}"

    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🎥 Kembali ke Kontrol", callback_data=f"control_zoom:{meeting_id}")],
        [InlineKeyboardButton(text="📋 Daftar Meeting", callback_data="list_meetings")]
    ])

    await _safe_edit_or_fallback(c, text, reply_markup=kb)


@router.callback_query(lambda c: c.data and c.data.startswith('cloud_stop_record:'))
async def cb_cloud_stop_record(c: CallbackQuery):
    """Stop cloud recording for a live meeting."""
    if c.from_user is None:
        await c.answer("Informasi pengguna tidak tersedia")
        return

    user = await get_user_by_telegram_id(c.from_user.id)
    if not is_registered_user(user):
        await c.answer("Anda belum terdaftar atau dibanned.")
        return

    meeting_id = c.data.split(':', 1)[1]
    await c.answer("Menghentikan cloud recording...")

    try:
        success = await zoom_client.control_live_meeting_recording(meeting_id, "stop")
        
        if success:
            # Update database status
            await update_meeting_recording_status(meeting_id, 'stopped')
            # Refresh control UI to show Start Recording + Download button
            await _refresh_control_zoom_ui(c, meeting_id)
            return
        else:
            text = "❌ <b>Gagal menghentikan cloud recording.</b> Pastikan recording sedang aktif."

    except Exception as e:
        logger.error(f"Failed to stop cloud recording for meeting {meeting_id}: {e}")
        text = f"❌ Error: {str(e)}"

    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🎥 Kembali ke Kontrol", callback_data=f"control_zoom:{meeting_id}")],
        [InlineKeyboardButton(text="📋 Daftar Meeting", callback_data="list_meetings")]
    ])

    await _safe_edit_or_fallback(c, text, reply_markup=kb)


@router.callback_query(lambda c: c.data and c.data.startswith('cloud_pause_record:'))
async def cb_cloud_pause_record(c: CallbackQuery):
    """Pause cloud recording for a live meeting."""
    if c.from_user is None:
        await c.answer("Informasi pengguna tidak tersedia")
        return

    user = await get_user_by_telegram_id(c.from_user.id)
    if not is_registered_user(user):
        await c.answer("Anda belum terdaftar atau dibanned.")
        return

    meeting_id = c.data.split(':', 1)[1]
    await c.answer("Menjeda cloud recording...")

    try:
        success = await zoom_client.control_live_meeting_recording(meeting_id, "pause")
        
        if success:
            # Update database status
            await update_meeting_recording_status(meeting_id, 'paused')
            # Refresh control UI to show Resume + Stop buttons
            await _refresh_control_zoom_ui(c, meeting_id)
            return
        else:
            text = "❌ <b>Gagal menjeda cloud recording.</b> Pastikan recording sedang aktif."

    except Exception as e:
        logger.error(f"Failed to pause cloud recording for meeting {meeting_id}: {e}")
        text = f"❌ Error: {str(e)}"

    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🎥 Kembali ke Kontrol", callback_data=f"control_zoom:{meeting_id}")],
        [InlineKeyboardButton(text="📋 Daftar Meeting", callback_data="list_meetings")]
    ])

    await _safe_edit_or_fallback(c, text, reply_markup=kb)


@router.callback_query(lambda c: c.data and c.data.startswith('cloud_resume_record:'))
async def cb_cloud_resume_record(c: CallbackQuery):
    """Resume cloud recording for a live meeting."""
    if c.from_user is None:
        await c.answer("Informasi pengguna tidak tersedia")
        return

    user = await get_user_by_telegram_id(c.from_user.id)
    if not is_registered_user(user):
        await c.answer("Anda belum terdaftar atau dibanned.")
        return

    meeting_id = c.data.split(':', 1)[1]
    await c.answer("Melanjutkan cloud recording...")

    try:
        success = await zoom_client.control_live_meeting_recording(meeting_id, "resume")
        
        if success:
            # Update database status back to recording
            await update_meeting_recording_status(meeting_id, 'recording')
            # Refresh control UI to show Pause + Stop buttons
            await _refresh_control_zoom_ui(c, meeting_id)
            return
        else:
            text = "❌ <b>Gagal melanjutkan cloud recording.</b> Pastikan recording sedang dijeda."

    except Exception as e:
        logger.error(f"Failed to resume cloud recording for meeting {meeting_id}: {e}")
        text = f"❌ Error: {str(e)}"

    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🎥 Kembali ke Kontrol", callback_data=f"control_zoom:{meeting_id}")],
        [InlineKeyboardButton(text="📋 Daftar Meeting", callback_data="list_meetings")]
    ])

    await _safe_edit_or_fallback(c, text, reply_markup=kb)


@router.callback_query(lambda c: c.data and c.data.startswith('view_cloud_recordings:'))
async def cb_view_cloud_recordings(c: CallbackQuery):
    """View available cloud recording download URLs for a meeting."""
    if c.from_user is None:
        await c.answer("Informasi pengguna tidak tersedia")
        return

    user = await get_user_by_telegram_id(c.from_user.id)
    if not is_registered_user(user):
        await c.answer("Anda belum terdaftar atau dibanned.")
        return

    meeting_id = c.data.split(':', 1)[1]
    
    # Show loading indicator
    try:
        await c.answer()  # Just acknowledge callback
    except Exception:
        pass

    loading_msg = await c.message.reply("⏳ Mengambil data cloud recording...")

    try:
        # Try to get cached recording data first
        cached_recording_data = await get_meeting_cloud_recording_data(meeting_id)
        
        # If no cached data, fetch from Zoom API and cache it
        if not cached_recording_data:
            logger.debug("No cached recording data, fetching from Zoom API")
            recording_data = await zoom_client.get_cloud_recording_urls(meeting_id)
            
            if recording_data:
                # Cache the data
                from datetime import datetime
                recording_data['last_checked'] = datetime.now().isoformat()
                await update_meeting_cloud_recording_data(meeting_id, recording_data)
                cached_recording_data = recording_data
        else:
            # Use cached data
            recording_data = cached_recording_data
            logger.debug("Using cached recording data for meeting %s", meeting_id)
        
        if not recording_data:
            text = (
                "📭 <b>Tidak ada Cloud Recordings</b>\n\n"
                f"Meeting ID: <code>{meeting_id}</code>\n\n"
                "Kemungkinan penyebab:\n"
                "• Meeting belum direkam\n"
                "• Recording masih diproses oleh Zoom\n"
                "• Recording sudah dihapus\n\n"
                "💡 <i>Cloud recording biasanya tersedia 1-2 jam setelah meeting selesai.</i>"
            )
            kb = InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="🔄 Refresh", callback_data=f"view_cloud_recordings:{meeting_id}")],
                [InlineKeyboardButton(text="🎥 Kembali ke Kontrol", callback_data=f"control_zoom:{meeting_id}")],
                [InlineKeyboardButton(text="📋 Daftar Meeting", callback_data="list_meetings")]
            ])
            await loading_msg.delete()
            await _safe_edit_or_fallback(c, text, reply_markup=kb)
            return

        # Parse recording data
        topic = recording_data.get('topic', 'No Topic')
        start_time_raw = recording_data.get('start_time', 'N/A')
        duration = recording_data.get('duration', 0)
        total_size = recording_data.get('total_size', 0)
        recording_count = recording_data.get('recording_count', 0)
        share_url = recording_data.get('share_url', '')
        recording_files = recording_data.get('recording_files', [])
        passcode = recording_data.get('password', '')  # Zoom API field name is 'password'
        
        # Format file size
        def format_size(bytes_size):
            if bytes_size < 1024:
                return f"{bytes_size} B"
            elif bytes_size < 1024**2:
                return f"{bytes_size/1024:.1f} KB"
            elif bytes_size < 1024**3:
                return f"{bytes_size/1024**2:.1f} MB"
            else:
                return f"{bytes_size/1024**3:.2f} GB"

        # Format start_time using user's timezone
        start_time = start_time_raw
        if start_time_raw and start_time_raw != 'N/A':
            try:
                from datetime import datetime, timezone
                import pytz
                from config import settings
                
                dt = datetime.fromisoformat(start_time_raw.replace('Z', '+00:00'))
                if dt.tzinfo is None:
                    dt = dt.replace(tzinfo=timezone.utc)
                
                user_tz = pytz.timezone(settings.timezone)
                local_dt = dt.astimezone(user_tz)
                
                day_name = {
                    'Monday': 'Senin', 'Tuesday': 'Selasa', 'Wednesday': 'Rabu',
                    'Thursday': 'Kamis', 'Friday': 'Jumat', 'Saturday': 'Sabtu',
                    'Sunday': 'Minggu'
                }.get(local_dt.strftime("%A"), local_dt.strftime("%A"))
                
                month_name = {
                    'January': 'Januari', 'February': 'Februari', 'March': 'Maret',
                    'April': 'April', 'May': 'Mei', 'June': 'Juni',
                    'July': 'Juli', 'August': 'Agustus', 'September': 'September',
                    'October': 'Oktober', 'November': 'November', 'December': 'Desember'
                }.get(local_dt.strftime("%B"), local_dt.strftime("%B"))
                
                start_time = f"{day_name}, {local_dt.day:02d} {month_name} {local_dt.year} {local_dt:%H:%M}"
            except Exception as e:
                logger.debug(f"Failed to format start_time {start_time_raw}: {e}")

        # Build message
        text = (
            f"📹 <b>Cloud Recordings Available</b>\n\n"
            f"<b>{topic}</b>\n"
            f"🆔 Meeting ID: <code>{meeting_id}</code>\n"
            f"🕐 Start Time: {start_time}\n"
            f"⏱️ Duration: {duration} minutes\n"
            f"📊 Total Size: {format_size(total_size)}\n"
            f"📁 Files: {recording_count}\n"
        )
        
        # Add passcode if available
        if passcode:
            text += f"🔐 Passcode: <code>{passcode}</code>\n"
        
        text += "\n"

        # Filter only MP4 files
        kb_rows = []
        mp4_files = [f for f in recording_files if f.get('file_type') == 'MP4']
        
        # Display MP4 file info with formatted start time
        for idx, file in enumerate(mp4_files, 1):
            file_size = file.get('file_size', 0)
            recording_start = file.get('recording_start', '')
            
            text += f"🎬 <b>File {idx}: MP4</b>\n"
            text += f"   Size: {format_size(file_size)}\n"
            
            # Convert recording start time to formatted date using user's timezone
            if recording_start:
                try:
                    from datetime import datetime, timezone, timedelta
                    import pytz
                    from config import settings
                    
                    # Parse ISO format datetime
                    dt = datetime.fromisoformat(recording_start.replace('Z', '+00:00'))
                    if dt.tzinfo is None:
                        dt = dt.replace(tzinfo=timezone.utc)
                    
                    # Convert to user's timezone from .env
                    user_tz = pytz.timezone(settings.timezone)
                    local_dt = dt.astimezone(user_tz)
                    
                    # Format: Hari, DD Bulan Tahun HH:MM (Indonesian day/month names)
                    day_name = {
                        'Monday': 'Senin', 'Tuesday': 'Selasa', 'Wednesday': 'Rabu',
                        'Thursday': 'Kamis', 'Friday': 'Jumat', 'Saturday': 'Sabtu',
                        'Sunday': 'Minggu'
                    }.get(local_dt.strftime("%A"), local_dt.strftime("%A"))
                    
                    month_name = {
                        'January': 'Januari', 'February': 'Februari', 'March': 'Maret',
                        'April': 'April', 'May': 'Mei', 'June': 'Juni',
                        'July': 'Juli', 'August': 'Agustus', 'September': 'September',
                        'October': 'Oktober', 'November': 'November', 'December': 'Desember'
                    }.get(local_dt.strftime("%B"), local_dt.strftime("%B"))
                    
                    formatted_date = f"{day_name}, {local_dt.day:02d} {month_name} {local_dt.year} {local_dt:%H:%M}"
                    text += f"   Start: {formatted_date}\n"
                except Exception as e:
                    logger.debug(f"Failed to format date {recording_start}: {e}")
                    text += f"   Start: {recording_start}\n"
            
            text += "\n"

        # Add MP4 download buttons
        for file in mp4_files:
            download_url = file.get('download_url', '')
            file_size = file.get('file_size', 0)
            
            if download_url:
                kb_rows.append([
                    InlineKeyboardButton(
                        text=f"📥 Download MP4 ({format_size(file_size)})", 
                        url=download_url
                    )
                ])
        
        # Add navigation buttons
        kb_rows.extend([
            [InlineKeyboardButton(text="🔄 Refresh", callback_data=f"view_cloud_recordings:{meeting_id}")],
            [InlineKeyboardButton(text="☁️ Kembali ke Cloud Recording", callback_data="list_cloud_recordings")],
            [InlineKeyboardButton(text="📋 Daftar Meeting", callback_data="list_meetings")]
        ])

        text += "⚠️ <i>Download links expire in 24 hours</i>"

        kb = InlineKeyboardMarkup(inline_keyboard=kb_rows)
        await loading_msg.delete()
        await _safe_edit_or_fallback(c, text, reply_markup=kb)

    except Exception as e:
        logger.exception(f"Failed to get cloud recordings for meeting {meeting_id}")
        text = f"❌ <b>Error getting cloud recordings</b>\n\n{str(e)}"
        kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🎥 Kembali ke Kontrol", callback_data=f"control_zoom:{meeting_id}")],
            [InlineKeyboardButton(text="📋 Daftar Meeting", callback_data="list_meetings")]
        ])
        await loading_msg.delete()
        await _safe_edit_or_fallback(c, text, reply_markup=kb)
