@echo off
echo ========================================
echo   WEATHER STATION FILE TRANSFER
echo   Laptop to Debian 12 Server
echo ========================================
echo.

:: Configuration - MODIFY THESE VALUES
set SERVER_IP=192.168.1.100
set SERVER_USER=root
set SERVER_PASSWORD=your_server_password
set SERVER_PATH=/opt/weather-station
set SOURCE_PATH=C:\Users\opera\Downloads\weather-station-server

:: Check if pscp is available
where pscp >nul 2>&1
if %errorlevel% neq 0 (
    echo [ERROR] pscp.exe not found!
    echo Please install PuTTY or WinSCP
    echo Download from: https://www.putty.org/
    pause
    exit /b 1
)

echo [INFO] Connecting to server: %SERVER_IP%
echo [INFO] Source: %SOURCE_PATH%
echo [INFO] Target: %SERVER_PATH%
echo.

:: Create server directory
echo [STEP 1] Creating server directory...
pscp -pw %SERVER_PASSWORD% -r "%SOURCE_PATH%\*" %SERVER_USER%@%SERVER_IP%:%SERVER_PATH%

if %errorlevel% neq 0 (
    echo [ERROR] File transfer failed!
    echo Check:
    echo 1. Server IP is correct: %SERVER_IP%
    echo 2. Server is accessible
    echo 3. SSH is enabled on server
    echo 4. Credentials are correct
    pause
    exit /b 1
)

echo [SUCCESS] Files transferred successfully!
echo.

:: Set permissions
echo [STEP 2] Setting permissions...
plink -pw %SERVER_PASSWORD% %SERVER_USER%@%SERVER_IP% "chown -R weatherstation:weatherstation %SERVER_PATH% && chmod -R 755 %SERVER_PATH%"

if %errorlevel% neq 0 (
    echo [WARNING] Permission setting failed, set manually on server
    echo Run: chown -R weatherstation:weatherstation /opt/weather-station
    echo Run: chmod -R 755 /opt/weather-station
)

echo.
echo [STEP 3] Setting up Python environment...
plink -pw %SERVER_PASSWORD% %SERVER_USER%@%SERVER_IP% "cd %SERVER_PATH% && python3 -m venv venv && source venv/bin/activate && pip install flask flask-cors requests scikit-learn numpy joblib pandas gunicorn"

echo.
echo ========================================
echo   TRANSFER COMPLETED!
echo ========================================
echo.
echo Next steps:
echo 1. SSH to server: plink -pw %SERVER_PASSWORD% %SERVER_USER%@%SERVER_IP%
echo 2. Configure: nano /etc/weather-station/server.conf
echo 3. Start service: systemctl start weather-station
echo 4. Check status: systemctl status weather-station
echo.
echo Server will be available at: http://%SERVER_IP%:5000
echo.
pause
