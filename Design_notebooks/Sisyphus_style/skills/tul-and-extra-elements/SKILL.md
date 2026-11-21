---
name: tul-and-extra-elements
description: Reference for Andrei's own libraries used in design notebooks - tiny_useful_lib (tul) for circuit physics (unit conversions, transmon and oscillator spectra, capacitance-matrix to Ec, coupled-system diagonalisation, kappa and Purcell formulas, BBQ root finding, CPW resonators) and extra_elements / extra_rendering for Qiskit Metal components. Use before writing any calculation or geometry code, to find the existing function or component instead of writing a new one, and to follow the rule for proposing a new function.
---

# tul and extra_elements: look here before writing code

Rule (from `sisyphus_style.md`, section 7): **use what exists; a new function is a last
resort and must be announced.** This skill is the map of what exists.

## Where the code is, and how to read it

| Package | Import | Source |
|---|---|---|
| `tiny_useful_lib` | `import tiny_useful_lib as tul` (everything is at top level; `tul.scaling` is a submodule) | `Github\quantum-circuits\tiny_useful_lib\` : `equations.py`, `single_elements.py`, `coupled_elements.py`, `circuits.py`, `math.py`, `scaling.py` |
| `extra_elements` | `from extra_elements.<group> import <Class>` | `Github\quantum-metal-extension\extra_elements\` : `jjs`, `cpw`, `general`, `coils`, `text` |
| `extra_rendering` | `from extra_rendering import copy_group, transform_group` | `Github\quantum-metal-extension\extra_rendering\` |

Both are editable installs in the `metal` env, so the files in `Github\` are what runs.
Read-only for you.

Every `tul` function has a docstring with `Parameters:` and `Returns:` and units. Read
it before use (search the source for `def <name>`, or `nbrun.py code --conn $k
"help(tul.<name>)"`). Find candidates with
`[x for x in dir(tul) if 'kappa' in x]`.

Units everywhere in `tul`: GHz (ordinary frequency), fF, nH, ohm, mm for CPW lengths,
mK, `pin_q` in GHz/mV, flux in flux quanta.

## tul by task

### Conversions and small formulas (`equations.py`)

| Function | Does |
|---|---|
| `Ec_of_C(C)`, `C_of_Ec(Ec)` | fF <-> GHz |
| `El_of_L(L)`, `L_of_El(El)` | nH <-> GHz. `L_of_El(Ej)` is the linear junction inductance |
| `C_of_Ej(Ej, Ej_to_S=400, C_to_S=45)` | junction capacitance (fF) from Ej through the junction area |
| `Ej_of_R(R)`, `R_of_Ej(Ej)` | Ambegaokar-Baratoff, R in kOhm |
| `Ej_of_F_SQUID`, `F_of_Ej_SQUID` | SQUID Ej against flux |
| `f_of_osc(El, Ec)`, `Z_of_osc(El, Ec)` | LC oscillator frequency and impedance |
| `n_zpf(Z)`, `phi_zpf(Z)` | zero-point fluctuations of an oscillator of impedance Z |
| `capacitive_coupling(C, C_1, C_2)` | `g`, `Ec_1`, `Ec_2` of two capacitively coupled islands |
| `pin_q_of_C(C_pin, C)` | effective pin charge from a coupling capacitor |
| `N_termal(f, T)` | thermal photon number |

### CPW lines and resonators (`equations.py`)

| Function | Does |
|---|---|
| `lambda_of_f(f, Z_0=50, c_cpw=169)` | wavelength in mm |
| `f_of_resonator_cpw(L, c, Z_in, Z_out, ...)` | mode frequencies of a CPW of length L with given terminations (`'open'`, `'short'`, ohm, or a function) |
| `Z_of_cpw(f, L, c, Z_l)` | input impedance of a loaded line |
| `Z_of_resonator_mode`, `El_of_resonator_mode`, `C_of_resonator_mode` | lumped equivalents of a resonator mode |

### Single systems (`single_elements.py`)

| Function | Returns |
|---|---|
| `transmon(Ej, Ec, truncation=10, Q=0)` | `(spectrum, phi, n)`, spectrum from 0, operators in the eigenbasis |
| `transmon_search(f01, alpha)` | `(Ej, Ec)` |
| `transmon_L(Ej, Ec, Ecj, El, ...)` | transmon with series inductance |
| `oscillator(f, Z=None, truncation=20)` | `(spectrum, at, a)`, or `(spectrum, phi, n)` if Z is given |
| `fluxonium(Ej, El, Ec, ...)`, `fluxonium_search(...)` | fluxonium spectrum and inverse |

### Coupled systems (`coupled_elements.py`)

| Function | Does |
|---|---|
| `mix_two_sys(spectrum_1, spectrum_2, V_12, V_21, truncation)` | diagonalise `H_1 + H_2 + V_12*V_21`; returns `(spectrum, (key, selfhood))`; `key[i, j]` = index of the dressed state of bare `(i, j)` |
| `mix_three_sys(...)` | the same for three systems |
| `mix_oscillators(f, g)` | dressed frequencies of linearly coupled oscillators; returns `(f_dressed, X, Y)` |
| `dressed_states_map`, `keys` | the labelling used inside the mix functions |
| `trans_isolation`, `side_transitions` | search for unwanted nearby transitions under a drive |

### Capacitance matrices (`circuits.py`)

| Function | Does |
|---|---|
| `lom_c_matrix_convert(C_init, island_sequence, pins=[], physical=False)` | Q3D matrix (DataFrame) -> ordered island matrix and island-to-pin matrix |
| `legendre_forward(C, C_pins=None, S=None)` | C (fF) -> `Ec` matrix (GHz) and `pin_q` (GHz/mV), in the variables defined by `S` |
| `legendre_backward(Ec, pin_q=None, S=None)` | the inverse: target `Ec` -> capacitances |
| `legendre_forward_opt(...)` | search for a C matrix near a start that gives a target `Ec` and `pin_q` |
| `cross_talk_solver(M)` | drive vectors that compensate crosstalk |

### Loss rates, Purcell, scattering (`equations.py`)

| Function | Does |
|---|---|
| `kappa_n(f, pin_q, Z=50)` | decay coefficient through a capacitive pin; multiply by `abs(n_ij)**2` |
| `kappa_osc_via_osc_eq(f_a, f_b, g, kappa_a, regime)` | decay of B through lossy A, from g (input-output model of two linear oscillators; if A or B is the transmon pass `g*abs(n[0, 1])`) |
| `kappa_osc_mw`, `kappa_osc_via_osc_mw`, `kappa_osc_via_2_osc_mw` | the same from capacitances with a microwave model: one LC on a line, one or two oscillators in between |
| `scattering_osc_eq`, `scattering_osc_via_osc_eq` | S-matrix of a resonator, or of a resonator behind a Purcell filter, on a feedline |
| `transmission_line_dressing_eq`, `transmission_line_baring_eq` | f and kappa with and without the feedline loading |

### Black-box quantisation (`equations.py`)

| Function | Does |
|---|---|
| `bbq_resonances_of_Y(f, Y, L, C, tolY, kappas=False)` | zeros of `Y + 1/(i w L) + i w C`: mode frequencies (and kappas) seen from a port |
| `find_Y_zeros(Y, band, ...)` | the root finder behind it, for an admittance given as a function |

### Numerics (`math.py`)

`dagger`, `kron`, `subspace`, `expand_space`, `index_linear`, `index_coord`,
`around(x, n)` (round to n significant digits), `parabolic_fit`, `linear_regression_fit`.

### `tul.scaling`

Multi-qubit coupler studies (ZZ, gap optimisation). Not used in single-transmon cavity
designs.

## Notebook helpers that are not in tul

`qubit_bbq_fit`, `reso_bbq_fit`, `pin_q_of_kappa`: defined in Sisyphus_A, copy verbatim
(style guide, section 6).

## extra_elements components

All are `QComponent`s: `Class(design, 'name', options=dict(pos_x=..., pos_y=...,
orientation=..., layer=..., ...))`. Defaults: `Class.default_options`. Option meaning: the
class docstring.

| Group | Classes |
|---|---|
| `extra_elements.general` | `TransmonPocketTeethCustom` (pocket transmon, round pad ends, optional teeth connection pads), `RectangleFillet`, `DipoleAntennaSmooth`, `Undercut` (grows the shapes of another component onto an undercut layer) |
| `extra_elements.jjs` | `Taper`, `GoodTaper`, `Patch`, `RectanglePatch`, `JunctionManhattan`, `JunctionManhattan_cross`, `JunctionTopDown`, `JunctionChain`, and the function `manhattan_complete(design, name, x, y, JJ_width, taper_gap, evaporation_shift, undercut, slope, length, ...)` that builds tapers + patches + cross in one call |
| `extra_elements.cpw` | `CirclePad`, `CpwCoupPinFillet`, `CpwClawExtraGround`, `CPWGapConnect`, `LineTee`, `CoupledLineTeeCustom`, `CapNInterdigital`, `FingerCapacitor`, `SquareSpiralCapacitor`, `SquareSpiralInductor`, `MeanderInductor`, `MeanderDJJAA`, `DCSQUIDBetweenCPW_Fab`, `DCSQUIDBetweenCPW_noFab`, `RFSQUIDBetweenCPW_noFab` |
| `extra_elements.coils` | `ResonatorCoilByTurns`, `ResonatorCoilByTurnsWithWirebonds` |
| `extra_elements.text` | `Text`, `Arrow`, `CrossedArrows` |
| `extra_rendering` | `copy_group(design, names, suffix)`, `transform_group(design, names, dx, dy, angle, pivot)`: copy or move a set of components as a rigid body |

Standard Metal parts used with them: `RouteMeander`, `RouteStraight`, `RouteFramed`
(`qiskit_metal.qlibrary.tlines`), `OpenToGround`, `ShortToGround`
(`qlibrary.terminations`), and the rest of `qiskit_metal.qlibrary`.

A second copy of this library is in `Claude\Quantum Metal\quantum-metal-extension`
(with GDS datatype changes not yet in `Github\`). The notebook kernel imports the
`Github\` one. Do not mix them.

## If nothing fits

1. Say which functions you checked and why each falls short.
2. Prefer composing existing calls in the cell over a new `def`.
3. If a `def` is still needed, put it in the notebook under the announcement cell
   from the style guide:

```markdown
> **NEW FUNCTION (proposed by Claude): `name(args)`**
> **What:** one sentence.
> **Why not existing code:** which `tul` / `extra_elements` functions were checked and why they do not fit.
> **Where it could live:** e.g. `tiny_useful_lib/equations.py`, if Andrei wants to keep it.
```

4. Write it in `tul` style: plain numpy/scipy, the units above, a docstring with
   `Parameters:` and `Returns:`, no side effects.
5. Test it against a case with a known answer (a value in Sisyphus_A's saved
   dictionaries, or a limit where an existing `tul` function applies) and show that
   check in the notebook.
6. Repeat the announcement in your final message. Never edit the libraries.
