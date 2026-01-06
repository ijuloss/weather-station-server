#!/bin/bash
# Weather Station Server Installation Script
# Optimized for Debian 12 with CasaOS

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Configuration
WEATHER_USER="weather-station"
WEATHER_DIR="/opt/weather-station"
SERVICE_NAME="weather-station"
PYTHON_VERSION="3.11"

echo -e "${GREEN}Weather Station Server Installation${NC}"
echo "=================================="
echo "This script will install Weather Station Server on Debian 12"
echo ""

# Check if running as root
if [[ $EUID -ne 0 ]]; then
   echo -e "${RED}This script must be run as root${NC}"
   exit 1
fi

# Check Debian version
if ! grep -q "Debian.*12" /etc/os-release; then
    echo -e "${RED}This script is designed for Debian 12${NC}"
    exit 1
fi

echo -e "${YELLOW}Step 1: System Update${NC}"
apt update && apt upgrade -y

echo -e "${YELLOW}Step 2: Install Dependencies${NC}"
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

echo -e "${YELLOW}Step 3: Create Weather Station User${NC}"
if ! id "$WEATHER_USER" &>/dev/null; then
    useradd -r -s /bin/false -d $WEATHER_DIR $WEATHER_USER
    echo "Created user: $WEATHER_USER"
fi

echo -e "${YELLOW}Step 4: Create Directories${NC}"
mkdir -p $WEATHER_DIR/{backend,frontend,config,scripts,logs,data,models,backups}
mkdir -p /var/log/weather-station
mkdir -p /var/lib/weather-station
mkdir -p /etc/weather-station
mkdir -p /run/weather-station

echo -e "${YELLOW}Step 5: Set Permissions${NC}"
chown -R $WEATHER_USER:$WEATHER_USER $WEATHER_DIR
chown -R $WEATHER_USER:$WEATHER_USER /var/log/weather-station
chown -R $WEATHER_USER:$WEATHER_USER /var/lib/weather-station
chown -R $WEATHER_USER:$WEATHER_USER /etc/weather-station
chown -R $WEATHER_USER:$WEATHER_USER /run/weather-station

echo -e "${YELLOW}Step 6: Install Python Dependencies${NC}"
cd $WEATHER_DIR
python3 -m venv venv
source venv/bin/activate
pip install --upgrade pip
pip install \
    flask \
    flask-cors \
    requests \
    scikit-learn \
    numpy \
    joblib \
    gunicorn

echo -e "${YELLOW}Step 7: Setup Configuration${NC}"
# Copy configuration files
cp config/server.conf /etc/weather-station/
cp config/server.conf.example /etc/weather-station/

echo -e "${YELLOW}Step 8: Create Systemd Service${NC}"
cat > /etc/systemd/system/$SERVICE_NAME.service << EOF
[Unit]
Description=Weather Station Backend Server
After=network.target

[Service]
Type=simple
User=$WEATHER_USER
Group=$WEATHER_USER
WorkingDirectory=$WEATHER_DIR
Environment=PATH=$WEATHER_DIR/venv/bin
Environment=PYTHONPATH=$WEATHER_DIR
ExecStart=$WEATHER_DIR/venv/bin/python backend/app.py
ExecReload=/bin/kill -HUP \$MAINPID
Restart=always
RestartSec=10
StandardOutput=journal
StandardError=journal
SyslogIdentifier=weather-station

# Security
NoNewPrivileges=true
PrivateTmp=true
ProtectSystem=strict
ProtectHome=true
ReadWritePaths=/var/lib/weather-station /var/log/weather-station /etc/weather-station /run/weather-station

[Install]
WantedBy=multi-user.target
EOF

echo -e "${YELLOW}Step 9: Setup Nginx Reverse Proxy${NC}"
cat > /etc/nginx/sites-available/$SERVICE_NAME << EOF
server {
    listen 80;
    server_name _;
    
    # Frontend
    location / {
        root $WEATHER_DIR/frontend;
        index index.html;
        try_files \$uri \$uri/ =404;
    }
    
    # Backend API
    location /api/ {
        proxy_pass http://127.0.0.1:5000;
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto \$scheme;
        proxy_connect_timeout 30;
        proxy_send_timeout 30;
        proxy_read_timeout 30;
    }
    
    # Enable gzip compression
    gzip on;
    gzip_vary on;
    gzip_min_length 1024;
    gzip_types text/plain text/css text/xml text/javascript application/javascript application/xml+rss application/json;
}
EOF

# Enable Nginx site
ln -sf /etc/nginx/sites-available/$SERVICE_NAME /etc/nginx/sites-enabled/
rm -f /etc/nginx/sites-enabled/default

