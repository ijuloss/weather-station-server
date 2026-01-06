# Weather Station Server - Manual Setup Guide
## No GitHub Repository Required

---

## 🎯 OVERVIEW

This guide shows how to deploy Weather Station server from your laptop to Debian 12 server **without using GitHub**. All files are transferred manually using SCP/SFTP.

### **Methods Available:**
1. **PuTTY/WinSCP** (Windows - Recommended)
2. **Manual SCP** (Linux/Mac)
3. **Direct SSH Copy** (Advanced)

---

## 📋 STEP-BY-STEP DEPLOYMENT

### **🔧 STEP 1: Server Preparation**

#### **1.1 SSH to Server**
```bash
# Using password
ssh root@YOUR_SERVER_IP

# Using SSH key
ssh -i /path/to/key root@YOUR_SERVER_IP
```

#### **1.2 Run Setup Script**
Copy this script content and paste directly into SSH:

```bash
# Create setup script on server
cat > setup-weather.sh << 'EOF'
#!/bin/bash
set -e

echo "Setting up Weather Station server..."

# Update system
apt update && apt upgrade -y

# Install packages
apt install -y python3 python3-pip python3-venv git curl wget htop nano vim unzip build-essential

# Install Python packages
pip3 install --upgrade pip
pip3 install flask flask-cors requests scikit-learn numpy joblib pandas gunicorn

# Create user
if ! id "weatherstation" &>/dev/null; then
    useradd -r -s /bin/bash -d /var/lib/weather-station weatherstation
fi

# Create directories
mkdir -p /var/lib/weather-station/{data,models,backups}
mkdir -p /var/log/weather-station
mkdir -p /etc/weather-station
mkdir -p /run/weather-station
mkdir -p /opt/weather-station

# Set permissions
chown -R weatherstation:weatherstation /var/lib/weather-station
chown -R weatherstation:weatherstation /var/log/weather-station
chown -R weatherstation:weatherstation /etc/weather-station
chown -R weatherstation:weatherstation /run/weather-station
chown -R weatherstation:weatherstation /opt/weather-station

chmod 755 /var/lib/weather-station
chmod 755 /var/log/weather-station
chmod 755 /etc/weather-station
chmod 755 /run/weather-station
chmod 755 /opt/weather-station

# Create virtual environment
cd /opt/weather-station
python3 -m venv venv

# Install Python packages
/opt/weather-station/venv/bin/pip install flask flask-cors requests scikit-learn numpy joblib pandas gunicorn

echo "Setup completed!"
EOF

# Make executable and run
chmod +x setup-weather.sh
./setup-weather.sh
```

---

### **📁 STEP 2: File Transfer Methods**

#### **Method 1: WinSCP (GUI - Recommended for Windows)**

1. **Download WinSCP**: https://winscp.net/
2. **Connect to Server**:
   - Host: `YOUR_SERVER_IP`
   - Username: `root`
   - Password: `your_password`
   - Port: `22`
3. **Transfer Files**:
   ```
   Source (Laptop) → Target (Server)
   C:\Users\opera\Downloads\weather-station-server\backend\app.py → /opt/weather-station/app.py
   C:\Users\opera\Downloads\weather-station-server\config\* → /etc/weather-station/
   C:\Users\opera\Downloads\weather-station-server\scripts\* → /opt/weather-station/scripts/
   ```

#### **Method 2: PuTTY + PSCP (Command Line)**

1. **Download PuTTY**: https://www.putty.org/
2. **Use transfer-manual.bat script**:
   ```batch
   # Edit the script with your server details
   set SERVER_IP=YOUR_SERVER_IP
   set SERVER_PASSWORD=your_password
   
   # Run the script
   transfer-manual.bat
   ```

#### **Method 3: Manual SCP (Linux/Mac)**

```bash
# From laptop to server
scp -r /path/to/weather-station-server/backend/* root@YOUR_SERVER_IP:/opt/weather-station/
scp -r /path/to/weather-station-server/config/* root@YOUR_SERVER_IP:/etc/weather-station/
scp -r /path/to/weather-station-server/scripts/* root@YOUR_SERVER_IP:/opt/weather-station/scripts/
```

#### **Method 4: SSH Copy-Paste (Direct)**

1. **Copy file content** from laptop
2. **SSH to server**: `ssh root@YOUR_SERVER_IP`
3. **Create and paste files**:

```bash
# Create app.py
nano /opt/weather-station/app.py
# Paste the entire app.py content, save: Ctrl+X, Y, Enter

# Create config
nano /etc/weather-station/server.conf
# Paste the config content, save: Ctrl+X, Y, Enter

# Create scripts
mkdir -p /opt/weather-station/scripts
nano /opt/weather-station/scripts/manage-service.sh
# Paste script content, save
```

---

### **⚙️ STEP 3: Configuration**

