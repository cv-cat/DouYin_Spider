@echo off
chcp 65001 >nul
set "TOOL_DIR=%~dp0"
"%TOOL_DIR%.venv_runtime\Scripts\python.exe" "%TOOL_DIR%clean_douyin_gender.py" --limit 50 --tabs 3 --wait-ms 3000 --stagger-ms 2000 --request-interval-ms 5000 --retries 0 --repair-retries 2 --repair-cooldown-ms 10000 --checkpoint "%TOOL_DIR%正式清洗50个_3标签结果.json"
pause
