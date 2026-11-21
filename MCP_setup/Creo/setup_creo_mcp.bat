@echo off
REM ==========================================================================
REM  One-click setup of the Creo MCP server for Claude Desktop and Claude Code.
REM    Step 1  env "creo-mcp": Python 3.13 + the official MCP Python SDK.
REM            The Claude apps start creo_mcp.py with this Python.
REM    Step 2  finds your Creo and checks that J-Link is installed in it.
REM    Step 3  downloads CREOSON 3.0.2 (open source, MIT) from GitHub, checks
REM            its SHA-256 and writes its setvars.bat for your Creo.
REM            Goes to %LOCALAPPDATA%\creoson - no admin rights needed.
REM    Step 4  asks first, then registers the server "creo" in Claude Code
REM            and/or Claude Desktop.
REM    Step 5  asks first, then restarts Claude Desktop.
REM  Safe to run again: env and CREOSON are reused, entries are updated.
REM  After setup: start Creo (CMTWelcome), then start_creoson.bat, then the
REM  check command printed at the end.
REM  No labels or GOTO on purpose: the file also works with Unix line endings.
REM ==========================================================================
setlocal

set "ENV_NAME=creo-mcp"
set "PY_VERSION=3.13"
set "MCP_SDK_VERSION=2.3.0"
set "PORT=9056"
REM Leave empty to search C:\PTC and Program Files\PTC. Or set the folder by hand, e.g.
REM set "CREO_COMMON=C:\PTC\Creo 9.0.3.0\Common Files"
set "CREO_COMMON="
set "HELPER=%~dp0creo_mcp.py"

if not exist "%HELPER%" (
    echo ERROR: creo_mcp.py must be in the same folder as this file.
    pause
    exit /b 1
)

REM ---- find mamba: PATH first, then the usual miniforge and conda locations ----
set "MAMBA="
where mamba >nul 2>&1 && set "MAMBA=mamba"
if not defined MAMBA if exist "%USERPROFILE%\miniforge3\condabin\mamba.bat" set "MAMBA=%USERPROFILE%\miniforge3\condabin\mamba.bat"
if not defined MAMBA if exist "%USERPROFILE%\mambaforge\condabin\mamba.bat" set "MAMBA=%USERPROFILE%\mambaforge\condabin\mamba.bat"
if not defined MAMBA if exist "%USERPROFILE%\miniforge3\condabin\conda.bat" set "MAMBA=%USERPROFILE%\miniforge3\condabin\conda.bat"
if not defined MAMBA (
    echo ERROR: mamba not found. Run this file from the Miniforge Prompt, or edit MAMBA above.
    pause
    exit /b 1
)
echo Using: %MAMBA%

REM ======================= Step 1: env ======================================
echo.
echo ==== Step 1 of 5: env %ENV_NAME% with the MCP Python SDK %MCP_SDK_VERSION% ====
call "%MAMBA%" run -n %ENV_NAME% python --version >nul 2>&1
if errorlevel 1 (
    echo Creating env %ENV_NAME% with Python %PY_VERSION% ...
    call "%MAMBA%" create -y -n %ENV_NAME% -c conda-forge python=%PY_VERSION% pip
    if errorlevel 1 (
        echo FAILED to create the env - see the messages above.
        pause
        exit /b 1
    )
) else (
    echo Env %ENV_NAME% already exists - reusing it.
)
call "%MAMBA%" run -n %ENV_NAME% python -m pip install --upgrade pip
call "%MAMBA%" run -n %ENV_NAME% python -m pip install "mcp==%MCP_SDK_VERSION%"
if errorlevel 1 (
    echo FAILED to install the MCP SDK - see the messages above.
    pause
    exit /b 1
)
set "PY="
for /f "usebackq delims=" %%P in (`call "%MAMBA%" run -n %ENV_NAME% python -c "import sys; print(sys.executable)"`) do set "PY=%%P"
if not defined PY (
    echo FAILED to find python.exe of env %ENV_NAME%.
    pause
    exit /b 1
)
"%PY%" -c "import mcp.server.mcpserver" >nul 2>&1
if errorlevel 1 (
    echo FAILED: the MCP SDK cannot be imported in env %ENV_NAME%.
    pause
    exit /b 1
)
echo OK - env ready. Python: %PY%

REM ======================= Step 2: Creo and J-Link ==========================
echo.
echo ==== Step 2 of 5: your Creo installs and J-Link ====
if defined CREO_COMMON echo Using the folder set in this file: %CREO_COMMON%
if not defined CREO_COMMON "%PY%" "%HELPER%" find-creo

REM ======================= Step 3: CREOSON ==================================
echo.
echo ==== Step 3 of 5: CREOSON server - download, SHA-256 check, setvars.bat ====
set "CREOSON_STATE=ok"
if defined CREO_COMMON "%PY%" "%HELPER%" install-creoson --port %PORT% --creo-common "%CREO_COMMON%"
if defined CREO_COMMON if errorlevel 1 set "CREOSON_STATE=failed"
if not defined CREO_COMMON "%PY%" "%HELPER%" install-creoson --port %PORT% --interactive
if not defined CREO_COMMON if errorlevel 1 set "CREOSON_STATE=failed"
if "%CREOSON_STATE%"=="failed" (
    echo.
    echo CREOSON setup stopped - see the lines marked [!!] above.
    pause
    exit /b 1
)

