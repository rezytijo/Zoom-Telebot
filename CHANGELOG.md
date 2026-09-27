# Changelog

All notable changes to this project will be documented in this file.

## [v2026.09.27h] - 2026-09-27 19:40 (Audit mode agent: tidak perlu MCP Playwright)

### Answered
- **"Apakah perlu install MCP Playwright agar AI agent bisa remote browser?"** Tidak, dan itu tidak akan membuat apa pun bekerja. Buktinya dari kode, bukan asumsi:
  1. **Mode `agent` adalah kerangka tanpa implementasi.** `ZOOM_CONTROL_MODE=agent` hanya menambah tombol "Control Meeting", "Mute All", dan pemilihan agent dari tabel `agents`. Tabel itu ada, `add_agent`/`list_agents` ada — tapi **tidak ada satu pun kode yang memanggil `base_url` milik agent**. Bot tidak pernah bicara ke agent. Folder `c2/` (Agent Layer) yang direncanakan di `context.md` tidak pernah dibuat.
  2. **`get_pending_commands()` ada tapi nol pemanggil.** Diekspor dari `db/__init__.py`, tidak dipanggil di bot, host, atau mana pun. Bot menulis antrean lewat `add_command()`; tidak ada yang membacanya. Kalau mode agent dihidupkan sekarang: bot mengantri `start_zoom`, menampilkan "Meeting telah diantrikan", lalu **tidak terjadi apa-apa selamanya** — dan `check_timeout_commands()` hanya menghitung, tidak memberi tahu user.
  3. **MCP Playwright menjalankan browser di tempat proses MCP-nya hidup** — mesin dev, mati bersama prosesnya. Yang dibutuhkan bot bukan "kemampuan browsing", tapi browser yang hidup terus di server. Itu sudah ada: `remote_browser/`, service aiohttp dengan bearer token yang menjalankan Chromium sendiri,dengan state di  di `zoom_browser_state:/data`. Dan itu **bukan MCP** — bot bicara lewat `RemoteZoomClient` biasa.
  4. Sesi Zoom di `remote_browser` sudah terverifikasi hidup: `session_ready: True, stored: True`.

### Fixed
- **`.mcp-probe/` tidak di-gitignore.** Skrip di sana membaca `state.vscdb` milik VS Code dan mencetak nilai kunci yang cocok `%mcp%` — isinya konfigurasi MCP server, lengkap dengan bearer token untuk apa pun yang sudah di-connect operator. File ini tidak boleh masuk repo. Ditambahkan ke `.gitignore` dengan alasannya, bukan cuma baris pola.

### Security verification
- **Dry-run `git add -An` sebelum push.** Scanner tidak bisa------------------------------------------------------------------------membuktikan file berstatus ignored benar-benar tidak akan ikut; yang bisa adalah melihat daftar file yang *akan* ter-add. Dicek terhadap `.env`, `*.session`, `*.db`, `tg_credentials.json`, `zoom_web_session.json` — **nol kebocoran**, semua sudah tertangkap `.gitignore`.

### Verified
- 46/46 unit test hijau, scan karakter asing bersih, kedua service rebuild dan ter-deploy.

## [v2026.09.27g] - 2026-09-27 19:05 (Tombol Uji Sesi Zoom)

### Added
- **Tombol 🩺 Uji Sesi Zoom** di panel Backup & Restore. Permintaan user: "takutnya sudah expired". Sebelumnya operator hanya bisa menebak — jalan satu-satunya untuk memastikan adalah meng-upload ulang file, yang membazir dan tidak membuktikan apa pun kalau sesinya memang masih hidup.
- **`POST /zoom/session/check` di host.** Bedanya dengan `/status` bukan derajat tapi **jenis**: `/status` melaporkan apa yang keberadaan file menyiratkan, endpoint ini melaporkan apa yang Zoom bilang setelah file itu benar-benar dimuat. Hanya yang ini bisa menangkap sesi yang ada di disk tapi sudah ditolak Zoom — kegagalan yang tidak bisa didiagnosis sendiri oleh operator.
- **`RemoteZoomClient.check_session()`** sebagai padanan. Terpisah dari `status()` bukan karena ribet, tapi karena biayanya berbeda: yang ini menyalakan Chromium dan menunggu `zoom.us`, sampai 30 detik.
- **`_session_action_keyboard()`** di setiap pesan gagal. Pesan buntu lebih buruk daripada tidak ada pesan — user harus mencari sendiri tombolnya, persis di pesan tempat ia butuh tombol itu.
- **10 test** (`tests/test_session_test_button.py`): tombol muncul hanya di mode remote, `callback_data` punya handler, sesi valid/expired/tidak pernah diunggah dibedakan, alasan host diteruskan apa adanya, non-admin tidak pernah mendapat vonis, dan `c.answer()` tidak menunggu cek lambat.

### Fixed
- **`check_session()` di host sudah ada tapi tidak pernah tersambung ke route.** Fungsi itu justru ditulis khusus untuk memisahkan "cookie kamu basi" dari "pemeriksaan-nya yang meledak" — dua-duanya `False`, dan hanya yang pertama salah operator. Tanpa itu, user dikirim ekspor ulang cookie yang tadinya bukan masalahnya. Voices code-nya sudah benar; yang hilang hanya kawat nyambungnya.

### Notes
- **`c.answer()` dijawab sebelum cek lambat dimulai.** Kalau tidak, tombol berputar selama 30 detik penuh dan Telegram akhirnya menampilkannya sebagai tombol mati. Hasil dikirim ke pesan terpisah, bukan berebut bubble yang sama dengan panel.
- **`_reply_with` diduplikasi dari `session_handlers._finish` secara sengaja.** Yang latter meng-hardcode tombol back-nya sendiri; mengimpornya akan diam-diam membuang tombol Import dari pesan gagal — pesan yang justru paling butuh tombol itu.

### Verified
- **46/46 unit test hijau** (dari 36; +10).
- Endpoint diuji langsung dari dalam container: `session_ready: True, stored: True, detail: ''` — sesi user **memang valid**. Jalur gagal juga diuji (token salah) dan menolak dengan 401, bukan crash.
- Log host mengonfirmasi `POST /zoom/session/check` → `200`, dan `Chromium started` on-demand sesuai desain (host idle tidak menahan browser).
- Scan karakter asing bersih.

## [v2026.09.27f] - 2026-09-27 18:20 (Upload sesi Zoom crash total)

### Fixed
- **Fitur upload sesi Zoom gagal total** dengan `TypeError: receive_session_file() got multiple values for argument 'bot'`. Penyebabnya konvensi pemanggilan aiogram: `Handler.call` melakukan `partial(self.callback, *args, **kwargs)`, jadi event selalu masuk ke slot positional pertama, sedangkan `bot` dan `state` datang sebagai **kwargs**. Parameternya terbalik — `bot: Bot` ditulis lebih dulu — sehingga event terikat ke slot bot, lalu kwargs `bot=` menabrakkan diri. Route terdaftar, filter cocok, lalu handler langsung crash di pesan pertama. Setiap upload gagal di langkah terakhir, dan operator tidak melihat apa pun.
- Test lama justru **menyalin bug-nya sendiri**: keenam call site memanggil `receive_session_file(FakeBot(...), msg, state)`. Karena dipanggil langsung, test selalu hijau tidak peduli bagaimana pun urutannya. Bug ini tidak bisa terlihat tanpa melewati mekanisme aiogram.

### Added
- **`tests/test_handler_dispatch_order.py`** — 4 test. Yang inti membungkus callback dengan `HandlerObject` aiogram sungguhan lalu memanggilnya persis seperti dispatcher: event positional, `bot`/`state` sebagai kwargs. Nama parameternya *harus* kebetulan cocok, jadi tes ini gagal kalau urutannya salah.
- **Sweep semua handler terdaftar**, bukan cuma yang kebetulan rusak. Sumber datanya `router.<observer>.handlers`, bukan namespace modul — modul ini meng-*re-export* belasan helper DB (`add_meeting`, `get_user_by_telegram_id`, dst.) yang sama sekali tidak ada hubungannya dengan dispatch Telegram, dan versi pertama sweep salah tangkap semuanya.
- **Status sesi di menu Backup & Restore.** Sebelumnya "apakah sesi saya tersimpan?" tidak punya jawaban di mana pun: umpan balik satu-satunya adalah konfirmasi import, yang segera hilang dari layar dan tidak menyebut import *sebelumnya*. Baris status baru membaca `session_ready` dari host — dan itu **live check, bukan sekadar file exists**, karena file bisa ada di disk sementara Zoom sudah meng-*expire*-nya. Persis itulah kegagalan yang peringatan import harus jelaskan. Status `saved` di DB host berarti "sudah pernah disimpan", bukan "masih valid" — dua hal berbeda, dan hanya yang kedua yang dipakai user.

### Answered
- **Docker Compose sudah benar.** `SESSION_FILE` di host resolve ke `/data/zoom_web_session.json`, dan `zoom-browser` sudah me-mount named volume `zoom_browser_state:/data` read-write. Dikonfirmasi: `zoom_web_session.json` (2.9K) benar-benar ada di dalam volume. Yang membedakan volume bot (`data:/app/data` — DB + shorteners) dari volume host: **sesi Zoom tinggal di host, bukan di bot.** Menghapus container bot tidak menyentuh sesi. Penulisan juga atomik (`tmp` + `os.replace` + `fsync`), jadi crash di tengah tidak menggagalkan sesi lama.

### Verified
- Regresi dibuktikan dua arah: bug dikembalikan sementara → **3 dari 4 test gagal** dengan pesan yang tepat; dipulihkan → 4/4 hijau.
- **36/36 unit test hijau** (naik dari 27; +4 dispatch order, dan 6 test session import kini memanggil dengan urutan benar).
- Fix ter-deploy: signature di dalam container sudah `receive_session_file(msg: Message, bot: Bot, state: FSMContext)`.
- Jalur import diuji langsung dari dalam container: payload rusak ditolak bersih (`CLEAN_REJECT: JSON tidak valid: Expecting value (baris 1)`), bukan 500.
- Scan karakter asing bersih.

