@echo off
rem Promilia Guide Tracker (screen-based) - portable exe build. No admin rights needed.
cd /d "%~dp0"
rem Shared files (gui.py, diag.py, updater.py) must match promilia-tracker-common (2026-11-27)
if exist "..\promilia-tracker-sync.py" (python "..\promilia-tracker-sync.py" --check || (echo Shared files differ - run promilia-tracker-sync.py first. & pause & exit /b 1))
python -m PyInstaller --noconfirm --clean --onefile --windowed ^
  --name PromiliaGuideTracker --icon assets\tracker.ico ^
  --add-data "assets\tracker.ico;assets" ^
  --exclude-module matplotlib --exclude-module pandas ^
  tracker2.py
echo.
echo Done: dist\PromiliaGuideTracker.exe
pause
