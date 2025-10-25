# Zoom-Telebot (Aiogram + Zoom Server-to-Server OAuth)

Ringkasan: bot Telegram untuk mengelola Zoom meeting dengan fitur whitelist, ownership, roles, polling/webhook modes, dan UI menggunakan inline keyboards.

## 🚀 Quick Start

### Docker Installation (Recommended)
Untuk deployment yang mudah dan konsisten, gunakan Docker:

#### 1. Install Docker Desktop
- **Windows**: Download dari [docker.com](https://www.docker.com/products/docker-desktop)
- **Linux**: `sudo apt update && sudo apt install docker.io docker-compose`
- **macOS**: Download dari [docker.com](https://www.docker.com/products/docker-desktop)

#### 2. Verifikasi Instalasi
```bash
docker --version
docker-compose --version
```

### Local Development Setup
```bash
# Clone repository
git clone <repository-url>
cd zoom-telebot

# Copy environment template
cp .env.example .env

# Edit .env with your configuration
nano .env
```

### 2. Configure Environment Variables
Edit file `.env` dengan konfigurasi berikut:

```bash
# Telegram Bot Configuration
TELEGRAM_TOKEN=your-telegram-bot-token-here
INITIAL_OWNER_ID=your-telegram-user-id-here
INITIAL_OWNER_USERNAME=@your-telegram-username

# Zoom Integration Configuration
ZOOM_CLIENT_ID=your-zoom-client-id
ZOOM_CLIENT_SECRET=your-zoom-client-secret
ZOOM_ACCOUNT_ID=your-zoom-account-id

# Shortener Configuration
SID_ID=your-sid-id
SID_KEY=your-sid-key
```

### 3. Run Setup Script
```bash
# Setup environment (validasi + inisialisasi)
python setup.py
```

### 4. Development Commands
```bash
# Setup environment
python dev.py setup

# Run bot (dengan auto-setup)
python dev.py run

# Run dengan debug logging
python dev.py debug

# Test imports
python dev.py test

# Check environment
python dev.py check

# Help
python dev.py help
```

### 5. Alternative: Manual Run
```bash
# Setup environment
python setup.py

# Run bot
python main.py
```

## ⚙️ Detailed Setup

### Prerequisites
- Python 3.8+ (for local development)
- Docker & Docker Compose (for containerized deployment)
- Telegram Bot Token (dari [@BotFather](https://t.me/botfather))
- Zoom Account dengan Server-to-Server OAuth App
- Optional: URL Shortener API keys (S.id, Bitly)

### Environment Configuration

File `.env.example` berisi template konfigurasi lengkap. Variabel wajib:

#### Telegram Configuration
```bash
TELEGRAM_TOKEN=1234567890:AAFakeTokenExampleForDocumentationPurposes
INITIAL_OWNER_ID=987654321
INITIAL_OWNER_USERNAME=@example_user
```

#### Zoom Configuration
```bash
ZOOM_CLIENT_ID=ExampleZoomClientIdForDocumentation
ZOOM_CLIENT_SECRET=ExampleZoomClientSecretForDocumentationPurposes
ZOOM_ACCOUNT_ID=ExampleZoomAccountIdForDocumentation
```

#### Shortener Configuration
```bash
SID_ID=example_sid_id_for_documentation
SID_KEY=example_sid_key_for_documentation_purposes_only
BITLY_TOKEN=example_bitly_token_for_documentation_only
```

### Setup Script Features

Script `setup.py` melakukan validasi dan inisialisasi:

1. **Environment Validation**
   - ✅ Telegram token format
   - ✅ Zoom credentials
   - ✅ Database path
   - ✅ Shortener configuration

2. **Database Initialization**
   - Membuat tabel users, meetings, shortlinks
   - Setup owner user dengan role 'owner'

3. **Shortener Setup**
   - Update `shorteners.json` dengan API keys dari `.env`
   - Validasi provider configuration

## 📱 Bot Features

### User Management
- **Registration**: User mendaftar via `/start`
- **Approval System**: Owner/Admin approve user baru
- **Role Management**: Owner → Admin → User → Guest
- **Ban/Unban**: Owner dapat ban user

### Meeting Management
- **Create Meeting**: Flow lengkap dengan validasi
  - Input topic → tanggal → waktu → konfirmasi
  - Format tanggal Indonesia + parsing bahasa Indonesia
  - Greeting format: "Selamat pagi/siang/sore/malam Bapak/Ibu/Rekan-rekan"
- **List Meetings**: Tampilkan meeting aktif
- **Auto Sync**: Sync dari Zoom setiap 30 menit

### URL Shortener
- **Multi-provider**: S.id, TinyURL, Bitly
- **Custom Alias**: Support custom short URLs
- **Dynamic Configuration**: Provider dapat ditambah tanpa coding

## 🛠️ Development

### Project Structure
```
zoom-telebot/
├── main.py              # Bot entry point
├── setup.py             # Environment setup script
├── handlers.py          # Bot command handlers
├── keyboards.py         # Inline keyboard definitions
├── config.py            # Configuration management
├── db.py               # Database operations
├── zoom.py             # Zoom API integration
├── shortener.py        # URL shortener logic
├── shorteners.json     # Shortener provider config
├── .env.example        # Environment template
├── requirements.txt    # Python dependencies
└── Test-Flow.md       # Testing guide
```

### Adding New Features
1. **New Command**: Tambah di `handlers.py`
2. **New Keyboard**: Tambah di `keyboards.py`
3. **Database Changes**: Update `db.py` CREATE_SQL
4. **New Shortener**: Edit `shorteners.json`

## 🐳 Docker Deployment

### Prerequisites
- Docker & Docker Compose
- `.env` file dengan konfigurasi lengkap

### Quick Start with Docker

```bash
# 1. Setup environment
cp .env.example .env
# Edit .env dengan credentials Anda

# 2. Build dan run dengan Docker Compose
docker-compose up -d

# 3. Check logs
docker-compose logs -f
```

### Development dengan Docker

```bash
# Development mode
docker-compose --profile dev up

# Atau gunakan Makefile
make dev-up
make dev-logs
```

### Production Deployment

```bash
# Production mode
docker-compose -f docker-compose.yml -f docker-compose.prod.yml up -d

# Atau gunakan Makefile
make prod-build
make prod-up
make prod-logs
```

### Docker Commands

```bash
# Build image
docker-compose build

# Start services
docker-compose up -d

# Stop services
docker-compose down

# View logs
docker-compose logs -f

# Restart services
docker-compose restart

# Shell access
docker-compose exec zoom-telebot /bin/bash
```

### Makefile Commands

```bash
# Development
make dev-build      # Build dev image
make dev-up         # Start dev environment
make dev-logs       # Show dev logs
make dev-restart    # Restart dev

# Production
make prod-build     # Build prod image
make prod-up        # Start prod environment
make prod-logs      # Show prod logs

# General
make build          # Build default
make up             # Start services
make down           # Stop services
make logs           # Show logs
make status         # Service status
make clean          # Clean everything

# Maintenance
make backup         # Create DB backup
make test           # Run tests
make info           # System info
```

### Testing dengan Docker

```bash
# Run tests menggunakan test profile
make test-run

# Build test image
make test-build

# Clean test environment
make test-clean

# Manual test run
docker-compose --profile test up --abort-on-container-exit
```

### Troubleshooting Docker

#### Container tidak bisa start
```bash
# Check logs
docker-compose logs zoom-telebot

# Check environment
docker-compose run --rm zoom-telebot python setup.py

# Shell access untuk debug
docker-compose exec zoom-telebot /bin/bash
```

#### Database issues
```bash
# Check volume
docker volume ls | grep zoom

# Backup database
make backup

# Restore dari backup
make restore FILE=backup_file.db
```

#### Permission issues
```bash
# Fix permissions (Linux/Mac)
sudo chown -R $USER:$USER data/ logs/

# Windows - run as administrator atau check permissions

# Note: Docker containers automatically fix permissions on startup
# If you still have issues, check that the host directories exist
# shorteners.json is automatically copied to data/ directory for modifications
```

#### Port conflicts
```bash
# Check used ports
netstat -tulpn | grep :80

# Change port di docker-compose.yml
ports:
  - "8080:80"
```

### Environment Variables untuk Docker

```bash
# Database (akan menggunakan volume)
DATABASE_URL=sqlite+aiosqlite:///./data/zoom_telebot.db

# Logging
LOG_LEVEL=INFO

# Skip validation (optional)
SKIP_ENV_VALIDATION=false
```

### Volume Management

```bash
# List volumes
docker volume ls

# Inspect volume
docker volume inspect zoom-telebot_bot-data

# Backup volume
docker run --rm -v zoom-telebot_bot-data:/data -v $(pwd)/backups:/backups alpine tar czf /backups/backup.tar.gz -C /data .
```

### Troubleshooting Docker

```bash
# Check container status
docker-compose ps

# View container logs
docker-compose logs zoom-telebot

# Execute commands in container
docker-compose exec zoom-telebot python dev.py check

# Rebuild without cache
docker-compose build --no-cache

# Clean up
docker system prune -f
docker volume prune -f
```

## 🔧 Troubleshooting

### Common Issues

1. **Bot tidak merespons**
   ```bash
   # Check token
   python -c "from config import settings; print('Token:', bool(settings.bot_token))"
   ```

2. **Database error**
   ```bash
   # Reset database
   rm zoom_telebot.db
   python setup.py
   ```

3. **Zoom API error**
   ```bash
   # Check credentials
   python -c "from config import settings; print('Zoom OK:', bool(settings.zoom_client_id))"
   ```

### Debug Mode
```bash
# Enable debug logging
LOG_LEVEL=DEBUG python main.py
```

## 📋 API References

- [Telegram Bot API](https://core.telegram.org/bots/api)
- [Aiogram Documentation](https://docs.aiogram.dev/)
- [Zoom API Reference](https://developers.zoom.us/docs/api/)
- [S.id API](https://s.id/APIdocumentation)
- [Bitly API](https://dev.bitly.com/)

## 🤝 Contributing

1. Fork repository
2. Create feature branch
3. Test changes dengan `Test-Flow.md`
4. Submit pull request

## 📄 License

This project is licensed under the MIT License.

### Template Variables

```json
"nama_provider": {
  "name": "Nama Provider",
  "description": "Deskripsi provider",
  "enabled": true,
  "api_url": "https://api.provider.com/shorten",
  "method": "post",
  "headers": {
    "Content-Type": "application/json",
    "Authorization": "Bearer {api_token}"
  },
  "body": {
    "url": "{url}"
  },
  "response_type": "json",
  "success_check": "status==200",
  "url_extract": "response.get('short_url')"
}
```

3. Restart bot atau panggil `reload_shortener_config()`
- `{url}`: URL yang akan di-shorten
- `{custom}`: Custom alias (jika didukung)
- `{api_token}`: Token dari environment variable

### Contoh Provider

Lihat `shorteners.json` untuk contoh implementasi TinyURL, S.id, dan Bitly.

### Menambah Environment Variables

Untuk provider baru yang butuh authentication, tambahkan ke `.env`:

```bash
API_TOKEN=your_api_token_here
```

Catatan: scaffold ini menyediakan fitur dasar: menyimpan user yang mendaftar, menampilkan /register_list dengan tombol per-user, menandai whitelist, ban/unban, dan struktur untuk integrasi Zoom.
