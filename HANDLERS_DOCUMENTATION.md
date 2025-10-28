# Dokumentasi Bot Telegram Zoom - Handlers.py

## 📋 Daftar Command dan Fitur

### 🤖 **Commands Utama**

| Command | Baris | Deskripsi | Akses |
|---------|-------|-----------|-------|
| `/start` | 659 | Menampilkan menu utama bot dan register user jika belum ada | Semua user |
| `/help` | 237 | Menampilkan bantuan dan daftar command yang tersedia | Semua user |
| `/about` | 267 | Menampilkan informasi tentang bot | Semua user |
| `/whoami` | 218 | Menampilkan informasi akun Telegram user | Semua user |
| `/meet` | 290 | Membuat meeting Zoom dengan format cepat | User terdaftar |
| `/zoom_del` | - | Menghapus meeting Zoom (dalam /meet) | User terdaftar |

### 👑 **Commands Admin/Owner**

| Command | Baris | Deskripsi | Akses |
|---------|-------|-----------|-------|
| `/register_list` | 482 | Melihat daftar user yang menunggu persetujuan | Admin/Owner |
| `/all_users` | 659 | Mengelola semua user (ubah role, status, hapus) | Admin/Owner |
| `/sync_meetings` | 437 | Sinkronkan meetings dari Zoom ke database | Owner only |
| `/check_expired` | 449 | Periksa dan tandai meeting yang sudah lewat waktu | Owner only |
| `/backup` | 1280 | Membuat backup database dan konfigurasi shorteners | Owner only |
| `/restore` | 1318 | Restore dari file backup ZIP | Owner only |

### 🎯 **Callback Handlers**

| Callback Pattern | Baris | Deskripsi |
|------------------|-------|-----------|
| `accept:*` | 756 | Menerima user pending menjadi whitelisted |
| `reject:*` | 767 | Menolak dan menghapus user pending |
| `ban:*` | 789 | Membanned user dari register list |
| `unban:*` | 800 | Unban user dari all users list |
| `manage_user:*` | 811 | Menampilkan menu management user individual |
| `register_list*` | 825 | Refresh daftar registrasi dengan pagination |
| `all_users*` | 1133 | Refresh daftar semua user dengan pagination |
| `ban_toggle:*` | 778 | Toggle status ban/unban user |
| `noop` | 1027 | No operation callback |

### 🔄 **FSM States (Finite State Machine)**

| State Class | Baris | Deskripsi |
|-------------|-------|-----------|
| `MeetingStates` | 32 | States untuk pembuatan meeting interaktif |
| `ShortenerStates` | 37 | States untuk konfigurasi shortener URL |
| `RestoreStates` | 42 | States untuk proses restore backup |

## 📖 **Penjelasan Detail Setiap Fungsi**

### **1. Helper Functions & Utilities**

#### `extract_zoom_meeting_id(url: str) -> Optional[str]`
- **Baris:** 47-62
- **File:** `handlers.py`
- **Deskripsi:** Mengekstrak Meeting ID Zoom dari URL Zoom
- **Return:** Meeting ID atau None jika tidak ditemukan

#### `_get_user_info_text(user: dict) -> str`
- **Baris:** 65-67
- **File:** `handlers.py`
- **Deskripsi:** Format informasi user untuk display
- **Return:** String formatted user info

#### `_get_username_from_telegram_id(telegram_id: str) -> str`
- **Baris:** 70-84
- **File:** `handlers.py`
- **Deskripsi:** Mendapatkan username dari telegram_id untuk display creator meeting

#### `_format_meeting_time(start_time_str: str) -> str`
- **Baris:** 87-121
- **File:** `handlers.py`
- **Deskripsi:** Format waktu meeting ke format Indonesia (WIB)
- **Return:** String waktu dalam format Indonesia

#### `_parse_indonesia_date(date_str: str) -> Optional[date]`
- **Baris:** 124-156
- **File:** `handlers.py`
- **Deskripsi:** Parse berbagai format tanggal Indonesia ke date object

#### `_parse_time_24h(time_str: str) -> Optional[time]`
- **Baris:** 159-206
- **File:** `handlers.py`
- **Deskripsi:** Parse format waktu 24 jam ke time object

