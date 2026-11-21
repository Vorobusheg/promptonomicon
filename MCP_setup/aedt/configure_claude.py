"""Register the Ansys AEDT MCP server in the Claude Desktop config.

What it does:
  1. Finds the Python of the mamba env that has `ansys-aedt-mcp` installed
     (by default: the Python that runs this script).
  2. Finds the AEDT installation (ANSYSEM_ROOT* variables or C:\\Program Files\\ANSYS Inc\\v*).
  3. Finds the Claude Desktop config by searching for claude_desktop_config.json in the
     Claude folders of the app-data directories. It does not rely on one fixed path,
     because the location has changed between versions of the Windows app.
  4. Makes a timestamped backup, adds / updates the "aedt" server entry, and reads the
     file back to check it. Other MCP servers in the file are kept as they are.

Safety rules:
  - It never creates a new config file. If none is found: open Claude Desktop ->
    Settings -> Developer -> Edit Config once. The app then creates the file in the
    place where it really reads it.
  - If more than one config is found, it stops and lists them. Check which file
    "Edit Config" opens and pass that one with --config. With --interactive it asks
    instead: choose one from the list, or paste the path that "Edit Config" shows.

Usage:
  Normally started by setup_mamba_env.bat (same folder), which passes --interactive.
  By hand (run it with the env's own Python):
    mamba run -n aedt-mcp python configure_claude.py --dry-run
    mamba run -n aedt-mcp python configure_claude.py
Options:
    --dry-run           show the new config, write nothing
    --interactive       if the config file is not clear (none or several found), ask
    --config PATH       the file (or its folder) that "Edit Config" opens - the most reliable choice
    --python PATH       Python of the MCP env (if not the one running this script)
    --aedt-root PATH    AnsysEM folder, e.g. "C:\\Program Files\\ANSYS Inc\\v252\\AnsysEM"
    --name NAME         server name shown in Claude (default: aedt)
    --remove            remove the server entry instead of adding it
Only the standard library is used.
"""
from __future__ import annotations

import argparse
import datetime as dt
import glob
import json
import os
import platform
import re
import shutil
import subprocess
import sys
from pathlib import Path

ENV_NAME = "aedt-mcp"
MCP_MODULE = "ansys.aedt.mcp"
CONFIG_NAME = "claude_desktop_config.json"


# ---------------------------------------------------------------- Python of the env
def python_has_server(python: Path) -> bool:
    """True if `python` can import the AEDT MCP server package."""
    if not python.is_file():
        return False
    try:
        r = subprocess.run(
            [str(python), "-c", f"import {MCP_MODULE}"],
            capture_output=True, timeout=120,
        )
        return r.returncode == 0
    except (OSError, subprocess.SubprocessError):
        return False


def env_python(env_dir: Path) -> Path:
    if platform.system() == "Windows":
        return env_dir / "python.exe"
    return env_dir / "bin" / "python"


def candidate_env_dirs() -> list[Path]:
    """Folders that may be the aedt-mcp env: from `mamba/conda env list` and usual roots."""
    dirs: list[Path] = []
    for tool in ("mamba", "conda"):
        exe = shutil.which(tool)
        if not exe:
            continue
        try:
            r = subprocess.run([exe, "env", "list", "--json"],
                               capture_output=True, text=True, timeout=60)
            for p in json.loads(r.stdout).get("envs", []):
                dirs.append(Path(p))
        except (OSError, ValueError, subprocess.SubprocessError):
            pass
    home = Path.home()
    for root in ("miniforge3", "mambaforge", "miniconda3", "anaconda3", ".conda"):
        dirs.append(home / root / "envs" / ENV_NAME)
    for var in ("MAMBA_ROOT_PREFIX", "CONDA_ROOT"):
        if os.environ.get(var):
            dirs.append(Path(os.environ[var]) / "envs" / ENV_NAME)
    # keep order, drop duplicates; put envs named aedt-mcp first
    seen, out = set(), []
    for d in sorted(dirs, key=lambda d: d.name != ENV_NAME):
        if str(d) not in seen:
            seen.add(str(d))
            out.append(d)
    return out


def find_python(explicit: str | None) -> Path:
    if explicit:
        p = Path(explicit)
        if not python_has_server(p):
            sys.exit(f"ERROR: {p} cannot import {MCP_MODULE}.")
        return p
    me = Path(sys.executable)
    if python_has_server(me):
        return me
    for d in candidate_env_dirs():
        p = env_python(d)
        if python_has_server(p):
            return p
    sys.exit(
        f"ERROR: no Python with {MCP_MODULE} found.\n"
        f"Run setup_mamba_env.bat first, or start this script with\n"
        f"    mamba run -n {ENV_NAME} python configure_claude.py"
    )


