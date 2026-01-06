# Weather Station Server - Debian 12 with CasaOS

## 🖥️ Overview

Production-ready Weather Station server optimized for Debian 12 with CasaOS integration. Complete IoT weather monitoring system with AI predictions, real-time dashboard, and comprehensive management tools.

## 🚀 Quick Start

### 1. System Requirements
- **OS**: Debian 12 (Bookworm)
- **RAM**: Minimum 2GB, Recommended 4GB
- **Storage**: Minimum 20GB, Recommended 50GB
- **Network**: Ethernet or WiFi connection
- **CasaOS**: Optional but recommended

### 2. One-Click Installation

```bash
# Download and run installer
wget https://raw.githubusercontent.com/your-repo/weather-station-server/main/scripts/install-debian12.sh
chmod +x install-debian12.sh
sudo ./install-debian12.sh
```

### 3. Manual Installation

```bash
# Clone repository
git clone https://github.com/your-repo/weather-station-server.git
cd weather-station-server

# Run installation script
sudo ./scripts/install-debian12.sh
```

## 📁 Directory Structure

```
weather-station-server/
├── backend/
│   └── app.py              # Main Flask application
├── frontend/
│   └── index.html          # Web dashboard
├── config/
│   ├── server.conf         # Main configuration
│   └── server.conf.example # Configuration template
├── scripts/
│   ├── install-debian12.sh # Installation script
│   └── manage.sh           # Management script
├── docker/
│   ├── Dockerfile          # Docker image
│   ├── docker-compose.yml  # Docker Compose
│   └── nginx.conf          # Nginx configuration
├── requirements.txt        # Python dependencies
└── README.md              # This file
```

## ⚙️ Configuration

### Server Configuration
Edit `/etc/weather-station/server.conf`:

```bash
# Server Settings
HOST=0.0.0.0
PORT=5000
DEBUG=false

# Logging
LOG_LEVEL=INFO
LOG_FILE=/var/log/weather-station/app.log

# Data Storage
DATA_DIR=/var/lib/weather-station
CONFIG_DIR=/etc/weather-station

# AI Model
MODEL_TRAINING_INTERVAL=50
PREDICTION_CONFIDENCE_THRESHOLD=0.6

# Performance
MAX_LOCAL_READINGS=1000
REQUEST_TIMEOUT=30
BACKUP_INTERVAL=3600
```

### Firebase Integration (Optional)
```bash
# Firebase Configuration
FIREBASE_API_KEY=your_api_key
FIREBASE_DATABASE_URL=https://your-project.firebaseio.com
FIREBASE_PROJECT_ID=your_project_id
```

## 🎯 Usage

### Management Commands

```bash
# Server management
sudo /opt/weather-station/scripts/manage.sh status
sudo /opt/weather-station/scripts/manage.sh start
sudo /opt/weather-station/scripts/manage.sh stop
sudo /opt/weather-station/scripts/manage.sh restart

# Data management
sudo /opt/weather-station/scripts/manage.sh backup
sudo /opt/weather-station/scripts/manage.sh restore backup_file.tar.gz

# System management
sudo /opt/weather-station/scripts/manage.sh health
sudo /opt/weather-station/scripts/manage.sh logs
sudo /opt/weather-station/scripts/manage.sh config
sudo /opt/weather-station/scripts/manage.sh update
```

### Systemd Commands

```bash
# Service management
sudo systemctl status weather-station
sudo systemctl start weather-station
sudo systemctl stop weather-station
sudo systemctl restart weather-station
sudo systemctl enable weather-station

# Logs
sudo journalctl -u weather-station -f
sudo tail -f /var/log/weather-station/app.log
```

## 🌐 Access

### Web Dashboard
- **URL**: `http://your-server-ip/`
- **Features**: Real-time monitoring, AI predictions, charts
- **Mobile**: Responsive design for mobile devices

### API Endpoints
- **Base URL**: `http://your-server-ip/api/`
- **Health**: `/api/health`
- **Stats**: `/api/dashboard-stats`
- **Data**: `/api/sensor-data` (POST)
- **Config**: `/api/config`

## 🔧 Features

### Backend
- ✅ **Flask REST API** with comprehensive error handling
- ✅ **AI Weather Prediction** using Random Forest
- ✅ **Real-time Data Processing** with validation
- ✅ **Automatic Backups** with rotation
- ✅ **Health Monitoring** with metrics
- ✅ **Configuration Management** externalized
- ✅ **Logging System** with rotation
- ✅ **Security Hardening** with systemd

### Frontend
- ✅ **Real-time Dashboard** with auto-refresh
- ✅ **Interactive Charts** using Chart.js
- ✅ **AI Prediction Display** with confidence
- ✅ **Responsive Design** for all devices
- ✅ **Toast Notifications** for feedback
- ✅ **Error Handling** with retry logic

