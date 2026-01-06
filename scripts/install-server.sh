#!/bin/bash
# Weather Station Server Setup Script for Debian 12 with CasaOS
# Run this script on your server as root or with sudo

set -e

echo "=========================================="
echo "  WEATHER STATION SERVER SETUP"
echo "  Debian 12 + CasaOS"
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

# Check if running as root
if [[ $EUID -ne 0 ]]; then
   print_error "This script must be run as root or with sudo"
   exit 1
fi

print_header "STEP 1: System Update & Dependencies"

# Update system
print_status "Updating system packages..."
apt update && apt upgrade -y

# Install essential packages
print_status "Installing essential packages..."
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

print_header "STEP 2: Create System User & Directories"

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

print_header "STEP 3: Setup Systemd Service"

# Create systemd service file
print_status "Creating systemd service..."
cat > /etc/systemd/system/weather-station.service << 'EOF'
[Unit]
Description=Weather Station Backend Service
After=network.target

[Service]
Type=simple
User=weatherstation
Group=weatherstation
WorkingDirectory=/opt/weather-station
Environment=PATH=/opt/weather-station/venv/bin
ExecStart=/opt/weather-station/venv/bin/python app.py
ExecReload=/bin/kill -HUP $MAINPID
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

print_header "STEP 4: Setup Firewall"

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

print_header "STEP 5: Setup Log Rotation"

# Create logrotate configuration
print_status "Setting up log rotation..."
cat > /etc/logrotate.d/weather-station << 'EOF'
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

print_header "STEP 6: Install Monitoring Tools"

# Install monitoring tools
print_status "Installing monitoring tools..."
apt install -y \
    net-tools \
    iotop \
    nethogs \
    sysstat

print_header "STEP 7: Setup Auto-start"

# Enable service
print_status "Enabling weather-station service..."
systemctl enable weather-station

print_header "INSTALLATION COMPLETED"
echo -e "${GREEN}✅ Weather Station Server setup completed!${NC}"
echo ""
echo -e "${BLUE}Next steps:${NC}"
echo "1. Transfer files from laptop to server"
echo "2. Configure settings in /etc/weather-station/server.conf"
echo "3. Start service: systemctl start weather-station"
echo "4. Check status: systemctl status weather-station"
echo "5. View logs: journalctl -u weather-station -f"
echo ""
echo -e "${YELLOW}Important:${NC} Reboot server before starting service"
echo ""
echo -e "${BLUE}Service commands:${NC}"
echo "Start:   systemctl start weather-station"
echo "Stop:    systemctl stop weather-station"
echo "Restart:  systemctl restart weather-station"
echo "Status:   systemctl status weather-station"
echo "Logs:     journalctl -u weather-station -f"
echo ""
echo -e "${GREEN}Setup complete!${NC}"
