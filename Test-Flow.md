# Test-Flow.md - Panduan Testing Manual Bot Telegram SOC

## 📋 Daftar Isi
1. [Persiapan Testing](#persiapan-testing)
2. [Fitur User Management](#fitur-user-management)
3. [Fitur Meeting Management](#fitur-meeting-management)
4. [Fitur URL Shortener](#fitur-url-shortener)
5. [Command Administratif](#command-administratif)
6. [Error Handling & Edge Cases](#error-handling--edge-cases)

---

## 🔧 Persiapan Testing

### Prerequisites
- Bot Telegram sudah running (`python main.py`)
- Minimal 2 akun Telegram untuk testing (1 owner, 1 user biasa)
- Zoom API credentials sudah dikonfigurasi
- Database SQLite sudah terinisialisasi
- File `.env` dengan konfigurasi lengkap

### Setup Awal
1. **Owner Setup**: Pastikan `INITIAL_OWNER_ID` di `.env` sudah benar
2. **Database**: Jalankan `python main.py` pertama kali untuk inisialisasi DB
3. **Shortener Config**: Pastikan `shorteners.json` memiliki provider yang aktif

---

## 👥 Fitur User Management

### 1. Registrasi User Baru
**Command**: `/start` (dari user baru)

**Expected Flow**:
```
User: /start
Bot: Selamat datang! Anda belum terdaftar. Mengirim permintaan registrasi...
Bot: Permintaan registrasi dikirim ke admin untuk approval.
```

**Verification**:
- Owner/Admin menerima notifikasi registrasi
- Cek database: user status = "pending"

### 2. Approval User (Owner/Admin Only)
**Trigger**: Owner/Admin klik tombol "✅ Terima" pada notifikasi registrasi

**Expected Flow**:
```
Bot: ✅ User @username telah diterima dan di-whitelist.
User: Status Anda telah diubah menjadi whitelisted.
```

**Verification**:
- User menerima pesan konfirmasi
- User bisa akses menu utama
- Database: status = "whitelisted"

### 3. Reject User (Owner/Admin Only)
**Trigger**: Owner/Admin klik tombol "❌ Tolak" pada notifikasi registrasi

**Expected Flow**:
```
Bot: ❌ User @username telah ditolak.
User: Maaf, permintaan registrasi Anda ditolak.
```

**Verification**:
- User menerima pesan penolakan
- Database: status = "rejected"

### 4. Ban/Unban User (Owner Only)
**Command**: `/all_users` → pilih user → klik "⛔ Banned"

**Expected Flow**:
```
Bot: User @username telah di-ban.
User: Anda telah di-ban dari bot ini.
```

**Unban Flow**:
```
Bot: User @username telah di-unban.
User: Status ban Anda telah dicabut.
```

**Verification**:
- User tidak bisa akses fitur saat banned
- Database: status = "banned"/"whitelisted"

### 5. Role Management (Owner Only)
**Command**: `/all_users` → pilih user → "🔄 Change Role"

**Available Roles**:
- 👑 Owner
- 👨‍💼 Admin
- 👤 User
- 👤 Guest

**Expected Flow**:
```
Bot: Role user @username berhasil diubah menjadi Admin.
```

**Verification**:
- User dengan role admin bisa approve user
- Owner bisa semua fitur

---

## 📅 Fitur Meeting Management

### 1. Create Meeting Flow
**Trigger**: Klik "📝 Create Meeting" di menu utama

**Step-by-Step Flow**:
```
Step 1: Kirim Topic
Bot: **Buat Meeting - Step 1/3**
     _Silakan kirim Topic Meeting:_

User: Rapat Koordinasi SOC
Bot: **Step 2/3**
     _Kapan diadakan?_
     Format: DD-MM-YYYY atau '31-12-2025' atau tulis seperti '31 Desember 2025' (Bulan dalam bahasa Indonesia).

Step 2: Kirim Tanggal
User: 25-10-2025
Bot: **Step 3/3**
     _Masukkan waktu (format 24-jam WIB) contohnya:_ 14:30

Step 3: Kirim Waktu
User: 14:30
Bot: **Konfirmasi pembuatan meeting:**
     📅 **Topik:** Rapat Koordinasi SOC
     ⏰ **Waktu (WIB):** 25 Oktober 2025 14:30

     [Konfirmasi] [Batal]

Step 4: Konfirmasi
User: Klik "Konfirmasi"
Bot: **Membuat meeting... Mohon tunggu.**
     (lalu)
     **Selamat siang Bapak/Ibu/Rekan-rekan**
     **Berikut disampaikan Kegiatan Rapat Koordinasi SOC pada:**

     📆  Jumat, 25 Oktober 2025
     ⏰  14:30 WIB – selesai
     🔗  https://zoom.us/j/123456789
     🔗 Buat Short URL
```

**Test Cases**:
- ✅ Format tanggal: `25-10-2025`, `25 Oktober 2025`, `25/10/2025`
- ✅ Format waktu: `14:30`, `09:15`, `23:59`
- ✅ Validasi: waktu masa lalu ditolak
- ✅ Cancel flow: klik "Batal" → kembali ke step 1

### 2. List Meetings
**Trigger**: Klik "📅 List Upcoming Meeting"

**Expected Output**:
```
📅 **Daftar Meeting Mendatang:**

1. **Rapat Koordinasi SOC**
   📆 Jumat, 25 Oktober 2025 14:30 WIB
   🔗 [Join Meeting](https://zoom.us/j/123456789)
   👤 Dibuat oleh: @username

   [🔄 Refresh] [🏠 Kembali ke Menu Utama]
```

**Test Cases**:
- ✅ Tampilkan meeting aktif saja
- ✅ Format tanggal Indonesia lengkap
- ✅ Link Zoom langsung clickable
- ✅ Refresh button berfungsi

### 3. Sync Meetings (Admin Only)
**Command**: `/sync_meetings`

**Expected Output**:
```
🔄 Syncing meetings from Zoom...
✅ Sync completed: {'created': 2, 'updated': 1, 'skipped': 0}
```

**Verification**:
- Database terupdate dengan meeting dari Zoom
- Background sync berjalan setiap 30 menit

---

## 🔗 Fitur URL Shortener

### 1. Short URL Flow
**Trigger**: Klik "🔗 Short URL" di menu utama

**Step-by-Step Flow**:
```
Bot: 🔗 **Short URL Generator**
     Kirim URL yang ingin di-shorten:

User: https://www.google.com/search?q=telegram+bot
Bot: 📋 **URL:** https://www.google.com/search?q=telegram+bot

     Pilih provider untuk membuat short URL:

     🔗 S.id
     🔗 TinyURL
     🔗 Bitly
     ❌ Batal

User: Klik "🔗 S.id"
Bot: 🔗 **Memproses...**
     (lalu)
     ✅ **Short URL berhasil dibuat!**

     📎 **Original:** https://www.google.com/search?q=telegram+bot
     🔗 **Short URL:** https://s.id/abc123

     [🔗 Buat Short URL Lagi] [🏠 Kembali ke Menu Utama]
```

### 2. Custom Alias (Opsional)
**Trigger**: Setelah pilih provider, bot akan tanya custom alias

```
Bot: ❓ **Custom URL Alias**
     Apakah Anda ingin menggunakan custom alias?

     Contoh: my-link, soc-meeting, dll.

     [Ya, Custom] [Tidak, Random]
```

**Custom Flow**:
```
User: Klik "Ya, Custom"
Bot: ✏️ **Custom Alias**
     Kirim alias yang diinginkan (tanpa spasi, max 20 karakter):

User: soc-meeting-2025
Bot: ✅ Alias tersedia! Memproses...
     (lalu)
     ✅ **Short URL berhasil dibuat!**

     📎 **Original:** https://zoom.us/j/123456789
     🔗 **Short URL:** https://s.id/soc-meeting-2025
```

### 3. Provider Management
**File**: `shorteners.json`

**Test Cases**:
- ✅ Provider aktif/non-aktif
- ✅ Error handling jika API down
- ✅ Custom alias validation (no spaces, unique)
- ✅ Fallback ke random jika custom gagal

---

## ⚙️ Command Administratif

### 1. `/start` - Welcome Message
**Expected Output**:
```
👋 Selamat datang, @username!

Pilih aksi yang ingin dilakukan:

📝 Create Meeting
📅 List Upcoming Meeting
🔗 Short URL
```

### 2. `/help` - Help Command
**Expected Output**:
```
🆘 **Bantuan Bot SOC**

**Perintah Utama:**
• /start - Menu utama bot
• /help - Tampilkan bantuan ini
• /whoami - Info akun Anda
• /about - Tentang bot ini

**Fitur Admin (Owner/Admin only):**
• /all_users - Kelola semua user
• /sync_meetings - Sync meeting dari Zoom
• /zoom_del - Hapus meeting Zoom

**Cara Penggunaan:**
1. Klik "Create Meeting" untuk buat meeting baru
2. Klik "List Meetings" untuk lihat meeting aktif
3. Klik "Short URL" untuk shorten link

📞 **Support:** Hubungi @owner_username
```

### 3. `/whoami` - User Info
**Expected Output**:
```
👤 **Info Akun Anda:**

🆔 **Telegram ID:** 123456789
👤 **Username:** @testuser
🎭 **Role:** User
📊 **Status:** Whitelisted
⏰ **Bergabung:** 25 Oktober 2025 10:30 WIB
```

### 4. `/about` - About Bot
**Expected Output**:
```
🤖 **Bot Telegram SOC**

**Versi:** 1.0.0
**Framework:** Aiogram + Zoom API
**Database:** SQLite + SQLAlchemy
**Features:**
• ✅ Meeting Management (Zoom)
• ✅ User Management & Whitelist
• ✅ URL Shortener (Multi-provider)
• ✅ Role-based Access Control

📅 **Dibuat:** Oktober 2025
👨‍💻 **Developer:** SOC Team
```

### 5. `/zoom` - Zoom Status
**Expected Output**:
```
🔍 **Status Zoom Integration:**

✅ **Zoom API:** Connected
📊 **Total Meetings:** 5
⏰ **Last Sync:** 25 Oktober 2025 14:30 WIB
🔄 **Auto Sync:** Every 30 minutes
```

### 6. `/all_users` - User Management (Owner Only)
**Expected Output**:
```
👥 **Daftar Semua User (Total: 3):**

1. 👑 **@owner** (Owner) - Whitelisted
   [🗑️ Delete] [🔄 Change Role] [📊 Change Status]

2. 👨‍💼 **@admin** (Admin) - Whitelisted
   [🗑️ Delete] [🔄 Change Role] [📊 Change Status]

3. 👤 **@user** (User) - Pending
   [🗑️ Delete] [🔄 Change Role] [📊 Change Status]
```

### 7. `/sync_meetings` - Manual Sync (Admin Only)
**Expected Output**:
```
🔄 Syncing meetings from Zoom...
✅ Sync completed: {'created': 2, 'updated': 1, 'skipped': 0}
```

### 8. `/zoom_del` - Delete Zoom Meeting (Owner Only)
**Command**: `/zoom_del <meeting_id>`

**Expected Flow**:
```
User: /zoom_del 123456789
Bot: 🔍 Mencari meeting dengan ID: 123456789
Bot: 🗑️ **Konfirmasi Hapus Meeting:**

     📝 **Topic:** Rapat Koordinasi SOC
     📅 **Waktu:** 25 Oktober 2025 14:30 WIB

     Apakah yakin ingin menghapus meeting ini?

     [✅ Ya, Hapus] [❌ Batal]
```

---

## 🚨 Error Handling & Edge Cases

### 1. Unauthorized Access
**Test**: User biasa akses `/all_users`
**Expected**: `"❌ Anda tidak memiliki akses ke perintah ini."`

### 2. Invalid Input Format
**Test Cases**:
- Tanggal: `99-99-9999` → `"Format tanggal tidak dikenal"`
- Waktu: `25:99` → `"Format waktu tidak valid"`
- URL: `not-a-url` → `"URL tidak valid"`

### 3. API Failures
**Test**: Zoom API down saat create meeting
**Expected**: `"❌ Gagal membuat meeting: Connection timeout"`

### 4. Database Errors
**Test**: Database corrupted
**Expected**: Graceful error handling dengan retry mechanism

### 5. Rate Limiting
**Test**: Spam commands dalam waktu singkat
**Expected**: Rate limit dengan cooldown message

### 6. Network Issues
**Test**: Internet connection lost
**Expected**: Proper error messages dan retry options

---

## 📊 Checklist Testing

### ✅ Functional Testing
- [ ] User registration & approval flow
- [ ] Meeting creation (all date/time formats)
- [ ] Meeting listing & refresh
- [ ] URL shortening (all providers)
- [ ] Role-based permissions
- [ ] Admin commands functionality

### ✅ UI/UX Testing
- [ ] Inline keyboards responsive
- [ ] Markdown formatting correct
- [ ] Indonesian language consistency
- [ ] Error messages user-friendly

### ✅ Integration Testing
- [ ] Zoom API integration
- [ ] Database operations
- [ ] Shortener API calls
- [ ] Background sync functionality

### ✅ Security Testing
- [ ] Authorization checks
- [ ] Input validation
- [ ] SQL injection prevention
- [ ] XSS protection

### ✅ Performance Testing
- [ ] Response time < 3 seconds
- [ ] Memory usage reasonable
- [ ] Database query optimization
- [ ] Concurrent user handling

---

## 🐛 Bug Report Template

**Title:** [BUG] Brief description

**Steps to Reproduce:**
1. Go to '...'
2. Click on '....'
3. Scroll down to '....'
4. See error

**Expected Behavior:**
What should happen

**Actual Behavior:**
What actually happened

**Environment:**
- Bot Version: 1.0.0
- Python Version: 3.9
- OS: Windows 11
- Database: SQLite

**Additional Context:**
Any other information about the problem

---

## 📞 Support & Troubleshooting

### Common Issues:
1. **Bot tidak merespons**: Check bot token & internet connection
2. **Zoom API error**: Verify credentials in `.env`
3. **Database error**: Check file permissions & disk space
4. **Shortener failed**: Check provider API status

### Debug Commands:
- `/zoom` - Check Zoom integration status
- `/sync_meetings` - Manual sync meetings
- Check logs in terminal for detailed errors

---

*Dokumen ini dibuat untuk testing manual Bot Telegram SOC. Update sesuai dengan perubahan fitur baru.*</content>
<parameter name="filePath">c:\Users\primall\OneDrive - Kementerian Komunikasi dan Informatika\Documents\Kantor\Program\BotTelegramSOC\Test-Flow.md