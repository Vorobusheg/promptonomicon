@echo off
REM ==========================================================================
REM  Starts the CREOSON server that setup_creo_mcp.bat installed.
REM  Order: 1. Creo (CMTWelcome)  2. this file  3. Claude.
REM  Keep this window open while Claude works with Creo; close it to stop.
REM  CREOSON connects to the Creo session that is already open. It does not
REM  start Creo, so your CMTWelcome start stays exactly as it is.
REM  No labels or GOTO on purpose: the file also works with Unix line endings.
REM ==========================================================================
setlocal
set "CREOSON_DIR=%LOCALAPPDATA%\creoson\CreosonServer-3.0.2"
set "PORT=9056"

if not exist "%CREOSON_DIR%\setvars.bat" (
    echo ERROR: CREOSON is not set up in %CREOSON_DIR%
    echo Run setup_creo_mcp.bat first.
    pause
    exit /b 1
)

netstat -ano | findstr /r /c:":%PORT% .*LISTENING" >nul 2>&1
if not errorlevel 1 (
    echo Something already listens on port %PORT% - CREOSON is probably running in another window.
    pause
    exit /b 0
)

tasklist /fi "imagename eq xtop.exe" | findstr /i "xtop.exe" >nul 2>&1
if errorlevel 1 echo NOTE: Creo does not run yet. Start it now through CMTWelcome - CREOSON will find it later.

title CREOSON server - port %PORT% - keep open
echo Starting CREOSON on port %PORT%. Close this window to stop it.
echo If Windows Firewall asks about Java: Cancel. Claude reaches it on this PC only.
echo.
cd /d "%CREOSON_DIR%"
call creoson_run.bat
