#!/usr/bin/env python3
"""
Server Backend Stasiun Cuaca
Dioptimalkan untuk Server Debian 12 dengan CasaOS
Siap produksi dengan penanganan error komprehensif
"""

import os
import sys
import logging
import json
import random
import string
import logging
import socket
import hashlib
import threading
import requests
import firebase_admin
from firebase_admin import credentials, db
import re
import hmac
import secrets
import time
import signal
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
try:
    from zoneinfo import ZoneInfo  # Python 3.9+
except Exception:  # pragma: no cover
    ZoneInfo = None
from dotenv import dotenv_values
from flask import Flask, request, jsonify
from flask_cors import CORS
from flask_socketio import SocketIO, emit
from flask_socketio import disconnect as socketio_disconnect
from sklearn.ensemble import RandomForestClassifier
from sklearn.model_selection import train_test_split
from sklearn.preprocessing import StandardScaler
from sklearn.metrics import accuracy_score, classification_report, f1_score, balanced_accuracy_score, confusion_matrix
from collections import Counter
import joblib
import numpy as np

# firebase_admin starts crashing on home networks
os.environ['GRPC_ENABLE_FORK_SUPPORT'] = '0'
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

# Bootstrap logger (will be reconfigured by setup_logging() after config loads)
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger("weather-station")

APP_VERSION = "3.1"

JAKARTA_TZ = ZoneInfo("Asia/Jakarta") if ZoneInfo else timezone(timedelta(hours=7))


def iso_from_dt(dt: datetime, assume_tz=JAKARTA_TZ) -> str:
    """Return ISO-8601 timestamp in UTC with trailing 'Z'."""
    if not isinstance(dt, datetime):
        return iso_now()
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=assume_tz)
    dt_utc = dt.astimezone(timezone.utc)
    return dt_utc.replace(microsecond=0).isoformat().replace("+00:00", "Z")


def iso_now() -> str:
    return iso_from_dt(datetime.now(timezone.utc), assume_tz=timezone.utc)


# Configuration management
class Config:
    def __init__(self):
        self.load_config()
    
    def _apply_kv_map(self, mapping: dict, source_label: str = "server.conf"):
        for key in self.config:
            raw = mapping.get(key)
            if raw is None:
                continue
            value = str(raw).strip()
            if key in ['DEBUG', 'FIREBASE_AUTO_CONNECT']:
                self.config[key] = value.lower() == 'true'
            elif key in ['PORT', 'MODEL_TRAINING_INTERVAL', 'MAX_LOCAL_READINGS',
                         'MAX_FIREBASE_READINGS', 'MAX_FIREBASE_PREDICTIONS',
                         'REQUEST_TIMEOUT', 'MAX_RETRIES', 'UPDATE_INTERVAL',
                         'BACKUP_INTERVAL', 'HEALTH_CHECK_INTERVAL']:
                self.config[key] = int(value)
            elif key in ['PREDICTION_CONFIDENCE_THRESHOLD']:
                self.config[key] = float(value)
            else:
                self.config[key] = value
        logger.info(f"Loaded konfigurasi dari {source_label}")

    def load_config(self):
        """Muat konfigurasi dari berbagai sumber"""
        # Default configuration
        self.config = {
            'HOST': '0.0.0.0',
            'PORT': 1111,
            'DEBUG': False,
            'LOG_LEVEL': 'INFO',
            'LOG_FILE': '/var/log/weather-station/app.log',
            'DATA_DIR': '/var/lib/weather-station',
            'CONFIG_DIR': '/etc/weather-station',
            'RUN_DIR': '/run/weather-station',
            'FIREBASE_AUTO_CONNECT': False,
            'FIREBASE_API_KEY': '',
            'FIREBASE_AUTH_DOMAIN': '',
            'FIREBASE_DATABASE_URL': '',
            'FIREBASE_PROJECT_ID': '',
            'FIREBASE_STORAGE_BUCKET': '',
            'FIREBASE_MESSAGING_SENDER_ID': '',
            'FIREBASE_APP_ID': '',
            'FIREBASE_MEASUREMENT_ID': '',
            'FIREBASE_CREDENTIALS_PATH': '',
            'ADMIN_API_KEY': 'change-me',
            'DEVICE_SHARED_SECRET': '',
            'DEVICE_REGISTRY_FILE': 'devices.json',
            'DEVICE_SESSION_TTL': 3600,
            'DEVICE_TIME_DRIFT': 60,
            'CLIENT_SETTINGS_FILE': 'client_settings.json',
            'MODEL_TRAINING_INTERVAL': 50,
            'PREDICTION_CONFIDENCE_THRESHOLD': 0.6,
            'MIN_TRAIN_SAMPLES_PER_CLASS': 10,
            'MAX_PREDICTION_HISTORY': 50,
            'MAX_LOCAL_READINGS': 1000,
            'MAX_FIREBASE_READINGS': 100,
            'MAX_FIREBASE_PREDICTIONS': 50,
            'REQUEST_TIMEOUT': 30,
            'MAX_RETRIES': 3,
            'UPDATE_INTERVAL': 2,
            'BACKUP_INTERVAL': 3600,  # 1 hour
            'HEALTH_CHECK_INTERVAL': 60,  # 1 minute
        }

        if os.name == 'nt':
            self.config.update({
                'LOG_FILE': str(PROJECT_ROOT / 'logs' / 'app.log'),
                'DATA_DIR': str(PROJECT_ROOT / 'data'),
                'CONFIG_DIR': str(PROJECT_ROOT / 'config'),
                'RUN_DIR': str(PROJECT_ROOT / 'run')
            })
        
        # Muat dari server.conf (format KEY=VALUE). Prioritas:
        # 1) config/server.conf di repo (dev/local)
        # 2) ${CONFIG_DIR}/server.conf (runtime di container)
        config_dir_env = os.getenv('CONFIG_DIR')
        config_dir_candidate = Path(config_dir_env) if config_dir_env else Path(self.config.get('CONFIG_DIR'))
        config_files = [
            (PROJECT_ROOT / 'config' / 'server.conf', 'config/server.conf'),
            (config_dir_candidate / 'server.conf', f'{config_dir_candidate}/server.conf')
        ]
        for cfg_path, label in config_files:
            if cfg_path.exists():
                try:
                    kv_map = dotenv_values(str(cfg_path))
                    self._apply_kv_map(kv_map, source_label=label)
                    logger.info(f"Config loaded from {label}: FIREBASE_AUTO_CONNECT={kv_map.get('FIREBASE_AUTO_CONNECT', 'NOT_FOUND')}")
                except Exception as exc:
                    logger.warning(f"Gagal membaca {label}: {exc}")
            else:
                logger.warning(f"Config file tidak ditemukan: {label}")
        env_map = {key: os.getenv(key) for key in self.config.keys() if os.getenv(key) is not None}
        if env_map:
            self._apply_kv_map(env_map, source_label="ENV")

        if os.name == 'nt':
            for path_key, fallback in {
                'LOG_FILE': str(PROJECT_ROOT / 'logs' / 'app.log'),
                'DATA_DIR': str(PROJECT_ROOT / 'data'),
                'CONFIG_DIR': str(PROJECT_ROOT / 'config'),
                'RUN_DIR': str(PROJECT_ROOT / 'run')
            }.items():
                current_value = self.config.get(path_key, '')
                if isinstance(current_value, str) and current_value.startswith('/'):
                    self.config[path_key] = fallback
    
    def get(self, key, default=None):
        return self.config.get(key, default)
    
    def set(self, key, value):
        self.config[key] = value
    
    def save(self):
        """Simpan konfigurasi runtime (tidak mengubah server.conf)."""
        runtime_path = Path(self.config.get('DATA_DIR')) / 'runtime_config.json'
        runtime_path.parent.mkdir(parents=True, exist_ok=True)
        with open(runtime_path, 'w', encoding='utf-8') as f:
            json.dump(self.config, f, indent=2, ensure_ascii=False)

# Initialize configuration
config = Config()

def ensure_writable_path(path: Path, fallback: Path):
    try:
        path.mkdir(parents=True, exist_ok=True)
        test_file = path / '.write_test'
        with open(test_file, 'w') as f:
            f.write('ok')
        test_file.unlink(missing_ok=True)
        return path
    except Exception:
        fallback.mkdir(parents=True, exist_ok=True)
        return fallback

# Resolve writable paths (avoid /var permission issues)
PROJECT_LOG_DIR = PROJECT_ROOT / 'logs'
PROJECT_DATA_DIR = PROJECT_ROOT / 'data'

log_path = Path(config.get('LOG_FILE'))
log_path = ensure_writable_path(log_path.parent, PROJECT_LOG_DIR) / log_path.name
config.set('LOG_FILE', str(log_path))

DATA_DIR = ensure_writable_path(Path(config.get('DATA_DIR')), PROJECT_DATA_DIR)
config.set('DATA_DIR', str(DATA_DIR))
DEVICE_REGISTRY_PATH = DATA_DIR / config.get('DEVICE_REGISTRY_FILE')
CLIENT_SETTINGS_PATH = DATA_DIR / config.get('CLIENT_SETTINGS_FILE')
DEVICE_CONFIGS_DIR = DATA_DIR / 'device_configs'
RAW_PAYLOAD_LOG = DATA_DIR / 'raw_payloads.log'

DEVICE_ID_RE = re.compile(r'^[A-Za-z0-9_-]{1,64}$')
MAX_DEVICE_JSON_BYTES = 32 * 1024  # batas payload konfigurasi device

# ==== instrumentation helpers ====
def file_checksum(path: Path) -> str:
    if not path.exists():
        return ""
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            h.update(chunk)
    return h.hexdigest()


def log_startup_paths():
    logger.info(
        "Startup paths: app=%s cwd=%s data_dir=%s log_file=%s models_dir=%s",
        __file__,
        os.getcwd(),
        DATA_DIR,
        config.get('LOG_FILE'),
        Path(config.get('DATA_DIR')) / 'models'
    )


def _is_valid_device_id(device_id: str) -> bool:
    return bool(device_id and DEVICE_ID_RE.match(device_id))


def _require_device_signature() -> bool:
    shared = str(config.get('DEVICE_SHARED_SECRET') or '').strip()
    return bool(shared)


def _verify_device_signature_or_skip(device_id: str) -> bool:
    """
    Hook keamanan ringan (opsional).

    Jika ENV/Config `DEVICE_SHARED_SECRET` diisi, maka request wajib mengirim
    header `X-Device-Signature` berupa HMAC-SHA256 (hex) dari:
    `{METHOD} {PATH}\\n{device_id}\\n{raw_body}`.

    Jika secret tidak diisi, verifikasi dilewati.
    """
    shared = str(config.get('DEVICE_SHARED_SECRET') or '').strip()
    if not shared:
        return True

    signature = request.headers.get('X-Device-Signature', '')
    if not signature:
        return False

    body = request.get_data(cache=True) or b''
    message = (f"{request.method} {request.path}\n{device_id}\n").encode('utf-8') + body
    expected = hmac.new(shared.encode('utf-8'), message, hashlib.sha256).hexdigest()
    return hmac.compare_digest(signature.strip().lower(), expected.lower())


def _read_device_config_file(device_id: str):
    cfg_path = DEVICE_CONFIGS_DIR / f"{device_id}.json"
    if not cfg_path.exists():
        return None
    with open(cfg_path, 'r', encoding='utf-8') as f:
        return json.load(f)


def _write_device_config_file(device_id: str, payload: dict):
    DEVICE_CONFIGS_DIR.mkdir(parents=True, exist_ok=True)
    cfg_path = DEVICE_CONFIGS_DIR / f"{device_id}.json"
    tmp_path = cfg_path.with_suffix('.json.tmp')
    with open(tmp_path, 'w', encoding='utf-8') as f:
        json.dump(payload, f, indent=2, ensure_ascii=False)
    tmp_path.replace(cfg_path)


class DeviceRegistry:
    """Simple device registry + session manager stored on disk."""

    def __init__(self, registry_path: Path, session_ttl: int, allowed_drift: int):
        self.registry_path = registry_path
        self.session_ttl = session_ttl
        self.allowed_drift = allowed_drift
        self.devices = {}
        self.sessions = {}
        self.lock = threading.Lock()
        self._load()

    def _load(self):
        if self.registry_path.exists():
            try:
                with open(self.registry_path, 'r') as f:
                    self.devices = json.load(f)
            except Exception as exc:
                logger.error(f"Failed to load device registry: {exc}")
                self.devices = {}

    def _save(self):
        try:
            self.registry_path.parent.mkdir(parents=True, exist_ok=True)
            with open(self.registry_path, 'w') as f:
                json.dump(self.devices, f, indent=2)
        except Exception as exc:
            logger.error(f"Failed to save device registry: {exc}")

    def register_device(self, device_id=None, secret=None, metadata=None):
        with self.lock:
            device_id = device_id or secrets.token_hex(8)
            secret = secret or secrets.token_hex(32)
            metadata = metadata or {}
            self.devices[device_id] = {
                "secret": secret,
                "metadata": metadata,
                "created_at": iso_now()
            }
            self._save()
        return device_id, secret

    def list_devices(self):
        return self.devices

    def is_registered(self, device_id):
        return device_id in self.devices

    def _parse_timestamp(self, timestamp):
        try:
            if isinstance(timestamp, (int, float)):
                return datetime.utcfromtimestamp(timestamp)
            if isinstance(timestamp, str):
                if timestamp.isdigit():
                    return datetime.utcfromtimestamp(int(timestamp))
                return datetime.fromisoformat(timestamp.replace('Z', '+00:00'))
        except Exception:
            return None
        return None

    def verify_signature(self, device_id, timestamp, signature):
        if not device_id or not signature or device_id not in self.devices:
            return False
        parsed_ts = self._parse_timestamp(timestamp)
        if not parsed_ts:
            return False
        drift = abs((datetime.utcnow() - parsed_ts).total_seconds())
        if drift > self.allowed_drift:
            return False
        secret_key = self.devices[device_id]['secret']
        payload = f"{device_id}:{timestamp}".encode()
        expected = hmac.new(secret_key.encode(), payload, hashlib.sha256).hexdigest()
        return secrets.compare_digest(expected, signature)

    def issue_session(self, device_id):
        if device_id not in self.devices:
            raise ValueError("Device not registered")
        token = secrets.token_urlsafe(32)
        expires_at = datetime.utcnow() + timedelta(seconds=self.session_ttl)
        with self.lock:
            self.sessions[token] = {
                "device_id": device_id,
                "expires_at": expires_at
            }
        return token, expires_at

    def validate_session(self, device_id, token):
        if not device_id or not token:
            return False
        session = self.sessions.get(token)
        if not session:
            return False
        if session['device_id'] != device_id:
            return False
        if session['expires_at'] < datetime.utcnow():
            with self.lock:
                self.sessions.pop(token, None)
            return False
        return True


