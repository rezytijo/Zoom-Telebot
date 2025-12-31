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

### **🗄️ Database & Migration**
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
BotTelegramZoom/
│
├── 📂 bot/                    # Core Bot Logic & Handlers
│   ├── __init__.py
│   ├── main.py               # Titik masuk utama & initialization bot
│   ├── handlers.py           # Semua message handlers, callback queries, commands
│   ├── keyboards.py          # ReplyKeyboard & InlineKeyboard definitions
│   ├── auth.py               # Authentication & authorization system
│   ├── middleware.py         # Middleware untuk logging, auth checks, rate limiting
│   ├── fsm_storage.py        # Database-backed FSM storage untuk persistent sessions
│   └── __pycache__/
│
├── 📂 zoom/                   # Zoom API Integration
│   ├── __init__.py
│   ├── zoom.py               # Zoom API client (OAuth, meeting CRUD, recording)
│   └── __pycache__/
│
├── 📂 db/                     # Database Layer
│   ├── __init__.py
│   ├── db.py                 # Database operations (user, meeting, shortener)
│   └── __pycache__/
│
├── 📂 config/                 # Configuration Management
│   ├── __init__.py
│   ├── config.py             # Settings dataclass, environment parsing, defaults
│   └── __pycache__/
│
├── 📂 c2/                     # C2 Framework Integration (Sliver)
│   ├── __init__.py
│   ├── sliver_zoom_c2.py     # Sliver C2 client untuk remote agent control
│   └── __pycache__/
│
├── 📂 shortener/             # URL Shortener Service
│   ├── __init__.py
│   ├── shortener.py          # Multi-provider shortener (TinyURL, S.id, Bitly)
│   └── __pycache__/
│
├── 📂 api/                    # API Server (Optional)
│   ├── __init__.py
│   ├── api_server.py         # FastAPI/aiohttp server untuk webhooks, API endpoints
│   └── __pycache__/
│
├── 📂 agent/                  # Agent Management (Optional)
│   ├── __init__.py
│   ├── todo_agent.md         # Documentation untuk agent deployment
│   └── __pycache__/
│
├── 📂 scripts/               # Utility & Setup Scripts
│   ├── __init__.py
│   ├── setup.py              # Initial setup & environment validation
│   └── dev.py                # Development runner (alternative untuk run.py)
│
├── 📂 docker/                # Docker Configuration
│   ├── __init__.py
│   ├── Dockerfile            # Docker image definition
│   └── docker-entrypoint.sh  # Entry point script untuk container
│
├── 📂 c2_server/             # C2 Server Setup (Optional)
│   ├── admin.cfg             # C2 server admin config
│   ├── *.bat                 # Windows batch scripts untuk setup
│   ├── README_Windows.md     # Setup guide untuk Windows
│   ├── implants/             # Pre-built implants (dummy_agent.bat)
│   ├── logs/                 # C2 server logs
│   └── generate_implants_api.py  # Script untuk generate implants
│
├── 📂 data/                  # Persistent Data
│   ├── shorteners.json       # Dynamic config untuk URL shortener providers
│   └── shorteners.json.back  # Backup shorteners.json
│
├── 📂 docs/                  # Documentation
│   ├── __init__.py
│   ├── README.md             # Project overview & quick start
│   ├── INSTALLATION.md       # Detailed installation guide
│   ├── DEVELOPMENT.md        # Development guide & best practices
│   └── C2_SETUP_GUIDE.md     # Detailed C2 Framework setup
│
├── 📂 logs/                  # Application Logs
│   └── *.log                 # Log files (created at runtime)
│
├── 📂 tests/                 # Unit Tests
│   ├── __init__.py
│   ├── test_c2.bat           # Windows batch untuk C2 testing
│   ├── test_c2_integration.py # C2 integration tests
│   ├── test_mock_agents.py   # Mock agent tests
│   └── __pycache__/
│
├── 📂 __pycache__/           # Compiled Python (auto-generated)
│
├── 🐳 Dockerfile             # Docker image recipe
├── 🐳 docker-compose.yml     # Docker Compose orchestration
│
├── 📄 .env                   # Environment variables (⚠️ create from .env.example)
├── 📄 .env.example           # Template untuk .env dengan 30+ variables
├── 📄 Makefile               # Shortcuts untuk Docker commands
│
├── 📄 run.py                 # Main entry point (polling mode)
├── 📄 dev.py                 # Development runner dengan auto-restart
├── 📄 demo_c2.py             # Demo script untuk C2 testing
├── 📄 setup_c2.sh            # Shell script untuk C2 server setup
│
├── 📄 requirements.txt        # Python dependencies (poetry-style format)
├── 📄 Readme.md              # Project overview (ini)
├── 📄 context.md             # AI assistant context reference
├── 📄 cleanup_dirs.py         # Cleanup script untuk __pycache__, logs
└── 📄 cleanup_dirs.bat        # Windows batch cleanup script
```

### 📝 Deskripsi Folder & File

#### **bot/** - Bot Core Logic
Berisi semua logika bot Telegram dan handlers:
- **main.py**: Inisialisasi bot, setup dispatcher, start polling/webhook
- **handlers.py**: Semua message handlers (/start, /help, /meet, dll) dan callback queries
- **keyboards.py**: Tombol dan keyboard layouts (ReplyKeyboard, InlineKeyboard)
- **auth.py**: Sistem role-based access (owner, admin, user)
- **middleware.py**: Pre/post processing (auth checks, logging, rate limiting)

#### **zoom/** - Zoom API Integration
Klien untuk berkomunikasi dengan Zoom API:
- **zoom.py**: OAuth token management, meeting CRUD, recording control, auto-sync

#### **db/** - Database Operations
Data layer untuk SQLite/PostgreSQL:
- **db.py**: User management, meeting storage, shortener URLs

#### **config/** - Configuration Management
Parsing dan validasi environment variables:
- **config.py**: Settings dataclass dengan defaults, environment parsing, type safety

#### **c2/** - C2 Framework (Sliver)
Integrasi dengan Sliver C2 Framework untuk remote agent control:
- **sliver_zoom_c2.py**: Client untuk mTLS communication dengan C2 server, agent commands

#### **shortener/** - URL Shortener
Multi-provider URL shortener service:
- **shortener.py**: Support TinyURL, S.id, Bitly dengan dynamic provider config

#### **api/** - API Server (Optional)
Webhook dan REST API endpoints:
- **api_server.py**: FastAPI/aiohttp server untuk webhook events, external API

#### **c2_server/** - C2 Server Setup
C2 Framework server configuration dan utilities:
- **admin.cfg**: C2 server admin configuration
- **generate_implants_api.py**: Otomasi pembuatan implants (agents)
- **implants/**: Pre-built agent executables

#### **data/** - Persistent Data
Data files yang disimpan di disk:
- **shorteners.json**: Dynamic config untuk URL shortener providers (tambah provider tanpa code change)

#### **docs/** - Documentation
Lengkap dokumentasi project:
- **INSTALLATION.md**: Setup lokal, Docker, Docker Compose
- **DEVELOPMENT.md**: Development workflow, testing, best practices
- **C2_SETUP_GUIDE.md**: Detail setup Sliver C2 framework
- **API.md**: API endpoints documentation
- **API_TESTING_GUIDE.md**: Testing guide untuk API

#### **tests/** - Unit Tests
Test suite untuk validasi functionality:
- **test_c2_integration.py**: Tests untuk C2 integration
- **test_mock_agents.py**: Mock agent tests

### 🔄 Data Flow

```
┌──────────────────────┐
│   Telegram User      │
└──────────────┬───────┘
             │
             ▼
