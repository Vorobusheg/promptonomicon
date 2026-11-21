---
name: aedt-render-cleanup
description: Mechanics shared by every Ansys block of a Sisyphus-style notebook - pre-flight check, connecting PyAEDT and the Qiskit Metal renderer to a template design of an open AEDT project, rendering a subset of components, removing the auto ground and sample holder, adding the junction as a lumped RLC sheet or lumped port, mesh operations, validation before solving, and the guarded cleanup cell that removes the rendered chip. Use before writing or running any Q3D or HFSS cell, when a render or solve fails, or when a template design must be checked or cleaned.
---

# Rendering into a template design and cleaning up

Every simulation block is: **connect -> render + setup -> analyze -> extract -> process
-> cleanup**. This skill covers connect, render, the junction sheet, checks and cleanup.
The solver-specific parts are in `q3d-capacitance-ec`, `hfss-eigenmode-modes`,
`hfss-bbq-coupling`, `hfss-pin-sparameter-kappa`.

## How the pieces talk to AEDT

Two independent connections to the **same running AEDT session**:

| Object | Library | Channel | Used for |
|---|---|---|---|
| `hfss = Hfss(...)`, `q3d = Q3d(...)` | PyAEDT | gRPC | everything except drawing the chip: deleting objects, JJ sheet, boundaries, mesh, setups, solving, reading results |
| `fourq_hfss = design.renderers.hfss`, `fourq_q3d = design.renderers.q3d` | Qiskit Metal + pyEPR | COM | drawing the Metal components into the active design; for Q3D also `get_capacitance_matrix()` |

The Metal renderer has no idea which project you mean: `start()` attaches to the first
registered AEDT session and takes its **active project**. `Hfss(project=..., design=...)`
is what makes your project and design active, so it always comes first.

**Pre-flight, once per work session and again whenever something looks odd:**

```powershell
# $py = metal env python, $dn = ...\Claude\Design_notebooks\Sisyphus_style  (see design-notebook-workflow)
& $py "$dn\tools\aedt_check.py" --project Sisyphus
```

Proceed only on `OK` (exactly one AEDT session, and COM sees the project). Two healthy
sessions: stop and ask Andrei, do not close his. A crashed or hung session, or none at
all: recover it yourself through the AEDT MCP, as described in
`design-notebook-workflow`, section "AEDT crashed or is not running".

## Template designs

The chip is rendered into designs that already contain the 3D environment and the
solver setup. Andrei's designs are not renamed, deleted or restructured; when none of
them fits, you may add a new design to the project, preferably as a copy of the closest
one (`design-notebook-workflow`, section "New simulations in the project"). For Sisyphus
(`Projects\GKP_cavity\cavity_simulations_HFSS\Cavity_V1\Sisyphus.aedt`, state of
2026-11-13):

| Design | Type | Template objects | Boundaries / ports | Setup | Variables |
|---|---|---|---|---|---|
| `Capacitance` | Q3D | `Region`, `Cavity_V1`, `Pin`, `wafer_edge` | nets `Cavity_V1`, `Pin` | `Setup` (Matrix; 0.1 %, 5-20 passes) | `pin_h`, `wire_length` |
| `Eigenmode` | HFSS Eigenmode | `Region`, `Cavity_V1`, `Pin`, `wafer_edge`, `Holder_and_taper`, sheet `Line` | lumped RLC `Pin` = 50 ohm on `Line` (this is what gives a finite Q through the pin) | `Setup` (4-15 passes, 3 converged, dF 0.05 %); parametric `drift_sweep`, `heigh_sweep` | `pin_h`, `drift`, `hhh` |
| `Network` | HFSS Modal Network (driven) | `RadiatingSurface`, `Cavity_V1`, `Pin`, `wafer_edge`, `Holder_and_taper`, sheet `Line` | radiation `AutoOpen1`, lumped port `line_port` (50 ohm) on `Line` | `Auto1` + sweep `Sweep` | `pin_h`, `pin_hn` |
| `Special_pin` | HFSS Modal Network | as `Network`, with a second, narrow pin | `AutoOpen1`, `line_port` | `Auto1` + `Sweep` | `pin_h`, `pin_hn`, `narrow_pin_h` |
| `Capacitance_special_pin` | Q3D | as `Capacitance`, narrow pin | nets `Cavity_V1`, `Pin` | `Setup` | `pin_h`, `wire_length`, `narrow_pin_h` |
| `Complete_cavity_model` | HFSS driven | CAD of the whole cavity | | | not used by the notebook |

For another project, list the same facts first (through `nbrun.py code`, read-only):