def ensure_default_client_settings(raw_settings):
    defaults = {
        "update_interval": config.get('UPDATE_INTERVAL', 5),
        "esp32_offline_seconds": 15,
        "auto_refresh": True,
        "updated_at": iso_now()
    }
    if not raw_settings:
        return defaults
    defaults.update({k: raw_settings.get(k, defaults[k]) for k in defaults})
    return defaults


client_settings_lock = threading.Lock()


def load_client_settings():
    if CLIENT_SETTINGS_PATH.exists():
        try:
            with open(CLIENT_SETTINGS_PATH, 'r') as f:
                stored = json.load(f)
                return ensure_default_client_settings(stored)
        except Exception as exc:
            logger.error(f"Failed to load client settings: {exc}")
    return ensure_default_client_settings({})


def save_client_settings(settings):
    try:
        CLIENT_SETTINGS_PATH.parent.mkdir(parents=True, exist_ok=True)
        with open(CLIENT_SETTINGS_PATH, 'w') as f:
            json.dump(settings, f, indent=2)
    except Exception as exc:
        logger.error(f"Failed to save client settings: {exc}")


device_registry = DeviceRegistry(
    DEVICE_REGISTRY_PATH,
    config.get('DEVICE_SESSION_TTL', 3600),
    config.get('DEVICE_TIME_DRIFT', 60)
)
client_settings = load_client_settings()

# Setup logging
def setup_logging():
    """Setup logging komprehensif"""
    log_dir = Path(config.get('LOG_FILE')).parent
    log_dir.mkdir(parents=True, exist_ok=True)
    
    logging.basicConfig(
        level=getattr(logging, config.get('LOG_LEVEL', 'INFO')),
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        force=True,
        handlers=[
            logging.FileHandler(config.get('LOG_FILE')),
            logging.StreamHandler(sys.stdout)
        ]
    )
    lg = logging.getLogger("weather-station")
    try:
        log_startup_paths()
    except Exception:
        pass
    return lg

logger = setup_logging()

# Create necessary directories
def create_directories():
    """Buat direktori yang diperlukan"""
    dirs = [
        config.get('DATA_DIR'),
        config.get('CONFIG_DIR'),
        config.get('RUN_DIR'),
        Path(config.get('DATA_DIR')) / 'backups',
        Path(config.get('DATA_DIR')) / 'models',
    ]
    
    for dir_path in dirs:
        Path(dir_path).mkdir(parents=True, exist_ok=True)
        logger.info(f"Direktori dibuat: {dir_path}")

create_directories()

# Initialize Flask app
app = Flask(__name__)
CORS(app, origins=["*"])
socketio = SocketIO(app, cors_allowed_origins="*")

def broadcast_status_change(status_type, new_value, additional_data=None):
    """
    Broadcast status change immediately when it occurs - Real-time status system
    
    Sistem ini menggantikan interval-based status checking dengan event-driven approach:
    - Firebase: Status berubah saat koneksi berhasil/gagal
    - ESP32: Status berubah saat data diterima atau timeout tercapai  
    - Server: Status berubah saat server start/stop
    - Local: Selalu tersedia
    
    Args:
        status_type (str): 'firebase', 'esp32', 'server'
        new_value (bool): Status baru (True/False)
        additional_data (dict): Data tambahan seperti last_seen untuk ESP32
    """
    global current_status
    
    try:
        # Update current status
        if status_type == 'firebase':
            current_status['firebase_connected'] = new_value
            current_status['firebase_enabled'] = bool(firebase_initialized)
            current_status['data_source'] = 'Firebase Real-time' if new_value else 'Local'
        elif status_type == 'esp32':
            current_status['esp32_connected'] = new_value
            if additional_data and 'last_seen' in additional_data:
                current_status['esp32_last_seen'] = additional_data['last_seen']
        elif status_type == 'server':
            current_status['server_connected'] = new_value
            current_status['server_status'] = 'online' if new_value else 'offline'
        
        current_status['last_update'] = iso_now()
        
        # Broadcast immediately
        socketio.emit('status_update', current_status.copy())
        logger.info(f"Status change broadcasted: {status_type} = {new_value}")
        
    except Exception as exc:
        logger.error(f"Gagal broadcast status change: {exc}")

def broadcast_client_settings():
    """Kirim pengaturan client terbaru ke semua klien"""
    try:
        socketio.emit('client_settings_update', client_settings)
    except Exception as exc:
        logger.error(f"Gagal broadcast client settings: {exc}")

# Get server IP
def get_server_ip():
    """Dapatkan alamat IP server"""
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return "127.0.0.1"

SERVER_IP = get_server_ip()

# Global status tracking - initialize early so Firebase tests can update status safely
current_status = {
    'server_status': 'online',
    'server_connected': True,
    'firebase_enabled': False,
    'firebase_connected': False,
    'esp32_connected': False,
    'esp32_last_seen': None,
    'last_update': iso_now(),
    'data_source': 'Local'
}

# Firebase configuration
firebase_config = {
    'apiKey': config.get('FIREBASE_API_KEY'),
    'authDomain': config.get('FIREBASE_AUTH_DOMAIN'),
    'databaseURL': config.get('FIREBASE_DATABASE_URL'),
    'projectId': config.get('FIREBASE_PROJECT_ID'),
    'storageBucket': config.get('FIREBASE_STORAGE_BUCKET'),
    'messagingSenderId': config.get('FIREBASE_MESSAGING_SENDER_ID'),
    'appId': config.get('FIREBASE_APP_ID'),
    'measurementId': config.get('FIREBASE_MEASUREMENT_ID')
}

# Firebase connection
firebase_initialized = False
last_firebase_check_at = None
firebase_last_ok = False

def set_firebase_enabled(enabled: bool):
    """Aktif/nonaktifkan penggunaan Firebase (mode runtime) tanpa mengubah konfigurasi."""
    global firebase_initialized, firebase_last_ok, last_firebase_check_at
    firebase_initialized = bool(enabled)
    current_status['firebase_enabled'] = bool(firebase_initialized)
    if not firebase_initialized:
        firebase_last_ok = False
        last_firebase_check_at = None
        if current_status.get('firebase_connected', False):
            broadcast_status_change('firebase', False)
        else:
            # tetap pastikan data_source konsisten
            current_status['data_source'] = 'Local'
        try:
            socketio.emit('status_update', current_status.copy())
        except Exception:
            pass

def test_firebase_connection():
    """Test Firebase connection"""
    global current_status
    
    try:
        if not firebase_config.get('databaseURL'):
            logger.warning("URL database Firebase tidak dikonfigurasi")
            # Broadcast status change if different
            if current_status.get('firebase_connected', False):
                broadcast_status_change('firebase', False)
            return False
        
        url = f"{firebase_config['databaseURL']}/.json"
        response = requests.get(url, timeout=config.get('REQUEST_TIMEOUT'))
        if response.status_code == 200:
            logger.info("Tes koneksi Firebase berhasil")
            # Broadcast status change if different
            if not current_status.get('firebase_connected', False):
                broadcast_status_change('firebase', True)
            return True
        else:
            logger.warning(f"Koneksi Firebase gagal dengan status: {response.status_code}")
            # Broadcast status change if different
            if current_status.get('firebase_connected', False):
                broadcast_status_change('firebase', False)
            return False
    except Exception as e:
        logger.error(f"Tes koneksi Firebase gagal: {e}")
        # Broadcast status change if different
        if current_status.get('firebase_connected', False):
            broadcast_status_change('firebase', False)
        return False


def get_firebase_connection_state():
    global last_firebase_check_at, firebase_last_ok
    if not firebase_config.get('databaseURL'):
        return False

    check_interval = max(10, min(config.get('HEALTH_CHECK_INTERVAL', 60), 300))
    now = datetime.utcnow()
    if last_firebase_check_at:
        elapsed = (now - last_firebase_check_at).total_seconds()
        if elapsed < check_interval:
            return firebase_last_ok

    firebase_last_ok = test_firebase_connection()
    last_firebase_check_at = now
    return firebase_last_ok

# Initialize Firebase
auto_connect = bool(config.get('FIREBASE_AUTO_CONNECT'))
logger.info(
    f"Firebase auto-connect config: {config.get('FIREBASE_AUTO_CONNECT')} (auto_connect: {auto_connect})"
)
if auto_connect:
    logger.info(
        "Firebase auto-connect flag true but startup test is skipped; "
        "gunakan dashboard untuk menyambungkan secara manual."
    )
else:
    logger.info("INFO: Firebase auto-connect dinonaktifkan; gunakan dashboard untuk menghubungkan.")

# Real-time Firebase listener
def start_firebase_listener():
    """Start real-time Firebase listener"""
    if not firebase_initialized:
        logger.warning("Firebase tidak terhubung, listener tidak dimulai")
        return
    
    def listener(event):
        """Handle Firebase real-time events"""
        try:
            # Jika Firebase dimatikan via dashboard, abaikan event agar UI kembali ke mode lokal
            if not firebase_initialized:
                return
            data = event.data
            if data:
                logger.info(f"Firebase update received: {data}")
                # normalize timestamp for frontend (ISO Z)
                if isinstance(data, dict):
                    parsed_ts = parse_sensor_timestamp(data.get('timestamp'))
                    if parsed_ts:
                        data['timestamp'] = iso_from_dt(parsed_ts)
                    else:
                        data.setdefault('timestamp', iso_now())
                # Broadcast ke semua connected clients
                socketio.emit('sensor_update', data)
                socketio.emit('status_update', {
                    'server_connected': True,
                    'server_status': 'online',
                    'firebase_enabled': bool(firebase_initialized),
                    'firebase_connected': True,
                    'esp32_connected': current_status.get('esp32_connected', False),
                    'esp32_last_seen': current_status.get('esp32_last_seen'),
                    'last_update': data.get('timestamp') if isinstance(data, dict) else iso_now(),
                    'data_source': 'Firebase Real-time'
                })
        except Exception as e:
            logger.error(f"Error handling Firebase event: {e}")
    
    try:
        # Start listener untuk sensor data
        ref = db.reference('/sensor_data')
        ref.listen(listener)
        logger.info("Firebase real-time listener started")
    except Exception as e:
        logger.error(f"Failed to start Firebase listener: {e}")

# WebSocket events
@socketio.on('connect')
def handle_connect():
    """Handle client connection"""
    logger.info(f"Client connected: {request.sid}")
    # Send current real-time status
    status = get_current_status()
    status['client_settings'] = client_settings
    emit('status_update', status)

@socketio.on('disconnect')
def handle_disconnect():
    """Handle client disconnection"""
    logger.info(f"Client disconnected: {request.sid}")

@socketio.on('request_status')
def handle_status_request():
    """Handle status request"""
    # Send current real-time status
    status = get_current_status()
    status['client_settings'] = client_settings
    emit('status_update', status)

