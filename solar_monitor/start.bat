@echo off
REM Starts the simulation backend + dashboard. No internet needed.
cd /d "%~dp0"
echo Open http://localhost:8000 in your browser.
start "" http://localhost:8000
python run.py
