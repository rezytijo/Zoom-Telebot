import os
from dataclasses import dataclass
from dotenv import load_dotenv

load_dotenv()


def _to_int(s: str | None) -> int | None:
    try:
        return int(s) if s else None
    except Exception:
        return None


def _to_bool(s: str | None) -> bool:
    if not s:
        return False
    return s.lower() in ('true', '1', 'yes', 'on')


def _db_path_from_database_url(database_url: str | None) -> str:
    if not database_url:
        return os.getenv("DB_PATH", "bot.db")
    # handle sqlite URLs like sqlite+aiosqlite:///./zoom_telebot.db
    if database_url.startswith("sqlite"):
        # split at three slashes
        if ":///" in database_url:
            return database_url.split(":///", 1)[1]
        # fallback: take trailing part
        return database_url.rsplit('/', 1)[-1]
    # otherwise return the raw URL
    return database_url


@dataclass
class Settings:
    """
    Application configuration loaded from environment variables.
    
    For database migrations and schema information, see:
    docs/DATABASE_MIGRATIONS.md
    
    Schema Version: v2.0 (with Cloud Recording Support)
    Latest Migration: December 31, 2025 - Added cloud_recording_data column
    """
    
    # Telegram
    bot_token: str | None = os.getenv("TELEGRAM_TOKEN")
    owner_id: int | None = _to_int(os.getenv("INITIAL_OWNER_ID"))
    owner_username: str | None = os.getenv("INITIAL_OWNER_USERNAME")

    # Database
    database_url: str | None = os.getenv("DATABASE_URL")
    db_path: str = _db_path_from_database_url(os.getenv("DATABASE_URL"))

    # Mode / webhook
    default_mode: str = os.getenv("DEFAULT_MODE", "polling")
    webhook_secret: str | None = os.getenv("WEBHOOK_SECRET")

    # Zoom
    zoom_account_id: str | None = os.getenv("ZOOM_ACCOUNT_ID")
    zoom_client_id: str | None = os.getenv("ZOOM_CLIENT_ID")
    zoom_client_secret: str | None = os.getenv("ZOOM_CLIENT_SECRET")
    # Optional: user id (Zoom userId) or user email to create meetings for.
    # Use one of these when requesting meetings on behalf of a specific Zoom user
    # in the account. If not provided, handlers may pass 'me' which requires a
    # user-scoped token instead of an account-level S2S token.
    zoom_user_id: str | None = os.getenv("ZOOM_USER_ID")
    zoom_user_email: str | None = os.getenv("ZOOM_USER_EMAIL")
    zoom_audience: str = os.getenv("ZOOM_AUDIENCE", "https://api.zoom.us")
    zoom_control_mode: str = os.getenv("ZOOM_CONTROL_MODE", "cloud")

    # Timezone (e.g., Asia/Jakarta). Also respects TZ/PYTZ_TIMEZONE if TIMEZONE unset.
    timezone: str = os.getenv("TIMEZONE") or os.getenv("TZ") or os.getenv("PYTZ_TIMEZONE", "Asia/Jakarta")

    # Shortener providers
    # DEFAULT_SHORTENER: 'sid', 'bitly', 'tinyurl'
    DEFAULT_SHORTENER: str = os.getenv('DEFAULT_SHORTENER', 'tinyurl')

    # Logging
    LOG_LEVEL: str = os.getenv('LOG_LEVEL', 'INFO')
    LOG_FORMAT: str = os.getenv('LOG_FORMAT', '%(asctime)s,%(msecs)03d - %(name)s - %(levelname)s - %(message)s')

    # Data directory
    DATA_DIR: str = os.getenv('DATA_DIR', './data')

    # alternative authentication using X-Auth-Id / X-Auth-Key
    sid_id: str | None = os.getenv('SID_ID')
    sid_key: str | None = os.getenv('SID_KEY')
    # base URL for S.id API (used to derive sid_api_url if not provided)
    sid_base_url: str = os.getenv('SID_BASE_URL', 'https://api.s.id')
    # base URL used to compose final short URL (e.g. https://s.id)
    sid_short_base: str = os.getenv('SID_SHORT_BASE', 'https://s.id')

    # TinyURL settings
    tinyurl_api_key: str | None = os.getenv('TINYURL_API_KEY')
    tinyurl_api_url: str = os.getenv('TINYURL_API_URL', 'https://api.tinyurl.com/create')

    # Bitly settings (if using Bitly provider)
    bitly_token: str | None = os.getenv('BITLY_TOKEN')
    bitly_api_url: str = os.getenv('BITLY_API_URL', 'https://api-ssl.bitly.com/v4/shorten')

    # FSM TTL (seconds). If None or invalid, storage defaults to 300s
    fsm_ttl_seconds: int | None = _to_int(os.getenv('FSM_TTL_SECONDS')) or (
        (_to_int(os.getenv('FSM_TTL_MINUTES')) or 0) * 60 or None
    )


settings = Settings()
