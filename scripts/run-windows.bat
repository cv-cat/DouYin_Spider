@echo off
chcp 65001 >nul
setlocal
cd /d "%~dp0.."

echo ============================================
echo    两把刷子获客 - Windows 启动脚本
echo ============================================
echo.

REM ---- 前置检查：Python / Node.js ----
where python >nul 2>nul
if errorlevel 1 (
  echo [错误] 没找到 Python。请先安装 Python 3.11 或 3.12（勾选 Add Python to PATH）：
  echo        https://www.python.org/downloads/windows/
  pause
  exit /b 1
)
where npm >nul 2>nul
if errorlevel 1 (
  echo [错误] 没找到 Node.js / npm。请先安装 Node.js LTS：
  echo        https://nodejs.org/
  pause
  exit /b 1
)

REM ---- 1) Python 虚拟环境 + 依赖 + 浏览器 ----
if not exist ".venv\Scripts\python.exe" (
  echo [1/3] 首次运行：创建虚拟环境并安装 Python 依赖...
  python -m venv .venv
  call ".venv\Scripts\activate.bat"
  python -m pip install --upgrade pip
  pip install -r requirements.txt
  echo [1/3] 下载 chromium 浏览器（约 150MB，请耐心等待）...
  python -m playwright install chromium
) else (
  call ".venv\Scripts\activate.bat"
)

REM ---- 2) Windows 原生 node_modules（抖音签名用，必须本平台编译）----
if not exist "node_modules\canvas\build" (
  echo [2/3] 安装 Node 签名依赖（删除跨平台的旧 node_modules 后重装，首次较慢）...
  if exist node_modules rmdir /s /q node_modules
  npm install
)

REM ---- 3) 启动客户端 ----
echo [3/3] 启动客户端...
echo.
python -m desktop.client

echo.
echo 程序已退出。
pause