# ---------------------------------------------------------------- AEDT installation
def find_aedt_root(explicit: str | None) -> tuple[str, Path] | None:
    """Return (env-var name, AnsysEM folder) of the newest AEDT, e.g. ("ANSYSEM_ROOT252", ...)."""
    if explicit:
        p = Path(explicit)
        m = re.search(r"v(\d{3})", str(p))
        return (f"ANSYSEM_ROOT{m.group(1)}" if m else "ANSYSEM_ROOT"), p
    found: dict[str, Path] = {}
    for k, v in os.environ.items():
        m = re.fullmatch(r"ANSYSEM_ROOT(\d{3})", k.upper())
        if m and Path(v).is_dir():
            found[m.group(1)] = Path(v)
    if platform.system() == "Windows":
        for pf in {os.environ.get("ProgramFiles", r"C:\Program Files"), r"C:\Program Files"}:
            for d in glob.glob(os.path.join(pf, "ANSYS Inc", "v[0-9][0-9][0-9]", "AnsysEM")):
                found.setdefault(Path(d).parent.name[1:], Path(d))
    else:
        for d in glob.glob("/usr/ansys_inc/v[0-9][0-9][0-9]/AnsysEM") + \
                 glob.glob("/ansys_inc/v[0-9][0-9][0-9]/AnsysEM"):
            found.setdefault(Path(d).parent.name[1:], Path(d))
    if not found:
        return None
    ver = max(found)  # "252" > "251" > "242" ...
    return f"ANSYSEM_ROOT{ver}", found[ver]


# ---------------------------------------------------------------- Claude config
SEARCH_DEPTH = 5  # deepest known layout: Packages\Claude_<id>\LocalCache\Roaming\Claude
SKIP_DIRS = {"logs", "cache", "code cache", "gpucache", "vm_bundles", "node_modules",
             "local-agent-mode-sessions", "indexeddb", "local storage", "session storage"}
EDIT_HINT = ("In Claude Desktop open Settings -> Developer -> Edit Config. It shows the file\n"
             "the app really uses (and creates it if it does not exist yet).")


def app_data_roots() -> list[Path]:
    home = Path.home()
    system = platform.system()
    if system == "Windows":
        return [Path(os.environ.get("LOCALAPPDATA", home / "AppData" / "Local")),
                Path(os.environ.get("APPDATA", home / "AppData" / "Roaming"))]
    if system == "Darwin":
        return [home / "Library" / "Application Support"]
    return [Path(os.environ.get("XDG_CONFIG_HOME", home / ".config"))]


def find_config_files() -> list[Path]:
    """All claude_desktop_config.json files below app-data folders whose name contains 'claude'.

    Known layouts (all of them are found by this search, and so are renamed folders,
    as long as the file name stays the same):
      %LOCALAPPDATA%\\Claude-Data\\claude_<id>\\                         (current Windows app)
      %APPDATA%\\Claude\\                                                 (classic installer, official docs)
      %LOCALAPPDATA%\\Packages\\Claude_<id>\\LocalCache\\Roaming\\Claude\\  (older Store app)
      ~/Library/Application Support/Claude/                              (macOS)
    """
    found: set[Path] = set()
    for root in app_data_roots():
        if not root.is_dir():
            continue
        for dirpath, dirnames, filenames in os.walk(root):
            rel = Path(dirpath).relative_to(root).parts
            if CONFIG_NAME in filenames and any("claude" in p.lower() for p in rel):
                found.add(Path(dirpath) / CONFIG_NAME)
            if len(rel) >= SEARCH_DEPTH:
                dirnames[:] = []
            elif len(rel) == 0:  # top level: only Claude folders and the Store "Packages" folder
                dirnames[:] = [d for d in dirnames if "claude" in d.lower() or d.lower() == "packages"]
            elif len(rel) == 1 and rel[0].lower() == "packages":
                dirnames[:] = [d for d in dirnames if "claude" in d.lower()]
            else:
                dirnames[:] = [d for d in dirnames if d.lower() not in SKIP_DIRS]
    return sorted(found, key=lambda p: p.stat().st_mtime, reverse=True)


def describe(p: Path) -> str:
    changed = dt.datetime.fromtimestamp(p.stat().st_mtime)
    return f"{p}\n      last changed {changed:%Y-%m-%d %H:%M}"


def config_from_user_text(text: str) -> Path:
    """Path typed or pasted by the user: quotes removed; a folder means the config inside it."""
    p = Path(text.strip().strip('"').strip("'")).expanduser()
    return p / CONFIG_NAME if p.is_dir() else p


