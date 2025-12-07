@echo off
cd /d "%~dp0"

REM Check for venv in parent directory (project root)
if exist "..\venv\Scripts\python.exe" (
    echo Using virtual environment...
    "..\venv\Scripts\python.exe" gui_app.py
) else (
    echo Using system Python...
    python gui_app.py
)

if errorlevel 1 (
    echo.
    echo Error: Failed to start the application.
    echo Make sure Python is installed and dependencies are installed.
    echo Run: pip install -r ..\requirements.txt
    pause
)

