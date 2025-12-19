# Database Package
from .db import (
    # Core database functions
    init_db,
    run_migrations,

    # User management
    add_pending_user,
    list_pending_users,
    list_all_users,
    update_user_status,
    get_user_by_telegram_id,
    ban_toggle_user,
    delete_user,
    search_users,

    # Meeting management
    add_meeting,
    update_meeting_short_url,
    update_meeting_short_url_by_join_url,
    list_meetings,
    list_meetings_with_shortlinks,
    sync_meetings_from_zoom,
    update_expired_meetings,
    update_meeting_status,
    update_meeting_details,
    update_meeting_recording_status,
    get_meeting_recording_status,
    update_meeting_live_status,
    get_meeting_live_status,
    sync_meeting_live_status_from_zoom,
    get_meeting_agent_id,

    # Agent management
    list_agents,
    count_agents,
    get_agent,
    add_agent,
    remove_agent,

    # Command management
    add_command,
    get_pending_commands,
    update_command_status,
    check_timeout_commands,

    # Shortlink management
    add_shortlink,
    update_shortlink_status,
    get_shortlinks_by_user,
    get_shortlink_stats,

    # Backup/Restore
    backup_database,
    backup_shorteners,
    create_backup_zip,
    restore_database,
    restore_shorteners,
    extract_backup_zip,
)

__all__ = [
    # Core database functions
    "init_db",
    "run_migrations",

    # User management
    "add_pending_user",
    "list_pending_users",
    "list_all_users",
    "update_user_status",
    "get_user_by_telegram_id",
    "ban_toggle_user",
    "delete_user",
    "search_users",

    # Meeting management
    "add_meeting",
    "update_meeting_short_url",
    "update_meeting_short_url_by_join_url",
    "list_meetings",
    "list_meetings_with_shortlinks",
    "sync_meetings_from_zoom",
    "update_expired_meetings",
    "update_meeting_status",
    "update_meeting_details",
    "update_meeting_recording_status",
    "get_meeting_recording_status",
    "update_meeting_live_status",
    "get_meeting_live_status",
    "sync_meeting_live_status_from_zoom",
    "get_meeting_agent_id",

    # Agent management
    "list_agents",
    "count_agents",
    "get_agent",
    "add_agent",
    "remove_agent",

    # Command management
    "add_command",
    "get_pending_commands",
    "update_command_status",
    "check_timeout_commands",

    # Shortlink management
    "add_shortlink",
    "update_shortlink_status",
    "get_shortlinks_by_user",
    "get_shortlink_stats",

    # Backup/Restore
    "backup_database",
    "backup_shorteners",
    "create_backup_zip",
    "restore_database",
    "restore_shorteners",
    "extract_backup_zip",
]