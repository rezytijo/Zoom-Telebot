# Shortener Configuration Migration Guide

## Overview

Fitur migrasi otomatis untuk `shorteners.json` memastikan file konfigurasi Anda selalu kompatibel dengan versi terbaru aplikasi, tanpa kehilangan kustomisasi yang telah Anda buat.

## Fitur Migrasi

### ✅ Keuntungan
- **Otomatis**: Migrasi berjalan otomatis saat aplikasi startup
- **Aman**: Backup file lama dibuat sebelum migrasi (`shorteners.json.pre-migration-backup`)
- **Preservatif**: Semua kustomisasi pengguna tetap tersimpan
- **Transparan**: Log detail tentang proses migrasi

### 🔍 Deteksi Perubahan
Migrasi otomatis terdeteksi jika:
1. File `shorteners.json` belum memiliki field `version`
2. Version di file lebih lama dari versi terbaru (2.0)
3. Ada field atau struktur provider yang tidak sesuai dengan skema terbaru

## Cara Menggunakan

### 1. Migrasi Otomatis (Recommended)

Migrasi terjadi otomatis saat aplikasi startup jika ada perubahan skema:

```bash
python run.py
```

Aplikasi akan mendeteksi dan melakukan migrasi otomatis jika diperlukan.

### 2. Migrasi Manual via Script

Gunakan script `migrate_shorteners.py` untuk kontrol penuh:

```bash
# Auto-detect dan migrasi jika diperlukan
python scripts/migrate_shorteners.py

# Paksa migrasi meskipun sudah versi terbaru
python scripts/migrate_shorteners.py --force

# Preview perubahan tanpa melakukan migrasi
python scripts/migrate_shorteners.py --preview

# Mode verbose (debug)
python scripts/migrate_shorteners.py --verbose
```

### 3. Migrasi dari Python Code

```python
from shortener import migrate_shortener_config

# Jalankan migrasi
migrated = migrate_shortener_config()

if migrated:
    print("✅ Config berhasil dimigrasikan")
else:
    print("ℹ️  Config sudah versi terbaru")
```

## Apa yang Dipreservasikan

Selama migrasi, hal-hal berikut **DIJAGA**:

✅ Status `enabled` untuk setiap provider
✅ Konfigurasi autentikasi (API keys, tokens)
✅ Custom headers yang telah diset
✅ Body parameter kustom
✅ Custom providers tambahan (provider yang tidak ada di template default)
✅ API URL yang sudah disesuaikan
✅ Method HTTP yang dipilih
✅ Response type dan parsing rules

## Apa yang Diupdate

Migrasi akan menambahkan/update:

📝 Version field (dari 1.0 ke 2.0)
📝 Struktur provider baru (jika ada)
📝 Field-field baru yang diperlukan
📝 Metadata migrasi

## Backup File

Setiap kali migrasi dilakukan, backup otomatis dibuat:

```
data/
├── shorteners.json                    (File terbaru setelah migrasi)
└── shorteners.json.pre-migration-backup    (Backup sebelum migrasi)
```

Backup dapat digunakan jika perlu rollback:

```bash
cp data/shorteners.json.pre-migration-backup data/shorteners.json
```

## Contoh Migrasi

### Sebelum Migrasi (v1.0)
```json
{
  "providers": {
    "tinyurl": {
      "name": "TinyURL",
      "enabled": true,
      "api_url": "https://api.tinyurl.com/create"
    }
  }
}
```

### Sesudah Migrasi (v2.0)
```json
{
  "version": "2.0",
  "migration_source_version": "1.0",
  "providers": {
    "tinyurl": {
      "name": "TinyURL",
      "description": "Free URL shortener with API key",
      "enabled": true,
      "api_url": "https://api.tinyurl.com/create",
      "method": "post",
      "headers": {
        "Content-Type": "application/json"
      },
      "auth": {
        "type": "header",
        "headers": {
          "Authorization": "Bearer YOUR_KEY"
        }
      },
      "body": {
        "url": "{url}"
      },
      "response_type": "json",
      "success_check": "status in (200, 201) and response.get('data', {}).get('tiny_url')",
      "url_extract": "response.get('data', {}).get('tiny_url', '')"
    }
  },
  "default_provider": "tinyurl",
  "fallback_provider": "tinyurl"
}
```

## Troubleshooting

### Migrasi Gagal

Jika migrasi gagal, pesan error akan ditampilkan:

```
❌ Failed to migrate shortener config: [error details]
```

**Solusi:**
1. Cek permission folder `data/`
2. Cek format JSON file `shorteners.json`
3. Cek disk space yang tersedia
4. Lihat log lengkap dengan `--verbose`

### Rollback

Jika ada masalah setelah migrasi:

```bash
# Restore dari backup
cp data/shorteners.json.pre-migration-backup data/shorteners.json

# Reload aplikasi
python run.py
```

### Verifikasi Migrasi

Cek apakah migrasi berhasil:

```bash
python scripts/migrate_shorteners.py --preview
```

Output akan menunjukkan status versi file.

## Logging Migrasi

Log migrasi akan ditampilkan di console dan log file:

```
2025-12-19 10:30:45,123 - shortener.shortener - INFO - Schema migration detected. Running migration...
2025-12-19 10:30:45,456 - shortener.shortener - INFO - Backup of pre-migration config created at: data/shorteners.json.pre-migration-backup
2025-12-19 10:30:45,789 - shortener.shortener - INFO - Preserved custom provider: my_custom_provider
2025-12-19 10:30:46,012 - shortener.shortener - INFO - ✅ Config migrated and saved successfully to: data/shorteners.json
```

## FAQ

### Q: Apakah migrasi berjalan otomatis?
**A:** Ya! Migrasi deteksi otomatis saat aplikasi startup. Jika ada perubahan skema, migrasi akan berjalan otomatis.

### Q: Bagaimana jika saya tidak ingin migrasi otomatis?
**A:** Anda masih bisa rollback dengan restore backup. Migrasi dirancang aman dan reversibel.

### Q: Apakah API keys saya akan hilang?
**A:** Tidak! Semua konfigurasi autentikasi dipreservasikan selama migrasi.

### Q: Apa beda antara migrasi otomatis dan script manual?
**A:** 
- **Otomatis**: Berjalan di background, transparan
- **Manual**: Memberikan kontrol lebih (preview, force), cocok untuk debugging

### Q: Berapa lama migrasi?
**A:** Biasanya < 1 detik untuk file standard.

---

**Dokumentasi terakhir diupdate**: 19 Desember 2025
