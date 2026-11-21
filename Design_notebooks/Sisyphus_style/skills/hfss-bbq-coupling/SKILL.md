---
name: hfss-bbq-coupling
description: BBQ (black-box quantization) blocks of a Sisyphus-style notebook - get the coupling g between two systems from one HFSS driven sweep of the admittance Y at a lumped port, by sweeping a lumped inductance in post-processing and fitting the avoided crossing. Covers "Qubit BBQ" (port at the junction, g between transmon and storage, readout or filter) and "Reso BBQ" (port cut into a resonator, g between resonators), with Andrei's qubit_bbq_fit and reso_bbq_fit helpers and tul.bbq_resonances_of_Y. Use when a coupling g must be computed or tuned.
---

# BBQ blocks -> coupling g

Reference: `Sisyphus_A.ipynb`, `## Qubit BBQ (Y-port at qubit)` and
`## Reso BBQ (Y-port at read reso)`. Shared mechanics: skill `aedt-render-cleanup`.
Template design: `Network` (driven modal, setup `Auto1`, sweep `Sweep`).

## Idea

1. Render the two systems whose coupling is wanted (and nothing else that is resonant
   in the band).
2. Put a **lumped port** where one of them can be tuned by an inductance: at the
   junction for the transmon, at a cut in the trace for a resonator.
3. One driven sweep gives `Y(f)` seen from the port.
4. In post-processing add a lumped `L` (and `C`) across the port: modes are the zeros
   of `Y(f) + 1/(i*w*L) + i*w*C`. `tul.bbq_resonances_of_Y(freqs, Y, L, C)` returns
   them. Repeating for a list of `L` moves one system through the other: an avoided
   crossing, without any new HFSS run.
5. Fit the two branches with two coupled oscillators (`tul.mix_oscillators`): the fit
   gives the bare frequencies and `g`.

The transmon is treated as a linear oscillator here. `g` goes into the non-linear
calculation later (skill `design-summary-chi-purcell`).

## Qubit BBQ

Helper `qubit_bbq_fit` (copy verbatim from Sisyphus_A into the first cell under the
`##` header; it reads `Ej_dict['T']` and `exp_vars['Ej_to_S']` for the junction
capacitance):

```python
L_list, reso_list, fit_list, f, C_T, g, L0_T = qubit_bbq_fit(freqs, Y, L_list, tolY=1e-8)
```

| Returned | Meaning |
|---|---|
| `L_list` | the L values (nH) for which exactly two resonances were found |
| `reso_list[n, :]` | the two simulated resonances at `L_list[n]`, GHz |
| `fit_list[n, :]` | the fitted model at the same points |
| `f` | bare frequency of the other mode, GHz |
| `C_T` | transmon capacitance, fF (`tul.Ec_of_C(C_T)` should be close to the Q3D `Ec`) |
| `g` | coupling in the charge convention: the interaction is `g * n * (a + at)` with the transmon Cooper-pair operator `n`. Inside the fit the oscillator coupling is `g*tul.n_zpf(Z_T)`. Store this `g` as it is. |
| `L0_T` | geometric inductance in series with the junction, nH |

Model in the fit: `f_T = 1/(2*pi*sqrt((L + L0_T)*C_T))`, `Z_T = sqrt((L + L0_T)/C_T)`,
fitted with `scp.optimize.dual_annealing`, bounds `f` 2-10 GHz, `C_T` 20-200 fF, `g`
0-0.4, `L0_T` 0-8 nH. If a design leaves these ranges, the bounds inside the helper must
change: that is a change to Andrei's function, so propose it, do not do it silently.

Cells for "To storage" (transmon alone in the cavity):

