@echo off
rem Promilia Guide Tracker (screen-based) - portable exe build. No admin rights needed.
cd /d "%~dp0"
python -m PyInstaller --noconfirm --clean --onefile --windowed ^
  --name PromiliaGuideTracker --icon assets\tracker.ico ^
  --add-data "assets\tracker.ico;assets" ^
  --exclude-module matplotlib --exclude-module pandas ^
  tracker2.py
echo.
echo Done: dist\PromiliaGuideTracker.exe
pause
