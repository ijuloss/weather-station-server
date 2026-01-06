# Weather Station Server - Complete Setup Guide
## Debian 12 + CasaOS Production Deployment

---

## 🎯 OVERVIEW

This guide provides step-by-step instructions to deploy the Weather Station system from your laptop to a Debian 12 server with CasaOS.

### **Source → Target**
- **Source**: `C:\Users\opera\Downloads\weather-station-server\` (Laptop)
- **Target**: `/opt/weather-station/` (Server)
- **OS**: Debian 12 with CasaOS
- **Architecture**: Production-ready, systemd service

---

## 📁 FILE STRUCTURE

### **Laptop (Source)**
```
weather-station-server/
├── backend/
│   └── app.py                    # Main Flask application
├── config/
│   ├── server.conf               # Production config
│   └── server.conf.example       # Config template
├── scripts/
│   ├── install-server.sh         # Server setup script
│   ├── configure-server.sh       # Configuration script
│   ├── manage-service.sh         # Service management
│   └── transfer-files.bat       # File transfer script
├── docs/
│   └── README.md               # This documentation
└── SETUP-GUIDE.md             # Complete setup guide
```

### **Server (Target)**
```
/opt/weather-station/              # Application directory
├── app.py                      # Main application
├── venv/                       # Python virtual environment
└── start.sh                    # Startup script

/etc/weather-station/             # Configuration
└── server.conf                 # Main config file

/var/lib/weather-station/         # Data storage
├── data/                       # Sensor data
├── models/                     # AI models
└── backups/                    # Data backups

/var/log/weather-station/         # Logs
└── app.log                     # Application log

/run/weather-station/             # Runtime files
```

---

## 🚀 STEP-BY-STEP SETUP

### **STEP 1: Server Preparation**

#### **1.1 Access Your Server**
```bash
# SSH to your Debian 12 server
ssh root@YOUR_SERVER_IP

# Or with password
ssh root@YOUR_SERVER_IP
```

#### **1.2 Run Installation Script**
```bash
# Download and run setup script
wget https://raw.githubusercontent.com/your-repo/weather-station/main/scripts/install-server.sh
chmod +x install-server.sh
sudo ./install-server.sh
```

**What this does:**
- ✅ Updates system packages
- ✅ Installs Python 3.11+ and pip
- ✅ Installs required packages (Flask, scikit-learn, etc.)
- ✅ Creates system user `weatherstation`
- ✅ Creates required directories
- ✅ Sets up systemd service
- ✅ Configures firewall
- ✅ Sets up log rotation

#### **1.3 Verify Installation**
```bash
# Check if user was created
id weatherstation

# Check directories
ls -la /var/lib/weather-station/
ls -la /etc/weather-station/
ls -la /var/log/weather-station/

# Check systemd service
systemctl status weather-station
```

---

### **STEP 2: File Transfer**

#### **2.1 Configure Transfer Script**
Edit `scripts\transfer-files.bat` on your laptop:

```batch
:: MODIFY THESE VALUES
set SERVER_IP=192.168.1.100          # Your server IP
set SERVER_USER=root                    # SSH username
set SERVER_PASSWORD=your_server_password   # SSH password
set SERVER_PATH=/opt/weather-station      # Target directory
```

#### **2.2 Transfer Files**
```batch
# Run on laptop (Windows)
cd C:\Users\opera\Downloads\weather-station-server\scripts
transfer-files.bat
```

**What this transfers:**
- ✅ Backend application (`app.py`)
- ✅ Configuration files
- ✅ Documentation
- ✅ Setup scripts

#### **2.3 Alternative: Manual Transfer**
```bash
# Using SCP (from laptop)
scp -r C:\Users\opera\Downloads\weather-station-server\* root@YOUR_SERVER_IP:/opt/weather-station/

# Using WinSCP (GUI)
# Host: YOUR_SERVER_IP
# Username: root
# Password: your_password
# Remote path: /opt/weather-station
```

---

### **STEP 3: Server Configuration**

#### **3.1 Run Configuration Script**
```bash
# SSH to server
ssh root@YOUR_SERVER_IP

# Run configuration script
cd /opt/weather-station
chmod +x scripts/configure-server.sh
./scripts/configure-server.sh
```

#### **3.2 Manual Configuration**
```bash
# Edit configuration file
nano /etc/weather-station/server.conf

# Key settings to modify:
HOST=0.0.0.0
PORT=5000
DEBUG=false
LOG_LEVEL=INFO

# Optional: Add Firebase credentials
FIREBASE_DATABASE_URL=https://your-project.firebaseio.com
FIREBASE_API_KEY=your_api_key
```

#### **3.3 Set Permissions**
```bash
# Set ownership
chown -R weatherstation:weatherstation /opt/weather-station
chown -R weatherstation:weatherstation /var/lib/weather-station
chown -R weatherstation:weatherstation /etc/weather-station

