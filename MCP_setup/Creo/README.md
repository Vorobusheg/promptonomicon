# Creo MCP: Claude works with PTC Creo Parametric

Claude controls the Creo session that is open on this PC: it can read and change
parameters and dimensions, regenerate, list features, build assemblies, make drawings,
export STEP/PDF/images, and look at the model.

```
 Claude Code / Claude Desktop
        |  stdio (MCP)
        v
 creo_mcp.py serve          env "creo-mcp", official MCP Python SDK 2.3.0
        |  HTTP + JSON, 127.0.0.1:9056
        v
 CREOSON server             start_creoson.bat, open source (MIT), Simplified Logic
        |  J-Link (async)
        v
 Creo Parametric 9          started by you, through CMTWelcome
```

All parts are open source or from PTC/Anthropic:

| Part | Author | Licence | Why trusted |
|------|--------|---------|-------------|
| CREOSON 3.0.2 | Simplified Logic, Inc. (github.com/SimplifiedLogic/creoson) | MIT | open code, in use since 2017, the zip is checked by SHA-256 |
| `mcp` 2.3.0 | Model Context Protocol project (Anthropic) | MIT | the official Python SDK |
| J-Link | PTC | part of Creo | free Creo option |
| `creo_mcp.py` | written for this folder | - | about 1000 lines, standard library + `mcp` only |

## Files

| File | What it does |
|------|--------------|
| `setup_creo_mcp.bat` | the installer. Double-click it once. Safe to run again. |
| `creo_mcp.py` | the helper: finds Creo, installs CREOSON, registers and runs the MCP server, tests the chain. Must stay next to the .bat file. |
| `start_creoson.bat` | starts CREOSON. Run it every time you want Claude to work with Creo. |

Created outside this folder (private to your Windows user, no admin rights needed):

| Path | Content |
|------|---------|
| `%LOCALAPPDATA%\creoson\CreosonServer-3.0.2\` | CREOSON with its own Java 25, and `setvars.bat` (your Creo path and the port) |
| `%LOCALAPPDATA%\creoson\downloads\` | the downloaded zip |
| `%LOCALAPPDATA%\creo-mcp\creo_mcp.py` | the copy that the Claude apps start |
| `%LOCALAPPDATA%\creo-mcp\settings.json` | Creo version, Creo path, CREOSON folder, port |

## Before you start: J-Link

CREOSON talks to Creo only through **J-Link**. It is free and part of every Creo licence,
but it is an install option that is often not selected. Step 2 of the installer checks it:
it looks for `Common Files\text\java\pfcasync.jar` and `Common Files\x86e_win64\obj\pro_comm_msg.exe`.

If it is missing: run the Creo 9 installer (`setup.exe`) -> *Reconfigure existing software*
-> Creo Parametric -> *Customize* -> *API Toolkits* -> select
*Creo Object TOOLKIT Java and J-Link* -> Install. This needs admin rights, so if IT installed
Creo, ask them to add this option.

## Setup (once)

1. Double-click `setup_creo_mcp.bat`.
   1. creates the env `creo-mcp` (Python 3.13) and installs `mcp==2.3.0`
   2. lists your Creo installs and checks J-Link in each
   3. downloads CREOSON 3.0.2 (86 MB), checks the SHA-256, unpacks it, writes `setvars.bat`.
      If there is more than one Creo, it asks which one: take the one that CMTWelcome starts.
   4. asks, then registers the server `creo` in Claude Code and/or Claude Desktop
   5. asks, then restarts Claude Desktop
2. To set the Creo folder by hand, edit `CREO_COMMON` at the top of the .bat file, e.g.
   `set "CREO_COMMON=C:\PTC\Creo 9.0.3.0\Common Files"`.

## Every time

```
 1. Creo        start it as always (CMTWelcome), wait for the main window
 2. CREOSON     start_creoson.bat - keep the window open
 3. Claude      new conversation: "what is open in Creo?"
