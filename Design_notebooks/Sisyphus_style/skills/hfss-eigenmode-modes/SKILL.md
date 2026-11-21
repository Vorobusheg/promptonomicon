---
name: hfss-eigenmode-modes
description: Eigenmode block of a Sisyphus-style notebook - HFSS eigenmode simulation of one strip-line resonator alone (bare frequency and rough external Q through the 50-ohm pin), of the complete chip (all modes), and Optimetrics parametric sweeps of a template variable such as the pin position. Use when a resonator frequency must be found or tuned by its length, when mode frequencies and Q of the whole device are needed, or when a pin position sweep is asked for.
---

# Eigenmode -> mode frequencies and Q

Reference: `Sisyphus_A.ipynb`, `## Eigenmode`. Shared mechanics: skill
`aedt-render-cleanup`. Template design: `Eigenmode` (setup `Setup`, 50-ohm lumped RLC
`Pin` on the coax sheet `Line`: the only loss, so `Q` is the external Q through the pin).

## Bare resonator (one resonator alone in the cavity)

```python
# connect to HFSS
hfss = Hfss(version=ansys_version, project='Sisyphus', design='Eigenmode')

fourq_hfss = design.renderers.hfss
fourq_hfss.start()
fourq_hfss.activate_ansys_design('Eigenmode')
```
```python
# add filter design
fourq_hfss.render_design(['filter_reso', 'filter_reso_pad_A', 'filter_reso_pad_B'],
                         [], box_plus_buffer=False)

# delete autoground and fake jj
hfss.modeler.delete('ground_main_plane')
hfss.modeler.delete('sample_holder')

#  assign the meander mesh
hfss.mesh.assign_length_mesh(['trace_filter_reso'], inside_selection=False, maximum_length="5um",
                             name='meander_mesh', maximum_elements=None,)

# setup config
setup = hfss.setups[0]
setup.props["MinimumFrequency"] = "7.5GHz"
setup.props["NumModes"] = 1
setup.update()
```
```python
hfss.analyze('Setup')
```
```python
sol = hfss.post.get_solution_data(
    expressions=[f're(Mode({n+1}))' for n in range(1)]+[f'Q({n+1})' for n in range(1)],
    setup_sweep_name=f"{hfss.setups[0].name} : LastAdaptive",
    report_category="Eigenmode Parameters",
)

freqs = []
Qs = []

for n in range(1):
    freqs.append(sol.data_real(f"re(Mode({n+1}))"))
    Qs.append(sol.data_real(f"Q({n+1})"))

freqs = np.around(np.asarray(freqs)/1e9, 3)
Qs = np.around(np.asarray(Qs))

display(pd.DataFrame([freqs[:, 0], Qs[:, 0]], index=['Frequency, GHz', 'Q'], columns=['filter']))
```
```python
f_dict.update({'filter_bare' : freqs[0, 0]})
Q_dict.update({'filter_bare':Qs[0, 0]})
```

then the guarded cleanup cell (the `delete('JJ')` line stays; it does nothing here).

* `MinimumFrequency` must be below the wanted mode and above every mode you do not
  want (the storage post mode is at 4.5 GHz, the resonators near 8.3 GHz, hence
  `"7.5GHz"`). With `NumModes = 1` HFSS returns the first mode above it.
* `re(Mode(n))` is in Hz, `Q(n)` is dimensionless. `freqs[m, 0]`: mode `m`, nominal
  variation.
* Row labels: the list `[freqs[:, 0], Qs[:, 0]]` goes with
  `index=['Frequency, GHz', 'Q']`, in this order. (The bare-readout cell of Sisyphus_A
  has the two labels swapped.)
* The readout version renders `['T', 'taper_p1', 'taper_p2', 'read_reso',
  'read_reso_pad_A', 'read_reso_pad_B']` and adds the junction as lumped RLC with the
  `transmon_mesh` operation (skill `aedt-render-cleanup`), because the readout
  resonator's capacitive load is the transmon pad.
* `kappa = f/Q` (GHz). `Q` from one eigenmode run through a far pin is rough
  (Sisyphus_A: bare readout `Q` 1.46e6 from eigenmode, `Qc` 2.5e6 from the S11 fit). Use
  the pin S-parameter block for a number you quote.

### Accuracy and coarse runs

The template setup converges on the real frequency to 0.05 % with 4-15 passes and 3
converged passes. The trace mesh length is the cost: 5 um took 2 h 12 min for the filter,
10 um took 30 min for the readout.

Coarse test, measured on the Sisyphus filter (2026-11-13): trace mesh `"100um"`,
`MaximumPasses=4, MinimumPasses=2, MinimumConvergedPasses=1` -> **17 s**,
f = 8.261 GHz (fine 8.344, 1 % low), Q = 137 (fine 122).

```python
setup.props.update(MaximumPasses=4, MinimumPasses=2, MinimumConvergedPasses=1)   # coarse test
setup.update()
...                      # in the cleanup cell, before the connection is released:
setup.props.update(MaximumPasses=15, MinimumPasses=4, MinimumConvergedPasses=3)  # template values
setup.update()
```

