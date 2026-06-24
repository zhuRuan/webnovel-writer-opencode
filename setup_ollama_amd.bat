@echo off
echo ========================================
echo   Ollama AMD GPU (9070 XT) 一键配置
echo ========================================
echo.

:: ==========================================
:: Step 1: 设置 AMD GPU 环境变量
:: ==========================================
echo [1/4] 配置 GPU 环境变量...

:: RDNA3 架构 (9070 XT) 需要这个变量
setx HSA_OVERRIDE_GFX_VERSION 11.0.0

:: 强制 Ollama 使用 AMD GPU
setx OLLAMA_DEVICE hip

:: 模型存储路径 (默认在 C 盘，如果想放 D 盘改这里)
:: setx OLLAMA_MODELS D:\ollama\models

echo 环境变量已设置

:: ==========================================
:: Step 2: 检查 Ollama 服务
:: ==========================================
echo.
echo [2/4] 重启 Ollama 服务...

:: 强制杀掉 Ollama
taskkill /f /im "ollama app.exe" >nul 2>&1
taskkill /f /im "ollama.exe" >nul 2>&1

:: 等待2秒
timeout /t 2 /nobreak >nul

:: 启动 Ollama (GUI 模式)
start "" "C:\Users\69490\AppData\Local\Programs\Ollama\ollama app.exe"

echo Ollama 已重启

:: ==========================================
:: Step 3: 验证 GPU 是否被识别
:: ==========================================
echo.
echo [3/4] 等待 Ollama 就绪 (5秒)...
timeout /t 5 /nobreak >nul

:: 检查 GPU 识别 (Windows 上用 ps 查日志)
echo 检查 GPU 状态...
curl -s http://localhost:11434/api/tags 2>nul | findstr "models" >nul && echo Ollama API 正常 || echo 请确保 Ollama 托盘图标已出现

:: ==========================================
:: Step 4: 拉取模型
:: ==========================================
echo.
echo [4/4] 准备拉取模型...
echo.
echo 推荐模型 (按 GPU 能力排序):
echo   1. qwen2.5:14b-instruct-q6_K    (约12GB, 推荐)
echo   2. qwen2.5:32b-instruct-q4_K_M  (约19GB, 超16GB不推荐)  
echo   3. qwen2.5:14b-instruct-q8_0    (约15GB, 高质量)
echo.
echo 运行以下命令拉取:
echo   ollama pull qwen2.5:14b-instruct-q6_K
echo.
echo ========================================
echo   配置完成！
echo ========================================
echo.
echo 验证 GPU 是否生效:
echo   打开任务管理器 -> 性能 -> GPU
echo   然后运行: ollama run qwen2.5:14b "你好"
echo   如果 GPU 使用率上升，说明配置成功
echo.
pause
