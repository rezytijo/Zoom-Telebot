# Zoom-Telebot SOC Documentation

## 📖 Overview

Zoom-Telebot SOC adalah bot Telegram yang komprehensif untuk mengelola meeting Zoom, dirancang khusus untuk Tim Keamanan Siber (SOC). Bot ini terintegrasi dengan Zoom API dan menyediakan fitur-fitur advanced untuk manajemen meeting, user, dan remote control.

## 🎯 Fitur Utama

### Meeting Management
- ✅ Interactive meeting creation dengan step-by-step flow
- ✅ Batch meeting creation via `/meet` command
- ✅ Meeting control (start/stop) via agents
- ✅ Recording management (start/stop/pause/resume)
- ✅ Meeting editing (topic, date, time)
- ✅ Auto-sync dengan Zoom API setiap 30 menit

### User Management
- ✅ Role-based access control (owner, admin, user, guest)
- ✅ Whitelist system dengan admin approval
- ✅ User search by username/ID
- ✅ Ban/unban user controls
- ✅ Auto-registration saat first use

### C2 Agent System
- ✅ Remote control system untuk meeting control via Sliver C2
- ✅ Real-time agent communication via mTLS
- ✅ Implant-based agent deployment
- ✅ Enhanced security and reliability

### URL Shortener
- ✅ Multi-provider support (TinyURL, S.id, Bitly)
- ✅ Dynamic configuration via JSON
- ✅ Custom aliases support
- ✅ Auto-shorten meeting URLs

### Backup & Restore
- ✅ Full system backup (database + config)
- ✅ ZIP export/import
- ✅ Backup integrity validation

## 🏗️ Arsitektur & Struktur Proyek

### High-Level Architecture

```
┌──────────────────────────────────────────────────────────────────────┐
│                    TELEGRAM USER                                     │
│              (via @BotFather bot token)                              │
└──────────────────────────────┬──────────────────────────────────────┘
                         │
         ┌───────────────┴───────────────┐
         │                               │
   ┌─────▼──────────┐            ┌─────▼──────────┐
   │  POLLING       │            │   WEBHOOK      │
   │  MODE          │            │   MODE         │
   │ (Dev)          │            │ (Production)   │
   └─────┬──────────┘            └──────┬─────────┘
         │                               │
         └───────────────┬───────────────┘
                         │
        ┌─────────────────▼───────────────────┐
        │   aiogram Dispatcher (async)        │
        │   • Message handlers                │
        │   • Callback queries                │
        │   • Middleware pipeline             │
        └────────────┬──────────────┬─────────┘
                    │              │
         ┌──────────▼─────┐  ┌─────▼──────────┐
         │  Bot Handlers  │  │  Auth Layer    │
         │  (handlers.py) │  │  (auth.py)     │
         └──────┬─────────┘  └────────────────┘
                │
    ┌───────────┼───────────┬──────────────────┐
    │           │           │                  │
    ▼           ▼           ▼                  ▼
┌────────┐ ┌────────┐  ┌────────┐   ┌──────────────┐
│Database│ │Zoom API│  │  C2    │   │ Shortener    │
│(db.py) │ │(zoom.py)  │(c2/)   │   │(shortener.py)│
│        │ │        │  │        │   │              │
└───┬────┘ └────┬───┘  └───┬────┘   └──────────────┘
    │           │          │
    ▼           ▼          ▼
 SQLite/     Zoom API   Sliver C2
 PostgreSQL  (OAuth S2S) Server
             Recording   (mTLS)
             Control
```

### Detailed Folder Structure

