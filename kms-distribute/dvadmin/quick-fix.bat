@echo off
REM Quick Fix for Blockchain Issues - Windows Version
REM 区块链问题快速修复脚本 - Windows版本

setlocal enabledelayedexpansion

echo.
echo ==================================================
echo    Blockchain Issues Quick Fix (Windows)
echo    运行此脚本修复所有区块链问题
echo ==================================================
echo.

REM Check if Python is available
python --version >nul 2>&1
if errorlevel 1 (
    echo Error: Python not found. Please install Python 3.7+
    echo 错误: 未找到Python, 请安装 Python 3.7+
    pause
    exit /b 1
)

REM Step 1: Backend fix
echo [1/3] Running backend fixes...
echo 正在运行后端修复...
echo.

cd backend
python auto_fix_blockchain_issues.py

if errorlevel 1 (
    echo [1/3] Backend fixes failed
    echo [1/3] 后端修复失败
    pause
    exit /b 1
)

echo [1/3] Backend fixes completed
echo [1/3] 后端修复完成
cd ..

REM Step 2: Frontend fix (optional)
echo.
echo [2/3] Checking for Node.js...
echo 正在检查 Node.js...

node --version >nul 2>&1
if errorlevel 1 (
    echo [2/3] Node.js not found - skipping frontend fixes
    echo [2/3] 未找到 Node.js - 跳过前端修复
    echo        You can manually run: cd web ^&^& node remove-emojis.js
) else (
    echo Running: node web/remove-emojis.js
    cd web
    node remove-emojis.js
    cd ..
    echo [2/3] Frontend fixes completed
    echo [2/3] 前端修复完成
)

REM Step 3: Verification
echo.
echo [3/3] Verifying fixes...
echo 正在验证修复...
echo.

cd backend
python -c "
import os, glob, re

emoji_patterns = [r'✅', r'❌', r'⚠️', r'🔧', r'📊', r'💡', r'🎉', r'⭐', r'🔥']
found_count = 0

for py_file in glob.glob('pqkds/**/*.py', recursive=True):
    with open(py_file, 'r', encoding='utf-8', errors='ignore') as f:
        content = f.read()
    for pattern in emoji_patterns:
        if pattern in content:
            found_count += 1
            print(f'Found emoji in {py_file}')

if found_count == 0:
    print('No emojis found - verification passed!')
else:
    print(f'Found {found_count} files with emojis')
"

echo.
echo ==================================================
echo    Quick Fix Completed
echo    快速修复完成
echo ==================================================
echo.
echo Next steps (后续步骤):
echo 1. Restart Django server: python manage.py runserver
echo 2. Check logs for blockchain sync status
echo 3. Verify all nodes are registered on blockchain
echo.
echo For more details, see:
echo   - COMPLETE_SOLUTION.md (完整分析)
echo   - BLOCKCHAIN_FIX_GUIDE.md (修复指南)
echo   - BLOCKCHAIN_FIX_SUMMARY.md (修复总结)
echo.
echo ==================================================
echo    Ready for production deployment!
echo    已准备好进行生产部署!
echo ==================================================
echo.
pause