#### **3.1 Edit Configuration File**
```bash
# SSH to server
ssh root@YOUR_SERVER_IP

# Edit configuration
nano /etc/weather-station/server.conf
```

**Key settings to configure:**
```bash
HOST=0.0.0.0                    # Listen on all interfaces
PORT=5000                         # API port
DEBUG=false                        # Production mode
LOG_LEVEL=INFO                     # Log level

# Optional: Add Firebase credentials
FIREBASE_DATABASE_URL=https://your-project.firebaseio.com
FIREBASE_API_KEY=your_api_key_here
```

#### **3.2 Set Permissions**
```bash
# Ensure correct permissions
chown -R weatherstation:weatherstation /opt/weather-station
chown -R weatherstation:weatherstation /etc/weather-station
chmod -R 755 /opt/weather-station
chmod 644 /etc/weather-station/server.conf
```

---

### **🚀 STEP 4: Service Setup**

#### **4.1 Create Systemd Service**
```bash
# Create service file
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
Restart=always
RestartSec=10
StandardOutput=journal
StandardError=journal
SyslogIdentifier=weather-station

[Install]
WantedBy=multi-user.target
EOF

# Reload and enable
systemctl daemon-reload
systemctl enable weather-station
```

#### **4.2 Start Service**
```bash
# Start the service
systemctl start weather-station

# Check status
systemctl status weather-station

# View logs
journalctl -u weather-station -f
```

---

## 🔍 VERIFICATION

### **Test API Locally**
```bash
# From server
curl http://localhost:5000

# Test health endpoint
curl http://localhost:5000/api/health
```

### **Test API Externally**
```bash
# From laptop
curl http://YOUR_SERVER_IP:5000

# Expected response:
{
  "message": "Weather Station Backend API",
  "version": "3.0",
  "status": "running",
  "server_ip": "YOUR_SERVER_IP",
  "port": 5000
}
```

### **Test Data Reception**
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

### **Service Commands**
```bash
# Control service
systemctl start weather-station
systemctl stop weather-station
systemctl restart weather-station
systemctl status weather-station

# View logs
journalctl -u weather-station -f
journalctl -u weather-station -n 100

# Configuration
nano /etc/weather-station/server.conf
cat /etc/weather-station/server.conf
```

### **File Locations**
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

---

## 🔍 TROUBLESHOOTING

### **Common Issues**

#### **Permission Denied**
```bash
# Fix ownership
chown -R weatherstation:weatherstation /opt/weather-station
chown -R weatherstation:weatherstation /etc/weather-station

# Fix permissions
chmod -R 755 /opt/weather-station
chmod 644 /etc/weather-station/server.conf
```

#### **Service Won't Start**
```bash
# Check logs
journalctl -u weather-station -n 50

# Manual start for debugging
sudo -u weatherstation /opt/weather-station/venv/bin/python /opt/weather-station/app.py

# Check Python path
which python3
/opt/weather-station/venv/bin/python --version
```

#### **API Not Accessible**
```bash
# Check if service is running
systemctl is-active weather-station

# Check port binding
netstat -tlnp | grep 5000

# Check firewall
ufw status
iptables -L
```

---

## 🎯 SUCCESS CRITERIA

### **✅ Deployment Successful When:**
- [ ] Service starts without errors
- [ ] API responds on port 5000
- [ ] Health endpoint returns OK
- [ ] Configuration is loaded correctly
- [ ] External access works
- [ ] Data can be posted via API
- [ ] AI model can train
- [ ] Logs are being written

---

## 📋 QUICK REFERENCE

### **Essential Commands**
```bash
# SSH to server
ssh root@YOUR_SERVER_IP

# Start service
systemctl start weather-station

# Check status
systemctl status weather-station

# View logs
journalctl -u weather-station -f

# Edit config
nano /etc/weather-station/server.conf

# Test API
curl http://localhost:5000
```

### **File Transfer Commands**
```bash
# Using SCP
scp -r ./backend/* root@YOUR_SERVER_IP:/opt/weather-station/
scp -r ./config/* root@YOUR_SERVER_IP:/etc/weather-station/
scp -r ./scripts/* root@YOUR_SERVER_IP:/opt/weather-station/scripts/

# Using rsync
rsync -av ./backend/ root@YOUR_SERVER_IP:/opt/weather-station/
```

---

## 🎉 DEPLOYMENT COMPLETE!

**Your Weather Station server is running at: `http://YOUR_SERVER_IP:5000`**

### **✅ What You Have:**
- Production-ready Flask application
- Systemd service for auto-start
- Comprehensive error handling
- AI weather prediction
- Firebase integration (optional)
- Data backup/restore
- Comprehensive logging
- Security hardening
- Performance optimization

---

**Weather Station Server v3.0 - Manual Deployment Ready**
