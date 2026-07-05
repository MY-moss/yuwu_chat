@echo off
chcp 65001 >nul
title 云雾酒馆
cd /d "%~dp0"

set AI_API_KEY=public
set AI_API_URL=https://opencode.ai/zen/v1/chat/completions
set PYTHONIOENCODING=utf-8

if exist "release\tavern.exe" (
    echo 启动发布版...
    start "" "http://127.0.0.1:9000"
    cd release
    tavern.exe
) else (
    echo 启动开发版...
    python "src\backend\app.py"
    start "" "http://127.0.0.1:9000"
)

pause
