# Zoom Telebot

[![Python](https://img.shields.io/badge/Python-3.8+-blue.svg)](https://www.python.org/downloads/)
[![aiogram](https://img.shields.io/badge/aiogram-3-green.svg)](https://github.com/aiogram/aiogram)
[![Docker](https://img.shields.io/badge/Docker-Ready-blue.svg)](https://www.docker.com/)

Bot Telegram yang efisien untuk mengelola rapat Zoom, dirancang dengan fitur-fitur untuk otomatisasi dan kemudahan penggunaan. Dibangun menggunakan `aiogram` dan terintegrasi dengan Zoom via Server-to-Server (S2S) OAuth.

## ✨ Fitur Utama

- **Manajemen Meeting**:
  - **Buat Meeting**: Buat rapat Zoom baru melalui alur interaktif atau perintah cepat (`/meet`).
  - **Hapus Meeting**: Hapus rapat Zoom menggunakan ID-nya (`/zoom_del`).
  - **Sinkronisasi Otomatis**: Sinkronisasi daftar rapat dari Zoom secara berkala dan saat startup.
  - **Cek Kadaluwarsa**: Secara otomatis menandai rapat yang sudah lewat waktu.
  - **Recording Control** (v2.3): Start/Stop/Pause/Resume dengan smart dual-payload start feature dan database status tracking.
- **Persistent Sessions** (v2.4): User sessions disimpan ke database - lanjut dari mana user berhenti setelah bot restart!
- **URL Shortener** (v2.4): Multi-provider dengan TinyURL API key integration (secure, tidak web scraping)
- **Shortener Config Migration** (v2.5): Automatic migration system untuk `shorteners.json` dengan data preservation & backup
- **System Hardening** (v2026.02.17):
  - **Graceful Shutdown**: Support clean exit pada Windows (`SIGBREAK`) dan Linux.
  - **Safe Migrations**: Lock file mechanism untuk mencegah concurrent database operations.
  - **Centralized Logging**: Log terpusat dengan rotasi harian dan format konsisten.
  - **Automated Testing**: Test suite menggunakan `pytest` untuk validasi FSM flow.
  - **Dependency Audit**: Cek otomatis kerentanan security pada startup.
- **Manajemen User**:
  - **Sistem Peran**: `owner`, `admin`, dan `user` dengan hak akses yang berbeda.
  - **Sistem Whitelist**: Admin dapat menyetujui (`whitelisted`), menolak, atau memblokir (`banned`) pengguna baru.
  - **Pendaftaran**: Pengguna baru otomatis masuk ke dalam daftar tunggu persetujuan.
- **URL Shortener**:
  - **Multi-Provider**: Dukungan untuk S.id, Bitly, dan TinyURL (dengan official API key).
  - **Konfigurasi Dinamis**: Tambah provider baru dengan mengedit file `shorteners.json` tanpa mengubah kode.
  - **Alias Kustom**: Mendukung alias kustom jika provider menyediakannya.
- **Backup & Restore**:
  - `/backup`: Buat file backup `.zip` berisi database (SQL) dan konfigurasi shortener.
  - `/restore`: Pulihkan data bot dari file backup.
- **Deployment**:
  - **Docker Ready**: Konfigurasi lengkap menggunakan Docker Compose untuk lingkungan `development` dan `production`.
  - **Makefile**: Perintah `make` untuk menyederhanakan manajemen Docker.
  - **Development Helper**: Skrip `dev.py` dengan fitur *auto-restart* saat ada perubahan file.

## 📚 Dokumentasi

Untuk informasi lebih lengkap tentang project ini, silakan baca dokumentasi berikut:

### **📌 Quick Start**
- **[🚀 START HERE](START_HERE.md)** - Entry point untuk pengguna baru
- **[📑 DOCS INDEX](DOCS_INDEX.md)** - Navigation hub untuk semua dokumentasi

### **📖 Core Documentation**
- **[📖 Overview Project](docs/README.md)** - Deskripsi lengkap bot dan fitur-fiturnya
- **[🚀 Panduan Instalasi](docs/INSTALLATION.md)** - Cara install dan menjalankan bot (PC langsung, Docker run, Docker Compose)
- **[💻 Development Guide](docs/DEVELOPMENT.md)** - Panduan development, testing, dan best practices
- **[🏗️ Architecture Guide](docs/ARCHITECTURE.md)** - Modular architecture dan multi-developer collaboration
- **[🤖 AI Context Reference](context.md)** - Referensi untuk AI assistant (internal use)

### **📖 Core Documentation**
- **[📖 Overview Project](docs/README.md)** - Deskripsi lengkap bot dan fitur-fiturnya
- **[🚀 Panduan Instalasi](docs/INSTALLATION.md)** - Cara install dan menjalankan bot (PC langsung, Docker run, Docker Compose)
- **[💻 Development Guide](docs/DEVELOPMENT.md)** - Panduan development, testing, dan best practices
- **[🏗️ Architecture Guide](docs/ARCHITECTURE.md)** - Modular architecture dan multi-developer collaboration
- **[🤖 AI Context Reference](context.md)** - Referensi untuk AI assistant (internal use)

### **🛡️ Security & Maintenance**
- **Dependency Audit**: Bot otomatis mengecek vulnerability saat startup (via `pip-audit`).
- **Log Rotation**: Logs disimpan di `logs/` dan dirotasi setiap hari (retensi 30 hari).
- **Graceful Shutdown**: Tekan `Ctrl+C` (atau kirim `SIGTERM`) untuk mematikan bot dengan aman tanpa merusak database.
- **[📖 Migration Index](docs/MIGRATION_INDEX.md)** - Quick navigation for all migration-related docs
- **[📚 Complete Migration Guide](docs/DATABASE_MIGRATIONS.md)** - Comprehensive guide with examples, troubleshooting, and best practices
- **[🔧 Schema Reference](db/schema.sql)** - Production SQL schema definition with inline documentation

### **🆕 Feature Documentation**
- **[🔄 Shortener Migration Guide](docs/SHORTENER_MIGRATION.md)** - Automatic config migration system
- **[📊 Migration Summary](docs/MIGRATION_SUMMARY.md)** - Technical implementation details
- **[💾 Backup/Restore Fix](docs/BACKUP_RESTORE_FIX.md)** - Bug fixes dan verification
- **[📋 Documentation Cleanup](docs/CLEANUP_REPORT.md)** - File organization report

## 🚀 Memulai

### Prasyarat

- [Docker](https://www.docker.com/products/docker-desktop/) & [Docker Compose](https://docs.docker.com/compose/install/)
- [Python](https://www.python.org/downloads/) 3.8+ (untuk development lokal)
- Kredensial aplikasi Zoom Server-to-Server OAuth.
- Token Bot dari [@BotFather](https://t.me/botfather).

---

### 🐳 Instalasi Docker (Direkomendasikan)

1.  **Clone Repository**
    ```bash
    git clone https://github.com/rezytijo/Zoom-Telebot.git
    cd Zoom-Telebot
    ```

2.  **Konfigurasi Environment**
    Salin file `.env.example` menjadi `.env` dan isi nilainya.
    ```bash
    cp .env.example .env
    nano .env # atau editor teks lainnya
    ```

3.  **Jalankan Bot**
    Gunakan Docker Compose untuk membangun image dan menjalankan kontainer.
    ```bash
    docker compose up --build -d
    ```

4.  **Lihat Log**
    ```bash
    docker compose logs -f
    ```

---

### 💻 Development Lokal

1.  **Clone Repository & Setup venv**
    ```bash
    git clone https://github.com/rezytijo/Zoom-Telebot.git
    cd Zoom-Telebot
    python -m venv .venv
    source .venv/bin/activate # atau .venv\Scripts\activate di Windows
    ```

2.  **Install Dependensi**
    ```bash
    pip install -r requirements.txt
    ```

3.  **Konfigurasi Environment**
    Salin `.env.example` menjadi `.env` dan isi nilainya.
    ```bash
    cp .env.example .env
    nano .env
    ```

4.  **Jalankan Bot (dengan Development Runner)**
    Skrip `run.py` mendukung berbagai opsi command line untuk memudahkan development.
    ```bash
    # Jalankan bot normal
    python run.py

    # Cek konfigurasi sebelum menjalankan bot
    python run.py --check-config

    # Jalankan dengan debug logging
    python run.py --log-level DEBUG

    # Lihat semua opsi yang tersedia
    python run.py --help

    # Lihat versi bot
    python run.py --version
    ```

    **Menjalankan Test Suite:**
    ```bash
    # Install dependencies testing
    pip install pytest pytest-asyncio

    # Jalankan test
    python -m pytest tests/
    ```

    Alternatif: Gunakan `dev.py` untuk auto-restart saat development:
    ```bash
    python dev.py run --watch
    ```

## ⚙️ Konfigurasi

Semua konfigurasi diatur melalui file `.env`.

| Variabel               | Deskripsi                                                               | Wajib      |
| ---------------------- | ----------------------------------------------------------------------- | ---------- |
| `TELEGRAM_TOKEN`       | Token bot dari @BotFather.                                              | **Ya**     |
| `INITIAL_OWNER_ID`     | ID Telegram unik milik owner bot.                                       | **Ya**     |
| `ZOOM_CLIENT_ID`       | Client ID dari aplikasi S2S OAuth Zoom.                                 | **Ya**     |
| `ZOOM_CLIENT_SECRET`   | Client Secret dari aplikasi S2S OAuth Zoom.                             | **Ya**     |
| `ZOOM_ACCOUNT_ID`      | Account ID dari akun Zoom Anda.                                         | **Ya**     |
| `TINYURL_API_KEY`      | API key untuk TinyURL shortener service.                                 | Tidak      |
| `DATABASE_URL`         | URL koneksi database. Default: `sqlite+aiosqlite:///./data/zoom_telebot.db` | Tidak      |
| `SID_ID` / `SID_KEY`   | Kredensial untuk layanan shortener S.id.                                | Tidak      |
| `BITLY_TOKEN`          | Token akses untuk layanan shortener Bitly.                              | Tidak      |
| `LOG_LEVEL`            | Level logging (DEBUG, INFO, WARNING, ERROR). Default: `INFO`.           | Tidak      |

## 🤖 Perintah Bot

### Perintah Umum
- `/start` - Memulai interaksi dengan bot dan menampilkan menu utama.
- `/help` - Menampilkan daftar perintah yang tersedia.
- `/about` - Menampilkan informasi tentang bot.
- `/whoami` - Menampilkan informasi ID Telegram dan status Anda.

### Fitur Meeting & Shortener
- `/meet <topik> <tgl> <waktu>` - Membuat meeting Zoom dengan cepat. Mendukung *batch creation*.
- `/zoom_del <meeting_id>` - Menghapus meeting Zoom. Mendukung *batch deletion*.
- **Tombol "Create Meeting"**: Membuat meeting melalui alur interaktif.
- **Tombol "Short URL"**: Membuat URL pendek dari link apa pun.

### Perintah Admin & Owner
- `/register_list` - Menampilkan daftar pengguna yang menunggu persetujuan.
- `/all_users` - Mengelola semua pengguna (mengubah peran, status, atau menghapus).
- `/sync_meetings` - Memulai sinkronisasi data meeting dari Zoom secara manual.
- `/check_expired` - Memeriksa dan menandai meeting yang sudah kadaluwarsa.
- `/backup` - Membuat backup data bot.
- `/restore` - Memulihkan data bot dari file backup.

## 🏗️ Struktur Proyek

Proyek ini diorganisir dalam struktur modular untuk maintainability dan scalability:

```
```
BotTelegramZoom/
│
├── 📂 bot/                    # Core Bot Logic
│   ├── __init__.py
│   ├── main.py               # Entry point & startup logic
│   ├── handlers.py           # General message handlers & callbacks
│   ├── cloud_recording_handlers.py # Handler khusus Cloud Recording
│   ├── keyboards.py          # Reply & Inline keyboards
│   ├── auth.py               # Role-based access control (RBAC)
│   ├── middleware.py         # Logging & Auth middleware
│   ├── fsm_storage.py        # Database-backed FSM storage
│   ├── logger.py             # Centralized logging configuration
│   ├── background_tasks.py   # Background task manager
│   └── utils/
│       └── loading.py        # Loading indicator utility
│
├── 📂 zoom/                   # Zoom Integration
│   ├── __init__.py
│   └── zoom.py               # Zoom API client
│
├── 📂 db/                     # Database Layer
│   ├── __init__.py
│   └── db.py                 # Async SQLite operations
│
├── 📂 config/                 # Configuration
│   ├── __init__.py
│   └── config.py             # Pydantic settings management
│
├── 📂 scripts/               # Utility Scripts
│   ├── check_dependencies.py # Security & update checker
│   ├── run_migration.py      # Manual DB migration
│   ├── setup.py              # Environment setup
│   ├── dev.py                # Development runner
│   └── ...
│
├── 📂 tests/                 # Automated Tests
│   ├── conftest.py           # Pytest fixtures
│   └── test_fsm_handlers.py  # FSM flow tests
│
├── 📂 reports/               # Audit Reports
│   ├── codebase-analysis...
│   ├── improvement-roadmap...
│   └── security-audit...
│
├── 📂 docker/                # Docker Config
│   ├── Dockerfile
│   └── docker-entrypoint.sh
│
├── 📂 logs/                  # Application Logs (Rotated daily)
├── 📂 data/                  # Persistent Data (JSON configs)
├── 📂 docs/                  # Detailed Documentation
│
├── 📄 .env                   # Environment secrets
├── 📄 requirements.txt       # Dependencies
├── 📄 run.py                 # Production runner
└── 📄 README.md              # Main documentation
```

### 📝 Deskripsi Folder & File

#### **bot/** - Bot Core Logic
Berisi semua logika bot Telegram dan handlers:
- **main.py**: Inisialisasi bot, setup dispatcher, start polling
- **handlers.py**: Message handlers utama (/start, /meet, dll)
- **cloud_recording_handlers.py**: Handler eksplisit untuk manajemen Cloud Recording
- **keyboards.py**: Tombol dan keyboard layouts (Reply & Inline)
- **auth.py**: Sistem role-based access (owner, admin, user) & whitelist
- **middleware.py**: Logging request, rate limiting, dan auth checks
- **fsm_storage.py**: Custom storage agar session user persist di database
- **logger.py**: Konfigurasi logging terpusat (console + file rotation)
- **background_tasks.py**: Task manager untuk sync Zoom, cleanup, dll
- **utils/loading.py**: Utility untuk menampilkan status "Processing..."

#### **zoom/** - Zoom API Integration
Klien untuk berkomunikasi dengan Zoom API:
- **zoom.py**: OAuth s2s, meeting CRUD logic, recording management

#### **db/** - Database Layer
Abstraksi database SQLite (asynchronous):
- **db.py**: Semua query SQL untuk users, meetings, shortlinks

#### **config/** - Configuration
- **config.py**: Validasi environment variables menggunakan Pydantic

#### **shortener/** - URL Shortener Service
- **shortener.py**: Logic multi-provider (TinyURL, S.id, Bitly)

#### **scripts/** - Utilities & Maintenance
Script pembantu untuk operasi dan maintenance:
- **run_migration.py**: Eksekusi update schema database secara manual
- **check_dependencies.py**: Audit security & update library
- **setup.py**: Validasi environment sebelum start
- **migrate_shorteners.py**: Tool migrasi config shortener (legacy)

#### **tests/** - Automated Testing
Test suite untuk validasi stabilitas:
- **test_fsm_handlers.py**: Test flow pembuatan meeting (Topic > Date > Time)
- **conftest.py**: Konfigurasi fixtures untuk pytest

#### **reports/** - Project Audit
Laporan analisis codebase (Generated by AI):
- **codebase-analysis-report.md**: Overview kualitas & arsitektur
- **improvement-roadmap.md**: Rencana perbaikan sistem
- **security-audit.md**: Hasil audit keamanan

#### **data/** - Persistent Data
Data JSON yang perlu persistensi:
- **shorteners.json**: Konfigurasi dynamic shortener

#### **logs/** - Application Logs
Folder tempat log file disimpan (rotasi harian `zoom-telebot.YYYY-MM-DD.log`)

### 🔄 Data Flow

```
                                  ┌─────────────────┐
                                  │  Telegram User  │
                                  └────────┬────────┘
                                           │
                                           ▼
┌─────────────────────────────────────────────────────────────────────────────────┐
│  Bot Engine (bot/)                                                              │
│                                                                                 │
│  ┌──────────────────┐    ┌───────────────────────────────────────────────┐      │
│  │ middleware.py    │──▶ │ handlers.py / keybords.py                     │      │
│  │ (Auth/Log/Rate)  │    │ (Command Processing & Logic)                  │      │
│  └──────────────────┘    └──────┬────────────┬─────────────┬─────────────┘      │
│                                 │            │             │                    │
│                                 ▼            ▼             ▼                    │
│                          ┌──────────┐  ┌──────────┐  ┌──────────────┐           │
│                          │ db/db.py │  │ auth.py  │  │ shortener/   │           │
│                          └────┬─────┘  └──────────┘  └─────┬────────┘           │
│                               │                            │                    │
│  ┌──────────────────┐         │                            │                    │
│  │ background_tasks │─────────┤                            ▼                    │
│  │ (Sync/Cleanup)   │         ▼                      ┌──────────────┐           │
│  └─────────┬────────┘    ┌──────────┐                │ External APIs│           │
│            │             │ SQLite   │                │ (TinyURL/etc)│           │
│            │             └──────────┘                └──────────────┘           │
│            │                                                                    │
│            ▼                                                                    │
│      ┌────────────┐                                                             │
│      │ zoom/      │ ◀──(OAuth S2S)──▶  [ Zoom API ]                            │
│      └────────────┘                                                             │
└─────────────────────────────────────────────────────────────────────────────────┘
```

### 🔐 Security Layers

1. **Authentication (auth.py)**:
   - Role-based access control (owner, admin, user)
   - Whitelist system untuk new users
   - Ban/unban management

2. **Middleware (middleware.py)**:
   - Auth checks sebelum execution
   - Rate limiting untuk prevent abuse
   - Request/response logging

3. **Database Security (db/db.py)**:
   - Prepared statements untuk prevent SQL injection
   - User role validation
   - Data encryption untuk sensitive info

### 📊 Development vs Production

**Development**:
```bash
# Environment
DEFAULT_MODE=polling        # Polling untuk testing
DATABASE_URL=sqlite://      # SQLite lokal
LOG_LEVEL=DEBUG             # Verbose logging

# Runner
python dev.py run --watch   # Auto-restart on file changes
```

**Production**:
```bash
# Environment
DEFAULT_MODE=webhook        # Webhook untuk Telegram updates
DATABASE_URL=postgresql://  # PostgreSQL production
LOG_LEVEL=INFO              # Normal logging


# Runner
docker compose up -d        # Docker Compose orchestration
```

## ✨ Recent Updates (June 2026)

### Version v2026.06.24 - Zoom Security Update

#### 🔒 Security & Passcode
- **Automatic Passcode Extraction**: Merespons kebijakan Zoom terbaru yang mewajibkan Passcode atau Waiting Room, bot sekarang mengekstrak dan menampilkan Passcode secara eksplisit pada balasan ke pengguna ketika meeting berhasil dibuat.

---

## ✨ Recent Updates (February 2026)
### Version v2026.02.17 - System Hardening & Security Audit

#### 🆕 System Hardening
- **Graceful Shutdown**: Implementasi signal handling yang robust untuk Windows (`SIGBREAK`) dan Linux. Memastikan `bot.lock` terhapus saat exit.
- **Safe Migrations**: Mencegah race condition saat startup dengan mekanisme lock file.
- **Centralized Logging**: Standardisasi logging ke `logs/` dengan rotasi harian.
- **Loading Indicators**: Feedback "⏳ Processing..." yang konsisten untuk operasi lama (Zoom sync, PDF generation).

#### 🛡️ Security Audit
- **Dependency Checker**: Script otomatis `scripts/check_dependencies.py` yang berjalan saat startup untuk mendeteksi library yang vuln (menggunakan `pip-audit`).
- **Alert System**: Notifikasi ke Admin jika ditemukan critical vulnerability.

#### 🧪 Automated Testing
- **FSM Tests**: Test suite awal untuk memvalidasi alur pembuatan meeting (Topic -> Date -> Time).
- **Test Runner**: Integrasi dengan `pytest` dan `pytest-asyncio`.

---

## ✨ Recent Updates (December 2025)

### Version 2.5.0 - Shortener Config Migration & Documentation Cleanup (December 19, 2025)

#### 🆕 Automatic Shortener Config Migration
- **Auto-Detection**: Deteksi otomatis saat `shorteners.json` butuh update ke struktur terbaru
- **Data Preservation**: 100% user customizations tetap tersimpan (API keys, headers, custom providers)
- **Automatic Backup**: Backup otomatis sebelum migrasi ke `shorteners.json.backup_TIMESTAMP`
- **CLI Tool**: `scripts/migrate_shorteners.py` untuk manual migration dengan preview mode
- **Interactive Demo**: `scripts/demo_migration.py` dengan 7 learning scenarios
- **Public API**: `migrate_shortener_config()` function untuk programmatic use

**Usage**:
```bash
# Automatic (saat bot startup)
python run.py  # Migration berjalan otomatis jika diperlukan

# Manual dengan script
python scripts/migrate_shorteners.py --preview  # Preview changes
python scripts/migrate_shorteners.py            # Execute migration

# Interactive demo
python scripts/demo_migration.py                # Learn about migration
```

**Benefit**: Schema updates tidak akan menghapus kustomisasi user!

#### 🔧 Backup/Restore Fix
- **Bug Fixed**: Indentation error di `cmd_backup` handler
- **Decorator Spacing**: Proper spacing between exception handlers
- **Verification**: Full workflow tested (backup creation, ZIP extraction, restore)
- **Status**: ✅ All functions working correctly

#### 📚 Documentation Cleanup
- **Organized Structure**: 4 root files (essential) + 16 docs files (reference)
- **Navigation Hub**: `DOCS_INDEX.md` untuk root, `docs/INDEX.md` untuk docs folder
- **No Redundancy**: 0 duplicate files, clean organization
- **Complete Guides**: 600+ lines of migration documentation

---

### Version 2.4.0 - Persistent Sessions & TinyURL API Integration

#### 🆕 Persistent User Sessions
- **Database-backed FSM Storage**: User sessions sekarang disimpan di database (`fsm_states` table)
- **Session Recovery**: Saat bot restart, user kembali ke state terakhir mereka
- **No User Interruption**: Users tidak perlu restart dari `/start` 
- **Implementation**: `bot/fsm_storage.py` - Custom FSM storage class

**Benefit**: Users dapat melanjutkan workflow mereka tanpa kehilangan progress!

#### 🆕 TinyURL API Integration  
- **Official API Endpoint**: Menggunakan `https://api.tinyurl.com/create` dengan Bearer token
- **API Key Authentication**: Aman disimpan di `.env` (tidak dicommit ke repo)
- **Structured API Calls**: JSON request/response format
- **Reliability**: Lebih robust dibanding web scraping

**Configuration**:
```bash
TINYURL_API_KEY=qwertyuiolkjhgfdsqwertyuiopmkjnhbgvfcds
TINYURL_API_URL=https://api.tinyurl.com/create
```

#### 📊 Database Schema Updates
- **New Table**: `fsm_states` untuk persistent session storage
- **Columns**: `user_id`, `state`, `data`, `updated_at`
- **Auto-migration**: Migrasi berjalan otomatis saat bot startup

---

Proyek ini dilisensikan di bawah [Lisensi MIT](LICENSE).