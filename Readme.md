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
- **Manajemen User**:
  - **Sistem Peran**: `owner`, `admin`, dan `user` dengan hak akses yang berbeda.
  - **Sistem Whitelist**: Admin dapat menyetujui (`whitelisted`), menolak, atau memblokir (`banned`) pengguna baru.
  - **Pendaftaran**: Pengguna baru otomatis masuk ke dalam daftar tunggu persetujuan.
- **URL Shortener**:
  - **Multi-Provider**: Dukungan untuk S.id, Bitly, dan TinyURL.
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

- **[📖 Overview Project](docs/README.md)** - Deskripsi lengkap bot dan fitur-fiturnya
- **[🚀 Panduan Instalasi](docs/INSTALLATION.md)** - Cara install dan menjalankan bot (PC langsung, Docker run, Docker Compose)
- **[💻 Development Guide](docs/DEVELOPMENT.md)** - Panduan development, testing, dan best practices
- **[🔌 API Documentation](docs/API.md)** - Dokumentasi API untuk agent system
- **[🤖 AI Context Reference](context.md)** - Referensi untuk AI assistant (internal use)

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

5.  **Jalankan API Server Saja (Opsional)**
    Jika Anda hanya ingin menjalankan API server untuk agent tanpa bot Telegram:
    ```bash
    python api_server.py
    ```
    API server akan berjalan di `http://localhost:8767` (atau sesuai konfigurasi `AGENT_API_PORT`).

## ⚙️ Konfigurasi

Semua konfigurasi diatur melalui file `.env`.

| Variabel               | Deskripsi                                                               | Wajib      |
| ---------------------- | ----------------------------------------------------------------------- | ---------- |
| `TELEGRAM_TOKEN`       | Token bot dari @BotFather.                                              | **Ya**     |
| `INITIAL_OWNER_ID`     | ID Telegram unik milik owner bot.                                       | **Ya**     |
| `ZOOM_CLIENT_ID`       | Client ID dari aplikasi S2S OAuth Zoom.                                 | **Ya**     |
| `ZOOM_CLIENT_SECRET`   | Client Secret dari aplikasi S2S OAuth Zoom.                             | **Ya**     |
| `ZOOM_ACCOUNT_ID`      | Account ID dari akun Zoom Anda.                                         | **Ya**     |
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

```
├── 📂 data/
│   ├── zoom_telebot.db
│   └── shorteners.json      # Konfigurasi provider URL Shortener
├── 📜 .env                   # File konfigurasi environment (wajib dibuat)
├── 📜 .env.example          # Contoh file .env
├── 📜 config.py             # Memuat dan mengelola konfigurasi
├── 📜 main.py               # Titik masuk utama aplikasi bot
├── 📜 handlers.py           # Logika untuk semua perintah dan callback bot
├── 📜 db.py                 # Operasi database (SQLite)
├── 📜 zoom.py               # Klien untuk interaksi dengan Zoom API
├── 📜 shortener.py          # Logika untuk layanan URL shortener
├── 📜 setup.py               # Skrip inisialisasi dan validasi environment
├── 📜 dev.py                 # Skrip helper untuk development
├── 📜 requirements.txt       # Daftar dependensi Python
├── 🐳 Dockerfile              # Resep untuk membangun image Docker
├── 🐳 docker-compose.yml     # Konfigurasi dasar Docker Compose
└── 📜 Makefile               # Pintasan untuk perintah-perintah Docker
```

## 📄 Lisensi

Proyek ini dilisensikan di bawah [Lisensi MIT](LICENSE).