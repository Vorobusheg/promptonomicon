---
name: design-notebook-workflow
description: Entry point for building or analysing a superconducting-chip design notebook for Andrei (Qiskit Metal drawing + Ansys Q3D/HFSS simulation + tiny_useful_lib analysis, "Sisyphus style"). Use first whenever asked to create, extend, run or optimise a design notebook like Sisyphus_A. Gives the pipeline map, the machine facts, the safety rules, how to run cells with tools/nbrun.py and what to report. Points to the other skills for each step.
---

# Design notebook workflow

Read `Claude/Design_notebooks/Sisyphus_style/sisyphus_style.md` before writing any cell.
It defines what the notebook must look like. This skill defines how to work.

Everything of this skill set is in one folder, `Claude\Design_notebooks\Sisyphus_style\`
(`sisyphus_style.md`, `skills\`, `tools\`, `playground\`). It is used by direct reference
to that folder; it is one of several notebook-style sets Andrei plans to make.

## Facts about this machine

| Thing | Value |
|---|---|
| Workspace root | `C:\Users\akugut\Documents\AndreiK_backup` |
| Project folder for agent files | `Claude\Design_notebooks\` |
| This skill set (style guide, skills, tools) | `Claude\Design_notebooks\Sisyphus_style\` |
| Reference notebook (read-only) | `Projects\GKP_cavity\notebooks\Sisyphus_A.ipynb` |
| Python env | mamba env `metal`, Python 3.12: `C:\Users\akugut\.local\share\mamba\envs\metal\python.exe` (the `miniforge3\envs\metal` folder is a different, empty env: do not use it) |
| Jupyter kernel | `metal` ("Python (metal)") |
| `tiny_useful_lib` (`tul`) | editable install from `Github\quantum-circuits\tiny_useful_lib` |
| `extra_elements`, `extra_rendering` | editable install from `Github\quantum-metal-extension` |
| Ansys | AEDT 2025 R2, `ansys_version=252`, PyAEDT (`ansys.aedt.core`) |
| HFSS template project of Sisyphus | `Projects\GKP_cavity\cavity_simulations_HFSS\Cavity_V1\Sisyphus.aedt` |
| Files of a design | one folder `Projects\<project>\notebooks\<Design>\`: `<Design>.ipynb`, `data\` (`<Design>_<name>_dict.pkl`, `.npz` sweeps), `figs\`, `hfss_shots\` (layout: style guide, cell 1). Not the shared `Projects\<project>\data\` (rule of 2026-11-17) |

## The pipeline

```
inputs: Ej_dict['T'], exp_vars, target f / Ec / g / kappa / chi
   |
   v
Wafer drawing (Metal)            skill: qmetal-chip-drawing
   |
   v   render a subset of components into a template design, solve, clean up
       (the render / JJ sheet / cleanup mechanics: skill aedt-render-cleanup)
Capacitance (Q3D)       -> C matrix -> Ec, pin_q, f01, alpha     skill: q3d-capacitance-ec
Eigenmode, bare         -> f, Q of each resonator alone          skill: hfss-eigenmode-modes
Eigenmode, complete     -> all modes of the full chip (long)     skill: hfss-eigenmode-modes
Qubit BBQ / Reso BBQ    -> g between two systems                 skill: hfss-bbq-coupling
Pin S-parameter         -> f, Qc, Qi, kappa seen from the pin    skill: hfss-pin-sparameter-kappa
   |
   v   numbers stored in f_dict, Q_dict, Qe_dict, Qi_dict, g_dict, Ec_dict, Ej_dict (+ pickle)
Summary / Chi           -> chi, Purcell limits                   skill: design-summary-chi-purcell
   |
   v
