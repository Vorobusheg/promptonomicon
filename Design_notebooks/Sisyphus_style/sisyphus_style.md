# Sisyphus style: how to write a design notebook for Andrei

This is the style codex for Jupyter notebooks that draw a superconducting chip in
Qiskit Metal (`qiskit_metal` + `extra_elements`), simulate pieces of it in Ansys
(Q3D and HFSS through PyAEDT) and turn the results into circuit parameters with
`tiny_useful_lib` (`tul`).

The reference is `Projects/GKP_cavity/notebooks/Sisyphus_A.ipynb`. **Never edit that
file.** Read it when in doubt; a new notebook should look as if Andrei wrote it.

The how-to for each step is in `skills/*/SKILL.md` (start with
`skills/design-notebook-workflow`). This file only says what the result must look like.

## 1. The three rules that matter most

1. **Reuse, do not write.** Physics and conversions come from `tul`, geometry from
   `qiskit_metal.qlibrary` and `extra_elements`, fits from `resonator_tools` and the
   three helper functions already in Sisyphus_A (section 6). A new function is a last
   resort and must be announced (section 7).
2. **Every simulation block is self-contained.** It connects to AEDT, renders only the
   components it needs into a template design, solves, reads the result, stores numbers
   in a dictionary, deletes what it rendered and releases AEDT. After the setup and
   drawing cells have run, any block can be run alone, in any order.
3. **Numbers live in dictionaries, dictionaries live on disk.** Every result that a
   later cell needs goes into `f_dict`, `Q_dict`, `Qe_dict`, `Qi_dict`, `g_dict`,
   `Ec_dict` or `Ej_dict`, and each `##` section ends with a `### Save` cell. The
   Summary section reads only from the dictionaries, never from live simulation
   variables.

## 2. Notebook skeleton

Headers are the only markdown in the notebook. No prose cells (one exception: the
announcement of a new function, section 7).

```
(cell)  magics + imports + paths
(cell)  exp_vars + result dictionaries + load
## Wafer drawing
        layers / GUI init / chip parameters / delete_all_components
### Transmon
### Read reso
### Purcell reso            (one ### per element group; each followed by gui.rebuild())
# HFSS simulations
## Capacitance (Q3D)        -> Ec, pin_q, f01, alpha
## Eigenmode
### Bare readout reso       -> f, Q of one resonator alone
### Bare filter reso
#### Pin variation          (optional parametric sweeps of a template variable)
### Complete                -> all modes of the full chip
### Save
## Qubit BBQ (Y-port at qubit)
### To storage / To readout / To filter     -> g between transmon and each mode
### Save
## Reso BBQ (Y-port at read reso)
### To storage / To filter                  -> g between resonators
### Save
## Pin S-parameter
### Filter / Readout / Transmon / Complete  -> f, Qc, Qi, kappa seen from the pin
### Save
# Summary
## Chi
### Filter / Read / Storage                 -> chi and Purcell limits from the dictionaries
```

Keep this order and these header names. Drop a section that the design does not need;
add a new `##` only for a new kind of simulation. `Sisyphus_B` and `Sisyphus_C` are
shorter notebooks with the same skeleton.

## 3. The two setup cells

Cell 1, in this order: magics, standard libraries, PyAEDT, fit tools, paths, `tul`,
Metal, Metal components, `extra_elements`, logging.

```python
%load_ext autoreload
%autoreload 2
%load_ext autotime

import os
import sys
import logging
import pandas as pd
from IPython.display import display
import pickle
import matplotlib.pyplot as plt
import numpy as np
import scipy as scp
import tqdm
from ansys.aedt.core import Hfss
from ansys.aedt.core import Q3d
from ansys.aedt.core import generic
ansys_version=252
import numdifftools as nd
from resonator_tools import circuit as rfit

# folder path: everything of this design lives in its own folder
system = "C:/Users/akugut/Documents/AndreiK_backup/"
design_path = system+"Projects/<project>/notebooks/<Design>/"
data_path = design_path+"data/"
figs_path = design_path+"figs/"
shots_path = design_path+"hfss_shots/"
gds_path = design_path+"gds/"
for path in [data_path, figs_path, shots_path]: os.makedirs(path, exist_ok=True)

import tiny_useful_lib as tul
import qiskit_metal as metal

from qiskit_metal import designs, draw
from qiskit_metal import MetalGUI, Dict, open_docs

from qiskit_metal.qlibrary.tlines.meandered import RouteMeander
...
from extra_elements.jjs import Taper
...

# turn off INFO output
logging.disable(logging.INFO)
```

