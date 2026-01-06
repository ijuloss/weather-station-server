#!/bin/bash
# Weather Station Configuration Script
# Run this after transferring files to server

set -e

# Colors
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

print_status() {
    echo -e "${GREEN}[INFO]${NC} $1"
}

print_warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
}

print_header() {
    echo -e "${BLUE}==========================================${NC}"
    echo -e "${BLUE}$1${NC}"
    echo -e "${BLUE}==========================================${NC}"
}

print_header "WEATHER STATION CONFIGURATION"

# Get server IP
SERVER_IP=$(hostname -I | awk '{print $1}')
print_status "Server IP detected: $SERVER_IP"

# Create configuration file
print_status "Creating configuration file..."
cat > /etc/weather-station/server.conf << EOF
# Weather Station Server Configuration
# Auto-generated on $(date)

# Server Configuration
HOST=0.0.0.0
PORT=5000
DEBUG=false

# Logging Configuration
LOG_LEVEL=INFO
LOG_FILE=/var/log/weather-station/app.log

# Data Storage
DATA_DIR=/var/lib/weather-station
CONFIG_DIR=/etc/weather-station
RUN_DIR=/run/weather-station

# Firebase Configuration (Optional - configure if needed)
FIREBASE_API_KEY=
FIREBASE_AUTH_DOMAIN=
FIREBASE_DATABASE_URL=
FIREBASE_PROJECT_ID=
FIREBASE_STORAGE_BUCKET=
FIREBASE_MESSAGING_SENDER_ID=
FIREBASE_APP_ID=
FIREBASE_MEASUREMENT_ID=

# AI Model Configuration
MODEL_TRAINING_INTERVAL=50
PREDICTION_CONFIDENCE_THRESHOLD=0.6

# Data Management
MAX_LOCAL_READINGS=1000
MAX_FIREBASE_READINGS=100
MAX_FIREBASE_PREDICTIONS=50

# Performance Settings
REQUEST_TIMEOUT=30
MAX_RETRIES=3
UPDATE_INTERVAL=2

# Background Tasks
BACKUP_INTERVAL=3600
HEALTH_CHECK_INTERVAL=60

# Security
ALLOWED_ORIGINS=*
CORS_ENABLED=true
EOF

# Set permissions
chown weatherstation:weatherstation /etc/weather-station/server.conf
chmod 644 /etc/weather-station/server.conf

print_status "Configuration file created: /etc/weather-station/server.conf"

# Create startup script
print_status "Creating startup script..."
cat > /opt/weather-station/start.sh << 'EOF'
#!/bin/bash
# Weather Station Startup Script

# Activate virtual environment
source /opt/weather-station/venv/bin/activate

# Set environment variables
export PYTHONPATH=/opt/weather-station
export WEATHER_STATION_CONFIG=/etc/weather-station/server.conf

# Start the application
cd /opt/weather-station
python app.py
EOF

chmod +x /opt/weather-station/start.sh
chown weatherstation:weatherstation /opt/weather-station/start.sh

print_status "Startup script created: /opt/weather-station/start.sh"

print_header "CONFIGURATION COMPLETED"
echo ""
echo -e "${GREEN}✅ Configuration completed!${NC}"
echo ""
echo -e "${BLUE}Configuration file:${NC} /etc/weather-station/server.conf"
echo -e "${BLUE}Startup script:${NC} /opt/weather-station/start.sh"
echo ""
echo -e "${YELLOW}To configure Firebase:${NC}"
echo "1. Edit: nano /etc/weather-station/server.conf"
echo "2. Add your Firebase credentials"
echo "3. Save: Ctrl+X, Y, Enter"
echo ""
echo -e "${BLUE}Next steps:${NC}"
echo "1. Start service: systemctl start weather-station"
echo "2. Check status: systemctl status weather-station"
echo "3. View logs: journalctl -u weather-station -f"
echo "4. Test API: curl http://$SERVER_IP:5000"
echo ""
echo -e "${GREEN}Server will be available at: http://$SERVER_IP:5000${NC}"
