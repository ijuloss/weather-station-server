# Dokumentasi Sistem Weather Station Server

Dokumen ini menjelaskan arsitektur menyeluruh Weather Station Server: backend, frontend, dan komponen AI/Machine Learning. Juga daftar library inti beserta fungsinya.

## 1. Gambaran Arsitektur

```
┌──────────────┐   HTTPS/HTTP     ┌───────────────────┐
│  ESP32       │ ───────────────▶ │  Nginx :9999     │
│  (Firmware)  │                  │  (Reverse Proxy)  │
└──────────────┘                  └─────────┬─────────┘
    │   ▲                                   │ proxy_pass
    │   │ Socket.IO push (opsional)         ▼
    │   │                          ┌───────────────────┐
    │   │                          │  Flask :1111      │
    │   │                          │  + Socket.IO      │
    │   │                          │  + WeatherAIModel │
    │   │                          └─────────┬─────────┘
    │   │                                    │
    │   │                          ┌─────────┴─────────┐
    │   │                          │   Penyimpanan     │
    │   │                          │ data/ (JSON, PKL) │
    │   │                          │ logs/ (rotasi)    │
    │   └──── Socket.IO ──────────┐│ Firebase (REST)   │
    │                             ▼└───────────────────┘
    │                      ┌───────────────────┐
    └────── OLED/Serial──▶ │  Dashboard Web    │
                           │  (index.html)     │
                           │  Chart.js, JS     │
                           └───────────────────┘
```

Tiga aktor utama:

1. **ESP32** — mengumpulkan data sensor (suhu, kelembapan, kualitas udara, cahaya, GPS, daya) lalu POST ke `/api/sensor-data` dan polling `/api/devices/<id>/commands`.
2. **Backend Flask + Socket.IO** — menerima data, menyimpan lokal + opsional mirror ke Firebase REST, melatih & melayani prediksi AI, mem-broadcast realtime ke dashboard.
3. **Dashboard Web** — halaman statis (`frontend/index.html`) yang disajikan Nginx, terhubung ke backend via Socket.IO dan REST.

---

## 2. Backend — `backend/app.py`

File tunggal ~3.500 baris yang menggabungkan seluruh logika server. Bagian utama:

### 2.1 Bootstrapping & Config
- **`config.get(...)`** membaca urutan prioritas: (1) `config/server.conf`, (2) `/etc/weather-station/server.conf`, (3) environment `.env`. ENV selalu menang.
- **`setup_logging()`** mengatur `RotatingFileHandler` (5 MB × 5 backup) + stdout.
- **`create_directories()`** memastikan `data/`, `logs/`, `run/` ada dan writable.
- **CORS & Socket.IO** — membaca `ALLOWED_ORIGINS` (koma-dipisah) dari env. Default `*` untuk dev.

### 2.2 Endpoint REST Utama

| Method | Path | Fungsi |
|---|---|---|
| GET | `/api/health` | Liveness probe (untuk Docker/K8s) |
| GET | `/api/status` | Status keseluruhan: server, Firebase, ESP32, last_update |
| GET | `/api/config` | Config publik untuk dashboard |
| GET/POST | `/api/client-settings` | Ambil/simpan setting UI (interval poll, offline threshold) |
| POST | `/api/sensor-data` | **Endpoint utama** ESP32 kirim reading → trigger broadcast realtime |
| GET | `/api/dashboard-stats` | Statistik agregat (avg, min, max) untuk kartu dashboard |
| GET | `/api/historical-data` | Riwayat sensor (limit, sumber Firebase/lokal) |
| GET | `/api/export-data` | Export CSV/JSON rentang tanggal |
| GET | `/api/predictions` | Daftar prediksi AI terakhir |
| GET | `/api/ai/status` | Status model: `data_count`, `distribution`, `evaluation_mode`, `model_checksum` |
| POST | `/api/train-model` | Trigger training manual |
| POST/GET | `/api/ai/seed-demo` | Seed data sintetis untuk demo (bila belum cukup data nyata) |
| GET | `/api/test-firebase` | Uji koneksi Firebase REST |
| GET | `/api/firebase/status` | Status saat ini Firebase |
| POST | `/api/firebase/connect` | Nyalakan mode Firebase (runtime toggle) |
| POST | `/api/firebase/disconnect` | Matikan mode Firebase |
| POST | `/api/backup` | Buat arsip JSON ke `data/backups/` |
| POST | `/api/restore` | Restore dari backup terbaru |
| POST | `/api/devices/<id>/config` | Simpan konfigurasi pending untuk ESP32 |
| GET | `/api/devices/<id>/commands` | ESP32 polling; jika ada pending kirim `apply_config` |
| POST | `/api/devices/<id>/ack` | ESP32 ACK hasil penerapan config |
| GET/POST | `/api/esp32/status`, `/api/esp32/config`, `/reboot`, `/reset`, `/logs` | Kontrak legacy ESP32 (backward-compat) |
| GET/POST | `/api/logs` | Tail log backend + aksi `clear` |

