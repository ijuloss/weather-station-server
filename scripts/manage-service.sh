#!/bin/bash
# Weather Station Service Management Script
# For managing the weather station service on Debian 12

set -e

# Colors
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
BLUE='\033[0;34m'
NC='\033[0m'

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

# Get server IP
SERVER_IP=$(hostname -I | awk '{print $1}')

show_menu() {
    clear
    print_header "WEATHER STATION SERVICE MANAGEMENT"
    echo ""
    echo -e "${GREEN}Server IP: $SERVER_IP${NC}"
    echo ""
    echo "Select an option:"
    echo ""
    echo "1. Start Weather Station Service"
    echo "2. Stop Weather Station Service"
    echo "3. Restart Weather Station Service"
    echo "4. Check Service Status"
    echo "5. View Service Logs"
    echo "6. Test API Connection"
    echo "7. Edit Configuration"
    echo "8. View Configuration"
    echo "9. Backup Data"
    echo "10. Restore Data"
    echo "11. Update System"
    echo "12. Uninstall Service"
    echo "0. Exit"
    echo ""
    echo -n "Enter choice [0-12]: "
}

start_service() {
    print_status "Starting Weather Station service..."
    systemctl start weather-station
    sleep 2
    show_status
}

stop_service() {
    print_status "Stopping Weather Station service..."
    systemctl stop weather-station
    sleep 2
    show_status
}

restart_service() {
    print_status "Restarting Weather Station service..."
    systemctl restart weather-station
    sleep 2
    show_status
}

show_status() {
    print_header "SERVICE STATUS"
    if systemctl is-active --quiet weather-station; then
        echo -e "${GREEN}● Weather Station Service: RUNNING${NC}"
        echo -e "${GREEN}  Status: Active${NC}"
        
        # Check if API is responding
        if curl -s http://localhost:5000 > /dev/null; then
            echo -e "${GREEN}  API: Responding${NC}"
        else
            echo -e "${YELLOW}  API: Not responding${NC}"
        fi
    else
        echo -e "${RED}● Weather Station Service: STOPPED${NC}"
        echo -e "${RED}  Status: Inactive${NC}"
    fi
    
    echo ""
    echo "Service details:"
    systemctl status weather-station --no-pager -l
}

view_logs() {
    print_header "SERVICE LOGS"
    echo "Showing last 50 lines of logs..."
    echo "Press Ctrl+C to exit"
    echo ""
    journalctl -u weather-station -n 50 -f
}

test_api() {
    print_header "API CONNECTION TEST"
    echo "Testing Weather Station API..."
    echo ""
    
    # Test basic endpoint
    echo "Testing root endpoint..."
    if curl -s http://localhost:5000 | python3 -m json.tool; then
        echo -e "${GREEN}✅ Root API: Working${NC}"
    else
        echo -e "${RED}❌ Root API: Failed${NC}"
    fi
    
    echo ""
    echo "Testing health endpoint..."
    if curl -s http://localhost:5000/api/health | python3 -m json.tool; then
        echo -e "${GREEN}✅ Health API: Working${NC}"
    else
        echo -e "${RED}❌ Health API: Failed${NC}"
    fi
    
    echo ""
    echo "External access test:"
    echo "curl http://$SERVER_IP:5000"
    echo ""
    echo "Dashboard access:"
    echo "http://$SERVER_IP:5000"
}

edit_config() {
    print_status "Opening configuration file..."
    nano /etc/weather-station/server.conf
    print_warning "After editing, restart service to apply changes"
}

view_config() {
    print_header "CURRENT CONFIGURATION"
    if [ -f /etc/weather-station/server.conf ]; then
        cat /etc/weather-station/server.conf
    else
        print_error "Configuration file not found!"
    fi
}

backup_data() {
    print_status "Creating data backup..."
    BACKUP_DIR="/var/lib/weather-station/backups"
    BACKUP_FILE="$BACKUP_DIR/backup_$(date +%Y%m%d_%H%M%S).json"
    
    mkdir -p "$BACKUP_DIR"
    
    # Call backup API
    curl -s -X POST http://localhost:5000/api/backup | python3 -m json.tool > "$BACKUP_FILE"
    
    if [ $? -eq 0 ]; then
        print_status "Backup created: $BACKUP_FILE"
    else
        print_error "Backup failed"
    fi
}

restore_data() {
    print_status "Restoring data from backup..."
    echo "Available backups:"
    ls -la /var/lib/weather-station/backups/backup_*.json 2>/dev/null || echo "No backups found"
    echo ""
    echo -n "Enter backup filename (or press Enter to cancel): "
    read BACKUP_FILE
    
    if [ -n "$BACKUP_FILE" ]; then
        curl -s -X POST http://localhost:5000/api/restore | python3 -m json.tool
        print_status "Restore completed"
    fi
}

update_system() {
    print_status "Updating Weather Station system..."
    
    # Update system packages
    apt update && apt upgrade -y
    
    # Update Python packages
    source /opt/weather-station/venv/bin/activate
    pip install --upgrade flask flask-cors requests scikit-learn numpy joblib pandas gunicorn
    
    # Restart service
    systemctl restart weather-station
    
    print_status "System updated and service restarted"
}

uninstall_service() {
    print_warning "This will completely remove Weather Station service"
    echo -n "Are you sure? (yes/no): "
    read CONFIRM
    
    if [ "$CONFIRM" = "yes" ]; then
        print_status "Stopping service..."
        systemctl stop weather-station
        systemctl disable weather-station
        
        print_status "Removing files..."
        rm -rf /opt/weather-station
        rm -rf /etc/weather-station
        rm -rf /var/lib/weather-station
        rm -rf /var/log/weather-station
        rm -f /etc/systemd/system/weather-station.service
        rm -f /etc/logrotate.d/weather-station
        
        systemctl daemon-reload
        
        print_status "Removing user weatherstation..."
        userdel -r weatherstation 2>/dev/null || true
        
        print_status "Weather Station service uninstalled"
    else
        print_status "Uninstall cancelled"
    fi
}

# Main menu loop
while true; do
    show_menu
    read choice
    
    case $choice in
        1)
            start_service
            ;;
        2)
            stop_service
            ;;
        3)
            restart_service
            ;;
        4)
            show_status
            ;;
        5)
            view_logs
            ;;
        6)
            test_api
            ;;
        7)
            edit_config
            ;;
        8)
            view_config
            ;;
        9)
            backup_data
            ;;
        10)
            restore_data
            ;;
        11)
            update_system
            ;;
        12)
            uninstall_service
            ;;
        0)
            print_status "Exiting..."
            exit 0
            ;;
        *)
            print_error "Invalid option. Please try again."
            ;;
    esac
    
    echo ""
    echo -n "Press Enter to continue..."
    read
done
