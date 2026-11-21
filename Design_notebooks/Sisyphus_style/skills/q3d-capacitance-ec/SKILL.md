---
name: q3d-capacitance-ec
description: Capacitance (Q3D) block of a Sisyphus-style notebook - render the transmon into the Q3D template design, solve the capacitance matrix, convert it with tul.lom_c_matrix_convert and tul.legendre_forward into the transmon charging energy Ec and the effective pin charge pin_q, then get f01 and anharmonicity with tul.transmon. Use when the qubit Ec, frequency, anharmonicity or direct coupling to the drive pin must be computed or tuned by pad geometry.
---

# Capacitance (Q3D) -> Ec, pin_q, f01, alpha

Reference: `Sisyphus_A.ipynb`, `## Capacitance (Q3D)`. Shared mechanics (connect,
render, cleanup, checks): skill `aedt-render-cleanup`. Fine run: 5 min; coarse: 1 min.

## Cells

```python
q3d = Q3d(version=ansys_version, project='Sisyphus', design='Capacitance')
```
```python
fourq_q3d = design.renderers.q3d
fourq_q3d.start()
fourq_q3d.activate_ansys_design('Capacitance')
```
```python
# add transmon to design
fourq_q3d.render_design(['T', 'taper_p1', 'taper_p2'], box_plus_buffer=False)

# delete autoground
q3d.modeler.delete('ground_main_plane')
```
```python
q3d.analyze('Setup')
```
```python
C_lom = fourq_q3d.get_capacitance_matrix()
display(C_lom[0])
print('unit:', C_lom[1])
```

`C_lom[0]` is the Maxwell capacitance matrix as a DataFrame in fF, one row per net. Net
names are object names. For Sisyphus: `Cavity_V1` (the cavity = ground), `pad_bot_T`,
`pad_top_T`, `Pin`. The tapers touch the pads and belong to the pad nets. If more nets
appear than expected, two shapes that should be one conductor do not touch: fix the
drawing.

```python
# order island names
island_sequence = []
island_sequence.append('pad_bot_T -> T_bot')
island_sequence.append('pad_top_T -> T_top')

# order pins names
pins = []
pins.append('Pin -> pin')

# conver C_lom to fancy form
C_df, C_pins_df = tul.lom_c_matrix_convert(C_lom[0], island_sequence, pins=pins, physical=False)

display(C_df)
display(C_pins_df)

C = np.asarray(C_df)
C_pins = np.asarray(C_pins_df)

# add jj capacitance
C[0, 1] += tul.C_of_Ej(Ej_dict['T'], Ej_to_S=exp_vars['Ej_to_S'])
```

* `'old -> new'` renames and orders the islands. Every net except one must be listed as
  island or pin: `len(island_sequence) + len(pins)` = number of nets - 1. The net that
  is left out is the ground (here `Cavity_V1`).
* `physical=False` gives the reduced form: diagonal = capacitance of the island to
  ground, upper triangle = capacitance between islands (positive), lower triangle zero.
  `C_pins[i, j]` = capacitance between island `i` and pin `j`.
* The junction capacitance is added between the two pads, element `[0, 1]`.

```python
# transfer matrix
S = np.eye(C.shape[0])

# first mode will be amtisym = transmon
S[0, 1] = -1
S[1, 0] = 1

Ec, pin_q = tul.legendre_forward(C, C_pins=C_pins, S=S)
print(f'Transmon Ec = {np.around(Ec[0, 0], 3)} GHz')
s, _, n = tul.transmon(Ej_dict['T'], Ec[0, 0], truncation=20)
print(f'f01: {np.around(s[1], 3)} GHz\nalpha: {np.around(s[2] - 2*s[1], 3)} GHz')
print(f'pin_q: {np.around(pin_q[0, 0], 3)} GHz/mV')

Ec_dict.update({'Ec_T':Ec})
Ec_dict.update({'pin_q':pin_q})
Ec_dict.update({'C':C})
Ec_dict.update({'C_pins':C_pins})

f_dict.update({'T':s[1]})
f_dict.update({'alpha':s[2] - 2*s[1]})
```

* `S` changes variables from the two pad nodes to (difference, sum). Row 0 is the
  antisymmetric mode, the transmon. For a two-pad floating transmon always use this `S`.
