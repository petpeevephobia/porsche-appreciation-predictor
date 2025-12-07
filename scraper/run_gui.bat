@echo off
cd /d "%~dp0"

REM Check for venv in parent directory (project root)
if exist "..\venv\Scripts\python.exe" (
    "..\venv\Scripts\python.exe" gui_app.py
) else (
    python gui_app.py
)

pause

