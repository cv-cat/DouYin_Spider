@echo off
chcp 65001 >nul
REM ============================================================
REM  两把刷子获客 - Windows 一键启动
REM  下载 zip 解压后，双击本文件即可。
REM  首次会自动安装 Python / Node.js / 依赖 / 浏览器，无需手动配环境。
REM ============================================================
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\windows-setup.ps1"
echo.
pause
