@echo off
echo ========================================
echo   Ollama AMD RX 9070 XT GPU 加速配置
echo ========================================
echo.

:: ==========================================
:: ROCm 6.4 路径
:: ==========================================
set ROCM_PATH=C:\Program Files\AMD\ROCm\6.4
set HIP_PATH=%ROCM_PATH%
set PATH=%ROCM_PATH%\bin;%PATH%

:: ==========================================
:: RDNA 3.5 (9070 XT) GPU 变量
:: ==========================================
:: 9070 XT 是 RDNA 3.5, 需要 12.0.0
setx HSA_OVERRIDE_GFX_VERSION 12.0.0
:: 如果 12.0.0 不行, 试试下面这行
:: setx HSA_OVERRIDE_GFX_VERSION 11.0.0

:: 使用第一个 GPU
setx HIP_VISIBLE_DEVICES 0

:: 后台编译 (减少首次推理延迟)
setx GPU_MAX_HW_QUEUES 2

:: ==========================================
:: Ollama GPU 配置
:: ==========================================
:: 强制使用 AMD GPU
setx OLLAMA_DEVICE hip

:: 模型层数全部放 GPU (加速)
setx OLLAMA_GPU_LAYERS 999

:: 上下文窗口 (K/V cache 大小, 根据显存调整)
:: 16GB 显存, 留 2GB 给系统, 设 14GB
setx OLLAMA_CONTEXT_LENGTH 8192

:: 并行请求数
setx OLLAMA_NUM_PARALLEL 1

:: ==========================================
:: 重启 Ollama
:: ==========================================
echo.
echo 重启 Ollama...
taskkill /f /im "ollama app.exe" >nul 2>&1
taskkill /f /im "ollama.exe" >nul 2>&1
timeout /t 3 /nobreak >nul

echo 启动 Ollama (带环境变量)...
set HSA_OVERRIDE_GFX_VERSION=12.0.0
set HIP_VISIBLE_DEVICES=0
set OLLAMA_GPU_LAYERS=999
set OLLAMA_DEVICE=hip
start "" "C:\Users\69490\AppData\Local\Programs\Ollama\ollama app.exe"

echo.
echo ========================================
echo   配置完成！
echo ========================================
echo.
echo 验证 GPU 加速:
echo   1. 打开任务管理器 -> 性能 -> GPU
echo   2. 运行: ollama run qwen3.5-local "写一首七言绝句" --verbose
echo   3. 观察 GPU 使用率应上升到 80%%+
echo.
echo 如果 GPU 还是不动:
echo   - 试试改成: setx HSA_OVERRIDE_GFX_VERSION 11.0.0
echo   - 确认 ROCm 6.4 完整安装
echo   - 检查: ollama run qwen3.5-local --verbose 的输出
echo.
pause
