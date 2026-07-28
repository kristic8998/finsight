@echo off
rem ============================================================================
rem  FinSight - build the PORTABLE distribution (a self-contained .zip).
rem
rem  The portable build needs no installer and no admin rights: the user
rem  unzips it anywhere (USB stick, Desktop, network share) and double-clicks
rem  FinSight.exe. Python is bundled inside, so the target PC needs no Python.
rem
rem  Prereq: run scripts\build_windows.bat first (creates dist\FinSight).
rem  Output: dist\FinSight-1.6.0-portable.zip
rem ============================================================================
setlocal
cd /d "%~dp0.."
set "VERSION=1.6.0"
set "PKG=FinSight-%VERSION%-portable"

if not exist "dist\FinSight\FinSight.exe" (
    echo dist\FinSight\FinSight.exe not found.
    echo Run scripts\build_windows.bat first, then re-run this script.
    pause
    exit /b 1
)

echo Staging portable folder ...
if exist "dist\%PKG%" rmdir /s /q "dist\%PKG%"
xcopy "dist\FinSight" "dist\%PKG%\FinSight\" /e /i /q || goto :error

rem A friendly launcher at the top level of the zip.
> "dist\%PKG%\Start FinSight.bat" echo @echo off
>>"dist\%PKG%\Start FinSight.bat" echo start "" "%%~dp0FinSight\FinSight.exe"

rem A short readme so a non-technical recipient knows what to do.
> "dist\%PKG%\READ ME FIRST.txt" echo FinSight %VERSION% - Portable edition
>>"dist\%PKG%\READ ME FIRST.txt" echo ---------------------------------------
>>"dist\%PKG%\READ ME FIRST.txt" echo(
>>"dist\%PKG%\READ ME FIRST.txt" echo No installation required. No Python required.
>>"dist\%PKG%\READ ME FIRST.txt" echo(
>>"dist\%PKG%\READ ME FIRST.txt" echo 1. Unzip this whole folder anywhere (Desktop is fine).
>>"dist\%PKG%\READ ME FIRST.txt" echo 2. Double-click "Start FinSight.bat" (or FinSight\FinSight.exe).
>>"dist\%PKG%\READ ME FIRST.txt" echo 3. Your data is stored under %%LOCALAPPDATA%%\FinSight.
>>"dist\%PKG%\READ ME FIRST.txt" echo(
>>"dist\%PKG%\READ ME FIRST.txt" echo If Windows SmartScreen warns you: More info -^> Run anyway.
>>"dist\%PKG%\READ ME FIRST.txt" echo Full guide: docs\USER_GUIDE.md at github.com/kristic8998/finsight

echo Compressing to dist\%PKG%.zip ...
if exist "dist\%PKG%.zip" del /q "dist\%PKG%.zip"
powershell -NoProfile -Command ^
  "Compress-Archive -Path 'dist\%PKG%\*' -DestinationPath 'dist\%PKG%.zip' -Force" || goto :error

echo(
echo ============================================================================
echo  PORTABLE BUILD COMPLETE
echo    dist\%PKG%.zip
echo  Share that single .zip. The recipient unzips and runs it - nothing to install.
echo ============================================================================
pause
exit /b 0

:error
echo(
echo Portable packaging FAILED - see the message above.
pause
exit /b 1