compare with targets, change geometry, repeat                    skill: geometry-optimization
```

Library lookup and the rule for new functions: skill `tul-and-extra-elements`.

Dependencies between blocks (run in this order the first time):

* Q3D needs only the drawing and `Ej_dict['T']`.
* Bare eigenmode needs only the drawing. It gives `f_dict['<mode>_bare']`, which the
  BBQ and S-parameter blocks use as solution frequency.
* BBQ to storage needs `f_dict['storage']`. If the complete eigenmode has not been run,
  take the storage frequency from a cheap eigenmode of the empty cavity or from Andrei.
* Summary needs `Ec_dict['Ec_T']`, `Ec_dict['pin_q']`, the `g_dict` entries,
  `f_dict['*_bare']`, `Qe_dict['*_via_pin_S']`.

## Safety rules (hard)

1. **Never modify** `Sisyphus_A.ipynb` or any other notebook, library file or `.pkl` /
   `.npz` that you did not create in this task. To experiment, copy the notebook into
   `Claude\Design_notebooks\` and work on the copy.
2. **Never overwrite result files of another design.** A copy of a notebook must get its
   own `<Design>` prefix or its own `data_path` before any `### Save` cell runs.
   (Sisyphus_A's own `data_path` points to the network drive `B:`. A copy that keeps
   that line overwrites Andrei's real results.)
3. **One AEDT session only.** Before the first cell that touches AEDT, run
   `tools\aedt_check.py --project <Project>`. If it prints two healthy sessions, stop
   and ask Andrei: a healthy session with his work open is his, do not close it.
   Reason: Metal's renderer attaches through COM to the first registered AEDT session,
   not necessarily the one with your project; on 2026-11-13 it pointed at a different
   project that also had a design named `Eigenmode`. A crashed or hung session, or no
   session at all, you fix yourself: section "AEDT crashed or is not running" below.
4. **Andrei's template designs stay as they are; new simulations are yours to add.**
   You may create new designs, setups, sweeps and parametric setups inside the HFSS
   project when the task needs them (section "New simulations in the project" below).
   You may not rename, delete or restructure the designs and setups that were there
   before you, and you do not create a new project file without asking.
5. **Before rendering into a template design, remove the previous render**, and after
   your run remove yours. Use the cleanup cell of the block (skill
   `aedt-render-cleanup`). Never call `fourq_hfss.clean_active_design()`: it deletes
   everything, including the cavity.
6. **Restore every template setting you change** that the notebook does not set
   explicitly itself (number of passes of the eigenmode and Q3D setups, values of
   template variables such as `drift`, `hhh`, `narrow_pin_h`).
7. **Run time budget.** Coarse test runs are free. Ask Andrei before starting any single
   run or sweep that you expect to take more than about 30 minutes, including the final
   fine-mesh verification. Say what you will run, why, and the expected time.
8. Do not edit `tiny_useful_lib` or `extra_elements`. Propose changes instead.

## AEDT crashed or is not running

Andrei's instruction (2026-11-16): solve this yourself, do not hand it back. Reopen the
right project file through the AEDT MCP, using your access to the project folder, then
continue. Tell him afterwards what happened.

How it shows: a cell that talks to AEDT hangs or times out, gRPC/COM calls raise
connection errors, or `aedt_check.py` finds no session. A hung session usually sits
behind the internal-error dialog ("Describe what you were doing when the error
occurred ... Save Data / Cancel"): a window of class `#32770` titled
"Electronics Desktop 2025 R2" that belongs to `ansysedt.exe` and blocks every script
call.

1. **Save nothing.** Do not call `save_project` on a session that misbehaves.
2. Stop the notebook kernel (`nbrun.py stop`): its `hfss` / `fourq_hfss` handles are
   dead.
3. If the crashed `ansysedt.exe` is still there, end that process (`Stop-Process -Id
   <pid>`), and only that one. If a second, healthy session exists it is Andrei's.
4. Look into the project folder. A leftover `<Project>.aedt.lock` with no AEDT process
   behind it is stale: remove it. Leave `<Project>.aedt.auto` and the `.aedtresults`
   folder alone and mention an `.auto` file in your report.
5. Bring AEDT back with the MCP tools, in this order: `check_aedt_installed`,
   `check_aedt_status`, then `launch_aedt(confirm_new_session=True)` if no session is
   left (this section is the confirmation the MCP asks for) or `connect_to_aedt` if one
   is, then `open_project` with the full path of the `.aedt` file (table "Facts about
   this machine"; for another project, the path in the notebook's connect cells).
   Launch with the GUI, not non-graphical: Andrei watches the model, and Metal's
   renderer needs the normal desktop. Never `clear_aedt`.
6. Run `tools\aedt_check.py --project <Project>` until it prints `OK`.
7. The file is in the state of its last save, and AEDT saves at every `analyze`. So
   expect a half-finished render and coarse setup values inside: start a kernel, run
   the two setup cells, the drawing cells and the block's connect cell, then the
   guarded cleanup cell, and write the template setup numbers back (skill
   `aedt-render-cleanup`). Then re-run the block from its connect cell.
8. If the same step crashes AEDT a second time, stop and report: what the cell does,
   the last AEDT messages (`get_pyaedt_logs`), and what you tried.

## New simulations in the project

Andrei's instruction (2026-11-16): the agent is free to create new simulations within
the HFSS project. Use this when no template design fits the question (another port
position, a part of the chip alone, a different solution type), not as a way around
cleaning up a template design.

* **Prefer a copy of the closest template design** (`hfss.duplicate_design('<name>')`,
  or copy/paste of the design): it brings the cavity, the pin, the boundaries and a
  working setup. An empty design (`create_design` of the MCP, or
  `Hfss(project=..., design='<new name>', solution_type=...)`) needs all of that built
  again; do it only when the 3D environment is really different.
* **Name it so the origin is visible:** `<Template>_<purpose>`, for example
  `Eigenmode_no_filter`, `Network_two_ports`. Never reuse or change an existing name.
* New setups and sweeps inside an existing design are allowed too, under a new name
  (`Setup_coarse`, `Sweep_wide`). Andrei's `Setup`, `Auto1`, `Sweep`, `drift_sweep`,
  `heigh_sweep` keep their names and, after your run, their values.
* The notebook block that uses the new design names it in its connect cell
  (`design='Eigenmode_no_filter'`) and gets a one-line markdown note under its heading:
  what the design is, from which template it was copied, what was changed.
* The block still ends with the guarded cleanup cell, so the new design is left as a
  clean environment that can be rendered into again.
* The run time budget (rule 7) applies as everywhere.
* List every design, setup and sweep you created in the final report. Remove those
  that turned out to be dead ends before you finish; keep the ones the notebook uses.

## Running cells: tools/nbrun.py

There are no Jupyter tools in the agent session. `tools\nbrun.py` keeps one kernel alive
and runs chosen cells of the notebook in it; outputs are written into the `.ipynb`.

```powershell
$py  = 'C:\Users\akugut\.local\share\mamba\envs\metal\python.exe'
$dn  = 'C:\Users\akugut\Documents\AndreiK_backup\Claude\Design_notebooks\Sisyphus_style'
$nb  = "<path>\<Design>.ipynb"
$k   = "<scratch folder>\kernel.json"

& $py "$dn\tools\nbrun.py" start --conn $k --cwd "<folder of the notebook>"   # once
& $py "$dn\tools\nbrun.py" list  $nb                                          # index + first line of each cell
& $py "$dn\tools\nbrun.py" exec  $nb --conn $k --cells 1-22 --timeout 300     # run cells, save outputs
& $py "$dn\tools\nbrun.py" code  --conn $k "print(f_dict)"                    # run code that is NOT in the notebook
& $py "$dn\tools\nbrun.py" stop  --conn $k                                    # at the very end
```

* Cell numbers are positions in the file, markdown cells included. Run `list` again
  after you insert or delete a cell.
* Do not edit the notebook file while an `exec` is running: `exec` rewrites the file
  after every cell.
* `exec` stops at the first failing cell (`--keep-going` to continue). It prints the
  text outputs of each cell.
* **Figures do not come back as outputs.** Qiskit Metal switches matplotlib to the Qt
  backend, so `plt.show()` and `pin.plotall()` open windows on Andrei's screen and the
  notebook stores no image (his own notebooks are the same). To see a figure, save it
  right after the cell and close the windows:
  `code --conn $k "plt.figure(plt.get_fignums()[-1]).savefig(r'<folder>\<name>.png', dpi=100); plt.close('all')"`,
  then read the PNG. Save the figures that matter for the report into
  `<Design>\figs\` (the design folder) and name them in the report. Always
  `plt.close('all')` afterwards, or dozens of windows pile up on his desktop.
* A solve that may take longer than the shell limit: start `exec` in the background with
  a large `--timeout`. If the shell is killed anyway, the kernel keeps solving; wait with
  `code --conn $k "1"`, which returns when the kernel is free, then re-run the extract
  cell. The output of the interrupted analyze cell is then missing in the notebook:
  say so in the report or re-run it.
* Use `code` for everything diagnostic (object lists, `hfss.validate_simple()`, AEDT
  messages, intermediate prints, saving a picture of the drawing). Diagnostics do not
  belong in notebook cells.
* `MetalGUI` opens a real window on Andrei's screen. That is expected. Leave it open
  while the kernel lives.
* Add `| Where-Object { $_ -notmatch '^PyAEDT INFO' }` to keep the log readable.

Writing cells: create and edit the `.ipynb` with the notebook editing tool or with a
short `nbformat` script. One logical step per cell, as in the style guide.

## Order of work

1. **Clarify the task.** You need: the element list (transmon, which resonators, which
   pin), the HFSS template project and which design is for what, `Ej`, and targets with
   tolerances. Ask for anything missing in one batch.
2. **Create the notebook** `<Design>.ipynb` in its own design folder (default
   `Projects\<project>\notebooks\<Design>\`, with `data\`, `figs\`, `hfss_shots\` inside),
   with the skeleton from the style guide.
3. **Start the kernel, run setup and drawing cells, look at the picture**
   (skill `qmetal-chip-drawing`). Fix geometry before any simulation.
4. **Pre-flight** `aedt_check.py`, then simulation blocks in pipeline order with
   coarse settings. After each block: read the numbers, compare with expectation, run
   the cleanup cell, run `### Save`.
5. **Optimise** (skill `geometry-optimization`) if targets are given.
6. **Final pass:** production mesh and pass settings in the cells (coarse values removed
   or moved to the trailing comment), ask before long runs, run, save.
7. **Finish:** run Summary; check that no rendered object is left in any template
   design you touched and that the setups carry the template values; save the project
   once (skill `aedt-render-cleanup`, "Live values and saved values"); `nbrun stop`;
   run `aedt_check.py` a last time; write the report.

## Typical run times (Sisyphus_A, fine settings, this workstation)

| Block | Fine settings | Time | Coarse test (2026-11-13) |
|---|---|---|---|
| Q3D capacitance, transmon only | PerError 0.1 %, up to 20 passes | 5 min | 48 s (PerError 2 %, 6 passes): `Ec` equal to 3 digits, `pin_q` 30 % off |
| Eigenmode, bare readout | trace mesh 10 um | 30 min | not run |
| Eigenmode, bare filter | trace mesh 5 um | 2 h 12 min | 17 s (100 um, 4 passes): f 1 % low, Q 12 % high |
| Eigenmode, complete chip, 5 modes | meshes 10-30 um | 10 h 44 min | never as a test |
| Qubit BBQ to storage (transmon only) | 20 passes, 30 um | 2 min + 1 min fit | 45 s + 1.5 min fit (4 passes, 100 um): `g` 2 % high |
| Qubit BBQ to readout | 6 passes | 34 min | not run |
| Qubit BBQ to filter | 20 passes | 7 min | not run |
| Reso BBQ | 5 passes | 5-7 min | not run |
| Pin S-parameter, filter | 20 passes, 30 um | 19 min | 92 s (5 passes, 100 um): `Qc` 1.5 % low, f 2 % low |
| Pin S-parameter, readout | 5 passes | 6 min | not run |
| 51-point template-variable sweep | | 3-5.5 h | never without asking |

"Not run" rows: no coarse timing was measured; expect minutes, and treat the first run
as the measurement.

## Report to Andrei when done

Lead with the result. Then, briefly:

* table of the headline numbers (f01, alpha, Ec, mode frequencies, g, kappa/Qc, chi,
  Purcell limits) with units, next to the targets;
* which numbers come from coarse runs and which from converged runs;
* every geometry change you made, old value and new value;
* every new function or component you proposed (style guide, section 7);
* anything that failed, was skipped, or looked wrong, with the AEDT message;
* confirmation that the template designs are clean and the changed settings restored;
* every design, setup or sweep you created in the HFSS project, and every AEDT crash
  with what you did to recover.
