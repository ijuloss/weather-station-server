#!/usr/bin/env python3
"""
Weather Station Backend Server
Optimized for Debian 12 Server with CasaOS
Production-ready with comprehensive error handling
"""

import os
import sys
import logging
import socket
import random
import signal
import json
from datetime import datetime
from pathlib import Path
from flask import Flask, request, jsonify
from flask_cors import CORS
import requests
import joblib
import numpy as np
from sklearn.ensemble import RandomForestClassifier
from sklearn.preprocessing import StandardScaler
from sklearn.model_selection import train_test_split
from sklearn.metrics import accuracy_score, classification_report
import threading
import time

# Add project root to path
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

# Configuration management
class Config:
    def __init__(self):
        self.load_config()
    
    def load_config(self):
        """Load configuration from multiple sources"""
        # Default configuration
        self.config = {
            'HOST': '0.0.0.0',
            'PORT': 5000,
            'DEBUG': False,
            'LOG_LEVEL': 'INFO',
            'LOG_FILE': '/var/log/weather-station/app.log',
            'DATA_DIR': '/var/lib/weather-station',
            'CONFIG_DIR': '/etc/weather-station',
            'RUN_DIR': '/run/weather-station',
            'FIREBASE_API_KEY': '',
            'FIREBASE_AUTH_DOMAIN': '',
            'FIREBASE_DATABASE_URL': '',
            'FIREBASE_PROJECT_ID': '',
            'FIREBASE_STORAGE_BUCKET': '',
            'FIREBASE_MESSAGING_SENDER_ID': '',
            'FIREBASE_APP_ID': '',
            'FIREBASE_MEASUREMENT_ID': '',
            'MODEL_TRAINING_INTERVAL': 50,
            'PREDICTION_CONFIDENCE_THRESHOLD': 0.6,
            'MAX_LOCAL_READINGS': 1000,
            'MAX_FIREBASE_READINGS': 100,
            'MAX_FIREBASE_PREDICTIONS': 50,
            'REQUEST_TIMEOUT': 30,
            'MAX_RETRIES': 3,
            'UPDATE_INTERVAL': 2,
            'BACKUP_INTERVAL': 3600,  # 1 hour
            'HEALTH_CHECK_INTERVAL': 60,  # 1 minute
        }
        
        # Load from environment variables
        for key in self.config:
            env_value = os.getenv(key)
            if env_value is not None:
                if key in ['DEBUG']:
                    self.config[key] = env_value.lower() == 'true'
                elif key in ['PORT', 'MODEL_TRAINING_INTERVAL', 'MAX_LOCAL_READINGS', 
                           'MAX_FIREBASE_READINGS', 'MAX_FIREBASE_PREDICTIONS', 
                           'REQUEST_TIMEOUT', 'MAX_RETRIES', 'UPDATE_INTERVAL',
                           'BACKUP_INTERVAL', 'HEALTH_CHECK_INTERVAL']:
                    self.config[key] = int(env_value)
                elif key in ['PREDICTION_CONFIDENCE_THRESHOLD']:
                    self.config[key] = float(env_value)
                else:
                    self.config[key] = env_value
        
        # Load from config file
        config_file = Path(self.config['CONFIG_DIR']) / 'server.conf'
        if config_file.exists():
            try:
                with open(config_file, 'r') as f:
                    file_config = json.load(f)
                self.config.update(file_config)
            except Exception as e:
                print(f"Warning: Could not load config file: {e}")
    
    def get(self, key, default=None):
        return self.config.get(key, default)
    
    def set(self, key, value):
        self.config[key] = value
    
    def save(self):
        """Save configuration to file"""
        config_file = Path(self.config['CONFIG_DIR']) / 'server.conf'
        config_file.parent.mkdir(parents=True, exist_ok=True)
        with open(config_file, 'w') as f:
            json.dump(self.config, f, indent=2)

# Initialize configuration
config = Config()

# Setup logging
def setup_logging():
    """Setup comprehensive logging"""
    log_dir = Path(config.get('LOG_FILE')).parent
    log_dir.mkdir(parents=True, exist_ok=True)
    
    logging.basicConfig(
        level=getattr(logging, config.get('LOG_LEVEL', 'INFO')),
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        handlers=[
            logging.FileHandler(config.get('LOG_FILE')),
            logging.StreamHandler(sys.stdout)
        ]
    )
    return logging.getLogger(__name__)

