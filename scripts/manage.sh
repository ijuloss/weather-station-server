#!/bin/bash
# Weather Station Server Management Script

set -e

# Configuration
WEATHER_DIR="/opt/weather-station"
SERVICE_NAME="weather-station"
LOG_FILE="/var/log/weather-station/management.log"

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

# Logging
log() {
    echo "$(date '+%Y-%m-%d %H:%M:%S') - $1" | tee -a $LOG_FILE
}

# Check if running as root
check_root() {
    if [[ $EUID -ne 0 ]]; then
        echo -e "${RED}This script must be run as root${NC}"
        exit 1
    fi
}

# Status check
status() {
    echo -e "${BLUE}Weather Station Server Status${NC}"
    echo "================================"
    
    # Service status
    if systemctl is-active --quiet $SERVICE_NAME; then
        echo -e "Service: ${GREEN}Running${NC}"
    else
        echo -e "Service: ${RED}Stopped${NC}"
    fi
    
    # Nginx status
    if systemctl is-active --quiet nginx; then
        echo -e "Nginx: ${GREEN}Running${NC}"
    else
        echo -e "Nginx: ${RED}Stopped${NC}"
    fi
    
    # Data points
    if [ -f "$WEATHER_DIR/data/data_points.json" ]; then
        data_points=$(jq '. | length' $WEATHER_DIR/data/data_points.json 2>/dev/null || echo "0")
    else
        data_points="0"
    fi
    echo -e "Data Points: ${YELLOW}$data_points${NC}"
    
    # Disk usage
    disk_usage=$(du -sh $WEATHER_DIR 2>/dev/null | cut -f1 || echo "Unknown")
    echo -e "Disk Usage: ${YELLOW}$disk_usage${NC}"
    
    # Memory usage
    memory_usage=$(ps aux | grep weather-station | grep -v grep | awk '{sum+=$6} END {print sum/1024 " MB"}' 2>/dev/null || echo "0 MB")
    echo -e "Memory Usage: ${YELLOW}$memory_usage${NC}"
    
    # Last backup
    last_backup=$(ls -t $WEATHER_DIR/backups/*.tar.gz 2>/dev/null | head -1 | xargs -I {} basename {} 2>/dev/null || echo "No backups")
    echo -e "Last Backup: ${YELLOW}$last_backup${NC}"
    
    # Server IP
    server_ip=$(hostname -I | awk '{print $1}' 2>/dev/null || echo "Unknown")
    echo -e "Server IP: ${GREEN}$server_ip${NC}"
    
    echo ""
    echo "Access URLs:"
    echo "  Dashboard: http://$server_ip/"
    echo "  API: http://$server_ip/api/"
    echo "  Health: http://$server_ip/api/health"
}

# Start services
start() {
    echo -e "${GREEN}Starting Weather Station Services${NC}"
    systemctl start $SERVICE_NAME
    systemctl start nginx
    echo "Services started"
    log "Services started"
}

# Stop services
stop() {
    echo -e "${RED}Stopping Weather Station Services${NC}"
    systemctl stop $SERVICE_NAME
    systemctl stop nginx
    echo "Services stopped"
    log "Services stopped"
}

# Restart services
restart() {
    echo -e "${YELLOW}Restarting Weather Station Services${NC}"
    systemctl restart $SERVICE_NAME
    systemctl restart nginx
    echo "Services restarted"
    log "Services restarted"
}

# Backup data
backup() {
    echo -e "${BLUE}Creating Backup${NC}"
    
    BACKUP_DIR="$WEATHER_DIR/backups"
    DATE=$(date +%Y%m%d_%H%M%S)
    BACKUP_FILE="$BACKUP_DIR/weather_station_$DATE.tar.gz"
    
    # Create backup
    tar -czf $BACKUP_FILE \
        $WEATHER_DIR/data \
        $WEATHER_DIR/models \
        /etc/weather-station \
        /var/log/weather-station 2>/dev/null
    
    echo "Backup created: $BACKUP_FILE"
    log "Backup created: $BACKUP_FILE"
    
    # Keep only last 7 backups
    find $BACKUP_DIR -name "weather_station_*.tar.gz" -mtime +7 -delete 2>/dev/null
    echo "Old backups cleaned up"
}

# Restore data
restore() {
    if [ $# -eq 0 ]; then
        echo -e "${RED}Usage: $0 restore <backup_file>${NC}"
        exit 1
    fi
    
    BACKUP_FILE=$1
    if [ ! -f "$BACKUP_FILE" ]; then
        echo -e "${RED}Backup file not found: $BACKUP_FILE${NC}"
        exit 1
    fi
    
    echo -e "${YELLOW}Restoring from backup${NC}"
    
    # Stop services
    systemctl stop $SERVICE_NAME
    
    # Restore backup
    tar -xzf $BACKUP_FILE -C / 2>/dev/null
    
    # Fix permissions
    chown -R weather-station:weather-station $WEATHER_DIR
    chown -R weather-station:weather-station /var/lib/weather-station
    chown -R weather-station:weather-station /etc/weather-station
    chown -R weather-station:weather-station /var/log/weather-station
    
    # Start services
    systemctl start $SERVICE_NAME
    
    echo "Restore completed from: $BACKUP_FILE"
    log "Restore completed from: $BACKUP_FILE"
}

# Update system
update() {
    echo -e "${BLUE}Updating Weather Station${NC}"
    
    # Update system packages
    apt update && apt upgrade -y
    
    # Update Python dependencies
    cd $WEATHER_DIR
    source venv/bin/activate
    pip install --upgrade pip
    pip install -r requirements.txt
    
    # Restart services
    systemctl restart $SERVICE_NAME
    
    echo "Weather Station updated"
    log "Weather Station updated"
}

# Logs
logs() {
    echo -e "${BLUE}Weather Station Logs${NC}"
    echo "=================="
    
    # Service logs
    echo -e "${YELLOW}Service Logs:${NC}"
    journalctl -u $SERVICE_NAME -n 50 --no-pager
    
    echo ""
    echo -e "${YELLOW}Application Logs:${NC}"
    tail -n 50 /var/log/weather-station/app.log 2>/dev/null || echo "No application logs found"
    
    echo ""
    echo -e "${YELLOW}Nginx Logs:${NC}"
    journalctl -u nginx -n 20 --no-pager
}

# Configuration
config() {
    echo -e "${BLUE}Weather Station Configuration${NC}"
    echo "================================"
    
    if [ -f "/etc/weather-station/server.conf" ]; then
        echo "Current configuration:"
        cat /etc/weather-station/server.conf
    else
        echo "Configuration file not found"
    fi
}

# Health check
health() {
    echo -e "${BLUE}Weather Station Health Check${NC}"
    echo "================================"
    
    # Check service
    if systemctl is-active --quiet $SERVICE_NAME; then
        echo -e "Service: ${GREEN}OK${NC}"
    else
        echo -e "Service: ${RED}FAILED${NC}"
    fi
    
    # Check API
    if curl -f http://localhost/api/health &>/dev/null; then
        echo -e "API: ${GREEN}OK${NC}"
    else
        echo -e "API: ${RED}FAILED${NC}"
    fi
    
    # Check disk space
    disk_usage=$(df $WEATHER_DIR | tail -1 | awk '{print $5}' | sed 's/%//')
    if [ $disk_usage -lt 80 ]; then
        echo -e "Disk Space: ${GREEN}OK${NC} (${disk_usage}%)"
    else
        echo -e "Disk Space: ${RED}LOW${NC} (${disk_usage}%)"
    fi
    
    # Check memory
    memory_usage=$(free | grep Mem | awk '{printf "%.0f", $3/$2 * 100.0}')
    if [ $memory_usage -lt 80 ]; then
        echo -e "Memory: ${GREEN}OK${NC} (${memory_usage}%)"
    else
        echo -e "Memory: ${RED}HIGH${NC} (${memory_usage}%)"
    fi
}

# Install
install() {
    echo -e "${GREEN}Installing Weather Station Server${NC}"
    echo "This will install Weather Station on your Debian 12 server"
    echo ""
    read -p "Continue? (y/N): " -n 1 -r
    echo
    
    if [[ $REPLY =~ ^[Yy]$ ]]; then
        # Run installation script
        if [ -f "$WEATHER_DIR/scripts/install-debian12.sh" ]; then
            bash $WEATHER_DIR/scripts/install-debian12.sh
        else
            echo -e "${RED}Installation script not found${NC}"
            exit 1
        fi
    else
        echo "Installation cancelled"
    fi
}

# Uninstall
uninstall() {
    echo -e "${RED}Uninstalling Weather Station Server${NC}"
    echo "This will remove Weather Station and all data"
    echo ""
    read -p "Continue? (y/N): " -n 1 -r
    echo
    
    if [[ $REPLY =~ ^[Yy]$ ]]; then
        # Stop services
        systemctl stop $SERVICE_NAME 2>/dev/null || true
        systemctl stop nginx 2>/dev/null || true
        
        # Disable services
        systemctl disable $SERVICE_NAME 2>/dev/null || true
        
        # Remove files
        rm -rf $WEATHER_DIR
        rm -rf /var/lib/weather-station
        rm -rf /var/log/weather-station
        rm -rf /etc/weather-station
        rm -f /etc/systemd/system/$SERVICE_NAME.service
        rm -f /etc/nginx/sites-available/$SERVICE_NAME
        rm -f /etc/nginx/sites-enabled/$SERVICE_NAME
        rm -f /etc/logrotate.d/weather-station
        
        # Reload systemd
        systemctl daemon-reload
        
        # Restart nginx
        systemctl restart nginx
        
        echo "Weather Station uninstalled"
        log "Weather Station uninstalled"
    else
        echo "Uninstall cancelled"
    fi
}

# Help
help() {
    echo "Weather Station Server Management Script"
    echo "======================================="
    echo ""
    echo "Usage: $0 <command>"
    echo ""
    echo "Commands:"
    echo "  status      - Show server status"
    echo "  start       - Start services"
    echo "  stop        - Stop services"
    echo "  restart     - Restart services"
    echo "  backup      - Create backup"
    echo "  restore     - Restore from backup"
    echo "  update      - Update system"
    echo "  logs        - Show logs"
    echo "  config      - Show configuration"
    echo "  health      - Health check"
    echo "  install     - Install Weather Station"
    echo "  uninstall   - Uninstall Weather Station"
    echo "  help        - Show this help"
    echo ""
    echo "Examples:"
    echo "  $0 status"
    echo "  $0 backup"
    echo "  $0 restore /path/to/backup.tar.gz"
}

# Main
case "$1" in
    status)
        status
        ;;
    start)
        check_root
        start
        ;;
    stop)
        check_root
        stop
        ;;
    restart)
        check_root
        restart
        ;;
    backup)
        check_root
        backup
        ;;
    restore)
        check_root
        restore "$2"
        ;;
    update)
        check_root
        update
        ;;
    logs)
        logs
        ;;
    config)
        config
        ;;
    health)
        health
        ;;
    install)
        check_root
        install
        ;;
    uninstall)
        check_root
        uninstall
        ;;
    help|--help|-h)
        help
        ;;
    *)
        echo -e "${RED}Unknown command: $1${NC}"
        echo ""
        help
        exit 1
        ;;
esac
