r"""nbrun - run chosen cells of a Jupyter notebook in one persistent kernel, from a terminal.

For agents that have no Jupyter MCP tools in the session. The kernel stays alive between
calls, so the Metal design, the dictionaries and the AEDT connection survive from cell to
cell, exactly as in an interactive notebook. Outputs are written back into the .ipynb.

Run it with the Python of the "metal" env:
    C:\Users\akugut\.local\share\mamba\envs\metal\python.exe tools\nbrun.py <command> ...

Commands
    start  --conn K.json [--cwd DIR]             start a kernel (same Python as this script)
    list   NB.ipynb                              index, type and first line of every cell
    exec   NB.ipynb --conn K.json --cells 0-7,9  run code cells, save outputs in the notebook
           [--timeout 600] [--keep-going] [--figs DIR] [--limit 3000]
    code   --conn K.json "print(design.components.keys())"    run code that is NOT in the notebook
           [--timeout 600] [--limit 3000]
    stop   --conn K.json                         shut the kernel down

Notes
    * exec saves the notebook after every cell. Close the notebook tab in VS Code first, or
      reload it from disk afterwards.
    * png outputs are also saved to --figs (default: <notebook>_figs) as cell<idx>_<n>.png.
      That only happens with an inline matplotlib backend. Qiskit Metal switches the kernel
      to the Qt backend: figures then open as windows and no png comes back. To look at one:
          code --conn K.json "plt.figure(plt.get_fignums()[-1]).savefig(r'C:\...\fit.png'); plt.close('all')"
    * A cell that runs longer than --timeout is NOT interrupted: the kernel keeps working.
      Wait and collect later with:  code --conn K.json "1"   (returns when the kernel is free).
"""
from __future__ import annotations

import argparse
import base64
import json
import os
import re
import subprocess
import sys
import time
from pathlib import Path
from queue import Empty

import nbformat
from jupyter_client import BlockingKernelClient
from jupyter_client.connect import write_connection_file

ANSI = re.compile(r"\x1b\[[0-9;]*[A-Za-z]")


def client(conn: str) -> BlockingKernelClient:
    kc = BlockingKernelClient(connection_file=conn)
    kc.load_connection_file()
    kc.start_channels()
    kc.wait_for_ready(timeout=60)
    return kc


def run(kc: BlockingKernelClient, code: str, timeout: float):
    """Execute code; return (outputs as nbformat nodes, execution_count, status)."""
    msg_id = kc.execute(code, store_history=True, allow_stdin=False)
    outs, count, status = [], None, "timeout"
    deadline = time.monotonic() + timeout
    while True:
        left = deadline - time.monotonic()
        if left <= 0:
            break
        try:
            msg = kc.get_iopub_msg(timeout=min(left, 5))
        except Empty:
            continue
        if msg["parent_header"].get("msg_id") != msg_id:
            continue
        t, c = msg["msg_type"], msg["content"]
        if t == "status" and c["execution_state"] == "idle":
            status = "ok" if status == "timeout" else status
            break
        if t == "execute_input":
            count = c["execution_count"]
        elif t == "stream":
            if outs and outs[-1]["output_type"] == "stream" and outs[-1]["name"] == c["name"]:
                outs[-1]["text"] += c["text"]
            else:
                outs.append(nbformat.v4.new_output("stream", name=c["name"], text=c["text"]))
        elif t in ("display_data", "execute_result"):
            kw = dict(data=c["data"], metadata=c.get("metadata", {}))
            if t == "execute_result":
                kw["execution_count"] = c["execution_count"]
            outs.append(nbformat.v4.new_output(t, **kw))
        elif t == "error":
            status = "error"
            outs.append(nbformat.v4.new_output("error", ename=c["ename"], evalue=c["evalue"],
                                               traceback=c["traceback"]))
    return outs, count, status


