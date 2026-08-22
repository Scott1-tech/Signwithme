@echo off
REM ---------------------------------------------------------------------------
REM  Contract Review Desk - back up everything that matters
REM
REM    backup.bat E:\contract-desk-backup
REM
REM  Copies the contracts, the record of who approved what, and the private
REM  key. Executed contracts have to be retained under 49 CFR 391.51, and one
REM  laptop is not a backup.
REM ---------------------------------------------------------------------------
setlocal
cd /d "%~dp0"

if "%~1"=="" (
  echo  Usage: backup.bat E:\path\to\backup\folder
  echo  Ideally an encrypted external drive.
  pause
  exit /b 1
)

for /f "tokens=2 delims==" %%d in ('wmic os get localdatetime /value') do set LDT=%%d
set STAMP=%LDT:~0,4%-%LDT:~4,2%-%LDT:~6,2%
set TARGET=%~1\%STAMP%

echo.
echo  Backing up to %TARGET%
if not exist "%TARGET%" mkdir "%TARGET%"

if exist backend\storage          xcopy /e /i /y /q backend\storage "%TARGET%\storage" >nul && echo   copied  storage
if exist backend\contract_desk.db copy /y backend\contract_desk.db "%TARGET%\" >nul       && echo   copied  contract_desk.db
if exist backend\.env             copy /y backend\.env "%TARGET%\" >nul                   && echo   copied  .env

echo.
echo  Done. Keep this drive encrypted and somewhere else.
echo.
pause
