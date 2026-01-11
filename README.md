# Weather Station Server

Backend Flask + Socket.IO dan dashboard web yang disajikan melalui Nginx reverse proxy.

## Arsitektur (Produksi)

- `nginx` (host `:9999`) melayani dashboard (`frontend/`) dan mem-proxy:
  - `/api/` ke `http://weather-station:1111`
  - `/socket.io/` (WebSocket upgrade) ke `http://weather-station:1111`
- `weather-station` (host `:1111`) menjalankan API dan Socket.IO.

Tidak ada IP yang di-hardcode di frontend maupun backend; seluruh akses menggunakan origin/proxy (relative path).

## Menjalankan (Docker Compose dari root repo)

1. Salin template environment:
```bash
cp .env.example .env
```

2. Jalankan:
```bash
docker compose up -d --build
```

3. Uji cepat:
```bash
curl http://localhost:1111/api/health
```

4. Buka dashboard:
- `http://localhost:9999/#dashboard`

## Struktur Folder (final)

```
weather-station-server/
  backend/
    app.py
  config/
    server.conf
    server.conf.example
  data/
    backups/               # lokasi backup (persist)
    models/                # lokasi model runtime (persist)
    device_configs/        # konfigurasi device (persist)
    client_settings.json   # pengaturan dashboard (persist)
  docker/
    Dockerfile
    nginx.conf
    docker-compose.example.yml
  frontend/
    index.html
    styles.css
  logs/
  ssl/
  .env                    # tidak di-commit (lihat .gitignore)
  .env.example
  .gitignore
  docker-compose.yml      # satu-satunya sumber kebenaran
  requirements.txt
```

## Konfigurasi

### `config/server.conf` (format KEY=VALUE)

`server.conf` wajib format dotenv-like:
```ini
HOST=0.0.0.0
PORT=1111
DEBUG=false
LOG_LEVEL=INFO
```

Urutan prioritas konfigurasi:
1) `config/server.conf` (dev/local) dan `/etc/weather-station/server.conf` (runtime container)
2) Environment dari `.env` (ENV selalu menang)

Catatan: backend tidak pernah menulis ulang `server.conf`. Jika diperlukan penyimpanan runtime, backend akan menulis ke:
- `data/runtime_config.json` (opsional, untuk snapshot)

### `.env` / `.env.example`

- `.env` digunakan oleh `docker-compose.yml` dan tidak boleh di-commit.
- `DEVICE_SHARED_SECRET` (opsional): aktifkan verifikasi signature untuk endpoint device (lihat bagian ESP32).

## Fondasi Integrasi ESP32 via Web (API Kontrak)

Semua konfigurasi device disimpan per perangkat di `data/device_configs/<device_id>.json`.

### 1) Simpan konfigurasi yang diinginkan (pending)
`POST /api/devices/<device_id>/config`

Contoh:
```bash
curl -X POST http://localhost:1111/api/devices/esp32-1/config \
  -H "Content-Type: application/json" \
  -d '{"sensor_interval":5,"selected_sensors":{"temperature":true}}'
```

### 2) Device polling perintah
`GET /api/devices/<device_id>/commands`

Contoh:
```bash
curl http://localhost:1111/api/devices/esp32-1/commands
```

Jika ada konfigurasi pending, server akan mengirim:
- `command: "apply_config"`
- `command_id`
- `payload` (konfigurasi)

### 3) ACK hasil penerapan
`POST /api/devices/<device_id>/ack`

Contoh:
```bash
curl -X POST http://localhost:1111/api/devices/esp32-1/ack \
  -H "Content-Type: application/json" \
  -d '{"command_id":"<isi-dari-commands>","success":true,"reason":""}'
```

### Signature (opsional) untuk device

Jika `DEVICE_SHARED_SECRET` diisi, request device wajib mengirim header:
- `X-Device-Signature: <hex>`

Format HMAC (SHA-256) yang ditandatangani:
`{METHOD} {PATH}\n{device_id}\n{raw_body}`

Jika tidak diisi, verifikasi signature dilewati.
