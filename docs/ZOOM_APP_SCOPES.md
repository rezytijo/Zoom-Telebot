# Zoom Marketplace App - Required Scopes & Permissions

## 📋 Ringkasan Analisa

Berdasarkan fungsi bot ini, berikut adalah daftar lengkap **Zoom OAuth Scopes** yang diperlukan saat membuat **Server-to-Server OAuth App** di Zoom Marketplace.

---

## 🔐 Required Scopes (Wajib)

### 1. **Meeting Management** ✅

| Scope | Deskripsi | Digunakan Di |
|-------|-----------|--------------|
| `meeting:read:admin` | Read all user meetings | `get_meeting()`, `list_upcoming_meetings()` |
| `meeting:write:admin` | Create, update, delete meetings | `create_meeting()`, `update_meeting()`, `delete_meeting()` |
| `meeting:read:meeting_summary:admin` | Read meeting details & settings | `get_meeting()` |

**Fungsi Bot Yang Menggunakan:**
- ✅ `/meet` - Create new meeting
- ✅ `/list` - List all meetings
- ✅ `Edit Meeting` - Update topic/time
- ✅ `Delete Meeting` - Delete meeting
- ✅ `Meeting Details` - View meeting info

---

### 2. **Live Meeting Control** ✅

| Scope | Deskripsi | Digunakan Di |
|-------|-----------|--------------|
| `meeting:update:admin` | Update meeting status (start/end) | `start_meeting()`, `end_meeting()` |
| `meeting:update:meeting_status:admin` | Control meeting status | `end_meeting()` via `/meetings/{id}/status` |

**Fungsi Bot Yang Menggunakan:**
- ✅ `⏹️ End Meeting` button
- ✅ `▶️ Start Meeting` button (manual control)

---

### 3. **Recording Management** ✅

| Scope | Deskripsi | Digunakan Di |
|-------|-----------|--------------|
| `recording:read:admin` | Read cloud recording metadata | `get_meeting_recording_status()`, `get_cloud_recording_urls()` |
| `recording:write:admin` | Start/stop/pause/resume recording | `control_live_meeting_recording()` |

**Fungsi Bot Yang Menggunakan:**
- ✅ `🔴 Start Recording` button
- ✅ `⏹️ Stop Recording` button
- ✅ `⏸️ Pause Recording` button
- ✅ `▶️ Resume Recording` button
- ✅ `☁️ Cloud Recordings` menu
- ✅ Auto-sync cloud recording data (background task)

---

### 4. **Participant Management** ✅

| Scope | Deskripsi | Digunakan Di |
|-------|-----------|--------------|
| `meeting:read:participant:admin` | View meeting participants | `get_meeting_participants()` |
| `meeting:write:participant:admin` | Mute/unmute participants | `mute_all_participants()` |

**Fungsi Bot Yang Menggunakan:**
- ✅ `🔇 Mute All Participants` button
- ✅ View participant count in meeting control UI

---

### 5. **User Information** ✅

| Scope | Deskripsi | Digunakan Di |
|-------|-----------|--------------|
| `user:read:admin` | Read user profile | `create_meeting(user_id="me")`, `list_upcoming_meetings()` |

**Fungsi Bot Yang Menggunakan:**
- ✅ Create meetings on behalf of authenticated user
- ✅ List meetings for specific user

---

## 🎯 Recommended Scopes (Opsional Tapi Berguna)

### 6. **Metrics & Analytics** 🔔

| Scope | Deskripsi | Use Case |
|-------|-----------|----------|
| `dashboard_meetings:read:admin` | Read meeting metrics | Future feature: Meeting analytics |
| `report:read:admin` | Access meeting reports | Future feature: Usage statistics |

**Catatan:** Belum digunakan di bot saat ini, tapi berguna untuk fitur monitoring dan reporting di masa depan.

---

## 📝 Konfigurasi Zoom Marketplace App

### Step-by-Step Setup:

