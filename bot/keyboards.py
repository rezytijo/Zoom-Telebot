from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from typing import List, Dict
from shortener import get_available_providers
from config import settings


def _is_agent_control_enabled() -> bool:
    """Check if agent control is enabled via ZOOM_CONTROL_MODE."""
    return settings.zoom_control_mode.lower() == "agent"


def main_menu_keyboard(user_role: str = "user") -> InlineKeyboardMarkup:
    """Main menu keyboard (ringkas): create, shortener, list, info; admin adds backup + agent control."""
    keyboard = []

    # Core actions for all users
    keyboard.append([InlineKeyboardButton(text="➕ Create Meeting!", callback_data="create_meeting")])
    keyboard.append([InlineKeyboardButton(text="📋 List Meeting", callback_data="list_meetings")])
    keyboard.append([InlineKeyboardButton(text="🔗 URL Shortener", callback_data="menu_shortener")])
    keyboard.append([InlineKeyboardButton(text="ℹ️ Informasi & Bantuan", callback_data="menu_info")])

    # Admin/Owner extras
    if user_role in ["admin", "owner"]:
        keyboard.append([InlineKeyboardButton(text="💾 Backup & Restore", callback_data="menu_backup")])
        if _is_agent_control_enabled():
            keyboard.append([InlineKeyboardButton(text="🟢 Agent Control ON", callback_data="noop")])

    return InlineKeyboardMarkup(inline_keyboard=keyboard)


def meetings_menu_keyboard() -> InlineKeyboardMarkup:
    """Meeting management submenu."""
    keyboard = [
        [InlineKeyboardButton(text="📝 Buat Meeting Baru", callback_data="create_meeting")],
        [InlineKeyboardButton(text="📋 Daftar Meeting", callback_data="list_meetings")],
        [InlineKeyboardButton(text="🔄 Sync dari Zoom", callback_data="sync_meetings")],
        [InlineKeyboardButton(text="⏰ Cek Meeting Expired", callback_data="check_expired")],
        [InlineKeyboardButton(text="⬅️ Kembali ke Menu Utama", callback_data="back_to_main")],
    ]
    return InlineKeyboardMarkup(inline_keyboard=keyboard)


def users_menu_keyboard() -> InlineKeyboardMarkup:
    """User management submenu (admin/owner only)."""
    keyboard = [
        [InlineKeyboardButton(text="📊 Semua User", callback_data="all_users:0")],
        [InlineKeyboardButton(text="⏳ User Pending", callback_data="pending_users")],
        [InlineKeyboardButton(text="🔍 Cari User", callback_data="search_user")],
        [InlineKeyboardButton(text="⬅️ Kembali ke Menu Utama", callback_data="back_to_main")],
    ]
    return InlineKeyboardMarkup(inline_keyboard=keyboard)


def backup_menu_keyboard() -> InlineKeyboardMarkup:
    """Backup and restore submenu (admin/owner only)."""
    keyboard = [
        [InlineKeyboardButton(text="💾 Backup Database", callback_data="backup_db")],
        [InlineKeyboardButton(text="📦 Restore Database", callback_data="restore_db")],
        [InlineKeyboardButton(text="⬅️ Kembali ke Menu Utama", callback_data="back_to_main")],
    ]
    return InlineKeyboardMarkup(inline_keyboard=keyboard)


def info_menu_keyboard() -> InlineKeyboardMarkup:
    """Information and help submenu."""
    keyboard = [
        [InlineKeyboardButton(text="❓ Bantuan (Help)", callback_data="show_help")],
        [InlineKeyboardButton(text="ℹ️ Tentang Bot", callback_data="show_about")],
        [InlineKeyboardButton(text="👤 Info Saya", callback_data="whoami")],
        [InlineKeyboardButton(text="⬅️ Kembali ke Menu Utama", callback_data="back_to_main")],
    ]
    return InlineKeyboardMarkup(inline_keyboard=keyboard)


def shortener_menu_keyboard() -> InlineKeyboardMarkup:
    """URL shortener submenu."""
    keyboard = [
        [InlineKeyboardButton(text="🔗 Shorten URL", callback_data="short_url")],
        [InlineKeyboardButton(text="⬅️ Kembali ke Menu Utama", callback_data="back_to_main")],
    ]
    return InlineKeyboardMarkup(inline_keyboard=keyboard)


# Legacy keyboards (keeping for backward compatibility)
def pending_user_buttons(telegram_id: int) -> InlineKeyboardMarkup:
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="✅ Terima", callback_data=f"accept:{telegram_id}"),
            InlineKeyboardButton(text="❌ Tolak", callback_data=f"reject:{telegram_id}"),
        ],
        [InlineKeyboardButton(text="⛔ Banned", callback_data=f"ban:{telegram_id}")]
    ])
    return kb


