@echo off
REM ---------------------------------------------------------------------------
REM  Contract Review Desk - start the app (Windows)
REM
REM  Double-click this. Two small windows open and stay open while the app
REM  runs; close them to stop it.
REM ---------------------------------------------------------------------------
cd /d "%~dp0"

if not exist backend\.venv (
  echo  The app is not set up yet. Run setup.bat first.
  pause
  exit /b 1
)
if not exist frontend\.next (
  echo  The app is not set up yet. Run setup.bat first.
  pause
  exit /b 1
)

echo.
echo  Starting the contract desk...
echo.

REM 127.0.0.1 only: driver Social Security numbers are in these files and
REM must not be reachable from the network.
start "Contract Desk - engine" /min cmd /c ^
  "cd /d "%~dp0backend" && .venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8000"

start "Contract Desk - screens" /min cmd /c ^
  "cd /d "%~dp0frontend" && node_modules\.bin\next.cmd start"

echo  Waiting for it to be ready...
set READY=0
for /l %%i in (1,1,60) do (
  if !READY!==0 (
    timeout /t 1 /nobreak >nul
    curl -s -o nul http://127.0.0.1:3000/api/health && set READY=1
  )
)

start "" http://localhost:3000

echo.
echo  The contract desk is open in your browser at http://localhost:3000
echo.
echo  Two small windows named "Contract Desk" are running it.
echo  Close both when you are finished for the day.
echo.
pause