### System
- ✅ **Debian 12 Optimized** with security hardening
- ✅ **CasaOS Integration** with app manifest
- ✅ **Nginx Reverse Proxy** with SSL support
- ✅ **Systemd Service** with auto-restart
- ✅ **Log Rotation** for disk management
- ✅ **Firewall Configuration** for security

## 🐳 Docker Deployment

### Using Docker Compose

```bash
# Clone repository
git clone https://github.com/your-repo/weather-station-server.git
cd weather-station-server

# Start services
docker-compose up -d

# Check status
docker-compose ps

# View logs
docker-compose logs -f
```

### Manual Docker Build

```bash
# Build image
docker build -t weather-station-server ./docker

# Run container
docker run -d \
  --name weather-station \
  -p 5000:5000 \
  -v $(pwd)/config:/etc/weather-station:ro \
  -v $(pwd)/data:/var/lib/weather-station \
  weather-station-server
```

## 🔍 Monitoring

### Health Check
```bash
# API health check
curl http://localhost/api/health

# Service status
systemctl is-active weather-station

# Resource usage
htop
df -h
free -h
```

### Log Monitoring
```bash
# Real-time logs
tail -f /var/log/weather-station/app.log

# Service logs
journalctl -u weather-station -f

# Nginx logs
tail -f /var/log/nginx/access.log
```

## 🔒 Security

### System Security
- **Non-root user** for service execution
- **Systemd sandboxing** with restrictions
- **Firewall rules** for port access
- **Log rotation** for disk management
- **Automatic updates** for security patches

### Application Security
- **Input validation** for all API requests
- **CORS configuration** for web access
- **Rate limiting** for API protection
- **HTTPS support** with SSL certificates
- **Environment variables** for sensitive data

## 🚨 Troubleshooting

### Common Issues

#### Service Won't Start
```bash
# Check logs
sudo journalctl -u weather-station -n 50

# Check configuration
sudo /opt/weather-station/scripts/manage.sh config

# Check permissions
ls -la /opt/weather-station/
```

#### API Not Responding
```bash
# Check service status
sudo systemctl status weather-station

# Test API directly
curl http://localhost:5000/api/health

# Check Nginx configuration
sudo nginx -t
```

#### High Memory Usage
```bash
# Check memory usage
free -h
ps aux | grep weather-station

# Restart service
sudo systemctl restart weather-station
```

#### Disk Space Issues
```bash
# Check disk usage
df -h
du -sh /var/lib/weather-station

# Clean old backups
find /var/lib/weather-station/backups -name "*.tar.gz" -mtime +7 -delete

# Rotate logs
sudo logrotate -f /etc/logrotate.d/weather-station
```

### Performance Optimization

#### Database Optimization
```bash
# Reduce data retention
# Edit /etc/weather-station/server.conf
MAX_LOCAL_READINGS=500

# Increase backup interval
BACKUP_INTERVAL=7200
```

#### Memory Optimization
```bash
# Reduce Python memory
# Edit /etc/systemd/system/weather-station.service
MemoryMax=512M
```

## 🔄 Updates

### System Updates
```bash
# Update Weather Station
sudo /opt/weather-station/scripts/manage.sh update

# Update system packages
sudo apt update && sudo apt upgrade
```

### Configuration Updates
```bash
# Backup current config
sudo cp /etc/weather-station/server.conf /etc/weather-station/server.conf.bak

# Update configuration
sudo nano /etc/weather-station/server.conf

# Restart service
sudo systemctl restart weather-station
```

## 📊 Performance Metrics

### Expected Performance
- **Response Time**: <200ms
- **Memory Usage**: <512MB
- **CPU Usage**: <10%
- **Disk Usage**: <1GB/month
- **Concurrent Users**: 100+

### Monitoring Metrics
- **API Response Time**
- **Memory Usage**
- **CPU Usage**
- **Disk Usage**
- **Network Traffic**
- **Error Rate**

## 🌍 CasaOS Integration

### App Installation
1. Open CasaOS web interface
2. Go to App Store
3. Install "Weather Station"
4. Configure settings
5. Access dashboard

### CasaOS Features
- **One-click installation**
- **Automatic updates**
- **Backup integration**
- **Resource monitoring**
- **Web terminal access**

## 📞 Support

### Documentation
- **Installation Guide**: See Installation section
- **API Documentation**: See API Endpoints
- **Configuration Guide**: See Configuration section

### Community Support
- **GitHub Issues**: Report bugs and feature requests
- **Discussions**: Ask questions and share experiences
- **Wiki**: Community-maintained documentation

### Professional Support
- **Email**: support@weather-station.com
- **Phone**: +1-555-WEATHER
- **Chat**: Available on website

---

## 📝 License

Weather Station Server is licensed under the MIT License. See LICENSE file for details.

## 🤝 Contributing

Contributions are welcome! Please see CONTRIBUTING.md for guidelines.

---

**Weather Station Server v3.0**  
*Production-ready IoT Weather Monitoring for Debian 12 with CasaOS*
