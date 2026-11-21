@echo off
REM ==========================================================================
REM  One-click setup of the Ansys AEDT MCP server for Claude Desktop and Claude Code.
REM    Step 1  create or reuse the mamba env "aedt-mcp" with Python 3.13 and
REM            install the server package ansys-aedt-mcp
REM    Step 2  asks first, then registers the server in Claude Code (user scope),
REM            so the VS Code panel and the CLI see it in all your projects
REM    Step 3  asks first, then runs configure_claude.py from this folder, which
REM            adds the server to the Claude Desktop config and makes a backup
REM    Step 4  asks first, then restarts Claude Desktop so it loads the new config
REM  Safe to run again: the env is reused and the config entries are updated.
REM  No labels or GOTO on purpose: the file then also works with Unix line endings.
REM ==========================================================================
setlocal

set "ENV_NAME=aedt-mcp"
set "PY_VERSION=3.13"
set "SERVER_VERSION=0.3.2"
set "CONFIGURE=%~dp0configure_claude.py"

if not exist "%CONFIGURE%" (
    echo ERROR: configure_claude.py must be in the same folder as this file.
    pause
    exit /b 1
)

echo ==== Step 1 of 4: mamba env %ENV_NAME% with ansys-aedt-mcp %SERVER_VERSION% ====

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

REM ---- create the env if it does not exist yet ----
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

REM ---- install the MCP server, which also installs ansys-aedt-core ----
echo Installing ansys-aedt-mcp==%SERVER_VERSION% ...
call "%MAMBA%" run -n %ENV_NAME% python -m pip install --upgrade pip
call "%MAMBA%" run -n %ENV_NAME% python -m pip install "ansys-aedt-mcp==%SERVER_VERSION%"
if errorlevel 1 (
    echo FAILED to install ansys-aedt-mcp - see the messages above.
    pause
    exit /b 1
)

REM ---- find python.exe of the env, used directly below ----
set "ENV_PY="
for /f "usebackq delims=" %%P in (`call "%MAMBA%" run -n %ENV_NAME% python -c "import sys; print(sys.executable)"`) do set "ENV_PY=%%P"
if not defined ENV_PY (
    echo FAILED to find python.exe of env %ENV_NAME%.
    pause
    exit /b 1
)
"%ENV_PY%" -c "import ansys.aedt.mcp" >nul 2>&1
if errorlevel 1 (
    echo FAILED: the server package cannot be imported in env %ENV_NAME%.
    pause
    exit /b 1
)
echo OK - server installed. Env Python: %ENV_PY%

REM ---- Step 2: register the server in Claude Code, asks first ----
REM Claude Code (VS Code panel and CLI) does not read the Claude Desktop config, so the
REM server is added to its user config with "claude mcp add": then it works in every project.
echo.
echo ==== Step 2 of 4: register the "aedt" server in Claude Code (VS Code panel and CLI) ====

REM ---- find the Claude Code CLI: standalone install, npm install, then the newest copy
REM      bundled with the VS Code extension. PATH is not searched on purpose: an old
REM      Claude Desktop can put its own claude.exe there, which opens the app instead.
set "CLAUDE_CLI="
if exist "%USERPROFILE%\.local\bin\claude.exe" set "CLAUDE_CLI=%USERPROFILE%\.local\bin\claude.exe"
if not defined CLAUDE_CLI if exist "%APPDATA%\npm\claude.cmd" set "CLAUDE_CLI=%APPDATA%\npm\claude.cmd"
if not defined CLAUDE_CLI for /f "delims=" %%D in ('dir /b /ad /o:d "%USERPROFILE%\.vscode\extensions\anthropic.claude-code-*" 2^>nul') do if exist "%USERPROFILE%\.vscode\extensions\%%D\resources\native-binary\claude.exe" set "CLAUDE_CLI=%USERPROFILE%\.vscode\extensions\%%D\resources\native-binary\claude.exe"

REM ---- find AEDT like configure_claude.py: the newest ANSYSEM_ROOT### variable,
REM      else the newest "C:\Program Files\ANSYS Inc\v###\AnsysEM" folder ----
set "AEDT_VAR="
set "AEDT_ROOT="
set "AEDT_VER="
for /f "tokens=1,* delims==" %%A in ('set ANSYSEM_ROOT 2^>nul') do if exist "%%B\" (
    set "AEDT_VAR=%%A"
    set "AEDT_ROOT=%%B"
)
if not defined AEDT_ROOT for /d %%D in ("%ProgramFiles%\ANSYS Inc\v*") do if exist "%%D\AnsysEM\" (
    set "AEDT_ROOT=%%D\AnsysEM"
    set "AEDT_VER=%%~nxD"
)
if defined AEDT_VER set "AEDT_VAR=ANSYSEM_ROOT%AEDT_VER:~1%"

