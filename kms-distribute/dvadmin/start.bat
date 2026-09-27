@echo off
cd /d "%~dp0"
start "PQKDS-Backend" cmd /k "cd /d %~dp0backend && python manage.py runserver 0.0.0.0:8000"
timeout /t 3 /nobreak >nul
start "PQKDS-Frontend" cmd /k "cd /d %~dp0web && npm run dev"
echo.
echo   Backend: http://localhost:8000
echo   Frontend: http://localhost:8081
echo   Login: admin / admin123456
echo.
pause