REM ======================= Step 4: registration =============================
echo.
echo ==== Step 4 of 5: register the server "creo" in the Claude apps ====
set "TARGETS="
choice /c YN /n /m "Register in Claude Code - VS Code panel and CLI? [Y/N] "
set "ANS_CODE=%errorlevel%"
choice /c YN /n /m "Register in Claude Desktop? [Y/N] "
set "ANS_DESKTOP=%errorlevel%"
if "%ANS_CODE%"=="1" set "TARGETS=code"
if "%ANS_DESKTOP%"=="1" if defined TARGETS set "TARGETS=code,desktop"
if "%ANS_DESKTOP%"=="1" if not defined TARGETS set "TARGETS=desktop"
set "REG_STATE=skip"
if defined TARGETS set "REG_STATE=run"
if "%REG_STATE%"=="run" "%PY%" "%HELPER%" setup --targets "%TARGETS%" --interactive
if "%REG_STATE%"=="run" if errorlevel 1 set "REG_STATE=failed"
if "%REG_STATE%"=="skip" echo Skipped. Nothing was registered.
if "%REG_STATE%"=="failed" (
    echo.
    echo Registration stopped - see the lines marked [!!] above.
    pause
    exit /b 1
)

REM ======================= Step 5: restart Claude Desktop ===================
echo.
echo ==== Step 5 of 5: restart Claude Desktop so it loads the new config ====
set "RESTART=no"
if "%REG_STATE%"=="run" if "%ANS_DESKTOP%"=="1" set "RESTART=ask"
if "%RESTART%"=="no" echo Not needed - Claude Desktop config was not changed.
if "%RESTART%"=="ask" echo Text you have not sent yet, and any task running in Claude Desktop, will be lost.
if "%RESTART%"=="ask" choice /c YN /n /m "Restart Claude Desktop now? [Y/N] "
if "%RESTART%"=="ask" if errorlevel 2 set "RESTART=no"
if "%RESTART%"=="ask" set "RESTART=yes"
REM The restart is done by the PowerShell code at the end of this file.
if "%RESTART%"=="yes" powershell -NoProfile -ExecutionPolicy Bypass -Command "$f = Get-Content -LiteralPath '%~f0' -Raw; $m = '#' + 'RESTART_CLAUDE_PS'; & ([scriptblock]::Create($f.Substring($f.IndexOf($m) + $m.Length)))"
if "%RESTART%"=="yes" if errorlevel 1 echo Restart did not work. Quit Claude Desktop completely, also from the tray, and start it again.

echo.
echo ==== Setup finished ====
echo 1. Start Creo the usual way (CMTWelcome) and wait for the main window.
echo 2. Start CREOSON:   start_creoson.bat  - keep its window open.
echo    If Windows Firewall asks about Java: Cancel. Claude reaches it on this PC only.
echo 3. Test the chain:  "%PY%" "%HELPER%" check
echo 4. New conversation in Claude Code or Claude Desktop, ask: "what is open in Creo?"
pause
exit /b 0

#RESTART_CLAUDE_PS
# ---------------------------------------------------------------------------
# PowerShell part, run by Step 5 above. cmd never reaches these lines.
# It restarts only the Claude Desktop app: processes that run from its install
# folder (Microsoft Store package, or the classic installer). Claude Code and
# other programs named claude.exe are not touched.
# ---------------------------------------------------------------------------
$pkg = Get-AppxPackage -Name 'Claude' -ErrorAction SilentlyContinue | Select-Object -First 1
if ($pkg) { $dir = $pkg.InstallLocation } else { $dir = Join-Path $env:LOCALAPPDATA 'AnthropicClaude' }
if (-not $dir -or -not (Test-Path -LiteralPath $dir)) {
    Write-Host 'Claude Desktop installation not found.'
    exit 1
}
$prefix = $dir.TrimEnd('\', '/') + [IO.Path]::DirectorySeparatorChar

function Get-ClaudeDesktopProcess {
    Get-Process | Where-Object {
        try { $_.Path -and $_.Path.StartsWith($prefix, [StringComparison]::OrdinalIgnoreCase) } catch { $false }
    }
}

$procs = @(Get-ClaudeDesktopProcess)
if ($procs.Count -gt 0) {
    Write-Host "Closing Claude Desktop ($($procs.Count) processes) ..."
    $procs | Stop-Process -Force -ErrorAction SilentlyContinue
    $procs | Wait-Process -Timeout 20 -ErrorAction SilentlyContinue
    if (@(Get-ClaudeDesktopProcess).Count -gt 0) {
        Write-Host 'Could not close Claude Desktop.'
        exit 1
    }
    Start-Sleep -Seconds 2
} else {
    Write-Host 'Claude Desktop is not running.'
}

Write-Host 'Starting Claude Desktop ...'
if ($pkg) {
    # Store app: start it through its app ID, e.g. Claude_pzs8sxrjxfjjc!Claude
    $appId = (Get-AppxPackageManifest -Package $pkg.PackageFullName).Package.Applications.Application |
             Select-Object -First 1 -ExpandProperty Id
    Start-Process explorer.exe "shell:AppsFolder\$($pkg.PackageFamilyName)!$appId"
} else {
    Start-Process (Join-Path $dir 'claude.exe')
}

for ($i = 0; $i -lt 30; $i++) {
    Start-Sleep -Seconds 1
    if (@(Get-ClaudeDesktopProcess).Count -gt 0) {
        Write-Host 'Claude Desktop is running again.'
        exit 0
    }
}
Write-Host 'Claude Desktop did not start within 30 s. Please start it by hand.'
exit 1
