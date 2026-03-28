@echo off
rm -f "%CD%\nul" 2>nul
cmd /c "rm -f \"%CD%\nul\"" 2>nul
chcp 65001 >nul 2>&1

echo.
echo ========================================
echo   Webnovel Writer for OpenCode
echo   Installer v1.2.0
echo ========================================
echo.

set "PROJECT_DIR=%CD%"
set "REPO=lujih/webnovel-writer-opencode"
set "SUCCESS=0"

echo [0/4] Cleaning existing .opencode...
if exist ".opencode" (
    rmdir /S /Q ".opencode"
)

echo [1/4] Downloading...
powershell -Command "try { Invoke-WebRequest -Uri 'https://github.com/%REPO%/archive/refs/heads/master.zip' -OutFile 'webnovel-writer.zip' -UseBasicParsing -TimeoutSec 60 -ErrorAction Stop; exit 0 } catch { exit 1 }"
if %errorlevel% neq 0 (
    echo Trying mirror...
    powershell -Command "try { Invoke-WebRequest -Uri 'https://github.akams.cn/%REPO%/archive/refs/heads/master.zip' -OutFile 'webnovel-writer.zip' -UseBasicParsing -TimeoutSec 60 -ErrorAction Stop; exit 0 } catch { exit 1 }"
)

if not exist "webnovel-writer.zip" (
    echo ERROR: Download failed
    echo.
    echo Solutions:
    echo   1. Check internet connection
    echo   2. Use VPN if in restricted region
    echo   3. Download manually from: https://github.com/%REPO%/archive/master.zip
    echo.
    pause
    exit /b 1
)

echo [2/4] Extracting...
powershell -Command "Expand-Archive -Path 'webnovel-writer.zip' -DestinationPath '.' -Force"
del /Q webnovel-writer.zip 2>nul

echo [3/4] Copying files...
if not exist ".opencode" mkdir ".opencode"

set "SOURCE_DIR="
for /d %%d in ("%PROJECT_DIR%\webnovel-writer-opencode-*") do (
    set "SOURCE_DIR=%%d"
)

if not defined SOURCE_DIR goto :check_empty
if "%SOURCE_DIR%"=="" goto :check_empty
goto :dir_ok

:check_empty
echo ERROR: Extraction failed - source dir not found
pause
exit /b 1

:dir_ok

xcopy /E /I /Y "%SOURCE_DIR%\.opencode" ".opencode\" >nul 2>&1
echo   .opencode: OK

echo [4/4] Finalizing...
if exist "%SOURCE_DIR%\requirements.txt" (
    pip install -r "%SOURCE_DIR%\requirements.txt" >nul 2>&1
    if %errorlevel% equ 0 (
        echo   Python deps: OK
    ) else (
        echo   Python deps: Already installed or skipped
    )
)
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
    echo   .env created
) else (
    echo   .env: Already exists, skipped
)

REM Cleanup source directory
if defined SOURCE_DIR rmdir /S /Q "%SOURCE_DIR%" 2>nul

echo.
echo ========================================
echo   Webnovel Writer for OpenCode
echo   Installation Complete!
echo ========================================
echo.
echo Next steps:
echo   1. Edit .env and add your API Key
echo   2. Restart OpenCode and enjoy writing!
echo.
pause