```
BotTelegramZoom/
│
├── 📂 bot/                    # ⭐ Core Bot Logic & Handlers
│   ├── __init__.py
│   ├── main.py               # Bot initialization, dispatcher setup, polling/webhook start
│   ├── handlers.py           # All message handlers, command callbacks, query callbacks
│   │                          # ├─ /start, /help, /meet, /zoom_del, /sync_meetings, /backup, etc.
│   ├── keyboards.py          # ReplyKeyboard & InlineKeyboard definitions
│   │                          # ├─ Main menu, meeting control, admin panel, etc.
│   ├── auth.py               # Authentication & authorization
│   │                          # ├─ Role system (owner, admin, user), whitelist, ban management
│   ├── middleware.py         # Request/response middleware pipeline
│   │                          # ├─ Logging, auth checks, rate limiting, error handling
│   └── __pycache__/
│
├── 📂 zoom/                   # 🔗 Zoom API Integration
│   ├── __init__.py
│   ├── zoom.py               # Zoom API client
│   │                          # ├─ OAuth token management (S2S authentication)
│   │                          # ├─ Meeting CRUD (create, read, update, delete)
│   │                          # ├─ Recording control (start, stop, pause, resume)
│   │                          # ├─ Meeting list sync (periodic every 30 min)
│   │                          # └─ Auto-recording strategy (LOCAL vs CLOUD)
│   └── __pycache__/
│
├── 📂 db/                     # 💾 Database Layer
│   ├── __init__.py
│   ├── db.py                 # Database operations with aiosqlite/asyncpg
│   │                          # ├─ User management (roles, whitelist, ban)
│   │                          # ├─ Meeting storage & queries
│   │                          # ├─ Shortener URLs cache
│   │                          # └─ Transaction management
│   └── __pycache__/
│
├── 📂 config/                 # ⚙️ Configuration Management
│   ├── __init__.py
│   ├── config.py             # Settings dataclass with type safety
│   │                          # ├─ Environment variable parsing
│   │                          # ├─ Defaults for optional variables
│   │                          # ├─ C2_ENABLED, AGENT_API_ENABLED toggles
│   │                          # └─ Validation & error handling
│   └── __pycache__/
│
├── 📂 c2/                     # 🤖 C2 Framework Integration (Sliver)
│   ├── __init__.py
│   ├── sliver_zoom_c2.py     # Sliver C2 client
│   │                          # ├─ mTLS connection to C2 server
│   │                          # ├─ Agent command execution (remote control)
│   │                          # ├─ Agent status monitoring
│   │                          # └─ Real-time meeting control via agents
│   └── __pycache__/
│
├── 📂 shortener/             # 🔗 URL Shortener Service
│   ├── __init__.py
│   ├── shortener.py          # Multi-provider URL shortener
│   │                          # ├─ TinyURL (default, no config)
│   │                          # ├─ S.id (Indonesian, recommended)
│   │                          # └─ Bitly (advanced, custom domains)
│   └── __pycache__/
│
├── 📂 api/                    # 🌐 API Server (Optional/Future)
│   ├── __init__.py
│   ├── api_server.py         # FastAPI/aiohttp server
│   │                          # ├─ Webhook endpoints for Telegram/Zoom
│   │                          # └─ REST API for external integrations
│   └── __pycache__/
│
├── 📂 agent/                  # 🛠️ Agent Management (Future)
│   ├── __init__.py
│   ├── todo_agent.md         # Agent deployment notes
│   └── __pycache__/
│
├── 📂 scripts/               # 📝 Utility & Setup Scripts
│   ├── __init__.py
│   ├── setup.py              # Initial setup: env validation, db init, auth setup
│   ├── dev.py                # Development runner with auto-restart
│   │                          # └─ Watchdog integration for .py & .json files
│   └── __pycache__/
│
├── 📂 docker/                # 🐳 Docker Configuration
│   ├── __init__.py
│   ├── Dockerfile            # Multi-stage Docker image definition
│   └── docker-entrypoint.sh  # Container startup script with env validation
│
├── 📂 c2_server/             # 🏆 C2 Server Setup (Optional)
│   ├── admin.cfg             # C2 server admin configuration
│   ├── start_server.bat      # Batch script to start C2 server
│   ├── stop_server.bat       # Batch script to stop C2 server
│   ├── generate_implants_api.py  # Script to generate agent implants
│   ├── generate_implants.bat # Batch script for implant generation
│   ├── README_Windows.md     # Windows-specific setup guide
│   ├── implants/
│   │   └── dummy_agent.bat   # Sample agent payload
│   └── logs/                 # C2 server operational logs
│
├── 📂 data/                  # 📊 Persistent Data
│   ├── shorteners.json       # Dynamic shortener provider config
│   │                          # └─ Add new providers without code change!
│   └── shorteners.json.back  # Backup of shortener config
│
├── 📂 docs/                  # 📚 Documentation
│   ├── __init__.py
│   ├── README.md             # Project overview, features, quick start
│   ├── INSTALLATION.md       # Detailed install guide (Windows, Docker, venv)
│   ├── DEVELOPMENT.md        # Development workflow, testing, best practices
│   ├── C2_SETUP_GUIDE.md     # Detailed Sliver C2 framework setup
│   ├── API.md                # API endpoints & integration guide
│   ├── API_TESTING_GUIDE.md  # Testing suite & validation procedures
│   └── __pycache__/
│
├── 📂 logs/                  # 📋 Application Logs (created at runtime)
│   └── *.log                 # Timestamped log files (rotated daily)
│
├── 📂 tests/                 # ✅ Unit Tests & Integration Tests
│   ├── __init__.py
│   ├── test_c2_integration.py     # C2 integration test suite
│   ├── test_mock_agents.py        # Mock agent testing
│   ├── test_c2.bat                # Windows batch test runner
│   └── __pycache__/
│
├── 📂 __pycache__/           # 🗑️ Compiled Python (auto-generated)
│
├── 🐳 Dockerfile             # Docker image recipe (prod & dev)
├── 🐳 docker-compose.yml     # Docker Compose orchestration (dev & prod)
│
├── 📄 .env                   # ⚠️ Environment variables (created from .env.example)
├── 📄 .env.example           # Template for .env (30+ variables, 2 sections)
├── 📄 Makefile               # Shortcuts for Docker commands (make up, make logs, etc.)
│
├── 📄 run.py                 # Main entry point for bot (polling mode)
├── 📄 dev.py                 # Alternative entry point (auto-restart on file change)
├── 📄 demo_c2.py             # Demo script for C2 testing
├── 📄 setup_c2.sh            # Shell script for C2 server setup
│
├── 📄 requirements.txt        # Python dependencies (Core, Dev, Tools)
├── 📄 Readme.md              # Project overview (this file)
├── 📄 context.md             # AI assistant context reference (for continuation)
│
├── 📄 cleanup_dirs.py         # Cleanup script (__pycache__, logs, temp files)
├── 📄 cleanup_dirs.bat        # Windows batch cleanup script
│
└── 📄 .gitignore             # Git ignore patterns
```

