@echo off
REM One-time setup (needs internet once): Python packages + frontend build.
cd /d "%~dp0"

echo === Installing Python packages ===
python -m pip install -r requirements.txt || goto :fail

echo === Building the frontend (needs Node.js) ===
where npm >nul 2>nul
if errorlevel 1 (
  echo Node.js/npm not found. A pre-built frontend is used if frontend\dist exists.
  if not exist frontend\dist goto :fail
) else (
  pushd frontend
  call npm install --no-audit --no-fund || (popd & goto :fail)
  call npm run build || (popd & goto :fail)
  popd
)
echo.
echo Setup finished. Start the simulation with start.bat
exit /b 0

:fail
echo Setup failed - see the messages above.
exit /b 1