┌──────────────────────────────────────────────────────────────────┐
│   bot/handlers.py           │ ← Receive & process user input
├──────────────────────────────────────────────────────────────────┤
│  • /start, /help            │
│  • /meet (create meeting)   │
│  • /zoom_control (agent)    │
│  • Callbacks (keyboards)    │
└──────────────────┬──────┬──────┬──────────────────────────────┘
                  │      │      │
            ┌─────┴──┐  │  ┌─────┴──┐
            ▼        ▼  ▼  ▼        ▼
       ┌────────────┐ ┌──────────────┐ ┌──────────────┐
       │ db/db.py   │ │ zoom/zoom.py │ │ c2/sliver    │
       └──────┬─────┘ └────────┬─────┘ └──────┬───────┘
              ▼                ▼               ▼
         ┌─────────────┐ ┌──────────┐  ┌──────────────┐
         │ SQLite/     │ │ Zoom API │  │ C2 Server    │
         │ PostgreSQL  │ │ (OAuth)  │  │ (mTLS)       │
         └─────────────┘ └──────────┘  └──────────────┘
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

3. **C2 Security (c2/sliver_zoom_c2.py)**:
   - mTLS encryption untuk agent communication
   - Token-based authentication
   - Real-time agent status monitoring

4. **Database Security (db/db.py)**:
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
C2_ENABLED=true             # C2 Framework aktif

# Runner
docker compose up -d        # Docker Compose orchestration
```

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
TINYURL_API_KEY=1dChPWi1S8H1dTzTXbDdc95HT55dqKiUhKagsnFgMQ6BHt4D56EJcGvsrQye
TINYURL_API_URL=https://api.tinyurl.com/create
```

#### 📊 Database Schema Updates
- **New Table**: `fsm_states` untuk persistent session storage
- **Columns**: `user_id`, `state`, `data`, `updated_at`
- **Auto-migration**: Migrasi berjalan otomatis saat bot startup

---

Proyek ini dilisensikan di bawah [Lisensi MIT](LICENSE).