## [v2026.09.27e] - 2026-09-27 (Meeting test bocor ke akun Zoom asli)

### Fixed
- **14 meeting test menumpuk di akun Zoom asli** dan tidak pernah dihapus. Penyebabnya struktural, bukan satu bug: cleanup ada **di ujung jalur bahagia**, bukan di `finally`. Setiap `assert` yang gagal melewati cleanup, dan setiap run berikutnya menambah satu lagi. Empat meeting bocor dalam satu sore.
- **`test_remote_host_join` sama sekali tidak punya cleanup Zoom** — itu yang menyumbang 6 dari 14. Worse, test itu `pytest.skip` di cabang "host tidak pernah join", yang justru cabang yang paling sering terjadi, jadi cleanup di jalur bahagia pun tidak akan pernah jalan.
- **Delete meeting tidak menghapus cloud recording-nya.** Zoom menyimpan recording di tab Recordings akun sampai di-*trash* eksplisit, dan recording itu **bertahan melewati meeting-nya**. Akun Zoom yang "bersih" tapi masih menyimpan semua recording test bukan bersih.

### Added
- **`tests/zoom_test_cleanup.py`** — satu helper untuk ketiga integration test. Recordings di-*trash* **dulu**, baru meeting dihapus, jadi kalau proses mati di tengah, yang tertinggal adalah meeting hidup yang recording-nya sudah di trash (bisa dipulihkan). Arah sebaliknya meninggalkan meeting hancur dengan recording hidup — artefak yang tidak terlihat siapa pun berbulan-bulan.
- **10 test untuk helper-nya**, karena ini kode yang bisa menghapus meeting orang: batas prefix-vs-topic manusia, urutan trash-sebelum-delete, kegagalan recording tidak menghalangi penghapusan meeting, dan `cleanup_zoom_meetings` tidak pernah raise maupun redden test.
- **`--dry-run` dan `--db`** untuk script-nya. `--db` ada karena bot normalnya jalan di container dengan file DB-nya sendiri; membersihkan DB host saja cuma memindahkan masalah.

### Security decision
- **`created_by` tidak bisa jadi discriminator.** Test memanggil bot lewat bot lewat akun Telegram asli, jadi row-nya carrying user ID operator sendiri. Kalau difilter itu, meeting yang dibuat manual oleh orang juga ikut terhapus. Yang dikendalikan penuh oleh test end-to-end cuma topic.
- **Matcher wajib prefix + timestamp utuh, bukan startswith.** Versi pertama hanya cek `startswith(prefix)`, dan unit test langsung menangkapnya: `"Integration Test Meeting Planning"` ikut kena — itu bisa berarti rapat manusia. Perbaikannya: topic harus persis `prefix` + angka unix 9-11 digit, tanpa kata lain di antaranya. Ada test yang mengunci kedua kasus itu bersama-sama, supaya matcher tidak pernah diam-diam jadi tidak berguna lagi.

### Known limitation
- **Recording test tidak bisa dihapus dengan token saat ini.** Server-to-server OAuth token proyek ini tidak punya scope `recording:write:admin`, jadi Zoom menjawab `400 code 4711`. Jalur kodenya benar dan tetap ada; yang perlu adalah memberi scope itu di Zoom App. Sampai itu dilakukan, **meeting dibersihkan, recording tidak** — dan laporan menyatakan begitu secara jujur, bukan mengklaim berhasil.

### Verified
- **Zoom: 0 upcoming meeting tersisa** setelah 14 dihapus, dikonfirmasi ulang lewat `list_upcoming_meetings`, bukan diasumsikan dari exit code.
- **Kedua database 0 active**: host `zoom_telebot.db` dan `zoom_telebot.db` di dalam container. Yang container sempat tertinggal karena `mark_deleted_in_db` hanya menulis ke file host — itulah alasan `--db` ditambahkan.
- 10/10 test cleanup hijau, 27/27 untuk suite unit (`test_zoom_test_cleanup` + `test_bot_session_import`), 30 test tercollect, scan karakter asing bersih.

## [v2026.09.27d] - 2026-09-27 (Verifikasi tombol import dengan pytest)

### Fixed
- **11 assertion import sesi tidak pernah dijalankan pytest** — filenya bernama `tests/bot_session_import_selfcheck.py`, dan `pytest tests/` hanya mengumpulkan `test_*.py`. Jadi suite itu hijau setiap kali dijalankan manual, tapi **tidak pernah terpicu oleh CI maupun `pytest tests/`**. Ini kelas kegagalan yang lebih buruk dari ketiadaan test: ada coverage, tapi tidak ada yang memakai. Diubah nama filenya menjadi `tests/test_bot_session_import.py`; sekarang ikut CI dan ikut `pytest tests/`.
- **Asyncio strict diam-diam men-skip test async tanpa marker** (`pytest.ini`): `asyncio_mode = auto`, bukan `strict`. Di mode strict, `async def test_` tanpa `@pytest.mark.asyncio` **tidak gagal — ia di-skip**, jadi suite bisa hijau tanpa menguji apa pun. Diverifikasi dulu: ketiga test async yang sudah ada punya marker eksplisit, jadi `auto` tidak mengubah perilaku mereka, hanya mengaktifkan 10 test baru tanpa marker. `asyncio_default_fixture_loop_scope` ikut diset agar tidak ada warning EventLoop.
- **Tiga test tombol baru**, karena tidak ada satu pun pengujian yang menyentuh tampilan yang dilaporkan user:
  - `test_backup_panel_renders_the_import_button` — bukan cuma "ada tombol", tapi `callback_data`-nya persis `zoom_import_session`. Typo di `callback_data` merender tombol yang terlihat benar tapi **tidak sampai ke handler siapa pun**.
  - `test_import_button_is_reachable_from_the_main_menu` — tombol di panel yang tidak bisa dibuka bukan fitur. Menguji jalur klik yang sebenarnya: menu utama → Backup & Restore → import.
  - `test_import_button_unreachable_for_a_regular_user` — panelnya admin-only; menu utama adalah gerbang yang mencegah user biasa diberi jalur itu.
  - `test_button_callback_has_a_handler` — `callback_data` tanpa `callback_query` handler yang cocok di-drop **senyap** oleh aiogram: tombol muncul, tap tidak melakukan apa-apa, dan tidak ada satu baris log pun yang menjelaskannya. Ini proksi statis terdekat dari gejala yang dilaporkan.
  - `test_callback_arms_the_state_for_an_admin` / `test_callback_rejects_a_non_admin_before_arming_the_state` — tap adalah satu-satunya tempat state di-set, jadi kedua sisi diuji: admin benar-benar membuka alur dan melihat langkah export, non-admin tidak pernah meng-*arm* state milik orang lain.

### Verified
- **17/17 hijau** (`pytest tests/test_bot_session_import.py -v`), plus `remote_browser/selfcheck.py` exit 0 dan `tests/host_confirmation_selfcheck.py` exit 0.
- **Regression test `restart()` terbukti masih bergigi** — `restart()` sengaja dikembalikan ke versi lamanya (`context.close()` tanpa `_release()`), self-check keluar `EXIT=1` dengan `AttributeError: 'NoneType' object has no attribute 'close'`; setelah dikembalikan, `EXIT=0`. **Test yang tidak pernah terlihat gagal bukan bukti apa pun.**
- **Tiga kegagalan `pytest tests/` yang tersisa bukan regresi.** Semuanya integration test lama yang butuh bot live: `test_remote_host_join` gagal karena "Remote Zoom controller is not reachable" — layanan itu adalah **Kasm `zoom-remote` yang sudah dinyatakan gagal** dan digantikan `zoom-browser`, jadi test-nya masih menunjuk endpoint yang sudah tidak ada. `test_bot_integration` dan `test_meeting_details_controls` gagal karena container `zoom-telebot-soc` sedang berjalan dan **memakan update Telegram** yang seharusnya dilihat bot lokal — persis seperti pesan peringatan di test itu sendiri. Setelah container dihentikan, 19 dari 20 lulus; container sudah dijalankan kembali dan lingkungan pengguna dipulihkan.

## [v2026.09.27c] - 2026-09-27 (Tombol import tidak terlihat: image lama + dokumentasi salah)

### Fixed
- **Image `zoom-telebot` tidak pernah di-rebuild sejak fitur import dibuat**, jadi container berjalan dengan `keyboards.py` lama — `grep -c zoom_import_session /app/bot/keyboards.py` = `0` di dalam container, padahal ada di workspace. Gejalanya identik dengan fitur yang tidak ada. **Kode yang benar di workspace tidak berarti kode yang jalan.** Setelah rebuild, `backup_menu_keyboard()` merender 4 baris (Backup / Restore / **Import Sesi Zoom** / Kembali).
- **Dokumentasi salah arah** (`Readme.md`): `/backup` ditulis seolah-olah membuka panel tombol, padahal `cmd_backup` di `bot/handlers.py` **langsung membuat file zip**. Panel tombolnya ada di `menu_backup` (💾 Backup & Restore di menu utama). Dua tempat di Readme diperbaiki. Dokumentasi yang salah arah lebih buruk daripada tidak ada dokumentasi — user diarahkan mencari tombol di tempat yang memang tidak punya tombol.
- **Harness test bot mengarang `is_owner_or_admin` sebagai fungsi async** (`tests/test_bot_session_import.py`): fungsi aslinya di `bot/auth.py` adalah `def` biasa, dan handler memanggilnya tanpa `await`. Fake-nya `async def`, jadi mengembalikan objek coroutine yang **selalu truthy** — `if not <coroutine>` bernilai `False` dan **seluruh pemeriksaan izin dalam 11 kelompok assertion itu tidak menguji apa pun**. Gejalanya `test_non_admin_cannot_import` gagal: byte milik non-admin diteruskan ke host. Guard di `bot/session_handlers.py` **benar dan tidak diubah** — yang salah adalah fake-nya.
- **Tiga jebakan harness lain di file yang sama** (semuanya di perakh, bukan produksi): (1) `bot/keyboards.py` meng-`import settings` langsung dari `config`, jadi menambal `session_handlers.settings` tidak pernah menjangkau `settings.zoom_control_mode` yang dibaca keyboard — harus menambal `keyboards.settings`; (2) `Bot.answer()` mengembalikan objek `Message` yang kemudian diedit `_finish()`, sedangkan fake-nya mengembalikan `None` → `AttributeError: 'NoneType' object has no attribute 'edit_text'`; (3) `restore()` awalnya menulis 3-tuple ke 4 atribut, sehingga test saling menimpa nilai pemulihannya sendiri.