# AI Weather Model
class WeatherAIModel:
    def __init__(self):
        self.model = RandomForestClassifier(
            n_estimators=120,
            random_state=42,
            class_weight='balanced_subsample',
            max_depth=None
        )
        self.scaler = StandardScaler()
        self.trained = False
        self.model_trained_at = None
        self.last_metrics = {}
        self.evaluation_mode = "UNKNOWN"
        # Pastikan direktori model writable; fallback ke ./data/models bila /var tidak bisa ditulis
        models_dir = ensure_writable_path(
            Path(config.get('DATA_DIR')) / 'models',
            PROJECT_DATA_DIR / 'models'
        )
        self.model_file = models_dir / 'weather_model.pkl'
        self.scaler_file = models_dir / 'scaler.pkl'
        
        # Load existing model if available
        self.load_model()
    
    def load_model(self):
        """Load existing model"""
        try:
            if self.model_file.exists() and self.scaler_file.exists():
                self.model = joblib.load(self.model_file)
                self.scaler = joblib.load(self.scaler_file)
                self.trained = True
                logger.info("AI model loaded successfully")
                return True
        except Exception as e:
            logger.error(f"Failed to load AI model: {e}")
        return False
    
    def _atomic_write(self, target_path: Path, obj):
        """Simpan objek menggunakan joblib ke temp lalu rename (atomic)."""
        tmp_path = target_path.with_suffix(target_path.suffix + ".tmp")
        joblib.dump(obj, tmp_path)
        tmp_path.replace(target_path)

    def save_model(self):
        """Save model to disk secara atomic and write model metadata."""
        try:
            self.model_file.parent.mkdir(parents=True, exist_ok=True)
            self._atomic_write(self.model_file, self.model)
            self._atomic_write(self.scaler_file, self.scaler)

            # Persist metadata alongside model
            meta = getattr(self, 'model_meta', None) or {}
            meta.update({
                'model_path': str(self.model_file),
                'scaler_path': str(self.scaler_file),
                'saved_at': iso_now(),
            })
            meta_path = self.model_file.with_suffix('.meta.json')
            with open(meta_path, 'w') as f:
                json.dump(meta, f, indent=2, default=str)

            logger.info(f"AI model saved successfully to {self.model_file}")
            return True
        except Exception as e:
            logger.error(f"Failed to save AI model: {e}")
            return False
    
    def prepare_training_data(self, data):
        """Prepare data for AI model training.

        Use banding on temperature/humidity + air quality to produce richer labels
        and reduce the chance of single-class outputs for typical sensor distributions.
        """

    def _label_from_features(self, temp, humidity, air_quality):
        """Derive label from features (same logic as prepare_training_data)."""
        if air_quality and air_quality > 300:
            return 'Polluted'
        if temp < 15:
            tband = 'cold'
        elif temp < 20:
            tband = 'cool'
        elif temp < 25:
            tband = 'normal'
        elif temp < 30:
            tband = 'warm'
        elif temp < 35:
            tband = 'hot'
        else:
            tband = 'very_hot'

        if humidity < 30:
            hband = 'dry'
        elif humidity < 60:
            hband = 'normal'
        elif humidity < 80:
            hband = 'humid'
        else:
            hband = 'very_humid'

        if tband in ('very_hot', 'hot') and hband in ('humid', 'very_humid'):
            return 'Hot Humid'
        if tband in ('very_hot', 'hot') and hband in ('dry',):
            return 'Hot Dry'
        if tband in ('very_hot', 'hot') and hband in ('normal',):
            return 'Very Hot'
        if tband in ('warm',) and hband in ('very_humid',):
            return 'Very Humid'
        if tband in ('cold', 'cool') and hband in ('very_humid', 'humid'):
            return 'Cool Humid'
        if tband in ('cold', 'cool'):
            return 'Cold'
        return 'Normal'

    def _generate_synthetic_features(self, archetypes, rng, n_each=2):
        """Generate synthetic feature vectors from archetype dicts using small jitter."""
        feats = []
        labels = []
        for arch in archetypes:
            for _ in range(n_each):
                temp = float(arch.get('temperature', 20.0)) + float(rng.normal(0, 0.5))
                humidity = float(arch.get('humidity', 50.0)) + float(rng.normal(0, 1.0))
                air_quality = float(arch.get('air_quality', 50.0)) + float(rng.normal(0, 5.0))
                light_intensity = float(arch.get('light_intensity', 500.0)) + float(rng.normal(0, 50.0))
                battery_voltage = float(arch.get('battery_voltage', 3.8)) + float(rng.normal(0, 0.02))
                feats.append([temp, humidity, air_quality, light_intensity, battery_voltage])
                labels.append(self._label_from_features(temp, humidity, air_quality))
        return np.array(feats, dtype=float), np.array(labels)

    def _oversample_minority(self, X_train, y_train, rng, min_per_class):
        """Oversample classes in X_train to have at least min_per_class examples using gaussian jitter."""
        X_new = [np.array(X_train)]
        y_new = [np.array(y_train)]
        unique, counts = np.unique(y_train, return_counts=True)
        for label, count in zip(unique, counts):
            if count >= min_per_class:
                continue
            needed = min_per_class - int(count)
            # pick indices of this label
            idxs = np.where(y_train == label)[0]
            if idxs.size == 0:
                continue
            samples = X_train[idxs]
            for i in range(needed):
                src = samples[i % len(samples)]
                jitter = rng.normal(0, [0.5, 1.0, 5.0, 50.0, 0.02])
                new_sample = src + jitter
                X_new.append(new_sample.reshape(1, -1))
                y_new.append(np.array([label]))
        if len(X_new) > 1:
            X_aug = np.vstack(X_new)
            y_aug = np.concatenate(y_new)
            return X_aug, y_aug
        return np.array(X_train), np.array(y_train)
        features = []
        labels = []
        timestamps = []

        def to_float_safe(v, default=0.0):
            try:
                return float(v)
            except Exception:
                return default

        for item in data:
            temp = to_float_safe(item.get('temperature'))
            humidity = to_float_safe(item.get('humidity'))
            air_quality = to_float_safe(item.get('air_quality'))
            light_intensity = to_float_safe(item.get('light_intensity'))
            battery_voltage = to_float_safe(item.get('battery_voltage'))

            feature_vector = [temp, humidity, air_quality, light_intensity, battery_voltage]
            features.append(feature_vector)

            # Strong signal: polluted air
            if air_quality and air_quality > 300:
                condition = 'Polluted'
            else:
                # Derive bands
                if temp < 15:
                    tband = 'cold'
                elif temp < 20:
                    tband = 'cool'
                elif temp < 25:
                    tband = 'normal'
                elif temp < 30:
                    tband = 'warm'
                elif temp < 35:
                    tband = 'hot'
                else:
                    tband = 'very_hot'

                if humidity < 30:
                    hband = 'dry'
                elif humidity < 60:
                    hband = 'normal'
                elif humidity < 80:
                    hband = 'humid'
                else:
                    hband = 'very_humid'

                # Map band pairs to human-friendly labels
                if tband in ('very_hot', 'hot') and hband in ('humid', 'very_humid'):
                    condition = 'Hot Humid'
                elif tband in ('very_hot', 'hot') and hband in ('dry',):
                    condition = 'Hot Dry'
                elif tband in ('very_hot', 'hot') and hband in ('normal',):
                    condition = 'Very Hot'
                elif tband in ('warm',) and hband in ('very_humid',):
                    condition = 'Very Humid'
                elif tband in ('cold', 'cool') and hband in ('very_humid', 'humid'):
                    condition = 'Cool Humid'
                elif tband in ('cold', 'cool'):
                    condition = 'Cold'
                else:
                    condition = 'Normal'

            labels.append(condition)
            ts_raw = item.get('timestamp') or item.get('ts') or item.get('time')
            timestamps.append(ts_raw)

        X = np.array(features, dtype=float)
        y = np.array(labels)
        return X, y, timestamps
    
    def train_model(self, force_single_class: bool = False):
        """Train AI weather prediction model with time-based split and imbalance awareness."""
        logger.info("AI: Starting model training...")
        
        try:
            status = "OK"
            evaluation_mode = "VALID"
            synthetic_used = False
            warning_msgs = []

            if len(local_data) < 50:
                status = "DATA_TOO_SMALL"
                evaluation_mode = "NON_VALID"
                msg = f"AI: Training dibatalkan, data nyata terlalu sedikit ({len(local_data)}/50)"
                logger.error(msg)
                self.last_metrics = {"status": status, "message": msg, "evaluation_mode": evaluation_mode, "label_distribution": dict(Counter(y))}
                return False

            sample_data = local_data.copy()
            X, y, timestamps = self.prepare_training_data(sample_data)
            label_counts = Counter(y)
            logger.info("AI: Label distribution (all) %s", dict(label_counts))

            # Use deterministic seed for augmentation reproducibility
            seed = int(time.time())
            rng = np.random.default_rng(seed)

            unique_labels = np.unique(y)
            needs_synthetic = False
            if len(unique_labels) < 2 and not force_single_class:
                status = "DATA_INSUFFICIENT_VARIETY"
                evaluation_mode = "NON_VALID"
                msg = "AI: Training dibatalkan, hanya ada 1 kelas label pada data nyata."
                logger.error(msg)
                self.last_metrics = {"status": status, "message": msg, "evaluation_mode": evaluation_mode, "label_distribution": dict(label_counts)}
                return False

            if len(unique_labels) < 2 and force_single_class:
                logger.warning("AI: Force training diaktifkan, sampel sintetik akan ditambahkan ke TRAIN set. Evaluasi NON_VALID.")
                evaluation_mode = "NON_VALID"
                synthetic_used = True
                needs_synthetic = True
                archetypes = [
                    {'temperature': 10, 'humidity': 50, 'air_quality': 50, 'light_intensity': 100, 'battery_voltage': 3.8},   # Cold
                    {'temperature': 38, 'humidity': 35, 'air_quality': 80, 'light_intensity': 1200, 'battery_voltage': 3.9}, # Very Hot / Hot Dry
                    {'temperature': 26, 'humidity': 85, 'air_quality': 90, 'light_intensity': 800, 'battery_voltage': 4.0},  # Hot Humid
                    {'temperature': 24, 'humidity': 60, 'air_quality': 80, 'light_intensity': 500, 'battery_voltage': 3.8},  # Normal
                ]

            # Jika ada kelas dengan count < 2, tandai evaluasi NON_VALID, lakukan split non-stratified
            class_counts = {label: int(np.sum(y == label)) for label in unique_labels}
            if any(count < 2 for count in class_counts.values()):
                evaluation_mode = "NON_VALID"
                warning_msgs.append("Kelas minor <2; evaluasi tidak representatif (NON_VALID). Tidak pakai stratify.")

            # Time-based split: sort by timestamp (fallback ke urutan indeks)
            def _parse_ts(ts_raw, idx):
                try:
                    if ts_raw is None:
                        dt = datetime.fromtimestamp(idx, tz=timezone.utc)
                    elif isinstance(ts_raw, (int, float)):
                        dt = datetime.fromtimestamp(ts_raw, tz=timezone.utc)
                    elif isinstance(ts_raw, datetime):
                        dt = ts_raw.astimezone(timezone.utc) if ts_raw.tzinfo else ts_raw.replace(tzinfo=timezone.utc)
                    else:
                        ts_str = str(ts_raw)
                        if ts_str.endswith('Z'):
                            ts_str = ts_str.replace('Z', '+00:00')
                        dt = datetime.fromisoformat(ts_str)
                        if dt.tzinfo is None:
                            dt = dt.replace(tzinfo=timezone.utc)
                        else:
                            dt = dt.astimezone(timezone.utc)
                    # Normalize to naive UTC for consistent comparison
                    return dt.astimezone(timezone.utc).replace(tzinfo=None)
                except Exception as e:
                    logger.debug(f"AI: _parse_ts failed for {ts_raw} ({type(ts_raw)}): {e}")
                    return datetime.fromtimestamp(idx, tz=timezone.utc).replace(tzinfo=None)
            
            time_keys = [(_parse_ts(timestamps[i], i), i) for i in range(len(timestamps))]
            try:
                sorted_indices = [idx for _, idx in sorted(time_keys, key=lambda x: x[0])]
            except TypeError as e:
                # Fallback: keep original order if timestamps cannot be compared
                logger.warning(f"AI: Timestamp comparison failed, falling back to insertion order: {e}")
                sorted_indices = list(range(len(timestamps)))
            split_idx = max(1, min(len(sorted_indices) - 1, int(len(sorted_indices) * 0.8)))
            train_idx = sorted_indices[:split_idx]
            test_idx = sorted_indices[split_idx:]
            
            X_train, X_test = X[train_idx], X[test_idx]
            y_train, y_test = y[train_idx], y[test_idx]

            # If synthetic augmentation requested (force single-class), add synthetic samples to TRAIN only
            if needs_synthetic:
                syn_X, syn_y = self._generate_synthetic_features(archetypes, rng, n_each=3)
                X_train = np.vstack([X_train, syn_X])
                y_train = np.concatenate([y_train, syn_y])
                logger.info(f"AI: Added {len(syn_y)} synthetic samples to training set")

            # Oversample minority classes in training set to a minimal per-class count
            min_per = int(config.get('MIN_TRAIN_SAMPLES_PER_CLASS', 10))
            X_train, y_train = self._oversample_minority(X_train, y_train, rng, min_per)

            all_counts = {lbl: int(np.sum(y == lbl)) for lbl in unique_labels}
            train_counts = {lbl: int(np.sum(y_train == lbl)) for lbl in np.unique(y_train)}
            test_counts = {lbl: int(np.sum(y_test == lbl)) for lbl in np.unique(y_test)}
            logger.info(f"AI: Label distribution all={all_counts}, train={train_counts}, test={test_counts}")

            # Scale features
            X_train_scaled = self.scaler.fit_transform(X_train)
            X_test_scaled = self.scaler.transform(X_test)
            
            # Train model
            self.model.fit(X_train_scaled, y_train)

            # Evaluate
            y_test_pred = self.model.predict(X_test_scaled)
            train_score = self.model.score(X_train_scaled, y_train)
            test_score = self.model.score(X_test_scaled, y_test)
            macro_f1 = f1_score(y_test, y_test_pred, average='macro', zero_division=0)
            bal_acc = balanced_accuracy_score(y_test, y_test_pred)
            cm = confusion_matrix(y_test, y_test_pred, labels=unique_labels)

            # Baseline majority class (use proportion in TEST set to avoid >1.0 values)
            train_counts_for_baseline = Counter(y_train)
            majority_label, majority_count_train = train_counts_for_baseline.most_common(1)[0]
            majority_in_test = int(np.sum(y_test == majority_label)) if len(y_test) > 0 else 0
            baseline_acc = (majority_in_test / len(y_test)) if len(y_test) > 0 else 0.0
            baseline_acc = min(1.0, float(baseline_acc))

            # Periksa validitas evaluasi
            test_class_counts = {lbl: int(np.sum(y_test == lbl)) for lbl in np.unique(y_test)}
            if len(np.unique(y_test)) < 2 or any(cnt < 2 for cnt in test_class_counts.values()):
                evaluation_mode = "NON_VALID"
                warning_msgs.append("Distribusi test set tidak memadai (kelas <2). Metrik tidak representatif.")

            # classification_report hanya jika valid
            report = ""
            if evaluation_mode == "VALID":
                report = classification_report(y_test, y_test_pred, zero_division=0)
                logger.info("AI: Classification report (VALID):\n%s", report)
            else:
                logger.warning("AI: Evaluation mode NON_VALID. Lewati classification_report yang menyesatkan.")

            # If evaluation is NON_VALID, mark metrics as untrusted and null out misleading numeric metrics
            metrics_trusted = (evaluation_mode == "VALID")
            display_test_score = float(test_score) if metrics_trusted else None
            display_macro_f1 = float(macro_f1) if metrics_trusted else None
            display_bal_acc = float(bal_acc) if metrics_trusted else None
            display_baseline = float(baseline_acc) if metrics_trusted else float(min(1.0, baseline_acc))

            logger.info(
                "AI: Metrics train_acc=%.4f test_acc=%s macro_f1=%s bal_acc=%s baseline_majority=%s mode=%s",
                train_score,
                f"{display_test_score:.4f}" if display_test_score is not None else "<NON_VALID>",
                f"{display_macro_f1:.4f}" if display_macro_f1 is not None else "<NON_VALID>",
                f"{display_bal_acc:.4f}" if display_bal_acc is not None else "<NON_VALID>",
                f"{display_baseline:.4f}" if display_baseline is not None else "<NON_VALID>",
                evaluation_mode
            )
            logger.info("AI: Confusion matrix (labels=%s):\n%s", list(unique_labels), cm)

            # Simpan state/metrics
            self.trained = True
            self.model_trained_at = iso_now()
            self.accuracy = test_score if metrics_trusted else None
            self.last_metrics = {
                "status": status,
                "evaluation_mode": evaluation_mode,
                "metrics_trusted": metrics_trusted,
                "synthetic_used": synthetic_used,
                "warnings": warning_msgs,
                "train_accuracy": float(train_score),
                "test_accuracy": display_test_score,
                "macro_f1": display_macro_f1,
                "balanced_accuracy": display_bal_acc,
                "baseline_majority_accuracy": display_baseline,
                "confusion_matrix": cm.tolist(),
                "labels": list(unique_labels),
                "all_counts": all_counts,
                "train_counts": train_counts,
                "test_counts": test_counts,
            }

            # Model metadata for reproducibility / debugging
            self.model_meta = {
                'version': str(uuid.uuid4()),
                'training_seed': int(seed),
                'training_samples': int(len(y)),
                'training_samples_train': int(len(y_train)),
                'training_samples_test': int(len(y_test)),
                'synthetic_used': synthetic_used,
                'evaluation_mode': evaluation_mode,
                'metrics_trusted': metrics_trusted,
            }

            if not self.save_model():
                logger.error("AI: Failed to save model.")
                return False
            
            logger.info("AI model saved successfully")
            return True
            
        except Exception as e:
            logger.error(f"AI: Model training failed: {e}")
            return False
    
    def predict_weather(self, sensor_data):
        """Predict weather condition based on sensor data"""
        if not self.trained:
            return {
                'condition': 'Model not trained',
                'confidence': 0.0,
                'recommendations': ['Train the AI model first']
            }
        
        try:
            # Prepare features
            features = np.array([[
                sensor_data.get('temperature', 0),
                sensor_data.get('humidity', 0),
                sensor_data.get('air_quality', 0),
                sensor_data.get('light_intensity', 0),
                sensor_data.get('battery_voltage', 0)
            ]])
            
            # Scale features
            features_scaled = self.scaler.transform(features)
            
            # Make prediction
            prediction = self.model.predict(features_scaled)[0]
            prob_map = None
            confidence = 0.0
            if hasattr(self.model, 'predict_proba'):
                probabilities = self.model.predict_proba(features_scaled)[0]
                classes = self.model.classes_
                prob_map = {str(c): float(p) for c, p in zip(classes, probabilities)}
                # Pick top label and confidence
                top_label = max(prob_map, key=prob_map.get)
                confidence = float(prob_map.get(top_label, 0.0))
            else:
                # Fallback to model score-based confidence
                try:
                    probs = np.max(self.model.predict_proba(features_scaled), axis=1)
                    confidence = float(probs[0])
                except Exception:
                    confidence = 0.0

            # Get recommendations
            recommendations = self.get_recommendations(prediction, sensor_data)

            result = {
                'condition': prediction,
                'confidence': confidence,
                'probabilities': prob_map,
                'recommendations': recommendations
            }
            return result
        except Exception as e:
            logger.error(f"AI prediction failed: {e}")
            return {
                'condition': 'Prediction Error',
                'confidence': 0.0,
                'recommendations': ['AI model error occurred']
            }
    
    def get_recommendations(self, condition, sensor_data):
        """Get weather-based recommendations"""
        recommendations = []
        
        condition_recommendations = {
            "Cold": ["Wear warm clothing", "Consider indoor heating", "Protect pipes from freezing"],
            "Very Hot": ["Stay hydrated", "Avoid direct sun exposure", "Use air conditioning"],
            "Very Humid": ["Use dehumidifier", "Wear breathable clothing", "Check for mold"],
            "Polluted": ["Wear mask outdoors", "Use air purifier", "Limit outdoor activities"],
            "Hot Dry": ["Stay hydrated", "Use moisturizer", "Protect from sunburn"],
            "Hot Humid": ["Stay in air conditioning", "Wear light clothing", "Watch for heat exhaustion"],
            "Cool Humid": ["Wear light layers", "Use umbrella if needed", "Check for dampness"],
            "Normal": ["Great weather for activities", "Perfect conditions for exercise", "Enjoy outdoors"]
        }
        
        recommendations.extend(condition_recommendations.get(condition, ["Weather conditions normal"]))
        
        # Air quality recommendations
        air_quality = sensor_data.get('air_quality', 0)
        if air_quality > 400:
            recommendations.append("Hazardous air quality - stay indoors")
        elif air_quality > 300:
            recommendations.append("Very unhealthy air - avoid outdoor activities")
        elif air_quality > 200:
            recommendations.append("Unhealthy air - limit outdoor exercise")
        elif air_quality > 100:
            recommendations.append("Moderate air quality - sensitive groups should limit exposure")
        
        # Temperature recommendations
        temp = sensor_data.get('temperature', 0)
        if temp > 35:
            recommendations.append("Extreme heat - seek immediate cooling")
        elif temp < 5:
            recommendations.append("Freezing conditions - take winter precautions")
        
        return recommendations[:5]  # Limit to 5 recommendations

