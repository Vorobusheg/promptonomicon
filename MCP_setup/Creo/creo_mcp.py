r"""Creo MCP helper: PTC Creo Parametric <-> CREOSON <-> this MCP server <-> Claude.

One file, five commands. Run it with the Python of the env "creo-mcp"
(setup_creo_mcp.bat does all of this for you):

  find-creo        lists the Creo installs on this PC and checks J-Link in each
  install-creoson  downloads CREOSON (open source, MIT, Simplified Logic), checks
                   its SHA-256, unpacks it and writes its setvars.bat for your Creo
  setup            copies this file to the runtime folder and registers the MCP
                   server "creo" in Claude Code and/or Claude Desktop
  serve            started by the Claude apps, never by hand (stdio MCP server)
  check            end-to-end test: CREOSON port, Creo connection, MCP handshake

Chain at run time:
  Claude app --stdio--> creo_mcp.py serve --HTTP JSON--> CREOSON (port 9056)
             --J-Link async--> the Creo session that is already open

Folders, private to your Windows user and not synced:
  %LOCALAPPDATA%\creoson\CreosonServer-<ver>\   CREOSON itself (+ its own Java)
  %LOCALAPPDATA%\creo-mcp\creo_mcp.py           the copy that the Claude apps start
  %LOCALAPPDATA%\creo-mcp\settings.json         what install-creoson found

Safety: functions that delete files, erase models from memory or close Creo
(see GUARDED) are refused unless CREO_MCP_ALLOW_DESTRUCTIVE=1 is set in the
server entry. Everything else in Creo can still be undone by not saving.

Examples:
  python creo_mcp.py find-creo
  python creo_mcp.py install-creoson --interactive
  python creo_mcp.py install-creoson --creo-common "C:\PTC\Creo 9.0.3.0\Common Files"
  python creo_mcp.py setup --targets code,desktop --interactive
  python creo_mcp.py setup --targets code,desktop --remove
  python creo_mcp.py check
"""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import os
import platform
import queue
import re
import shutil
import socket
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
import zipfile
from pathlib import Path

SERVER_NAME = "creo"
DEFAULT_PORT = 9056
CREOSON_VERSION = "3.0.2"
CREOSON_ZIP = f"CreosonServerWithSetup-{CREOSON_VERSION}-win64.zip"
CREOSON_URL = ("https://github.com/SimplifiedLogic/creoson/releases/download/"
               f"v{CREOSON_VERSION}/{CREOSON_ZIP}")
# SHA-256 of the release zip above, taken from GitHub on 2026-11-18.
CREOSON_SHA256 = "4645d276950709130e6c1476715627e87862ff8ed3adcd4a78c771e04ace5f70"
PROE_ENV = "x86e_win64"
CONFIG_NAME = "claude_desktop_config.json"
WINDOWS = os.name == "nt"
OK, BAD, SKIP = "[ok]", "[!!]", "[--]"
MAX_IMAGE_BYTES = 1_500_000  # larger MCP messages can break the connection to the Claude app

# command-function pairs that cannot be undone by "do not save":
# they delete files on disk, drop models from memory, or close Creo.
GUARDED = {
    ("connection", "kill_creo"), ("connection", "stop_creo"),
    ("creo", "delete_files"), ("creo", "rmdir"),
    ("file", "erase"), ("file", "erase_not_displayed"),
    ("windchill", "clear_workspace"), ("windchill", "delete_workspace"),
}


def say(text: str = "") -> None:
    print(text, flush=True)


def warn(text: str) -> None:
    print(text, file=sys.stderr, flush=True)


# ---------------------------------------------------------------- folders and settings
def local_appdata() -> Path:
    if os.environ.get("CREO_MCP_LOCALAPPDATA"):  # used by tests
        return Path(os.environ["CREO_MCP_LOCALAPPDATA"])
    if WINDOWS:
        return Path(os.environ.get("LOCALAPPDATA") or Path.home() / "AppData" / "Local")
    return Path.home() / ".local" / "share"


def runtime_dir() -> Path:
    return local_appdata() / "creo-mcp"


def default_creoson_dir() -> Path:
    return local_appdata() / "creoson" / f"CreosonServer-{CREOSON_VERSION}"


def settings_path() -> Path:
    return runtime_dir() / "settings.json"