# Set permissions
chmod -R 755 /opt/weather-station
chmod 644 /etc/weather-station/server.conf
```

---

### **STEP 4: Service Management**

#### **4.1 Start Service**
```bash
# Enable and start service
systemctl enable weather-station
systemctl start weather-station

# Check status
systemctl status weather-station
```

#### **4.2 Use Management Script**
```bash
# Make management script executable
chmod +x /opt/weather-station/scripts/manage-service.sh

# Run management interface
./manage-service.sh
```

**Management Options:**
- 🚀 Start/Stop/Restart service
- 📊 View service status
- 📋 View live logs
- 🔧 Edit configuration
- 🧪 Test API connection
- 💾 Backup/Restore data
- 🔄 Update system

---

### **STEP 5: Verification & Testing**

#### **5.1 Check Service Status**
```bash
# Service status
systemctl status weather-station

# Check if API is responding
curl http://localhost:5000

# Check health endpoint
curl http://localhost:5000/api/health

# View logs
journalctl -u weather-station -f
```

#### **5.2 Test from External Network**
```bash
# From another computer on same network
curl http://YOUR_SERVER_IP:5000

# Expected response:
{
  "message": "Weather Station Backend API",
  "version": "3.0",
  "status": "running",
  "server_ip": "YOUR_SERVER_IP",
  "port": 5000,
  "firebase": false,
  "ai_model": false,
  "data_points": 0
}
```

#### **5.3 Test Data Reception**
```bash
# Send test data
curl -X POST http://YOUR_SERVER_IP:5000/api/sensor-data \
  -H "Content-Type: application/json" \
  -d '{
    "temperature": 25.5,
    "humidity": 60.0,
    "air_quality": 150,
    "light_intensity": 500,
    "battery_voltage": 4.1
  }'
```

---

## 🔧 CONFIGURATION OPTIONS

### **Server Settings**
```bash
# /etc/weather-station/server.conf

# Network
HOST=0.0.0.0              # Bind address (0.0.0.0 = all interfaces)
PORT=5000                   # API port

# Performance
DEBUG=false                  # Production mode
REQUEST_TIMEOUT=30           # Request timeout (seconds)
MAX_RETRIES=3               # Max retry attempts
MAX_LOCAL_READINGS=1000      # Max data points in memory

# AI Model
MODEL_TRAINING_INTERVAL=50    # Auto-train after N readings
PREDICTION_CONFIDENCE_THRESHOLD=0.6  # Min confidence for predictions

# Logging
LOG_LEVEL=INFO              # DEBUG, INFO, WARNING, ERROR
LOG_FILE=/var/log/weather-station/app.log

# Background Tasks
BACKUP_INTERVAL=3600       # Backup every hour
HEALTH_CHECK_INTERVAL=60    # Health check every minute
```

### **Firebase Integration (Optional)**
```bash
# Add to server.conf for cloud backup
FIREBASE_API_KEY=your_api_key
FIREBASE_DATABASE_URL=https://your-project.firebaseio.com
FIREBASE_PROJECT_ID=your_project_id
```

---

## 🔍 TROUBLESHOOTING

### **Service Won't Start**
```bash
# Check logs for errors
journalctl -u weather-station -n 50

# Check configuration
cat /etc/weather-station/server.conf

# Check permissions
ls -la /opt/weather-station/
ls -la /var/log/weather-station/

# Manual start for debugging
sudo -u weatherstation /opt/weather-station/start.sh
```

### **API Not Accessible**
```bash
# Check if service is running
systemctl is-active weather-station

# Check port binding
netstat -tlnp | grep 5000

# Check firewall
ufw status
iptables -L

# Test locally
curl http://localhost:5000
```

### **Permission Issues**
```bash
# Fix ownership
chown -R weatherstation:weatherstation /opt/weather-station
chown -R weatherstation:weatherstation /var/lib/weather-station

# Fix permissions
chmod -R 755 /opt/weather-station
chmod 755 /var/log/weather-station
```

### **Python Issues**
```bash
# Check Python version
python3 --version  # Should be 3.9+

# Check virtual environment
ls -la /opt/weather-station/venv/

# Reinstall packages
source /opt/weather-station/venv/bin/activate
pip install --upgrade flask flask-cors requests scikit-learn
```

---

## 📊 MONITORING & MAINTENANCE

### **Log Management**
```bash
# View live logs
journalctl -u weather-station -f

# View last 100 lines
journalctl -u weather-station -n 100

# Filter by log level
journalctl -u weather-station | grep ERROR

# Log rotation (automatic)
ls -la /var/log/weather-station/
```

### **Performance Monitoring**
```bash
# System resources
htop                    # CPU/Memory
iotop                    # I/O usage
nethogs                  # Network usage
df -h                    # Disk space

# Service-specific
systemctl status weather-station
curl http://localhost:5000/api/health
```

### **Backup Management**
```bash
# Manual backup
curl -X POST http://localhost:5000/api/backup

# List backups
ls -la /var/lib/weather-station/backups/