```

The order of 1 and 2 does not matter: CREOSON finds Creo when the first request arrives.
Close the CREOSON window when you finish.

Test the whole chain at any time (the installer prints the full command):

```
"<env creo-mcp>\python.exe" creo_mcp.py check
```

## What Claude gets

| Tool | Use |
|------|-----|
| `creo_status` | is CREOSON running, is Creo connected, working directory, active model |
| `creoson_list_functions` | the ~200 CREOSON functions, by group (file, parameter, dimension, feature, drawing, familytable, interface, ...) |
| `creoson_describe` | exact parameters, notes and examples of one function |
| `creoson_call` | runs one function, e.g. `parameter.list`, `dimension.set`, `file.regenerate`, `interface.export_file` |
| `creo_screenshot` | JPEG of the model as Creo shows it, so Claude can check its work |

Blocked, because they cannot be undone: `connection.kill_creo`, `connection.stop_creo`,
`creo.delete_files`, `creo.rmdir`, `file.erase`, `file.erase_not_displayed`,
`windchill.clear_workspace`, `windchill.delete_workspace`. To allow them, run
`creo_mcp.py setup --allow-destructive` (it adds `CREO_MCP_ALLOW_DESTRUCTIVE=1` to the entry).
Everything else changes only the model in memory until something is saved.

## CMTWelcome

CREOSON does not start Creo here. It connects to the Creo session that is already running,
through J-Link. So it does not matter how Creo was started, and your CMTWelcome start stays
as it is. This works when these conditions are true:

| Condition | How to check |
|-----------|--------------|
| CMTWelcome starts the same Creo that `setvars.bat` points to (here Creo 9.0.3.0) | Task Manager -> Details -> `xtop.exe` -> right-click -> *Open file location*. The path must be inside the `Common Files` folder from the installer. |
| Creo runs as your Windows user on this PC, not in a remote or streamed session | same: `xtop.exe` is listed in your Task Manager |
| only one Creo session is open | CREOSON refuses to choose between two sessions |

CREOSON also has a function `connection.start_creo` that starts Creo from a copy of
`parametric.bat`. Do not use it: it would skip CMTWelcome, and with it the licence and
config settings that CMTWelcome probably sets.

## Creo configuration that matters

| Topic | What to know |
|-------|--------------|
| Creo version | CREOSON must be told the version for Creo 7 to 9 (needed for regenerate, assemble, suppress, delete). `creo_mcp.py` does this for every new session, from `settings.json` (`creo_version: 9`). |
| Dialogs | J-Link calls wait while a modal dialog is open in Creo (file exists, regeneration failed, licence messages, the *Welcome to Creo* / Resource Center window). Keep Creo free of open dialogs while Claude works. The Welcome window can be switched off in its own check box (PTC article CS174199). |
| Working directory | Creo opens and saves files there. Claude reads it with `creo_status` and can change it with `creo.cd`. Set it to your project folder first. |
| Saving | Creo never overwrites: each save writes a new version (`box.prt.1`, `box.prt.2`, ...). Claude is told to save only when you ask. |
| `config.pro` | No change is needed for CREOSON. Options set by CMTWelcome still apply, because Claude works inside your session. Claude can read options with `creo.get_config`. |
| Units | Dimensions and parameters use the model's units (your start part decides). Claude can read them with `file.get_unit_system`. |
| Port 9056 | CREOSON listens on all network cards and has no password. When Windows Firewall asks about Java, choose *Cancel*: Claude connects from this PC, which the firewall does not block. Close CREOSON when you do not use it. |

## Problems

| Message | Fix |
|---------|-----|
| `J-Link is not installed` | see *Before you start* |
| `nothing answers on port 9056` | start `start_creoson.bat` |
| `Creo not reachable` | Creo is not running, still starting, or a second session is open. Check the `xtop.exe` path (see CMTWelcome). |
| `Unable to connect to Creo through J-Link` in the CREOSON window, although Creo runs | the Creo in `setvars.bat` is not the one that runs; run the installer again and choose the right one. If it still fails, CREOSON's Java 25 may not work with Creo 9 J-Link: run `creo_mcp.py install-creoson --java-home "C:\PTC\JRE_11"` (not tested). |
| A call never returns | a dialog is open in Creo - close it |
| `SHA-256 mismatch` | the download is not the checked release; it was deleted. Try again, or download the zip in a browser from the CREOSON GitHub release page into `%LOCALAPPDATA%\creoson\downloads\`. |

Remove: `creo_mcp.py setup --targets code,desktop --remove`, then delete
`%LOCALAPPDATA%\creoson` and `%LOCALAPPDATA%\creo-mcp` and the env (`mamba env remove -n creo-mcp`).

## Later

CREOSON 4.0 (beta in November 2026) will have its own MCP endpoint over HTTP. When it is
released, it may replace `creo_mcp.py`; until then this setup uses the stable 3.0.2.
