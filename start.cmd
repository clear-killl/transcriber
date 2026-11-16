@echo off
setlocal
cd /d "%~dp0"
if not exist ".venv\Scripts\pythonw.exe" (
    powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0setup.ps1"
    if errorlevel 1 goto failed
)
".venv\Scripts\python.exe" -c "import PySide6.QtWidgets, faster_whisper, docx" >nul 2>&1
if errorlevel 1 (
    powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0setup.ps1"
    if errorlevel 1 goto failed
)
start "" ".venv\Scripts\pythonw.exe" -m transcriber %*
exit /b 0
:failed
echo Setup failed. See the message above.
pause
exit /b 1
