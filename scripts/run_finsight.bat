@echo off
rem Launch FinSight using the project virtual environment.
cd /d "%~dp0.."
if not exist .venv\Scripts\activate.bat (
    echo Run scripts\install_windows.bat first.
    pause
    exit /b 1
)
call .venv\Scripts\activate.bat
start "" pythonw -m finsight.selftest
