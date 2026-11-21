@echo off
REM ==========================================================================
REM  Starts JupyterLab for Claude's Jupyter MCP server.
REM  Keep this window open while Claude works in notebooks. Ctrl+C stops it.
REM  - Listens on 127.0.0.1 only, so other computers cannot connect.
REM  - The token comes from the token file that setup_jupyter_mcp.bat made.
REM    The Claude bridge reads the same file, so the two always match.
REM    The token is never shown on screen or written on a command line.
REM  - The browser tab that opens is logged in already. In another browser,
REM    paste the content of token.txt into the login page once.
REM  - PORT must be the port used at registration (default 8888).
REM    port_retries=0: if the port is busy, JupyterLab stops with an error
REM    instead of moving to 8889 quietly, where Claude would not find it.
REM  - NOTEBOOK_ROOT is the top folder that JupyterLab and Claude's file
REM    tools see. Code running in a kernel is NOT limited to this folder.
REM  Remote server instead of this PC: start JupyterLab there the same way
REM  (127.0.0.1, its own token file), put a copy of that token in
REM  %LOCALAPPDATA%\jupyter-mcp\token-server.txt here, open a tunnel
REM      ssh -N -L 8889:127.0.0.1:8888 user@server
REM  and register it once with
REM      jupyter_mcp.py setup --name jupyter-server --port 8889 --token-file "%LOCALAPPDATA%\jupyter-mcp\token-server.txt"
REM  No labels or GOTO on purpose: the file also works with Unix line endings.
REM ==========================================================================
setlocal

set "LAB_ENV=jupyter-lab"
set "PORT=8888"
set "NOTEBOOK_ROOT=%USERPROFILE%\Documents\AndreiK_backup\Projects"
set "TOKEN_FILE=%LOCALAPPDATA%\jupyter-mcp\token.txt"

if not exist "%TOKEN_FILE%" (
    echo ERROR: token file not found: %TOKEN_FILE%
    echo Run setup_jupyter_mcp.bat first.
    pause
    exit /b 1
)
if not exist "%NOTEBOOK_ROOT%\" (
    echo ERROR: notebook folder not found: %NOTEBOOK_ROOT%
    echo Edit NOTEBOOK_ROOT at the top of this file.
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

REM ---- python.exe of the JupyterLab env, started directly: live log, clean Ctrl+C ----
set "LAB_PY="
for /f "usebackq delims=" %%P in (`call "%MAMBA%" run -n %LAB_ENV% python -c "import sys; print(sys.executable)"`) do set "LAB_PY=%%P"
if not defined LAB_PY (
    echo ERROR: env %LAB_ENV% not found. Run setup_jupyter_mcp.bat first.
    pause
    exit /b 1
)

REM ---- token: from the file into this window's environment only ----
set "JUPYTER_TOKEN="
set /p JUPYTER_TOKEN=<"%TOKEN_FILE%"
if not defined JUPYTER_TOKEN (
    echo ERROR: the token file is empty: %TOKEN_FILE%
    echo Run setup_jupyter_mcp.bat again - it writes a new token.
    pause
    exit /b 1
)

echo JupyterLab env:  %LAB_PY%
echo Notebook folder: %NOTEBOOK_ROOT%
echo Address:         http://127.0.0.1:%PORT%/lab
echo The log shows token=... because the token comes from your token file.
echo.
"%LAB_PY%" -m jupyterlab --ServerApp.ip=127.0.0.1 --ServerApp.port=%PORT% --ServerApp.port_retries=0 --ServerApp.root_dir="%NOTEBOOK_ROOT%"
echo.
echo JupyterLab has stopped.
pause
exit /b 0