### **2. Command Handlers**

#### `cmd_whoami(msg: Message)`
- **Baris:** 218-227
- **File:** `handlers.py`
- **Command:** `/whoami`
- **Deskripsi:** Menampilkan informasi akun Telegram user (diagnostic)

#### `cmd_help(msg: Message)`
- **Baris:** 237-282
- **File:** `handlers.py`
- **Command:** `/help`
- **Deskripsi:** Menampilkan bantuan lengkap dengan semua command yang tersedia

#### `cmd_about(msg: Message)`
- **Baris:** 267-276
- **File:** `handlers.py`
- **Command:** `/about`
- **Deskripsi:** Menampilkan informasi tentang bot

#### `cmd_zoom(msg: Message)` / `cmd_meet(msg: Message)`
- **Baris:** 290-437
- **File:** `handlers.py`
- **Command:** `/meet`
- **Deskripsi:** Membuat meeting Zoom dengan format cepat, support batch creation

#### `cmd_sync_meetings(msg: Message)`
- **Baris:** 437-447
- **File:** `handlers.py`
- **Command:** `/sync_meetings`
- **Akses:** Owner only
- **Deskripsi:** Sinkronkan meetings dari Zoom API ke database lokal

#### `cmd_check_expired(msg: Message)`
- **Baris:** 449-459
- **File:** `handlers.py`
- **Command:** `/check_expired`
- **Akses:** Owner only
- **Deskripsi:** Periksa dan tandai meeting yang sudah expired

#### `cmd_register_list(msg: Message)`
- **Baris:** 482-550
- **File:** `handlers.py`
- **Command:** `/register_list`
- **Akses:** Admin/Owner
- **Deskripsi:** Menampilkan daftar user yang menunggu persetujuan registrasi

#### `cmd_all_users(msg: Message)`
- **Baris:** 659-750
- **File:** `handlers.py`
- **Command:** `/all_users`
- **Akses:** Admin/Owner
- **Deskripsi:** Menampilkan daftar semua user aktif/banned dengan opsi management

#### `cmd_start(msg: Message)`
- **Baris:** 752-782
- **File:** `handlers.py`
- **Command:** `/start`
- **Deskripsi:** Menampilkan menu utama dan register user jika belum terdaftar

#### `cmd_backup(msg: Message, bot: Bot)`
- **Baris:** 1280-1300
- **File:** `handlers.py`
- **Command:** `/backup`
- **Akses:** Owner only
- **Deskripsi:** Membuat backup database dan konfigurasi shorteners

#### `cmd_restore(msg: Message, state: FSMContext)`
- **Baris:** 1318-1335
- **File:** `handlers.py`
- **Command:** `/restore`
- **Akses:** Owner only
- **Deskripsi:** Memulai mode restore dari file backup

### **3. Callback Handlers**

#### `cb_accept(c: CallbackQuery)`
- **Baris:** 756-765
- **File:** `handlers.py`
- **Callback:** `accept:*`
- **Deskripsi:** Menerima user pending menjadi whitelisted

#### `cb_reject(c: CallbackQuery)`
- **Baris:** 767-777
- **File:** `handlers.py`
- **Callback:** `reject:*`
- **Deskripsi:** Menolak dan menghapus user pending

#### `cb_ban_toggle(c: CallbackQuery)`
- **Baris:** 778-788
- **File:** `handlers.py`
- **Callback:** `ban_toggle:*`
- **Deskripsi:** Toggle status ban/unban user

#### `cb_ban(c: CallbackQuery)`
- **Baris:** 789-799
- **File:** `handlers.py`
- **Callback:** `ban:*`
- **Deskripsi:** Ban user dari register list

#### `cb_unban(c: CallbackQuery)`
- **Baris:** 800-810
- **File:** `handlers.py`
- **Callback:** `unban:*`
- **Deskripsi:** Unban user dari all users list

#### `cb_manage_user(c: CallbackQuery)`
- **Baris:** 811-823
- **File:** `handlers.py`
- **Callback:** `manage_user:*`
- **Deskripsi:** Menampilkan menu management untuk user individual

#### `cb_register_list(c: CallbackQuery)`
- **Baris:** 825-1025
- **File:** `handlers.py`
- **Callback:** `register_list*`
- **Deskripsi:** Refresh daftar registrasi dengan pagination support

