from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from shortener import get_available_providers


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
    ])
    return kb


def all_users_buttons(telegram_id: int) -> InlineKeyboardMarkup:
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🗑️ Delete User", callback_data=f"delete_user:{telegram_id}")],
        [InlineKeyboardButton(text="🔄 Change Role", callback_data=f"change_role:{telegram_id}")],
        [InlineKeyboardButton(text="📊 Change Status", callback_data=f"change_status:{telegram_id}")],
    ])
    return kb


def role_selection_buttons(telegram_id: int) -> InlineKeyboardMarkup:
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="👑 Owner", callback_data=f"set_role:{telegram_id}:owner")],
        [InlineKeyboardButton(text="👨‍💼 Admin", callback_data=f"set_role:{telegram_id}:admin")],
        [InlineKeyboardButton(text="👤 User", callback_data=f"set_role:{telegram_id}:user")],
        [InlineKeyboardButton(text="👤 Guest", callback_data=f"set_role:{telegram_id}:guest")],
        [InlineKeyboardButton(text="❌ Cancel", callback_data=f"cancel_change:{telegram_id}")],
    ])
    return kb


def status_selection_buttons(telegram_id: int) -> InlineKeyboardMarkup:
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="⏳ Pending", callback_data=f"set_status:{telegram_id}:pending")],
        [InlineKeyboardButton(text="✅ Whitelisted", callback_data=f"set_status:{telegram_id}:whitelisted")],
        [InlineKeyboardButton(text="🚫 Banned", callback_data=f"set_status:{telegram_id}:banned")],
        [InlineKeyboardButton(text="❌ Cancel", callback_data=f"cancel_change:{telegram_id}")],
    ])
    return kb


def list_meetings_buttons() -> InlineKeyboardMarkup:
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔄 Refresh", callback_data="list_meetings")],
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
