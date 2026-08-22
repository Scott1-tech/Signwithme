@echo off
REM ---------------------------------------------------------------------------
REM  Contract Review Desk - start it so other devices can reach it
REM
REM  Use this when the desk needs to be opened from another computer, a phone,
REM  or over Tailscale. Ordinary daily use does not need it: start.bat keeps
REM  everything on this machine, which is safer.
REM
REM  An account is required. The app refuses to start this way without one,
REM  because these files hold driver Social Security numbers.
REM ---------------------------------------------------------------------------
setlocal
cd /d "%~dp0"

if not exist backend\.venv (
  echo  The app is not set up yet. Run setup.bat first.
  pause
  exit /b 1
)

REM Fail here with an explanation rather than letting the server refuse later.
cd backend
.venv\Scripts\python.exe -m app.cli list-users 2>nul | findstr /c:"No accounts" >nul
if not errorlevel 1 (
  cd ..
  echo.
  echo  This desk has no account yet.
  echo.
  echo  Sharing it without a login would put driver Social Security
  echo  numbers on the network. Create an account first:
  echo.
  echo      cd backend
  echo      .venv\Scripts\python.exe -m app.cli create-user
  echo.
  pause
  exit /b 1
)
cd ..

echo.
echo  Starting the contract desk for other devices...
echo.

start "Contract Desk - engine" /min cmd /c ^
  "cd /d "%~dp0backend" && set HOST=0.0.0.0&& .venv\Scripts\python.exe -m uvicorn app.main:app --host 0.0.0.0 --port 8000"

start "Contract Desk - screens" /min cmd /c ^
  "cd /d "%~dp0frontend" && node_modules\.bin\next.cmd start --hostname 0.0.0.0"

echo  Waiting for it to be ready...
set READY=0
for /l %%i in (1,1,60) do (
  if !READY!==0 (
    timeout /t 1 /nobreak >nul
    curl -s -o nul http://127.0.0.1:3000/api/health && set READY=1
  )
)

echo.
echo  On this computer:  http://localhost:3000
echo.
echo  From other devices, use this computer's address on port 3000.
echo  To find it, run  ipconfig  and look for IPv4 Address.
echo  On Tailscale, run  tailscale ip -4
echo.
echo  Reachable from the network. Everyone needs to sign in, and the
echo  connection is plain HTTP - keep this to a private network such as
echo  Tailscale or your own office, never a public one.
echo.
echo  Two small windows named "Contract Desk" are running it.
echo  Close both when you are finished.
echo.
pause