```python
print(hfss.modeler.solid_names, hfss.modeler.sheet_names)
print([(b.name, b.type) for b in hfss.boundaries])
print(hfss.setup_names, dict(hfss.setups[0].props))
print({k: v.expression for k, v in hfss.variable_manager.design_variables.items()})
```

Write the object list of the clean template down. After your cleanup the design must
show exactly that list again.

## Cell 1: connect

```python
# connect to HFSS
hfss = Hfss(version=ansys_version, project='Sisyphus', design='Eigenmode')

fourq_hfss = design.renderers.hfss
fourq_hfss.start()
fourq_hfss.activate_ansys_design('Eigenmode')
```

Q3D is the same with `Q3d(...)`, `design.renderers.q3d`, `fourq_q3d`. In Sisyphus_A the
Q3D block has `q3d = Q3d(...)` in its own cell; both forms are fine.

* `project` is the name of an already open project. If it is not open, PyAEDT silently
  creates an empty project with that name: check `hfss.project_file` if in doubt.
* The warning "Service Pack is not detected ... Insecure Mode" is normal here.
* If `activate_ansys_design` logs "was not in active project ... A new design will be
  added", COM is looking at another project. Stop, run `aedt_check.py`.

**Before rendering, make sure the design is clean.** Compare `solid_names` and
`sheet_names` with the template list. Leftovers of an earlier run (`main`, `JJ`,
`pad_*`, `trace_*`, `taper_main_*`) must go first: run the cleanup cell of the block,
then the connect cell again.

## Cell 2: render

```python
# add read reso and transmon
fourq_hfss.render_design(['T', 'taper_p1', 'taper_p2', 'read_reso', 'read_reso_pad_A', 'read_reso_pad_B'],
                         [], box_plus_buffer=False)

# delete autoground and fake jj
hfss.modeler.delete('ground_main_plane')
hfss.modeler.delete('sample_holder')
```

* First argument: the Metal component names to draw. Second: open pins, always `[]`
  here. `box_plus_buffer=False`: the chip box `main` gets the size and position from
  `design.chips.main`, so it lands where the template expects it.
* The renderer creates: one sheet per metal shape (`pad_top_T`, `trace_read_reso`, ...,
  all in the model-tree group `Perfect E`, with one boundary `PerfE`), the silicon box
  `main`, a ground sheet `ground_main_plane`, and (HFSS only) a vacuum box
  `sample_holder`. The chip sits in a 3D cavity, so the ground sheet and the vacuum box
  are deleted right away. In Q3D only `ground_main_plane` exists.
* In Q3D the sheets get a thin-conductor boundary and nets are identified
  automatically; the sheets are in the group `Sheets`.
* Rendering twice without cleanup fails or duplicates objects.

## The junction sheet (HFSS)

The junction is one rectangle `JJ` that bridges the gap between the two base-metal
tapers. Size and position come from the drawing variables:

```python
# add JJ inductance and capacitance
gap_mm = taper_gap/1e3+ 2*float(length_cut_taper[:-2])/1e3

rect = hfss.modeler.create_rectangle(orientation=generic.constants.Plane.XY,
                                     origin=[0 - 0.022/2, float(T_y[:-2])/1e3 - gap_mm/2, 0],
                                     sizes = ['0.022mm', f'{gap_mm}mm'],
                                     name='JJ',
                                     is_covered=True,
                                    )
```

`0.022` mm is the taper width at the cut, `T_y` the transmon centre. For a transmon at
another x or with another orientation, derive origin and sizes from its variables the
same way; the sheet must touch both tapers.

Then one of two assignments:

| Purpose | Code | Used in |
|---|---|---|
| junction as linear L parallel C (the transmon becomes an oscillator) | `hfss.assign_lumped_rlc_to_sheet('JJ', start_direction=1, name='JJ_RLC', inductance=f'{tul.L_of_El(Ej_dict['T'])}n', capacitance=f'{tul.C_of_Ej(Ej_dict['T'], Ej_to_S=exp_vars['Ej_to_S'])}f')` | eigenmode, pin S-parameter, reso BBQ (sheet named `JJ_T` there) |
| junction as a port, to read the admittance Y seen by the junction | `hfss.lumped_port('JJ', integration_line=1, name='JJ_port')` | qubit BBQ |

`start_direction` / `integration_line`: 0 = x, 1 = y. Use the axis along which the
junction current flows (`1` for a transmon lying along y).

`tul.L_of_El(Ej)` returns nH, `tul.C_of_Ej(Ej, Ej_to_S=...)` returns fF, hence the
suffixes `n` and `f`.