#### `cb_noop(c: CallbackQuery)`
- **Baris:** 1027-1030
- **File:** `handlers.py`
- **Callback:** `noop`
- **Deskripsi:** No operation callback untuk menghilangkan loading state

#### `cb_all_users(c: CallbackQuery)`
- **Baris:** 1133-1278
- **File:** `handlers.py`
- **Callback:** `all_users*`
- **Deskripsi:** Refresh daftar semua user dengan pagination

### **4. FSM State Handlers**

#### `handle_restore_file(msg: Message, state: FSMContext, bot: Bot)`
- **Baris:** 1337-1400
- **File:** `handlers.py`
- **State:** `RestoreStates.waiting_for_file`
- **Deskripsi:** Menangani upload file backup untuk restore

#### `cancel_restore(msg: Message, state: FSMContext)`
- **Baris:** 1402-1406
- **File:** `handlers.py`
- **State:** `RestoreStates.waiting_for_file`
- **Command:** `/cancel`
- **Deskripsi:** Membatalkan proses restore

### **5. Utility Functions**

#### `_safe_edit_or_fallback(c: CallbackQuery, text: str, reply_markup=None, parse_mode=None)`
- **Baris:** 784-803
- **File:** `handlers.py`
- **Deskripsi:** Safe method untuk edit message atau fallback ke reply

## 📊 **Ringkasan Statistik**

- **Total Commands:** 12 commands
- **Total Callback Handlers:** 9 patterns
- **Total Functions:** 25+ functions
- **Total FSM States:** 3 state groups
- **Total Lines:** ~1400+ lines

## 🔗 **Dependencies**

**Files yang di-import:**
- `db.py` - Database operations
- `keyboards.py` - Inline keyboard layouts
- `config.py` - Settings dan konfigurasi
- `auth.py` - Authentication helpers
- `zoom.py` - Zoom API client

**External Libraries:**
- `aiogram` - Telegram Bot API framework
- `datetime/timezone` - DateTime handling
- `re` - Regular expressions
- `tempfile` - Temporary file handling
- `os` - Operating system interface

---

*Dokumentasi ini dibuat pada: Oktober 28, 2025*
*File: `handlers.py`*
*Total functions/commands: 35+*

## 🔍 Detailed function locations (generated)

Berikut adalah daftar fungsi, handler, dan kelas FSM beserta rentang baris (start..end) di file `handlers.py`. Ini dihasilkan otomatis dari scan file dan melengkapi dokumentasi di atas dengan lokasi yang presisi.

```
extract_zoom_meeting_id          : 50..66
_get_user_info_text             : 67..71
_get_username_from_telegram_id  : 72..88
_format_meeting_time            : 89..129
_parse_indonesia_date           : 130..177
_parse_time_24h                 : 178..214

cmd_whoami                      : 215..233
cmd_help                        : 234..288
cmd_about                       : 289..302
cmd_zoom (/meet)                : 303..487
cmd_sync_meetings               : 488..518
cmd_check_expired               : 519..546
cmd_register_list               : 547..658
cmd_all_users                   : 659..770
cmd_start                       : 771..821

_safe_edit_or_fallback          : 822..871

cb_accept                       : 872..894
cb_reject                       : 895..919
cb_ban_toggle                   : 920..945
cb_ban                          : 946..966
cb_unban                        : 967..987
cb_manage_user                  : 988..1010
cb_register_list                : 1011..1138
cb_noop                         : 1139..1144
cb_all_users                    : 1145..1266

cmd_backup                      : 1267..1302
cmd_restore                     : 1303..1324
handle_restore_file             : 1325..1404
```

Catatan singkat:

- Rentang baris di atas adalah 1-indexed dan diambil dari versi file saat ini di workspace (total ~1404 baris).
- Jika Anda mengedit `handlers.py`, rentang baris bisa berubah; jalankan scan ulang bila perlu (saya bisa bantu memperbarui otomatis).
- Untuk navigasi cepat, saya juga menyimpan file terpisah `handlers_features_with_lines.md` yang berisi penjelasan lebih lengkap dan konteks tiap fungsi.

Generated on: 2025-10-28
