# Weather Station Server - GitHub Setup Guide
## Create Repository & Deploy via GitHub

---

## 🎯 OVERVIEW

This guide shows how to create a new GitHub repository for your Weather Station server and deploy it to your Debian 12 server using Git.

### **Benefits of Using GitHub:**
- ✅ Version control for your code
- ✅ Easy deployment to multiple servers
- ✅ Backup and collaboration
- ✅ Automated deployment options
- ✅ Change tracking and rollback

---

## 📁 STEP 1: Create GitHub Repository

### **1.1 Create Repository on GitHub**
1. **Go to GitHub**: https://github.com
2. **Click "New repository"** (green button)
3. **Repository settings**:
   ```
   Repository name: weather-station-server
   Description: Weather Station Backend API - Production Ready
   Visibility: Private (recommended) or Public
   Initialize with: README
   Add .gitignore: Python
   Add license: MIT
   ```
4. **Click "Create repository"**

### **1.2 Get Repository URL**
After creating, you'll see:
```bash
# HTTPS URL (recommended)
https://github.com/YOUR_USERNAME/weather-station-server.git

# Or SSH URL
git@github.com:YOUR_USERNAME/weather-station-server.git
```

---

## 📋 STEP 2: Setup Local Git Repository

### **2.1 Initialize Git on Laptop**
```bash
# Navigate to your project folder
cd C:\Users\opera\Downloads\weather-station-server

# Initialize Git repository
git init

# Configure Git user (first time only)
git config --global user.name "Your Name"
git config --global user.email "your.email@example.com"
```

### **2.2 Add Remote Repository**
```bash
# Add GitHub repository (replace with your URL)
git remote add origin https://github.com/YOUR_USERNAME/weather-station-server.git

# Verify remote
git remote -v
```

---

## 📋 STEP 3: Commit and Push to GitHub

### **3.1 Stage and Commit Files**
```bash
# Add all files
git add .

# Check status
git status

# Commit files
git commit -m "Initial commit - Weather Station Server v3.0

- Production-ready Flask application
- Debian 12 server setup scripts
- Configuration management
- Service management tools
- Complete documentation

Features:
- AI weather prediction
- Firebase integration
- Real-time data processing
- Comprehensive error handling
- Systemd service management
- Performance optimization
- Security hardening"
```

### **3.2 Push to GitHub**
```bash
# Push to main branch
git push -u origin main

# If prompted for credentials:
# Username: Your GitHub username
# Password: Your GitHub personal access token
```

---

## 📋 STEP 4: Setup Personal Access Token

### **4.1 Create GitHub Personal Access Token**
1. **Go to GitHub Settings**: https://github.com/settings/tokens
2. **Click "Generate new token"**
3. **Token settings**:
   ```
   Note: Weather Station Server
   Expiration: 90 days (or as needed)
   Scopes: 
   ☑️ repo (Full control of private repositories)
   ☑️ workflow (Update GitHub Action workflows)
   ```
