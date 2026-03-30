@echo off
setlocal EnableDelayedExpansion

chcp 65001 >nul 2>&1

echo.
echo ========================================
echo   Webnovel Writer for OpenCode
echo   Installer v1.3.0
echo ========================================
echo.

set "PROJECT_DIR=%CD%"
set "REPO=lujih/webnovel-writer-opencode"

REM ========================================
REM [0/5] Dependency Check
REM ========================================
echo [0/5] Checking dependencies...

REM Check Python
python --version >nul 2>&1
if %errorlevel% neq 0 (
    python3 --version >nul 2>&1
    if %errorlevel% neq 0 (
        echo ERROR: Python is not installed
        echo.
        echo Please install Python 3.9 or higher:
        echo   Download: https://www.python.org/downloads/
        echo.
        pause
        exit /b 1
    ) else (
        set "PYTHON=python3"
    )
) else (
    set "PYTHON=python"
)

!PYTHON! -c "import sys; v=sys.version_info[:2]; sys.exit(0 if v[0]>3 or (v[0]==3 and v[1]>=9) else 1)" 2>nul
if %errorlevel% neq 0 (
    for /f "tokens=*" %%v in ('!PYTHON! -c "import sys; print(sys.version)"') do set "PYTHON_VERSION=%%v"
    echo ERROR: Python !PYTHON_VERSION! is too old. Requires Python 3.9+
    echo Please upgrade: https://www.python.org/downloads/
    pause
    exit /b 1
)

for /f "tokens=*" %%v in ('!PYTHON! -c "import sys; print(f\"{sys.version_info[0]}.{sys.version_info[1]}\")"') do set "PYTHON_VERSION=%%v"
echo      Python: !PYTHON_VERSION! OK

REM Check pip
!PYTHON! -m pip --version >nul 2>&1
if %errorlevel% neq 0 (
    echo ERROR: pip is not installed
    echo Try: !PYTHON! -m ensurepip --upgrade
    pause
    exit /b 1
)
echo      pip: OK

REM Check PowerShell
powershell -Command "exit 0" >nul 2>&1
if %errorlevel% neq 0 (
    echo WARNING: PowerShell not found, some features may not work
)

echo.

echo Project: !PROJECT_DIR!

REM ========================================
REM [1/5] Clean existing .opencode
REM ========================================
echo [1/5] Cleaning existing .opencode...
if exist ".opencode" (
    rmdir /S /Q ".opencode" 2>nul
)

REM ========================================
REM [2/5] Download with retry
REM ========================================
echo [2/5] Downloading...
set "SUCCESS=0"
set "RETRY=0"

:download_retry
set /a RETRY+=1
if !RETRY! gtr 3 (
    echo ERROR: Download failed after 3 attempts
    echo.
    echo Solutions:
    echo   1. Check internet connection
    echo   2. Use VPN if in restricted region
    echo   3. Download manually: https://github.com/%REPO%/archive/master.zip
    echo.
    pause
    exit /b 1
)

echo       Attempt !RETRY!/3...
powershell -Command "try { Invoke-WebRequest -Uri 'https://github.com/%REPO%/archive/refs/heads/master.zip' -OutFile 'webnovel-writer.zip' -UseBasicParsing -TimeoutSec 60 -ErrorAction Stop; exit 0 } catch { exit 1 }"
if %errorlevel% neq 0 (
    echo       Trying mirror...
    powershell -Command "try { Invoke-WebRequest -Uri 'https://github.akams.cn/%REPO%/archive/refs/heads/master.zip' -OutFile 'webnovel-writer.zip' -UseBasicParsing -TimeoutSec 60 -ErrorAction Stop; exit 0 } catch { exit 1 }"
)

if not exist "webnovel-writer.zip" (
    echo       Download failed, retrying...
    timeout /t 3 /nobreak >nul
    goto :download_retry
)

set "SUCCESS=1"

REM ========================================
REM [3/5] Extract
REM ========================================
echo [3/5] Extracting...
powershell -Command "Expand-Archive -Path 'webnovel-writer.zip' -DestinationPath '.' -Force"
del /Q /F "webnovel-writer.zip" 2>nul

REM Safe cleanup - avoid nul device
for %%f in (webnovel-writer.zip) do del /Q /F "%%f" 2>nul

REM ========================================
REM [4/5] Copy files
REM ========================================
echo [4/5] Installing to .opencode...
if not exist ".opencode" mkdir ".opencode"

set "SOURCE_DIR="
for /d %%d in ("!PROJECT_DIR!\webnovel-writer-opencode-*") do (
    set "SOURCE_DIR=%%d"
)

if not defined SOURCE_DIR goto :extract_error
if "!SOURCE_DIR!"=="" goto :extract_error
goto :source_ok

:extract_error
echo ERROR: Extraction failed - source directory not found
echo.
pause
exit /b 1

:source_ok

xcopy /E /I /Y "!SOURCE_DIR!\.opencode" ".opencode\" >nul 2>&1
echo      .opencode: OK

REM ========================================
REM [5/5] Install dependencies
REM ========================================
echo [5/5] Installing Python dependencies...

set "PIP_SUCCESS=0"
if exist "!SOURCE_DIR!\requirements.txt" (
    echo       Installing dependencies...
    !PYTHON! -m pip install -r "!SOURCE_DIR!\requirements.txt" --quiet >nul 2>&1
    if !errorlevel! equ 0 (
        set "PIP_SUCCESS=1"
    ) else (
        !PYTHON! -m pip install -r "!SOURCE_DIR!\requirements.txt" >nul 2>&1
        if !errorlevel! equ 0 set "PIP_SUCCESS=1"
    )
    
    if !PIP_SUCCESS! equ 1 (
        echo      Python deps: OK
    ) else (
        echo      Python deps: Already installed or skipped
    )
)

REM Create .env
echo      Creating .env...
if not exist ".env" (
    (
        echo # Webnovel Writer for OpenCode Config
        echo # Fill in your API Key
        echo.
        echo EMBED_BASE_URL=https://api-inference.modelscope.cn/v1
        echo EMBED_MODEL=Qwen/Qwen3-Embedding-8B
        echo EMBED_API_KEY=your_api_key
        echo.
        echo RERANK_BASE_URL=https://api.jina.ai/v1
        echo RERANK_MODEL=jina-reranker-v3
        echo RERANK_API_KEY=your_api_key
    ) > .env
    echo      .env: CREATED
) else (
    echo      .env: Already exists, skipped
)

REM Cleanup source directory (safe deletion, avoid nul)
if defined SOURCE_DIR (
    if exist "!SOURCE_DIR!" rmdir /S /Q "!SOURCE_DIR!" 2>nul
)

REM Safe temp file cleanup - avoid using *.* pattern
for /f "tokens=*" %%f in ('dir /b *.tmp 2^>nul') do (
    del /Q /F "%%f" 2>nul
)
for /f "tokens=*" %%f in ('dir /b *.zip 2^>nul') do (
    del /Q /F "%%f" 2>nul
)

echo.
echo ========================================
echo   Webnovel Writer for OpenCode
echo   Installation Complete!
echo ========================================
echo.
echo Next steps:
echo   1. Edit .env and add your API Key
echo      - Get API keys from:
echo        * ModelScope: https://modelscope.cn/my/settings
echo        * Jina AI: https://jina.ai/
echo   2. Restart OpenCode and run /webnovel-init
echo   3. Enjoy writing your novel!
echo.
pause
