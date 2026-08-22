@echo off
REM ---------------------------------------------------------------------------
REM  Contract Review Desk - first-time setup (Windows)
REM
REM  Double-click this once. It installs everything the app needs and creates
REM  a private key for hashing Social Security numbers. Running it again is
REM  safe: it will not touch the key it already made.
REM ---------------------------------------------------------------------------
setlocal enabledelayedexpansion
cd /d "%~dp0"

echo.
echo  == Contract Review Desk - setup ==
echo.

REM --- 1. Check what is installed --------------------------------------------
set "PY="
where py >nul 2>&1 && set "PY=py -3"
if not defined PY (
  where python >nul 2>&1 && set "PY=python"
)
if not defined PY (
  echo  Python is not installed.
  echo  Get it from https://www.python.org/downloads/
  echo  On the first screen, tick "Add Python to PATH".
  echo.
  pause
  exit /b 1
)

where node >nul 2>&1
if errorlevel 1 (
  echo  Node.js is not installed.
  echo  Get the LTS version from https://nodejs.org
  echo.
  pause
  exit /b 1
)

echo  Python and Node.js found.

REM --- 2. Backend --------------------------------------------------------------
echo.
echo  Installing the backend. This takes a minute.
cd backend
if not exist .venv (
  %PY% -m venv .venv
  if errorlevel 1 goto :failed
)
call .venv\Scripts\python.exe -m pip install --quiet --upgrade pip
call .venv\Scripts\python.exe -m pip install --quiet -r requirements.txt
if errorlevel 1 goto :failed
echo  Done.

REM --- 3. The private key ------------------------------------------------------
REM Never regenerate: changing it makes every existing record unmatchable.
echo.
if exist .env (
  echo  backend\.env already exists, so your key is untouched.
) else (
  echo  Creating your private key.
  copy /y .env.example .env >nul
  call .venv\Scripts\python.exe -c "import secrets,pathlib; p=pathlib.Path('.env'); p.write_text(p.read_text().replace('SSN_SALT=change-me-before-first-real-contract','SSN_SALT='+secrets.token_hex(32)))"
  echo  Written to backend\.env - back this file up. Without it, stored
  echo  records can no longer be matched.
)
cd ..

REM --- 4. Frontend --------------------------------------------------------------
echo.
echo  Installing the screens. The first time takes a few minutes.
cd frontend
call npm install --no-audit --no-fund --silent
if errorlevel 1 goto :failed
call npm run build
if errorlevel 1 goto :failed
cd ..

echo.
echo  == Setup finished ==
echo.
echo  Start the app by double-clicking start.bat
echo.
pause
exit /b 0

:failed
echo.
echo  Setup failed. Read the message above, fix it, and run this again.
echo.
pause
exit /b 1