## Mesh operations

```python
#  assign the JJ mesh
hfss.mesh.assign_length_mesh(['JJ', 'taper_main_taper_p1', 'taper_main_taper_p2'], inside_selection=False, maximum_length="30um",
                             name='transmon_mesh', maximum_elements=None,)

#  assign the meander mesh
hfss.mesh.assign_length_mesh(['trace_read_reso'], inside_selection=False, maximum_length="10um",
                             name='meander_mesh', maximum_elements=None,)
```

* Names `transmon_mesh` and `meander_mesh`. They are deleted automatically with their
  objects at cleanup.
* `maximum_length` on the CPW trace is the main cost knob. Production values in
  Sisyphus_A: 5-10 um (eigenmode), 30 um (driven). Coarse test: 100 um. A coarse value
  stays in the cell as `maximum_length="100um", #"10um",` until the final run.

## Check before solving (through `nbrun.py code`)

```python
print(hfss.validate_simple())                 # must be 1 / True
print(hfss.modeler.sheet_names, [(b.name, b.type) for b in hfss.boundaries])
```

If a solve returns `False` or validation fails, read the reason:

```python
for m in list(hfss.odesktop.GetMessages(hfss.project_name, hfss.design_name, 0))[-15:]: print(m.strip())
```

Known causes:

| Message | Cause | What to do |
|---|---|---|
| `Parts main and wafer_edge intersect` | chip box from `design.chips.main` overlaps a template solid | fix chip size / centre in the drawing (skill `qmetal-chip-drawing`); ask Andrei which value is right |
| `Boundary 'PerfE' ... lost its assignment` (warning) | normal after cleanup | nothing |
| solve fails at once, no clear message | leftover objects of an earlier render, or a second render on top | cleanup, connect, render again |
| `analyze` returns `False` now and then in long loops | licence or solver hiccup | retry up to three times, as Sisyphus_A does in its sweep loops |

`hfss.analyze(...)` returns `True`/`False` and does not raise. Always look at the
returned value before the extract cell.

## Screenshots

Andrei's rule (2026-11-17), see `sisyphus_style.md` section 5. API of PyAEDT 0.23
(checked in the `metal` env): `hfss.post.export_model_picture(full_name, show_axis,
show_grid, show_ruler, show_region, selections, field_selections, orientation, width,
height)` writes a JPG; `orientation` is one of `'isometric'`, `'top'`, `'bottom'`,
`'front'`, `'back'`, `'left'`, `'right'`, `'trimetric'`, `'dimetric'`. It works only with
the AEDT GUI. `plot_field_from_fieldplot` needs PyVista, which is not installed: do not
use it.

Cell 2a, after render + setup (here for the bare filter eigenmode):

```python
# take screenshots of the model
shot = shots_path + 'Eigenmode_bare_filter_'
chip_objs = hfss.modeler.get_objects_in_group('Perfect E') + ['JJ']
hfss.post.export_model_picture(full_name=shot+'1_model_iso.jpg', orientation='isometric', show_grid=False, width=1600, height=1000)
hfss.post.export_model_picture(full_name=shot+'1_model_top.jpg', orientation='top', show_grid=False, width=1600, height=1000)
hfss.post.export_model_picture(full_name=shot+'1_model_chip_top.jpg', selections=chip_objs, orientation='top', show_grid=False, width=1600, height=1000)
```

Cell 4a, after extract (eigenmode; one `Mag_E` picture per mode):

```python
# take screenshots of mesh and field
mesh_plot = hfss.post.create_fieldplot_surface(chip_objs, 'Mesh', plot_name='shot_mesh')
hfss.post.export_model_picture(full_name=shot+'2_mesh_top.jpg', selections=chip_objs, field_selections='shot_mesh', orientation='top', show_grid=False, width=1600, height=1000)
for m in range(len(freqs)):
    E_plot = hfss.post.create_fieldplot_surface(chip_objs, 'Mag_E', setup='Setup : LastAdaptive',
                                                intrinsics={'Phase': '0deg'}, plot_name=f'shot_E_mode{m+1}')
    hfss.post.export_model_picture(full_name=shot+f'3_E_mode{m+1}_top.jpg', selections=chip_objs, field_selections=f'shot_E_mode{m+1}', orientation='top', show_grid=False, width=1600, height=1000)
```

* Driven blocks: same, with `setup=hfss.nominal_adaptive` and
  `intrinsics={'Freq': f'{f_res}GHz', 'Phase': '0deg'}` at the frequency of the fit.
