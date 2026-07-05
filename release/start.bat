@echo off
chcp 65001 >nul
cd /d "%~dp0"

echo.
echo   ====================================
echo   :                                  :
echo   :     🍺 云雾酒馆 正在开门...       :
echo   :                                  :
echo   ====================================
echo.

setlocal enabledelayedexpansion

echo [1/3] 清理旧进程...
for /f "tokens=5" %%a in ('netstat -ano ^| findstr ":9000 "') do (
    if not "%%a"=="" taskkill /F /PID %%a >nul 2>&1
)
timeout /t 1 /nobreak >nul

echo [2/3] 配置 AI 引擎...
set AI_API_KEY=public
set AI_API_URL=https://opencode.ai/zen/v1/chat/completions
set AI_MODEL=mimo-v2.5-free
set PYTHONIOENCODING=utf-8

echo   AI: opencode.ai/zen (free)
echo   Key: public
echo.

echo [3/3] 启动服务器...

if exist "云雾酒馆.exe" (
    start "" http://127.0.0.1:9000
    "云雾酒馆.exe"
) else if exist "tavern.exe" (
    start "" http://127.0.0.1:9000
    "tavern.exe"
) else (
    echo   ❌ 错误: 未找到可执行文件
    echo   请确保 tavern.exe 或 云雾酒馆.exe 存在于当前目录
)

echo.
pause