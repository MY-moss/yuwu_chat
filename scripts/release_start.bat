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
set PYTHONIOENCODING=utf-8

if exist ".env" (
    for /f "usebackq tokens=1,2 delims==" %%a in (".env") do (
        if "%%a"=="AI_API_KEY" set "AI_API_KEY=%%b"
        if "%%a"=="AI_API_URL" set "AI_API_URL=%%b"
        if "%%a"=="AI_MODEL" set "AI_MODEL=%%b"
        if "%%a"=="SECRET_KEY" set "SECRET_KEY=%%b"
    )
)

if defined AI_API_KEY (
    echo   AI: configured \(Key: ********\)
) else (
    echo   AI: not configured \(edit .env to set AI_API_KEY\)
)
echo.

echo [3/3] 启动服务器...

if exist "云雾酒馆.exe" (
    start "" http://127.0.0.1:9000
    "云雾酒馆.exe"
) else if exist "tavern.exe" (
    start "" http://127.0.0.1:9000
    "tavern.exe"
)

echo.
pause