# Cloud Recording Control Handlers
# These handlers use Zoom's live_meetings/events API for cloud recording control

from aiogram import Router
from aiogram.types import CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from zoom import zoom_client
from bot.auth import is_owner_or_admin
from db import get_user_by_telegram_id, get_meeting_recording_status, update_meeting_recording_status, list_meetings
import logging
import asyncio

logger = logging.getLogger(__name__)
router = Router()


async def _safe_edit_or_fallback(c: CallbackQuery, text: str, reply_markup=None, parse_mode=None) -> None:
    """Try to edit the original message. If that's not available, reply to the message or answer the callback."""
    from aiogram.types import Message as AiMessage
    from aiogram.exceptions import TelegramBadRequest
    
    m = getattr(c, 'message', None)
    
    if isinstance(m, AiMessage):
        try:
            await m.edit_text(text, reply_markup=reply_markup, parse_mode=parse_mode)
            return
        except TelegramBadRequest:
            try:
                await m.reply(text, reply_markup=reply_markup, parse_mode=parse_mode)
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
            [InlineKeyboardButton(text="🔄️ Refresh Status", callback_data=f"control_zoom:{meeting_id}")],
            [InlineKeyboardButton(text="📊 Meeting Details", callback_data=f"zoom_meeting_details:{meeting_id}")],
            [InlineKeyboardButton(text="⬅️ Kembali ke Daftar", callback_data="list_meetings")]
        ])

        kb = InlineKeyboardMarkup(inline_keyboard=kb_rows)
        await _safe_edit_or_fallback(c, text, reply_markup=kb, parse_mode="HTML")

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
    
    if not is_owner_or_admin(user):
        logger.warning("cb_cloud_start_record: User not admin/owner")
        await c.answer("Aksi ini hanya untuk Admin/Owner.")
        return

    meeting_id = c.data.split(':', 1)[1]
    logger.debug("cb_cloud_start_record: Meeting ID extracted: %s", meeting_id)
    await c.answer("Memulai cloud recording...")

    try:
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
            return
        else:
            text = "❌ <b>Gagal memulai cloud recording.</b> Pastikan meeting sedang berlangsung."
            logger.warning("cb_cloud_start_record: Both start and resume failed")

    except Exception as e:
        logger.exception("cb_cloud_start_record: Exception occurred")
        text = f"❌ Error: {str(e)}"

    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🎥 Kembali ke Kontrol", callback_data=f"control_zoom:{meeting_id}")],
        [InlineKeyboardButton(text="📋 Daftar Meeting", callback_data="list_meetings")]
    ])

    await _safe_edit_or_fallback(c, text, reply_markup=kb, parse_mode="HTML")


@router.callback_query(lambda c: c.data and c.data.startswith('cloud_stop_record:'))
async def cb_cloud_stop_record(c: CallbackQuery):
    """Stop cloud recording for a live meeting."""
    if c.from_user is None:
        await c.answer("Informasi pengguna tidak tersedia")
        return

    user = await get_user_by_telegram_id(c.from_user.id)
    if not is_owner_or_admin(user):
        await c.answer("Aksi ini hanya untuk Admin/Owner.")
        return

    meeting_id = c.data.split(':', 1)[1]
    await c.answer("Menghentikan cloud recording...")

    try:
        success = await zoom_client.control_live_meeting_recording(meeting_id, "stop")
        
        if success:
            # Update database status
            await update_meeting_recording_status(meeting_id, 'stopped')
            # Wait for Zoom API to update status
            await asyncio.sleep(5)

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

    await _safe_edit_or_fallback(c, text, reply_markup=kb, parse_mode="HTML")


@router.callback_query(lambda c: c.data and c.data.startswith('cloud_pause_record:'))
async def cb_cloud_pause_record(c: CallbackQuery):
    """Pause cloud recording for a live meeting."""
    if c.from_user is None:
        await c.answer("Informasi pengguna tidak tersedia")
        return

    user = await get_user_by_telegram_id(c.from_user.id)
    if not is_owner_or_admin(user):
        await c.answer("Aksi ini hanya untuk Admin/Owner.")
        return

    meeting_id = c.data.split(':', 1)[1]
    await c.answer("Menjeda cloud recording...")

    try:
        success = await zoom_client.control_live_meeting_recording(meeting_id, "pause")
        
        if success:
            # Update database status
            await update_meeting_recording_status(meeting_id, 'paused')
            # Wait for Zoom API to update status
            await asyncio.sleep(5)

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

    await _safe_edit_or_fallback(c, text, reply_markup=kb, parse_mode="HTML")


@router.callback_query(lambda c: c.data and c.data.startswith('cloud_resume_record:'))
async def cb_cloud_resume_record(c: CallbackQuery):
    """Resume cloud recording for a live meeting."""
    if c.from_user is None:
        await c.answer("Informasi pengguna tidak tersedia")
        return

    user = await get_user_by_telegram_id(c.from_user.id)
    if not is_owner_or_admin(user):
        await c.answer("Aksi ini hanya untuk Admin/Owner.")
        return

    meeting_id = c.data.split(':', 1)[1]
    await c.answer("Melanjutkan cloud recording...")

    try:
        success = await zoom_client.control_live_meeting_recording(meeting_id, "resume")
        
        if success:
            # Update database status back to recording
            await update_meeting_recording_status(meeting_id, 'recording')
            # Wait for Zoom API to update status
            await asyncio.sleep(5)

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

    await _safe_edit_or_fallback(c, text, reply_markup=kb, parse_mode="HTML")