```python
# connect to HFSS
hfss = Hfss(version=ansys_version, project='Sisyphus', design='Network')

fourq_hfss = design.renderers.hfss
fourq_hfss.start()
fourq_hfss.activate_ansys_design('Network')
```
```python
fourq_hfss.render_design(['T', 'taper_p1', 'taper_p2'], box_plus_buffer=False)
hfss.modeler.delete('ground_main_plane')
hfss.modeler.delete('sample_holder')

# add JJ
gap_mm = taper_gap/1e3+ 2*float(length_cut_taper[:-2])/1e3
rect = hfss.modeler.create_rectangle(orientation=hfss.PLANE.XY,
                                     origin=[0 - 0.022/2, float(T_y[:-2])/1e3 - gap_mm/2, 0],
                                     sizes = ['0.022mm', f'{gap_mm}mm'],
                                     name='JJ',
                                     is_covered=True,
                                    )

# assign lumped port to JJ sheet
hfss.lumped_port('JJ', integration_line=1, name='JJ_port')

#  assign the JJ mesh
hfss.mesh.assign_length_mesh(['JJ', 'taper_main_taper_p1', 'taper_main_taper_p2'], inside_selection=False, maximum_length="30um",
                             name='transmon_mesh', maximum_elements=None,)

# create sweep
setup = hfss.get_setup(hfss.get_setups()[0])
setup.update_property('Solution Freq', f'{f_dict['storage']}GHz')
setup.update_property('Passes', '20')
hfss.oanalysis.DeleteSweep(setup.name, setup.get_sweep_names()[0])
sweep = setup.add_sweep(name='Sweep', sweep_type='Interpolating')
sweep.props.update(RangeStart=f'{3.8}GHz', RangeEnd=f'{5.2}GHz', RangeCount=24001, InterpTolerance=0.01, InterpMaxSolns=3000)
sweep.update()
```
```python
# start simulation
hfss.analyze(setup=hfss.get_setups()[0])
```
```python
data = hfss.post.get_solution_data(expressions=['re(Y(JJ_port,JJ_port))', 'im(Y(JJ_port,JJ_port))'], primary_sweep_variable="Freq")
Y = data.data_real("re(Y(JJ_port,JJ_port))")+1j*data.data_real("im(Y(JJ_port,JJ_port))")
freqs = np.asarray(data.primary_sweep_values, dtype=float)
```
```python
L_list, reso_list, fit_list, f_storage, C_T, g, L0_T = qubit_bbq_fit(freqs, Y, L_list=np.linspace(15, 11, 101))
```
```python
print(f'storage frequency: {np.around(f_storage, 3)} GHz')
print(f'transmon: C={np.around(C_T, 3)} fF, Ec={np.around(tul.Ec_of_C(C_T), 3)} GHz, L0={np.around(L0_T, 3)} nH')
print(f'g: {np.around(g*1e3, 3)} MHz\n')

f_dict.update({'storage_bbq':f_storage})
Ej_dict.update({'L0':L0_T})
Ec_dict.update({'C_bbq':C_T})
g_dict.update({'T-stor':g})
```
```python
plt.figure(figsize=(8, 6))
plt.plot(L_list, reso_list[:, 0], label='simulation', color='blue', alpha=0.5)
plt.plot(L_list, reso_list[:, 1], color='blue', alpha=0.5)
plt.plot(L_list, fit_list[:, 0], label='fit', color='black', linestyle='dashed')
plt.plot(L_list, fit_list[:, 1], color='black', linestyle='dashed')

plt.xlabel('L, nH')
plt.ylabel('f, GHz')
plt.title('Transmon-Storage BBQ')
plt.grid(True, alpha=0.3)
plt.legend()

plt.tight_layout()
plt.show()
```

then the guarded cleanup cell.

Per target:

| Block | Render | `Solution Freq` | Sweep range (Sisyphus_A) | `L_list` (nH) | Stores |
|---|---|---|---|---|---|
| To storage | `T`, tapers | `f_dict['storage']` | 3.8-5.2 GHz | `np.linspace(15, 11, 101)` | `g_dict['T-stor']`, `f_dict['storage_bbq']`, `Ej_dict['L0']`, `Ec_dict['C_bbq']` |
| To readout | + `read_reso`, pads; mesh `trace_read_reso` | `f_dict['read_bare']` | 7.7-8.9 GHz | `np.linspace(2.2, 3, 101)`, `tolY=1e-6` | `g_dict['T-read']`, `f_dict['read_bbq']`, `Ej_dict['L0_r']`, `Ec_dict['C_bbq_r']` |
| To filter | + `filter_reso`, pads; mesh `trace_filter_reso` | `f_dict['filter_bare']` | 7.9-8.3 GHz | `np.linspace(2.8, 3.5, 301)` | `g_dict['T-filt']`, `f_dict['filt_bbq']`, `Ej_dict['L0_f']`, `Ec_dict['C_bbq_f']` |