REM ---- ask, then remove an old "aedt" entry and add the current one ----
set "CC_STATE=skip"
if not defined CLAUDE_CLI echo Claude Code not found: no standalone CLI and no VS Code extension. Step skipped.
if defined CLAUDE_CLI echo Using: %CLAUDE_CLI%
if defined CLAUDE_CLI if defined AEDT_ROOT echo AEDT : %AEDT_ROOT%  [%AEDT_VAR%]
if defined CLAUDE_CLI if not defined AEDT_ROOT echo WARNING: AEDT installation not found; the server will try to find it itself.
if defined CLAUDE_CLI choice /c YN /n /m "Register the server in Claude Code now? [Y/N] "
if defined CLAUDE_CLI if not errorlevel 2 set "CC_STATE=run"
if "%CC_STATE%"=="run" call "%CLAUDE_CLI%" mcp remove aedt --scope user >nul 2>&1
if "%CC_STATE%"=="run" if defined AEDT_ROOT call "%CLAUDE_CLI%" mcp add --env "%AEDT_VAR%=%AEDT_ROOT%" --transport stdio --scope user aedt -- "%ENV_PY%" -m ansys.aedt.mcp
if "%CC_STATE%"=="run" if not defined AEDT_ROOT call "%CLAUDE_CLI%" mcp add --transport stdio --scope user aedt -- "%ENV_PY%" -m ansys.aedt.mcp
if "%CC_STATE%"=="run" if errorlevel 1 set "CC_STATE=failed"
if "%CC_STATE%"=="run" call "%CLAUDE_CLI%" mcp get aedt
if "%CC_STATE%"=="run" echo OK - in VS Code start a new Claude Code conversation; /mcp lists "aedt".
if "%CC_STATE%"=="failed" echo FAILED to register the server in Claude Code - see the message above.
if "%CC_STATE%"=="skip" if defined CLAUDE_CLI echo Skipped. Claude Code was not changed.

REM ---- Step 3: add the server to the Claude Desktop config, asks first ----
echo.
echo ==== Step 3 of 4: add the "aedt" server to the Claude Desktop config ====
echo configure_claude.py finds the config file, makes a backup, then adds the entry.
choice /c YN /n /m "Run configure_claude.py now? [Y/N] "
set "ANSWER=%errorlevel%"
if not "%ANSWER%"=="1" (
    echo Skipped. The Claude Desktop config was not changed.
    pause
    exit /b 0
)
"%ENV_PY%" "%CONFIGURE%" --interactive
if errorlevel 1 (
    echo.
    echo configure_claude.py stopped - see the message above. Claude Desktop was not restarted.
    pause
    exit /b 1
)

REM ---- Step 4: restart Claude Desktop, asks first ----
echo.
echo ==== Step 4 of 4: restart Claude Desktop so it loads the new config ====
echo Text you have not sent yet, and any task running in Claude Desktop, will be lost.
choice /c YN /n /m "Restart Claude Desktop now? [Y/N] "
set "ANSWER=%errorlevel%"
if not "%ANSWER%"=="1" (
    echo Not restarted. Quit Claude Desktop completely, also from the tray, and start it again.
    pause
    exit /b 0
)
REM The restart is done by the PowerShell code at the end of this file.
powershell -NoProfile -ExecutionPolicy Bypass -Command "$f = Get-Content -LiteralPath '%~f0' -Raw; $m = '#' + 'RESTART_CLAUDE_PS'; & ([scriptblock]::Create($f.Substring($f.IndexOf($m) + $m.Length)))"
if errorlevel 1 (
    echo Restart did not work. Quit Claude Desktop completely, also from the tray, and start it again.
    pause
    exit /b 1
)

echo.
echo ==== Setup finished ====
echo In Claude Desktop, Settings - Developer should show the "aedt" server as running.
pause
exit /b 0

#RESTART_CLAUDE_PS
# ---------------------------------------------------------------------------
# PowerShell part, run by Step 4 above. cmd never reaches these lines.
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
