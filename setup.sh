#!/bin/bash
# Weather Station Server Quick Setup for Debian 12 with CasaOS

set -e

# Colors
GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
NC='\033[0m'

echo -e "${GREEN}Weather Station Server Setup${NC}"
echo "=================================="
echo "Quick setup for Debian 12 with CasaOS"
echo ""

# Check if running as root
if [[ $EUID -ne 0 ]]; then
   echo -e "${YELLOW}This script must be run as root${NC}"
   echo "Please run: sudo ./setup.sh"
   exit 1
fi

# Check Debian version
if ! grep -q "Debian.*12" /etc/os-release; then
    echo -e "${YELLOW}This script is designed for Debian 12${NC}"
    echo "Continue anyway? (y/N): "
    read -r response
    if [[ ! $response =~ ^[Yy]$ ]]; then
        exit 1
    fi
fi

echo -e "${BLUE}Step 1: System Update${NC}"
apt update && apt upgrade -y

echo -e "${BLUE}Step 2: Install Dependencies${NC}"
apt install -y \
    python3 \
    python3-pip \
    python3-venv \
    python3-dev \
    build-essential \
    curl \
    wget \
    git \
    nginx \
    systemd \
    logrotate \
    supervisor

echo -e "${BLUE}Step 3: Create Weather Station User${NC}"
if ! id "weather-station" &>/dev/null; then
    useradd -r -s /bin/false -d /opt/weather-station weather-station
    echo "Created user: weather-station"
fi

echo -e "${BLUE}Step 4: Create Directories${NC}"
mkdir -p /opt/weather-station/{backend,frontend,config,scripts,logs,data,models,backups}
mkdir -p /var/log/weather-station
mkdir -p /var/lib/weather-station
mkdir -p /etc/weather-station
mkdir -p /run/weather-station

echo -e "${BLUE}Step 5: Set Permissions${NC}"
chown -R weather-station:weather-station /opt/weather-station
chown -R weather-station:weather-station /var/log/weather-station
chown -R weather-station:weather-station /var/lib/weather-station
chown -R weather-station:weather-station /etc/weather-station
chown -R weather-station:weather-station /run/weather-station

echo -e "${BLUE}Step 6: Install Python Dependencies${NC}"
cd /opt/weather-station
python3 -m venv venv
source venv/bin/activate
pip install --upgrade pip
pip install flask flask-cors requests scikit-learn numpy joblib gunicorn

echo -e "${BLUE}Step 7: Setup Configuration${NC}"
# Create basic configuration
cat > /etc/weather-station/server.conf << 'EOF'
# Weather Station Server Configuration
HOST=0.0.0.0
PORT=5000
DEBUG=false
LOG_LEVEL=INFO
LOG_FILE=/var/log/weather-station/app.log
DATA_DIR=/var/lib/weather-station
CONFIG_DIR=/etc/weather-station
MODEL_TRAINING_INTERVAL=50
MAX_LOCAL_READINGS=1000
REQUEST_TIMEOUT=30
BACKUP_INTERVAL=3600
EOF

echo -e "${BLUE}Step 8: Create Systemd Service${NC}"
cat > /etc/systemd/system/weather-station.service << 'EOF'
[Unit]
Description=Weather Station Backend Server
After=network.target

[Service]
Type=simple
User=weather-station
Group=weather-station
WorkingDirectory=/opt/weather-station
Environment=PATH=/opt/weather-station/venv/bin
ExecStart=/opt/weather-station/venv/bin/python backend/app.py
Restart=always
RestartSec=10
StandardOutput=journal
StandardError=journal
SyslogIdentifier=weather-station

[Install]
WantedBy=multi-user.target
EOF

echo -e "${BLUE}Step 9: Setup Nginx${NC}"
cat > /etc/nginx/sites-available/weather-station << 'EOF'
server {
    listen 80;
    server_name _;
    
    location / {
        root /opt/weather-station/frontend;
        index index.html;
        try_files $uri $uri/ =404;
    }
    
    location /api/ {
        proxy_pass http://127.0.0.1:5000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
EOF

ln -sf /etc/nginx/sites-available/weather-station /etc/nginx/sites-enabled/
rm -f /etc/nginx/sites-enabled/default

echo -e "${BLUE}Step 10: Enable Services${NC}"
systemctl daemon-reload
systemctl enable weather-station
systemctl start weather-station
systemctl enable nginx
systemctl restart nginx

echo -e "${BLUE}Step 11: Setup Firewall${NC}"
if command -v ufw &> /dev/null; then
    ufw allow 22/tcp
    ufw allow 80/tcp
    ufw --force enable
fi

echo -e "${GREEN}Setup Complete!${NC}"
echo ""
echo "Weather Station Server is now running."
echo ""
echo "Access Information:"
echo "  Dashboard: http://$(hostname -I | awk '{print $1}')/"
echo "  API: http://$(hostname -I | awk '{print $1}')/api/"
echo "  Config: /etc/weather-station/server.conf"
echo "  Logs: /var/log/weather-station/app.log"
echo ""
echo "Next Steps:"
echo "  1. Copy your application files to /opt/weather-station/"
echo "  2. Restart service: systemctl restart weather-station"
echo "  3. Check status: systemctl status weather-station"
echo ""
echo -e "${GREEN}Weather Station Server is ready!${NC}"