def ask_for_config(found: list[Path], reason: str) -> Path:
    """Interactive fallback: choose a listed config, or paste the path from "Edit Config"."""
    print(reason)
    for i, p in enumerate(found, 1):
        print(f"  [{i}] {describe(p)}")
    print(EDIT_HINT)
    prompt = ("Type a number from the list, or paste the path" if found else "Paste the path") \
        + " (Enter alone = stop): "
    while True:
        try:
            answer = input(prompt).strip()
        except EOFError:
            answer = ""
        if not answer:
            sys.exit("Stopped - nothing was changed.")
        if answer.isdigit() and 1 <= int(answer) <= len(found):
            return found[int(answer) - 1]
        p = config_from_user_text(answer)
        if p.is_file():
            return p
        print(f"  Not found: {p}")


def find_config(explicit: str | None, interactive: bool = False) -> Path:
    if explicit:
        p = config_from_user_text(explicit)
        if not p.is_file():
            sys.exit(f"ERROR: {p} does not exist.\n{EDIT_HINT}")
        return p
    found = find_config_files()
    if len(found) == 1:
        return found[0]
    if not found:
        reason = f"No {CONFIG_NAME} found in the Claude app-data folders."
        if interactive:
            return ask_for_config(found, reason)
        sys.exit(f"ERROR: {reason}\n{EDIT_HINT}\nThen run this script again (or pass --config PATH).")
    reason = "More than one Claude config found. The app uses only one of them:"
    if interactive:
        return ask_for_config(found, reason)
    listing = "\n".join(f"  {describe(p)}" for p in found)
    sys.exit(f"ERROR: {reason}\n{listing}\n{EDIT_HINT}\n"
             'Then run this script again with --config "<that path>".')


def load_config(path: Path) -> dict:
    if not path.is_file() or path.stat().st_size == 0:
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8-sig"))
    except json.JSONDecodeError as e:
        sys.exit(f"ERROR: {path} is not valid JSON ({e}). Fix it by hand first.")


# ---------------------------------------------------------------- main
def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--python")
    ap.add_argument("--aedt-root")
    ap.add_argument("--config")
    ap.add_argument("--name", default="aedt")
    ap.add_argument("--remove", action="store_true")
    ap.add_argument("--interactive", action="store_true")
    a = ap.parse_args()

    cfg_path = find_config(a.config, a.interactive)
    cfg = load_config(cfg_path)
    servers = cfg.setdefault("mcpServers", {})
    print(f"Claude config : {cfg_path}")

    if a.remove:
        if servers.pop(a.name, None) is None:
            print(f"No server named '{a.name}' in the config - nothing to do.")
            return
    else:
        python = find_python(a.python)
        print(f"Env Python    : {python}")
        entry: dict = {"command": str(python), "args": ["-m", MCP_MODULE]}
        aedt = find_aedt_root(a.aedt_root)
        if aedt:
            var, root = aedt
            print(f"AEDT          : {root}  ({var})")
            entry["env"] = {var: str(root)}
        else:
            print("WARNING: AEDT installation not found; the server will try to find it itself.")
        if a.name in servers:
            print(f"Updating existing server '{a.name}'.")
        servers[a.name] = entry

    text = json.dumps(cfg, indent=2, ensure_ascii=False) + "\n"
    if a.dry_run:
        print("\n--- new config (dry run, nothing written) ---\n" + text)
        return

    stamp = dt.datetime.now().strftime("%Y%m%d-%H%M%S")
    backup = cfg_path.with_name(f"{cfg_path.stem}.backup-{stamp}.json")
    n = 1
    while backup.exists():  # never overwrite an older backup
        backup = cfg_path.with_name(f"{cfg_path.stem}.backup-{stamp}-{n}.json")
        n += 1
    shutil.copy2(cfg_path, backup)
    print(f"Backup        : {backup}")
    cfg_path.write_text(text, encoding="utf-8")

    # read the file back and check that the change is really there
    check = load_config(cfg_path).get("mcpServers", {})
    ok = (a.name not in check) if a.remove else (check.get(a.name) == servers[a.name])
    if not ok:
        sys.exit(f"ERROR: re-reading {cfg_path} does not show the change. Restore {backup}.")
    print(f"Checked       : '{a.name}' is {'removed' if a.remove else 'present'} in the saved file.")
    print("\nDone. Quit Claude Desktop completely (also from the system tray) and start it again.")
    if not a.remove:
        print(f"Then check Settings -> Developer: the server '{a.name}' should be shown as running.")


if __name__ == "__main__":
    main()