# Fuzzy + short-horizon forecast engine (rule-based, trainable ML remains optional)
class FuzzyForecastEngine:
    def __init__(self):
        self.light_bins = [
            ("Gelap", 0, 50),
            ("Mendung", 50, 1000),
            ("Berawan", 1000, 10000),
            ("Cerah", 10000, 50000),
            ("Terik", 50000, float("inf")),
        ]

    def _to_float(self, value, default=0.0):
        try:
            return float(value)
        except Exception:
            return default

    def classify_light(self, lux: float) -> str:
        for name, lo, hi in self.light_bins:
            if lux >= lo and lux < hi:
                return name
        return "Cerah"

    def rain_probability(self, temp_c: float, humidity: float, lux: float) -> float:
        # Normalized scores (0..1)
        humidity_score = min(1.0, max(0.0, (humidity - 55.0) / 45.0))
        light_score = min(1.0, max(0.0, (10000.0 - lux) / 10000.0))
        temp_score = min(1.0, max(0.0, (temp_c - 28.0) / 12.0))

        risk = 0.55 * humidity_score + 0.35 * light_score + 0.10 * temp_score
        light_label = self.classify_light(lux)
        if light_label == "Terik":
            risk *= 0.6
        elif light_label == "Gelap":
            risk = min(1.0, risk * 1.15)
        return min(1.0, max(0.0, risk)) * 100.0

    def weather_type(self, rain_prob: float, lux: float) -> str:
        if rain_prob >= 70:
            return "Hujan"
        if lux < 1000:
            return "Mendung"
        if lux < 10000:
            return "Berawan"
        return "Cerah"

    def recommendation(self, weather_type: str, temp_c: float, humidity: float, air_quality: float) -> str:
        tips = []
        if weather_type == "Hujan":
            tips.append("Bawa payung/jas hujan")
        elif weather_type == "Mendung":
            tips.append("Siapkan payung")
        elif weather_type == "Berawan":
            tips.append("Perhatikan kemungkinan hujan, siapkan payung")
        else:
            if temp_c >= 32:
                tips.append("Gunakan sunscreen & topi bila di luar")
            else:
                tips.append("Cuaca cerah, cocok beraktivitas")

        if air_quality >= 200:
            tips.append("Gunakan masker jika di luar")
        if humidity >= 85 and weather_type != "Hujan":
            tips.append("Udara lembap, kurangi aktivitas berat")

        return " / ".join(tips[:2]) if tips else "Pantau kondisi cuaca"

    def _fit_linear(self, series):
        """
        Fit y = a*x + b, where x is minutes relative to now (x=0 at now).
        series: list[(dt_utc, y_float)]
        """
        if len(series) < 3:
            return None
        series = sorted(series, key=lambda it: it[0])
        t0 = series[-1][0]
        xs = []
        ys = []
        for ts, y in series[-30:]:
            x = (ts - t0).total_seconds() / 60.0
            xs.append(x)
            ys.append(y)
        if not xs or (max(xs) - min(xs) > -0.5 and max(xs) - min(xs) < 0.5):
            return None
        try:
            a, b = np.polyfit(np.array(xs, dtype=float), np.array(ys, dtype=float), 1)
            return float(a), float(b)
        except Exception:
            return None

    def forecast_3h(self, latest: dict, history: list) -> dict:
        # Base timestamp
        base_ts = parse_sensor_timestamp(latest.get("timestamp")) or datetime.now(timezone.utc)
        if base_ts.tzinfo is None:
            base_ts = base_ts.replace(tzinfo=timezone.utc)
        base_ts_utc = base_ts.astimezone(timezone.utc)

        temp_now = self._to_float(latest.get("temperature"))
        hum_now = self._to_float(latest.get("humidity"))
        air_now = self._to_float(latest.get("air_quality"))
        lux_now = self._to_float(latest.get("light_intensity"))

        # Collect recent series (prefer last 30 minutes)
        series_temp = []
        series_hum = []
        series_lux = []
        cutoff = base_ts_utc - timedelta(minutes=30)
        for item in history[-200:]:
            if not isinstance(item, dict):
                continue
            ts = parse_sensor_timestamp(item.get("timestamp"))
            if not ts:
                continue
            if ts.tzinfo is None:
                ts = ts.replace(tzinfo=timezone.utc)
            ts = ts.astimezone(timezone.utc)
            if ts < cutoff or ts > base_ts_utc:
                continue
            series_temp.append((ts, self._to_float(item.get("temperature"), temp_now)))
            series_hum.append((ts, self._to_float(item.get("humidity"), hum_now)))
            series_lux.append((ts, self._to_float(item.get("light_intensity"), lux_now)))

        fit_temp = self._fit_linear(series_temp)
        fit_hum = self._fit_linear(series_hum)
        fit_lux = self._fit_linear(series_lux)

        def predict_val(now_val, fit, horizon_minutes, clamp_lo=None, clamp_hi=None):
            if not fit:
                v = now_val
            else:
                a, b = fit
                v = b + a * float(horizon_minutes)
            if clamp_lo is not None:
                v = max(clamp_lo, v)
            if clamp_hi is not None:
                v = min(clamp_hi, v)
            return float(v)

        history_factor = min(1.0, max(0.0, len(series_temp) / 12.0))
        base_conf = 0.62 + 0.22 * history_factor

        hourly = []
        predicted_rain_time = None
        for h in (1, 2, 3):
            horizon_min = h * 60
            t_pred = base_ts_utc + timedelta(hours=h)
            t_val = predict_val(temp_now, fit_temp, horizon_min, clamp_lo=-10, clamp_hi=60)
            h_val = predict_val(hum_now, fit_hum, horizon_min, clamp_lo=0, clamp_hi=100)
            l_val = predict_val(lux_now, fit_lux, horizon_min, clamp_lo=0, clamp_hi=200000)

            rain_prob = self.rain_probability(t_val, h_val, l_val)
            w_type = self.weather_type(rain_prob, l_val)
            conf = max(0.0, min(1.0, base_conf - 0.08 * h))

            if predicted_rain_time is None and rain_prob >= 60:
                predicted_rain_time = iso_from_dt(t_pred)

            hourly.append({
                "timestamp": iso_from_dt(t_pred),
                "weather_type": w_type,
                "rain_probability": round(rain_prob, 1),
                "confidence": round(conf, 3),
                "light_label": self.classify_light(l_val),
                "temperature": round(t_val, 2),
                "humidity": round(h_val, 2),
                "light_intensity": round(l_val, 2),
            })

        rain_now = self.rain_probability(temp_now, hum_now, lux_now)
        w_now = self.weather_type(rain_now, lux_now)
        now_payload = {
            "timestamp": iso_from_dt(base_ts_utc),
            "weather_type": w_now,
            "rain_probability": round(rain_now, 1),
            "confidence": round(base_conf, 3),
            "light_label": self.classify_light(lux_now),
            "temperature": round(temp_now, 2),
            "humidity": round(hum_now, 2),
            "light_intensity": round(lux_now, 2),
        }

        return {
            "now": now_payload,
            "hourly_forecast": hourly,
            "predicted_rain_time": predicted_rain_time,
            "primary_recommendation": self.recommendation(w_now, temp_now, hum_now, air_now),
        }


forecast_engine = FuzzyForecastEngine()

# Initialize AI model
weather_ai = WeatherAIModel()

# Data storage
local_data = []
last_prediction = None
prediction_history = []  # in-memory rolling buffer of recent predictions
last_esp32_seen_at = None
last_esp32_device_id = None
latest_by_device = {}

# Training state (manual only)
ai_training_in_progress = False
ai_training_lock = threading.Lock()


# AI readiness thresholds
MIN_AI_TRAIN_DATA = 50
MIN_PREDICTION_DATA = 10
ENABLE_AUTO_PREDICTION = False
# If dataset is single-class but has many samples, allow auto force-training (will augment synthetically and mark evaluation NON_VALID)
ALLOW_AUTO_TRAIN_SINGLE_CLASS_THRESHOLD = 100


def get_label_distribution(data_points):
    """Ambil distribusi label rule-based dari data sensor yang ada."""
    if not data_points:
        return {}
    try:
        _, y, _ = weather_ai.prepare_training_data(data_points)
        labels, counts = np.unique(y, return_counts=True)
        return {lbl: int(cnt) for lbl, cnt in zip(labels, counts)}
    except Exception:
        return {}


def ai_ready_for_training():
    """True jika data sensor sudah cukup untuk training manual."""
    if len(local_data) < MIN_AI_TRAIN_DATA:
        return False, {
            "reason": "data_below_min",
            "min_required": MIN_AI_TRAIN_DATA,
            "count": len(local_data),
            "distribution": get_label_distribution(local_data),
        }

    dist = get_label_distribution(local_data)
    if len(dist.keys()) < 2:
        # If single-class but plenty of samples, allow auto-force training with warning.
        allow_threshold = config.get('ALLOW_AUTO_TRAIN_SINGLE_CLASS_THRESHOLD', ALLOW_AUTO_TRAIN_SINGLE_CLASS_THRESHOLD)
        if len(local_data) >= allow_threshold:
            return True, {
                "reason": "single_class_auto_allowed",
                "auto_force": True,
                "count": len(local_data),
                "distribution": dist,
                "message": f"Single-class data but >={allow_threshold} samples; server will allow training with synthetic augmentation (evaluation NON_VALID)."
            }
        return False, {
            "reason": "single_class",
            "count": len(local_data),
            "distribution": dist,
        }
    if any(v < 2 for v in dist.values()):
        return False, {
            "reason": "class_too_small",
            "count": len(local_data),
            "distribution": dist,
        }
    return True, {
        "reason": "ready",
        "count": len(local_data),
        "min_required": MIN_AI_TRAIN_DATA,
        "distribution": dist,
    }


def get_esp32_connection_state():
    threshold = client_settings.get('esp32_offline_seconds', 15)
    try:
        threshold = int(threshold)
    except (TypeError, ValueError):
        threshold = 15
    if threshold < 1:
        threshold = 1

    if not last_esp32_seen_at:
        return False, None
    last_seen = normalize_ts(last_esp32_seen_at)
    elapsed = (datetime.utcnow() - last_seen).total_seconds()
    # expose as ISO UTC (Z) to frontend
    try:
        return elapsed <= threshold, iso_from_dt(last_seen.replace(tzinfo=timezone.utc))
    except Exception:
        return elapsed <= threshold, iso_now()


