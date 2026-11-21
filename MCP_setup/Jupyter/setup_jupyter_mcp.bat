@echo off
REM ==========================================================================
REM  One-click setup of Jupyter MCP Server for Claude Desktop and Claude Code.
REM    Step 1  bridge env "jupyter-mcp": Python 3.13 + jupyter-mcp-server
REM            The Claude apps start this one. It only talks to JupyterLab.
REM    Step 2  JupyterLab env "jupyter-lab": JupyterLab with real-time
REM            collaboration, so edits by Claude appear live in your tab.
REM    Step 3  asks first, then offers your existing envs as kernels.
REM            Kernels are where code really runs.
REM    Step 4  asks first, then jupyter_mcp.py creates the token file and
REM            registers the server in Claude Code and/or Claude Desktop.
REM    Step 5  asks first, then restarts Claude Desktop.
REM  Safe to run again: envs are reused, the token is kept, entries updated.
REM  Versions below were tested together on 2026-11-13.
REM  After setup: start_jupyterlab.bat, then the check command printed at the end.
REM  No labels or GOTO on purpose: the file also works with Unix line endings.
REM ==========================================================================
setlocal

set "BRIDGE_ENV=jupyter-mcp"
set "LAB_ENV=jupyter-lab"
set "PY_VERSION=3.13"
set "MCP_SERVER_VERSION=2.2.5"
set "PORT=8888"
REM Envs to offer as kernels in JupyterLab, separated by spaces. Each needs ipykernel.
set "KERNEL_ENVS=metal"
set "HELPER=%~dp0jupyter_mcp.py"

if not exist "%HELPER%" (
    echo ERROR: jupyter_mcp.py must be in the same folder as this file.
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

REM ======================= Step 1: bridge env ===============================
echo.
echo ==== Step 1 of 5: bridge env %BRIDGE_ENV% with jupyter-mcp-server %MCP_SERVER_VERSION% ====
call "%MAMBA%" run -n %BRIDGE_ENV% python --version >nul 2>&1
if errorlevel 1 (
    echo Creating env %BRIDGE_ENV% with Python %PY_VERSION% ...
    call "%MAMBA%" create -y -n %BRIDGE_ENV% -c conda-forge python=%PY_VERSION% pip
    if errorlevel 1 (
        echo FAILED to create the env - see the messages above.
        pause
        exit /b 1
    )
) else (
    echo Env %BRIDGE_ENV% already exists - reusing it.
)
call "%MAMBA%" run -n %BRIDGE_ENV% python -m pip install --upgrade pip
call "%MAMBA%" run -n %BRIDGE_ENV% python -m pip install "jupyter-mcp-server==%MCP_SERVER_VERSION%"
if errorlevel 1 (
    echo FAILED to install jupyter-mcp-server - see the messages above.
    pause
    exit /b 1
)
set "BRIDGE_PY="
for /f "usebackq delims=" %%P in (`call "%MAMBA%" run -n %BRIDGE_ENV% python -c "import sys; print(sys.executable)"`) do set "BRIDGE_PY=%%P"
if not defined BRIDGE_PY (
    echo FAILED to find python.exe of env %BRIDGE_ENV%.
    pause
    exit /b 1
)
"%BRIDGE_PY%" -c "import jupyter_mcp_server" >nul 2>&1
if errorlevel 1 (
    echo FAILED: jupyter_mcp_server cannot be imported in env %BRIDGE_ENV%.
    pause
    exit /b 1
)
echo OK - bridge installed. Python: %BRIDGE_PY%

REM ======================= Step 2: JupyterLab env ===========================
echo.
echo ==== Step 2 of 5: JupyterLab env %LAB_ENV% with real-time collaboration ====
call "%MAMBA%" run -n %LAB_ENV% python --version >nul 2>&1
if errorlevel 1 (
    echo Creating env %LAB_ENV% with Python %PY_VERSION% ...
    call "%MAMBA%" create -y -n %LAB_ENV% -c conda-forge python=%PY_VERSION% pip
    if errorlevel 1 (
        echo FAILED to create the env - see the messages above.
        pause
        exit /b 1
    )
) else (
    echo Env %LAB_ENV% already exists - reusing it.
)
call "%MAMBA%" run -n %LAB_ENV% python -m pip install --upgrade pip
call "%MAMBA%" run -n %LAB_ENV% python -m pip install "jupyterlab==4.6.6" "jupyter-collaboration==5.0.4" "jupyter-mcp-tools==0.1.8" "ipykernel==7.4.0"
if errorlevel 1 (
    echo FAILED to install JupyterLab - see the messages above.
    pause
    exit /b 1
)
call "%MAMBA%" run -n %LAB_ENV% python -c "import jupyterlab, jupyter_server_ydoc" >nul 2>&1
if errorlevel 1 (
    echo FAILED: JupyterLab or the collaboration extension cannot be imported in env %LAB_ENV%.
    pause
    exit /b 1
)
echo OK - JupyterLab with real-time collaboration installed.

REM ======================= Step 3: kernels ==================================
echo.
echo ==== Step 3 of 5: offer existing envs as kernels in JupyterLab ====
echo Envs: %KERNEL_ENVS%
echo This writes a small kernel.json per env. The envs themselves are not changed.
choice /c YN /n /m "Register these envs as Jupyter kernels? [Y/N] "
set "ANSWER=%errorlevel%"
if "%ANSWER%"=="1" for %%E in (%KERNEL_ENVS%) do (
    call "%MAMBA%" run -n %%E python -m ipykernel install --user --name %%E --display-name "Python - %%E"
    if errorlevel 1 echo   %%E was not registered. Does the env exist, and does it have ipykernel?
)
if not "%ANSWER%"=="1" echo Skipped.

REM ======================= Step 4: token and registration ===================
echo.
echo ==== Step 4 of 5: token file and registration in the Claude apps ====
echo jupyter_mcp.py creates %LOCALAPPDATA%\jupyter-mcp\token.txt once and keeps it.
echo The Claude configs get only the path of that file, never the token itself.
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
if "%REG_STATE%"=="run" "%BRIDGE_PY%" "%HELPER%" setup --port %PORT% --targets "%TARGETS%" --interactive
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
echo 1. Start JupyterLab:  start_jupyterlab.bat  - keep its window open
echo 2. Test the chain:    "%BRIDGE_PY%" "%HELPER%" check
echo 3. Start a new conversation in Claude Code or Claude Desktop and ask:
echo    "list my Jupyter kernels"
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