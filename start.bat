@echo off
chcp 65001 >nul
cd /d "%~dp0"
echo =========================================
echo       正在启动 AI Agent 个人助手
echo =========================================

:: 1. 检查并激活虚拟环境
if exist venv\Scripts\activate.bat (
    echo [1/3] 正在激活虚拟环境...
    call venv\Scripts\activate.bat
) else (
    echo [警告] 未找到 venv 虚拟环境，请确保已在项目目录下创建并安装了依赖。
)

:: 2. 启动 FastAPI 后端 (新开一个窗口)
echo [2/3] 正在启动后端服务 (FastAPI)...
start "AI Agent Backend" cmd /k "chcp 65001 >nul && call venv\Scripts\activate.bat && uvicorn main:app --reload"

:: 等待 2 秒，确保后端先启动
timeout /t 2 >nul

:: 3. 启动 Streamlit 前端 (新开一个窗口)
echo [3/3] 正在启动前端界面 (Streamlit)...
start "AI Agent Frontend" cmd /k "chcp 65001 >nul && call venv\Scripts\activate.bat && streamlit run app.py"

echo =========================================
echo ✅ 启动指令已发送！请查看弹出的新窗口。
echo =========================================
timeout /t 3 >nul
exit