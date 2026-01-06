#!/bin/bash
# Weather Station Server Update Script
# Update from GitHub repository

set -e

echo "=========================================="
echo "  WEATHER STATION UPDATE"
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

# Configuration
INSTALL_DIR="/opt/weather-station"
GITHUB_USERNAME="your_github_username"
REPO_NAME="weather-station-server"

# Get server IP
SERVER_IP=$(hostname -I | awk '{print $1}')

print_header "UPDATE CONFIGURATION"
echo "Install Directory: $INSTALL_DIR"
echo "Repository: https://github.com/$GITHUB_USERNAME/$REPO_NAME"
echo "Server IP: $SERVER_IP"
echo ""

# Check if running as root
if [[ $EUID -ne 0 ]]; then
   print_error "This script must be run as root or with sudo"
   exit 1
fi

# Check if installation exists
if [ ! -d "$INSTALL_DIR" ]; then
    print_error "Weather Station not found at $INSTALL_DIR"
    print_status "Please run deployment script first"
    exit 1
fi

print_header "STEP 1: Backup Current Configuration"

# Backup current configuration
if [ -f /etc/weather-station/server.conf ]; then
    print_status "Backing up current configuration..."
    cp /etc/weather-station/server.conf /etc/weather-station/server.conf.backup.$(date +%Y%m%d_%H%M%S)
fi

print_header "STEP 2: Update from GitHub"

# Navigate to installation directory
cd "$INSTALL_DIR"

# Stash local changes (if any)
print_status "Stashing any local changes..."
sudo -u weatherstation git stash

# Pull latest changes
print_status "Pulling latest changes from GitHub..."
sudo -u weatherstation git pull origin main

# Update Python packages if requirements changed
if [ -f "requirements.txt" ]; then
    print_status "Updating Python packages..."
    sudo -u weatherstation "$INSTALL_DIR/venv/bin/pip" install -r requirements.txt
else
    print_status "Installing default Python packages..."
    sudo -u weatherstation "$INSTALL_DIR/venv/bin/pip" install \
        flask \
        flask-cors \
        requests \
        scikit-learn \
        numpy \
        joblib \
        pandas \
        gunicorn
fi

print_header "STEP 3: Update Configuration"

# Check if configuration template changed
if [ -f "config/server.conf.example" ]; then
    print_status "Checking configuration updates..."
    # Compare with current config and notify of changes
    if ! cmp -s "config/server.conf.example" "/etc/weather-station/server.conf"; then
        print_warning "Configuration template has changed!"
        print_status "Review and update: /etc/weather-station/server.conf"
        print_status "Template location: $INSTALL_DIR/config/server.conf.example"
    fi
fi

print_header "STEP 4: Update Service"

# Reload systemd if service file changed
if [ -f "scripts/weather-station.service" ]; then
    print_status "Updating systemd service..."
    cp scripts/weather-station.service /etc/systemd/system/weather-station.service
    systemctl daemon-reload
fi

# Restart service
print_status "Restarting weather-station service..."
systemctl restart weather-station

# Wait for service to start
sleep 3

print_header "STEP 5: Verification"

# Check service status
if systemctl is-active --quiet weather-station; then
    print_status "Service is running!"
    
    # Test API
    if curl -s http://localhost:5000 > /dev/null; then
        print_status "API is responding!"
    else
        print_warning "API not responding yet, check logs"
    fi
    
    # Test health endpoint
    if curl -s http://localhost:5000/api/health > /dev/null; then
        print_status "Health endpoint is working!"
    else
        print_warning "Health endpoint not responding"
    fi
else
    print_error "Service failed to start!"
    print_status "Check logs: journalctl -u weather-station -n 50"
    
    # Try to restore backup
    if [ -f "/etc/weather-station/server.conf.backup.$(date +%Y%m%d_%H%M%S)" ]; then
        print_status "Attempting to restore backup configuration..."
        cp /etc/weather-station/server.conf.backup.$(date +%Y%m%d_%H%M%S) /etc/weather-station/server.conf
        systemctl restart weather-station
        sleep 3
        
        if systemctl is-active --quiet weather-station; then
            print_status "Service restored with backup configuration!"
        else
            print_error "Service still failing, manual intervention required"
        fi
    fi
fi

print_header "UPDATE COMPLETED"
echo ""
echo -e "${GREEN}✅ Weather Station Server updated successfully!${NC}"
echo ""
echo -e "${BLUE}Server Information:${NC}"
echo "Server IP: $SERVER_IP"
echo "API URL: http://$SERVER_IP:5000"
echo "Repository: https://github.com/$GITHUB_USERNAME/$REPO_NAME"
echo ""
echo -e "${BLUE}Service Status:${NC}"
systemctl status weather-station --no-pager -l
echo ""
echo -e "${BLUE}Recent Logs:${NC}"
journalctl -u weather-station -n 10 --no-pager
echo ""
echo -e "${GREEN}Update complete!${NC}"
echo -e "${BLUE}Access your Weather Station at: http://$SERVER_IP:5000${NC}"