### 2.3 Event Socket.IO (server → client)

| Event | Payload | Kapan dipicu |
|---|---|---|
| `sensor_update` | reading lengkap | setiap `POST /api/sensor-data` berhasil |
| `status_update` | status bundle | perubahan koneksi Firebase/ESP32, startup, refresh |
| `ai_update` | `{ready, last_prediction, metrics}` | selesai training manual / seed demo |
| `client_settings_update` | settings baru | `POST /api/client-settings` |

### 2.4 Keamanan ESP32
- Opsional: set `DEVICE_SHARED_SECRET` → ESP32 wajib kirim header `X-Device-Signature`.
- Tanda tangan HMAC-SHA256 atas string: `"{METHOD} {PATH}\n{device_id}\n{raw_body}"`.
- Backend memakai `hmac.compare_digest` untuk constant-time compare (cegah timing attack).

### 2.5 Penyimpanan
- **`local_data`** — list in-memory reading terakhir, dibatasi `MAX_LOCAL_READINGS` (default 1000).
- **`data/backups/backup_*.json`** — snapshot periodik (`BACKUP_INTERVAL`, default 3600 detik).
- **`data/models/weather_model.pkl` + `scaler.pkl` + `weather_model.meta.json`** — artefak AI.
- **`data/device_configs/<id>.json`** — konfigurasi per-device ESP32.
- **`data/client_settings.json`** — preferensi dashboard.
- **Firebase REST** (opsional) — mirror data kalau `FIREBASE_DATABASE_URL` diset.

---

## 3. Frontend — `frontend/index.html` + `styles.css`

Single-page dashboard, tanpa framework berat. JavaScript inline + Chart.js + Socket.IO-client dari CDN.

### 3.1 Komponen UI utama
- **Kartu metrik realtime**: suhu, kelembapan, kualitas udara, intensitas cahaya, tekanan, angin.
- **Chart.js (4 chart)**: temperature, humidity, air quality, light — di-refresh saat `sensor_update`.
- **Panel AI**: banner evaluasi (VALID/NON_VALID), distribusi train/test, metrik (accuracy, macro F1, baseline), forecast per-jam.
- **Panel Settings**: interval polling, offline threshold, auto-refresh toggle.
- **Panel Data Management**: clear old data, backup, restore, export CSV/JSON.
- **Panel ESP32 Devices**: list device, push config pending, baca status.

### 3.2 Alur Koneksi
1. Saat load: `fetch /api/config` → init UI defaults.
2. Buka Socket.IO (`path:/socket.io`, transport websocket→polling).
3. Listener terpasang untuk 6 event: `connect`, `disconnect`, `connect_error`, `sensor_update`, `status_update`, `ai_update`, `client_settings_update`.
4. Polling fallback (REST) berjalan hanya bila socket disconnect.

### 3.3 Helper Penting
- `apiUrl(path)` — pintu tunggal pembentukan URL, mempermudah deploy sub-path.
- `escHtml(s)` — escape HTML entity untuk semua data yang diinterpolasi lewat `innerHTML` (anti-XSS).
- `scheduleUiUpdate(data)` — batching update via `requestAnimationFrame` agar tidak thrashing DOM.
- `recreateChart pattern` — tiap init chart, cek `chart.destroy()` dulu untuk cegah memory leak.

