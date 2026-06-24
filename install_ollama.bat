@echo off
echo ========================================
echo   名家技法采集 — Ollama 一键部署
echo ========================================
echo.

:: Step 1: Check if Ollama is installed
where ollama >nul 2>nul
if %errorlevel% neq 0 (
    echo [1/3] 下载 Ollama...
    curl -L https://ollama.com/download/OllamaSetup.exe -o %TEMP%\OllamaSetup.exe
    start /wait %TEMP%\OllamaSetup.exe
    echo Ollama 安装完成，请确保它正在运行
) else (
    echo [1/3] Ollama 已安装
)

:: Step 2: Pull the model
echo.
echo [2/3] 拉取 qwen2.5:14b-instruct-q6_K (约8GB，需要几分钟)...
ollama pull qwen2.5:14b-instruct-q6_K

:: Step 3: Verify
echo.
echo [3/3] 验证模型...
ollama run qwen2.5:14b "你好，请用一句话介绍你自己"
echo.
echo ========================================
echo   部署完成！回到 Dashboard 开始采集
echo ========================================
pause
