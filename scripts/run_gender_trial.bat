@echo off
chcp 65001 >nul
set "TOOL_DIR=%~dp0"
"%TOOL_DIR%.venv_runtime\Scripts\python.exe" "%TOOL_DIR%clean_douyin_gender.py" --limit 3
pause