logger = setup_logging()

# Create necessary directories
def create_directories():
    """Create necessary directories"""
    dirs = [
        config.get('DATA_DIR'),
        config.get('CONFIG_DIR'),
        config.get('RUN_DIR'),
        Path(config.get('DATA_DIR')) / 'backups',
        Path(config.get('DATA_DIR')) / 'models',
    ]
    
    for dir_path in dirs:
        Path(dir_path).mkdir(parents=True, exist_ok=True)
        logger.info(f"Created directory: {dir_path}")

create_directories()

# Initialize Flask app
app = Flask(__name__)
CORS(app, origins=["*"])

# Get server IP
def get_server_ip():
    """Get server IP address"""
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return "127.0.0.1"

SERVER_IP = get_server_ip()

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

def test_firebase_connection():
    """Test Firebase connection"""
    try:
        if not firebase_config.get('databaseURL'):
            logger.warning("Firebase database URL not configured")
            return False
        
        url = f"{firebase_config['databaseURL']}/.json"
        response = requests.get(url, timeout=config.get('REQUEST_TIMEOUT'))
        if response.status_code == 200:
            logger.info("Firebase connection test successful")
            return True
        else:
            logger.warning(f"Firebase connection failed with status: {response.status_code}")
            return False
    except Exception as e:
        logger.error(f"Firebase connection test failed: {e}")
        return False

# Initialize Firebase
if firebase_config.get('databaseURL') and firebase_config.get('apiKey'):
    firebase_initialized = test_firebase_connection()
    if firebase_initialized:
        logger.info("SUCCESS: Firebase connected using REST API")
    else:
        logger.warning("WARNING: Firebase connection failed - running in local mode")
else:
    logger.info("INFO: Firebase not configured - running in local mode")

# AI Weather Model
class WeatherAIModel:
    def __init__(self):
        self.model = RandomForestClassifier(n_estimators=100, random_state=42)
        self.scaler = StandardScaler()
        self.trained = False
        self.model_trained_at = None
        self.model_file = Path(config.get('DATA_DIR')) / 'models' / 'weather_model.pkl'
        self.scaler_file = Path(config.get('DATA_DIR')) / 'models' / 'scaler.pkl'
        
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
    
    def save_model(self):
        """Save model to disk"""
        try:
            self.model_file.parent.mkdir(parents=True, exist_ok=True)
            joblib.dump(self.model, self.model_file)
            joblib.dump(self.scaler, self.scaler_file)
            logger.info("AI model saved successfully")
            return True
        except Exception as e:
            logger.error(f"Failed to save AI model: {e}")
            return False
    
    def prepare_training_data(self, data):
        """Prepare data for AI model training"""
        features = []
        labels = []
        
        for item in data:
            feature_vector = [
                item.get('temperature', 0),
                item.get('humidity', 0),
                item.get('air_quality', 0),
                item.get('light_intensity', 0),
                item.get('battery_voltage', 0)
            ]
            features.append(feature_vector)
            
            # Weather condition classification
            temp = item.get('temperature', 0)
            humidity = item.get('humidity', 0)
            air_quality = item.get('air_quality', 0)
            
            if temp < 15:
                condition = "Cold"
            elif temp > 35:
                condition = "Very Hot"
            elif humidity > 80:
                condition = "Very Humid"
            elif air_quality > 300:
                condition = "Polluted"
            elif temp > 30 and humidity < 50:
                condition = "Hot Dry"
            elif temp > 25 and humidity > 70:
                condition = "Hot Humid"
            elif temp < 20 and humidity > 80:
                condition = "Cool Humid"
            else:
                condition = "Normal"
                
            labels.append(condition)
        
        X = np.array(features)
        y = np.array(labels)
        return X, y
    
    def train_model(self):
        """Train AI weather prediction model"""
        logger.info("AI: Starting model training...")
        
        try:
            # Use available data or generate sample data
            if len(local_data) < 30:
                logger.info("AI: Generating sample training data...")
                sample_data = []
                for i in range(200):
                    sample_data.append({
                        'temperature': random.uniform(10, 40),
                        'humidity': random.uniform(20, 95),
                        'air_quality': random.uniform(30, 500),
                        'light_intensity': random.uniform(0, 2000),
                        'battery_voltage': random.uniform(3.0, 4.5)
                    })
            else:
                sample_data = local_data.copy()
            
            X, y = self.prepare_training_data(sample_data)
            
            if len(X) < 10:
                logger.error("AI: Not enough data for training")
                return False
            
            # Split data
            X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.2, random_state=42)
            
            # Scale features
            X_train_scaled = self.scaler.fit_transform(X_train)
            X_test_scaled = self.scaler.transform(X_test)
            
            # Train model
            self.model.fit(X_train_scaled, y_train)
            
            # Evaluate
            train_score = self.model.score(X_train_scaled, y_train)
            test_score = self.model.score(X_test_scaled, y_test)
            
            self.trained = True
            self.model_trained_at = datetime.now().isoformat()
            
            # Save model
            self.save_model()
            
            logger.info(f"AI: Model trained successfully!")
            logger.info(f"AI: Training accuracy: {train_score:.2f}")
            logger.info(f"AI: Test accuracy: {test_score:.2f}")
            
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
            probabilities = self.model.predict_proba(features_scaled)[0]
            confidence = max(probabilities)
            
            # Get recommendations
            recommendations = self.get_recommendations(prediction, sensor_data)
            
            return {
                'condition': prediction,
                'confidence': confidence,
                'recommendations': recommendations
            }
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