### Added
- **Tiga suite self-check sekarang jalan otomatis di CI** (`security-audit-and-test.yml`, job `run-selfcheck`): `tests/test_bot_session_import.py`, `remote_browser/selfcheck.py`, dan `tests/host_confirmation_selfcheck.py`. Sebelumnya ketiga suite itu hanya dijalankan manual di PC — **survey green yang tidak dipicu siapa pun akan tetap hijau selamanya**, dan bug `restart()` sudah terbukti bisa lolos ke produksi selama ini justru karena tidak ada yang menjalankannya otomatis.
- **Job `chromium-selfcheck`**: membangun image host lalu menjalankan self-check **di dalamnya**, di jadwal nightly (`37 3 * * *`) dan saat manual dispatch. Alasan dipisah dari jalur push: test `restart()` yang menangkap `TargetClosedError` **hanya bisa gagal di dalam image**, sedangkan image itu ~1,4 GB browser binaries. Jalur push tetap dijaga suite biasa; grup yang butuh Chromium **mencetak alasannya lalu skip**, bukan gagal diam-diam.
- **Job `credential-guard`** — dua lapis pengaman untuk cookie sesi Zoom:
  - Scan **file terlacak** untuk tiga nama cookie sesi (`_zm_page_auth`, `_zm_multi_ac`, `zm_haid`). `.gitignore` hanya melindungi file baru; file yang sudah terlacak tidak bisa dijangkaunya sama sekali. Pola sengaja **tidak** memakai `zoom_web_session`, karena string itu adalah nama file sah yang muncul di `.gitignore`, `docker-compose.yml`, dan dokumentasi — mencocokkannya membuat guard gagal pada konfigurasinya sendiri, dan guard yang hanya bisa gagal tidak akan pernah dijalankan.
  - Verifikasi bahwa `dbg/s.json`, `zoom_web_session.json`, dan `data/zoom_web_session.json` benar-benar ter-ignore, sehingga aturan tidak bisa hilang diam-diam saat `.gitignore` diedit.
  - **Kedua arah sudah dibuktikan lokal**: repo bersih → lulus, dan file dummy `dbg/leak_probe.json` berisi `_zm_page_auth` → **tertangkap**. Guard yang tidak pernah diuji menangkap apa pun tidak berguna.
- **Self-check import sesi tanpa jaringan** (`tests/test_bot_session_import.py`, baru): 11 kelompok assertion yang **tidak** butuh token Telegram, tidak menyentuh Zoom, dan tidak memanggil jaringan sama sekali — `Bot`, `File`, `Message`, `FSMContext` semuanya di-fake. Yang diuji adalah perilaku yang benar-benar bisa rusak: tombol hanya muncul saat `zoom_control_mode == "remote"`, router sesi terdaftar **sebelum** catch-all, non-admin tidak bisa meng-import, mode kontrol salah ditolak, file >4 MB ditolak **sebelum** diunduh, `/cancel` menghapus state, teks liar tidak memicu import, dan nilai cookie tidak pernah muncul di source.

### Verified
- **Tiga suite hijau bersamaan**: `tests/test_bot_session_import.py` **11/11 exit 0**; `remote_browser/selfcheck.py` exit 0; `tests/host_confirmation_selfcheck.py` exit 0. Yang menentukan: perbaikan harness **tidak menyentuh satu baris pun kode produksi**, dan dua suite produksi tetap hijau — itu bedanya dengan menutupi regresi.
- **Ketiga workflow YAML valid** dan ter-parse: `security-audit-and-test.yml` kini punya 4 trigger (`push`, `pull_request`, `workflow_dispatch`, `schedule`) dan 5 job. `Build-&-Deploy.yml` dan `Build-Dev.yml` **tidak disentuh** — `git diff` kosong untuk keduanya.
- **YAML workflow diverifikasi lokal sebelum commit**, bukan diasumsikan benar. Job `run-selfcheck` yang baru menjalankan ketiga suite secara lokal lebih dulu: `BOT=0 HOST=0 CONFIRM=0`, dengan `repeated restart SKIPPED (no Playwright browser binary)` — persis perilaku yang dikomentari di dalam workflow, bukan asumsi.
- **Graphify diperbarui** (`graphify . --update --code-only` + `graphify cluster-only . --code-only`): 1112 node, 2559 edge, 60 komunitas, 52 file ter-extract. Modul baru masuk: `session_handlers` (187 hit), `bot_session_import_selfcheck` (389 hit), `import_session` (30), `check_session` (6), `save_session_file` (7), `cookies_to_storage_state` (10). **Nol kredensial bocor ke graph** — `aw1_c_` dan `42ED75554C` = 0 hit di `graph.json`, `GRAPH_REPORT.md`, dan `graph.html`.

### Notes
- **Kredensial Zoom bocor ke dalam workspace dan hampir ter-commit** — `dbg/s.json` berisi export Cookie Editor **nyata**: `_zm_page_auth`, `cred` untuk `us06web.zoom.us`, `zm_haid`, `_zm_multi_ac`. File ini tidak pernah terlacak git dan tidak ter-*ignore*, jadi bisa ikut ter-*stage* tanpa disadari. Berkas sudah dihapus, `dbg/` sekarang di-`.gitignore`, Plus jaring pengaman `*cookies*.json` dan `*session_export*.json`. Dicatat karena **nilai yang sudah pernah ada di dalam working tree tidak bisa dianggap aman** — kalau cookie itu dari akun nyata, tetap lakukan logout di Zoom. Aturan baru sengaja lebih sempit dari `*.json` karena repo butuh JSON asli (mis. `data/shorteners.json`); sudah diverifikasi tidak ada file terlacak yang ikut kena.
- **Saat test gagal, periksa dulu apa yang dipalsukan harness sebelum menyalahkan kode produksi.** Untuk test permission/auth, fake yang terlalu longgar membuat seluruh kelas test diam-diam tidak bergigi — lebih buruk dari test yang tidak ada, karena ia terlihat hijau.

## [v2026.09.27b] - 2026-09-27 (Import Sesi Zoom dari Telegram)

### Fixed
- **`restart()` meninggalkan context yang sudah mati** (`remote_browser/server.py`): `restart()` menutup context tapi **tidak pernah menolakkan handlenya**, sehingga `_ensure_started()` melihat `self._context` yang masih truthy, melewati launch, dan `new_page()` berikutnya mati dengan `TargetClosedError: BrowserContext.new_page`. Import pertama sempat terlihat benar hanya karena **lazy Chromium** membuat belum ada browser yang hidup saat restart pertama terjadi — bug ini baru muncul di restart kedua, yaitu saat user benar-benar meng-import ulang. Diubah ke `await self._release()`, yang juga menolakkan handle dan menghentikan Playwright. **Bug laten yang hanya ditemukan dengan memanggil endpoint-nya dua kali**, bukan dengan membaca kodenya.
- **Laporan hasil import yang tidak bisa ditindaklanjuti** (`remote_browser/server.py`): jalur `except` menyimpan alasan ke `detail` tapi tidak pernah mengisinya ke `reload_error`, jadi host menjawab `{"signed_in": false, "reload_error": ""}` — operator tidak bisa membedakan cookie yang ditolak Zoom dari host yang rusak, padahal keduanya butuh perbaikan berbeda. Ditambah `check_session()` yang mengembalikan `(bool, alasan)`, dan `session_ready()` kini mencatat alasan sebenarnya (ditolak Zoom vs pengecekan yang error). **Aturan yang ditegakkan test: `signed_in: false` tanpa alasan = laporan yang tidak bisa ditindaklanjuti.**
- **`test_browser_stays_off_until_needed` bergantung pada asumsi yang hanya benar di mesin penulis** (`remote_browser/selfcheck.py`): komentar lamanya *"expected no session file on a dev box"* — di dalam container host `/data/zoom_web_session.json` justru **ada**, jadi test gagal padahal tidak ada bug. Sekarang `SESSION_FILE` diarahkan ke path yang dijamin tidak ada, alih-alih mengandalkan kondisi sekeliling.
- **`test_session_import_endpoint` mengklaim satu hasil verifikasi tertentu** (`remote_browser/selfcheck.py`): `assert signed_in is False` + `assert reload_error` hanya berlaku di mesin tanpa Chromium. Di dalam image host Chromium benar-benar boot, sehingga assertion itu salah. Diganti assertion kontrak kejujuran yang berlaku di kedua tempat.
- **Harness test bot mengarang `is_owner_or_admin` sebagai fungsi async** (`tests/test_bot_session_import.py`): fungsi aslinya di `bot/auth.py` adalah `def` biasa, dan handler memanggilnya tanpa `await`. Fake-nya `async def`, jadi mengembalikan objek coroutine yang **selalu truthy** — `if not <coroutine>` bernilai `False` dan **seluruh pemeriksaan izin dalam test itu lolos tanpa pernah menguji apa pun**. Akibatnya `test_non_admin_cannot_import` gagal (`payloads: [b'[]']`, `answers: []`): byte milik non-admin diteruskan ke host. Guard di `bot/session_handlers.py` sendiri **benar** dan tidak diubah; yang salah adalah fake-nya. Produksi tidak perlu disentuh saat test gagal.
- **Tiga jebakan harness lain di file yang sama** (semua di perakh, bukan produksi): (1) `bot/keyboards.py` meng-`import settings` langsung dari `config`, jadi menambal `session_handlers.settings` tidak pernah menjangkau `settings.zoom_control_mode` yang dibaca keyboard — harus menambal `keyboards.settings`; (2) `Bot.answer()` mengembalikan objek `Message` yang kemudian diedit `_finish()`, sedangkan fake-nya mengembalikan `None` → `AttributeError: 'NoneType' object has no attribute 'edit_text'`; (3) `restore()` awalnya menulis 3-tuple ke 4 atribut, sehingga test saling menimpa nilai pemulihannya sendiri.