* `Ec` is a matrix in GHz: diagonal = charging energies in the `4*Ec*n^2` convention,
  upper triangle = coupling between modes. `Ec[0, 0]` is the transmon `Ec`.
* `pin_q[i, j]` (GHz/mV) is the effective charge of mode `i` seen by pin `j`.
  `pin_q[0, 0]` is the transmon-to-pin coupling used for the direct decay through the
  pin: `kappa = tul.kappa_n(f01, pin_q[0, 0]) * abs(n[0, 1])**2` (GHz),
  `T1 = 1/(2*np.pi*kappa)` (ns).
* `tul.transmon(Ej, Ec, truncation)` returns `(spectrum, phi, n)`: the spectrum starts
  at 0, so `s[1]` is f01 and `s[2] - 2*s[1]` the anharmonicity; `n` is the charge
  operator in the eigenbasis (needed later in Summary).

Then the cleanup cell (Q3D version, guarded: skill `aedt-render-cleanup`) and

```python
# save
with open(data_path + '<Design>_Ec_dict.pkl', 'wb') as f: pickle.dump(Ec_dict, f)
with open(data_path + '<Design>_f_dict.pkl', 'wb') as f: pickle.dump(f_dict, f)
```

## Accuracy and coarse runs

The template setup `Setup` asks for 0.1 % error with 5 to 20 passes (`AccuracyLevel`
Highest). For a quick look relax it (end of the render cell), and put the template
numbers back in the cleanup cell, before the connection is released:

```python
q3d_setup = q3d.setups[0]
q3d_setup.props['Cap'].update(MaxPass=6, MinPass=2, MinConvPass=1, PerError=2)   # coarse test
q3d_setup.update()
...
q3d_setup.props['Cap'].update(MaxPass=20, MinPass=5, MinConvPass=2, PerError=0.1)   # template values
q3d_setup.update()
```

Write the template numbers out. Do not read "the original" back from
`q3d_setup.props` in the same session: that view comes from the last saved project file
and can already contain your coarse values.

Measured on Sisyphus_A (2026-11-13), coarse against fine:

| | fine (4 min 53 s) | coarse (48 s) |
|---|---|---|
| pad-to-ground C | 114.98 / 114.07 fF | 112.07 / 113.88 fF |
| pad-to-pad C | 33.55 fF | 34.36 fF |
| `Ec` | 0.207 GHz | 0.207 GHz |
| f01 | 6.096 GHz | 6.090 GHz |
| pad-to-pin C | 0.0465 / 0.0039 fF | 0.0595 / 0.0048 fF |
| `pin_q` | 0.110 GHz/mV | 0.143 GHz/mV |

So a coarse run is good for `Ec`, f01 and alpha (use it to tune pad size and gap), and
not good for `pin_q` (capacitances of 0.01 fF need the fine setup).

## What moves what

| Want | Change | Direction |
|---|---|---|
| lower `Ec` (lower f01, smaller abs(alpha)) | larger pads (`pad_R_mm`, `pad_height_*`), smaller `pad_gap` | more pad-to-pad and pad-to-ground C |
| f01 at fixed `Ec` | `Ej_dict['T']` (junction area, i.e. `JJ_width`) | f01 is about `sqrt(8*Ej*Ec) - Ec` |
| `pin_q` (direct pin coupling) | distance and height of the pin: a template variable (`pin_h`, `narrow_pin_h`), or the transmon position `T_y` | closer pin = larger `pin_q` |

Inverse problem without a simulation: `tul.transmon_search(f01, alpha)` gives the
`(Ej, Ec)` that produce a wanted f01 and anharmonicity; `tul.C_of_Ec(Ec)` the total
capacitance that corresponds to an `Ec`.

## Sweep of a template variable (optional, long)

Sisyphus_A, `## Special transmon pin / ### Q3D`: one render, then a `tqdm` loop that
sets `q3d.variable_manager.set_variable(name="narrow_pin_h", expression=f"{h}mm",
overwrite=True)`, solves (three tries), converts as above and calls `np.savez` after
every point. 51 points took 4.5 h: ask before running, and set the variable back to its
original value in the cleanup cell.
