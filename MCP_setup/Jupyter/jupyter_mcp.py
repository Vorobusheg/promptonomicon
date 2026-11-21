r"""Jupyter MCP helper for Claude Desktop and Claude Code. Standard library only.

One file, three commands. Run it with the Python of the bridge env "jupyter-mcp".

  setup    creates the token file, copies this file to the runtime folder and
           registers the MCP server in Claude Code and/or Claude Desktop
  bridge   started by the Claude apps, never by hand: reads the token file and
           runs jupyter-mcp-server on stdio with that token
  check    end-to-end test after JupyterLab is running: port, token, kernels,
           collaboration, and an MCP handshake through the bridge

Runtime folder, private to your Windows user and not synced:
  %LOCALAPPDATA%\jupyter-mcp\token.txt         the shared secret (nothing else stores it)
  %LOCALAPPDATA%\jupyter-mcp\jupyter_mcp.py    the copy that the Claude apps start

Examples (normally setup_jupyter_mcp.bat runs the first one):
  python jupyter_mcp.py setup --targets code,desktop --interactive
  python jupyter_mcp.py setup --targets code,desktop --dry-run
  python jupyter_mcp.py setup --new-token      new secret; restart JupyterLab and the Claude apps
  python jupyter_mcp.py setup --targets code,desktop --remove
  python jupyter_mcp.py check
A second server for a remote JupyterLab reached through an SSH tunnel on local port 8889:
  python jupyter_mcp.py setup --name jupyter-server --port 8889 --token-file "%LOCALAPPDATA%\jupyter-mcp\token-server.txt" --targets code,desktop
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import platform
import queue
import re
import secrets
import shutil
import socket
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

SERVER_NAME = "jupyter"
DEFAULT_PORT = 8888
CONSOLE_SCRIPT = "jupyter-mcp-server"
CONFIG_NAME = "claude_desktop_config.json"
WINDOWS = os.name == "nt"
OK, BAD, SKIP = "[ok]", "[!!]", "[--]"


def say(text: str = "") -> None:
    print(text, flush=True)


def warn(text: str) -> None:
    print(text, file=sys.stderr, flush=True)


# ---------------------------------------------------------------- paths and token
def runtime_dir() -> Path:
    if os.environ.get("JUPYTER_MCP_HOME"):  # used by tests
        return Path(os.environ["JUPYTER_MCP_HOME"])
    if WINDOWS:
        base = os.environ.get("LOCALAPPDATA") or str(Path.home() / "AppData" / "Local")
        return Path(base) / "jupyter-mcp"
    return Path.home() / ".local" / "share" / "jupyter-mcp"


def read_token(path: Path) -> str:
    return path.read_text(encoding="utf-8-sig").strip()


def ensure_token(path: Path, new: bool, dry: bool) -> str:
    """Create the token file once; keep it on later runs unless new=True."""
    if path.is_file() and not new and read_token(path):
        return "kept"
    if dry:
        return "would be created"
    path.parent.mkdir(parents=True, exist_ok=True)
    existed = path.is_file()
    path.write_text(secrets.token_hex(24), encoding="utf-8")  # 48 hex chars, no newline
    if not WINDOWS:
        os.chmod(path, 0o600)
    return "replaced" if existed else "created"


def server_entry_point():
    """The console script 'jupyter-mcp-server' of the interpreter running this file."""
    from importlib.metadata import entry_points
    for ep in entry_points(group="console_scripts"):
        if ep.name == CONSOLE_SCRIPT:
            return ep
    return None


def host_port(url: str) -> tuple[str, int]:
    u = urllib.parse.urlparse(url)
    return u.hostname or "127.0.0.1", u.port or (443 if u.scheme == "https" else 80)


def port_open(url: str, timeout: float = 1.0) -> bool:
    try:
        with socket.create_connection(host_port(url), timeout=timeout):
            return True
    except OSError:
        return False


def server_env(url: str, exec_timeout: int | None = None) -> dict:
    """Settings of jupyter-mcp-server, passed as environment variables (no secrets here)."""
    env = {"JUPYTER_URL": url,
           "ALLOW_IMG_OUTPUT": "true",         # plots come back as images
           "OPEN_NOTEBOOK_IN_UI": "true",      # the notebook Claude uses opens in your JupyterLab tab
           "START_NEW_CODE_SANDBOX": "false"}  # default true leaves one idle kernel per bridge start
    if exec_timeout:
        env["JUPYTER_MCP_EXECUTION_TIMEOUT"] = str(exec_timeout)  # server default: 120 s
    return env


# ---------------------------------------------------------------- bridge (started by Claude)
def cmd_bridge(a: argparse.Namespace) -> int:
    """Runs on the stdio pipes of the Claude app: never print to stdout here."""
    token_file = Path(a.token_file) if a.token_file else runtime_dir() / "token.txt"
    try:
        token = read_token(token_file)
    except OSError as e:
        warn(f"[jupyter-mcp] cannot read the token file {token_file}: {e}. Run setup_jupyter_mcp.bat.")
        return 1
    if not token:
        warn(f"[jupyter-mcp] the token file {token_file} is empty. Run setup_jupyter_mcp.bat.")
        return 1
    url = os.environ.get("JUPYTER_URL", f"http://127.0.0.1:{DEFAULT_PORT}")
    if not port_open(url):
        warn(f"[jupyter-mcp] nothing answers at {url} yet - start JupyterLab with start_jupyterlab.bat.")
    ep = server_entry_point()
    if ep is None:
        warn(f"[jupyter-mcp] {sys.executable} has no '{CONSOLE_SCRIPT}'. Run setup_jupyter_mcp.bat.")
        return 1
    os.environ["JUPYTER_TOKEN"] = token  # only this process and its children see it
    sys.argv = [CONSOLE_SCRIPT]
    ep.load()()  # the same call the jupyter-mcp-server.exe launcher makes
    return 0


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
def cmd_setup(a: argparse.Namespace) -> int:
    targets = {t.strip().lower() for t in a.targets.split(",") if t.strip()}
    unknown = targets - {"code", "desktop"}
    if unknown or not targets:
        say(f"{BAD} --targets takes code, desktop or code,desktop (got: {a.targets})")
        return 2
    rt = runtime_dir()
    token_file = Path(a.token_file).expanduser() if a.token_file else rt / "token.txt"
    script_copy = rt / "jupyter_mcp.py"
    url = a.url or f"http://127.0.0.1:{a.port}"
    entry = None
    if not a.remove:
        if server_entry_point() is None:
            say(f"{BAD} {sys.executable} has no '{CONSOLE_SCRIPT}'.\n"
                "    Run this file with the Python of the bridge env, as setup_jupyter_mcp.bat does.")
            return 1
        say(f"Bridge Python : {sys.executable}")
        say(f"JupyterLab URL: {url}")
        say(f"Token file    : {token_file}  ({ensure_token(token_file, a.new_token, a.dry_run)})")
        here = Path(__file__).resolve()
        if not a.dry_run and here != script_copy.resolve():
            rt.mkdir(parents=True, exist_ok=True)
            shutil.copy2(here, script_copy)
        say(f"Started by app: {script_copy}")
        entry = {"command": sys.executable,
                 "args": ["-I", str(script_copy), "bridge", "--token-file", str(token_file)],
                 "env": server_env(url, a.exec_timeout)}
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
    if entry is not None and not a.dry_run:
        say("\nNext: start JupyterLab with start_jupyterlab.bat, then test the whole chain with")
        say(f'  "{sys.executable}" "{script_copy}" check' + (f" --port {a.port}" if a.port != DEFAULT_PORT else ""))
    return 0 if ok else 1


# ---------------------------------------------------------------- check
class StdioClient:
    """Minimal MCP client: newline-delimited JSON-RPC over the bridge's stdin/stdout."""

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
                raise RuntimeError("the bridge exited")
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


