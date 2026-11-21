# MCP_setup

Scripts that connect Claude Desktop to the software I use, through MCP servers.
One subfolder per program.

| Folder  | Program | MCP server | Files |
|---------|---------|------------|-------|
| `aedt/` | Ansys Electronics Desktop 2025 R2 (HFSS) | `ansys-aedt-mcp` 0.3.2 (official, PyAnsys) | `setup_mamba_env.bat` (creates env `aedt-mcp`, Python 3.13), `configure_claude.py` (writes the Claude Desktop config) |
| `Creo/` | PTC Creo Parametric 9 | own `creo_mcp.py` (MCP SDK 2.3.0) over CREOSON 3.0.2 (open source, MIT) | `setup_creo_mcp.bat` (env `creo-mcp`, CREOSON download + SHA-256 check, registration), `start_creoson.bat`, `creo_mcp.py`; guide in `Creo/README.md` |

Setup for `aedt/`: double-click `aedt\setup_mamba_env.bat`. It does everything:
1. creates or reuses the env and installs the server,
2. asks, then runs `configure_claude.py` (must stay in the same folder),
3. asks, then restarts Claude Desktop.
Start AEDT before using the tools.

Claude Desktop config on this PC: `%LOCALAPPDATA%\Claude-Data\claude_<id>\claude_desktop_config.json`
(older layouts: `%APPDATA%\Claude\`, `%LOCALAPPDATA%\Packages\Claude_*\LocalCache\Roaming\Claude\`).
This location is not guaranteed and has changed between app versions. The reliable reference is
Claude Desktop -> Settings -> Developer -> Edit Config, which opens the file the app really uses.