### Added
- **Self-check import sesi tanpa jaringan** (`tests/test_bot_session_import.py`, baru): 11 kelompok assertion yang **tidak** butuh token Telegram, tidak menyentuh Zoom, dan tidak memanggil jaringan sama sekali — `Bot`, `File`, `Message`, `FSMContext` semuanya di-fake. Yang diuji adalah perilaku yang benar-benar bisa rusak: tombol hanya muncul saat `zoom_control_mode == "remote"`, router sesi terdaftar **sebelum** catch-all (dibaca dari urutan di `bot/main.py`), non-admin tidak bisa meng-import, mode kontrol salah ditolak, file >4 MB ditolak **sebelum** diunduh, `/cancel` menghapus state, teks liar tidak memicu import, dan nilai cookie tidak pernah muncul di source. Nol threshold fiktif — fake API Telegram yang terlalu longgar bisa membuat test hijau tanpa menguji apa pun.
- **Import sesi lewat bot, tanpa `docker cp`** (`bot/session_handlers.py`, baru): `/backup` → **🔐 Import Sesi Zoom** → kirim hasil export JSON dari Cookie Editor. Router dipasang **sebelum** router utama karena `bot/handlers.py` diakhiri catch-all yang mencocoki pesan `/...` apa pun — kalau dipasang setelah, `/cancel` akan tertangkap di sana dan import yang sedang menunggu file tidak bisa dibatalkan. Otorisasi `is_owner_or_admin` dicek ulang **di titik pakai**, bukan hanya saat tombol ditekan, karena telegram_id bisa berubah di grup. Ukuran file dibatasi 4 MB. Nilai cookie tidak pernah diecho.
- **Endpoint host `POST /zoom/session`** (`remote_browser/server.py`): menerima body JSON mentah, bukan multipart. Telegram memberi bot `file_id` lalu bot meneruskan byte apa adanya, jadi amplop multipart cuma encoding kedua dari hal yang sama. Multimime ini Everis karena gagal nyata: `request.multipart()` meng-assert content type `multipart/*`, sedangkan yang terkirim `application/json`.
- **`cookies_to_storage_state()`** (`remote_browser/server.py`): menerima array mentah, `{"cookies": [...]}`, atau storage_state asli. Hanya menyimpan domain `.zoom.us`/`zoom.us` (suffix `.zoom.us.evil.com` ikut terbuang), memetakan `expirationDate` → `expires`, `sameSite`, `httpOnly`, `secure`, `path`.
- **Pemeriksaan penanda sesi**: export yang tidak memuat salah satu dari `_zm_page_auth` / `_zm_multi_ac` / `zm_haid` / `cred` **ditolak**, bukan disimpan diam-diam — kalau tidak, sesi yang masih jalan tertimpa cookie pengunjung anonim.
- **`save_session_file()`** (`remote_browser/server.py`): tulis atomik (tmp + `os.fsync` + `os.chmod 0o600` + `os.replace`), jadi crash di tengah tulis menyisakan sesi lama yang masih utuh, bukan file kosong.
- **Import ditolak 409 selagi ada meeting yang berjalan**, karena memuat ulang konteks akan mematikan browser yang sedang dipakai meeting itu.
- **Kontrak "tulisnya berhasil tetap dilaporkan jujur"**: `save_session_file()` sukses tapi verifikasi Chromium gagal → `200 {imported: true, signed_in: false, reload_error}`, **bukan** 500. 500 akan memberi tahu operator file upload-nya hilang padahal file itu sudah tersimpan di disk.
- **`RemoteZoomClient.import_session()` + perbaikan merge header** (`zoom/remote.py`): `headers=self._headers(), **kwargs` akan jadi `TypeError: multiple values for keyword argument 'headers'` untuk pemanggil yang butuh `Content-Type`. Header digabung, dan pesan error teks polos dari host kini diteruskan apa adanya — tanpa itu, penolakan cookie jadi "HTTP 400" tanpa alasan.

### Verified (bukti runtime, bukan asumsi)
- **Import end-to-end dari cookie export nyata → `{"imported":true,"cookies":18,"signed_in":true,"reload_error":""}`.** Ini bukti pertama bahwa host benar-benar bisa autentikasi ke Zoom — blocker `zoom_web_session.json` yang tersisa di laporan sebelumnya sudah cleared.
- **Import kedua langsung setelahnya juga `signed_in: true`.** Inilah yang membuktikan perbaikan `restart()`; sebelum itu, pemanggilan kedua persis menghasilkan `TargetClosedError`. Kasus yang sama, dua kali berturut-turut, di server yang sama.
- Log host: `Session imported (18 cookies)` → `Chromium 153.0.8010.12 started` → `Session import verified against Zoom: signed_in=True`. `GET /status` → `{"status":"idle","session_ready":true,"browser_running":true}`, dan `false` setelah restart — bukti lazy Chromium tetap berlaku.
- **Berkas tersimpan benar**: mode `0600`, 18 cookie, domain tanpa titik depan (`zoom.us` bukan `.zoom.us`), 5 cookie sesi pada sentinel `-1` dan cookie ber-expiry pada float.
- **Test memang menangkap bug, bukan cuma menghijaukan log** — `restart()` yang sengaja dikembalikan ke versi lamanya membuat self-check gagal dengan `EXIT=1` dan `TargetClosedError` yang sama; dengan perbaikan, `EXIT=0`. Test yang tidak bisa gagal tidak layak dipercayai.
- **Bentuk input + alasan penolakan ter-cover** (`remote_browser/selfcheck.py`): 3 bentuk input ternormalisasi identik, JSON rusak memberi alasan bernomor baris, export anonim ditolak, upload buruk **tidak merusak sesi yang sudah ada** (byte-identik sesudahnya), 413 saat kelewat besar, 401 tanpa token, 409 saat meeting hidup, dan restart berulang tetap menghasilkan browser yang bisa dipakai. Total **14 kelompok assertion**.
- **Kedua suite hijau di kedua tempat**: di mesin dev 14 kelompok (satu di-skip karena binary Chromium hanya ada di image) dan `tests/host_confirmation_selfcheck.py`, keduanya exit 0; di dalam container host, 14 kelompok termasuk `repeated restart OK`, exit 0.
- **Tiga suite hijau bersamaan** setelah perbaikan harness: `tests/test_bot_session_import.py` **11/11, exit 0**; `remote_browser/selfcheck.py` exit 0; `tests/host_confirmation_selfcheck.py` exit 0. Yang penting: perbaikan test bot **tidak menyentuh kode produksi**, dan dua suite produksi tetap hijau — jadi ini perbaikan perakh, bukan penutupi regresi.

### Notes
- Cookie sesi adalah **kredensial hidup**. Berkas hasil import sudah otomatis 0600 di dalam volume, `zoom_web_session.json` tetap ada di `.gitignore` (terverifikasi `git check-ignore`), dan fixture di `selfcheck.py` memakai nilai palsu semua.
- **Test harus dijalankan di dalam image host untuk cakupan penuh** — Chromium hanya ada di sana. Di mesin dev, test restart dilewati dengan pesan, bukan diam-diam lolos:
  `docker cp remote_browser\selfcheck.py zoom-browser:/tmp/ && docker compose exec zoom-browser cp /app/server.py /tmp/ && docker compose exec -w /tmp zoom-browser python selfcheck.py`
- **Playwright meninggalkan `/tmp/playwright-artifacts-*` dan `playwright_chromiumdev_profile-*` tiap launch.** Terukur 716K setelah beberapa launch, jadi bukan masalah-now — tapi volumenya tumbuh per meeting dan tidak pernah dibersihkan otomatis. Kalau image dipakai jangka panjang, tambahkan periodic cleanup atau `tmpfs` untuk `/tmp`.
- Satu host = satu meeting. Import di tengah meeting yang hidup memang dikembalikan 409; itu batas desain, bukan bug.

## [v2026.09.27a] - 2026-09-27 (Verifikasi Docker: build + run)

### Fixed
- **Image `zoom-browser` crash-loop karena paket Python `playwright` tidak pernah di-install** (`remote_browser/Dockerfile`). Image `mcr.microsoft.com/playwright/python:v1.63.0-noble` ternyata hanya berisi *browser binaries* + Node CLI, **bukan** paket Python `playwright` — `import playwright` gagal di atas image apa adanya. Dockerfile sekarang `pip install "playwright==1.63.0"`. Kedua pin wajib: paket Python yang menjalankan Chromium, dan tag image yang menentukan build Chromium yang cocok. Versi tidak sinkron adalah penyebab umum `Executable doesn't exist` saat launch.
- **Port host 8080 bentrok** (`docker-compose.yml`, `.env`): `Antigravity IDE` sudah memegang `127.0.0.1:8080`, jadi publish gagal. Mapping jadi `${ZOOM_BROWSER_HOST_PORT:-8080}:8080`, di-`.env` disetel `8090`. Mapping ini cuma buat `curl` operator; bot tetap lewat `zoom-browser:8080` di network internal, jadi bentrok di sini tidak menyentuh jalur bot.