### 🔄 Module Dependencies & Data Flow

```
User Input (Telegram)
        │
        ▼
    main.py (dispatcher)
        │
        ▼
    middleware.py (auth, logging)
        │
        ▼
    handlers.py (message logic)
        │
    ┌───────────────────────────────────────────────┐
    │  branching to services                        │
    ├───────────────────────────────────────────────┤
    │  │                            │
    ├──┴──► db.py ─────┐    ┌──────► zoom.py ─┐
    │           │      │    │            │      │
    │       SQLite/    │    │        Zoom API
    │       PostgreSQL │    │       (OAuth S2S)
    │           │      │    │            │      │
    ├───────────────────┴────┴────┬──────────────┤
    │                          │
    ├──────────────────► c2.py ────────┤  ← Agent Control
    │            (Sliver)             │     (mTLS to C2 Server)
    │                          │
    ├──────────────► shortener.py ────┤  ← URL Shortening
    │            (Multi-Provider)
    │
    └──────────────► api.py ──────────┘  ← External APIs
                 (Webhooks, REST)

Response sent back to User
```

### 🔐 Security Architecture

```
Level 1: Request Layer
├─ middleware.py: Rate limiting, request validation
└─ Input sanitization

Level 2: Authentication Layer
├─ auth.py: User role verification (owner, admin, user)
├─ Whitelist/ban checks
└─ Telegram ID validation

Level 3: Service Layer
├─ C2 mTLS encryption (sliver_zoom_c2.py)
├─ Zoom OAuth token management (zoom.py)
└─ DB prepared statements (db.py)

Level 4: Transport Layer
├─ HTTPS for Zoom API calls
├─ mTLS for C2 communication
└─ Encrypted environment variables
```

