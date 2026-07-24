@echo off
rem FinSight one-time setup: virtual env + dependencies + selftest.
cd /d "%~dp0.."
echo Creating virtual environment...
python -m venv .venv || goto :error
call .venv\Scripts\activate.bat
echo Installing FinSight (this takes a few minutes the first time)...
pip install --upgrade pip >nul
pip install -e . || goto :error
echo.
echo Running the self-test...
finsight --selftest || goto :error
echo.
echo Setup complete. Start FinSight any time with scripts\run_finsight.bat
pause
exit /b 0
:error
echo.
echo Setup failed - see the message above. Python 3.10+ from python.org is required.
pause
exit /b 1