### Verified (bukti runtime, bukan asumsi)
Build dan run pertama kali di container, dengan hasil nyata:
- **RAM idle = 28.96 MiB** (`docker stats zoom-browser`, healthy). Ini angka yang membuktikan desain lazy Chromium v2026.09.26e bekerja — boot-time start akan menunjukkan ±400–600 MB.
- **`/health` terbuka tanpa auth** → `{"ok": true, "zoom_running": false}`; **`/status` tanpa token → 401**; dengan token → `{"status":"idle","meeting_id":"","zoom_running":false,"browser_running":false,"session_ready":false}`. Field `browser_running: false` dengan container healthy = tidak ada Chromium yang tersembunyi.
- **Chromium benar-benar boot**: `153.0.8010.12`, `goto('https://us05web.zoom.us/')` → **HTTP 200**, title `One platform to connect | Zoom`. Egress ke Zoom dari container terbukti terbuka (sebelumnya `zoom.us` 200 sudah pernah terlihat dari container, tapi ini konfirmasi render, bukan cuma TCP).
- **Binary**: image punya `chromium_headless_shell-1243` (default `headless=True` sejak Playwright 1.49), bukan full chromium. Tidak masalah — shell headless memang yang dipakai, dan smoke test membuktikannya jalan.
- **Full stack hidup**: `zoom-browser` (healthy) + `zoom-telebot-soc` (healthy). `ZOOM_CONTROL_MODE=remote`, `ZOOM_REMOTE_BASE_URL=http://zoom-browser:8080` terbaca di dalam container bot, dan `GET /status` dari dalam bot container → 200 dengan JSON yang benar. Jalur bot ke host terbukti, bukan hanya assumed dari config.

### Known Issues (belum selesai)
- **`zoom_web_session.json` belum ada** — `/data` di container kosong, dan tidak ada file di mesin dev. Sampai file itu ada (login interaktif, butuh display + MFA/SSO), `session_ready: false` dan `launch()` nyata akan gagal. Bot bisa start, polling, dan sync; yang belum bisa adalah menjalankan meeting sungguhan. Ini satu-satunya langkah yang belum bisa dibuktikan dari container.

## [v2026.09.26e] - 2026-09-26 (Lazy Chromium: hemat RAM saat standby)

### Changed
- **Chromium tidak lagi jalan 24 jam** (`remote_browser/server.py`): `lifespan` yang melakukan boot-time `host.start()` dihapus. Chromium sekarang dinyalakan oleh `_ensure_started()` pada `launch()` pertama dan dilepas oleh `_release_if_idle()` ketika `stop()`/launch gagal. Effectnya container idle ±400–600 MB menjadi ±50 MB (cuma server aiohttp), sementara container-nya sendiri tetap hidup — nol downtime, nol restart, nol service baru.
- **`session_ready()` ikut lazy**: sebelumnya menolak `False` bila `self._context` belum ada; sekarang memanggil `_ensure_started()` di bawah `self._lock` (tanpa lock, dua request bersamaan akan menjalankan dua Chromium dan membocorkan yang pertama). Path tanpa file sesi tetap return `False` tanpa menyentuh Playwright sama sekali.
- **`restart()` tetap menyisakan browser hidup** (`_ensure_started()` di akhir): restart ini ada untuk membaca ulang `zoom_web_session.json`, jadi harus meninggalkan browser yang siap — kalau ikut dilepas, restart jadi tidak berarti.
- **`snapshot()` menambah `browser_running`**: `zoom_running` hanya menyatakan ada halaman terbuka, jadi nilainya `false` baik saat Chromium hidup maupun mati. Field baru yang membedakan keduanya.
- **`depends_on` bot → `zoom-browser`: health check diganti urutan start biasa** (`docker-compose.yml`): service ini start dalam hitungan detik dan tidak punya startup ordering yang berarti. `condition: service_healthy` hanya menambah risiko: bot tertahan start saat host lambat, tanpa imbalan apa pun.

### Added
- **`BROWSER_MEMORY_LIMIT` (default `1g`) dan `BROWSER_CPU_LIMIT` (default `1.0`)** (`docker-compose.yml`): batas resource untuk `zoom-browser`, disetel untuk kasus meeting aktif. Sebelumnya tanpa batas, jadi runaway Chromium bisa jadi Silent OOM-kill yang mengorbankan host.
- **`test_browser_stays_off_until_needed`** (`remote_browser/selfcheck.py`): assert bahwa setelah `make_app()` dan setelah `session_ready()` tidak ada browser yang hidup, dan `/health` tetap 200 tanpa browser. Tanpa test ini, regresi ke boot-time start tidak akan terdeteksi karena semua test lain berjalan tanpa Chromium. Total 10 kelompok assertion.
- **Stub `no_browser` dihapus** (`remote_browser/selfcheck.py`): override `cleanup_ctx` itu ada khusus untuk men-stub lifespan. Tanpa lifespan, stub-nya jadi kode mati.

### Known Issues (belum selesai)
- **Cold start ±2 detik tiap container.** Launch pertama setelah container start butuh ±2 detik untuk Chromium. Tersembunyi di `ZOOM_REMOTE_LAUNCH_TIMEOUT` (120s), tapi `ZOOM_REMOTE_HOST_CONFIRM_TIMEOUT` juga mulai berjalan sejak request dikirim — kalau meeting dijadwalkan sangat dekat dengan waktu launch, ini bukan belt-and-suspenders worth pre-warming. Naikkan `ZOOM_REMOTE_HOST_CONFIRM_TIMEOUT` untuk meeting yang sangat pendek.
- **Ukuran image tidak turun** (±2 GB): berisi Chromium dan system deps-nya. Lazy start menghemat RAM, tidak menghemat disk.
- **Perilaku `start_url` di browser belum terverifikasi terhadap Zoom live** — carried over dari v2026.09.26d.

## [v2026.09.26d] - 2026-09-26 (Zoom Web host: pakai `start_url`)

### Changed
- **Browser host sekarang membuka `start_url`, bukan `join_url`** (`remote_browser/server.py`). `launch()` memilih `start_url` bila ada (`https://us05web.zoom.us/s/<id>?zak=<host key>` — link **host**), jatuh ke `join_url` (`/j/<id>?pwd=`) sebagai cadangan, dan menolak `400 no start_url or join_url in request` bila keduanya kosong. Handler `launch()` dan `ZoomBrowserHost.launch()`/_join() memakai nama `launch_url` karena sekarang keduanya. `bot/handlers.py` sudah mengirim keduanya sejak v2026.09.26c, jadi tidak ada perubahan di sisi bot.

  Alasan: docs resmi Zoom (`GET /v2/meetings/{meetingId}`) menyatakan `start_url` adalah link host sementara `join_url` adalah link peserta. Versi sebelumnya menyimpulkan `zak` tidak bisa dipakai di browser; entri ini sengaja membalikkan keputusan itu dan memindahkan `join_url` ke posisi cadangan.

### Added
- **`_is_zoom_link(url)`** (`remote_browser/server.py`): allowlist `https://` + hostname persis `zoom.us` atau berakhiran `.zoom.us`. Validator lama menolak apa pun yang bukan `/j/`, jadi harus dilepas agar `start_url` bisa lewat; tanpa pengganti, endpoint bertoken bearer bisa diarahkan ke situs mana pun dan memuat sesi Zoom yang sudah login di sana. Menolak juga suffix-jebakan `https://zoom.us.evil.com/`.
- **`test_zoom_link_allowlist`, `test_zak_start_url_accepted`, `test_non_zoom_url_rejected`, `test_missing_urls_rejected`** (`remote_browser/selfcheck.py`): menggantikan `test_zak_rejected` yang menguji perilaku lama. 9 kelompok assertion, semua lulus.

### Fixed
- **`_is_zoom_link` hilang setelah edit** (`remote_browser/server.py`): helper gagal terpasang, `AttributeError` saat self-check. `urlparse` juga belum di-import.
- **`bot/keyboards.py` kehilangan 3 fungsi**: `pending_user_owner_buttons`, `shortener_provider_buttons`, dan 19 baris lain terhapus — `import` di `bot/handlers.py` gagal. File dipulihkan dari HEAD.
- **`_render_launch_detail` + `_fmt_ts` hilang dari `bot/handlers.py`**: keduanya hilang saat file korup, tapi masih dirujuk `tests/host_confirmation_selfcheck.py` dan `bot/background_tasks.py`. Ditulis ulang, lalu disambungkan kembali ke `cb_control_zoom` — tanpa itu state `launch_requested`/`failed`/`started` tetap runtuh jadi satu baris "Remote" yang sama.
- **Import `LoadingContext` mati** (`bot/handlers.py`): `bot/utils/loading.py` dihapus tapi import-nya tertinggal, membuat modul gagal di-import sama sekali. Diapus.

### Known Issues (belum selesai)
- **Perilaku `start_url` di browser belum terverifikasi terhadap Zoom live.** Entri v2026.09.26c mencatat bukti sebaliknya (`us05web.zoom.us/s/<id>?zak=` → *"Join from Zoom Workplace app"* di browser mana pun, dengan `zoom.us` HTTP 200 dari container, jadi penolakan Zoom bukan masalah jaringan). Kalau gagal, gejalanya `join_timeout`, dan `join_url` yang dikirim sebagai cadangan perlu diaktifkan manual.
- **Selector DOM Zoom Web belum diuji ke halaman live** (`#foot-bar`, `.footer-button__text`, `button[class*='leave']`, `input#password`) — image tidak pernah ter-build karena Docker daemon mati.
- **Satu host satu meeting**: launch kedua dapat 409 sampai `BROWSER_STATE_TTL` (600s) habis. Batas desain, bukan bug.

