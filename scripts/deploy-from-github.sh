#!/bin/bash
# Weather Station Server Deployment from GitHub
# Deploy to Debian 12 server from GitHub repository

set -e

echo "=========================================="
echo "  WEATHER STATION DEPLOYMENT"
echo "  From GitHub Repository"
echo "=========================================="

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Function to print colored output
print_status() {
    echo -e "${GREEN}[INFO]${NC} $1"
}

print_warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
}

print_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

print_header() {
    echo -e "${BLUE}==========================================${NC}"
    echo -e "${BLUE}$1${NC}"
    echo -e "${BLUE}==========================================${NC}"
}

# Configuration - MODIFY THESE VALUES
GITHUB_USERNAME="your_github_username"
REPO_NAME="weather-station-server"
INSTALL_DIR="/opt/weather-station"

# Get server IP
SERVER_IP=$(hostname -I | awk '{print $1}')

print_header "DEPLOYMENT CONFIGURATION"
echo "GitHub Username: $GITHUB_USERNAME"
echo "Repository: $REPO_NAME"
echo "Install Directory: $INSTALL_DIR"
echo "Server IP: $SERVER_IP"
echo ""

# Check if running as root
if [[ $EUID -ne 0 ]]; then
   print_error "This script must be run as root or with sudo"
   exit 1
fi

print_header "STEP 1: Install Dependencies"

# Update system
print_status "Updating system packages..."
apt update && apt upgrade -y

# Install required packages
print_status "Installing required packages..."
apt install -y \
    python3 \
    python3-pip \
    python3-venv \
    git \
    curl \
    wget \
    htop \
    nano \
    vim \
    unzip \
    build-essential \
    software-properties-common \
    apt-transport-https \
    ca-certificates \
    gnupg \
    lsb-release

# Install Python packages
print_status "Installing Python packages..."
pip3 install --upgrade pip
pip3 install \
    flask \
    flask-cors \
    requests \
    scikit-learn \
    numpy \
    joblib \
    pandas \
    gunicorn

print_header "STEP 2: Create System User"

# Create weather station user
print_status "Creating weatherstation system user..."
if ! id "weatherstation" &>/dev/null; then
    useradd -r -s /bin/bash -d /var/lib/weather-station weatherstation
    print_status "User weatherstation created"
else
    print_warning "User weatherstation already exists"
fi

# Create directories
print_status "Creating system directories..."
mkdir -p /var/lib/weather-station/{data,models,backups}
mkdir -p /var/log/weather-station
mkdir -p /etc/weather-station
mkdir -p /run/weather-station

# Set permissions
print_status "Setting directory permissions..."
chown -R weatherstation:weatherstation /var/lib/weather-station
chown -R weatherstation:weatherstation /var/log/weather-station
chown -R weatherstation:weatherstation /etc/weather-station
chown -R weatherstation:weatherstation /run/weather-station

chmod 755 /var/lib/weather-station
chmod 755 /var/log/weather-station
chmod 755 /etc/weather-station
chmod 755 /run/weather-station

print_header "STEP 3: Clone Repository"

# Remove existing installation
if [ -d "$INSTALL_DIR" ]; then
    print_status "Removing existing installation..."
    rm -rf "$INSTALL_DIR"
fi

# Clone repository
print_status "Cloning repository from GitHub..."
git clone "https://github.com/$GITHUB_USERNAME/$REPO_NAME.git" "$INSTALL_DIR"

# Set ownership
chown -R weatherstation:weatherstation "$INSTALL_DIR"
chmod -R 755 "$INSTALL_DIR"

print_header "STEP 4: Setup Python Environment"

# Create virtual environment
print_status "Creating Python virtual environment..."
cd "$INSTALL_DIR"
sudo -u weatherstation python3 -m venv venv

# Install Python packages in virtual environment
print_status "Installing Python packages in virtual environment..."
sudo -u weatherstation "$INSTALL_DIR/venv/bin/pip" install \
    flask \
    flask-cors \
    requests \
    scikit-learn \
    numpy \
    joblib \
    pandas \
    gunicorn

print_header "STEP 5: Setup Configuration"

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