### Choosing sweep range and `L_list`

* The crossing is where the L-tuned transmon equals the other mode:
  `L_cross = 1e6/((2*np.pi*f)**2 * C_T) - L0_T` (nH, with `f` in GHz and `C_T` in fF).
  First guess: `C_T = tul.C_of_Ec(Ec_dict['Ec_T'][0, 0])`, `L0_T` about 1 nH.
  Centre `L_list` there, wide enough to show both asymptotes (the flat branch and the
  falling `1/sqrt(L)` branch) on each side: about +/-15 % for a weak coupling, more for a
  strong one.
* The sweep range must contain both branches for the whole `L_list`: from the lower
  branch at the largest `L` to the upper branch at the smallest `L`.
* Only one other mode may be inside the sweep range. `qubit_bbq_fit` keeps only the `L`
  values with exactly two resonances. If `reso_list` comes back short or empty: widen
  the sweep, check the range of `L_list`, or loosen `tolY` (1e-8 default; 1e-6 was needed
  for the readout).
* `RangeCount=24001` with an interpolating sweep is cheap. Keep it: the storage mode
  is very narrow.

### Checks

* The plot: simulated and fitted branches lie on top of each other over the whole
  range. A fit that misses the gap or the slope means wrong bounds or a third mode.
* `tul.Ec_of_C(C_T)` within about 5 % of the Q3D `Ec`. `L0_T` about 1 nH for the
  Sisyphus transmon, and the same in all three qubit BBQ blocks (1.01, 1.11, 1.10 nH).
* `f` of the other mode within about 1 % of its eigenmode value.
* `dual_annealing` is stochastic: `g` repeats to 3 digits when the fit is good. Each fit
  takes 1-2 min.

### Accuracy and coarse runs

Measured on Sisyphus_A "To storage" (2026-11-13):

| | fine: 20 passes, 30 um | coarse: 4 passes, 100 um |
|---|---|---|
| solve time | 1 min 42 s | 45 s |
| `g` (T-stor) | 18.33 MHz | 18.67 MHz |
| storage f | 4.456 GHz | 4.444 GHz |
| `C_T` | 97.15 fF | 92.32 fF |
| `L0_T` | 1.008 nH | 1.008 nH |

`g` to a storage post is robust to 2 %. Blocks with a resonator in the model cost more
(34 min for the readout with 6 passes) and depend on the trace mesh: keep the same mesh
settings between iterations when you compare.

`setup.update_property('Passes', ...)` and `('Solution Freq', ...)` do take effect in
AEDT, but `setup.props` does not show them. To read the live values:
`o = hfss.odesign.GetChildObject('Analysis').GetChildObject(setup.name); o.GetPropValue('Passes')`.

The notebook sets `Solution Freq`, `Passes` and the sweep in every driven block, so
these need no restoring between blocks. If your last driven block was a test, leave the
setup as the template had it (Sisyphus `Network`: 8.344 GHz, 20 passes, sweep
7.9-8.3 GHz, 24001 points, tolerance 0.01, 3000 solutions).

## Reso BBQ

Helper `reso_bbq_fit` (copy verbatim):

```python
L_list, reso_list, fit_list, f1, f1_to_L, f1_to_L2, f2, g = reso_bbq_fit(freqs, Y, L_list)
```

The port is cut into the readout resonator, so the lumped `L` in series tunes the
resonator: `f(L) = f1 + f1_to_L*(L - Lmid) + f1_to_L2*(L - Lmid)**2`. `f2` is the bare
frequency of the other mode and `g` the coupling in GHz, directly between two
oscillators (`g*(at + a)(bt + b)`). Fit bounds: `f1` 2-9, `f1_to_L` -2..0,
`f1_to_L2` -0.5..0.5, `f2` 4-9 GHz, `g` 0-0.2 GHz.