## [v2026.09.26b] - 2026-09-26 (Remote Host: chase-the-join)

### Fixed
- **Passcode hilang dari deep link** (`remote/main.go`, `zoom/remote.py`, `bot/handlers.py`): start_url dari Zoom API berbentuk `https://us05web.zoom.us/s/<id>?zak=<JWT>` — **tidak pernah berisi `pwd`**. `deepLink()` hanya menyalin `pwd` bila ada di query string, jadi setiap launch mengirim `zoommtg://.../join?action=join&confno=...&zak=...` tanpa passcode, dan client berhenti di prompt passcode. Sekarang `launchRequest` menerima field `passcode` baru; `deepLink(startURL, fallbackPasscode)` memakainya hanya bila URL tidak punya `pwd` sendiri. Sisi bot meneruskan `meeting_details['password']` dari `prepare_remote_meeting()`. `RemoteZoomClient.launch_meeting()` mendapat parameter `passcode` opsional — pemanggil lama tidak perlu berubah. Terbukti di log: `zoommtg://zoom.us/join?action=join&confno=85895463055&pwd=bdY3n4&zak=REDACTED`.
- **Zombie process mengunci launch** (`remote/main.go`): `killZoomAndWait()` memakai `pgrep -x zoom`, dan `pgrep` menghitung **zombie** (state `Z`) sebagai proses hidup. Proses yang di-`SIGKILL` tapi tidak direap parent-nya menggantung selamanya di state `Z`, sehingga setelah launch pertama setiap launch berikutnya gagal dengan `could not free host: Zoom processes did not exit within 10s` → HTTP 500. Akar masalahnya `ZoomWebviewHost` di-`SIGKILL` sebelum parent-nya (`zoom`) mati, jadi tidak ada yang mereapnya. Diperbaiki dengan `liveProcess(name)`: `pgrep` → baca `/proc/<pid>/stat` → abaikan pid dengan field state `Z`. Loop kill kini memeriksa `zoom`, `ZoomLauncher`, **dan** `ZoomWebviewHost` (sebelumnya hanya dua yang pertama, sehingga webview yang tersisa tidak pernah dihitung).
- **CEF singleton lock di `cefcache/`** (`remote/main.go`): black VNC screen dengan proses `zoom` yang masih hidup berasal dari `ContentMainRun failed with exit code 21` — profil Chromium terkunci. Sumbernya **dua** lokasi, bukan satu: `data/cefIpcChannel/` (satu unix socket per webview) dan `data/cefcache/` (`SingletonCookie`, `SingletonLock`, `SingletonSocket`). Fungsi `clearCEFSockets()` hanya membersihkan yang pertama sehingga `exit code 21` tetap muncul. Diganti `clearCEFState(dir)` yang diterapkan ke keduanya dan hanya menghapus entri berawalan `Singleton*` agar CEF cache bawaan image tetap utuh. Verifikasi: `grep -c 'exit code 21' cef.log` → `0`, luma layar `YAVG=228` (sebelumnya 0/hitam).
- **`ZoomWebviewHost` dibungkus bash script** (`remote/Dockerfile`): Dockerfile lama me-rename binary ELF asli ke `ZoomWebviewHost.bin` lalu mengganti `ZoomWebviewHost` dengan wrapper bash yang meng-inject `--no-sandbox`. Akibatnya client mencatat `ZoomWebviewHost finally lanuch state is false` (typo dari Zoom sendiri) dan dialog join tidak pernah ter-render. Image `kasmweb/zoom:1.18.0` sudah menjalankan kontainer sebagai non-root sehingga sandbox tidak perlu di-bypass. Baris `mv` + `printf` dihapus; binary asli sekarang dibiarkan apa adanya.
- **`XDG_RUNTIME_DIR` kosong** (`remote/custom_startup.sh`, `docker-compose.yml`): Zoom menyimpan single-instance lock di `XDG_RUNTIME_DIR`; tanpa itu client mencatat `QStandardPaths: XDG_RUNTIME_DIR not set, defaulting to '/tmp/runtime-kasm-user'` dan hand-off deep link antar instance `ZoomLauncher` tidak pernah selesai. Script startup kini `export` + `mkdir -p` + `chmod 700`, dan `docker-compose.yml` meng-set env yang sama supaya launcher yang di-spawn controller mewarisi path yang identik.
- **Launch loop "already-running"** (`remote/main.go`): `pkill -9` disusul `cmd.Start()` tanpa menunggu, sehingga instance baru berlomba dengan instance lama yang belum mati dan keluar dengan `Exit zoom as another zoom instance is running!` — 14 siklus, nol join. `killZoomAndWait()` kini mengirim sinyal lalu **poll** sampai benar-benar tidak ada proses hidup.
- **`state` tidak pernah maju** (`remote/main.go`): status `opened` tidak pernah di-clear oleh apa pun, jadi conflict check memblokir meeting berikutnya selamanya dengan 409 `another meeting is assigned to this host` sampai ada yang menekan restart manual. Ditambah `stateTTL = 10 * time.Minute`.
- **Bocornya host key ke log** (`remote/main.go`): `zak` berukuran 438 karakter dan memberi kendali penuh atas meeting. Ditambah `redactLink()` (mengganti `zak` jadi `REDACTED`) dan `hostJoinMode()` sehingga log berbunyi "host (zak present)" alih-alih URL mentah.
- **Loop `https://` lewat Firefox** (`remote/main.go`): `xdg-open` me-rutekan start_url ke Firefox (padahal tidak ada binary firefox), lalu halaman harus mengembalikan deep link `zoommtg://` ke Zoom — bolak-balik itu titik join-nya hilang. Controller sekarang memanggil `/opt/zoom/ZoomLauncher --no-sandbox <deep-link>` secara langsung.
- **`handlers.py` menelan alasan gagal** (`bot/handlers.py`): `except` pada `cb_start_zoom_meeting` menyimpan `type(e).__name__` saja, jadi `TokenError` tidak bisa dibedakan dari Zoom 403. Sekarang menyimpan `f"{type}: {e}"` terpotong 200 karakter dan menampilkannya ke user.

### Added
- **`remote/main_test.go`**: test Go untuk logika yangDiam-diam rusak. `TestDeepLinkCarriesPasscodeFallback` (fallback passcode dari 3 sisi: `pwd` di URL, fallback, atau keduanya absen), `TestDeepLinkRejectsURLWithoutConferenceNumber`, `TestRedactLinkHidesHostKey` (guard anti-bocor host key), `TestHostJoinMode`, plus guard untuk `liveProcess`. Semua lulus `go vet` bersih.
- **`scripts/read_container_logs.py`**: pembaca log container (compose & single container) dengan ringkasan error yang dikelompokkan. `extract_error()` menormalkan timestamp prefix dan hex token supaya 148 pengulangan `bridge->relay: timeout` kolaps jadi satu baris, bukan 148 "jenis" berbeda.
- **`scripts/check_zoom_login.py`**: pemeriksa status login Zoom read-only lewat ukuran profile DB (`zoomus.enc.v2.db` > 100 KB = signed in) plus daftar proses. Dipakai untuk memverifikasi login VNC_User benar-benar persist ke volume.
- **`tests/test_remote_host_join.py`** + **`tests/_bot_host_launcher.py`**: test end-to-end yang menjalankan alur Telegram penuh (create meeting → list → control screen → "Start on Remote Zoom") lalu mem-poll konfirmasi host. `_bot_host_launcher.py` ada karena `config/config.py` memanggil `load_dotenv(override=True)` di level import — env var dari test **selalu ditimpa** oleh `.env`, jadi test patch `settings.zoom_remote_base_url` setelah import.
- **`tests/host_join_e2e_check.py`**, **`tests/host_confirmation_selfcheck.py`**, **`tests/check_dependencies_selfcheck.py`**: pemeriksaan mandiri untuk logika gabungan advisory dan filter query launch.

### Verification
`go vet` bersih, `go test ./...` → `ok zoomremote 0.015s`. Controller merespons `/health` 200 dengan `zoom_running: true`, 401 tanpa token. Launch diterima berulang: `{"accepted":true,"meeting_id":"85895463055","state":"opened"}`. Loop `already-running` beku di 14 (tidak bertambah). Login Zoom persist lintas restart container (volume-backed).

### Known Issues (belum selesai)
- **Host belum benar-benar join.** Meeting tetap `status = waiting` di API setelah semua perbaikan di atas. Desktop client menerima deep link (`cmd line: --no-sandbox zoommtg://...?pwd=...&zak=...` muncul di `zoom_stdout_stderr.log`) tapi tidak pernah menyelesaikan join tanpa interaksi. Dugaan penyebab: `llvmpipe` software rendering (container tanpa GPU) + `Qt Quick Layouts: Detected recursive rearrange`.
- **Chrome web client bukan fallback.** Host link `zak` bersifat desktop-only: dibuka di browser mana pun (`us05web.zoom.us/s/<id>?zak=`, `us05web.zoom.us/j/<id>?pwd=&zak=`, `zoom.us/s/<id>`) Zoom mengembalikan halaman *"Join from Zoom Workplace app"*. `zoom.us` terjangkau dari container (HTTP 200) sehingga ini penolakan Zoom, bukan masalah jaringan.
- **Tooling screenshot tidak konsisten.** `ffmpeg -x11grab` melaporkan desktop abu-abu datar, sementara `xwd` pada root window melaporkan 134 warna berbeda. Keduanya tidak bisa dipercaya sendiri; jangan menyimpulkan "layar hitam" dari `ffmpeg` saja.
- **`pkill -f zoom` di dalam container mematikan controller**, karena `zoom-remote-controller` mengandung "zoom". Kode Go sengaja memakai `pkill -x` dan `pkill -f '*.bin'`, jadi aman — tapi perintah ad-hoc di container adalah jebakan.

