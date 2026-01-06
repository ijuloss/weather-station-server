# Weather Station Server - Quick Start Guide
## From Laptop to Debian 12 Server

---

## 🚀 ONE-CLICK DEPLOYMENT

### **Prerequisites:**
- ✅ Debian 12 server with CasaOS installed
- ✅ SSH access to server (IP address known)
- ✅ PuTTY/Winscp installed on laptop
- ✅ Server password or SSH key ready

---

## 📋 EXECUTION STEPS

### **STEP 1: Prepare Server (5 minutes)**
```bash
# SSH to your server
ssh root@YOUR_SERVER_IP

# Download and run setup script
wget https://raw.githubusercontent.com/your-repo/weather-station/main/scripts/install-server.sh
chmod +x install-server.sh
./install-server.sh

# Reboot when prompted
reboot
```

### **STEP 2: Transfer Files (2 minutes)**
```batch
# On laptop: Edit scripts\transfer-files.bat
# Change: SERVER_IP=your_server_ip
# Change: SERVER_PASSWORD=your_password

# Run the script
cd C:\Users\opera\Downloads\weather-station-server\scripts
transfer-files.bat
```

### **STEP 3: Configure Server (2 minutes)**
```bash
# SSH back to server
ssh root@YOUR_SERVER_IP

# Run configuration
cd /opt/weather-station
./scripts/configure-server.sh

# Optional: Edit Firebase settings
nano /etc/weather-station/server.conf
```

### **STEP 4: Start Service (1 minute)**
```bash
# Start the service
systemctl start weather-station

# Check status
systemctl status weather-station

# Test API
curl http://localhost:5000
```

---

## ✅ VERIFICATION

### **Test from Server:**
```bash
# Health check
curl http://localhost:5000/api/health

# Expected response:
{
  "status": "healthy",
  "server_ip": "YOUR_SERVER_IP",
  "data_points": 0,
  "ai_model": false
}
```

### **Test from Laptop:**
```bash
# Test external access
curl http://YOUR_SERVER_IP:5000

# Access in browser:
# http://YOUR_SERVER_IP:5000
```

### **Test Data Reception:**
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

## 🔧 MANAGEMENT

### **Service Management:**
```bash
# Interactive management menu
./manage-service.sh

# Or manual commands:
systemctl start weather-station
systemctl stop weather-station
systemctl restart weather-station
systemctl status weather-station
```

### **Configuration:**
```bash
# Edit main config
nano /etc/weather-station/server.conf

# View logs
journalctl -u weather-station -f

# Backup data
curl -X POST http://localhost:5000/api/backup
```

---

## 🌐 ACCESS POINTS

### **API Endpoints:**
- **Root**: `http://YOUR_SERVER_IP:5000/`
- **Health**: `http://YOUR_SERVER_IP:5000/api/health`
- **Data**: `http://YOUR_SERVER_IP:5000/api/sensor-data` (POST)
- **Stats**: `http://YOUR_SERVER_IP:5000/api/dashboard-stats` (GET)
- **Config**: `http://YOUR_SERVER_IP:5000/api/config` (GET)

### **Web Dashboard:**
```
http://YOUR_SERVER_IP:5000
```

---

## 📊 FILE LOCATIONS

### **On Server:**
```
/opt/weather-station/              # Application
├── app.py                      # Main application
├── venv/                       # Python environment
└── scripts/                     # Management scripts

/etc/weather-station/             # Configuration
└── server.conf                 # Main config file

/var/lib/weather-station/         # Data storage
├── data/                       # Sensor data
├── models/                     # AI models
└── backups/                    # Data backups

/var/log/weather-station/         # Logs
└── app.log                     # Application log
```

### **On Laptop (Source):**
```
C:\Users\opera\Downloads\weather-station-server\
├── backend\app.py              # Application
├── config\server.conf           # Configuration
├── scripts\                    # Setup scripts
└── docs\                      # Documentation
```

---

## 🔍 TROUBLESHOOTING

### **Service Won't Start:**
```bash
# Check logs
journalctl -u weather-station -n 50

# Check config
cat /etc/weather-station/server.conf

# Manual start
sudo -u weatherstation /opt/weather-station/start.sh
```

### **Can't Access API:**
```bash
# Check if running
systemctl is-active weather-station

# Check port
netstat -tlnp | grep 5000

# Check firewall
ufw status
```

### **Permission Issues:**
```bash
# Fix ownership
chown -R weatherstation:weatherstation /opt/weather-station

# Fix permissions
chmod -R 755 /opt/weather-station
```

---

## 📞 QUICK COMMANDS

### **Essential Commands:**
```bash
# Service control
systemctl start weather-station
systemctl stop weather-station
systemctl restart weather-station
systemctl status weather-station

# Logs
journalctl -u weather-station -f
journalctl -u weather-station -n 100

# Configuration
nano /etc/weather-station/server.conf
cat /etc/weather-station/server.conf

# API testing
curl http://localhost:5000
curl http://localhost:5000/api/health

# Data management
curl -X POST http://localhost:5000/api/backup
ls -la /var/lib/weather-station/backups/

# Service management
./manage-service.sh
```

---

## 🎯 SUCCESS INDICATORS

### **✅ Deployment Successful When:**
- [ ] Service starts: `systemctl start weather-station`
- [ ] API responds: `curl http://localhost:5000`
- [ ] Health check passes: `curl http://localhost:5000/api/health`
- [ ] External access works: `curl http://YOUR_SERVER_IP:5000`
- [ ] Data can be posted via API
- [ ] AI model trains automatically
- [ ] Logs are being written
- [ ] Configuration is loaded correctly

### **🎉 Final Result:**
Your Weather Station server is running at:
```
http://YOUR_SERVER_IP:5000
```

With:
- ✅ Production-ready Flask application
- ✅ Systemd service for auto-start
- ✅ Comprehensive error handling
- ✅ AI weather prediction
- ✅ Firebase integration (optional)
- ✅ Data backup/restore
- ✅ Comprehensive logging
- ✅ Security hardening
- ✅ Performance optimization

---

## 📚 DOCUMENTATION

- **Complete Guide**: `docs/COMPLETE-SETUP-GUIDE.md`
- **Configuration**: `config/server.conf.example`
- **Installation**: `scripts/install-server.sh`
- **Management**: `scripts/manage-service.sh`

---

**Weather Station Server v3.0 - Ready for Production Deployment**

**Total Setup Time: ~10 minutes**
**Requirements: Debian 12 + SSH access**
**Result: Production Weather Station server**