def show(outs, idx, figs: Path | None, limit=3000):
    n_fig = 0
    for o in outs:
        if o["output_type"] == "stream":
            text = o["text"]
        elif o["output_type"] == "error":
            text = ANSI.sub("", "\n".join(o["traceback"]))
        else:
            text = o["data"].get("text/plain", "")
            if "image/png" in o["data"] and figs is not None:
                figs.mkdir(parents=True, exist_ok=True)
                p = figs / f"cell{idx}_{n_fig}.png"
                p.write_bytes(base64.b64decode(o["data"]["image/png"]))
                text += f"   [png saved: {p}]"
                n_fig += 1
        if len(text) > limit:
            text = text[:limit // 2] + f"\n ... [{len(text) - limit} chars cut] ...\n" + text[-limit // 2:]
        print(text.rstrip())


def parse_cells(spec: str, n: int) -> list[int]:
    out = []
    for part in spec.split(","):
        if "-" in part:
            a, b = part.split("-")
            out += list(range(int(a), int(b) + 1))
        else:
            out.append(int(part))
    return [i for i in out if 0 <= i < n]


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("start"); s.add_argument("--conn", required=True); s.add_argument("--cwd")
    s = sub.add_parser("list"); s.add_argument("nb")
    s = sub.add_parser("exec"); s.add_argument("nb"); s.add_argument("--conn", required=True)
    s.add_argument("--cells", required=True); s.add_argument("--timeout", type=float, default=600)
    s.add_argument("--keep-going", action="store_true"); s.add_argument("--figs")
    s.add_argument("--limit", type=int, default=3000, help="max characters printed per output")
    s = sub.add_parser("code"); s.add_argument("--conn", required=True); s.add_argument("source")
    s.add_argument("--timeout", type=float, default=600)
    s.add_argument("--limit", type=int, default=3000, help="max characters printed per output")
    s = sub.add_parser("stop"); s.add_argument("--conn", required=True)
    a = ap.parse_args()

    if a.cmd == "start":
        conn = str(Path(a.conn).resolve())
        write_connection_file(conn, ip="127.0.0.1")
        flags = 0x00000008 | 0x00000200 if os.name == "nt" else 0  # DETACHED_PROCESS | NEW_PROCESS_GROUP
        p = subprocess.Popen([sys.executable, "-Xfrozen_modules=off", "-m", "ipykernel_launcher", "-f", conn],
                             cwd=a.cwd or os.getcwd(), creationflags=flags,
                             stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        kc = client(conn)
        kc.stop_channels()
        print(f"kernel ready, pid {p.pid}, connection file {conn}")
        return 0

    if a.cmd == "list":
        nb = nbformat.read(a.nb, as_version=4)
        for i, c in enumerate(nb.cells):
            first = next((l for l in c.source.splitlines() if l.strip()), "")
            print(f"{i:>4} {c.cell_type[:4]} {first[:110]}")
        return 0

    if a.cmd == "stop":
        kc = client(a.conn)
        kc.shutdown()
        kc.stop_channels()
        print("kernel shut down")
        return 0

    kc = client(a.conn)
    try:
        if a.cmd == "code":
            outs, _, status = run(kc, a.source, a.timeout)
            show(outs, "x", None, a.limit)
            print(f"[{status}]")
            return 0 if status == "ok" else 1

        nb_path = Path(a.nb)
        figs = Path(a.figs) if a.figs else nb_path.with_name(nb_path.stem + "_figs")
        nb = nbformat.read(nb_path, as_version=4)
        for i in parse_cells(a.cells, len(nb.cells)):
            cell = nb.cells[i]
            if cell.cell_type != "code" or not cell.source.strip():
                continue
            t0 = time.monotonic()
            outs, count, status = run(kc, cell.source, a.timeout)
            cell.outputs, cell.execution_count = outs, count
            nbformat.write(nb, nb_path)
            print(f"\n===== cell {i} [{status}] {time.monotonic() - t0:.1f} s")
            show(outs, i, figs, a.limit)
            if status != "ok" and not a.keep_going:
                return 1
        return 0
    finally:
        kc.stop_channels()


if __name__ == "__main__":
    sys.exit(main())
