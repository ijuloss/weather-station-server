@echo off
echo ========================================
echo   WEATHER STATION FILE TRANSFER
echo   Laptop to Debian 12 Server
echo   MANUAL TRANSFER - No GitHub
echo ========================================
echo.

:: Configuration - MODIFY THESE VALUES
set SERVER_IP=192.168.1.100
set SERVER_USER=root
set SERVER_PASSWORD=your_server_password
set SERVER_PATH=/opt/weather-station
set SOURCE_PATH=C:\Users\opera\Downloads\weather-station-server

echo [INFO] Server IP: %SERVER_IP%
echo [INFO] Source: %SOURCE_PATH%
echo [INFO] Target: %SERVER_PATH%
echo.

:: Check if pscp is available
where pscp >nul 2>&1
if %errorlevel% neq 0 (
    echo [ERROR] pscp.exe not found!
    echo Please install PuTTY or WinSCP
    echo Download from: https://www.putty.org/
    echo Alternative: Use manual SCP commands
    pause
    exit /b 1
)

echo [STEP 1] Creating server directory structure...
pscp -pw %SERVER_PASSWORD% -r "%SOURCE_PATH%\backend\*" %SERVER_USER%@%SERVER_IP%:/opt/weather-station/

if %errorlevel% neq 0 (
    echo [ERROR] Backend transfer failed!
    echo Check server connection and credentials
    pause
    exit /b 1
)

echo [STEP 2] Transferring configuration files...
pscp -pw %SERVER_PASSWORD% -r "%SOURCE_PATH%\config\*" %SERVER_USER%@%SERVER_IP%:/etc/weather-station/

if %errorlevel% neq 0 (
    echo [WARNING] Config transfer failed, continue anyway
)

echo [STEP 3] Transferring scripts...
pscp -pw %SERVER_PASSWORD% -r "%SOURCE_PATH%\scripts\*" %SERVER_USER%@%SERVER_IP%:/opt/weather-station/

if %errorlevel% neq 0 (
    echo [WARNING] Scripts transfer failed, continue anyway
)

echo [STEP 4] Setting permissions...
pscp -pw %SERVER_PASSWORD% %SERVER_USER%@%SERVER_IP% "chown -R weatherstation:weatherstation /opt/weather-station && chmod -R 755 /opt/weather-station && chown -R weatherstation:weatherstation /etc/weather-station && chmod 755 /etc/weather-station"

if %errorlevel% neq 0 (
    echo [WARNING] Permission setting failed, set manually on server
    echo Run these commands on server:
    echo chown -R weatherstation:weatherstation /opt/weather-station
    echo chmod -R 755 /opt/weather-station
    echo chown -R weatherstation:weatherstation /etc/weather-station
    echo chmod 755 /etc/weather-station
)

echo.
echo [STEP 5] Setting up Python environment...
pscp -pw %SERVER_PASSWORD% %SERVER_USER%@%SERVER_IP% "cd /opt/weather-station && python3 -m venv venv && source venv/bin/activate && pip install flask flask-cors requests scikit-learn numpy joblib pandas gunicorn"

echo.
echo ========================================
echo   TRANSFER COMPLETED!
echo ========================================
echo.
echo Files transferred:
echo - Backend app.py: /opt/weather-station/app.py
echo - Config files: /etc/weather-station/
echo - Scripts: /opt/weather-station/scripts/
echo.
echo Next steps:
echo 1. SSH to server: plink -pw %SERVER_PASSWORD% %SERVER_USER%@%SERVER_IP%
echo 2. Run setup: /opt/weather-station/scripts/install-debian12.sh
echo 3. Configure: nano /etc/weather-station/server.conf
echo 4. Start service: systemctl start weather-station
echo 5. Check status: systemctl status weather-station
echo.
echo Server will be available at: http://%SERVER_IP%:5000
echo.
pause