---

## 4. AI / Machine Learning — kelas `WeatherAIModel`

Fokus: klasifikasi kondisi cuaca dari 4 fitur sensor + forecasting sederhana.

### 4.1 Fitur Input (4 dimensi)
| Urutan | Fitur | Satuan | Sumber |
|---|---|---|---|
| 1 | `temperature` | °C | SHT31 |
| 2 | `humidity` | % | SHT31 |
| 3 | `air_quality` | AQI-like | MQ-series / estimasi |
| 4 | `light_intensity` | lux | BH1750 |

### 4.2 Label (7 kelas, rule-based dari banding suhu × kelembapan + override AQI)

| Label | Kriteria Pokok |
|---|---|
| `Polluted` | `air_quality > 300` (override semua) |
| `Hot Humid` | suhu ≥ 30 & humidity ≥ 60 |
| `Hot Dry` | suhu ≥ 30 & humidity < 30 |
| `Very Hot` | suhu ≥ 30 & humidity normal |
| `Very Humid` | suhu 25–30 & humidity ≥ 80 |
| `Cool Humid` | suhu < 20 & humidity ≥ 60 |
| `Cold` | suhu < 20 |
| `Normal` | selainnya |

Logika berada di `_label_from_features()` — inilah "ground truth" supervised yang dipakai untuk melatih RandomForest. Dengan kata lain, model belajar **mempercepat** evaluasi yang deterministik ini dari sensor noisy, sekaligus membangun kepercayaan diri (confidence) per kelas.

### 4.3 Pipeline Training (`train_model`)
1. **Ambil data** — `local_data` (+ augmentasi sintetis jika data <N atau single-class).
2. **Preprocess** — `prepare_training_data()` → `X (n,4)`, `y (n,)`, timestamps.
3. **Split** — `train_test_split(test_size=0.2, stratify=y)` bila jumlah kelas cukup; fallback random split.
4. **Scale** — `StandardScaler.fit_transform(X_train)`, `transform(X_test)`.
5. **Fit** — `RandomForestClassifier(n_estimators=120, class_weight='balanced_subsample', random_state=42)`.
6. **Evaluasi** — `accuracy_score`, `f1_score(macro)`, `balanced_accuracy_score`, `confusion_matrix`, baseline majority.
7. **Tentukan evaluation_mode** — `VALID` bila test set punya ≥2 kelas berbeda & sample cukup; kalau tidak `NON_VALID` dengan warning.
8. **Persist** — atomic write `weather_model.pkl`, `scaler.pkl`, `weather_model.meta.json`.
9. **Emit** `ai_update` via Socket.IO.

### 4.4 Inferensi (`predict_weather`)
- Input 1 reading sensor.
- `scaler.transform(x)` → `model.predict_proba(x)`.
- Pilih argmax + tingkat keyakinan (confidence).
- Batasi output sesuai `PREDICTION_CONFIDENCE_THRESHOLD` (default 0.6); di bawahnya ditandai `low_confidence`.

### 4.5 Forecasting Sederhana (linear trend + heuristik hujan)
- `_fit_linear(series)` — regresi linear OLS atas 30 titik terakhir suhu/kelembapan/lux.
- `rain_probability(...)` — kombinasi kelembapan tinggi + lux rendah + tren menurun.
- `weather_type(rain_prob, lux)` — map ke label Indonesia:
  - `Hujan` jika rain_prob ≥ 70%
  - `Mendung` jika lux < 1000
  - `Berawan` jika lux < 10000
  - `Cerah` lainnya
- `recommendation(...)` — saran praktis (bawa payung, pakai masker, dll).

### 4.6 Library ML yang Dipakai

