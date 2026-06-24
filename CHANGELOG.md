# Changelog

All notable changes to this project will be documented in this file.

## [v2026.06.24] - 2026-06-24

### Added
- **Zoom Security Update**: Merespons kebijakan Zoom terbaru yang mewajibkan Passcode atau Waiting Room, bot sekarang mengekstrak dan menampilkan Passcode secara eksplisit pada balasan ke pengguna ketika meeting berhasil dibuat.
- Ditambahkan pengabaian folder `graphify-out/` dan file `run_graphify.py` pada `.gitignore`.

### Changed
- Pembaruan struktur output dokumentasi `README.md` terkait kebijakan Passcode.

### Fixed
- Memperbaiki parsing JSON `pip-audit` pada `scripts/check_dependencies.py` yang sebelumnya mengalami `AttributeError` akibat perbedaan format respons antar versi `pip-audit`.
- **Security Update**: Memperbarui versi dependency `pytz`, `pytest`, `pytest-asyncio`, dan `pip-audit` serta *core packages* di Dockerfile untuk mengatasi peringatan kerentanan keamanan (*vulnerabilities*).
