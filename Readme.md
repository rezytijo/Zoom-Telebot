# Zoom-Telebot (Aiogram + Zoom Server-to-Server OAuth)

Ringkasan: bot Telegram untuk mengelola Zoom meeting dengan fitur whitelist, ownership, roles, polling/webhook modes, dan UI menggunakan inline keyboards.

## 🚀 Quick Start

### Docker Installation (Recommended)
Untuk deployment yang mudah dan konsisten, gunakan Docker:

#### 1. Install Docker Desktop
- **Windows**: Download dari [docker.com](https://www.docker.com/products/docker-desktop)
- **Linux**: `sudo apt update && sudo apt install docker.io docker-compose-plugin`
- **macOS**: Download dari [docker.com](https://www.docker.com/products/docker-desktop)

#### 2. Verifikasi Instalasi
```bash
docker --version
docker compose version
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

## 🐳 Docker Deployment
- **Telegram Bot Token** dari [@BotFather](https://t.me/botfather)
- **Zoom App Credentials** dari [Zoom Marketplace](https://marketplace.zoom.us/)

### 1️⃣ Local Development (Basic)

#### Setup Environment
```bash
# Clone repository
git clone https://github.com/rezytijo/Zoom-Telebot.git
cd Zoom-Telebot

# Create virtual environment
python -m venv .venv
# Activate (Windows)
.venv\Scripts\activate
# Activate (Linux/Mac)
source .venv/bin/activate

# Install dependencies
pip install -r requirements.txt

# Copy environment template
cp .env.example .env

# Edit .env dengan credentials Anda
nano .env  # atau gunakan editor favorit Anda
```

#### Environment Variables (.env)
```bash
# Telegram Configuration
TELEGRAM_TOKEN=your_bot_token_here
INITIAL_OWNER_ID=your_telegram_user_id
INITIAL_OWNER_USERNAME=@your_username

# Zoom Configuration
ZOOM_CLIENT_ID=your_zoom_client_id
ZOOM_CLIENT_SECRET=your_zoom_client_secret
ZOOM_ACCOUNT_ID=your_zoom_account_id

# Optional: URL Shorteners
SID_ID=your_sid_id
SID_KEY=your_sid_key
BITLY_TOKEN=your_bitly_token

# Optional: Database
DATABASE_URL=sqlite+aiosqlite:///./zoom_telebot.db
```

#### Run Bot Locally
```bash
# Method 1: Using dev.py (Recommended)
python dev.py setup  # Setup environment
python dev.py run    # Run bot

# Method 2: Manual setup
python setup.py      # Setup environment
python main.py       # Run bot

# Method 3: Development runner (auto-restart)
python dev_run.py    # Auto-restart on file changes
```

### 2️⃣ Local Development (Advanced)

#### Development Commands
```bash
# Check environment configuration
python dev.py check

# Run with debug logging
python dev.py debug

# Test all imports
python dev.py test

# Show help
python dev.py help
```

#### Code Structure Overview
```
zoom-telebot/
├── main.py              # Entry point
├── dev.py               # Development utilities
├── setup.py             # Environment setup & validation
├── config.py            # Configuration management
├── handlers.py          # Telegram bot handlers
├── keyboards.py         # Inline keyboard layouts
├── db.py                # Database operations
├── zoom.py              # Zoom API integration
├── shortener.py         # URL shortener services
├── middleware.py        # Bot middleware
├── oauth_helper.py      # OAuth utilities
└── requirements.txt     # Python dependencies
```

#### Adding New Features
1. **Handlers**: Tambahkan logic baru di `handlers.py`
2. **Keyboards**: Design UI di `keyboards.py`
3. **Database**: Update schema di `db.py`
4. **Configuration**: Tambahkan env vars di `config.py`

#### Testing Your Changes
```bash
# Run unit tests
python -m pytest tests/ -v

# Test specific file
python -m pytest tests/test_handlers.py -v

# Run with coverage
python -m pytest --cov=. --cov-report=html
```

### 3️⃣ Docker Development

#### Quick Docker Setup
```bash
# Clone repository
git clone https://github.com/rezytijo/Zoom-Telebot.git
cd Zoom-Telebot

# Copy environment template
cp .env.example .env
# Edit .env dengan credentials Anda

# Start development environment
docker compose up --build

# Atau run in background
docker compose up -d --build
```

#### Docker Development Workflow
```bash
# View logs
docker compose logs -f

# Access container shell
docker compose exec zoom-telebot /bin/bash

# Run tests in container
docker compose exec zoom-telebot python -m pytest tests/

# Stop services
docker compose down

# Clean up (remove volumes too)
docker compose down --volumes --remove-orphans
```

#### Docker Compose Files Explained
```
docker-compose.yml          # Base configuration (production-ready)
├── docker-compose.override.yml    # Development overrides (auto-loaded)
├── docker-compose.prod.yml        # Production optimizations
└── docker-compose.test.yml        # Testing environment
```

**Key Differences:**
- **Development**: Source code mounted, debug logging, auto-restart disabled
- **Production**: Optimized image, security hardening, resource limits
- **Testing**: Isolated environment, test database, pytest command

### 4️⃣ Development Best Practices

#### Code Quality
```bash
# Format code
black .

# Sort imports
isort .

# Lint code
flake8 .

# Type checking
mypy .
```

#### Git Workflow
```bash
# Create feature branch
git checkout -b feature/new-feature

# Make changes
# ... code changes ...

# Commit changes
git add .
git commit -m "feat: add new feature"

# Push to branch
git push origin feature/new-feature

# Create Pull Request
# ... GitHub PR ...
```

#### Debugging Tips
```bash
# Enable debug logging
export LOG_LEVEL=DEBUG
python dev.py debug

# Check database
sqlite3 zoom_telebot.db
.schema
SELECT * FROM users LIMIT 5;

# Test API endpoints
curl -X POST http://localhost:8080/webhook \
  -H "Content-Type: application/json" \
  -d '{"test": "data"}'
```

### 5️⃣ Deployment Options

#### Option 1: Docker Production
```bash
# Build production image
docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d --build

# Check logs
docker compose logs -f
```

#### Option 2: Portainer (Recommended)
1. Import `docker-compose.yml` ke Portainer
2. Set environment variables di Portainer UI
3. Setup webhook untuk auto-deployment
4. GitHub Actions akan trigger update otomatis

#### Option 3: Manual Server Deployment
```bash
# On your server
git clone https://github.com/rezytijo/Zoom-Telebot.git
cd Zoom-Telebot

# Setup environment
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

# Configure environment variables
export TELEGRAM_TOKEN=your_token
export INITIAL_OWNER_ID=your_id
# ... other vars ...

# Run with process manager (pm2, systemd, etc.)
python main.py
```

### 6️⃣ Troubleshooting

#### Common Issues
```bash
# Bot not responding
python dev.py check  # Check environment
docker compose logs  # Check container logs

# Database issues
rm zoom_telebot.db
python setup.py      # Reinitialize database

# Permission issues
sudo chown -R $USER:$USER .
docker compose down --volumes
docker compose up -d --build
```

#### Getting Help
- 📖 Check [Test-Flow.md](Test-Flow.md) for detailed testing procedures
- 🐛 Open issues on GitHub
- 💬 Join our Telegram channel for community support

---

## 🐳 Docker Deployment

### Prerequisites
- Docker Engine 20.10+
- Docker Compose V2 (`docker compose` command)

### Environment Setup
```bash
# Clone repository
git clone https://github.com/rezytijo/Zoom-Telebot.git
cd Zoom-Telebot

# Copy environment template
cp .env.example .env

# Edit .env dengan konfigurasi Anda
nano .env
```

### Development Environment
```bash
# Build dan start development environment
docker compose up --build

# Atau run di background
docker compose up -d --build

# View logs
docker compose logs -f

# Stop services
docker compose down
```

### Production Environment
```bash
# Build untuk production
docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d --build

# Atau gunakan Makefile
make prod-build
make prod-up
make prod-logs
```

### Portainer Deployment (Recommended)
Untuk deployment dengan Portainer:

1. **Import Stack** di Portainer dengan file `docker-compose.yml`
2. **Environment Variables**:
   - Set semua variabel di bagian Environment Portainer
   - Atau mount file `.env` sebagai volume
3. **Webhook Integration**:
   - Setup webhook di Portainer stack
   - GitHub Actions akan otomatis trigger update setelah build

### Docker Commands Reference

```bash
# Build image
docker compose build

# Start services
docker compose up -d

# Stop services
docker compose down

# View logs
docker compose logs -f

# Restart services
docker compose restart

# Shell access ke container
docker compose exec zoom-telebot /bin/bash

# Update services (pull latest image)
docker compose pull
docker compose up -d

# Clean up
docker compose down --volumes --remove-orphans
docker system prune -f
```

### Troubleshooting Docker

#### Container tidak start
```bash
# Check logs
docker compose logs zoom-telebot

# Check environment
docker compose exec zoom-telebot python setup.py

# Debug mode
docker compose exec zoom-telebot python dev.py debug
```

#### Permission issues
```bash
# Fix permissions
sudo chown -R $USER:$USER .
docker compose down --volumes
docker compose up -d --build
```

#### Port conflicts
```bash
# Check used ports
docker compose ps
netstat -tulpn | grep :80

# Change ports di docker-compose.yml jika perlu
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
docker compose up -d

# 3. Check logs
docker compose logs -f
```

### Development dengan Docker

```bash
# Development mode
docker compose --profile dev up

# Atau gunakan Makefile
make dev-up
make dev-logs
```

### Production Deployment

```bash
# Production mode
docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d

# Atau gunakan Makefile
make prod-build
make prod-up
make prod-logs
```

### Docker Commands

```bash
# Build image
docker compose build

# Start services
docker compose up -d

# Stop services
docker compose down

# View logs
docker compose logs -f

# Restart services
docker compose restart

# Shell access
docker compose exec zoom-telebot /bin/bash
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