def parse_sensor_timestamp(value):
    if not value:
        return None
    try:
        if isinstance(value, (int, float)):
            return datetime.utcfromtimestamp(value)
        if isinstance(value, str):
            if value.isdigit():
                return datetime.utcfromtimestamp(int(value))
            try:
                return datetime.fromisoformat(value.replace('Z', '+00:00'))
            except ValueError:
                pass
            for fmt in (
                '%d/%m/%Y, %H.%M.%S',
                '%d/%m/%Y, %H:%M:%S',
                '%d/%m/%Y %H:%M:%S',
                '%Y-%m-%d %H:%M:%S',
                '%Y/%m/%d %H:%M:%S'
            ):
                try:
                    return datetime.strptime(value, fmt)
                except ValueError:
                    continue
    except Exception:
        return None
    return None

def normalize_ts(ts):
    """Normalisasi datetime ke UTC naive agar perbandingan konsisten."""
    if not ts:
        return None
    if ts.tzinfo is not None:
        return ts.astimezone(timezone.utc).replace(tzinfo=None)
    return ts


def validate_and_normalize_sensor_payload(payload: dict):
    """Validate sensor payload, detect unit issues (milli), clamp/outlier detection.

    Returns (normalized_payload, warnings_list, invalid_reasons_list)
    """
    warnings = []
    invalids = []
    data = payload.copy()

    # Prefer explicit fields if provided
    if 'temp_c' in data and 'temperature' not in data:
        data['temperature'] = data.get('temp_c')
    if 'temp_milli' in data and 'temperature' not in data:
        try:
            data['temperature'] = float(data.get('temp_milli')) / 1000.0
            warnings.append('temperature converted from milli')
        except Exception:
            invalids.append('temp_milli invalid')

    # Numeric coercion (caller will perform basic float conversion but we double-check ranges)
    def safe_float(val):
        try:
            return float(val)
        except Exception:
            return None

    for k in ['temperature', 'humidity', 'air_quality', 'light_intensity', 'battery_voltage', 'battery_current', 'battery_power']:
        if k in data:
            v = safe_float(data.get(k))
            data[k] = v

    # Detect milli-units (heuristic)
    t = data.get('temperature')
    if t is not None:
        if abs(t) > 1000:
            data['temperature'] = t / 1000.0
            warnings.append('temperature appeared in milli, converted')
        if data['temperature'] < -50 or data['temperature'] > 80:
            warnings.append('temperature out-of-range')

    h = data.get('humidity')
    if h is not None:
        if h > 1000:
            data['humidity'] = h / 1000.0
            warnings.append('humidity appeared in milli, converted')
        if data['humidity'] < 0 or data['humidity'] > 100:
            warnings.append('humidity out-of-range')

    aq = data.get('air_quality')
    if aq is not None:
        if aq > 100000:
            data['air_quality'] = aq / 1000.0
            warnings.append('air_quality appeared in milli, converted')
        if data['air_quality'] < 0:
            warnings.append('air_quality negative')

    bv = data.get('battery_voltage')
    if bv is not None:
        if bv > 100:
            data['battery_voltage'] = bv / 1000.0
            warnings.append('battery_voltage appeared in milli, converted')
        if data['battery_voltage'] < 0 or data['battery_voltage'] > 20:
            warnings.append('battery_voltage out-of-range')

    # GPS check
    lat = data.get('lat') or data.get('latitude')
    lon = data.get('lon') or data.get('longitude')
    if lat is not None and lon is not None:
        try:
            latf = float(lat)
            lonf = float(lon)
            if abs(latf) > 90 or abs(lonf) > 180:
                warnings.append('gps out-of-range')
            else:
                data['latitude'] = latf
                data['longitude'] = lonf
        except Exception:
            warnings.append('gps parse error')

    return data, warnings, invalids


def update_last_seen_from_reading(reading):
    global last_esp32_seen_at
    if not reading or not isinstance(reading, dict):
        return
    ts = normalize_ts(parse_sensor_timestamp(reading.get('timestamp')))
    if not ts:
        return
    if last_esp32_seen_at:
        last_esp32_seen_at = normalize_ts(last_esp32_seen_at)
    if not last_esp32_seen_at or ts > last_esp32_seen_at:
        last_esp32_seen_at = ts


# Firebase helper functions
def build_firebase_url(path):
    """Build a valid Firebase REST URL including query parameters."""
    base_url = firebase_config['databaseURL'].rstrip('/')
    clean_path = (path or '').lstrip('/')

    # Remove trailing .json if caller accidentally includes it
    if clean_path.endswith('.json'):
        clean_path = clean_path[:-5]

    if '?' in clean_path:
        path_part, query_part = clean_path.split('?', 1)
        safe_query = query_part.replace('"', '%22')
        return f"{base_url}/{path_part}.json?{safe_query}"

    return f"{base_url}/{clean_path}.json"


def send_to_firebase(path, data):
    """Send data to Firebase using REST API"""
    global current_status
    
    if not firebase_initialized:
        return None
    
    try:
        url = build_firebase_url(path)
        response = requests.post(url, json=data, timeout=config.get('REQUEST_TIMEOUT'))
        if response.status_code == 200:
            # Firebase is working - broadcast status change if needed
            if not current_status.get('firebase_connected', False):
                broadcast_status_change('firebase', True)
            return response.json()
        else:
            logger.warning(f"Firebase write failed with status: {response.status_code}")
            # Firebase failed - broadcast status change if needed
            if current_status.get('firebase_connected', False):
                broadcast_status_change('firebase', False)
            return None
    except Exception as e:
        logger.error(f"Firebase write error: {e}")
        # Firebase error - broadcast status change if needed
        if current_status.get('firebase_connected', False):
            broadcast_status_change('firebase', False)
        return None

def get_from_firebase(path):
    """Get data from Firebase using REST API"""
    global current_status
    
    if not firebase_initialized:
        return None
    
    try:
        url = build_firebase_url(path)
        response = requests.get(url, timeout=config.get('REQUEST_TIMEOUT'))
        if response.status_code == 200:
            # Firebase is working - broadcast status change if needed
            if not current_status.get('firebase_connected', False):
                broadcast_status_change('firebase', True)
            return response.json()
        else:
            logger.warning(f"Firebase read failed with status: {response.status_code}")
            # Firebase failed - broadcast status change if needed
            if current_status.get('firebase_connected', False):
                broadcast_status_change('firebase', False)
            return None
    except Exception as e:
        logger.error(f"Firebase read error: {e}")
        # Firebase error - broadcast status change if needed
        if current_status.get('firebase_connected', False):
            broadcast_status_change('firebase', False)
        return None

# Data backup functions
def backup_data():
    """Backup data to file"""
    try:
        global local_data, last_prediction
        backup_dir = Path(config.get('DATA_DIR')) / 'backups'
        backup_dir.mkdir(parents=True, exist_ok=True)
        backup_file = backup_dir / f"backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        
        backup_data = {
            'timestamp': iso_now(),
            'local_data': local_data.copy() if local_data else [],
            'last_prediction': last_prediction,
            'config': config.config
        }
        
        with open(backup_file, 'w') as f:
            json.dump(backup_data, f, indent=2)
        
        logger.info(f"Data backed up to {backup_file}")
        
        # Keep only last 10 backups
        backup_files = sorted(backup_dir.glob("backup_*.json"))
        if len(backup_files) > 10:
            for old_backup in backup_files[:-10]:
                old_backup.unlink()
                logger.info(f"Removed old backup: {old_backup}")
        
        return True
    except Exception as e:
        logger.error(f"Backup failed: {e}")
        return False

def restore_data():
    """Restore data from latest backup"""
    try:
        backup_dir = Path(config.get('DATA_DIR')) / 'backups'
        backup_files = sorted(backup_dir.glob("backup_*.json"))
        
        if not backup_files:
            logger.info("No backup files found")
            return False
        
        latest_backup = backup_files[-1]
        with open(latest_backup, 'r') as f:
            backup_data = json.load(f)
        
        global local_data, last_prediction
        local_data = backup_data.get('local_data', [])
        last_prediction = backup_data.get('last_prediction')
        
        logger.info(f"Data restored from {latest_backup}")
        return True
    except Exception as e:
        logger.error(f"Restore failed: {e}")
        return False

# Background tasks
def background_tasks():
    """Run background tasks"""
    global local_data, last_prediction
    while True:
        try:
            # Backup data
            backup_data()
            
            # Clean old data
            if len(local_data) > config.get('MAX_LOCAL_READINGS'):
                old_data = local_data[:-config.get('MAX_LOCAL_READINGS')]
                local_data = local_data[-config.get('MAX_LOCAL_READINGS'):]
                logger.info(f"Cleaned {len(old_data)} old data points")
            
            # Health check
            logger.info(f"Health check - Data points: {len(local_data)}, AI trained: {weather_ai.trained}")
            
        except Exception as e:
            logger.error(f"Background task error: {e}")
        
        time.sleep(config.get('BACKUP_INTERVAL'))


def get_current_status():
    """Get current system status"""
    global current_status

    current_status['server_connected'] = True
    current_status['server_status'] = 'online'
    current_status['firebase_enabled'] = bool(firebase_initialized)
    
    if local_data:
        update_last_seen_from_reading(local_data[-1])
        try:
            ts = parse_sensor_timestamp(local_data[-1].get('timestamp')) if isinstance(local_data[-1], dict) else None
            if ts:
                current_status['last_update'] = iso_from_dt(ts)
        except Exception:
            pass
    
    # Update ESP32 status based on real-time check
    esp32_connected, esp32_last_seen = get_esp32_connection_state()
    if current_status['esp32_connected'] != esp32_connected:
        current_status['esp32_connected'] = esp32_connected
        current_status['esp32_last_seen'] = esp32_last_seen
    
    # Update Firebase status based on real-time check
    firebase_connected = get_firebase_connection_state() if firebase_initialized else False
    if current_status['firebase_connected'] != firebase_connected:
        current_status['firebase_connected'] = firebase_connected
        current_status['data_source'] = 'Firebase Real-time' if firebase_connected else 'Local'

    return current_status.copy()


def monitor_esp32_connection():
    """Monitor ESP32 connection independent from data update interval."""
    while True:
        try:
            if firebase_initialized:
                latest = get_from_firebase('/sensor_data?orderBy="$key"&limitToLast=1')
                if isinstance(latest, dict):
                    for _, reading in latest.items():
                        update_last_seen_from_reading(reading)
            esp32_connected, esp32_last_seen = get_esp32_connection_state()
            previous = current_status.get('esp32_connected', False)
            if esp32_connected != previous:
                broadcast_status_change('esp32', esp32_connected, {'last_seen': esp32_last_seen})
        except Exception as exc:
            logger.error(f"ESP32 monitor error: {exc}")

        threshold = client_settings.get('esp32_offline_seconds', 15)
        try:
            threshold = int(threshold)
        except (TypeError, ValueError):
            threshold = 15
        check_interval = max(1, min(config.get('HEALTH_CHECK_INTERVAL', 60), max(2, int(threshold / 2))))
        time.sleep(check_interval)


def monitor_firebase_connection():
    """Monitor Firebase connection independent from data update interval."""
    while True:
        try:
            firebase_connected = get_firebase_connection_state() if firebase_initialized else False
            previous = current_status.get('firebase_connected', False)
            if firebase_connected != previous:
                broadcast_status_change('firebase', firebase_connected)
        except Exception as exc:
            logger.error(f"Firebase monitor error: {exc}")

        time.sleep(config.get('HEALTH_CHECK_INTERVAL', 60))


def status_heartbeat_loop():
    """Emit status updates every second for real-time clock display."""
    while True:
        try:
            socketio.emit('status_update', get_current_status())
        except Exception as exc:
            logger.error(f"Status heartbeat error: {exc}")
        time.sleep(1)

# Start background tasks
background_thread = threading.Thread(target=background_tasks, daemon=True)
background_thread.start()

# Start monitoring threads
esp32_monitor_thread = threading.Thread(target=monitor_esp32_connection, daemon=True)
esp32_monitor_thread.start()

firebase_monitor_thread = threading.Thread(target=monitor_firebase_connection, daemon=True)
firebase_monitor_thread.start()

status_heartbeat_thread = threading.Thread(target=status_heartbeat_loop, daemon=True)
status_heartbeat_thread.start()

# Initialize current status
current_status['firebase_connected'] = get_firebase_connection_state() if firebase_initialized else False
current_status['data_source'] = 'Firebase Real-time' if current_status['firebase_connected'] else 'Local'
esp32_connected, esp32_last_seen = get_esp32_connection_state()
current_status['esp32_connected'] = esp32_connected
current_status['esp32_last_seen'] = esp32_last_seen

# API Routes
@app.route('/')
def home():
    """Server information"""
    return jsonify({
        "message": "Weather Station Backend API",
        "version": "3.0",
        "status": "running",
        "server_ip": SERVER_IP,
        "port": config.get('PORT'),
        "firebase": firebase_initialized,
        "ai_model": weather_ai.trained,
        "data_points": len(local_data),
        "uptime": iso_now(),
        "endpoints": [
            "/api/sensor-data (POST)",
            "/api/dashboard-stats (GET)",
            "/api/historical-data (GET)",
            "/api/predictions (GET)",
            "/api/train-model (POST)",
            "/api/test-firebase (GET)",
            "/api/health (GET)",
            "/api/config (GET)",
            "/api/backup (POST)",
            "/api/restore (POST)"
        ]
    })

@app.route('/api/health')
def health_check():
    """Health check endpoint"""
    # best-effort storage check (tanpa menulis file permanen)
    storage_ok = True
    try:
        Path(config.get('DATA_DIR')).mkdir(parents=True, exist_ok=True)
        Path(config.get('LOG_FILE')).parent.mkdir(parents=True, exist_ok=True)
    except Exception:
        storage_ok = False

    return jsonify({
        "status": "ok",
        "version": APP_VERSION,
        "time": iso_now(),
        "firebase_enabled": bool(firebase_initialized),
        "firebase_connected": bool(current_status.get('firebase_connected', False)),
        "model_loaded": bool(getattr(weather_ai, 'trained', False)),
        "storage_ok": storage_ok,
        # backward-compatible fields
        "timestamp": iso_now(),
        "server_ip": SERVER_IP,
        "data_points": len(local_data),
        "ai_model": weather_ai.trained,
        "firebase": firebase_initialized,
        "memory_usage": f"{sys.getsizeof(local_data) / 1024:.2f} KB"
    })

