@echo off
echo ========================================
echo   WEATHER STATION - GIT INITIALIZATION
echo   Setup GitHub Repository
echo ========================================
echo.

:: Configuration - MODIFY THESE VALUES
set GITHUB_USERNAME=your_github_username
set REPO_NAME=weather-station-server
set PROJECT_PATH=C:\Users\opera\Downloads\weather-station-server

echo [INFO] GitHub Username: %GITHUB_USERNAME%
echo [INFO] Repository: %REPO_NAME%
echo [INFO] Project Path: %PROJECT_PATH%
echo.

:: Check if Git is installed
where git >nul 2>&1
if %errorlevel% neq 0 (
    echo [ERROR] Git not found!
    echo Please install Git from: https://git-scm.com/
    pause
    exit /b 1
)

echo [STEP 1] Navigate to project directory...
cd /d "%PROJECT_PATH%"

echo [STEP 2] Initialize Git repository...
git init

echo [STEP 3] Configure Git user (first time only)...
git config --global user.name "Your Name"
git config --global user.email "your.email@example.com"

echo [STEP 4] Create .gitignore file...
echo # Python > .gitignore
echo __pycache__/ >> .gitignore
echo *.pyc >> .gitignore
echo .env >> .gitignore
echo .env.local >> .gitignore
echo venv/ >> .gitignore
echo *.log >> .gitignore
echo .DS_Store >> .gitignore
echo Thumbs.db >> .gitignore
echo. >> .gitignore
echo # IDE >> .gitignore
echo .vscode/ >> .gitignore
echo *.swp >> .gitignore
echo *.swo >> .gitignore

echo [STEP 5] Add all files...
git add .

echo [STEP 6] Check status...
git status

echo [STEP 7] Create initial commit...
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

echo.
echo [STEP 8] Add remote repository...
echo Please create repository on GitHub first:
echo 1. Go to: https://github.com/new
echo 2. Repository name: %REPO_NAME%
echo 3. Description: Weather Station Backend API - Production Ready
echo 4. Set to Private or Public
echo 5. Click "Create repository"
echo.
echo After creating repository, press Enter to continue...
pause

echo [STEP 9] Add GitHub remote...
git remote add origin https://github.com/%GITHUB_USERNAME%/%REPO_NAME%.git

echo [STEP 10] Push to GitHub...
echo You will be prompted for GitHub credentials:
echo Username: %GITHUB_USERNAME%
echo Password: Your GitHub Personal Access Token
echo.
echo Get Personal Access Token from: https://github.com/settings/tokens
echo.
git push -u origin main

if %errorlevel% neq 0 (
    echo.
    echo [ERROR] Push failed!
    echo Common issues:
    echo 1. Repository doesn't exist on GitHub
    echo 2. Wrong username/password
    echo 3. Need Personal Access Token (not password)
    echo 4. Network connectivity issues
    echo.
    echo Troubleshooting:
    echo - Check repository exists: https://github.com/%GITHUB_USERNAME%/%REPO_NAME%
    echo - Create Personal Access Token: https://github.com/settings/tokens
    echo - Try manual push: git push -u origin main
    pause
    exit /b 1
)

echo.
echo ========================================
echo   GIT SETUP COMPLETED!
echo ========================================
echo.
echo Repository URL: https://github.com/%GITHUB_USERNAME%/%REPO_NAME%
echo.
echo Next steps:
echo 1. Visit your repository on GitHub
echo 2. Verify files are uploaded
echo 3. Setup deployment to server
echo.
echo Deployment commands (on server):
echo   git clone https://github.com/%GITHUB_USERNAME%/%REPO_NAME%.git /opt/weather-station
echo   cd /opt/weather-station
echo   ./scripts/install-debian12.sh
echo.
pause