### 📊 Environment Modes

**Development (DEFAULT_MODE=polling)**
```
Telegram → Polling → Bot → SQLite → Response
(Simple, good for testing)
```

**Production (DEFAULT_MODE=webhook)**
```
Telegram → Webhook → Bot → PostgreSQL → Response
(Scalable, used in production)
```

**With C2 Control (C2_ENABLED=true)**
```
Telegram → Bot → C2 Server (mTLS) → Agent → Zoom
(Real-time remote control, no polling overhead)
```

## 🚀 Quick Start

### Prerequisites
- Python 3.11+
- Telegram Bot Token (dari @BotFather)
- Zoom App credentials (Server-to-Server OAuth)

### Instalasi Cepat

```bash
# Clone repository
git clone <repository-url>
cd BotTelegramZoom

# Install dependencies
pip install -r requirements.txt

# Setup environment
cp .env.example .env
# Edit .env dengan credentials Anda

# Jalankan setup
python scripts/setup.py

# Jalankan bot
python run.py
```

## 📋 File Dokumentasi

- **[INSTALLATION.md](INSTALLATION.md)** - Panduan instalasi lengkap
- **[DEVELOPMENT.md](DEVELOPMENT.md)** - Panduan development
- **[API.md](API.md)** - Dokumentasi API (jika ada)

## 🔧 Teknologi

- **Framework**: aiogram (Telegram Bot API)
- **Database**: SQLite dengan aiosqlite
- **HTTP Client**: aiohttp
- **Container**: Docker
- **Language**: Python 3.11+

## 🚨 Error Handling & Graceful Shutdown

Bot ini dilengkapi dengan sistem error handling yang komprehensif untuk menangani berbagai situasi penghentian proses:

### Penyebab Penghentian Proses:

#### 1. **Interupsi User (Ctrl+C)**
```
🛑 Bot dihentikan oleh user (Ctrl+C)
✅ Proses bot telah berhenti dengan aman
```
- **Penyebab**: User menekan `Ctrl+C` di terminal
- **Penanganan**: Shutdown graceful dengan cleanup session

#### 2. **Signal Sistem**
```
INFO - Received signal SIGTERM (15). Initiating graceful shutdown...
INFO - Bot shutdown initiated by system signal
```
- **Penyebab**: Sistem mengirim signal (SIGTERM, SIGINT)
- **Penanganan**: Signal handler mencegah termination paksa

#### 3. **Error Sistem**
```
❌ Error sistem: [error message]
🔍 Periksa log file untuk detail lebih lanjut
```
- **Penyebab**: Exception tak terduga dalam kode
- **Penanganan**: Logging detail error dan exit dengan kode error

#### 4. **Polling Cancellation**
```
INFO - Bot polling was cancelled
INFO - Closing bot session...
INFO - Bot session closed. Shutdown complete.
```
- **Penyebab**: Task asyncio dibatalkan
- **Penanganan**: Cleanup proper tanpa crash

### Fitur Error Handling:

- ✅ **Signal Handlers**: Menangkap SIGTERM/SIGINT
- ✅ **Exception Wrapping**: Semua exception ditangkap
- ✅ **Graceful Cleanup**: Session bot ditutup dengan aman
- ✅ **User Messages**: Pesan jelas di console
- ✅ **Detailed Logging**: Log lengkap untuk debugging
- ✅ **Exit Codes**: Kode exit yang tepat (0=success, 1=error)

### Testing Error Handling:

```bash
# Test normal shutdown
python run.py  # lalu tekan Ctrl+C

# Test dengan timeout (Unix)
timeout 10 python run.py

# Check log setelah error
tail -f logs/$(date +%d-%b-%Y)-INFO.log
```

## 📞 Support

Untuk pertanyaan atau dukungan, silakan buat issue di repository GitHub.

## 📄 Lisensi

Project ini menggunakan lisensi yang sesuai dengan kebijakan organisasi.