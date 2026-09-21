@echo off
rem Double-click to launch. Pass extra flags through, e.g. run.bat --fullscreen
cd /d "%~dp0"
python viz.py %*
if errorlevel 1 pause