Render the two systems, add the transmon junction as lumped RLC on a sheet named `JJ_T`
if the transmon is part of the model, then cut the port into the middle of the meander
(verbatim from Sisyphus_A):

```python
# add reso JJ
meander = hfss.modeler['trace_read_reso']

# find proper port position
n = len(meander.vertex_positions)//8 //2
coords = np.asarray(meander.vertex_positions[n*8 + 4:n*8+8])

# building proper rectangle
lx = max(np.abs(coords[0, 1] - coords[1, 1])*0.1, 0.1)
ly = np.abs(coords[0, 1] - coords[1, 1])

rect = hfss.modeler.create_rectangle(orientation=hfss.PLANE.XY,
                                     origin=np.average(coords, axis=0) - np.asarray([lx/2, ly/2, 0]),
                                     sizes = [f'{lx}mm',
                                              f'{ly}mm'],
                                     name='JJ_hole',
                                     is_covered=True,
                                    )

# remove `tool_obj` from `blank_obj`; blank_obj is what remains
hfss.modeler.subtract(meander, 'JJ_hole', keep_originals=False)

rect = hfss.modeler.create_rectangle(orientation=hfss.PLANE.XY,
                                     origin=np.average(coords, axis=0) - np.asarray([lx/2, ly/2, 0]),
                                     sizes = [f'{lx}mm',
                                              f'{ly}mm'],
                                     name='JJ',
                                     is_covered=True,
                                    )

# assign lumped port to JJ sheet
hfss.lumped_port('JJ', integration_line=0, name='JJ_port')
```

* The cut is made in a straight segment that runs along x, hence `integration_line=0`.
  This vertex arithmetic belongs to the Sisyphus meander. For another route, print
  `meander.vertex_positions` first and check with a screenshot that `JJ` sits across the
  trace, in the middle of a straight segment.
* Mesh: `['JJ', 'trace_read_reso', ...]` under `meander_mesh`; `['JJ_T', tapers]` under
  `transmon_mesh`.
* Extract `Y` exactly as in the qubit block.
* Cleanup needs one more line: `hfss.modeler.delete('JJ_T')`.

| Block | Render | Sweep | `L_list` | Stores |
|---|---|---|---|---|
| To storage | `T`, tapers, `read_reso`, pads | 4.3-4.6 GHz, 5 passes | `np.linspace(4.8, 5.6, 101)` | `g_dict['read-stor_via_T']` |
| To filter | `filter_reso`, `read_reso`, pads (no transmon) | 8-9 GHz, 5 passes | `np.linspace(-0.15, 0.3, 101)` | `g_dict['read-filter']`, `f_dict['filt_bbq_r']` |

`L_list` here is found by trial: start wide (for example `np.linspace(-0.5, 8, 201)`),
plot `reso_list`, then narrow to the crossing. Negative `L` is allowed; it only means the
resonator is tuned upwards.

## Save

```python
with open(data_path + '<Design>_f_dict.pkl', 'wb') as f: pickle.dump(f_dict, f)
with open(data_path + '<Design>_Ec_dict.pkl', 'wb') as f: pickle.dump(Ec_dict, f)
with open(data_path + '<Design>_g_dict.pkl', 'wb') as f: pickle.dump(g_dict, f)
with open(data_path + '<Design>_Ej_dict.pkl', 'wb') as f: pickle.dump(Ej_dict, f)
```

## What moves g

| Coupling | Geometry knob |
|---|---|
| transmon - storage post | transmon position along the chip (`T_y`), pad size and `pad_gap` (dipole length) |
| transmon - readout | distance between `read_reso_pad_A` (open end) and the lower pad; pad area |
| transmon - filter | set by distance; meant to be small (1 MHz in Sisyphus_A) |
| readout - filter | distance between the resonator ends, `CirclePad` radius |

Changing the pads also changes `Ec`: re-run the Q3D block after such a change.