The pass numbers are not set by any notebook cell, so they must be restored, with the
template numbers written out. Do not capture "the original" from `setup.props` during
the session: PyAEDT fills `props` from the last saved project file, and AEDT saves the
project at every analyze, so after one coarse run `props` already shows the coarse
values (this happened on 2026-11-13 and left the setup at 4 passes until it was fixed
by hand). The live value is
`hfss.odesign.GetChildObject('Analysis').GetChildObject('Setup').GetPropValue('Passes')`.

A coarse
frequency is good to about 1 %: enough to bring a length into range (see below), not
enough to place two resonators 50 MHz apart. For that, compare runs done with the same
mesh settings, or go to the fine mesh (ask first).

### Tuning a resonator length

A half-wave resonator: `f` is proportional to `1/total_length`, to first order. From one
simulation `(L0, f0)` and a target `f_t`:

```
L1 = L0 * f0 / f_t          (then simulate again and repeat once with the same rule)
```

Two iterations normally land within the mesh error. Keep the correction visible in the
cell, as Sisyphus_A does: `total_length=f'{3.5}mm' + '+0.34mm'`. Check after
`gui.rebuild()` that the meander really has the new length.

## Complete chip

Render everything, junction as lumped RLC, both mesh operations, then

```python
# setup config
setup = hfss.setups[0]
setup.props["MinimumFrequency"] = "3GHz"
setup.props["NumModes"] = 5
setup.update()
```

and the same extract cell with `range(5)` and
`columns=['storage', 'transmon', 'filter', 'read', 'high-post']`.

* 10 h 44 min in Sisyphus_A. Never a test run. Ask before starting it.
* **Identify the modes before labelling them.** Modes are ordered by frequency only.
  Use frequency and Q together: the storage post mode has a huge Q and the lowest
  frequency; the transmon mode sits near the linear frequency
  `1/(2*pi*sqrt(L*C))` (below f01 of the Q3D block); of the two modes near the
  resonator frequencies, the one with Q close to `Q_dict['filter_bare']` is the filter.
  If two resonators are close, they hybridise and the labels become a matter of
  convention: say so in the report.
* Store each mode under its own index, for example:

```python
f_dict.update({'storage':freqs[0, 0]})
f_dict.update({'T_egm':freqs[1, 0]})
f_dict.update({'filter':freqs[2, 0]})
f_dict.update({'read':freqs[3, 0]})
f_dict.update({'high-post':freqs[4, 0]})

Q_dict.update({'storage_egm':Qs[0, 0]})
Q_dict.update({'T_egm':Qs[1, 0]})
Q_dict.update({'filter_egm':Qs[2, 0]})
Q_dict.update({'read_egm':Qs[3, 0]})
Q_dict.update({'high-post_egm':Qs[4, 0]})
```

  (In Sisyphus_A this cell writes `freqs[1, 0]` into `'read'` and `'filter'` and the Q
  keys are crossed: a slip, do not copy the indices from there.)

## Parametric sweep of a template variable

For a geometric parameter that lives in the template (pin position `drift`, pin height
`hhh`), HFSS Optimetrics does the loop. Sisyphus_A, `#### Pin variation`:

```python
print(hfss.setup_names)                    # solve setups actually present
print(hfss.ooptimetrics.GetSetupNames())   # parametric setups already present (stale ones too)
print(hfss["drift"])                       # value and units of the swept variable
```
```python
par = hfss.parametrics.add("drift", "-0.5mm", "0.5mm", "0.1mm", "LinearStep", solution="Setup", name="drift_sweep")
```
```python
par.props["ProdOptiSetupDataV2"]["SaveFields"] = False
par.update()

hfss.save_project()
hfss.analyze_setup("drift_sweep", cores=8, num_variations_to_distribute=2)
```
```python
mode = 1
sol = hfss.post.get_solution_data(
    expressions=[f"re(Mode({mode}))", f"Q({mode})"],
    setup_sweep_name=f"{hfss.setups[0].name} : LastAdaptive",
    report_category="Eigenmode Parameters",
    primary_sweep_variable="drift",          # drift becomes the x-axis of the report
    variations={"drift": ["All"]},           # include every solved variation, not just the nominal one
)

drift = np.asarray(sol.primary_sweep_values, dtype=float)                 # in sol.units_sweeps["drift"]
freqs = np.around(np.asarray(sol.data_real(f"re(Mode({mode}))")) / 1e9, 3)   # GHz
Qs    = np.around(np.asarray(sol.data_real(f"Q({mode})")))
```

then `kappas = freqs/Qs`, two plots (f and kappa against the variable) and
`np.savez(data_path+'<name>', drift=drift, freqs=freqs, kappas=kappas)`.

* The parametric setups `drift_sweep` and `heigh_sweep` already exist in the Sisyphus
  template. `hfss.parametrics.add` with an existing name fails or duplicates: check
  `GetSetupNames()` first and reuse the existing setup.
* 11 points took 6 h. Ask first.
* Set the variable back afterwards:
  `hfss.variable_manager.set_variable(name="drift", expression="0mm", overwrite=True)`.
* A parameter of the **chip** (a length in the Metal drawing) cannot be swept this way:
  the chip is redrawn from Python. Loop in the notebook instead: change the option,
  `gui.rebuild()`, cleanup, render, analyze, extract, `np.savez` inside the loop.
