@echo off
cd /d "%~dp0"
".venv\Scripts\python.exe" sabah_raporu.py %*
if errorlevel 1 pause
