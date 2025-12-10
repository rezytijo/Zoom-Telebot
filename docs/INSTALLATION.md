# Instalasi dan Menjalankan Zoom-Telebot SOC

Panduan lengkap untuk menginstall dan menjalankan Zoom-Telebot SOC dengan berbagai metode.

## 📋 Prerequisites

### Sistem Requirements
- **OS**: Windows 10/11, Linux, atau macOS
- **Python**: 3.11 atau lebih baru
- **RAM**: Minimum 512MB (1GB recommended)
- **Storage**: 100MB free space

### Akun dan Credentials
1. **Telegram Bot Token**
   - Buka [@BotFather](https://t.me/botfather) di Telegram
   - Buat bot baru dengan `/newbot`
   - Simpan token yang diberikan

2. **Zoom API Credentials**
   - Login ke [Zoom Marketplace](https://marketplace.zoom.us/)
   - Buat Server-to-Server OAuth app
   - Dapatkan Account ID, Client ID, dan Client Secret

3. **URL Shortener (Opsional)**
   - **S.id**: Dapatkan ID dan Key dari s.id
   - **Bitly**: Dapatkan access token dari Bitly

## 🔧 Metode Instalasi

### Metode 1: Instalasi Langsung di PC

#### Step 1: Clone Repository
```bash
git clone <repository-url>
cd BotTelegramZoom
```

#### Step 2: Install Python Dependencies
```bash
# Install requirements
pip install -r requirements.txt

# Atau jika menggunakan pipenv
pipenv install
pipenv shell
```

#### Step 3: Setup Environment
```bash
# Copy environment template
cp .env.example .env

# Edit .env file dengan text editor
# Isi semua credentials yang diperlukan
```

#### Step 4: Initial Setup
```bash
# Jalankan setup script
python scripts/setup.py
```

#### Step 5: Jalankan Bot
```bash
# Cek konfigurasi sebelum menjalankan bot
python run.py --check-config

# Jalankan sebagai foreground
python run.py

# Jalankan dengan log level DEBUG
python run.py --log-level DEBUG

# Lihat semua opsi yang tersedia
python run.py --help

# Atau jalankan sebagai background (Linux/Mac)
nohup python run.py &

# Atau jalankan sebagai background (Windows)
# Gunakan screen/tmux atau Windows Task Scheduler
```

### Metode 2: Menggunakan Docker Run

#### Prerequisites Docker
- Docker Desktop terinstall
- Minimal Docker version 20.10+

#### Step 1: Build Docker Image
```bash
# Build image
docker build -f docker/Dockerfile -t zoom-telebot .

# Atau build dengan target production
docker build --target production -t zoom-telebot .
```

#### Step 2: Prepare Environment File
```bash
# Copy dan edit .env file
cp .env.example .env
# Edit .env dengan credentials
```

#### Step 3: Run Container
```bash
# Jalankan container
docker run -d \
  --name zoom-telebot \
  --env-file .env \
  -p 8767:8767 \
  -v zoom_telebot_data:/app/data \
  -v zoom_telebot_logs:/app/logs \
  zoom-telebot

# Cek logs
docker logs -f zoom-telebot
```

### Metode 3: Menggunakan Docker Compose

#### Prerequisites
- Docker dan Docker Compose terinstall

#### Step 1: Setup Environment
```bash
# Copy dan edit .env file
cp .env.example .env
# Edit .env dengan credentials
```

#### Step 2: Jalankan dengan Docker Compose
```bash
# Jalankan sebagai daemon
docker compose up -d

# Jalankan dan lihat logs
docker compose up

# Cek status
docker compose ps

# Lihat logs
docker compose logs -f
```

#### Step 3: Management Commands
```bash
# Stop bot
docker compose down

# Restart bot
docker compose restart

# Rebuild dan restart
docker compose up -d --build

# Hapus volumes (untuk reset data)
docker compose down -v
```

## 🔄 Menjalankan di Background

### Linux/Mac
```bash
# Menggunakan nohup
nohup python run.py &

# Menggunakan screen
screen -S zoom-bot
python run.py
# Ctrl+A, D untuk detach

# Menggunakan tmux
tmux new -s zoom-bot
python run.py
# Ctrl+B, D untuk detach

# Menggunakan systemd (recommended untuk production)
sudo cp scripts/zoom-telebot.service /etc/systemd/system/
sudo systemctl enable zoom-telebot
sudo systemctl start zoom-telebot
```

### Windows
```bash
# Menggunakan Windows Task Scheduler
# 1. Buka Task Scheduler
# 2. Create Basic Task
# 3. Program: python.exe
# 4. Arguments: run.py
# 5. Start in: C:\path\to\BotTelegramZoom

# Menggunakan PowerShell
# Buat script start-bot.ps1
Start-Process -FilePath "python.exe" -ArgumentList "run.py" -WindowStyle Hidden
```

### Docker Background
```bash
# Docker Compose sudah berjalan di background secara default
docker compose up -d

# Cek status
docker compose ps
```

## 🔍 Verifikasi Instalasi

### Test Bot Functionality
1. **Kirim `/start`** ke bot di Telegram
2. **Cek logs** untuk error messages
3. **Test command** seperti `/help` atau `/status`

### Health Check
```bash
# Untuk Docker
docker compose exec zoom-telebot python -c "print('Bot is running')"

# Untuk direct run
python -c "import sys; print('Python OK')"
```

### Troubleshooting

#### Bot Tidak Merespons
```bash
# Cek logs
docker compose logs zoom-telebot

# Cek environment variables
docker compose exec zoom-telebot env | grep TELEGRAM

# Test bot token
curl "https://api.telegram.org/bot<YOUR_TOKEN>/getMe"
```

#### Database Issues
```bash
# Cek database file
ls -la data/zoom_telebot.db

# Reset database (backup dulu!)
rm data/zoom_telebot.db
python scripts/setup.py
```

#### Port Conflicts
## 📊 Monitoring

### Logs
```bash
# Docker logs
docker compose logs -f zoom-telebot

# System logs (Linux)
journalctl -u zoom-telebot -f

# File logs
tail -f logs/bot.log
```

### Resource Usage
```bash
# Docker stats
docker stats zoom-telebot

# System resources
top -p $(pgrep python)
```

## 🔄 Update dan Maintenance

### Update Bot
```bash
# Pull latest changes
git pull

# Update dependencies
pip install -r requirements.txt

# Restart bot
docker compose restart
```

### Backup Data
```bash
# Backup database dan config
cp data/zoom_telebot.db data/backup_$(date +%Y%m%d).db
cp .env .env.backup
```

## 🆘 Support

Jika mengalami masalah:
1. Cek logs untuk error messages
2. Verifikasi semua environment variables
3. Pastikan semua prerequisites terinstall
4. Buat issue di repository dengan detail error