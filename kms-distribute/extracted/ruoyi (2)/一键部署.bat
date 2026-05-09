@echo off
chcp 65001 >nul 2>&1
cd /d "%~dp0"
echo.
echo   PQKDS 一键自动化部署
echo   =====================
echo.
echo   默认数据库配置: root/password@127.0.0.1:3306/falcon_kds
echo   如需修改，请用: python auto_deploy.py --db-pass 你的密码
echo.
python auto_deploy.py %*
echo.
pause
