---
name: hfss-pin-sparameter-kappa
description: Pin S-parameter block of a Sisyphus-style notebook - HFSS driven sweep of the reflection S11 at the coupling pin port (line_port), fitted with resonator_tools to get resonance frequency, coupling Q (Qc), internal Q and kappa of a resonator or filter; also the Y-port variant that gives the transmon decay through a pin, and sweeps of a pin height. Use when an external Q, linewidth kappa or T1 limit through the pin must be computed or tuned.
---

# Pin S-parameter -> f, Qc, Qi, kappa

Reference: `Sisyphus_A.ipynb`, `## Pin S-parameter` and `## Special transmon pin`.
Shared mechanics: skill `aedt-render-cleanup`. Template design: `Network` (driven
modal). Its port `line_port` (50 ohm, on the coax sheet `Line`) is part of the template
and is the only port in these blocks: the junction is a lumped RLC, not a port.

## Cells (filter)

```python
# connect to HFSS
hfss = Hfss(version=ansys_version, project='Sisyphus', design='Network')

fourq_hfss = design.renderers.hfss
fourq_hfss.start()
fourq_hfss.activate_ansys_design('Network')
```
```python
fourq_hfss.render_design(['T', 'taper_p1', 'taper_p2', 'filter_reso',
                          'filter_reso_pad_A', 'filter_reso_pad_B'], box_plus_buffer=False)
hfss.modeler.delete('ground_main_plane')
hfss.modeler.delete('sample_holder')


# add JJ inductance and capacitance
gap_mm = taper_gap/1e3+ 2*float(length_cut_taper[:-2])/1e3
rect = hfss.modeler.create_rectangle(orientation=generic.constants.Plane.XY,
                                     origin=[0 - 0.022/2, float(T_y[:-2])/1e3 - gap_mm/2, 0],
                                     sizes = ['0.022mm', f'{gap_mm}mm'],
                                     name='JJ',
                                     is_covered=True,
                                    )

hfss.assign_lumped_rlc_to_sheet('JJ', start_direction=1, name='JJ_RLC',
                                inductance=f'{tul.L_of_El(Ej_dict['T'])}n',
                                capacitance=f'{tul.C_of_Ej(Ej_dict['T'], Ej_to_S=exp_vars['Ej_to_S'])}f')

#  assign the JJ mesh
hfss.mesh.assign_length_mesh(['JJ', 'taper_main_taper_p1', 'taper_main_taper_p2'], inside_selection=False, maximum_length="30um",
                             name='transmon_mesh', maximum_elements=None,)


#  assign the meander mesh
hfss.mesh.assign_length_mesh(['trace_filter_reso'], inside_selection=False, maximum_length="30um",
                             name='meander_mesh', maximum_elements=None,)

# create sweep
setup = hfss.get_setup(hfss.get_setups()[0])
setup.update_property('Solution Freq', f'{f_dict['filter_bare']}GHz')
setup.update_property('Passes', '20')
hfss.oanalysis.DeleteSweep(setup.name, setup.get_sweep_names()[0])
sweep = setup.add_sweep(name='Sweep', sweep_type='Interpolating')
sweep.props.update(RangeStart=f'{7.6}GHz', RangeEnd=f'{9}GHz', RangeCount=24001, InterpTolerance=0.01, InterpMaxSolns=3000)
sweep.update()
```
```python
# start simulation
hfss.analyze(setup=hfss.get_setups()[0])
```
```python
data = hfss.post.get_solution_data(expressions=['re(S(line_port,line_port))', 'im(S(line_port,line_port))'], primary_sweep_variable="Freq")
S = data.data_real("re(S(line_port,line_port))")+1j*data.data_real("im(S(line_port,line_port))")
freqs = np.asarray(data.primary_sweep_values, dtype=float)
```
```python
# fit
pin = rfit.reflection_port()
pin.add_data(freqs*1e9, S)
pin.autofit(electric_delay=0)

pin.plotall()
display(pd.DataFrame([pin.fitresults]).applymap(lambda x: "{0:.2e}".format(x)))
print(f'bandwidth: {np.around(pin.fitresults['fr']/pin.fitresults['Ql']*1e-6, 3)} MHz\n')

f_dict.update({'filter_via_pin_S':pin.fitresults['fr']/1e9})
Qe_dict.update({'filter_via_pin_S':pin.fitresults['Qc']})
Qi_dict.update({'filter_via_pin_S':pin.fitresults['Qi']})
```

then the guarded cleanup cell, and after the last block of the section