def load_settings() -> dict:
    try:
        return json.loads(settings_path().read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def save_settings(data: dict) -> None:
    settings_path().parent.mkdir(parents=True, exist_ok=True)
    settings_path().write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")


# ---------------------------------------------------------------- Creo installs
class CreoInstall:
    """One Creo Parametric install, found by its 'Common Files' folder."""

    def __init__(self, common: Path):
        self.common = common
        self.root = common.parent  # e.g. C:\PTC\Creo 9.0.3.0
        m = re.search(r"Creo[ _]?(\d+)(?:\.(\d+))?", str(self.root), re.I)
        self.major = int(m.group(1)) if m else 0
        self.label = self.root.name if m is None or self.root.name.lower().startswith("creo") \
            else f"{self.root.parent.name}\\{self.root.name}"
        self.jlink = common / "text" / "java" / "pfcasync.jar"
        self.comm_msg = common / PROE_ENV / "obj" / "pro_comm_msg.exe"
        self.parametric_bat = self.root / "Parametric" / "bin" / "parametric.bat"

    @property
    def usable(self) -> bool:
        return self.jlink.is_file() and self.comm_msg.is_file()

    def report(self) -> list[str]:
        mark = lambda ok: OK if ok else BAD  # noqa: E731
        return [f"{self.label}   ({self.common})",
                f"    {mark(self.major > 0)} Creo version      {self.major or 'unknown'}",
                f"    {mark(self.jlink.is_file())} J-Link (async)    {self.jlink.name}",
                f"    {mark(self.comm_msg.is_file())} pro_comm_msg.exe  {self.comm_msg.parent}",
                f"    {SKIP} parametric.bat    "
                f"{'found' if self.parametric_bat.is_file() else 'not found'}"]


def creo_search_roots() -> list[Path]:
    roots = [Path("C:/PTC")]
    for var in ("ProgramFiles", "ProgramW6432", "ProgramFiles(x86)"):
        if os.environ.get(var):
            roots.append(Path(os.environ[var]) / "PTC")
    roots.append(Path("C:/Program Files/PTC"))
    if os.environ.get("CREO_MCP_SEARCH_ROOT"):  # used by tests
        roots.insert(0, Path(os.environ["CREO_MCP_SEARCH_ROOT"]))
    seen, out = set(), []
    for r in roots:
        key = str(r).lower()
        if key not in seen and r.is_dir():
            seen.add(key)
            out.append(r)
    return out


def find_creo_installs() -> list[CreoInstall]:
    """'Common Files' folders up to two levels below a PTC root that contain x86e_win64.
    Creo 4 and later: PTC\\Creo 9.0.3.0\\Common Files. Creo 3: PTC\\Creo 3.0\\M020\\Common Files."""
    found: dict[str, CreoInstall] = {}
    for root in creo_search_roots():
        for pattern in ("*/Common Files", "*/*/Common Files"):
            for common in root.glob(pattern):
                if (common / PROE_ENV).is_dir():
                    found[str(common.resolve()).lower()] = CreoInstall(common)
    return sorted(found.values(), key=lambda c: (c.major, str(c.root)), reverse=True)


def cmd_find_creo(a: argparse.Namespace) -> int:
    installs = find_creo_installs()
    if not installs:
        say(f"{BAD} No Creo install found below: " + ", ".join(map(str, creo_search_roots())))
        return 1
    for c in installs:
        say("\n".join(c.report()))
    return 0


def choose_creo(explicit: str | None, interactive: bool) -> CreoInstall | None:
    if explicit:
        p = Path(explicit.strip().strip('"'))
        if p.name.lower() != "common files" and (p / "Common Files").is_dir():
            p = p / "Common Files"
        if not (p / PROE_ENV).is_dir():
            say(f"{BAD} {p} is not a Creo 'Common Files' folder (no {PROE_ENV} inside).")
            return None
        return CreoInstall(p)
    installs = find_creo_installs()
    if not installs:
        say(f"{BAD} No Creo install found below: " + ", ".join(map(str, creo_search_roots())))
        say("    Run again with --creo-common \"<Creo folder>\\Common Files\".")
        return None
    usable = [c for c in installs if c.usable]
    if len(usable) == 1 and len(installs) == 1:
        return usable[0]
    say("Creo installs on this PC:")
    for i, c in enumerate(installs, 1):
        say(f"  [{i}] " + "\n      ".join(c.report()))
    if not interactive:
        if len(usable) == 1:
            return usable[0]
        say(f"{BAD} Several or no usable installs. Run again with --creo-common or --interactive.")
        return None
    while True:
        try:
            ans = input("Number of the Creo you start through CMTWelcome (Enter = cancel): ").strip()
        except EOFError:
            ans = ""
        if not ans:
            return None
        if ans.isdigit() and 1 <= int(ans) <= len(installs):
            return installs[int(ans) - 1]


def jlink_help(c: CreoInstall) -> str:
    return (f"{BAD} J-Link is not installed in {c.label}.\n"
            "    CREOSON talks to Creo only through J-Link (free, part of every Creo license).\n"
            "    Add it: run the Creo installer (setup.exe of the same Creo version) ->\n"
            "    'Reconfigure existing software' -> Creo Parametric -> Customize ->\n"
            "    'API Toolkits' -> tick 'Creo Object TOOLKIT Java and J-Link' -> Install.\n"
            "    This needs admin rights: if Creo was installed by IT, ask them for this option.")


# ---------------------------------------------------------------- CREOSON install
def sha256_of(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def download(url: str, dest: Path) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_suffix(dest.suffix + ".part")
    say(f"  downloading {url}")
    with urllib.request.urlopen(url, timeout=120) as r, tmp.open("wb") as f:
        total = int(r.headers.get("Content-Length") or 0)
        done, last = 0, -10
        while True:
            chunk = r.read(1 << 20)
            if not chunk:
                break
            f.write(chunk)
            done += len(chunk)
            pct = int(100 * done / total) if total else 0
            if total and pct >= last + 10:
                say(f"    {pct:3d} %  ({done >> 20} MB)")
                last = pct
    tmp.replace(dest)


def safe_extract(zip_path: Path, target: Path) -> None:
    target.mkdir(parents=True, exist_ok=True)
    base = target.resolve()
    with zipfile.ZipFile(zip_path) as z:
        for info in z.infolist():
            out = (target / info.filename).resolve()
            if base != out and base not in out.parents:
                raise RuntimeError(f"unsafe path in zip: {info.filename}")
        z.extractall(target)


def setvars_text(c: CreoInstall, java_home: Path, port: int) -> str:
    # The same four variables that CreosonSetup.exe writes and creoson_run.bat reads.
    return ("@echo off\r\n"
            "rem Written by creo_mcp.py install-creoson. Read by creoson_run.bat.\r\n"
            f'set "PROE_COMMON={c.common}"\r\n'
            f'set "PROE_ENV={PROE_ENV}"\r\n'
            f'set "JAVA_HOME={java_home}"\r\n'
            f'set "JSON_PORT={port}"\r\n')


def cmd_install_creoson(a: argparse.Namespace) -> int:
    c = choose_creo(a.creo_common, a.interactive)
    if c is None:
        return 1
    say(f"Creo          : {c.label}  (version {c.major or 'unknown'})")
    if not c.usable:
        say(jlink_help(c) if not c.jlink.is_file() else
            f"{BAD} {c.comm_msg} is missing: the Creo install looks incomplete.")
        return 1
    say(f"{OK} J-Link found : {c.jlink}")
    target = Path(a.creoson_dir) if a.creoson_dir else default_creoson_dir()
    jar = target / f"CreosonServer-{CREOSON_VERSION}.jar"
    if jar.is_file():
        say(f"{OK} CREOSON {CREOSON_VERSION} already unpacked in {target} - reusing it")
    elif a.dry_run:
        say(f"  would download {CREOSON_ZIP} and unpack it to {target}")
    else:
        zip_path = target.parent / "downloads" / CREOSON_ZIP
        if not zip_path.is_file() or sha256_of(zip_path) != CREOSON_SHA256:
            try:
                download(CREOSON_URL, zip_path)
            except (OSError, urllib.error.URLError) as e:
                say(f"{BAD} download failed: {e}\n    Download it in a browser from\n    {CREOSON_URL}\n"
                    f"    and put it here: {zip_path}  - then run this again.")
                return 1
        digest = sha256_of(zip_path)
        if digest != CREOSON_SHA256:
            say(f"{BAD} SHA-256 mismatch - the file is not the release that was checked.\n"
                f"    expected {CREOSON_SHA256}\n    got      {digest}\n    Deleted it; nothing was unpacked.")
            zip_path.unlink(missing_ok=True)
            return 1
        say(f"{OK} SHA-256 matches the checked release")
        safe_extract(zip_path, target)
        if not jar.is_file():
            say(f"{BAD} {jar.name} is not in the zip. Unexpected release layout.")
            return 1
        say(f"{OK} unpacked to {target}")
    java_home = Path(a.java_home) if a.java_home else target / "jre"
    if not a.dry_run and not (java_home / "bin" / ("java.exe" if WINDOWS else "java")).is_file():
        say(f"{BAD} no java in {java_home}. Give another one with --java-home.")
        return 1
    text = setvars_text(c, java_home, a.port)
    if a.dry_run:
        say(f"  would write {target / 'setvars.bat'}:\n{text}")
        return 0
    (target / "setvars.bat").write_text(text, encoding="ascii", errors="replace")
    say(f"{OK} setvars.bat  : PROE_COMMON={c.common}, JSON_PORT={a.port}, JAVA_HOME={java_home}")
    save_settings({"creoson_dir": str(target), "port": a.port, "creo_common": str(c.common),
                   "creo_version": c.major, "parametric_bat": str(c.parametric_bat),
                   "written": dt.datetime.now().isoformat(timespec="seconds")})
    say(f"{OK} settings     : {settings_path()}")
    return 0


# ---------------------------------------------------------------- CREOSON client
class CreosonError(Exception):
    pass


class Creoson:
    """Small JSON client for the CREOSON server. One session, re-made when it expires."""

    def __init__(self, url: str, creo_version: int = 0, timeout: float = 600):
        self.url = url
        self.creo_version = creo_version
        self.timeout = timeout
        self.session = ""
        self.version_sent = False
        self.lock = threading.Lock()

    def _post(self, command: str, function: str, data: dict | None) -> dict:
        body = {"sessionId": self.session, "command": command, "function": function}
        if data:
            body["data"] = data
        req = urllib.request.Request(self.url, data=json.dumps(body).encode("utf-8"),
                                     headers={"Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as r:
                return json.loads(r.read().decode("utf-8", "replace") or "{}")
        except urllib.error.URLError as e:
            raise CreosonError(f"CREOSON does not answer at {self.url} ({e.reason}). "
                               "Start it with start_creoson.bat and keep its window open.") from e

    def _connect(self) -> None:
        self.session = ""
        self.version_sent = False
        r = self._post("connection", "connect", None)
        if r.get("status", {}).get("error"):
            raise CreosonError(r["status"].get("message") or "CREOSON refused the connection")
        self.session = r.get("sessionId", "")

    def call(self, command: str, function: str, data: dict | None = None) -> dict:
        with self.lock:
            if not self.session:
                self._connect()
            if command != "connection":
                self._send_version()
            r = self._post(command, function, data)
            msg = r.get("status", {}).get("message") or ""
            if r.get("status", {}).get("error") and re.search(r"session|expired", msg, re.I):
                self._connect()
                if command != "connection":
                    self._send_version()
                r = self._post(command, function, data)
                msg = r.get("status", {}).get("message") or ""
            if r.get("status", {}).get("error"):
                raise CreosonError(msg or f"{command}.{function} failed")
            return r.get("data") or {}

    def _send_version(self) -> None:
        # CREOSON needs this once per session for Creo 7-9 (regenerate, assemble,
        # suppress, delete...). Creo 10+ uses its native library instead.
        if self.version_sent or not 7 <= self.creo_version <= 9:
            return
        r = self._post("creo", "set_creo_version", {"version": self.creo_version})
        if not r.get("status", {}).get("error"):
            self.version_sent = True


# ---------------------------------------------------------------- MCP server
INSTRUCTIONS = """\
Drives the PTC Creo Parametric session that is open on this PC, through CREOSON.
- Start with creo_status. If CREOSON or Creo is not running, tell the user what to start
  (Creo through CMTWelcome first, then start_creoson.bat). Do not start Creo yourself.
- CREOSON has about 200 functions. Find them with creoson_list_functions, read the exact
  parameters with creoson_describe, then run them with creoson_call.
- File names include the extension (bracket.prt, box.asm). Paths use the Creo working directory
  unless 'dirname' is given. Dimensions and parameters use the model's own units.
- Never save, rename or overwrite files unless the user asked for it. Model changes in memory
  are harmless until saved. After changes, regenerate (file.regenerate) and check for errors.
- creo_screenshot shows the active model, so you can check the result of your changes.
"""


def make_server(client: Creoson, creoson_dir: Path | None, allow_destructive: bool):
    from mcp.server.mcpserver import Image, MCPServer
    from mcp.server.mcpserver.exceptions import ToolError

    # annotations are strings here (from __future__), so the SDK resolves 'Image' in globals
    globals()["Image"] = Image
    server = MCPServer("creo", instructions=INSTRUCTIONS, version=CREOSON_VERSION)
    specs_dir = (creoson_dir / "web" / "assets" / "creoson_stuff" / "jsonSpecs") if creoson_dir else None

    def specs() -> dict[tuple[str, str], dict]:
        if not specs_dir or not specs_dir.is_dir():
            raise ToolError(f"CREOSON function specs not found in {specs_dir}. Run setup_creo_mcp.bat.")
        out = {}
        for f in specs_dir.glob("*-*.json"):
            cmd, fn = f.stem.split("-", 1)
            try:
                out[(cmd, fn)] = json.loads(f.read_text(encoding="utf-8"))
            except ValueError:
                continue
        return out

    def run(command: str, function: str, data: dict | None = None) -> dict:
        try:
            return client.call(command, function, data)
        except CreosonError as e:
            raise ToolError(str(e)) from e

    @server.tool()
    def creo_status() -> dict:
        """Check the chain: CREOSON server, Creo session, working directory, active model."""
        out = {"creoson_url": client.url, "creo_version_setting": client.creo_version}
        try:
            running = client.call("connection", "is_creo_running").get("running", False)
        except CreosonError as e:
            out.update(creoson="not reachable", hint=str(e))
            return out
        out["creoson"] = "running"
        out["creo_connected"] = bool(running)
        if not running:
            out["hint"] = ("CREOSON runs, but no Creo session is reachable. Start Creo the usual way "
                           "(CMTWelcome). Only one Creo session may be open.")
            return out
        try:
            out["working_directory"] = client.call("creo", "pwd").get("dirname")
        except CreosonError as e:
            out["working_directory_error"] = str(e)
        try:
            act = client.call("file", "get_active")
            out["active_model"] = act.get("file") or None
        except CreosonError:
            out["active_model"] = None
        return out

    @server.tool()
    def creoson_list_functions(command: str = "") -> dict:
        """List CREOSON functions with a one-line description, grouped by command
        (bom, connection, creo, dimension, drawing, familytable, feature, file, geometry,
        interface, layer, note, parameter, view, windchill). Give 'command' to see one group."""
        groups: dict[str, dict[str, str]] = {}
        for (cmd, fn), spec in sorted(specs().items()):
            if command and cmd != command:
                continue
            desc = spec.get("spec", {}).get("function_description", "")
            if (cmd, fn) in GUARDED and not allow_destructive:
                desc += "  [blocked: destructive]"
            groups.setdefault(cmd, {})[fn] = desc
        if command and not groups:
            raise ToolError(f"No command group '{command}'. Call without arguments to see all.")
        return groups

    @server.tool()
    def creoson_describe(command: str, function: str) -> dict:
        """Full description of one CREOSON function: parameters (names, types, valid
        values, defaults), response fields, notes and example requests/responses."""
        spec = specs().get((command, function))
        if spec is None:
            raise ToolError(f"Unknown function {command}.{function}. Use creoson_list_functions.")
        return spec

    @server.tool()
    def creoson_call(command: str, function: str, data: dict | None = None) -> dict:
        """Run one CREOSON function in the open Creo session and return its 'data' part.
        Example: command='parameter', function='list', data={'file': 'box.prt'}.
        Read creoson_describe first when you are not sure about the parameters."""
        if (command, function) in GUARDED and not allow_destructive:
            raise ToolError(f"{command}.{function} is blocked: it deletes files, drops models from "
                            "memory or closes Creo, and that cannot be undone. Ask the user to do it in "
                            "Creo, or to set CREO_MCP_ALLOW_DESTRUCTIVE=1 in the 'creo' server entry.")
        if command == "connection" and function in ("connect", "disconnect"):
            raise ToolError("The session is handled by this server. Use creo_status.")
        return run(command, function, data)

    @server.tool()
    def creo_screenshot(file: str = "", width_px: int = 800) -> Image:
        """Picture (JPEG, 4:3) of a model as Creo shows it now. file = model name,
        empty = active model. width_px: 200 to 1600 pixels (default 800)."""
        if not 200 <= width_px <= 1600:
            raise ToolError("width_px must be between 200 and 1600")
        # CREOSON takes width/height in INCHES plus dpi: pixels = inches * dpi.
        dpi = 100
        name = f"cv{int(time.time()) % 100000000}.jpg"  # Creo: < 32 characters before .jpg
        data = {"type": "JPEG", "filename": name, "dpi": dpi,
                "width": round(width_px / dpi, 2), "height": round(width_px * 0.75 / dpi, 2)}
        if file:
            data["file"] = file
        res = run("interface", "export_image", data)
        path = Path(res.get("dirname") or "") / (res.get("filename") or name)
        try:
            img = path.read_bytes()
        except OSError as e:
            raise ToolError(f"Creo wrote the picture, but it cannot be read at {path}: {e}") from e
        finally:
            try:
                path.unlink()
            except OSError:
                pass
        if len(img) > MAX_IMAGE_BYTES:
            raise ToolError(f"The picture is {len(img) >> 10} kB, too large to send. Use a smaller width_px.")
        return Image(data=img, format="jpeg")

    return server


def cmd_serve(a: argparse.Namespace) -> int:
    """Runs on the stdio pipes of the Claude app: never print to stdout here."""
    s = load_settings()
    port = int(os.environ.get("CREOSON_PORT") or s.get("port") or DEFAULT_PORT)
    url = os.environ.get("CREOSON_URL") or f"http://127.0.0.1:{port}/creoson"
    version = int(os.environ.get("CREO_VERSION") or s.get("creo_version") or 0)
    cdir = os.environ.get("CREOSON_DIR") or s.get("creoson_dir")
    allow = os.environ.get("CREO_MCP_ALLOW_DESTRUCTIVE", "") == "1"
    client = Creoson(url, version)
    if not port_open(url):
        warn(f"[creo-mcp] nothing answers at {url} yet - start start_creoson.bat.")
    make_server(client, Path(cdir) if cdir else None, allow).run("stdio")
    return 0


# ---------------------------------------------------------------- small helpers
def host_port(url: str) -> tuple[str, int]:
    u = urllib.parse.urlparse(url)
    return u.hostname or "127.0.0.1", u.port or (443 if u.scheme == "https" else 80)


def port_open(url: str, timeout: float = 1.0) -> bool:
    try:
        with socket.create_connection(host_port(url), timeout=timeout):
            return True
    except OSError:
        return False


# ---------------------------------------------------------------- Claude Desktop config
SEARCH_DEPTH = 5  # deepest known layout: Packages\Claude_<id>\LocalCache\Roaming\Claude
SKIP_DIRS = {"logs", "cache", "code cache", "gpucache", "vm_bundles", "node_modules",
             "local-agent-mode-sessions", "indexeddb", "local storage", "session storage"}
EDIT_HINT = ("In Claude Desktop open Settings -> Developer -> Edit Config. It shows the file\n"
             "the app really uses (and creates it if it does not exist yet).")


def app_data_roots() -> list[Path]:
    home = Path.home()
    if WINDOWS:
        return [Path(os.environ.get("LOCALAPPDATA", home / "AppData" / "Local")),
                Path(os.environ.get("APPDATA", home / "AppData" / "Roaming"))]
    if platform.system() == "Darwin":
        return [home / "Library" / "Application Support"]
    return [Path(os.environ.get("XDG_CONFIG_HOME", home / ".config"))]


def find_config_files() -> list[Path]:
    """Every claude_desktop_config.json below app-data folders whose path contains 'claude'."""
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
            elif len(rel) == 0:
                dirnames[:] = [d for d in dirnames if "claude" in d.lower() or d.lower() == "packages"]
            elif len(rel) == 1 and rel[0].lower() == "packages":
                dirnames[:] = [d for d in dirnames if "claude" in d.lower()]
            else:
                dirnames[:] = [d for d in dirnames if d.lower() not in SKIP_DIRS]
    return sorted(found, key=lambda p: p.stat().st_mtime, reverse=True)


def config_from_user_text(text: str) -> Path:
    p = Path(text.strip().strip('"').strip("'")).expanduser()
    return p / CONFIG_NAME if p.is_dir() else p


def ask_for_config(found: list[Path], reason: str) -> Path | None:
    say(reason)
    for i, p in enumerate(found, 1):
        changed = dt.datetime.fromtimestamp(p.stat().st_mtime)
        say(f"  [{i}] {p}\n      last changed {changed:%Y-%m-%d %H:%M}")
    say(EDIT_HINT)
    prompt = ("Type a number from the list, or paste the path" if found else "Paste the path") \
        + " (Enter alone = skip Claude Desktop): "
    while True:
        try:
            answer = input(prompt).strip()
        except EOFError:
            answer = ""
        if not answer:
            return None
        if answer.isdigit() and 1 <= int(answer) <= len(found):
            return found[int(answer) - 1]
        p = config_from_user_text(answer)
        if p.is_file():
            return p
        say(f"  Not found: {p}")


def find_desktop_config(explicit: str | None, interactive: bool) -> Path | None:
    if explicit:
        p = config_from_user_text(explicit)
        if not p.is_file():
            say(f"  {BAD} {p} does not exist.\n{EDIT_HINT}")
            return None
        return p
    found = find_config_files()
    if len(found) == 1:
        return found[0]
    reason = (f"No {CONFIG_NAME} found in the Claude app-data folders." if not found
              else "More than one Claude Desktop config found. The app uses only one of them:")
    if interactive:
        return ask_for_config(found, reason)
    say(f"  {BAD} {reason}")
    for p in found:
        say(f"      {p}")
    say(f"{EDIT_HINT}\n  Then run again with --desktop-config \"<that path>\".")
    return None


def load_json(path: Path) -> dict:
    if not path.is_file() or path.stat().st_size == 0:
        return {}
    return json.loads(path.read_text(encoding="utf-8-sig"))


def desktop_update(cfg_path: Path, name: str, entry: dict | None, dry: bool) -> bool:
    """entry=None removes the server. Backup first, then write, then read back."""
    try:
        cfg = load_json(cfg_path)
    except json.JSONDecodeError as e:
        say(f"  {BAD} {cfg_path} is not valid JSON ({e}). Fix it by hand first.")
        return False
    servers = cfg.setdefault("mcpServers", {})
    if entry is None:
        if servers.pop(name, None) is None:
            say(f"  {SKIP} no server '{name}' in {cfg_path}")
            return True
    else:
        servers[name] = entry
    text = json.dumps(cfg, indent=2, ensure_ascii=False) + "\n"
    if dry:
        say(f"  would write {cfg_path} with:\n" + json.dumps({name: entry}, indent=2))
        return True
    stamp = dt.datetime.now().strftime("%Y%m%d-%H%M%S")
    backup = cfg_path.with_name(f"{cfg_path.stem}.backup-{stamp}.json")
    n = 1
    while backup.exists():
        backup = cfg_path.with_name(f"{cfg_path.stem}.backup-{stamp}-{n}.json")
        n += 1
    shutil.copy2(cfg_path, backup)
    cfg_path.write_text(text, encoding="utf-8")
    check = load_json(cfg_path).get("mcpServers", {})
    ok = (name not in check) if entry is None else (check.get(name) == entry)
    if not ok:
        say(f"  {BAD} re-reading {cfg_path} does not show the change. Restore {backup}.")
        return False
    say(f"  {OK} Claude Desktop: '{name}' {'removed from' if entry is None else 'written to'} {cfg_path}")
    say(f"       backup: {backup.name}")
    return True


# ---------------------------------------------------------------- Claude Code
def find_claude_cli(explicit: str | None) -> Path | None:
    """Standalone install, npm install, newest VS Code extension copy. On Windows PATH is
    not searched: an old Claude Desktop can put its own claude.exe there."""
    if explicit:
        p = Path(explicit)
        return p if p.is_file() else None
    if not WINDOWS:
        w = shutil.which("claude")
        return Path(w) if w else None
    home = Path.home()
    for p in (home / ".local" / "bin" / "claude.exe",
              Path(os.environ.get("APPDATA", home / "AppData" / "Roaming")) / "npm" / "claude.cmd"):
        if p.is_file():
            return p
    best, best_ver = None, ()
    for d in (home / ".vscode" / "extensions").glob("anthropic.claude-code-*"):
        exe = d / "resources" / "native-binary" / "claude.exe"
        m = re.match(r"anthropic\.claude-code-(\d+)\.(\d+)\.(\d+)", d.name)
        if exe.is_file() and m:
            ver = tuple(int(x) for x in m.groups())
            if ver > best_ver:
                best, best_ver = exe, ver
    return best


def run_cli(cli: Path, args: list[str], timeout: int = 180) -> subprocess.CompletedProcess:
    return subprocess.run([str(cli), *args], capture_output=True, text=True, encoding="utf-8",
                          errors="replace", timeout=timeout, stdin=subprocess.DEVNULL)


def code_update(cli: Path, name: str, entry: dict | None, dry: bool) -> bool:
    if entry is None:
        add = None
    elif cli.suffix.lower() in (".cmd", ".bat"):
        # cmd.exe re-parses the arguments of a .cmd file and breaks JSON quotes,
        # so the npm install gets plain flags instead of add-json.
        add = ["mcp", "add"]
        for k, v in entry["env"].items():
            add += ["-e", f"{k}={v}"]
        add += ["--transport", "stdio", "--scope", "user", name, "--", entry["command"], *entry["args"]]
    else:
        add = ["mcp", "add-json", name, json.dumps({"type": "stdio", **entry}), "--scope", "user"]
    if dry:
        say(f"  would run: {cli.name} mcp remove {name} --scope user")
        if add:
            say(f"  would run: {cli.name} {' '.join(add[:3])} ... --scope user")
        return True
    r = run_cli(cli, ["mcp", "remove", name, "--scope", "user"])
    if add is None:
        say(f"  {OK if r.returncode == 0 else SKIP} Claude Code: "
            f"{'removed' if r.returncode == 0 else 'nothing to remove for'} '{name}'")
        return True
    r = run_cli(cli, add)
    if r.returncode != 0:
        say(f"  {BAD} Claude Code refused the entry:\n{(r.stderr or r.stdout).strip()}")
        return False
    say(f"  {OK} Claude Code: '{name}' added to the user config (all projects)")
    r = run_cli(cli, ["mcp", "get", name])
    for line in (r.stdout or r.stderr).strip().splitlines():
        if line.strip().startswith(("Status", "Scope", "Command", "Args")):
            say(f"       {line.strip()}")
    return True


# ---------------------------------------------------------------- setup
def server_env(s: dict, allow_destructive: bool) -> dict:
    env = {"CREOSON_URL": f"http://127.0.0.1:{s.get('port', DEFAULT_PORT)}/creoson",
           "CREOSON_DIR": s.get("creoson_dir", str(default_creoson_dir())),
           "CREO_VERSION": str(s.get("creo_version", 0))}
    if allow_destructive:
        env["CREO_MCP_ALLOW_DESTRUCTIVE"] = "1"
    return env


def cmd_setup(a: argparse.Namespace) -> int:
    targets = {t.strip().lower() for t in a.targets.split(",") if t.strip()}
    if (targets - {"code", "desktop"}) or not targets:
        say(f"{BAD} --targets takes code, desktop or code,desktop (got: {a.targets})")
        return 2
    rt = runtime_dir()
    script_copy = rt / "creo_mcp.py"
    entry = None
    if not a.remove:
        try:
            import mcp.server.mcpserver  # noqa: F401
        except ImportError:
            say(f"{BAD} {sys.executable} cannot import the MCP SDK (mcp 2.x).\n"
                "    Run this file with the Python of the env creo-mcp, as setup_creo_mcp.bat does.")
            return 1
        s = load_settings()
        if not s:
            say(f"{BAD} {settings_path()} is missing - run install-creoson first.")
            return 1
        say(f"Server Python : {sys.executable}")
        say(f"CREOSON       : {s['creoson_dir']}  (port {s['port']})")
        say(f"Creo version  : {s.get('creo_version')}")
        here = Path(__file__).resolve()
        if not a.dry_run and here != script_copy.resolve():
            rt.mkdir(parents=True, exist_ok=True)
            shutil.copy2(here, script_copy)
        say(f"Started by app: {script_copy}")
        entry = {"command": sys.executable, "args": ["-I", str(script_copy), "serve"],
                 "env": server_env(s, a.allow_destructive)}
    ok = True
    if "code" in targets:
        say("\nClaude Code (VS Code panel and CLI):")
        cli = find_claude_cli(a.claude_cli)
        if cli is None:
            say(f"  {BAD} Claude Code not found: no standalone CLI and no VS Code extension.")
            ok = False
        else:
            say(f"  using {cli}")
            ok &= code_update(cli, a.name, entry, a.dry_run)
    if "desktop" in targets:
        say("\nClaude Desktop:")
        cfg = find_desktop_config(a.desktop_config, a.interactive)
        if cfg is None:
            say(f"  {SKIP} Claude Desktop skipped.")
            ok = False
        else:
            ok &= desktop_update(cfg, a.name, entry, a.dry_run)
    return 0 if ok else 1


# ---------------------------------------------------------------- check
class StdioClient:
    """Minimal MCP client: newline-delimited JSON-RPC over the server's stdin/stdout."""

    def __init__(self, cmd: list[str], env: dict):
        self.p = subprocess.Popen(cmd, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                  stderr=subprocess.PIPE, env=env)
        self.lines: queue.Queue = queue.Queue()
        self.stderr: list[str] = []
        threading.Thread(target=self._pump_out, daemon=True).start()
        threading.Thread(target=self._pump_err, daemon=True).start()
        self.next_id = 1

    def _pump_out(self):
        for raw in self.p.stdout:
            self.lines.put(raw)
        self.lines.put(None)

    def _pump_err(self):
        for raw in self.p.stderr:
            self.stderr.append(raw.decode("utf-8", "replace").rstrip())

    def send(self, msg: dict) -> None:
        self.p.stdin.write((json.dumps(msg) + "\n").encode("utf-8"))
        self.p.stdin.flush()

    def request(self, method: str, params: dict, timeout: float) -> dict:
        rid = self.next_id
        self.next_id += 1
        self.send({"jsonrpc": "2.0", "id": rid, "method": method, "params": params})
        deadline = time.monotonic() + timeout
        while True:
            left = deadline - time.monotonic()
            if left <= 0:
                raise TimeoutError(f"no answer to {method} within {timeout:.0f} s")
            try:
                raw = self.lines.get(timeout=left)
            except queue.Empty:
                continue
            if raw is None:
                raise RuntimeError("the MCP server exited")
            try:
                msg = json.loads(raw)
            except ValueError:
                continue
            if msg.get("id") == rid and "method" not in msg:
                return msg

    def close(self) -> None:
        try:
            self.p.stdin.close()
            self.p.wait(timeout=10)
        except Exception:
            self.p.kill()


def text_of(result: dict) -> str:
    parts = result.get("result", {}).get("content", [])
    return "\n".join(p.get("text", "") for p in parts if p.get("type") == "text").strip()


def cmd_check(a: argparse.Namespace) -> int:
    s = load_settings()
    if not s:
        say(f"{BAD} settings     {settings_path()} missing - run setup_creo_mcp.bat")
        return 1
    port = a.port or s.get("port", DEFAULT_PORT)
    url = f"http://127.0.0.1:{port}/creoson"
    bad = 0
    say(f"Checking {url}\n")
    cdir = Path(s["creoson_dir"])
    if (cdir / "setvars.bat").is_file():
        say(f"{OK} CREOSON      installed in {cdir}")
    else:
        say(f"{BAD} CREOSON      no setvars.bat in {cdir} - run setup_creo_mcp.bat")
        bad += 1
    if not port_open(url):
        say(f"{BAD} CREOSON      nothing answers on port {port} - start start_creoson.bat")
        return 1
    client = Creoson(url, int(s.get("creo_version") or 0), timeout=60)
    try:
        running = client.call("connection", "is_creo_running").get("running", False)
        say(f"{OK} CREOSON      answers, session {client.session[:8]}...")
    except CreosonError as e:
        say(f"{BAD} CREOSON      {e}")
        return 1
    if running:
        pwd = client.call("creo", "pwd").get("dirname")
        say(f"{OK} Creo         connected through J-Link, working directory {pwd}")
    else:
        say(f"{BAD} Creo         not reachable. Start Creo (CMTWelcome), wait for the main window,\n"
            "               then run check again. Only one Creo session may be open.")
        bad += 1
    say(f"{SKIP} MCP          starting the server the way the Claude apps do ...")
    env = dict(os.environ, **server_env(s, False))
    cmd = [sys.executable, "-I", str(Path(__file__).resolve()), "serve"]
    mc = StdioClient(cmd, env)
    try:
        init = mc.request("initialize", {
            "protocolVersion": "2025-06-18", "capabilities": {},
            "clientInfo": {"name": "creo-mcp-check", "version": "1"}}, timeout=90)
        info = init.get("result", {}).get("serverInfo", {})
        mc.send({"jsonrpc": "2.0", "method": "notifications/initialized"})
        tools = mc.request("tools/list", {}, timeout=60).get("result", {}).get("tools", [])
        say(f"{OK} MCP          {info.get('name', 'server')}: " + ", ".join(sorted(t["name"] for t in tools)))
        res = mc.request("tools/call", {"name": "creo_status", "arguments": {}}, timeout=120)
        if res.get("result", {}).get("isError") or "error" in res:
            say(f"{BAD} creo_status  {text_of(res) or res.get('error')}")
            bad += 1
        else:
            say(f"{OK} creo_status  {text_of(res)[:300]}")
    except Exception as e:
        say(f"{BAD} MCP          {e}")
        for line in mc.stderr[-15:]:
            say(f"               {line}")
        bad += 1
    finally:
        mc.close()
    say("\nAll good." if not bad else f"\n{bad} problem(s) - see the lines marked {BAD}.")
    return 0 if not bad else 1


# ---------------------------------------------------------------- main
def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="command", required=True)

    f = sub.add_parser("find-creo", help="list Creo installs and check J-Link")
    f.set_defaults(func=cmd_find_creo)

    i = sub.add_parser("install-creoson", help="download, verify and configure CREOSON")
    i.add_argument("--creo-common", help="the 'Common Files' folder of your Creo (default: search)")
    i.add_argument("--port", type=int, default=DEFAULT_PORT, help="CREOSON port (default: 9056)")
    i.add_argument("--creoson-dir", help=f"default: %%LOCALAPPDATA%%\\creoson\\CreosonServer-{CREOSON_VERSION}")
    i.add_argument("--java-home", help="Java for CREOSON (default: the JRE inside the CREOSON zip)")
    i.add_argument("--interactive", action="store_true", help="ask when several Creo installs exist")
    i.add_argument("--dry-run", action="store_true", help="show what would happen, change nothing")
    i.set_defaults(func=cmd_install_creoson)

    s = sub.add_parser("setup", help="register the MCP server in the Claude apps")
    s.add_argument("--targets", default="code,desktop", help="code, desktop or code,desktop")
    s.add_argument("--name", default=SERVER_NAME, help="server name shown in Claude (default: creo)")
    s.add_argument("--allow-destructive", action="store_true",
                   help="also allow delete/erase/close functions (see GUARDED)")
    s.add_argument("--desktop-config", help="the file that Claude Desktop 'Edit Config' opens")
    s.add_argument("--claude-cli", help="path of the Claude Code CLI to use")
    s.add_argument("--interactive", action="store_true", help="ask when the Desktop config is unclear")
    s.add_argument("--remove", action="store_true", help="remove the server instead of adding it")
    s.add_argument("--dry-run", action="store_true", help="show what would change, write nothing")
    s.set_defaults(func=cmd_setup)

    v = sub.add_parser("serve", help="started by the Claude apps (stdio), not by hand")
    v.set_defaults(func=cmd_serve)

    c = sub.add_parser("check", help="end-to-end test while CREOSON and Creo run")
    c.add_argument("--port", type=int, help="CREOSON port (default: from settings)")
    c.set_defaults(func=cmd_check)

    a = ap.parse_args()
    return a.func(a)


if __name__ == "__main__":
    sys.exit(main())
