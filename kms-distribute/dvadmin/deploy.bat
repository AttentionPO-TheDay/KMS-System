@echo off
chcp 65001 >nul 2>&1
cd /d "%~dp0"
echo.
echo   PQKDS One-Click Deploy
echo   Default: root/password@127.0.0.1:3306/falcon_kds
echo   Custom:  python deploy.py --db-pass YOUR_PASSWORD
echo.
python deploy.py %*
pause
