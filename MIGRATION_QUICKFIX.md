# 🚨 Quick Fix: "no such column: cloud_recording_data"

## Penyebab
Database production Anda tidak memiliki kolom terbaru yang diperlukan oleh kode.

## ✅ Solusi Tercepat

### Opsi 1: Auto-Migration via Restart (RECOMMENDED)
```bash
# Stop bot
docker stop <container_name>

# Start bot (migration otomatis berjalan)
docker start <container_name>

# Monitor logs untuk memastikan migration sukses
docker logs -f <container_name> | grep -i migration
```

**Expected log output:**
```
Running database migrations
Adding cloud_recording_data column to meetings table
Migration 2 completed: cloud_recording_data column added
Database migrations completed
```

---

### Opsi 2: Manual Migration Script
```bash
# Jalankan migration script
docker exec -it <container_name> python scripts/run_migration.py

# Restart bot
docker restart <container_name>
```

---

### Opsi 3: Menggunakan Makefile (Recommended untuk Dev)
```bash
# Production
make migrate
make restart

# Development
make migrate-dev
make dev-restart

# Check database schema
make db-check
```

---

## 🔍 Verifikasi

Cek apakah kolom sudah ada:
```bash
docker exec <container_name> sqlite3 /app/zoom_telebot.db \
  "SELECT sql FROM sqlite_master WHERE name='meetings';"
```

Seharusnya ada baris:
```
cloud_recording_data TEXT
```

---

## 📚 Dokumentasi Lengkap
Lihat [docs/DATABASE_MIGRATION_GUIDE.md](docs/DATABASE_MIGRATION_GUIDE.md) untuk detail lengkap.

---

## ⚠️ Troubleshooting

### Migration tidak berjalan saat restart
1. Cek apakah `init_db()` dipanggil di startup
2. Cek logs untuk error messages
3. Jalankan manual migration: `docker exec <container_name> python scripts/run_migration.py`

### Error "database is locked"
```bash
# Stop bot dulu
docker stop <container_name>

# Jalankan migration
docker exec <container_name> python scripts/run_migration.py

# Start bot
docker start <container_name>
```

### Tetap error setelah migration
1. Pastikan bot sudah di-restart
2. Verify database path correct: `echo $DATABASE_URL` atau `echo $DB_PATH`
3. Check file permissions: `docker exec <container_name> ls -la /app/zoom_telebot.db`