echo -e "${YELLOW}Step 10: Setup Log Rotation${NC}"
cat > /etc/logrotate.d/weather-station << EOF
/var/log/weather-station/*.log {
    daily
    missingok
    rotate 30
    compress
    delaycompress
    notifempty
    create 644 $WEATHER_USER $WEATHER_USER
    postrotate
        systemctl reload weather-station
    endscript
}
EOF

echo -e "${YELLOW}Step 11: Setup Firewall${NC}"
if command -v ufw &> /dev/null; then
    ufw allow 22/tcp
    ufw allow 80/tcp
    ufw allow 443/tcp
    ufw --force enable
fi

echo -e "${YELLOW}Step 12: Enable and Start Services${NC}"
systemctl daemon-reload
systemctl enable $SERVICE_NAME
systemctl start $SERVICE_NAME
systemctl enable nginx
systemctl restart nginx

echo -e "${YELLOW}Step 13: Setup CasaOS Integration${NC}"
# Create CasaOS app manifest
cat > /etc/casaos/apps/weather-station.json << EOF
{
    "name": "Weather Station",
    "version": "3.0",
    "description": "IoT Weather Station with AI Predictions",
    "icon": "https://raw.githubusercontent.com/weather-station/icon.png",
    "port": 80,
    "author": "Weather Station Team",
    "category": "IoT",
    "permissions": [
        "network",
        "storage"
    ],
    "dependencies": [],
    "install_script": "/opt/weather-station/scripts/install.sh",
    "uninstall_script": "/opt/weather-station/scripts/uninstall.sh",
    "update_script": "/opt/weather-station/scripts/update.sh"
}
EOF

echo -e "${YELLOW}Step 14: Create Management Scripts${NC}"
# Create management scripts
cat > $WEATHER_DIR/scripts/backup.sh << 'EOF'
#!/bin/bash
# Backup Weather Station Data
BACKUP_DIR="/var/lib/weather-station/backups"
DATE=$(date +%Y%m%d_%H%M%S)
BACKUP_FILE="$BACKUP_DIR/weather_station_$DATE.tar.gz"

# Create backup
tar -czf $BACKUP_FILE \
    /var/lib/weather-station/data \
    /var/lib/weather-station/models \
    /etc/weather-station \
    /var/log/weather-station

echo "Backup created: $BACKUP_FILE"

# Keep only last 7 backups
find $BACKUP_DIR -name "weather_station_*.tar.gz" -mtime +7 -delete
EOF

cat > $WEATHER_DIR/scripts/restore.sh << 'EOF'
#!/bin/bash
# Restore Weather Station Data
if [ $# -eq 0 ]; then
    echo "Usage: $0 <backup_file>"
    exit 1
fi

BACKUP_FILE=$1
if [ ! -f "$BACKUP_FILE" ]; then
    echo "Backup file not found: $BACKUP_FILE"
    exit 1
fi

# Stop services
systemctl stop weather-station

# Restore backup
tar -xzf $BACKUP_FILE -C /

# Fix permissions
chown -R weather-station:weather-station /var/lib/weather-station
chown -R weather-station:weather-station /etc/weather-station
chown -R weather-station:weather-station /var/log/weather-station

# Start services
systemctl start weather-station

echo "Restore completed from: $BACKUP_FILE"
EOF

cat > $WEATHER_DIR/scripts/update.sh << 'EOF'
#!/bin/bash
# Update Weather Station
cd /opt/weather-station
git pull origin main
systemctl restart weather-station
echo "Weather Station updated"
EOF

cat > $WEATHER_DIR/scripts/status.sh << 'EOF'
#!/bin/bash
# Weather Station Status
echo "=== Weather Station Status ==="
echo "Service: $(systemctl is-active weather-station)"
echo "Nginx: $(systemctl is-active nginx)"
echo "Data Points: $(find /var/lib/weather-station/data -name "*.json" | wc -l)"
echo "Last Backup: $(ls -t /var/lib/weather-station/backups/*.tar.gz 2>/dev/null | head -1 | xargs -I {} basename {})"
echo "Disk Usage: $(du -sh /var/lib/weather-station | cut -f1)"
echo "Memory Usage: $(ps aux | grep weather-station | grep -v grep | awk '{sum+=$6} END {print sum/1024 " MB"}')"
EOF

# Make scripts executable
chmod +x $WEATHER_DIR/scripts/*.sh

echo -e "${YELLOW}Step 15: Final Setup${NC}"
# Create startup script
cat > $WEATHER_DIR/scripts/start.sh << 'EOF'
#!/bin/bash
# Start Weather Station Services
systemctl start weather-station
systemctl start nginx
echo "Weather Station services started"
EOF

cat > $WEATHER_DIR/scripts/stop.sh << 'EOF'
#!/bin/bash
# Stop Weather Station Services
systemctl stop weather-station
systemctl stop nginx
echo "Weather Station services stopped"
EOF

chmod +x $WEATHER_DIR/scripts/start.sh $WEATHER_DIR/scripts/stop.sh

echo -e "${GREEN}Installation Complete!${NC}"
echo ""
echo "Weather Station Server is now installed and running."
echo ""
echo "Access Information:"
echo "  Dashboard: http://$(hostname -I | awk '{print $1}')/"
echo "  API: http://$(hostname -I | awk '{print $1}')/api/"
echo "  Config: /etc/weather-station/server.conf"
echo "  Logs: /var/log/weather-station/app.log"
echo "  Data: /var/lib/weather-station/"
echo ""
echo "Management Commands:"
echo "  Start: $WEATHER_DIR/scripts/start.sh"
echo "  Stop: $WEATHER_DIR/scripts/stop.sh"
echo "  Status: $WEATHER_DIR/scripts/status.sh"
echo "  Backup: $WEATHER_DIR/scripts/backup.sh"
echo "  Restore: $WEATHER_DIR/scripts/restore.sh <backup_file>"
echo ""
echo "Service Commands:"
echo "  systemctl status weather-station"
echo "  systemctl restart weather-station"
echo "  journalctl -u weather-station -f"
echo ""
echo -e "${GREEN}Weather Station Server is ready for CasaOS!${NC}"
