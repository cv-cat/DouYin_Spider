@echo off
chcp 65001 >nul
set "TOOL_DIR=%~dp0"
"%TOOL_DIR%.venv_runtime\Scripts\python.exe" "%TOOL_DIR%clean_douyin_gender.py" --dry-run --limit 20 --tabs 5 --checkpoint "%TOOL_DIR%gender_trial_concurrent.json"
pause