4. **Click "Generate token"**
5. **Copy token** (save it securely - you won't see it again)

### **4.2 Use Token for Git Operations**
```bash
# When prompted for password, use your personal access token
# Username: Your GitHub username
# Password: ghp_xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx (your token)
```

---

## 📋 STEP 5: Deploy to Server via GitHub

### **5.1 SSH to Server**
```bash
ssh root@YOUR_SERVER_IP
```

### **5.2 Install Git on Server**
```bash
# Install Git
apt update && apt install -y git

# Configure Git
git config --global user.name "Your Name"
git config --global user.email "your.email@example.com"
```

### **5.3 Clone Repository**
```bash
# Navigate to application directory
cd /opt

# Clone repository
git clone https://github.com/YOUR_USERNAME/weather-station-server.git

# Move to correct location
mv weather-station-server weather-station
cd weather-station
```

### **5.4 Setup Application**
```bash
# Run setup script
chmod +x scripts/install-debian12.sh
./scripts/install-debian12.sh

# Configure application
./scripts/configure-server.sh

# Edit configuration
nano /etc/weather-station/server.conf
```

---

## 📋 STEP 6: Service Setup

### **6.1 Create Systemd Service**
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

# Enable and start service
systemctl daemon-reload
systemctl enable weather-station
systemctl start weather-station
```

---

## 📋 STEP 7: Update and Deploy Workflow

### **7.1 Make Changes on Laptop**
```bash
# Navigate to project
cd C:\Users\opera\Downloads\weather-station-server

# Make changes to files
# Example: Edit configuration, update code, etc.

# Stage and commit changes
git add .
git commit -m "Update configuration - Add new settings"

# Push to GitHub
git push origin main
```

### **7.2 Update Server**
```bash
# SSH to server
ssh root@YOUR_SERVER_IP

# Navigate to application
cd /opt/weather-station

# Pull latest changes
git pull origin main

# Restart service
systemctl restart weather-station

# Check status
systemctl status weather-station
```

---

## 🔄 STEP 8: Automated Deployment (Optional)

### **8.1 Create GitHub Actions Workflow**
Create `.github/workflows/deploy.yml`:
```yaml
name: Deploy to Server

on:
  push:
    branches: [ main ]
  pull_request:
    branches: [ main ]

jobs:
  deploy:
    runs-on: ubuntu-latest
    
    steps:
    - uses: actions/checkout@v3
    
    - name: Deploy to server
      uses: appleboy/ssh-action@v0.1.5
      with:
        host: ${{ secrets.SERVER_HOST }}
        username: ${{ secrets.SERVER_USERNAME }}
        key: ${{ secrets.SERVER_SSH_KEY }}
        script: |
          cd /opt/weather-station
          git pull origin main
          systemctl restart weather-station
          systemctl status weather-station
```

### **8.2 Add GitHub Secrets**
1. **Go to repository settings**: https://github.com/YOUR_USERNAME/weather-station-server/settings/secrets
2. **Add secrets**:
   ```
   SERVER_HOST: YOUR_SERVER_IP
   SERVER_USERNAME: root
   SERVER_SSH_KEY: Your private SSH key content
   ```

---

## 🔧 ADVANCED GIT WORKFLOW

### **Branch Management**
```bash
# Create feature branch
git checkout -b feature/new-sensor

# Make changes
git add .
git commit -m "Add new sensor support"

# Push branch
git push origin feature/new-sensor

# Merge to main (via GitHub or command line)
git checkout main
git merge feature/new-sensor
git push origin main

# Delete feature branch
git branch -d feature/new-sensor
git push origin --delete feature/new-sensor
```

### **Tagging Releases**
```bash
# Create tag
git tag -a v3.0.0 -m "Weather Station Server v3.0.0"

# Push tags
git push origin v3.0.0
git push origin --tags
```

---

## 🔍 TROUBLESHOOTING

### **Git Authentication Issues**
```bash
# If using HTTPS with token
git remote set-url origin https://YOUR_USERNAME:YOUR_TOKEN@github.com/YOUR_USERNAME/weather-station-server.git

# If using SSH
git remote set-url origin git@github.com:YOUR_USERNAME/weather-station-server.git
```

### **Merge Conflicts**
```bash
# Pull latest changes
git pull origin main

# Resolve conflicts in files
# Then stage and commit
git add .
git commit -m "Resolve merge conflicts"
git push origin main
```

### **Deployment Issues**
```bash
# Check service status
systemctl status weather-station

# View logs
journalctl -u weather-station -f

# Manual restart
systemctl restart weather-station
```

---

## 🎯 BENEFITS OF GITHUB SETUP

### **✅ Version Control**
- Track all changes to your code
- Rollback to previous versions
- Branch for features and experiments

### **✅ Easy Deployment**
- Deploy to multiple servers
- Automated deployment with GitHub Actions
- Consistent deployments across environments

### **✅ Collaboration**
- Multiple developers can contribute
- Code review process
- Issue tracking and discussions

### **✅ Backup**
- Your code is backed up on GitHub
- Can recover from local failures
- Historical record of all changes

---

## 📋 QUICK REFERENCE

### **Essential Git Commands**
```bash
# Clone repository
git clone https://github.com/YOUR_USERNAME/weather-station-server.git

# Add changes
git add .
git commit -m "Your commit message"
git push origin main

# Pull latest changes
git pull origin main

# Check status
git status
git log --oneline
```

### **Deployment Commands**
```bash
# SSH to server
ssh root@YOUR_SERVER_IP

# Update application
cd /opt/weather-station
git pull origin main
systemctl restart weather-station
```

---

## 🎉 SETUP COMPLETE!

### **🚀 Your Weather Station Server is now:**
- ✅ **Version controlled** with Git
- ✅ **Backed up** on GitHub
- ✅ **Deployable** to multiple servers
- ✅ **Updatable** with simple commands
- ✅ **Collaborative** for team development

### **🌐 Repository Structure:**
```
weather-station-server/
├── backend/
│   └── app.py                    # Flask application
├── config/
│   ├── server.conf               # Configuration
│   └── server.conf.example       # Template
├── scripts/
│   ├── install-debian12.sh       # Server setup
│   ├── configure-server.sh       # Configuration
│   ├── manage-service.sh         # Management
│   └── transfer-manual.bat      # Transfer script
├── docs/
│   ├── COMPLETE-SETUP-GUIDE.md  # Complete guide
│   └── MANUAL-SETUP-GUIDE.md    # Manual guide
├── QUICK-START.md               # Quick reference
└── README.md                   # Overview
```

### **🔄 Workflow:**
1. **Develop** on laptop
2. **Commit** changes to Git
3. **Push** to GitHub
4. **Deploy** to server
5. **Monitor** and maintain

---

**Weather Station Server v3.0 - GitHub Ready!** 🚀