print_header "STEP 6: Setup Systemd Service"

# Create systemd service file
print_status "Creating systemd service..."
cat > /etc/systemd/system/weather-station.service << EOF
[Unit]
Description=Weather Station Backend Service
After=network.target

[Service]
Type=simple
User=weatherstation
Group=weatherstation
WorkingDirectory=$INSTALL_DIR
Environment=PATH=$INSTALL_DIR/venv/bin
ExecStart=$INSTALL_DIR/venv/bin/python app.py
ExecReload=/bin/kill -HUP \$MAINPID
Restart=always
RestartSec=10
StandardOutput=journal
StandardError=journal
SyslogIdentifier=weather-station

[Install]
WantedBy=multi-user.target
EOF

# Reload systemd
print_status "Reloading systemd..."
systemctl daemon-reload

print_header "STEP 7: Setup Firewall"

# Configure firewall (if ufw is available)
if command -v ufw; then
    print_status "Configuring firewall..."
    ufw allow 22/tcp    # SSH
    ufw allow 5000/tcp  # Weather Station API
    ufw allow 8080/tcp  # Optional: Web interface
    ufw --force enable
    print_status "Firewall configured"
else
    print_warning "UFW not found, skipping firewall configuration"
fi

print_header "STEP 8: Setup Log Rotation"

# Create logrotate configuration
print_status "Setting up log rotation..."
cat > /etc/logrotate.d/weather-station << EOF
/var/log/weather-station/*.log {
    daily
    missingok
    rotate 30
    compress
    delaycompress
    notifempty
    create 644 weatherstation weatherstation
    postrotate
        systemctl reload weather-station
    endscript
}
EOF

print_header "STEP 9: Install Monitoring Tools"

# Install monitoring tools
print_status "Installing monitoring tools..."
apt install -y \
    net-tools \
    iotop \
    nethogs \
    sysstat

print_header "STEP 10: Enable and Start Service"

# Enable service
print_status "Enabling weather-station service..."
systemctl enable weather-station

# Start service
print_status "Starting weather-station service..."
systemctl start weather-station

# Wait for service to start
sleep 3

print_header "DEPLOYMENT COMPLETED"
echo ""
echo -e "${GREEN}✅ Weather Station Server deployed successfully!${NC}"
echo ""
echo -e "${BLUE}Server Information:${NC}"
echo "Server IP: $SERVER_IP"
echo "API URL: http://$SERVER_IP:5000"
echo "Repository: https://github.com/$GITHUB_USERNAME/$REPO_NAME"
echo ""
echo -e "${BLUE}Service Commands:${NC}"
echo "Start:   systemctl start weather-station"
echo "Stop:    systemctl stop weather-station"
echo "Restart:  systemctl restart weather-station"
echo "Status:   systemctl status weather-station"
echo "Logs:     journalctl -u weather-station -f"
echo ""
echo -e "${BLUE}Update Commands:${NC}"
echo "cd $INSTALL_DIR"
echo "git pull origin main"
echo "systemctl restart weather-station"
echo ""
echo -e "${BLUE}Configuration:${NC}"
echo "Edit: nano /etc/weather-station/server.conf"
echo "View: cat /etc/weather-station/server.conf"
echo ""
echo -e "${BLUE}Testing:${NC}"
echo "API test: curl http://$SERVER_IP:5000"
echo "Health: curl http://$SERVER_IP:5000/api/health"
echo ""

# Test service
if systemctl is-active --quiet weather-station; then
    echo -e "${GREEN}✅ Service is running!${NC}"
    
    # Test API
    if curl -s http://localhost:5000 > /dev/null; then
        echo -e "${GREEN}✅ API is responding!${NC}"
    else
        echo -e "${YELLOW}⚠️  API not responding yet, check logs${NC}"
    fi
else
    echo -e "${RED}❌ Service failed to start!${NC}"
    echo "Check logs: journalctl -u weather-station -n 50"
fi

echo ""
echo -e "${GREEN}Deployment complete!${NC}"
echo -e "${BLUE}Access your Weather Station at: http://$SERVER_IP:5000${NC}"