@app.route('/api/status')
def get_status():
    """Get real-time status independent of update interval"""
    status = get_current_status()
    status['client_settings'] = client_settings
    return jsonify(status)

@app.route('/api/config')
def get_config():
    """Get current configuration"""
    return jsonify({
        "config": config.config,
        "client_settings": client_settings,
        "firebase_configured": bool(firebase_config.get('databaseURL')),
        "server_info": {
            "ip": SERVER_IP,
            "port": config.get('PORT'),
            "version": "3.0"
        }
    })

@app.route('/api/client-settings', methods=['GET', 'POST'])
def client_settings_endpoint():
    """Kelola pengaturan dashboard client (interval & auto refresh)"""
    global client_settings
    
    if request.method == 'GET':
        return jsonify({"settings": client_settings})
    
    payload = request.get_json() or {}
    new_interval = payload.get('update_interval', client_settings.get('update_interval'))
    new_auto_refresh = payload.get('auto_refresh', client_settings.get('auto_refresh', True))
    new_offline_seconds = payload.get('esp32_offline_seconds', client_settings.get('esp32_offline_seconds', 15))
    
    try:
        new_interval = int(new_interval)
    except (TypeError, ValueError):
        return jsonify({"error": "update_interval harus berupa angka"}), 400
    
    if new_interval < 1 or new_interval > 120:
        return jsonify({"error": "update_interval harus antara 1-120 detik"}), 400

    try:
        new_offline_seconds = int(new_offline_seconds)
    except (TypeError, ValueError):
        return jsonify({"error": "esp32_offline_seconds harus berupa angka"}), 400

    if new_offline_seconds < 1 or new_offline_seconds > 600:
        return jsonify({"error": "esp32_offline_seconds harus antara 1-600 detik"}), 400
    
    if isinstance(new_auto_refresh, str):
        new_auto_refresh = new_auto_refresh.lower() == 'true'
    else:
        new_auto_refresh = bool(new_auto_refresh)
    
    with client_settings_lock:
        client_settings['update_interval'] = new_interval
        client_settings['auto_refresh'] = new_auto_refresh
        client_settings['esp32_offline_seconds'] = new_offline_seconds
        client_settings['updated_at'] = iso_now()
        save_client_settings(client_settings)
    
    broadcast_client_settings()
    logger.info(
        "Client settings diperbarui: interval=%ss, auto_refresh=%s, esp32_offline_seconds=%ss",
        new_interval,
        new_auto_refresh,
        new_offline_seconds
    )
    return jsonify({"settings": client_settings})

@app.route('/api/sensor-data', methods=['POST'])
def receive_sensor_data():
    """Receive sensor data from ESP32"""
    try:
        sensor_reading = request.get_json(silent=True)
        
        # Persist raw payload (one JSON line) for debugging
        try:
            RAW_PAYLOAD_LOG.parent.mkdir(parents=True, exist_ok=True)
            with open(RAW_PAYLOAD_LOG, 'a', encoding='utf-8') as rf:
                rf.write(json.dumps({
                    'received_at': iso_now(),
                    'raw': sensor_reading
                }, ensure_ascii=False) + "\n")
        except Exception as exc:
            logger.warning(f"Failed to append raw payload log: {exc}")
        
        if not sensor_reading:
            logger.warning("No data received in POST request")
            return jsonify({"error": "No data received"}), 400
        
        if not isinstance(sensor_reading, dict):
            return jsonify({"error": "Body harus berupa objek JSON"}), 400

        # Validate required fields
        required_fields = [
            'device_id', 'temperature', 'humidity', 'air_quality',
            'light_intensity', 'battery_voltage'
        ]
        missing_fields = [field for field in required_fields if field not in sensor_reading]
        if missing_fields:
            logger.warning(f"Missing required fields: {missing_fields}")
            return jsonify({"error": f"Missing required fields: {missing_fields}"}), 400

        # Normalize keys and values (basic coercion)
        # Additional validation and normalization follows later

        device_id = str(sensor_reading.get('device_id') or '').strip()
        if not _is_valid_device_id(device_id):
            return jsonify({"error": "device_id tidak valid"}), 400

        # Normalize sensor keys used in UI (alias device payload names)
        if 'voltage' in sensor_reading and 'battery_voltage' not in sensor_reading:
            sensor_reading['battery_voltage'] = sensor_reading.get('voltage')
        if 'current' in sensor_reading and 'battery_current' not in sensor_reading:
            sensor_reading['battery_current'] = sensor_reading.get('current')
        if 'power' in sensor_reading and 'battery_power' not in sensor_reading:
            sensor_reading['battery_power'] = sensor_reading.get('power')

        # Basic numeric coercion (we'll do more validation below)
        numeric_fields = [
            'temperature', 'humidity', 'air_quality',
            'light_intensity', 'battery_voltage'
        ]
        for field in numeric_fields:
            try:
                sensor_reading[field] = float(sensor_reading.get(field))
            except (TypeError, ValueError):
                return jsonify({"error": f"{field} harus berupa angka"}), 400

        optional_numeric = ['battery_current', 'battery_power']
        for field in optional_numeric:
            if field in sensor_reading:
                try:
                    sensor_reading[field] = float(sensor_reading.get(field))
                except (TypeError, ValueError):
                    sensor_reading[field] = None

        # Add/normalize timestamp (client expects ISO UTC Z)
        if 'timestamp' not in sensor_reading:
            sensor_reading['timestamp'] = iso_now()
        else:
            parsed_ts = parse_sensor_timestamp(sensor_reading.get('timestamp'))
            sensor_reading['timestamp'] = iso_from_dt(parsed_ts) if parsed_ts else iso_now()

        # Run detailed validation and normalization
        normalized, warnings, invalids = validate_and_normalize_sensor_payload(sensor_reading)
        if invalids:
            logger.warning(f"Invalid sensor payload: {invalids}")
            # Append normalized + warnings to debug log as well
            try:
                with open(RAW_PAYLOAD_LOG, 'a', encoding='utf-8') as rf:
                    rf.write(json.dumps({
                        'received_at': iso_now(),
                        'device_id': device_id,
                        'raw': sensor_reading,
                        'normalized': normalized,
                        'warnings': warnings,
                        'invalids': invalids
                    }, ensure_ascii=False) + "\n")
            except Exception:
                pass
            return jsonify({"error": "Payload invalid", "details": invalids}), 400

        # If warnings exist, keep the reading but log them
        if warnings:
            logger.warning(f"Sensor payload warnings for device {device_id}: {warnings}")
            try:
                with open(RAW_PAYLOAD_LOG, 'a', encoding='utf-8') as rf:
                    rf.write(json.dumps({
                        'received_at': iso_now(),
                        'device_id': device_id,
                        'raw': sensor_reading,
                        'normalized': normalized,
                        'warnings': warnings
                    }, ensure_ascii=False) + "\n")
            except Exception:
                pass

        # Use normalized payload moving forward
        sensor_reading.update(normalized)

        global last_esp32_seen_at, last_esp32_device_id
        previous_esp32_connected = current_status.get('esp32_connected', False)
        
        last_esp32_seen_at = datetime.utcnow()
        last_esp32_device_id = device_id

        # Cache latest reading per device (untuk kebutuhan dashboard/admin)
        latest_by_device[device_id] = sensor_reading.copy()
        
        # Check if ESP32 status changed and broadcast if needed
        esp32_connected, esp32_last_seen = get_esp32_connection_state()
        if esp32_connected != previous_esp32_connected:
            broadcast_status_change('esp32', esp32_connected, {'last_seen': esp32_last_seen})
        
        # Store in local memory
        local_data.append(sensor_reading.copy())

        # Emit realtime update ke dashboard (jalur utama, tanpa Firebase)
        socketio.emit('sensor_update', sensor_reading)
        
        # Store in Firebase if available
        data_id = None
        if firebase_initialized:
            try:
                result = send_to_firebase('/sensor_data', sensor_reading)
                if result:
                    data_id = result.get('name')
                    logger.info(f"Data stored in Firebase with ID: {data_id}")
                else:
                    logger.warning("Firebase storage failed - using local only")
            except Exception as firebase_error:
                logger.error(f"Firebase storage error: {firebase_error}")
        
        logger.debug(
            "Sensor data diterima: device=%s T=%s H=%s AQ=%s Lux=%s",
            device_id,
            sensor_reading.get('temperature'),
            sensor_reading.get('humidity'),
            sensor_reading.get('air_quality'),
            sensor_reading.get('light_intensity'),
        )
        
        prediction = None
        if ENABLE_AUTO_PREDICTION and len(local_data) >= MIN_PREDICTION_DATA:
            # Generate prediction payload (fuzzy forecast is always available; ML remains optional)
            ml_prediction = weather_ai.predict_weather(sensor_reading) if weather_ai else {"condition": None, "confidence": 0.0, "recommendations": []}
            forecast = forecast_engine.forecast_3h(sensor_reading, local_data)

            prediction = {
                "timestamp": sensor_reading.get("timestamp") or iso_now(),
                "condition": forecast.get("now", {}).get("weather_type", "N/A"),
                "confidence": float(forecast.get("now", {}).get("confidence", 0.0)),
                "weather_type": forecast.get("now", {}).get("weather_type", "N/A"),
                "sky_now": forecast.get("now", {}).get("light_label", None),
                "rain_probability": float(forecast.get("now", {}).get("rain_probability", 0.0)),
                "predicted_rain_time": forecast.get("predicted_rain_time"),
                "hourly_forecast": forecast.get("hourly_forecast", []),
                "primary_recommendation": forecast.get("primary_recommendation", "Pantau kondisi cuaca"),
                "recommendations": [forecast.get("primary_recommendation", "Pantau kondisi cuaca")],
                "ml_condition": ml_prediction.get("condition"),
                "ml_confidence": float(ml_prediction.get("confidence", 0.0) or 0.0),
                "ml_recommendations": ml_prediction.get("recommendations", []),
            }

            global last_prediction, prediction_history
            last_prediction = prediction
            # Append to in-memory prediction history (trim to config)
            prediction_history.append(prediction)
            max_hist = int(config.get('MAX_PREDICTION_HISTORY', 50))
            while len(prediction_history) > max_hist:
                prediction_history.pop(0)
            logger.info(
                "Generated prediction: %s (rain=%.1f%%, conf=%.2f)",
                prediction.get("weather_type", "N/A"),
                prediction.get("rain_probability", 0.0),
                prediction.get("confidence", 0.0)
            )
        
        # Store prediction in Firebase if available
        if firebase_initialized and prediction is not None:
            try:
                prediction_data = prediction.copy()
                prediction_data["sensor_data_id"] = data_id
                 
                pred_result = send_to_firebase('/predictions', prediction_data)
                if pred_result:
                    logger.info("AI prediction stored in Firebase")
            except Exception as firebase_error:
                logger.error(f"Firebase prediction storage error: {firebase_error}")
        
        # Training AI manual saja (dipicu via endpoint /api/train-model)
        
        return jsonify({
            "status": "ok",
            "message": "Data diterima",
            "data_id": data_id or f"local_{len(local_data)}",
            "ai_prediction": prediction,
            "ai_ready": ai_ready_for_training()[0],
            "firebase_available": firebase_initialized,
            "storage_method": "firebase" if data_id else "local",
            "server_info": {
                "ip": SERVER_IP,
                "port": config.get('PORT')
            }
        })
        
    except Exception as e:
        logger.error(f"Error processing sensor data: {e}")
        return jsonify({"error": str(e)}), 500

@app.route('/api/dashboard-stats', methods=['GET'])
def get_dashboard_stats():
    """Get dashboard statistics"""
    try:
        # Get latest reading from local data
        latest_reading = None
        if local_data:
            latest_reading = local_data[-1]

        # Get current real-time status
        status = get_current_status()
        
        # Initialize stats with local data
        stats = {
            "total_readings": len(local_data),
            "model_trained": weather_ai.trained,
            "ai_ready": ai_ready_for_training()[0],
            "last_reading": latest_reading,
            "last_prediction": last_prediction,
            "firebase_available": status['firebase_connected'],
            "esp32_connected": status['esp32_connected'],
            "esp32_last_seen": status['esp32_last_seen'],
            "model_trained_at": weather_ai.model_trained_at,
            "system_status": "running",
            "data_source": status['data_source'],
            "client_settings": client_settings,
            "server_info": {
                "ip": SERVER_IP,
                "port": config.get('PORT'),
                "uptime": iso_now()
            }
        }
        
        # Try to get Firebase data if available and connected
        if status['firebase_connected']:
            try:
                # Get sensor data from Firebase
                sensor_data = get_from_firebase(f'/sensor_data?limitToLast={config.get("MAX_FIREBASE_READINGS")}')
                
                if sensor_data and isinstance(sensor_data, dict):
                    firebase_count = len(sensor_data)
                    
                    if firebase_count > 0:
                        stats["total_readings"] = firebase_count
                        stats["data_source"] = "firebase"
                        
                        # Get latest reading from Firebase
                        latest_firebase_reading = None
                        latest_timestamp = 0
                        
                        for key, value in sensor_data.items():
                            if isinstance(value, dict) and value.get('timestamp'):
                                try:
                                    ts = parse_sensor_timestamp(value.get('timestamp'))
                                    if not ts:
                                        continue
                                    if ts.tzinfo is None:
                                        ts = ts.replace(tzinfo=JAKARTA_TZ)
                                    numeric_timestamp = ts.astimezone(timezone.utc).timestamp()
                                    if numeric_timestamp > latest_timestamp:
                                        latest_timestamp = numeric_timestamp
                                        latest_firebase_reading = value
                                        latest_firebase_reading['timestamp'] = iso_from_dt(ts)
                                except Exception:
                                    continue

                        if latest_firebase_reading:
                            stats["last_reading"] = latest_firebase_reading
                
                # Get latest predictions from Firebase
                predictions = get_from_firebase(f'/predictions?limitToLast={config.get("MAX_FIREBASE_PREDICTIONS")}')
                
                if predictions and isinstance(predictions, dict):
                    latest_prediction = None
                    latest_timestamp = 0
                    
                    for key, value in predictions.items():
                        if isinstance(value, dict) and value.get('timestamp'):
                            try:
                                ts = parse_sensor_timestamp(value.get('timestamp'))
                                if not ts:
                                    continue
                                if ts.tzinfo is None:
                                    ts = ts.replace(tzinfo=JAKARTA_TZ)
                                numeric_timestamp = ts.astimezone(timezone.utc).timestamp()
                                if numeric_timestamp > latest_timestamp:
                                    latest_timestamp = numeric_timestamp
                                    latest_prediction = value
                                    latest_prediction['timestamp'] = iso_from_dt(ts)
                            except Exception:
                                continue
                    
                    if latest_prediction:
                        stats["last_prediction"] = latest_prediction
                
            except Exception as firebase_error:
                logger.warning(f"Firebase data retrieval failed: {firebase_error}")
        
        logger.info(f"Dashboard stats - Source: {stats['data_source']}, Total: {stats['total_readings']}, Latest: {stats['last_reading']['timestamp'] if stats['last_reading'] else 'None'}")
        
        return jsonify(stats)
        
    except Exception as e:
        logger.error(f"Error getting dashboard stats: {e}")
        return jsonify({"error": str(e)}), 500