def http_get(url: str, token: str | None, timeout: float = 10) -> tuple[int, str]:
    req = urllib.request.Request(url)
    if token:
        req.add_header("Authorization", f"token {token}")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.status, r.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as e:
        return e.code, ""


def text_of(result: dict) -> str:
    parts = result.get("result", {}).get("content", [])
    return "\n".join(p.get("text", "") for p in parts if p.get("type") == "text").strip()


def cmd_check(a: argparse.Namespace) -> int:
    rt = runtime_dir()
    token_file = Path(a.token_file).expanduser() if a.token_file else rt / "token.txt"
    url = (a.url or f"http://127.0.0.1:{a.port}").rstrip("/")
    bad = 0
    say(f"Checking {url}\n")
    try:
        token = read_token(token_file)
        say(f"{OK} token file   {token_file}")
    except OSError:
        say(f"{BAD} token file   missing: {token_file} - run setup_jupyter_mcp.bat")
        return 1
    if not port_open(url):
        say(f"{BAD} JupyterLab   nothing answers at {url} - start start_jupyterlab.bat")
        return 1
    say(f"{OK} JupyterLab   answers at {url}")
    no_tok, _ = http_get(f"{url}/api/status", None)
    with_tok, body = http_get(f"{url}/api/status", token)
    if with_tok == 200 and no_tok in (401, 403):
        say(f"{OK} token        accepted; a request without it gets {no_tok}")
    elif with_tok == 200:
        say(f"{BAD} token        accepted, but a request WITHOUT a token also passes ({no_tok}): auth is off")
        bad += 1
    else:
        say(f"{BAD} token        refused ({with_tok}): JupyterLab runs with another token.\n"
            "               Stop it and start it again with start_jupyterlab.bat.")
        return 1
    code, body = http_get(f"{url}/api/kernelspecs", token)
    if code == 200:
        specs = json.loads(body).get("kernelspecs", {})
        say(f"{OK} kernels      {len(specs)} available - this is where the agent's code runs:")
        for name, spec in sorted(specs.items()):
            argv = spec.get("spec", {}).get("argv", ["?"])
            where = "the JupyterLab env itself" if argv[0] in ("python", "python3") else argv[0]
            say(f"               {name:<14} {spec.get('spec', {}).get('display_name', '')}  ->  {where}")
    code, _ = http_get(f"{url}/api/collaboration/session/__probe__.ipynb", token)
    if code == 404:
        say(f"{BAD} collaboration not installed in the JupyterLab env: edits will not appear live")
        bad += 1
    else:
        say(f"{OK} collaboration real-time sync is on")
    say(f"{SKIP} MCP          starting the bridge the way the Claude apps do ...")
    env = dict(os.environ, **server_env(url))
    cmd = [sys.executable, "-I", str(Path(__file__).resolve()), "bridge", "--token-file", str(token_file)]
    client = StdioClient(cmd, env)
    try:
        init = client.request("initialize", {
            "protocolVersion": "2025-06-18", "capabilities": {},
            "clientInfo": {"name": "jupyter-mcp-check", "version": "1"}}, timeout=90)
        info = init.get("result", {}).get("serverInfo", {})
        client.send({"jsonrpc": "2.0", "method": "notifications/initialized"})
        tools = client.request("tools/list", {}, timeout=60).get("result", {}).get("tools", [])
        names = sorted(t["name"] for t in tools)
        say(f"{OK} MCP          {info.get('name', 'server')} {info.get('version', '')}: {len(names)} tools")
        for i in range(0, len(names), 4):
            say("               " + ", ".join(names[i:i + 4]))
        res = client.request("tools/call", {"name": "list_kernels", "arguments": {}}, timeout=60)
        if res.get("result", {}).get("isError") or "error" in res:
            say(f"{BAD} bridge->Lab  list_kernels failed: {text_of(res) or res.get('error')}")
            bad += 1
        else:
            say(f"{OK} bridge->Lab  list_kernels answered through the token")
    except Exception as e:
        say(f"{BAD} MCP          {e}")
        for line in client.stderr[-15:]:
            say(f"               {line}")
        bad += 1
    finally:
        client.close()
    say("\nAll good." if not bad else f"\n{bad} problem(s) - see the lines marked {BAD}.")
    return 0 if not bad else 1


