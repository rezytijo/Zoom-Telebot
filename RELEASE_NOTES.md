# Release Notes - Zoom-Telebot SOC

## v2026.01.14 - Meeting List Enhancement

### 🚀 New Features
- **Enhanced Meeting List**: Meeting list now displays meetings with status 'done' alongside 'active', providing a complete view of past and upcoming meetings.
- **Time Window Enforcement**: Implemented strict time filtering for meeting lists, showing only meetings from local 00:00 today up to +30 days ahead, ensuring focused and relevant listings.

### 🔧 Technical Changes
- **Database Query Update**: Modified `list_meetings_with_shortlinks()` in `db/db.py` to include status 'done' in the WHERE clause.
- **Handler Logic Enhancement**: Added time range filtering in `_do_list_meetings()` in `bot/handlers.py` using configured timezone (fallback to WIB/UTC+7).
- **UI Text Updates**: Updated user-facing messages to reflect the inclusion of both active and completed meetings.

### 📝 Documentation
- Updated `context.md` with detailed change logs and implementation notes.
- Maintained backward compatibility with existing functionality.

### 🐛 Bug Fixes
- No breaking changes; all existing features remain functional.

### 📊 Impact
- Users can now view completed meetings within the 30-day window, improving visibility and management.
- Consistent timezone handling ensures accurate local time displays.

---

## Previous Releases

### v2026.01.08 - Role Adjustments & Docker Multi-Platform
- Adjusted role requirements for better access control
- Docker images built with AMD64 and ARM64 support
- FSM state TTL implementation for better session management
- Various bug fixes for meeting editing and control

### v2025.12.31 - Cloud Recording & Time Range
- Cloud recording viewer with passcode display
- Meeting list time range from current time to +30 days
- Database caching for cloud recording data

*(For full history, see context.md)*