@app.route('/api/historical-data', methods=['GET'])
def get_historical_data():
    """Get historical sensor data"""
    try:
        limit = request.args.get('limit', 100, type=int)
        
        # Try Firebase first
        if firebase_initialized:
            try:
                data = get_from_firebase('/sensor_data')
                
                if data and isinstance(data, dict):
                    sorted_items = sorted(data.items(), 
                                      key=lambda x: x[1].get('timestamp', ''), 
                                      reverse=True)[:limit]
                    sorted_data = dict(sorted_items)
                    
                    return jsonify({
                        "data": sorted_data,
                        "count": len(sorted_data),
                        "source": "firebase"
                    })
            except Exception as firebase_error:
                logger.warning(f"Firebase historical data error: {firebase_error}")
        
        # Fallback to local data
        data = {}
        for i, item in enumerate(local_data[-limit:]):
            data[f"reading_{i}"] = item
        
        return jsonify({
            "data": data,
            "count": len(data),
            "source": "local"
        })
        
    except Exception as e:
        logger.error(f"Error getting historical data: {e}")
        return jsonify({"error": str(e)}), 500

@app.route('/api/predictions', methods=['GET'])
def get_predictions():
    """Get AI predictions"""
    try:
        limit = request.args.get('limit', 50, type=int)
        
        # Try Firebase first
        if firebase_initialized:
            try:
                data = get_from_firebase('/predictions')
                
                if data and isinstance(data, dict):
                    sorted_items = sorted(data.items(), 
                                      key=lambda x: x[1].get('timestamp', ''), 
                                      reverse=True)[:limit]
                    sorted_data = dict(sorted_items)
                    
                    return jsonify({
                        "predictions": sorted_data,
                        "count": len(sorted_data),
                        "source": "firebase"
                    })
            except Exception as firebase_error:
                logger.warning(f"Firebase predictions error: {firebase_error}")
        
        # Fallback to local latest prediction only (no simulated predictions)
        if last_prediction:
            return jsonify({
                "predictions": {"latest": last_prediction},
                "count": 1,
                "source": "local"
            })
        return jsonify({
            "predictions": {},
            "count": 0,
            "source": "local"
        })
        
    except Exception as e:
        logger.error(f"Error getting predictions: {e}")
        return jsonify({"error": str(e)}), 500


@app.route('/api/ai/status', methods=['GET'])
def ai_status():
    """Status kesiapan training AI + info model untuk debugging."""
    ready, info = ai_ready_for_training()
    model_path = str(weather_ai.model_file)
    scaler_path = str(weather_ai.scaler_file)
    model_exists = weather_ai.model_file.exists() and weather_ai.scaler_file.exists()
    model_size = weather_ai.model_file.stat().st_size if weather_ai.model_file.exists() else None
    # Prepare a compact prediction history for the status response
    max_hist = int(config.get('MAX_PREDICTION_HISTORY', 50))
    recent_preds = prediction_history[-max_hist:]

    return jsonify({
        "ready": bool(ready),
        "info": info,
        "data_count": len(local_data),
        "distribution": get_label_distribution(local_data),
        "trained": bool(weather_ai.trained),
        "training_in_progress": bool(ai_training_in_progress),
        "trained_at": weather_ai.model_trained_at,
        "model_path": model_path,
        "scaler_path": scaler_path,
        "model_exists": bool(model_exists),
        "model_size": model_size,
        "model_checksum": file_checksum(weather_ai.model_file),
        "scaler_checksum": file_checksum(weather_ai.scaler_file),
        "last_metrics": weather_ai.last_metrics,
        "last_prediction": last_prediction,
        "prediction_history": recent_preds,
        "model_meta": getattr(weather_ai, 'model_meta', None),
        "evaluation_mode": weather_ai.last_metrics.get("evaluation_mode", "UNKNOWN") if isinstance(weather_ai.last_metrics, dict) else "UNKNOWN",
    })

@app.route('/api/train-model', methods=['POST'])
def train_ai_model():
    """Train the AI weather prediction model"""
    try:
        body = request.get_json(silent=True) or {}
        force_single_class = bool(body.get("force_single_class"))

        # Log request for diagnostics
        logger.info(f"Received /api/train-model request from {request.remote_addr} body={{'force_single_class': {force_single_class}}} data_points={len(local_data)}")

        # Manual-only: jangan generate data sintetik di endpoint.
        ready, info = ai_ready_for_training()
        if not ready and not force_single_class:
            logger.info(f"Training request rejected (not_ready). info={info} data_points={len(local_data)}")
            return jsonify({
                "status": "not_ready",
                "message": "AI belum siap di-training. Kumpulkan data sensor terlebih dahulu.",
                "ready": False,
                "info": info,
                "data_points": len(local_data),
                "model_trained": bool(weather_ai.trained),
            }), 409

        global ai_training_in_progress
        with ai_training_lock:
            if ai_training_in_progress:
                logger.info("Training request accepted but training already in progress")
                return jsonify({
                    "status": "training_in_progress",
                    "message": "Training AI sedang berjalan.",
                    "ready": True,
                    "info": info,
                    "data_points": len(local_data),
                    "model_trained": bool(weather_ai.trained),
                }), 202
            ai_training_in_progress = True

        # If readiness check suggested auto_force, apply it unless user explicitly set force_single_class=false
        effective_force = force_single_class or bool(info.get('auto_force'))
        if effective_force and not force_single_class:
            logger.info("Auto-force enabled for this training run due to single-class large dataset (server policy)")

        def _run_train():
            global ai_training_in_progress, last_prediction
            try:
                logger.info(f"Background training starting (force_single_class={effective_force})")
                try:
                    success = weather_ai.train_model(force_single_class=effective_force)
                    if success:
                        logger.info("Background training completed successfully")

                        # Generate a fresh prediction using the latest reading (if present)
                        try:
                            latest_reading = local_data[-1] if local_data else None
                            if latest_reading:
                                ml_prediction = weather_ai.predict_weather(latest_reading)
                                forecast = forecast_engine.forecast_3h(latest_reading, local_data)
                                prediction = {
                                    "timestamp": latest_reading.get('timestamp') or iso_now(),
                                    "condition": forecast.get("now", {}).get("weather_type", "N/A"),
                                    "confidence": float(forecast.get("now", {}).get("confidence", 0.0)),
                                    "weather_type": forecast.get("now", {}).get("weather_type", "N/A"),
                                    "sky_now": forecast.get("now", {}).get("light_label", None),
                                    "rain_probability": float(forecast.get("now", {}).get("rain_probability", 0.0)),
                                    "predicted_rain_time": forecast.get("predicted_rain_time"),
                                    "hourly_forecast": forecast.get("hourly_forecast", []),
                                    "primary_recommendation": forecast.get("primary_recommendation", "Pantau kondisi cuaca"),
                                    "recommendations": [forecast.get("primary_recommendation", "Pantau kondisi cuaca")],
                                    "ml_condition": ml_prediction.get("condition"),
                                    "ml_confidence": float(ml_prediction.get("confidence", 0.0) or 0.0),
                                    "ml_recommendations": ml_prediction.get("recommendations", []),
                                }
                                global last_prediction, prediction_history
                                last_prediction = prediction
                                # Append to prediction history and trim
                                prediction_history.append(prediction)
                                max_hist = int(config.get('MAX_PREDICTION_HISTORY', 50))
                                while len(prediction_history) > max_hist:
                                    prediction_history.pop(0)

                                logger.info("Updated last_prediction after training completion: %s", prediction.get('condition'))

                                # Persist to Firebase if enabled
                                if firebase_initialized:
                                    try:
                                        pred_payload = prediction.copy()
                                        pred_payload['sensor_data_id'] = f"local_{len(local_data)}"
                                        send_to_firebase('/predictions', pred_payload)
                                        logger.info("Stored prediction to Firebase after training")
                                    except Exception as fe:
                                        logger.error(f"Failed to store prediction to Firebase: {fe}")

                                # Notify connected frontends
                                try:
                                    socketio.emit('ai_update', {
                                        'model_trained': weather_ai.trained,
                                        'model_trained_at': weather_ai.model_trained_at,
                                        'last_metrics': weather_ai.last_metrics,
                                        'last_prediction': last_prediction,
                                        'model_meta': getattr(weather_ai, 'model_meta', {})
                                    })
                                    socketio.emit('status_update', get_current_status())
                                except Exception as e:
                                    logger.debug(f"Socket emit after training failed: {e}")
                        except Exception as e:
                            logger.exception(f"Failed to generate/store prediction after training: {e}")
                    else:
                        logger.warning("Background training finished but returned failure (no model saved)")
                except Exception as e:
                    logger.exception(f"Exception during background training: {e}")
            finally:
                ai_training_in_progress = False
                logger.info("Background training flag cleared")

        threading.Thread(target=_run_train, daemon=True).start()
        
        return jsonify({
            "status": "training_started",
            "message": "AI model training started",
            "ready": True,
            "info": info,
            "data_points": len(local_data),
            "firebase_available": firebase_initialized,
            "model_trained": weather_ai.trained,
            "model_accuracy": weather_ai.accuracy if hasattr(weather_ai, 'accuracy') else 0.0
        })
        
    except Exception as e:
        logger.exception(f"Error training model: {e}")
        return jsonify({"error": str(e)}), 500


# Debug-only request echo endpoint (useful to confirm dashboard requests reach the server)
@app.route('/api/debug/request', methods=['GET', 'POST'])
def debug_request():
    if not config.get('DEBUG'):
        return jsonify({"error": "Debug disabled"}), 404
    try:
        body = request.get_json(silent=True)
    except Exception:
        body = None
    headers = {k: v for k, v in request.headers.items() if k.lower() not in ('authorization',)}
    logger.debug(f"Debug Request: method={request.method} remote={request.remote_addr} headers={dict(list(headers.items())[:10])} body_preview={str(body)[:200]}")
    return jsonify({
        "method": request.method,
        "remote_addr": request.remote_addr,
        "headers": headers,
        "body": body,
        "args": request.args
    })

@app.route('/api/test-firebase', methods=['GET'])
def test_firebase():
    """Test Firebase connection"""
    return jsonify({
        "firebase_available": firebase_initialized,
        "config": {
            "database_url": firebase_config.get('databaseURL'),
            "project_id": firebase_config.get('projectId')
        },
        "connection_test": test_firebase_connection(),
        "local_data_count": len(local_data)
    })




@app.route('/api/firebase/status', methods=['GET'])
def firebase_status():
    """Status Firebase untuk dashboard (aktif/nonaktif + koneksi)."""
    return jsonify({
        "configured": bool(firebase_config.get('databaseURL')),
        "enabled": bool(firebase_initialized),
        "connected": bool(current_status.get('firebase_connected', False)),
        "data_source": current_status.get('data_source', 'Local'),
    })


@app.route('/api/firebase/connect', methods=['POST'])
def firebase_connect():
    """Aktifkan Firebase (uji koneksi, bila gagal tetap mode lokal)."""
    global firebase_initialized, firebase_last_ok, last_firebase_check_at

    if not firebase_config.get('databaseURL'):
        set_firebase_enabled(False)
        return jsonify({
            "enabled": False,
            "connected": False,
            "error": "Firebase tidak dikonfigurasi (FIREBASE_DATABASE_URL kosong)."
        }), 400

    # Aktifkan dulu agar status_update dari tes tidak mengirim firebase_enabled=false
    set_firebase_enabled(True)

    # Coba koneksi dan pertahankan aktif hanya jika tes berhasil
    ok = test_firebase_connection()
    firebase_last_ok = bool(ok)
    last_firebase_check_at = datetime.utcnow()
    if not ok:
        set_firebase_enabled(False)

    return jsonify({
        "enabled": bool(firebase_initialized),
        "connected": bool(current_status.get('firebase_connected', False)),
        "connection_test": bool(ok),
        "data_source": current_status.get('data_source', 'Local'),
    })


@app.route('/api/firebase/disconnect', methods=['POST'])
def firebase_disconnect():
    """Nonaktifkan Firebase (paksa mode lokal)."""
    set_firebase_enabled(False)
    return jsonify({
        "enabled": False,
        "connected": False,
        "data_source": current_status.get('data_source', 'Local'),
    })

@app.route('/api/backup', methods=['POST'])
def backup_data_endpoint():
    """Manual backup endpoint"""
    try:
        success = backup_data()
        return jsonify({
            "status": "success" if success else "failed",
            "message": "Data backup completed" if success else "Data backup failed",
            "timestamp": iso_now()
        })
    except Exception as e:
        logger.error(f"Backup endpoint error: {e}")
        return jsonify({"error": str(e)}), 500

@app.route('/api/restore', methods=['POST'])
def restore_data_endpoint():
    """Manual restore endpoint"""
    try:
        success = restore_data()
        return jsonify({
            "status": "success" if success else "failed",
            "message": "Data restore completed" if success else "Data restore failed",
            "timestamp": iso_now(),
            "data_points": len(local_data)
        })
    except Exception as e:
        logger.error(f"Restore endpoint error: {e}")
        return jsonify({"error": str(e)}), 500