# Initialize AI model
weather_ai = WeatherAIModel()

# Data storage
local_data = []
last_prediction = None

# Firebase helper functions
def send_to_firebase(path, data):
    """Send data to Firebase using REST API"""
    if not firebase_initialized:
        return None
    
    try:
        url = f"{firebase_config['databaseURL']}/{path}.json"
        response = requests.post(url, json=data, timeout=config.get('REQUEST_TIMEOUT'))
        if response.status_code == 200:
            return response.json()
        else:
            logger.warning(f"Firebase write failed with status: {response.status_code}")
            return None
    except Exception as e:
        logger.error(f"Firebase write error: {e}")
        return None

def get_from_firebase(path):
    """Get data from Firebase using REST API"""
    if not firebase_initialized:
        return None
    
    try:
        url = f"{firebase_config['databaseURL']}/{path}.json"
        response = requests.get(url, timeout=config.get('REQUEST_TIMEOUT'))
        if response.status_code == 200:
            return response.json()
        else:
            logger.warning(f"Firebase read failed with status: {response.status_code}")
            return None
    except Exception as e:
        logger.error(f"Firebase read error: {e}")
        return None

# Data backup functions
def backup_data():
    """Backup data to file"""
    try:
        backup_dir = Path(config.get('DATA_DIR')) / 'backups'
        backup_file = backup_dir / f"backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        
        backup_data = {
            'timestamp': datetime.now().isoformat(),
            'local_data': local_data,
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

# Start background tasks
background_thread = threading.Thread(target=background_tasks, daemon=True)
background_thread.start()

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
        "uptime": datetime.now().isoformat(),
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
    return jsonify({
        "status": "healthy",
        "timestamp": datetime.now().isoformat(),
        "server_ip": SERVER_IP,
        "data_points": len(local_data),
        "ai_model": weather_ai.trained,
        "firebase": firebase_initialized,
        "memory_usage": f"{sys.getsizeof(local_data) / 1024:.2f} KB"
    })

@app.route('/api/config')
def get_config():
    """Get current configuration"""
    return jsonify({
        "config": config.config,
        "firebase_configured": bool(firebase_config.get('databaseURL')),
        "server_info": {
            "ip": SERVER_IP,
            "port": config.get('PORT'),
            "version": "3.0"
        }
    })

@app.route('/api/sensor-data', methods=['POST'])
def receive_sensor_data():
    """Receive sensor data from ESP32"""
    try:
        sensor_reading = request.get_json()
        
        if not sensor_reading:
            logger.warning("No data received in POST request")
            return jsonify({"error": "No data received"}), 400
        
        # Validate required fields
        required_fields = ['temperature', 'humidity', 'air_quality', 'light_intensity', 'battery_voltage']
        missing_fields = [field for field in required_fields if field not in sensor_reading]
        if missing_fields:
            logger.warning(f"Missing required fields: {missing_fields}")
            return jsonify({"error": f"Missing required fields: {missing_fields}"}), 400
        
        # Add timestamp if not present
        if 'timestamp' not in sensor_reading:
            sensor_reading['timestamp'] = datetime.now().isoformat()
        
        # Store in local memory
        local_data.append(sensor_reading.copy())
        
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
        
        logger.info(f"Received sensor data: {sensor_reading['temperature']}°C, {sensor_reading['humidity']}% humidity")
        
        # Generate AI prediction
        prediction = weather_ai.predict_weather(sensor_reading)
        global last_prediction
        last_prediction = prediction
        logger.info(f"Generated AI prediction: {prediction.get('condition', 'N/A')} with {prediction.get('confidence', 0):.2f} confidence")
        
        # Store prediction in Firebase if available
        if firebase_initialized:
            try:
                prediction_data = {
                    'condition': prediction['condition'],
                    'confidence': prediction['confidence'],
                    'recommendations': prediction['recommendations'],
                    'timestamp': datetime.now().isoformat(),
                    'sensor_data_id': data_id
                }
                
                pred_result = send_to_firebase('/predictions', prediction_data)
                if pred_result:
                    logger.info("AI prediction stored in Firebase")
            except Exception as firebase_error:
                logger.error(f"Firebase prediction storage error: {firebase_error}")
        
        # Train model if needed
        if len(local_data) >= config.get('MODEL_TRAINING_INTERVAL') and not weather_ai.trained:
            threading.Thread(target=weather_ai.train_model, daemon=True).start()
        
        return jsonify({
            "status": "success",
            "message": "Data received and processed",
            "data_id": data_id or f"local_{len(local_data)}",
            "ai_prediction": prediction,
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
        stats = {
            "total_readings": len(local_data),
            "model_trained": weather_ai.trained,
            "last_reading": local_data[-1] if local_data else None,
            "last_prediction": last_prediction,
            "firebase_available": firebase_initialized,
            "model_trained_at": weather_ai.model_trained_at,
            "system_status": "running",
            "data_source": "local",
            "server_info": {
                "ip": SERVER_IP,
                "port": config.get('PORT'),
                "uptime": datetime.now().isoformat()
            }
        }
        
        # Try to get Firebase data if available
        if firebase_initialized:
            try:
                sensor_data = get_from_firebase(f'/sensor_data?limitToLast={config.get("MAX_FIREBASE_READINGS")}')
                
                if sensor_data and isinstance(sensor_data, dict):
                    firebase_count = len(sensor_data)
                    
                    if firebase_count > len(local_data):
                        stats["total_readings"] = firebase_count
                        stats["data_source"] = "firebase"
                        
                        # Get latest reading
                        latest_reading = None
                        latest_timestamp = 0
                        
                        for key, value in sensor_data.items():
                            if isinstance(value, dict) and value.get('timestamp'):
                                timestamp_str = value['timestamp']
                                numeric_timestamp = 0
                                try:
                                    if timestamp_str.startswith('20') and 'T' in timestamp_str:
                                        numeric_timestamp = datetime.fromisoformat(timestamp_str.replace('Z', '+00:00')).timestamp()
                                    elif timestamp_str.startswith('Day'):
                                        parts = timestamp_str.split()
                                        if len(parts) >= 3:
                                            day = int(parts[1]) if parts[1].isdigit() else 0
                                            time_parts = parts[2].split(':')
                                            if len(time_parts) >= 3:
                                                hours = int(time_parts[0])
                                                minutes = int(time_parts[1])
                                                seconds = int(time_parts[2])
                                                numeric_timestamp = day * 86400 + hours * 3600 + minutes * 60 + seconds
                                except Exception:
                                    continue
                                
                                if numeric_timestamp > latest_timestamp:
                                    latest_timestamp = numeric_timestamp
                                    latest_reading = value
                        
                        if latest_reading:
                            stats["last_reading"] = latest_reading
                
                # Get latest predictions
                predictions = get_from_firebase(f'/predictions?limitToLast={config.get("MAX_FIREBASE_PREDICTIONS")}')
                
                if predictions and isinstance(predictions, dict):
                    latest_prediction = None
                    latest_timestamp = 0
                    
                    for key, value in predictions.items():
                        if isinstance(value, dict) and value.get('timestamp'):
                            timestamp_str = value['timestamp']
                            numeric_timestamp = 0
                            try:
                                if timestamp_str.startswith('20') and 'T' in timestamp_str:
                                    numeric_timestamp = datetime.fromisoformat(timestamp_str.replace('Z', '+00:00')).timestamp()
                                elif timestamp_str.startswith('Day'):
                                    parts = timestamp_str.split()
                                    if len(parts) >= 3:
                                        day = int(parts[1]) if parts[1].isdigit() else 0
                                        time_parts = parts[2].split(':')
                                        if len(time_parts) >= 3:
                                            hours = int(time_parts[0])
                                            minutes = int(time_parts[1])
                                            seconds = int(time_parts[2])
                                            numeric_timestamp = day * 86400 + hours * 3600 + minutes * 60 + seconds
                            except Exception:
                                continue
                            
                            if numeric_timestamp > latest_timestamp:
                                latest_timestamp = numeric_timestamp
                                latest_prediction = value
                    
                    if latest_prediction:
                        stats["last_prediction"] = latest_prediction
                
            except Exception as firebase_error:
                logger.warning(f"Firebase data retrieval failed: {firebase_error}")
        
        logger.info(f"Dashboard stats - Source: {stats['data_source']}, Total: {stats['total_readings']}")
        
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
        
        # Fallback to simulated predictions
        predictions = {}
        for i in range(min(limit, 10)):
            predictions[f"prediction_{i}"] = {
                "condition": random.choice(["Cold", "Very Hot", "Very Humid", "Polluted", "Hot Dry", "Hot Humid", "Cool Humid", "Normal"]),
                "confidence": random.uniform(0.7, 0.95),
                "timestamp": datetime.now().isoformat(),
                "recommendations": ["Sample recommendation"]
            }
        
        return jsonify({
            "predictions": predictions,
            "count": len(predictions),
            "source": "simulated"
        })
        
    except Exception as e:
        logger.error(f"Error getting predictions: {e}")
        return jsonify({"error": str(e)}), 500

@app.route('/api/train-model', methods=['POST'])
def train_ai_model():
    """Train the AI weather prediction model"""
    try:
        if len(local_data) < 10:
            # Generate more sample data if needed
            for i in range(100):
                local_data.append({
                    'temperature': random.uniform(10, 40),
                    'humidity': random.uniform(20, 95),
                    'air_quality': random.uniform(30, 500),
                    'light_intensity': random.uniform(0, 2000),
                    'battery_voltage': random.uniform(3.0, 4.5),
                    'timestamp': datetime.now().isoformat()
                })
        
        # Train model
        if len(local_data) >= config.get('MODEL_TRAINING_INTERVAL'):
            success = weather_ai.train_model()
        else:
            threading.Thread(target=weather_ai.train_model, daemon=True).start()
            success = True
        
        return jsonify({
            "status": "training_started" if not weather_ai.trained else "training_completed",
            "message": "AI model training started" if not weather_ai.trained else "AI model training completed",
            "data_points": len(local_data),
            "firebase_available": firebase_initialized,
            "model_trained": weather_ai.trained,
            "model_accuracy": weather_ai.trained
        })
        
    except Exception as e:
        logger.error(f"Error training model: {e}")
        return jsonify({"error": str(e)}), 500

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

@app.route('/api/backup', methods=['POST'])
def backup_data_endpoint():
    """Manual backup endpoint"""
    try:
        success = backup_data()
        return jsonify({
            "status": "success" if success else "failed",
            "message": "Data backup completed" if success else "Data backup failed",
            "timestamp": datetime.now().isoformat()
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
            "timestamp": datetime.now().isoformat(),
            "data_points": len(local_data)
        })
    except Exception as e:
        logger.error(f"Restore endpoint error: {e}")
        return jsonify({"error": str(e)}), 500

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
    
    # Start server
    app.run(
        host=config.get('HOST'),
        port=config.get('PORT'),
        debug=config.get('DEBUG'),
        threaded=True
    )