# ---------------------------------------------------------------- main
def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="command", required=True)

    s = sub.add_parser("setup", help="token file + registration in the Claude apps")
    s.add_argument("--targets", default="code,desktop", help="code, desktop or code,desktop")
    s.add_argument("--name", default=SERVER_NAME, help="server name shown in Claude (default: jupyter)")
    s.add_argument("--port", type=int, default=DEFAULT_PORT, help="JupyterLab port (default: 8888)")
    s.add_argument("--url", help="full JupyterLab URL instead of --port")
    s.add_argument("--token-file", help="default: %%LOCALAPPDATA%%\\jupyter-mcp\\token.txt")
    s.add_argument("--new-token", action="store_true", help="replace the secret with a new one")
    s.add_argument("--exec-timeout", type=int, help="default seconds per code run (server default: 120)")
    s.add_argument("--desktop-config", help="the file that Claude Desktop 'Edit Config' opens")
    s.add_argument("--claude-cli", help="path of the Claude Code CLI to use")
    s.add_argument("--interactive", action="store_true", help="ask when the Desktop config is unclear")
    s.add_argument("--remove", action="store_true", help="remove the server instead of adding it")
    s.add_argument("--dry-run", action="store_true", help="show what would change, write nothing")
    s.set_defaults(func=cmd_setup)

    b = sub.add_parser("bridge", help="started by the Claude apps (stdio), not by hand")
    b.add_argument("--token-file")
    b.set_defaults(func=cmd_bridge)

    c = sub.add_parser("check", help="end-to-end test while JupyterLab runs")
    c.add_argument("--port", type=int, default=DEFAULT_PORT)
    c.add_argument("--url")
    c.add_argument("--token-file")
    c.set_defaults(func=cmd_check)

    a = ap.parse_args()
    return a.func(a)


if __name__ == "__main__":
    sys.exit(main())