* Q3D blocks: only cell 2a, with `q3d` and the group `'Sheets'` for the chip objects.
* For eigenmode, selecting the mode of a field plot depends on the AEDT version
  (intrinsic or the variation `Modes`). Check the first picture: if all `Mag_E`
  pictures look the same, the mode was not selected; set it in the plot and report how.
* `selections` should limit the picture to the chip objects. If the chip picture still
  shows the whole cavity, do not hide or move template objects to get a close-up (that
  changes Andrei's project): keep the picture as it is and report it.
* Field and mesh plots on a fine mesh take some seconds to a few minutes; they are not
  part of the analyze cell, so its `time:` line stays the solve time.

These lines were not run live yet (written 2026-11-17 while AEDT held another project).
The first agent that runs them: check that the files appear and look right, and fix
this section if an argument is wrong.

## Last cell: cleanup

Before the delete lines, remove the screenshot field plots of this block (only those
named `shot_...`):

```python
# delete screenshot plots
for p in [p for p in hfss.post.field_plot_names if p.startswith('shot_')]: hfss.post.delete_field_plot(p)
```

Sisyphus_A's cleanup cell is

```python
# delete old qiskit design
hfss.modeler.delete(hfss.modeler.get_objects_in_group('Perfect E'))
hfss.modeler.delete('main')
hfss.modeler.delete('JJ')

# break connection with ANSYS
fourq_hfss.stop()
hfss.release_desktop(close_projects=False, close_desktop=False)
```

**Do not use the first delete line as it is.** If nothing is rendered,
`get_objects_in_group('Perfect E')` returns `None`, and `hfss.modeler.delete(None)`
means "delete all objects of the design". On 2026-11-13 this was tried by accident on
`Network`; AEDT refused only because the auto region `RadiatingSurface` cannot be
deleted. Write the cell with a guard:

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

Q3D version (group `Sheets`; there is no `JJ`):

```python
# delete old qiskit design
rendered = q3d.modeler.get_objects_in_group('Sheets')
if rendered: q3d.modeler.delete(rendered)
q3d.modeler.delete('main')

# break connection with ANSYS
fourq_q3d.stop()
q3d.release_desktop(close_projects=False, close_desktop=False)
```

* In HFSS never delete the group `Sheets`: the template's own port sheet `Line` is in it.
* Add one `delete` line for every extra object the block created (`JJ_T` in the reso
  BBQ block).
* `delete('<name>')` of an object that does not exist only prints
  "No objects to delete". That is harmless.
* Deleting the objects also deletes their boundaries (`PerfE`, `JJ_RLC`, `JJ_port`) and
  mesh operations.
* `release_desktop(close_projects=False, close_desktop=False)`: always with both
  `False`. Anything else closes Andrei's project or AEDT.
* Never `fourq_hfss.clean_active_design()`: it removes the cavity too.
* If the cleanup cell fails with `NameError` (kernel restarted, block never connected),
  run the connect cell and then the cleanup cell.
* Restore template settings you changed for a test (passes, template variables) in this
  cell, before the `# break connection with ANSYS` lines. Write the template numbers
  out (they are in the table above); see "Live values and saved values" below.

After cleanup, confirm through `nbrun.py code` after a fresh connect, or in the next
block's connect step, that `solid_names` and `sheet_names` equal the template list.

## Live values and saved values

* AEDT saves the project at every `analyze`. So the `.aedt` file on disk contains
  whatever was rendered at the moment of the last solve.
* PyAEDT's `setup.props` and `sweep.props` are filled from the **saved file**, not from
  the live session. After `setup.update_property(...)`, or after a change followed by
  no save, `props` is out of date. Read live values with

  ```python
  o = hfss.odesign.GetChildObject('Analysis').GetChildObject(setup.name)
  print({p: o.GetPropValue(p) for p in o.GetPropNames() if not p.endswith('/Choices')})
  ```

* Consequence 1: never "capture the original" from `props` after you have changed
  something in the session. Note the template values once, at the very start, and write
  them as numbers when restoring.
* Consequence 2: at the very end of your work, after the last cleanup, save once so
  that the file on disk is the clean template again:

  ```python
  hfss = Hfss(version=ansys_version, project='Sisyphus', design='Network')
  hfss.save_project()
  hfss.release_desktop(close_projects=False, close_desktop=False)
  ```

  Do this through `nbrun.py code`, after checking all touched designs are clean.

## Solutions in the project are disposable

Each render changes the geometry and invalidates the solution stored in the design; the
next block overwrites it. Nothing may depend on a solution staying in the `.aedt`
project. Every number needed later is extracted into a dictionary or `.npz` in the same
block, before the cleanup cell.
