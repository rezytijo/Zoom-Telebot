# Agent Installation & Usage (in-repo)

Panduan singkat untuk menjalankan `agent_server.py` yang sekarang ada di folder `agent/`.

## Prasyarat
- Python 3.8+
- Virtual environment (disarankan)
- Paket Python: `aiohttp`, `pyautogui`

## Menyalin file
File agent sudah berada di `agent/agent_server.py` dalam repo ini.

## Membuat virtualenv dan menginstal dependency (PowerShell)
```powershell
# Buat venv
python -m venv C:\zoom_agent_venv
# Aktifkan
C:\zoom_agent_venv\Scripts\Activate.ps1
# Install deps
pip install --upgrade pip
pip install aiohttp pyautogui
```

## Menjalankan agen (Polling mode — direkomendasikan)
```powershell
python agent\agent_server.py --api-key "PASTE_API_KEY_HERE" --server-url "http://SERVER_URL:8767" --verbose
```

## Menjalankan agen (Direct mode — server harus dapat menjangkau agen)
```powershell
python agent\agent_server.py --api-key "PASTE_API_KEY_HERE" --port 8766 --verbose
```

## Menjalankan otomatis saat user login (Task Scheduler)
Contoh Scheduled Task argument:
```
agent\agent_server.py --api-key "PASTE_API_KEY_HERE" --server-url "http://SERVER_URL:8767" --log-file "C:\zoom_agent\agent.log"
```

## Verifikasi & Troubleshooting
- Jalankan agen dari PowerShell dan periksa output log.
- Di bot Telegram, gunakan `/agents` untuk melihat agen yang terdaftar.
- Untuk pengujian cepat: dari bot queue-kan perintah open_url/hotkey ke agent dan perhatikan log agen.

## Keamanan
- Gunakan HTTPS untuk `--server-url` bila memungkinkan.
- Simpan API key agen dengan aman.