#### 1. **Buat Server-to-Server OAuth App**
   - Login ke [Zoom Marketplace](https://marketplace.zoom.us/)
   - Klik **Develop** → **Build App**
   - Pilih **Server-to-Server OAuth**
   - Isi informasi aplikasi:
     - **App Name:** Zoom Telebot SOC
     - **Short Description:** Telegram bot for Zoom meeting management and recording control
     - **Company Name:** (Nama organisasi Anda)

#### 2. **App Credentials** (akan digunakan di `.env`)
   ```
   ZOOM_ACCOUNT_ID=<account_id>
   ZOOM_CLIENT_ID=<client_id>
   ZOOM_CLIENT_SECRET=<client_secret>
   ```

#### 3. **Add Scopes** (di tab **Scopes**)
   
   Centang semua scopes berikut:

   **Meeting Scopes:**
   - ✅ `meeting:read:admin`
   - ✅ `meeting:write:admin`
   - ✅ `meeting:update:admin`
   - ✅ `meeting:read:meeting_summary:admin`
   - ✅ `meeting:update:meeting_status:admin`

   **Recording Scopes:**
   - ✅ `recording:read:admin`
   - ✅ `recording:write:admin`

   **Participant Scopes:**
   - ✅ `meeting:read:participant:admin`
   - ✅ `meeting:write:participant:admin`

   **User Scopes:**
   - ✅ `user:read:admin`

#### 4. **Activation**
   - Setelah semua scopes ditambahkan, klik **Continue**
   - **Activate** aplikasi
   - Copy **Account ID**, **Client ID**, **Client Secret** ke file `.env`

---

## 🚨 Troubleshooting Permissions

### Error: `Invalid access token`
**Penyebab:** Token tidak memiliki scope yang diperlukan atau expired.

**Solusi:**
```bash
# Cek scopes di token saat ini
python -c "from zoom import zoom_client; import asyncio; asyncio.run(zoom_client.fetch_token_info())"
```

### Error: `User does not have permission`
**Penyebab:** Account role tidak mendukung admin-level scopes.

**Solusi:**
- Pastikan akun Zoom Anda adalah **Owner** atau **Admin**
- Atau gunakan scopes level **user** bukan **admin** (jika hanya perlu kontrol meeting sendiri)

### Error: `Meeting not found`
**Penyebab:** Scope `meeting:read:admin` tidak aktif atau meeting ID salah.

**Solusi:**
- Verifikasi scope `meeting:read:admin` di Zoom Marketplace App
- Re-activate app setelah menambahkan scope

---

## 📊 Mapping Fitur Bot → Scopes

| Fitur Bot | Zoom API Endpoint | Required Scope |
|-----------|-------------------|----------------|
| Create Meeting | `POST /v2/users/{userId}/meetings` | `meeting:write:admin` |
| List Meetings | `GET /v2/users/{userId}/meetings` | `meeting:read:admin` |
| Delete Meeting | `DELETE /v2/meetings/{meetingId}` | `meeting:write:admin` |
| Update Meeting | `PATCH /v2/meetings/{meetingId}` | `meeting:write:admin` |
| End Meeting | `PUT /v2/meetings/{meetingId}/status` | `meeting:update:meeting_status:admin` |
| Start Recording | `PATCH /v2/live_meetings/{meetingId}/events` | `recording:write:admin` |
| Stop Recording | `PATCH /v2/live_meetings/{meetingId}/events` | `recording:write:admin` |
| Cloud Recordings | `GET /v2/meetings/{meetingId}/recordings` | `recording:read:admin` |
| Mute All | `PUT /v2/meetings/{meetingId}/participants/status` | `meeting:write:participant:admin` |
| View Participants | `GET /v2/meetings/{meetingId}?type=live` | `meeting:read:participant:admin` |

---

## ✅ Checklist Verifikasi

Sebelum production, pastikan:

- [ ] Semua 11 scopes wajib sudah ditambahkan di Zoom App
- [ ] App sudah di-**Activate** di Zoom Marketplace
- [ ] `.env` berisi `ZOOM_ACCOUNT_ID`, `ZOOM_CLIENT_ID`, `ZOOM_CLIENT_SECRET` yang benar
- [ ] Test create meeting: `/meet Test Meeting`
- [ ] Test recording control: Buat meeting → Start → Recording control buttons
- [ ] Test cloud recordings: Setelah meeting selesai, cek `☁️ Cloud Recordings`
- [ ] Log tidak menunjukkan error `403 Forbidden` atau `User does not have permission`

---

## 🔗 Referensi

- [Zoom API Documentation](https://developers.zoom.us/docs/api/)
- [OAuth Scopes Reference](https://developers.zoom.us/docs/integrations/oauth-scopes/)
- [Server-to-Server OAuth Guide](https://developers.zoom.us/docs/internal-apps/s2s-oauth/)

---

**Created:** 2025-12-31  
**Version:** 1.0  
**Bot Version:** v2025.12.31.18