* `system` is the machine root. New notebooks use the local `AndreiK_backup` folder
  (Andrei's decision, 2026-11-13). Sisyphus_A itself still points to `B:/...`; do not
  copy that line.
* **One folder per design** (Andrei's rule, 2026-11-17): everything that belongs to the
  notebook is in `Projects\<project>\notebooks\<Design>\`:

  ```
  <Design>\
      <Design>.ipynb
      data\         dictionaries <Design>_<name>_dict.pkl and sweeps <Design>_<name>.npz
      figs\         result plots saved from the notebook (fits, widget figures, animations)
      hfss_shots\   screenshots of the HFSS model (section "Screenshots of the HFSS model")
      gds\          layout exports, only if the notebook writes any
      <Design>_templates.py   how the AEDT template designs were made, if the agent made them
  ```

  Nothing of a design goes into the shared `Projects\<project>\data\` any more. Files keep
  their `<Design>_` prefix inside the folder, so a copied file still says where it is from.
  The `.aedt` projects stay where they are (shared by several designs).
* Import only the components the notebook uses.
* `%load_ext autotime` stays: the `time: ...` line under each cell is how Andrei sees
  how long a simulation took.

Cell 2: experimental constants, empty dictionaries, then the load block.

```python
# setup experimental variables
exp_vars = {}
exp_vars.update({'fudge_factor' : 1/(1 - 0.004)})
exp_vars.update({'cpw_c_fF/mm' : 169.4})
exp_vars.update({'Ej_to_S' : 400})
exp_vars.update({'evaporation_shift' : 1})
exp_vars.update({'undercut' : 0.2})

# other parameters dicts
Ej_dict = {}
Ej_dict.update({'T' : 24})
Ec_dict = {}
g_dict = {}
Qe_dict = {}
Qi_dict = {}
Q_dict = {}
f_dict = {}

# load
with open(data_path + '<Design>_f_dict.pkl', 'rb') as f: f_dict = pickle.load(f)
...
```

* `Ej_dict['T']` (GHz) is a design **input**, the target Josephson energy. Everything
  that needs the junction (`tul.L_of_El`, `tul.C_of_Ej`, the JJ width in the drawing)
  reads it from there.
* One file per dictionary: `<Design>_<name>_dict.pkl`, for example
  `Sisyphus_A_f_dict.pkl`. One `with open(...)` line per dictionary, written out, no loop.
* In a brand-new notebook the files do not exist yet: keep the `# load` lines commented
  out until the first `### Save` cell has run, then uncomment them. Loading must come
  after the initialisation, so that a loaded dictionary replaces the empty one.
* Constants that describe fabrication or the experiment go into `exp_vars`, never
  inline as bare numbers.

## 4. Drawing cells

```python
# define layers
reso_layer = 1
patch_layer = 2
JJ_layer = 3
undercut_layer = 4
```
```python
# metal GUI initialization
design = metal.designs.DesignPlanar()
gui = metal.MetalGUI(design)
design.overwrite_enabled = True
```
```python
# setup basic chip parameters
design._variables = {'cpw_width':'50um', 'cpw_gap':'10um', 'fudge_factor': 1/(1 - 0.04),}
chip_x = 2500
chip_y = 18800
design.chips.main.size.size_x = f'{chip_x}um'
design.chips.main.size.size_y = f'{chip_y}um'
design.chips.main.size.size_z = '-500um'
design.chips.main.size.center_y = '-1.75mm'
design.chips.main
```
```python
design.delete_all_components()
```

Then one `###` per element group. Inside a group:

* Free parameters first, as plain variables at the top of the cell: positions as
  strings with units (`T_x = f'{0}um'`), sizes as numbers with the unit in the name
  (`pad_R_mm = 0.3`, `pad_gap_mm = 2.2`). Derived geometry (for example the chord where
  a taper meets a circular pad) is computed right below, with a one-line comment.
* One constructor call per component, `options=dict(...)` with **one option per line**.
  Values are f-strings with units built from the variables above:
  `pad_gap = f'{pad_gap_mm}mm'`. Use design variables by name where they exist
  (`width_in='cpw_width'`).
* Component names are short and lower-case with a role suffix: `T`, `taper_p1`,
  `taper_j1`, `patch_1`, `jj`, `read_reso`, `read_reso_pad_A`, `filter_reso`,
  `filter_reso_pad_B`. The names matter: HFSS objects are called
  `<qgeometry name>_<component name>` (`trace_read_reso`, `pad_top_T`,
  `taper_main_taper_p1`) and the simulation cells refer to them.
* A separate cell with only `gui.rebuild()` after each group.
* A value that carries an experimental correction keeps the nominal number visible:
  `total_length=f'{3.5}mm' + '+0.34mm'` with the comment
  `# including experimental frequency shift`.
* The old value stays as a trailing comment when a number was tuned:
  `R = 0.7#0.8`, `# length_cut_taper='14um'`.

## 5. Simulation blocks

Every `###` simulation block is this sequence of cells. Keep the cell boundaries: Andrei
re-runs single cells (for example only "extract" after changing a fit range).

| # | Cell | Content |
|---|------|---------|
| 1 | connect | `hfss = Hfss(version=ansys_version, project=..., design=...)`, then `fourq_hfss = design.renderers.hfss; fourq_hfss.start(); fourq_hfss.activate_ansys_design(...)` |
| 2 | render + setup | `render_design([...], [], box_plus_buffer=False)`, delete `ground_main_plane` and `sample_holder`, add the JJ sheet (lumped RLC or lumped port), mesh operations, setup and sweep values |
| 2a | screenshots: model | `# take screenshots of the model` (see "Screenshots of the HFSS model" below) |
| 3 | analyze | only `hfss.analyze('Setup')` (eigenmode, Q3D) or `hfss.analyze(setup=hfss.get_setups()[0])` (driven) |
| 4 | extract | `get_solution_data` into numpy arrays (`freqs`, `Qs`, `Y`, `S`) |
| 4a | screenshots: mesh, field | `# take screenshots of mesh and field` (HFSS blocks) |
| 5 | process | fit, `print` with units, `*_dict.update({...})` |
| 6 | plot | optional, one figure per cell |
| 7 | cleanup | delete the rendered objects, `fourq_hfss.stop()`, `hfss.release_desktop(close_projects=False, close_desktop=False)` |

The cleanup cell, in the one form that is safe to run at any time:

```python
# delete old qiskit design
rendered = hfss.modeler.get_objects_in_group('Perfect E')
if rendered: hfss.modeler.delete(rendered)
hfss.modeler.delete('main')
hfss.modeler.delete('JJ')

# break connection with ANSYS
fourq_hfss.stop()
hfss.release_desktop(close_projects=False, close_desktop=False)
```

(Q3D: group `'Sheets'`, objects `q3d`, `fourq_q3d`, no `JJ` line.) The `if rendered:`
guard is the only deliberate difference from Sisyphus_A; the reason is in section 8.

Rules:

* The analyze cell contains nothing else, so its `time:` line is the solve time.
* Variable names are fixed: `hfss`, `q3d`, `fourq_hfss`, `fourq_q3d`, `setup`, `sweep`,
  `sol` (eigenmode data), `data` (driven data), `freqs`, `Qs`, `Y`, `S`, `pin` (the
  `rfit.reflection_port()` object), `C_lom`, `C_df`, `C_pins_df`, `C`, `C_pins`.
  Names are reused from block to block on purpose; a block never relies on a variable
  from another simulation block, only on the drawing variables and the dictionaries.
* Comments are short, lower-case, one per step: `# add JJ inductance and capacitance`,
  `#  assign the meander mesh`, `# create sweep`, `# delete old qiskit design`,
  `# break connection with ANSYS`.
* Frequencies for a setup come from the dictionaries, not typed again:
  `setup.update_property('Solution Freq', f'{f_dict['storage']}GHz')`.
* A coarse value used for a quick test stays next to the production value, in Andrei's
  own way: `maximum_length="60um", #"30um",`. The value in the comment is the one for
  the final run.
* Long loops (a sweep of a template variable) use `tqdm.tqdm`, retry a failed solve up
  to three times (`for m in range(3): res = hfss.analyze(...);  if(res): break`), and
  call `np.savez(data_path+'<name>', ...)` **inside** the loop after every point. A
  separate later cell loads the `.npz` and plots, so the plot can be redone without the
  simulation.
* A `### Save` cell closes each `##` section and writes only the dictionaries that the
  section changed:
  `with open(data_path + '<Design>_f_dict.pkl', 'wb') as f: pickle.dump(f_dict, f)`.
* Checks and diagnostics (object lists, `hfss.validate_simple()`, AEDT messages, saving
  a figure to a file) are run from outside with `nbrun.py code`. They are not notebook
  cells.

### Screenshots of the HFSS model

Andrei's rule (2026-11-17): **for HFSS simulations make comprehensive screenshots of the
modeled system at the different steps and save them in a dedicated folder next to the
notebook.** Not in Sisyphus_A; every new simulation block has them.

* Folder: `hfss_shots\` in the design folder (`shots_path`, first setup cell).
  Nothing else goes there; plots of results are a different thing (section 9).
* File name: `<HFSS design>_<block>_<n>_<step>_<view>.jpg`, for example
  `Eigenmode_bare_filter_1_model_iso.jpg`, `Eigenmode_bare_filter_3_E_top.jpg`.
  `<block>` is the `###` heading in lower case with `_`. A re-run overwrites the files
  of its block, so the folder always shows the last run and does not grow.
* Steps and views, as a minimum:

| Cell | Step | Views |
|---|---|---|
| 2a, after render + setup | `1_model`: whole system (cavity, chip, pin) | `iso`, `top` |
| 2a | `1_model_chip`: rendered chip objects only, with `JJ`, ports and lumped elements | `top` |
| 4a, after extract | `2_mesh`: mesh on the chip objects | `top` |
| 4a, eigenmode only | `3_E`: `Mag_E` on the chip objects, one picture per mode | `top` |
| 4a, driven | `3_E`: `Mag_E` at the resonance frequency found in the fit | `top` |

* Q3D blocks: only step 1 (model). Long sweep loops: screenshots once, for the first
  point, not inside the loop.
* The screenshot cells hold only the export lines; the field plots they create are
  named `shot_<...>` and are deleted again in the cleanup cell. Andrei's own field plots
  in the template designs are never touched.
* They need AEDT in graphical mode (the normal case) and bring the AEDT window to the
  front for a moment. The code is in `skills/aedt-render-cleanup`, section
  "Screenshots".
* Mention the folder in the final message and look at the pictures yourself before
  reporting: a missing JJ, a chip outside the cavity or a mesh far too coarse is
  visible there first.

### When HFSS crashes, and new simulations

Two standing instructions from Andrei (2026-11-16). The step-by-step procedure for both
is in `skills/design-notebook-workflow`.

* **HFSS crash or hang: fix it yourself.** Do not stop and wait for Andrei. End the
  crashed session, reopen the proper `.aedt` file through the AEDT MCP (`launch_aedt`,
  `open_project`) using your access to the project folder, check the session with
  `tools/aedt_check.py`, clean the half-finished render with the guarded cleanup cell
  and re-run the block from its connect cell. Save nothing while the session
  misbehaves. A healthy session with his work open is still his: never close that one.
  Report the crash and the recovery in your final message.
* **New simulations in the HFSS project are allowed.** When no template design fits,
  create a new design in the same project, preferably as a copy of the closest
  template design, named `<Template>_<purpose>` (for example `Eigenmode_no_filter`).
  New setups and sweeps in an existing design get new names too. Andrei's own designs,
  setups and sweeps are never renamed, deleted or left with changed values. In the
  notebook, the block names the new design in its connect cell and carries one
  markdown line under its heading saying what the design is and what it was copied
  from. Everything you created is listed in the final message.

### Units and output

| Quantity | Unit in code and dictionaries |
|---|---|
| frequencies, `Ec`, `Ej`, `El`, `g`, `alpha`, `kappa` | GHz (ordinary frequency, not angular; `T = 1/(2*pi*kappa)`) |
| capacitance | fF |
| inductance | nH |
| `pin_q` | GHz/mV |
| HFSS lengths | mm (strings with unit: `'0.022mm'`, `f'{gap_mm}mm'`) |
| Metal lengths | strings with unit, mostly `um` |
| Q factors | plain numbers |

* Print with an f-string, `np.around(value, 3)` and the unit:
  `print(f'g: {np.around(g*1e3, 3)} MHz\n')`. Convert to the readable unit inside the
  f-string (MHz, kHz, ms), keep GHz in the dictionary.
* **Always prefer plots to big data tables** (Andrei, 2026-11-17). The rule of thumb:
  **more than 8 numbers of the same value type → plot.** "Same type" means one quantity
  repeated over a parameter: frequencies over a sweep, `g` over `L_list`, Q of many
  modes, results over optimisation steps. Plot them against that parameter instead of
  printing an array or a long `DataFrame`, and print only the few values that go into
  the dictionaries. Tables whose entries are different quantities stay tables, whatever
  their size: a capacitance matrix (each entry is a different pair of nets), fit
  results (f, Qc, Qi, ...), the targets table, f and Q of a few modes.
* Small tables with `display(pd.DataFrame(...))`, modes as columns, quantities as rows
  (`index=['Frequency, GHz', 'Q']`).
* Plots: `plt.figure(figsize=(8, 6))`; simulation `color='blue', alpha=0.5`; fit
  `color='black', linestyle='dashed'`; axis labels as `'f, GHz'`, `'L, nH'`; a title;
  `plt.grid(True, alpha=0.3)`; `plt.legend()` if there are labels;
  `plt.tight_layout()`; `plt.show()`.
* Figures open as separate windows (Metal sets the Qt backend) and are not stored in
  the notebook. Leave it so; do not add `%matplotlib inline` or `savefig` lines to the
  cells.

### Dictionary keys

Use these names so that Summary cells from Sisyphus_A work unchanged. Mode names are
`T` (transmon), `storage`/`stor`, `read`, `filter`/`filt`, `high-post`.

| Dictionary | Key pattern | Example | Meaning |
|---|---|---|---|
| `f_dict` | `<mode>_bare` | `read_bare` | eigenmode of the resonator alone |
| | `<mode>` | `storage` | mode of the complete eigenmode run |
| | `T`, `alpha` | | transmon f01 and anharmonicity from Q3D `Ec` + `Ej` |
| | `T_egm` | | transmon mode in the complete eigenmode run (linear) |
| | `<mode>_bbq` | `storage_bbq` | bare mode frequency from the BBQ fit |
| | `<mode>_via_pin_S` | `filter_via_pin_S` | resonance seen in S11 of the pin, GHz |
| `Q_dict` | `<mode>_bare`, `<mode>_egm` | `filter_bare` | eigenmode Q |
| `Qe_dict`, `Qi_dict` | `<mode>_via_pin_S` | | `Qc`, `Qi` of the S11 fit |
| `g_dict` | `<a>-<b>` | `T-stor`, `T-read`, `T-filt`, `read-filter` | coupling, GHz |
| | `<a>-<b>_via_<c>` | `read-stor_via_T` | coupling measured with a third element present |
| `Ec_dict` | `Ec_T`, `pin_q`, `C`, `C_pins` | | matrices from `tul.legendre_forward` and their inputs |
| | `C_bbq`, `C_bbq_r`, `C_bbq_f` | | transmon C from each BBQ fit |
| `Ej_dict` | `T` | | junction Ej, GHz (input) |
| | `L0`, `L0_r`, `L0_f` | | geometric series inductance from each BBQ fit, nH |
| `opt_dict` | `log` | | list of optimisation steps, one small row of numbers and short strings per run (never arrays). Not in Sisyphus_A: added for agent-run tuning and accepted by Andrei on 2026-11-13; rules in `skills/geometry-optimization`, section 6. Only present when an optimisation was done. |

## 6. Helper functions that already exist in the notebooks

These three are Andrei's and are defined in Sisyphus_A at the top of the section that
uses them. Copy them **verbatim** into a new notebook at the same place. They are not
"new functions".

| Function | Defined under | Purpose |
|---|---|---|
| `qubit_bbq_fit(freqs, Y, L_list, tolY=1e-8)` | `## Qubit BBQ (Y-port at qubit)` | sweeps the lumped L at the JJ port, fits the avoided crossing, returns `L_list, reso_list, fit_list, f, C_T, g, L0_T` |
| `reso_bbq_fit(freqs, Y, L_list)` | `## Reso BBQ (Y-port at read reso)` | same idea for a port cut into a resonator, returns `L_list, reso_list, fit_list, f1, f1_to_L, f1_to_L2, f2, g` |
| `pin_q_of_kappa(kappa, f)` | `## Special transmon pin` | inverts `tul.kappa_n` to get the effective pin charge from a kappa |

## 7. New functions: last resort, always announced

Before writing any `def`:

1. Search `tul` (`skills/tul-and-extra-elements` has the list; also
   `dir(tul)` and the docstrings), `extra_elements`, `extra_rendering`,
   `qiskit_metal.qlibrary`, `resonator_tools`, PyAEDT, numpy/scipy.
2. If a library function does almost the job, use it and adapt the inputs.
3. If nothing fits, write the smallest function that does, in the notebook section
   that uses it, **directly under a markdown cell** of this form:

```markdown
> **NEW FUNCTION (proposed by Claude): `name(args)`**
> **What:** one sentence.
> **Why not existing code:** which `tul` / `extra_elements` functions were checked and why they do not fit.
> **Where it could live:** e.g. `tiny_useful_lib/equations.py`, if Andrei wants to keep it.
```

4. Follow the `tul` conventions inside it: units as in the table above, docstring with
   `Parameters:` and `Returns:` and units, no hidden reads of global dictionaries
   except the ones the three existing helpers already use.
5. List every new function again in the final message to Andrei. Never add code to
   `tiny_useful_lib` or `extra_elements` yourself.

A new Metal component follows the same rule: propose it, with the reason why the
existing `extra_elements` classes cannot be configured to give the shape.

## 8. Things in Sisyphus_A that are slips, not style

Do not reproduce these in new notebooks (and do not "fix" them in Sisyphus_A):

* `### Complete` eigenmode: `f_dict['read']` and `f_dict['filter']` are both set from
  `freqs[1, 0]` (the transmon mode). Use the index of the mode you mean, and check the
  mode identity by its Q before labelling (the mode with Q close to the bare filter Q
  is the filter).
* `### Bare readout reso`: the `DataFrame` index labels are swapped
  (`['Q', 'Frequency, GHz']` for rows `[freqs, Qs]`).
* `## Chi / ### Read` and `## Pin S-parameter / ### Readout` use
  `f_dict['filter_bare']` where the readout frequency is meant.
* The transmon Purcell cells pass the stored `g` to `tul.kappa_osc_via_osc_eq`. That
  function takes no operator, so the transmon matrix element must be put in by hand:
  `g*np.abs(n[0, 1])` (confirmed by Andrei, 2026-11-13). The chi cells with
  `tul.mix_two_sys` are right as they are. See `skills/design-summary-chi-purcell`.
* `f_dict['T_via_pin_S']` is stored in Hz, the other `*_via_pin_S` entries in GHz.
* The `narrow_pin_h` Y-port sweep loop uses a variable `L` left over from an earlier
  cell. A loop must not depend on leftovers of other cells.
* `design._variables` has `fudge_factor = 1/(1 - 0.04)` while `exp_vars` has
  `1/(1 - 0.004)`. Define a constant once.
* The cleanup cell starts with
  `hfss.modeler.delete(hfss.modeler.get_objects_in_group('Perfect E'))`. When nothing is
  rendered the group does not exist, the inner call returns `None`, and PyAEDT's
  `delete(None)` means "delete every object in the design". On 2026-11-13 this ran on
  the `Network` design; AEDT refused only because an auto region cannot be deleted.
  Always use the guarded form from section 5.
* Cleanup cells that failed with `NameError` or were run out of order. Run the cleanup
  cell of a block every time, before the next block.
* `chip_y = 18800` with `center_y = '-1.75mm'` puts the chip box 0.15 mm into the
  template solid `wafer_edge`; HFSS then refuses to solve ("Parts main and wafer_edge
  intersect"). Check the chip box against the template before the first HFSS run.
* Scratch cells (`T_ph(...)`), empty cells and duplicated cells.

## 9. What Andrei should find when he opens the notebook

* Every cell executed in order, outputs present, no error outputs left.
* The `time:` line under each analyze cell.
* For every HFSS block its screenshots (model, mesh, field) in `<Design>\hfss_shots\`.
* For each simulated quantity one printed line with value and unit, and for each fit
  one plot cell of data and fit (the figure itself is saved by you as a PNG in
  `<Design>\figs\`, because it is not stored in the file).
* The dictionaries saved, and a Summary section that reproduces all headline numbers
  from the saved files alone.
* At the top of your final message: which values are from coarse test runs and which
  from converged runs, and any new function you proposed.
