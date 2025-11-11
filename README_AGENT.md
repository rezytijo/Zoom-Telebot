# Agent Installation & Usage

Panduan singkat untuk menjalankan `agent_server.py` pada Windows (juga berlaku untuk Linux dengan sedikit penyesuaian).

## Prasyarat
- Python 3.8+
- Virtual environment (disarankan)
- Paket Python: `aiohttp`, `pyautogui`

## Menyalin file
Salin `agent_server.py` ke folder agen, misal `C:\zoom_agent`.

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
Agen akan mendaftar dan melakukan polling ke server (bot). Ganti `SERVER_URL` dengan URL publik server Anda jika ada.

```powershell
python C:\zoom_agent\agent_server.py --api-key "PASTE_API_KEY_HERE" --server-url "http://SERVER_URL:8767" --verbose
```

- `--verbose`: tampilkan log DEBUG di terminal
- `--log-file <path>`: jika ingin menuliskan log ke file, tambahkan `--log-file "C:\zoom_agent\agent.log"`

## Menjalankan agen (Direct mode — server harus dapat menjangkau agen)
```powershell
python C:\zoom_agent\agent_server.py --api-key "PASTE_API_KEY_HERE" --port 8766 --verbose
```

## Menjalankan otomatis saat user login (Task Scheduler)
Gunakan Scheduled Task agar agen berjalan pada sesi desktop interaktif (penting agar `pyautogui` dapat mengirim hotkeys).

Contoh membuat Scheduled Task via PowerShell (jalankan sebagai user yang akan login):

```powershell
$Action = New-ScheduledTaskAction -Execute "C:\zoom_agent_venv\Scripts\python.exe" -Argument "C:\zoom_agent\agent_server.py --api-key \"PASTE_API_KEY_HERE\" --server-url \"http://SERVER_URL:8767\" --log-file \"C:\\zoom_agent\\agent.log\""
$Trigger = New-ScheduledTaskTrigger -AtLogOn
Register-ScheduledTask -TaskName "ZoomAgent" -Action $Action -Trigger $Trigger -Description "Zoom agent polling to central server" -User $env:USERNAME -RunLevel Highest
```

- Pastikan opsi task dijalankan `Run only when user is logged on` agar agent punya akses desktop interaktif.

## Verifikasi
- Jalankan agent dari PowerShell dan periksa output log.
- Di bot Telegram, gunakan `/agents` untuk melihat agen yang terdaftar.
- Kirim perintah open_url/hotkey dari bot ke agent dan perhatikan log agen untuk melihat eksekusi dan reporting ke server.

## Troubleshooting singkat
- Jika `pyautogui` tidak mengirim hotkey: jalankan agen di sesi desktop aktif; jangan jalankan sebagai service tanpa sesi interaktif.
- Untuk headless Linux, butuh `xvfb` atau lingkungan X yang sesuai; `pyautogui` butuh utilitas seperti `scrot`.
- Pastikan koneksi outbound dari agen ke `server_url` tidak diblokir oleh firewall.

## Keamanan
- Gunakan HTTPS untuk `--server-url` jika agen dan server berkomunikasi lewat internet.
- Simpan API key agen dengan aman; rotasi saat perlu.
- Batasi perintah yang dapat dijalankan agen (open_url, hotkey). Jangan menerima perintah shell arbitrary.

---

Jika mau, saya bisa juga menambahkan file service/unit contoh (systemd) atau skrip instalasi otomatis ke repo.
