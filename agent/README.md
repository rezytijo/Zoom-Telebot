# Zoom Agent Server

Lightweight agent server untuk automasi Zoom yang berjalan di host (Windows/Linux).

## Fitur Utama

- **Konfigurasi Persistent**: Simpan konfigurasi ke file JSON, tidak perlu parameter berulang
- **HTTP API**: Endpoint untuk berbagai aksi Zoom (start meeting, recording, dll)
- **Polling Mode**: Auto-register ke server pusat dan polling untuk perintah
- **System Info**: Deteksi otomatis informasi sistem untuk registrasi

## Instalasi & Setup

1. Install dependencies:
```bash
pip install aiohttp pyautogui
```

2. Jalankan agent pertama kali dengan parameter lengkap:
```bash
python agent_server.py --api-key YOUR_API_KEY --server-url http://your-server:8081 --verbose
```

3. Setelah itu, tinggal jalankan tanpa parameter:
```bash
python agent_server.py
```

## Penggunaan

### Pertama Kali (Setup Konfigurasi)

```bash
# Jalankan dengan semua parameter yang diperlukan
python agent_server.py \
  --api-key "your-secret-api-key" \
  --server-url "http://your-telebot-server:8081" \
  --port 8767 \
  --host "0.0.0.0" \
  --verbose \
  --log-file "agent.log"
```

Konfigurasi akan otomatis tersimpan ke `agent_config.json`.

### Jalankan Ulang (Menggunakan Konfigurasi Tersimpan)

```bash
# Tinggal jalankan tanpa parameter
python agent_server.py
```

Agent akan menggunakan konfigurasi dari `agent_config.json`.

### Mengubah Konfigurasi

```bash
# Override parameter tertentu
python agent_server.py --port 9999 --verbose

# Atau hapus config dan mulai dari awal
python agent_server.py --reset-config
```

## Opsi Command Line

- `--config FILE`: Path file konfigurasi (default: agent_config.json)
- `--reset-config`: Reset konfigurasi ke default dan keluar
- `--api-key KEY`: API key untuk autentikasi (wajib)
- `--server-url URL`: URL server pusat untuk polling mode
- `--port PORT`: Port untuk listen (default: 8767)
- `--host HOST`: Host untuk bind (default: 0.0.0.0)
- `--verbose`: Enable logging verbose
- `--log-file FILE`: Path file log

## API Endpoints

- `POST /command`: Execute commands (start_zoom, start-record, dll)
- `GET /ping`: Health check dan info sistem

## Keamanan

- Gunakan API key yang kuat
- Jalankan agent di belakang firewall
- Hanya izinkan akses dari host terpercaya