def pending_user_owner_buttons(telegram_id: int, is_banned: bool=False) -> InlineKeyboardMarkup:
    text = "Unbanned" if is_banned else "Banned"
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="✅ Terima", callback_data=f"accept:{telegram_id}"),
            InlineKeyboardButton(text="❌ Tolak", callback_data=f"reject:{telegram_id}"),
        ],
        [InlineKeyboardButton(text=text, callback_data=f"ban_toggle:{telegram_id}")]
    ])
    return kb


def user_action_buttons() -> InlineKeyboardMarkup:
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📝 Create Meeting", callback_data="create_meeting")],
        [InlineKeyboardButton(text="📅 List Upcoming Meeting", callback_data="list_meetings")],
        [InlineKeyboardButton(text="🔗 Short URL", callback_data="short_url")],
        [InlineKeyboardButton(text="🔍 Search User", callback_data="search_user")],
    ])
    return kb


def manage_users_buttons(telegram_id: int) -> InlineKeyboardMarkup:
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🗑️ Delete User", callback_data=f"delete_user:{telegram_id}")],
        [InlineKeyboardButton(text="🔄 Change Role", callback_data=f"change_role:{telegram_id}")],
        [InlineKeyboardButton(text="📊 Change Status", callback_data=f"change_status:{telegram_id}")],
        [InlineKeyboardButton(text="⬅️ Kembali ke List User", callback_data="all_users:0")],
    ])
    return kb


def role_selection_buttons(telegram_id: int) -> InlineKeyboardMarkup:
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="👑 Owner", callback_data=f"set_role:{telegram_id}:owner")],
        [InlineKeyboardButton(text="👨‍💼 Admin", callback_data=f"set_role:{telegram_id}:admin")],
        [InlineKeyboardButton(text="👤 User", callback_data=f"set_role:{telegram_id}:user")],
        [InlineKeyboardButton(text="👤 Guest", callback_data=f"set_role:{telegram_id}:guest")],
        [InlineKeyboardButton(text="⬅️ Kembali", callback_data=f"cancel_change:{telegram_id}")],
    ])
    return kb


def status_selection_buttons(telegram_id: int) -> InlineKeyboardMarkup:
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="⏳ Pending", callback_data=f"set_status:{telegram_id}:pending")],
        [InlineKeyboardButton(text="✅ Whitelisted", callback_data=f"set_status:{telegram_id}:whitelisted")],
        [InlineKeyboardButton(text="🚫 Banned", callback_data=f"set_status:{telegram_id}:banned")],
        [InlineKeyboardButton(text="⬅️ Kembali", callback_data=f"cancel_change:{telegram_id}")],
    ])
    return kb


def list_meetings_buttons() -> InlineKeyboardMarkup:
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔄 Refresh", callback_data="sync_refresh_list")],
        [InlineKeyboardButton(text="☁️ Cloud Recording", callback_data="list_cloud_recordings")],
        [InlineKeyboardButton(text="🏠 Kembali ke Menu Utama", callback_data="back_to_main")],
    ])
    return kb


def shortener_provider_buttons(token: str) -> InlineKeyboardMarkup:
    """Generate keyboard for selecting shortener provider dynamically."""
    providers = get_available_providers()
    kb_buttons = []

    # Add provider buttons
    for provider_id, provider_name in providers.items():
        kb_buttons.append([
            InlineKeyboardButton(text=f"🔗 {provider_name}", callback_data=f"shorten_provider:{token}:{provider_id}")
        ])

    # Add cancel button
    kb_buttons.append([
        InlineKeyboardButton(text="❌ Batal", callback_data=f"cancel_shorten:{token}")
    ])

    return InlineKeyboardMarkup(inline_keyboard=kb_buttons)


def shortener_provider_selection_buttons() -> InlineKeyboardMarkup:
    """Provider selection for new shortener flow (without token)"""
    providers = get_available_providers()
    
    kb_buttons = []
    # Add provider buttons
    for provider_id, provider_name in providers.items():
        kb_buttons.append([
            InlineKeyboardButton(text=f"🔗 {provider_name}", callback_data=f"select_provider:{provider_id}")
        ])

    # Add cancel button
    kb_buttons.append([
        InlineKeyboardButton(text="❌ Batal", callback_data="cancel_shortener_flow")
    ])

    return InlineKeyboardMarkup(inline_keyboard=kb_buttons)


def shortener_custom_choice_buttons() -> InlineKeyboardMarkup:
    """Buttons for choosing custom URL or not"""
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ Ya, pakai custom URL", callback_data="custom_yes")],
        [InlineKeyboardButton(text="❌ Tidak, gunakan random", callback_data="custom_no")],
        [InlineKeyboardButton(text="🏠 Batal", callback_data="cancel_shortener_flow")]
    ])
    return kb


def back_to_main_buttons() -> InlineKeyboardMarkup:
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🏠 Kembali ke Menu Utama", callback_data="back_to_main")],
    ])
    return kb


def back_to_main_new_buttons() -> InlineKeyboardMarkup:
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🏠 Kembali ke Menu Utama (Pesan Baru)", callback_data="back_to_main_new")],
    ])
    return kb