```python
with open(data_path + '<Design>_Qi_dict.pkl', 'wb') as f: pickle.dump(Qi_dict, f)
with open(data_path + '<Design>_Qe_dict.pkl', 'wb') as f: pickle.dump(Qe_dict, f)
with open(data_path + '<Design>_f_dict.pkl', 'wb') as f: pickle.dump(f_dict, f)
```

* `freqs` from HFSS is in GHz; `resonator_tools` wants Hz, hence `freqs*1e9`.
  `pin.fitresults['fr']` is in Hz: **store it as `fr/1e9`**, GHz, like every other
  frequency. (Sisyphus_A stores `T_via_pin_S` in Hz: a slip.)
* `electric_delay=0`: the port is at the device, there is no cable.
* `pin.fitresults` keys: `Qi`, `Qc`, `Ql`, `fr`, `theta0`, `*_err`, `chi_square`.
  `Qc` is the external Q through the pin, `Qi` everything else (radiation, numerical
  loss; with lossless materials it is large and noisy).
* `kappa = f/Qc` in GHz is what the Summary uses:
  `kappa_f = f_dict['filter_bare']/Qe_dict['filter_via_pin_S']`.
* `pin.plotall()` opens a figure window (circle, magnitude, phase with the fit). To look
  at it: `nbrun.py code --conn $k "plt.figure(plt.get_fignums()[-1]).savefig(r'<scratch>\fit.png', dpi=90); plt.close('all')"`.

Per target:

| Block | Render | `Solution Freq` | Sweep (Sisyphus_A) | Stores |
|---|---|---|---|---|
| Filter | `T`, tapers, `filter_reso`, pads | `f_dict['filter_bare']` | 7.6-9 GHz, 20 passes | `filter_via_pin_S` in `f_dict`, `Qe_dict`, `Qi_dict` |
| Readout | `T`, tapers, `read_reso`, pads | `f_dict['read_bare']` | 8.34-8.4 GHz, 5 passes | `read_via_pin_S` |
| Complete | everything | | 7.6-9 GHz, `InterpTolerance=0.1` | plot of `np.abs(S)` on a log axis, no fit |

## Choosing the sweep range

* Wide resonance (filter, Q about 130, 63 MHz wide): a range of 10 to 20 linewidths
  around the eigenmode frequency.
* Narrow resonance (readout through its own pin coupling, Qc 2.5e6, 3 kHz wide): the
  range must be narrow enough that the line is resolved. Point spacing is
  `(RangeEnd - RangeStart)/RangeCount`; keep at least about 10 points inside the
  linewidth `f/Q`, estimated from the bare eigenmode `Q`. With 24001 points and a 3 kHz
  line that means a span of a few MHz, centred on the resonance. The resonance moves
  with the mesh, so first locate it (coarse eigenmode or a first wide sweep), then zoom.
* Only one resonance inside the fitted range. For a model with several modes plot
  `np.abs(S)` first and cut the arrays before fitting.

## When the fit means nothing

Check before storing:

* `fr` lies inside the swept range and on the dip you see in the plot;
* `Qc_err/Qc` and `Ql_err/Ql` below about 1 % (Sisyphus_A cleans its sweeps with
  `Qe_err/Qe < 0.01 and Qe > 100`);
* `chi_square` small (1e-3 for the filter, 1e-6 for the readout), fit on top of the
  data in all three panels.

In Sisyphus_A the block `### Transmon (cannot see)` returned `Qc` about 1 and `fr`
outside the range: the transmon mode is not visible in S11 of the main pin. That is the
case for any mode whose external coupling is much weaker than the numerical loss
floor. Do not store such a result. Use the Y-port method below or the capacitive route
(`pin_q` from Q3D with `tul.kappa_n`).

## Accuracy and coarse runs

Measured on the Sisyphus filter (2026-11-13):

| | fine: 20 passes, 30 um meshes | coarse: 5 passes, 100 um meshes |
|---|---|---|
| solve time | 19 min 25 s | 1 min 32 s |
| `fr` | 8.339 GHz | 8.18 GHz |
| `Qc` | 132 | 130 |
| bandwidth `fr/Ql` | 63.4 MHz | 63.1 MHz |

`Qc` of a strongly coupled resonator is robust to the mesh; its frequency is not
(2 % low here). Tune `Qc` with coarse runs, frequencies with the eigenmode block.

## Transmon decay through a pin: Y-port variant

Sisyphus_A, `## Special transmon pin / ### Y-port` (design `Special_pin`): the junction
is a lumped **port** `JJ_port` as in the qubit BBQ block, the sweep covers
`f_dict['T_egm'] +/- 0.3` GHz, and both quantities are read:

```python
data = hfss.post.get_solution_data(expressions=['re(S(line_port,line_port))', 'im(S(line_port,line_port))',
                                                're(Y(JJ_port,JJ_port))', 'im(Y(JJ_port,JJ_port))'], primary_sweep_variable="Freq")
Y = data.data_real("re(Y(JJ_port,JJ_port))")+1j*data.data_real("im(Y(JJ_port,JJ_port))")
S = data.data_real("re(S(line_port,line_port))")+1j*data.data_real("im(S(line_port,line_port))")
freqs = np.asarray(data.primary_sweep_values, dtype=float)
```
```python
tmp = tul.bbq_resonances_of_Y(freqs, Y, tul.L_of_El(Ej_dict['T']), C=tul.C_of_Ej(Ej_dict['T']), kappas=True)
f = tmp[0][0]
kappa = tmp[1][0]
pin_q = pin_q_of_kappa(kappa, f)
print(f'frequency: {np.around(f, 3)} GHz\npin_q: {np.around(pin_q, 3)} GHz/mV\nT1 limit: {np.around(1/kappa/2/np.pi*1e-6, 3)} ms')
```

`tul.bbq_resonances_of_Y(..., kappas=True)` returns `(frequencies, kappas)` in GHz: the
complex zero of the loaded admittance gives the linewidth directly, with the 50-ohm
`line_port` as the only loss. `pin_q_of_kappa` (Andrei's helper, copy verbatim) converts
it into an effective pin charge so it can be compared with the Q3D `pin_q`.

Three ways to the same number exist in Sisyphus_A and they do not agree closely
(`pin_q` of the narrow pin at `narrow_pin_h = -3.4mm`: 1.26 GHz/mV from Q3D, 0.087 from
the Y-port). When
asked for a pin-limited T1, say which method produced it.

## Sweep of a template variable (pin height)

One render, then a loop in the notebook (Sisyphus_A, `narrow_pin_h`):

```python
h_list = np.linspace(-4.75, -3.75, 51)
Qi_list = np.zeros(h_list.shape[0])
Qe_list = np.zeros(h_list.shape[0])
Qe_err_list = np.zeros(h_list.shape[0])
f_list = np.zeros(h_list.shape[0])

for n in tqdm.tqdm(range(h_list.shape[0])):
    # define pin length
    hfss.variable_manager.set_variable(name="narrow_pin_h", expression=f"{h_list[n]}mm", overwrite=True)

    for m in range(3):
        # start simulation
        res = hfss.analyze(setup=hfss.get_setups()[0])
        if(res): break

    data = hfss.post.get_solution_data(expressions=['re(S(line_port,line_port))', 'im(S(line_port,line_port))'], primary_sweep_variable="Freq")
    S = data.data_real("re(S(line_port,line_port))")+1j*data.data_real("im(S(line_port,line_port))")
    freqs = np.asarray(data.primary_sweep_values, dtype=float)

    # fit
    pin = rfit.reflection_port()
    pin.add_data(freqs*1e9, S)
    pin.autofit()

    Qi_list[n] = pin.fitresults['Qi']
    Qe_list[n] = pin.fitresults['Qc']
    f_list[n] = pin.fitresults['fr']
    Qe_err_list[n] = pin.fitresults['Qc_err']

    np.savez(data_path+'transmon_to_pin_coupling_S', h_list=h_list, f_list=f_list, Qi_list=Qi_list, Qe_list=Qe_list, Qe_err_list=Qe_err_list)
```

* Everything the loop body needs is defined inside the loop or in the cell above it. (The
  Y-port sweep of Sisyphus_A uses an `L` left over from another cell: do not repeat.)
* 51 points took 3 h, 101 points 5.5 h: ask first, and start with 5 points to see the
  trend.
* Set the variable back to the template value in the cleanup cell.
* A later cell loads the `.npz`, drops bad fits and plots kappa and T against the
  variable.

## What moves Qc

| Want | Change |
|---|---|
| stronger coupling of the filter to the pin (lower `Qc`) | pad nearer to the pin or larger: `CirclePad` `R`, `pin_y`/`pos_y`; pin deeper (template variable `pin_h`, `hhh`) |
| readout linewidth | mostly through the filter: `g_dict['read-filter']` and the filter `Qc` (skill `design-summary-chi-purcell`), not its direct `Qc` |

Moving or resizing a pad changes the resonator frequency too: re-run the bare
eigenmode after it.