## [v2026.09.26c] - 2026-09-26 (Zoom Web host, headless Playwright)

### Changed
- **Backend host remote diganti ke `zoom-browser` (default).** Zoom Desktop di container Kasm dinyatakan gagal: container tanpa GPU memakai software rendering `llvmpipe`, dialog join tidak pernah selesai di-render, dan client menerima deep link tapi tidak pernah join. Bukti: `cmd line: --no-sandbox zoommtg://...?pwd=...&zak=...` muncul di log, `status` tetap `waiting`. Host key `zak` juga terbukti desktop-only — dibuka di browser apa pun (`us05web.zoom.us/s/<id>?zak=`, `zoom.us/s/<id>`) Zoom mengembalikan *"Join from Zoom Workplace app"*; `zoom.us` HTTP 200 dari container, jadi ini penolakan Zoom bukan masalah jaringan. `remote/` dan `zoom-remote` **tidak dihapus** — dipindah ke compose profile `kasm`, rollback cukup `docker compose --profile kasm up -d`.

### Added
- **`remote_browser/server.py`**: host headless Chromium + Playwright yang menjalankan Zoom Web. Kontrak HTTP-nya sengaja meniru `remote/main.go` persis (`GET /health`, `GET /status`, `POST /meetings/{id}/launch`, `POST /meetings/{id}/stop`, `POST /zoom/restart`, Bearer token, `/health` tanpa auth) sehingga pindah backend cuma mengubah `ZOOM_REMOTE_BASE_URL` — `zoom/remote.py`, handler bot, tabel DB, dan poller konfirmasi tidak perlu disentuh. Clerk: `liveProcess`/zombie, CEF singleton lock, dan `XDG_RUNTIME_DIR` yang menyumbang banyak bug di jalur Kasm **tidak ada** di sini karena tidak ada proses Zoom native dan tidak ada profil Chromium yang perlu di-unlock.
- **`remote_browser/selfcheck.py`**: 6 kelompok assertion tanpa Chromium dan tanpa jaringan — parsing path, klasifikasi alasan gagal, deteksi sudah-join, exclusivity host + TTL, penolakan `zak` 400, dan batas auth.Menutup logika yang hanya bisa gagal melawan Zoom sungguhan.
- **`scripts/zoom_web_login.py`**: login Zoom Web sekali jalan di PC operator, menghasilkan `zoom_web_session.json` (Playwright `storage_state`) untuk disalin ke volume. Dipakai `storage_state`, bukan email/password, karena akun biasanya di balik MFA/SSO yang tidak bisa diotomatiskan — persis trade-off yang sama dengan login sekali lewat VNC di Kasm, tapi tanpa perlu passthrough noVNC.
- **`remote_browser/Dockerfile`**: image `mcr.microsoft.com/playwright/python:v1.63.0-noble`, non-root `pwuser`, healthcheck lewat stdlib `urllib`, volume state `/data`.
- **`zoom_browser_state` volume** + service `zoom-browser` di compose dengan `depends_on` yang sama seperti sebelumnya.
- **`playwright==1.63.0`** di `requirements-dev.txt`, di-pin sama dengan tag image agar tidak meleset. Hanya dipakai script login dan container host — image bot tidak mengimpornya.

### Fixed
- **Classification of Zoom Web failure** (`remote_browser/server.py`): ini bukan tebakan. Klaim "sudah join" dibuat dari hilangnya dialog + hadirnya toolbar in-meeting; sisanya dipetakan ke alasan spesifik (`bad_passcode`, `waiting_room_not_admitted`, `session_expired`, `meeting_id_invalid`, `join_timeout`) yang tersimpan di `last_remote_error` dan tampil di tombol "Cek Status". Vokal Zoom berbeda antar locale, jadi pencocokan memakai fragmen pendek dan urut dari paling spesifik — passcode dicek lebih dulu karena "sign in to join" ikut muncul di halaman passcode.
- **`status` kini melaporkan `session_ready` hasil cek langsung** (`remote_browser/server.py`): sebelumnya hanya `os.path.exists(SESSION_FILE)`, yang terlihat "siap" padahal cookie-nya sudah expired di sisi Zoom.
- **Dead `try/except`** di `_new_context()` yang membungkus `os.path.exists` — tidak mungkin melempar.

### Changed (contract)
- **`zoom/remote.py` `launch_meeting()`** dapat parameter opsional `join_url`. `start_url` (berisi `zak`) hanya berguna bagi Zoom Desktop; `join_url` (publik `https://zoom.us/j/<id>?pwd=`) yang bisa dipakai browser. Keduanya dikirim supaya satu panggilan melayani dua backend. Parameter baru opsional → pemanggil lama tidak berubah.
- **`bot/handlers.py` `cb_start_zoom_meeting`** mengambil `join_url` dari `meeting_details` dan meneruskannya; guard berubah dari `if start_url:` menjadi `if start_url or join_url:`, dan teks kegagalan menyebut keduanya.

### Verification
`remote_browser/selfcheck.py` → 6 kelompok assertion lulus. `host_confirmation_selfcheck.py` dan `check_dependencies_selfcheck.py` tetap lulus. `go test ./...` di `remote/` tetap `ok`. `docker compose config -q` → exit 0, service default `zoom-browser` + `zoom-telebot`, `zoom-remote` hanya muncul dengan `--profile kasm`. `pip-audit -r requirements.txt` → `No known vulnerabilities found`. `git check-ignore` mengonfirmasi `zoom_web_session.json` diabaikan.

### Known Issues
- **Image belum ter-build dan host belum diuji melawan Zoom sungguhan.** Docker daemon sedang mati saat perubahan ini dibuat (`_ping` 500). Routing, auth, guard, dan klasifikasi sudah teruji; yang belum teruji adalah selector DOM Zoom Web (`#foot-bar`, `.footer-button__text`, `button[class*='leave']`, `input#password`) terhadap halaman live. Kalau Zoom mengubah markup, `_in_meeting` akan salah menilai dan launch berakhir `join_timeout` — bukan diam-diam sukses. Verifikasi pertama setelah daemon hidup: `docker compose build zoom-browser && docker compose up -d zoom-browser`, lalu `curl /status` untuk memastikan `session_ready: true`.
- **Host masuk sebagai peserta, bukan host asli.** Browser ini tidak bisa memakai `zak`. Kalau `ZOOM_WAITING_ROOM=true`, Zoom tidak meng-admit dia otomatis → `waiting_room_not_admitted`. Untuk host yang di-automate, set `ZOOM_WAITING_ROOM=false`. Konsekuensi: orang pertama yang masuk ke `join_url` menjadi host. Kalau meeting butuh host tertentu, ini belum terpenuhi.
- **Satu host = satu meeting.** `_held_by` diserialisasi dengan `asyncio.Lock`; launch kedua dapat 409 sampai `BROWSER_STATE_TTL` habis. Ini batas desain, bukan bug — satu browser, satu sesi login.
- **Login manual sekali masih wajib**, persis seperti Kasm. Bedanya hanya file yang disalin (`zoom_web_session.json`) dan tidak perlu noVNC.

## [v2026.09.26] - 2026-09-26

### Added
- **Host Confirmation Poller** (`bot/background_tasks.py`): background task `_host_confirmation_watch` yang mem-poll `GET /v2/meetings/{id}` tiap 10 detik untuk meeting berstatus `launch_requested`, lalu menandai `started` saat Zoom mengonfirmasi, atau `failed` bila lewat `ZOOM_REMOTE_HOST_CONFIRM_TIMEOUT` (default 300 detik). Ini menutup gap yang belum terisi: sebelumnya `live_status` hanya bisa maju lewat Zoom webhook, sehingga tanpa webhook bot tidak pernah bisa memastikan host benar-benar join. Poll error bersifat transien dan tidak membatalkan launch — timeout di DB yang akhirnya menyerah.
- **`db.list_meetings_pending_launch()`**: query `live_status = 'launch_requested'` dengan `detect_types=PARSE_DECLTYPES` supaya `launch_requested_at` kembali sebagai `datetime`, bukan string. Tanpa ini `_as_naive()` akan melempar `AttributeError` dan pengecekan timeout diam-diam dilewati.
- **`db.mark_remote_launch_failed()`**: transisi ke `failed` + `last_remote_error`, di-guard `WHERE live_status = 'launch_requested'` supaya kegagalan yang datang terlambat tidak menimpa meeting yang sudah `started` (balapan dengan webhook).
- **Diagnostik di tombol "Cek Status"** (`bot/handlers.py`): `cb_control_zoom` kini memanggil `get_remote_launch_state()` dan merender lewat `_render_launch_detail()`. Sebelumnya `get_meeting_live_status()` meratakan `launch_requested` dan `failed` menjadi string yang tidak bisa dibedakan dari `not_started`, sehingga launch gagal tampak sama dengan launch yang tidak pernah dicoba. Sekarang tampil alasan kegagalan, siapa yang meminta, dan kapan.
- **`tests/host_confirmation_selfcheck.py`**: 9 assertion group — filter query hanya mengembalikan row `launch_requested`, `launch_requested_at` bertipe `datetime`, guard `mark_remote_launch_failed` tidak menimpa `started`, dan `last_remote_error` ter-escape HTML (nilainya berisi teks exception mentah).
- **Dokumentasi remote host di `Readme.md`**: section baru `🖥️ Remote Host (Host-join Otomatis)` berisi prerequisites, env wajib vs opsional, langkah login Zoom di container Kasm sekali saja, penjelasan dua jalur konfirmasi, dan tabel troubleshooting. Section `🤝 Contributing` dan file `LICENSE` (MIT) ditambahkan — `Readme.md` sebelumnya sudah merujuk `LICENSE` yang tidak pernah ada.
- **`from settings import settings` diperbaiki** → `from config import settings` di `bot/background_tasks.py`. Modul `settings` tidak pernah ada; import ini dibuat salah saat penambahan task dan membuat modul gagal di-import.

