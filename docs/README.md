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

### Agent System
- ✅ Remote control system untuk meeting control
- ✅ Agent management (add/remove/reinstall)
- ✅ Status monitoring (online/offline)
- ✅ Async command execution via API

### URL Shortener
- ✅ Multi-provider support (TinyURL, S.id, Bitly)
- ✅ Dynamic configuration via JSON
- ✅ Custom aliases support
- ✅ Auto-shorten meeting URLs

### Backup & Restore
- ✅ Full system backup (database + config)
- ✅ ZIP export/import
- ✅ Backup integrity validation

## 🏗️ Arsitektur

```
BotTelegramZoom/
├── bot/           # Core bot logic
├── zoom/          # Zoom API integration
├── db/            # Database layer
├── config/        # Configuration management
├── api/           # Agent API server
├── shortener/     # URL shortener service
├── scripts/       # Utility scripts
├── docker/        # Docker configuration
├── data/          # Persistent data
└── docs/          # Documentation
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