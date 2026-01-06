@echo off
echo ========================================
echo   WEATHER STATION - GIT AUTHENTICATION FIX
echo   Setup Personal Access Token
echo ========================================
echo.

echo [INFO] GitHub Authentication Issue Detected
echo [INFO] GitHub no longer supports password authentication
echo [INFO] You need to use Personal Access Token
echo.

echo [STEP 1] Get Personal Access Token
echo 1. Go to: https://github.com/settings/tokens
echo 2. Click: "Generate new token (classic)"
echo 3. Note: Weather Station Server
echo 4. Expiration: 90 days
echo 5. Scopes: ☑️ repo (Full control of private repositories)
echo 6. Click: "Generate token"
echo 7. Copy the token (starts with ghp_)
echo.

set /p TOKEN="Enter your Personal Access Token: "

if "%TOKEN%"=="" (
    echo [ERROR] Token cannot be empty!
    pause
    exit /b 1
)

echo.
echo [STEP 2] Configure Git with Token
cd "C:\Users\opera\Downloads\weather-station-server"

echo [INFO] Setting remote URL with token...
git remote set-url origin https://ijuloss:%TOKEN%@github.com/ijuloss/weather-station-server.git

echo [STEP 3] Push to GitHub
echo [INFO] Pushing to master branch...
git push -u origin master

if %errorlevel% neq 0 (
    echo.
    echo [ERROR] Push failed!
    echo Troubleshooting:
    echo 1. Check if token is correct (starts with ghp_)
    echo 2. Check if repository exists: https://github.com/ijuloss/weather-station-server
    echo 3. Check network connection
    echo 4. Try manual push: git push -u origin master
    pause
    exit /b 1
)

echo.
echo ========================================
echo   SUCCESS!
echo ========================================
echo.
echo Repository URL: https://github.com/ijuloss/weather-station-server
echo Branch: master
echo.
echo Next steps:
echo 1. Visit your repository on GitHub
echo 2. Verify files are uploaded
echo 3. Continue with deployment to server
echo.
pause