# Restore from backup
curl -X POST http://localhost:5000/api/restore
```

---

## 🔐 SECURITY CONSIDERATIONS

### **Network Security**
```bash
# Firewall configuration
ufw allow 22/tcp    # SSH
ufw allow 5000/tcp  # Weather Station API
ufw enable

# Optional: Web interface
ufw allow 8080/tcp

# Fail2ban for SSH protection
apt install fail2ban
systemctl enable fail2ban
```

### **Application Security**
```bash
# Run as non-root user
sudo -u weatherstation python app.py

# File permissions
chmod 644 /etc/weather-station/server.conf  # Config read-only
chmod 755 /opt/weather-station          # Application read/execute
chmod 644 /var/log/weather-station/*     # Logs append-only

# SELinux (if enabled)
setsebool -P httpd_can_network_connect 1
```

### **API Security**
```bash
# Rate limiting (built into app)
# Input validation (built into app)
# CORS configuration (configurable)
```

---

## 🚀 PRODUCTION DEPLOYMENT

### **Domain Setup**
```bash
# Configure domain in server.conf
HOST=your-domain.com
PORT=5000

# Setup reverse proxy (nginx)
apt install nginx
# Configure /etc/nginx/sites-available/weather-station
```

### **SSL Certificate**
```bash
# Let's Encrypt
apt install certbot python3-certbot-nginx
certbot --nginx -d your-domain.com

# Or self-signed
openssl req -x509 -nodes -days 365 -newkey rsa:2048 \
  -keyout /etc/ssl/private/weather-station.key \
  -out /etc/ssl/certs/weather-station.crt
```

### **Monitoring Setup**
```bash
# Prometheus monitoring
apt install prometheus grafana

# Custom metrics endpoint
curl http://localhost:5000/api/metrics
```

---

## 📝 MAINTENANCE TASKS

### **Weekly**
```bash
# Update system
apt update && apt upgrade -y

# Update Python packages
source /opt/weather-station/venv/bin/activate
pip install --upgrade -r requirements.txt

# Check logs for errors
journalctl -u weather-station --since "7 days ago" | grep ERROR
```

### **Monthly**
```bash
# Clean old backups
find /var/lib/weather-station/backups -name "backup_*.json" -mtime +30 -delete

# Check disk space
df -h /var/lib/weather-station

# Review security logs
journalctl -u sshd --since "30 days ago"
```

---

## 🎯 SUCCESS CRITERIA

### **✅ Deployment Success When:**
- [ ] Service starts without errors
- [ ] API responds on port 5000
- [ ] Health endpoint returns OK
- [ ] Logs are being written
- [ ] Configuration is loaded correctly
- [ ] Systemd service is enabled
- [ ] External access works
- [ ] Data reception works
- [ ] AI model can train
- [ ] Firebase integration works (if configured)

### **🔧 Final Verification Commands:**
```bash
# Service status
systemctl is-active weather-station && echo "✅ Service Active" || echo "❌ Service Inactive"

# API accessibility
curl -s http://localhost:5000 >/dev/null && echo "✅ API Accessible" || echo "❌ API Not Accessible"

# Configuration loaded
test -f /etc/weather-station/server.conf && echo "✅ Config Exists" || echo "❌ Config Missing"

# Permissions correct
test -O /opt/weather-station/app.py && echo "✅ App File OK" || echo "❌ App File Issue"

# Logs working
test -w /var/log/weather-station/app.log && echo "✅ Logs Writable" || echo "❌ Logs Not Writable"
```

---

## 📞 SUPPORT & HELP

### **Useful Commands**
```bash
# Quick service restart
systemctl restart weather-station

# Quick config edit
nano /etc/weather-station/server.conf

# Quick log view
journalctl -u weather-station -f

# Quick API test
curl http://localhost:5000/api/health

# Quick backup
curl -X POST http://localhost:5000/api/backup
```

### **File Locations Quick Reference**
- **Application**: `/opt/weather-station/app.py`
- **Configuration**: `/etc/weather-station/server.conf`
- **Logs**: `/var/log/weather-station/app.log`
- **Data**: `/var/lib/weather-station/data/`
- **Backups**: `/var/lib/weather-station/backups/`
- **Models**: `/var/lib/weather-station/models/`

---

## 🎉 DEPLOYMENT COMPLETE!

Once you complete these steps, you'll have:
- ✅ **Production-ready** Weather Station server
- ✅ **Systemd service** for auto-start
- ✅ **Comprehensive logging** and monitoring
- ✅ **Configuration management** via files
- ✅ **Backup/restore** functionality
- ✅ **Security hardening** and permissions
- ✅ **AI weather prediction** capabilities
- ✅ **Firebase integration** (optional)
- ✅ **API endpoints** for data reception
- ✅ **Health monitoring** and alerting

**Your Weather Station will be accessible at: `http://YOUR_SERVER_IP:5000`**

---

**Weather Station Server v3.0 - Production Ready for Debian 12 + CasaOS**
