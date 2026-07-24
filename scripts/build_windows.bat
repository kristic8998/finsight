@echo off
rem Build the standalone one-folder executable (run on Windows).
cd /d "%~dp0.."
call .venv\Scripts\activate.bat
pip install pyinstaller >nul
pyinstaller FinSight.spec --noconfirm || exit /b 1
echo Build complete: dist\FinSight\FinSight.exe
pause
