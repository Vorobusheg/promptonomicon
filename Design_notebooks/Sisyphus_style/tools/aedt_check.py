r"""aedt_check - read-only pre-flight check before any notebook cell touches AEDT.

Why: a design notebook talks to AEDT through two channels.
    PyAEDT   (Hfss(...), Q3d(...))              -> gRPC, finds a session by itself
    Metal    (design.renderers.hfss.start())    -> COM, attaches to the FIRST registered session
With two AEDT sessions open, the two channels can end up in different sessions, and Metal
renders the chip into whatever project is active there. This script shows where COM points.

Run with the Python of the "metal" env:
    C:\Users\akugut\.local\share\mamba\envs\metal\python.exe tools\aedt_check.py --project Sisyphus

Exit code 0 only if exactly one AEDT session runs and COM sees the expected project in it.
It changes nothing in AEDT.
"""
import argparse
import sys

import psutil
import pythoncom
import win32com.client


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--project", help="project name that must be open, e.g. Sisyphus")
    a = ap.parse_args()

    procs = [p for p in psutil.process_iter(["pid", "name", "cmdline", "create_time"])
             if (p.info["name"] or "").lower() == "ansysedt.exe"]
    print(f"AEDT sessions running: {len(procs)}")
    for p in procs:
        print(f"   pid {p.info['pid']}: {' '.join(p.info['cmdline'] or [])}")
    if not procs:
        print("FAIL: AEDT is not running. Ask the user to open the project in AEDT.")
        return 1

    pythoncom.CoInitialize()
    try:
        app = win32com.client.Dispatch("AnsoftHfss.HfssScriptInterface")  # the ProgID pyEPR / Metal use
        desktop = app.GetAppDesktop()
        com_pid = desktop.GetProcessID()
        projects = list(desktop.GetProjectList())
        active = desktop.GetActiveProject()
        active_name = active.GetName() if active else None
        designs = [d.GetName() for d in active.GetDesigns()] if active else []
        del active, desktop, app
    finally:
        pythoncom.CoUninitialize()

    print(f"COM (Metal renderer) attaches to pid {com_pid}")
    print(f"   open projects : {projects}")
    print(f"   active project: {active_name}")
    print(f"   its designs   : {designs}")

    ok = True
    if len(procs) != 1:
        print("FAIL: more than one AEDT session. Do not render. Ask the user which one to close.")
        ok = False
    if a.project and a.project not in projects:
        print(f"FAIL: project {a.project!r} is not open in the session COM attaches to.")
        ok = False
    print("OK" if ok else "NOT OK")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