### Fixed
- **Penyebab kegagalan launch dibuang** (`bot/handlers.py`): `except` pada `cb_start_zoom_meeting` hanya menyimpan `type(e).__name__`, sehingga `TokenError` (token salah) tidak bisa dibedakan dari Zoom 403. Sekarang menyimpan `f"{type}: {e}"` yang dipotong 200 karakter, dan menampilkan alasan itu ke user.
- **Komentar schema tidak akurat** (`db/schema.sql`): `live_status` terdokumentasi hanya sebagai `not_started, started, ended`, padahal kode juga menulis `launch_requested` dan `failed`.
- **Test Collection Crash**: `tests/test_bot_integration.py` dan `tests/test_meeting_details_controls.py` memanggil `sys.exit(1)` saat `telethon` belum terinstall. Saat collection, `SystemExit` memicu `INTERNALERROR` pada pytest yang membatalkan **seluruh** test run, bukan hanya suite terkait. Diganti menjadi `pytest.skip(..., allow_module_level=True)`.
- **Integration Test Race Condition**: `test_bot_integration.py` menunggu 5 detik tetap sebelum mengirim `/start`. `on_startup()` di `bot/main.py` memblokir polling awal dengan `await sync_meetings_from_zoom()`, sehingga pada mesin lambat perintah pertama tiba sebelum dispatcher aktif dan tidak pernah dijawab (`TimeoutError` — last text `'/start'`). Test kini mem-poll file log sampai marker `Run polling for bot` muncul, dengan batas waktu 45 detik dan pesan diagnostik yang menyertakan log tail.

### Changed
- `pytest_output.txt` dan `pytest_output_2.txt` di-untrack dari git dan ditambahkan ke `.gitignore` (bersama `logs/`, `latest_logs/`, `archived_logs/`). File ini adalah artefak hasil run yang membocorkan path absolut mesin lokal (`C:\Users\rezy0\OneDrive - ...`).
- **Test Suite entering version control**: `.gitignore` punya pola `test_*.py` yang ikut mencocoki `tests/*.py`, dan entri `!tests/` hanya membuka exception untuk direktori — bukan file di dalamnya. Akibatnya kedua suite integrasi (~42 KB) tidak pernah ter-commit, dan job `run-tests` di CI berjalan tanpa file test sama sekali. Pola diperbaiki menjadi `/test_*.py` (hanya root) plus `!tests/test_*.py`.
- **CI `run-tests`**: memasang `requirements-dev.txt` (bukan `requirements.txt`) agar `telethon` tersedia, ditambah step `Verify Test Collection` agar kegagalan import di level modul menjadi build merah, bukan diam-diam lolos.
- **Dependency Upgrade**: `aiogram` 3.29.0 → 3.31.0, `aiohttp` 3.14.1 → 3.14.3, `python-dotenv` 1.2.2 → 1.2.3, `pytz` 2026.2 → 2026.4. `aiosqlite`, `pytest`, `pytest-asyncio`, `watchdog`, dan `pip-audit` sudah di versi terbaru sehingga tidak berubah. Breaking change aiogram 3.30.0 (penghapusan parameter `receiver_user_id` pada shortcut `reply_*`) diverifikasi tidak terpakai di codebase ini. `pip-audit` melaporkan `No known vulnerabilities found`; test suite lulus `2 passed`. `telethon` di-pin dari `>=1.35.0` menjadi `==1.45.0` agar build Docker dan CI reproducible.
- **Dead Code Removal**: Pembersihan simbol yang tidak pernah dipanggil, hasil scan AST menyeluruh (35 file `.py`). Total **271 baris terhapus**:
  - `bot/utils/loading.py` (120 baris) — dihapus seluruhnya. `LoadingContext` hanya di-import di `bot/handlers.py` dan `bot/cloud_recording_handlers.py` tetapi tidak pernah diinstansiasi; ketiga handler loading message memakai `msg.reply()` langsung. Folder `bot/utils/` kini kosong.
  - `zoom/zoom.py` (98 baris) — 4 method `ZoomClient` tanpa pemanggil: `fetch_token_info` (debug-only), `get_short_url` (wrapper satu baris yang superseded akses `meeting.get("join_url")` langsung), `get_meeting_participants` dan `get_live_meeting_details` (superseded `sync_meeting_live_status_from_zoom`). Import `List` ikut dibuang.
  - `bot/keyboards.py` (31 baris) — `pending_user_owner_buttons` menghasilkan callback `ban_toggle:<id>` yang tidak punya handler di router mana pun, sehingga tombolnya mati; `shortener_provider_buttons` (menghasilkan `shorten_provider:<token>:<id>`) digantikan `shortener_provider_selection_buttons` (`select_provider:<id>`) yang memang dipakai di 3 tempat.
  - `db/db.py` (7 baris) — `update_agent_last_seen`; tabel `agents` dibaca saja oleh bot (perintah `/agents`), kolom `last_seen` tetap dipertahankan di `schema.sql` karena Zoom remote agent adalah penulis yang dimaksud.
  - `scripts/migrate_shorteners.py` (11 baris) — `get_config_version`, wrapper yang menduplikasi pembacaan `config.get("version")` inline di `preview_changes()`.
  - Import tidak terpakai: `Document` dan 2 keyboard factory di `bot/handlers.py`, `LoadingContext` di `bot/cloud_recording_handlers.py`, serta duplikasi `import logging` ganda di `bot/cloud_recording_handlers.py`.
- **Dependency Audit Alert** (`scripts/check_dependencies.py`): ID advisory yang sama muncul berkali-kali untuk satu paket karena setiap salinannya membawa `fix_versions` berbeda, sehingga alert menampilkan `PYSEC-2026-3547, PYSEC-2026-3546, PYSEC-2026-3545, PYSEC-2026-3545, PYSEC-2026-3546, PYSEC-2026-3547` beserta enam daftar fix yang nyaris identik — terbaca sebagai enam masalah berbeda padahal hanya tiga. Sekarang digabung per ID dan diambil versi fix tertinggi, dengan advisory tanpa fix ditampilkan sebagai `no fix`. Helper `_version_sort_key()` menambahkannya: perbandingan string biasa menempatkan `2026.10` di bawah `2026.9`, sehingga `max()` pernah memilih versi fix yang keliru.
- **Image Container**: `docker/Dockerfile` meng-upgrade `pip` ke `26.1.2` yang terkena `PYSEC-2026-3721` (fix `26.2`), dan `setuptools` bawaan `python:3.11-slim` di `82.0.1` terkena `PYSEC-2026-3447` (fix `83.0.0`). Keduanya sekarang di-pin eksplisit ke `pip==26.2.1` dan `setuptools==84.0.0` di stage `production-deps`, sebelum `requirements.txt` dipasang. Keduanya mendukung Python `>=3.10` sehingga aman untuk image 3.11.

### Verification
Scan ulang setelah pembersihan menyisakan 6-item yang seluruhnya false positive terverifikasi: `from __future__ import annotations` (2 file, direktif compiler), method `get_state`/`del_state`/`del_data` pada `DatabaseFSMStorage` (kontrak abstrak `aiogram.fsm.storage.base.BaseStorage`, dipanggil aiogram), dan `AutoRestartHandler.on_any_event` (override `watchdog.FileSystemEventHandler`, dipanggil internal). Regression test lulus `2 passed in 50.79s`.

`tests/check_dependencies_selfcheck.py` ditambahkan sebagai pemeriksaan mandiri untuk logika gabungan advisory, mencakup kasus duplikat yang persis muncul di alert container serta pengurutan versi numerik. `pip-audit -r requirements.txt` → `No known vulnerabilities found`; regression test ulang lulus `2 passed in 52.62s`.

## [v2026.07.17] - 2026-07-17

### Added
- **Zoom Remote Port Mapping**: Port 8080 remote agent dipetakan ke host machine di `docker-compose.yml` untuk verifikasi API langsung via `curl` dan pengembangan lokal.
- **Telegram Bot Integration Testing**: `tests/test_bot_integration.py` — suite integrasi end-to-end berbasis Telethon dengan auto-whitelisting via DB, manajemen subprocess bot (deteksi konflik token), dan pengujian UI (inline button, prompt FSM, create/delete Zoom).
- **Zoom Controls & Details Testing**: `tests/test_meeting_details_controls.py` — suite verifikasi untuk layar Zoom Control dan Meeting Details. Menyelesaikan masalah cache pesan Telethon dan constraint HTML Telegram (unescaped `'&'`, localhost URL).

### Fixed
- **Remote Agent**: Resolve crash sandbox CEF Zoom dan deadlock state welcome screen di dalam container (`remote/main.go`, `remote/Dockerfile`).
- **Dependencies**: Menambahkan `requirements-dev.txt` untuk dependensi pengembangan.

## [v2026.06.24] - 2026-06-24

### Added
- **Zoom Security Update**: Merespons kebijakan Zoom terbaru yang mewajibkan Passcode atau Waiting Room, bot sekarang mengekstrak dan menampilkan Passcode secara eksplisit pada balasan ke pengguna ketika meeting berhasil dibuat.
- Ditambahkan pengabaian folder `graphify-out/` dan file `run_graphify.py` pada `.gitignore`.

### Changed
- Pembaruan struktur output dokumentasi `README.md` terkait kebijakan Passcode.

### Fixed
- Memperbaiki parsing JSON `pip-audit` pada `scripts/check_dependencies.py` yang sebelumnya mengalami `AttributeError` akibat perbedaan format respons antar versi `pip-audit`.
- **Security Update**: Memperbarui versi dependency `pytz`, `pytest`, `pytest-asyncio`, dan `pip-audit` serta *core packages* di Dockerfile untuk mengatasi peringatan kerentanan keamanan (*vulnerabilities*).