| Library | Fungsi |
|---|---|
| `scikit-learn.ensemble.RandomForestClassifier` | Classifier utama; ensemble 120 pohon, class_weight balanced untuk menangani imbalanced dataset |
| `sklearn.model_selection.train_test_split` | Split stratified untuk jaga distribusi kelas |
| `sklearn.preprocessing.StandardScaler` | Standardisasi fitur (mean=0, std=1) — mencegah fitur bercampur skala dominasi pohon |
| `sklearn.metrics.accuracy_score` | Akurasi standar |
| `sklearn.metrics.f1_score(average='macro')` | Rata-rata F1 per kelas — adil untuk imbalanced |
| `sklearn.metrics.balanced_accuracy_score` | Akurasi yang memperhitungkan imbalance |
| `sklearn.metrics.confusion_matrix` | Untuk diagnostik misclassification per kelas |
| `sklearn.metrics.classification_report` | Laporan ringkas per kelas (P/R/F1/support) |
| `numpy` | Aljabar linear dasar untuk feature vector |
| `joblib` | Serialisasi atomik model & scaler (lebih cepat & pickle-compatible) |

---

## 5. Library Backend Non-ML

| Library | Fungsi |
|---|---|
| `flask` | Framework HTTP minimal (routing, request/response) |
| `flask_cors` | Mengelola header CORS — membaca `ALLOWED_ORIGINS` |
| `flask_socketio` | WebSocket server berbasis Socket.IO protocol (fallback polling) |
| `eventlet` | Green-thread worker untuk Socket.IO (mendukung long-lived WS) |
| `gunicorn` | WSGI production server (Linux/Docker) |
| `requests` | HTTP client — dipakai untuk Firebase REST dan probe self |
| `python-dotenv` | Baca file `.env` ke dict |
| `python-socketio` | Socket.IO server engine (dependency `flask_socketio`) |
| `pytest` | Framework test (`tests/test_ai_training.py`) |

---

## 6. Library Frontend (dari CDN)

| Library | Fungsi |
|---|---|
| `Chart.js` | Render 4 chart line realtime |
| `Socket.IO-client` | WebSocket client ke backend |
| `Font Awesome` | Icon UI |
| `Google Fonts (Inter, Inter Tight)` | Typography |

Tidak ada bundler/transpiler — semua JS inline, ES2017+ diasumsikan tersedia di browser modern.

---

## 7. Firmware ESP32 — `WEATHER_STATION_UNIFIED_v1_1_2.ino`

Ringkas (di luar scope server tapi relevan):
- **Sensor**: SHT31 (temp/hum), BH1750 (lux), INA219 (voltase/arus), opsional MQ untuk AQI, GPS NEO-6M.
- **Display**: OLED SSD1306 (icons di `icons.h`).
- **Storage**: Preferences (NVS) untuk Wi-Fi, device_id, shared secret, flag TLS.
- **Network**: `WiFiClientSecure` (default TLS verified, override via NVS `tls_insecure`).
- **Offline queue**: 25 slot × 1KB buffer, replay saat online lagi.
- **Task loop**: non-blocking dengan `millis()`, watchdog aktif, `delay()` ≤ 50ms.

---

## 8. Verifikasi Cepat

```bash
# Syntax & import
python -c "import ast; ast.parse(open('backend/app.py').read())"

# Jalankan
docker compose up -d --build
curl http://localhost:1111/api/health
curl http://localhost:1111/api/ai/status | jq .

# Training manual
curl -X POST http://localhost:1111/api/train-model -H "Content-Type: application/json" -d '{}'

# Export CSV
curl "http://localhost:1111/api/export-data?start_date=2026-04-01&end_date=2026-04-17&format=csv" -o export.csv

# Test
pytest tests/
```

Dashboard: `http://localhost:9999/#dashboard`

---

## 9. Diagram

Flowchart sistem utuh tersedia di [flowchart.drawio](flowchart.drawio). Buka via:
- **Online**: [app.diagrams.net](https://app.diagrams.net) → File → Open From → Device.
- **VSCode**: ekstensi "Draw.io Integration" (hediet.vscode-drawio) — klik dua kali file.
- **Desktop**: Draw.io Desktop.
