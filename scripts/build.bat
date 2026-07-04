@echo off
chcp 65001 >nul
cd /d "%~dp0.."

echo.
echo   ==============================================
echo   :     Tavern Build Tool                       :
echo   ==============================================
echo.

set "BUILD_DIR=build"
set "DIST_DIR=dist"
set "OUTPUT_DIR=release"
set "VERSION_FILE=version.json"

if "%1"=="major" goto BUMP_MAJOR
if "%1"=="minor" goto BUMP_MINOR
if "%1"=="patch" goto BUMP_PATCH
goto SHOW_VERSION

:BUMP_MAJOR
echo [0/5] Bumping version (major)...
python scripts/bump_version.py major
goto CHECK_BUMP

:BUMP_MINOR
echo [0/5] Bumping version (minor)...
python scripts/bump_version.py minor
goto CHECK_BUMP

:BUMP_PATCH
echo [0/5] Bumping version (patch)...
python scripts/bump_version.py patch
goto CHECK_BUMP

:CHECK_BUMP
if %errorlevel% neq 0 (
    echo ERROR: Version bump failed
    pause
    exit /b 1
)

:SHOW_VERSION
python scripts/bump_version.py show

echo [1/5] Cleaning old builds...
if exist "%BUILD_DIR%" rd /s /q "%BUILD_DIR%"
if exist "%DIST_DIR%" rd /s /q "%DIST_DIR%"
if exist "%OUTPUT_DIR%" rd /s /q "%OUTPUT_DIR%"

echo [2/5] Installing dependencies...
pip install -r src/backend/requirements.txt >nul 2>&1
if %errorlevel% neq 0 (
    echo ERROR: Dependency install failed
    pause
    exit /b 1
)
echo   Dependencies installed

echo [3/5] Building with PyInstaller...
pyinstaller ^
    --name "tavern" ^
    --onefile ^
    --add-data "src/backend\templates;templates" ^
    --add-data "src/backend\static;static" ^
    --add-data "src/backend\.env;." ^
    --add-data "src/backend\agents.json;." ^
    --add-data "src/backend\worldbooks.json;." ^
    --add-data "src/backend\world_ratings.json;." ^
    --add-data "src/backend\world_submissions.json;." ^
    --add-data "src/backend\rpg_sessions.json;." ^
    --add-data "src/backend\usage_log.json;." ^
    --add-data "version.json;." ^
    --add-data "CHANGELOG.json;." ^
    --hidden-import=flask_sqlalchemy ^
    --hidden-import=flask_login ^
    --hidden-import=werkzeug.security ^
    --hidden-import=requests ^
    --hidden-import=dotenv ^
    --hidden-import=uuid ^
    --hidden-import=json ^
    --hidden-import=threading ^
    --hidden-import=datetime ^
    --hidden-import=secrets ^
    --hidden-import=re ^
    --noconfirm ^
    src/backend/app.py

if %errorlevel% neq 0 (
    echo ERROR: Build failed
    pause
    exit /b 1
)
echo   PyInstaller build completed

echo [4/5] Organizing release files...
mkdir "%OUTPUT_DIR%"
copy "%DIST_DIR%\tavern.exe" "%OUTPUT_DIR%\tavern.exe" >nul
copy "tavern\start.bat" "%OUTPUT_DIR%\start.bat" >nul
copy "tavern\start.ps1" "%OUTPUT_DIR%\start.ps1" >nul
copy "src/backend\.env" "%OUTPUT_DIR%\.env" >nul
copy "src/backend\agents.json" "%OUTPUT_DIR%\agents.json" >nul
copy "src/backend\worldbooks.json" "%OUTPUT_DIR%\worldbooks.json" >nul
copy "src/backend\world_ratings.json" "%OUTPUT_DIR%\world_ratings.json" >nul
copy "src/backend\world_submissions.json" "%OUTPUT_DIR%\world_submissions.json" >nul
copy "src/backend\rpg_sessions.json" "%OUTPUT_DIR%\rpg_sessions.json" >nul
copy "src/backend\usage_log.json" "%OUTPUT_DIR%\usage_log.json" >nul
copy "src/backend\feedback.json" "%OUTPUT_DIR%\feedback.json" >nul
copy "%VERSION_FILE%" "%OUTPUT_DIR%\version.json" >nul
copy "CHANGELOG.json" "%OUTPUT_DIR%\CHANGELOG.json" >nul
copy "src/backend\requirements.txt" "%OUTPUT_DIR%\requirements.txt" >nul

if exist "src/backend/tavern.db" (
    copy "src/backend/tavern.db" "%OUTPUT_DIR%\tavern.db" >nul
) else if exist "src/backend/instance/tavern.db" (
    copy "src/backend/instance/tavern.db" "%OUTPUT_DIR%\tavern.db" >nul
)

xcopy "src/backend\static" "%OUTPUT_DIR%\static\" /E /Y >nul
xcopy "src/backend\templates" "%OUTPUT_DIR%\templates\" /E /Y >nul

echo   Files organized

echo [5/5] Cleaning temp files...
if exist "%BUILD_DIR%" rd /s /q "%BUILD_DIR%"
if exist "%DIST_DIR%" rd /s /q "%DIST_DIR%"
if exist "tavern.spec" del "tavern.spec"

echo.
echo   ==============================================
echo   :     BUILD SUCCESSFUL!                       :
echo   :     Output: %OUTPUT_DIR%                    :
echo   ==============================================
echo.

pause