# ESP32 API Endpoints

# Integrasi perangkat (fondasi): konfigurasi via web + polling commands + ACK.
@app.route('/api/devices/<device_id>/config', methods=['POST'])
def set_device_config(device_id):
    if not _is_valid_device_id(device_id):
        return jsonify({"error": "device_id tidak valid"}), 400

    if not _verify_device_signature_or_skip(device_id):
        return jsonify({"error": "signature tidak valid"}), 401

    if request.content_length and request.content_length > MAX_DEVICE_JSON_BYTES:
        return jsonify({"error": "payload terlalu besar"}), 413

    payload = request.get_json(silent=True)
    if payload is None:
        return jsonify({"error": "body JSON tidak valid"}), 400
    if not isinstance(payload, dict):
        return jsonify({"error": "body harus berupa objek JSON"}), 400

    command_id = uuid.uuid4().hex
    record = {
        "device_id": device_id,
        "pending": True,
        "command_id": command_id,
        "desired_config": payload,
        "updated_at": iso_now(),
        "last_ack": None
    }
    _write_device_config_file(device_id, record)

    return jsonify({
        "status": "ok",
        "device_id": device_id,
        "command_id": command_id,
        "pending": True
    })


@app.route('/api/devices/<device_id>/commands', methods=['GET'])
def get_device_commands(device_id):
    if not _is_valid_device_id(device_id):
        return jsonify({"error": "device_id tidak valid"}), 400

    if not _verify_device_signature_or_skip(device_id):
        return jsonify({"error": "signature tidak valid"}), 401

    record = _read_device_config_file(device_id)
    if record and record.get('pending') and record.get('desired_config') and record.get('command_id'):
        return jsonify({
            "status": "ok",
            "command": "apply_config",
            "command_id": record.get('command_id'),
            "payload": record.get('desired_config'),
            "server_time": iso_now()
        })

    return jsonify({
        "status": "ok",
        "command": "no_command",
        "server_time": iso_now()
    })


@app.route('/api/devices/<device_id>/ack', methods=['POST'])
def ack_device_command(device_id):
    if not _is_valid_device_id(device_id):
        return jsonify({"error": "device_id tidak valid"}), 400

    if not _verify_device_signature_or_skip(device_id):
        return jsonify({"error": "signature tidak valid"}), 401

    if request.content_length and request.content_length > MAX_DEVICE_JSON_BYTES:
        return jsonify({"error": "payload terlalu besar"}), 413

    payload = request.get_json(silent=True)
    if payload is None or not isinstance(payload, dict):
        return jsonify({"error": "body harus berupa objek JSON"}), 400

    command_id = str(payload.get('command_id') or '').strip()
    if not command_id:
        return jsonify({"error": "command_id wajib diisi"}), 400

    success = payload.get('success', None)
    if not isinstance(success, bool):
        return jsonify({"error": "success harus boolean"}), 400

    reason = payload.get('reason', '')
    if reason is None:
        reason = ''
    if not isinstance(reason, str):
        return jsonify({"error": "reason harus string"}), 400
    reason = reason.strip()
    if len(reason) > 500:
        return jsonify({"error": "reason terlalu panjang"}), 400

    record = _read_device_config_file(device_id)
    if not record:
        return jsonify({"error": "tidak ada perintah untuk device ini"}), 404

    current_cmd = str(record.get('command_id') or '').strip()
    if current_cmd != command_id:
        return jsonify({"error": "command_id tidak cocok"}), 409

    record['pending'] = False
    record['last_ack'] = {
        "command_id": command_id,
        "success": success,
        "reason": reason,
        "ack_at": iso_now()
    }
    record['updated_at'] = iso_now()
    if success:
        record['applied_config'] = record.get('desired_config')

    _write_device_config_file(device_id, record)

    return jsonify({
        "status": "ok",
        "device_id": device_id,
        "command_id": command_id,
        "pending": False
    })

@app.route('/api/esp32/status', methods=['GET'])
def get_esp32_status():
    """Get ESP32 device status"""
    try:
        esp32_connected, esp32_last_seen = get_esp32_connection_state()
        # Simulasi data ESP32 - ganti dengan data aktual dari ESP32
        esp32_data = {
            "connected": esp32_connected,
            "last_seen": esp32_last_seen,
            "uptime": 86400,    # detik
            "free_heap": 45875, # bytes
            "wifi_rssi": -45,   # dBm
            "firmware": "v1.2.0",
            "mac_address": "24:6F:28:5C:1A:3B",
            "ip_address": None,
            "cpu_freq": 240,    # MHz
            "flash_size": 4194304, # bytes
            "sketch_size": 1048576, # bytes
            "wifi_ssid": "WeatherStation_Network",
            "sensors": {
                "SHT31": {
                    "status": "active",
                    "temperature": 25.5,
                    "humidity": 60.0
                },
                "BH1750": {
                    "status": "active", 
                    "light_intensity": 500.0
                },
                "MQ135": {
                    "status": "active",
                    "air_quality": 150
                },
                "NEO6M": {
                    "status": "active",
                    "latitude": -7.230958,
                    "longitude": 112.753463
                },
                "INA219": {
                    "status": "active",
                    "current": 250.5,
                    "voltage": 5.0,
                    "power": 1.25
                },
                "Battery": {
                    "status": "active",
                    "voltage": 3.7,
                    "percentage": 85
                }
            }
        }
        
        return jsonify(esp32_data)
        
    except Exception as e:
        logger.error(f"Error getting ESP32 status: {e}")
        return jsonify({
            "connected": False,
            "error": str(e)
        }), 500

@app.route('/api/esp32/config', methods=['GET', 'POST'])
def esp32_config():
    """Get or update ESP32 configuration"""
    try:
        if request.method == 'GET':
            # Load konfigurasi ESP32 dari file atau database
            config_file = Path(config.get('DATA_DIR')) / 'esp32_config.json'
            
            if config_file.exists():
                with open(config_file, 'r') as f:
                    esp32_config = json.load(f)
            else:
                # Default configuration
                esp32_config = {
                    "sensor_interval": 1,
                    "selected_sensors": {
                        "temperature": True,
                        "humidity": True,
                        "air_quality": True,
                        "light_intensity": True,
                        "gps_latitude": True,
                        "gps_longitude": True,
                        "current": True,
                        "voltage": True,
                        "power": True,
                        "battery_voltage": True
                    },
                    "calibration_values": {
                        "temperature": 0.0,
                        "humidity": 0.0,
                        "air_quality": 0,
                        "light_intensity": 0,
                        "gps_latitude": 0.0,
                        "gps_longitude": 0.0,
                        "current": 0.0,
                        "voltage": 0.0,
                        "power": 0.0,
                        "battery_voltage": 0.0
                    },
                    "wifi_ssid": "",
                    "wifi_password": "",
                    "sleep_mode": "none",
                    "deep_sleep_duration": 300,
                    "auto_reboot": True,
                    "data_retention_days": 30
                }
            
            return jsonify(esp32_config)
            
        elif request.method == 'POST':
            # Save konfigurasi ESP32
            new_config = request.json
            
            # Validate input
            required_fields = ['sensor_interval', 'selected_sensors', 'calibration_values']
            for field in required_fields:
                if field not in new_config:
                    return jsonify({"error": f"Missing required field: {field}"}), 400
            
            # Validate sensor interval
            if not isinstance(new_config['sensor_interval'], int) or new_config['sensor_interval'] < 1 or new_config['sensor_interval'] > 60:
                return jsonify({"error": "sensor_interval must be between 1 and 60"}), 400
            
            # Validate selected sensors
            valid_sensors = ['temperature', 'humidity', 'air_quality', 'light_intensity', 'gps_latitude', 'gps_longitude', 'current', 'voltage', 'power', 'battery_voltage']
            for sensor in new_config['selected_sensors']:
                if sensor not in valid_sensors:
                    return jsonify({"error": f"Invalid sensor: {sensor}"}), 400
            
            # Validate calibration values
            for sensor, value in new_config['calibration_values'].items():
                if sensor not in valid_sensors:
                    return jsonify({"error": f"Invalid calibration sensor: {sensor}"}), 400
                if not isinstance(value, (int, float)):
                    return jsonify({"error": f"Calibration value for {sensor} must be numeric"}), 400
            
            # Save to file
            config_file = Path(config.get('DATA_DIR')) / 'esp32_config.json'
            config_file.parent.mkdir(parents=True, exist_ok=True)
            
            with open(config_file, 'w') as f:
                json.dump(new_config, f, indent=2)
            
            # TODO: Kirim konfigurasi ke ESP32 aktual via MQTT/HTTP
            logger.info(f"ESP32 configuration updated: {new_config}")
            
            # Log sensor calibration changes
            enabled_sensors = [sensor for sensor, enabled in new_config['selected_sensors'].items() if enabled]
            logger.info(f"Enabled sensors for calibration: {enabled_sensors}")
            
            for sensor, value in new_config['calibration_values'].items():
                if new_config['selected_sensors'].get(sensor, False) and value != 0:
                    logger.info(f"Calibration {sensor}: {value}")
            
            return jsonify({
                "status": "success",
                "message": "Konfigurasi ESP32 diperbarui",
                "config": new_config,
                "enabled_sensors": enabled_sensors
            })
            
    except Exception as e:
        logger.error(f"Error in ESP32 config endpoint: {e}")
        return jsonify({"error": str(e)}), 500

@app.route('/api/esp32/reboot', methods=['POST'])
def reboot_esp32():
    """Reboot ESP32 device"""
    try:
        # TODO: Kirim perintah reboot ke ESP32 aktual
        logger.info("ESP32 reboot command sent")
        
        return jsonify({
            "status": "success",
            "message": "Perintah reboot ESP32 dikirim",
            "reboot_time": iso_now()
        })
        
    except Exception as e:
        logger.error(f"Error rebooting ESP32: {e}")
        return jsonify({"error": str(e)}), 500

@app.route('/api/esp32/reset', methods=['POST'])
def reset_esp32():
    """Reset ESP32 to factory defaults"""
    try:
        # TODO: Kirim perintah reset ke ESP32 aktual
        logger.warning("ESP32 factory reset command sent")
        
        # Hapus file konfigurasi
        config_file = Path(config.get('DATA_DIR')) / 'esp32_config.json'
        if config_file.exists():
            config_file.unlink()
        
        return jsonify({
            "status": "success",
            "message": "ESP32 di-reset ke pengaturan default",
            "reset_time": iso_now()
        })
        
    except Exception as e:
        logger.error(f"Error resetting ESP32: {e}")
        return jsonify({"error": str(e)}), 500

@app.route('/api/esp32/logs', methods=['GET'])
def get_esp32_logs():
    """Get ESP32 device logs"""
    try:
        # TODO: Ambil logs dari ESP32 aktual
        logs = [
            {
                "timestamp": iso_now(),
                "level": "INFO",
                "message": "ESP32 started successfully"
            },
            {
                "timestamp": iso_now(),
                "level": "INFO",
                "message": "No device log endpoint implemented"
            }
        ]
        return jsonify({"logs": logs})
    except Exception as e:
        logger.error(f"Error getting ESP32 logs: {e}")
        return jsonify({"error": str(e)}), 500


# System logs (backend)
@app.route('/api/logs', methods=['GET', 'POST'])
def system_logs():
    """GET: return tail logs, POST with action=clear to truncate."""
    log_file = config.get('LOG_FILE')
    try:
        if request.method == 'POST':
            action = (request.json or {}).get('action')
            if action == 'clear':
                Path(log_file).parent.mkdir(parents=True, exist_ok=True)
                open(log_file, 'w').close()
                logger.info("Logs cleared via API")
                return jsonify({"status": "cleared"})
            return jsonify({"error": "unknown action"}), 400

        # GET - read last 200 lines
        Path(log_file).parent.mkdir(parents=True, exist_ok=True)
        if not os.path.exists(log_file):
            open(log_file, 'a').close()
            return jsonify({"logs": []})
        with open(log_file, 'r', errors='ignore') as f:
            lines = f.readlines()
        return jsonify({"logs": lines[-200:]})
    except Exception as exc:
        logger.error(f"Error handling /api/logs: {exc}")
        return jsonify({"error": str(exc)}), 500

# Graceful shutdown
def signal_handler(signum, frame):
    """Handle graceful shutdown"""
    logger.info("Received shutdown signal, backing up data...")
    backup_data()
    logger.info("Server shutting down...")
    sys.exit(0)

signal.signal(signal.SIGTERM, signal_handler)
signal.signal(signal.SIGINT, signal_handler)

# Main execution
if __name__ == '__main__':
    logger.info("Starting Weather Station Backend Server...")
    logger.info(f"Server: {SERVER_IP}:{config.get('PORT')}")
    logger.info(f"Environment: {'Production' if not config.get('DEBUG') else 'Development'}")
    logger.info(f"Firebase: {'Connected' if firebase_initialized else 'Disabled'}")
    logger.info(f"AI Model: {'Trained' if weather_ai.trained else 'Ready for training'}")
    logger.info(f"Data Directory: {config.get('DATA_DIR')}")
    logger.info(f"Log File: {config.get('LOG_FILE')}")
    logger.info("=" * 50)
    
    # Restore data if available
    restore_data()

    # CLI helper: --ai-status
    if '--ai-status' in sys.argv:
        ready, info = ai_ready_for_training()
        payload = {
            'ready': bool(ready),
            'info': info,
            'data_count': len(local_data),
            'distribution': get_label_distribution(local_data),
            'trained': bool(weather_ai.trained),
            'trained_at': weather_ai.model_trained_at,
            'model_path': str(weather_ai.model_file),
            'model_checksum': file_checksum(weather_ai.model_file),
            'evaluation_mode': weather_ai.last_metrics.get('evaluation_mode', 'UNKNOWN') if isinstance(weather_ai.last_metrics, dict) else 'UNKNOWN'
        }
        print(json.dumps(payload, indent=2, ensure_ascii=False))
        sys.exit(0)
    
    # Start Firebase listener in background
    if firebase_initialized:
        firebase_thread = threading.Thread(target=start_firebase_listener, daemon=True)
        firebase_thread.start()
        logger.info("Firebase real-time listener started in background")
    
    # Start SocketIO server
    socketio.run(
        app,
        host=config.get('HOST'),
        port=config.get('PORT'),
        debug=config.get('DEBUG'),
        allow_unsafe_werkzeug=True
    )
