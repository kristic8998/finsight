@echo off
rem ============================================================================
rem  FinSight - build the standalone Windows executable (one-folder build).
rem  Run this on a Windows 10/11 machine that has Python 3.10+ installed.
rem
rem  Output: dist\FinSight\FinSight.exe  (plus its _internal\ support folder)
rem  This is the input for BOTH the portable zip (build_portable.bat) and the
rem  Inno Setup installer (installer\finsight.iss).
rem ============================================================================
setlocal
cd /d "%~dp0.."

echo(
echo === FinSight build ===
echo(

rem --- 1. Ensure a virtual environment exists -------------------------------
if not exist ".venv\Scripts\activate.bat" (
    echo Creating virtual environment .venv ...
    python -m venv .venv || goto :error
)
call .venv\Scripts\activate.bat || goto :error

rem --- 2. Install the app plus build tooling --------------------------------
echo Installing FinSight and PyInstaller (first run downloads a lot) ...
python -m pip install --upgrade pip >nul
pip install -e ".[dev]" || goto :error

rem --- 3. Sanity-check the code before freezing it --------------------------
echo Running the self-test before packaging ...
finsight --selftest || goto :error

rem --- 4. Freeze to a one-folder build --------------------------------------
echo Cleaning previous build ...
if exist build rmdir /s /q build
if exist dist rmdir /s /q dist
echo Building the executable with PyInstaller ...
pyinstaller FinSight.spec --noconfirm --clean || goto :error

echo(
echo ============================================================================
echo  BUILD COMPLETE
echo    dist\FinSight\FinSight.exe
echo(
echo  Next, produce a distributable:
echo    scripts\build_portable.bat     -^> a portable .zip (no install needed)
echo    installer\finsight.iss         -^> compile in Inno Setup for Setup.exe
echo ============================================================================
pause
exit /b 0

:error
echo(
echo BUILD FAILED - see the message above.
echo Requirements: Python 3.10+ from python.org, on the PATH.
pause
exit /b 1
