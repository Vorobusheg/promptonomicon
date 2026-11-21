---
name: design-summary-chi-purcell
description: Summary section of a Sisyphus-style notebook - turn the stored dictionaries (Ec, pin_q, g, bare frequencies, Qe) into device numbers with tiny_useful_lib - transmon spectrum, dispersive shift chi with each resonator, decay through the pin, and Purcell limits through a resonator or filter. Use when writing or checking the "Summary" / "Chi" cells, when asked for chi, kappa, T1 limits or a comparison of a design with its targets, and when judging whether an optimisation step helped.
---

# Summary -> chi, kappa, Purcell limits

Reference: `Sisyphus_A.ipynb`, `# Summary`. No Ansys here: these cells read only the
dictionaries, so they run in seconds and can be re-run after every change.

Everything is in GHz (ordinary frequency). A rate `kappa` in GHz corresponds to a time
`1/(2*np.pi*kappa)` in ns; multiply by `1e-6` for ms, `1e-3` for us.

## Transmon from the stored Ec

```python
# init
print(f'Transmon Ec = {np.around(Ec_dict['Ec_T'][0, 0], 3)} GHz')
s, _, n = tul.transmon(Ej_dict['T'], Ec_dict['Ec_T'][0, 0], truncation=20)
print(f'f01: {np.around(s[1], 3)} GHz\nalpha: {np.around(s[2] - 2*s[1], 3)} GHz')
print(f'pin_q: {np.around(Ec_dict['pin_q'][0, 0], 3)} GHz/mV')
print(f'fat pin decay: {np.around(1/(2*np.pi*tul.kappa_n(s[1], Ec_dict['pin_q'][0, 0])*np.abs(n[0, 1])**2)/1e6, 3)} ms')
```

* `s` spectrum (starts at 0), `n` charge operator in the transmon eigenbasis. Both are
  reused by every cell below, so this cell runs first.
* Direct decay of the 0-1 transition into a 50-ohm pin:
  `kappa_q = tul.kappa_n(s[1], pin_q) * np.abs(n[0, 1])**2`.

## Chi with a resonator

```python
g = g_dict['T-read']
freq_r = f_dict['read_bare']
kappa_r = freq_r/Qe_dict['read_via_pin_S']
s0, a, at = tul.oscillator(freq_r)
sm, (key, selfhood) = tul.mix_two_sys(s, s0, n, g*(a+at), truncation=20)
print(f'chi: {(sm[key[1, 1]] - sm[key[0, 1]] - sm[key[1, 0]])/2*1e3} MHz')
```

* `tul.oscillator(f)` returns `(spectrum, at, a)`; only the sum `a + at` is used.
* `tul.mix_two_sys(spectrum_1, spectrum_2, V_12, V_21, truncation)` diagonalises
  `H = H_1 + H_2 + V_12*V_21`: it takes the operators of the two subsystems and
  combines them in the perturbation term. With `V_12 = n` (the full transmon charge
  operator, so all its matrix elements are included) and `V_21 = g*(a + at)`, the `g` of
  the qubit BBQ block goes in unchanged. This is Andrei's convention, confirmed
  2026-11-13: **`g` = `g_capacitive * n_zpf` of the oscillator; the transmon side is
  never folded into `g`.**
* `key[i, j]` is the index in `sm` of the dressed state that belongs to the bare state
  (transmon level `i`, oscillator level `j`). `selfhood` tells how much of the bare state
  is left in it; values well below 1 mean strong hybridisation and unreliable labels.
* **Andrei's chi is `(E11 - E01 - E10)/2`**: half of the shift of the resonator
  frequency between qubit states 0 and 1. Keep this definition and say "chi" only for
  it.
* Print in MHz for the readout, kHz for storage and filter (`*1e6`).
* Storage: `g_dict['T-stor']`, `f_dict['storage']`. Filter: `g_dict['T-filt']`,
  `f_dict['filter_bare']`.

## Purcell limit through a lossy oscillator

```python
kappa = tul.kappa_osc_via_osc_eq(freq_r, s[1], g*np.abs(n[0, 1]), kappa_r, regime='cut')
print(f'transmon Purcell limit via readout: {1/2/np.pi/kappa*1e-6} ms')
```

`tul.kappa_osc_via_osc_eq(f_a, f_b, g, kappa_a, regime)`:

| Argument | Meaning |
|---|---|
| `f_a`, `kappa_a` | the oscillator that is coupled to the line: its frequency and its linewidth, GHz |
| `f_b` | the system behind it whose induced decay is wanted |
| `g` | coupling between the two as linear oscillators, GHz. **If one of them is the transmon, pass `g*np.abs(n[0, 1])`** (see below) |
| `regime='cut'` | the line ends at the device (one port, reflection), which is the case for a single coupling pin. `'pass'` is a hanger on a through line. |
| returns | `kappa_b`, GHz |

Keep the argument order straight: **first the lossy one, second the protected one.**
Uses in a Sisyphus-type device:

| Question | Call |
|---|---|
| transmon decay through the filter | `tul.kappa_osc_via_osc_eq(f_dict['filter_bare'], s[1], g_dict['T-filt']*np.abs(n[0, 1]), kappa_f, regime='cut')` with `kappa_f = f_dict['filter_bare']/Qe_dict['filter_via_pin_S']` |
| transmon decay through the readout's own pin coupling | `tul.kappa_osc_via_osc_eq(f_dict['read_bare'], s[1], g_dict['T-read']*np.abs(n[0, 1]), kappa_r, regime='cut')` |
| effective readout linewidth through the filter | `tul.kappa_osc_via_osc_eq(f_dict['filter_bare'], f_dict['read_bare'], g_dict['read-filter'], kappa_f, regime='cut')` (both are resonators: `g` unchanged; a rate: print in MHz as "readout kappa via filter") |
| storage decay through the transmon | `tul.kappa_osc_via_osc_eq(s[1], f_dict['storage'], g_dict['T-stor']*np.abs(n[0, 1]), kappa_q, regime='cut')` with `kappa_q` from the pin (above) |

`mode_info=True` returns `(kappas, freqs, participations)` of both dressed modes instead.

Label each printed line with what it is ("transmon Purcell limit via filter", "readout
kappa via filter"). In Sisyphus_A several lines carry the copied label
"direct purcell limit", two cells use `f_dict['filter_bare']` for the readout, two
calls have `f_a` and `f_b` the other way round, and the transmon calls pass the stored
`g` without `abs(n[0, 1])`: do not copy those cells blindly, write them from the table
above.

### Which `g` goes where (settled with Andrei, 2026-11-13)

The stored `g_dict['T-...']` is `g_capacitive * n_zpf` of the oscillator. The transmon
side is supplied separately each time:

| Function | Transmon side enters through | What to pass |
|---|---|---|
| `tul.mix_two_sys(s, s0, n, g*(a+at))` (chi) | the full operator `n` | stored `g`, unchanged |
| `tul.kappa_osc_via_osc_eq(...)` (Purcell) | nothing: it has no operator argument and models two linear oscillators with exchange coupling `g` | `g*np.abs(n[0, 1])`, with `n` from the init cell |
| `tul.mix_oscillators(...)` inside `qubit_bbq_fit` | nothing, same reason | `g*tul.n_zpf(Z_T)` (already in Andrei's helper) |

Rule: a function that takes operators gets the stored `g`; a function that takes only a
number for the coupling to a transmon gets `g` times the transmon 0-1 charge matrix
element. Calls between two resonators (readout through filter) take the stored `g`.

Size of the effect in Sisyphus_A (`abs(n[0, 1])` = 1.355; the rate scales about as its
square, 1.84):

| Limit | stored `g` (as printed in Sisyphus_A) | `g*abs(n[0, 1])` (correct) |
|---|---|---|
| transmon via filter | 42.05 ms | 22.90 ms |
| transmon via readout pin coupling | 56.56 ms | 31.03 ms |
| storage via transmon | 77.7 s | 42.3 s |

## Other tul functions for this section

| Function | Use |
|---|---|
| `tul.mix_three_sys(...)` | transmon + two oscillators in one diagonalisation |
| `tul.mix_oscillators(f, g)` | dressed frequencies of coupled linear oscillators |
| `tul.kappa_osc_via_osc_mw`, `tul.kappa_osc_via_2_osc_mw` | same question from capacitances and a microwave model (one or two oscillators in between, feedline details); needs C values, not g |
| `tul.kappa_osc_mw` | kappa of one LC through a coupling capacitor |
| `tul.transmon_search(f01, alpha)` | `(Ej, Ec)` for a wanted transmon |
| `tul.N_termal(f, T)` | thermal photons at temperature T (mK) |
| `tul.scattering_osc_eq`, `tul.scattering_osc_via_osc_eq` | S-matrix of a resonator, or a resonator behind a filter, to compare with a measured or simulated trace |

## Targets table

When targets were given, end the Summary with one table (design value, target,
difference) built with `pd.DataFrame` and `display`. That table is what the
optimisation loop looks at and what goes into the report.

## Consistency checks before reporting

* `f_dict['T']` (Q3D + Ej, non-linear) is above `f_dict['T_egm']` (linear mode with the
  lumped L) by roughly `Ec`: 6.096 against 5.785 GHz in Sisyphus_A.
* The same mode from different blocks agrees within about 1 %:
  `storage` / `storage_bbq`, `read_bare` / `read_bbq` / `read_via_pin_S`,
  `filter_bare` / `filt_bbq` / `filter_via_pin_S`.
* `tul.Ec_of_C(Ec_dict['C_bbq'])` close to `Ec_dict['Ec_T'][0, 0]`.
* Eigenmode `Q` of a bare resonator and `Qc` of the S11 fit have the same order of
  magnitude.
* Dispersive regime: `g*abs(n[0, 1])` much smaller than the detuning; otherwise `key`
  labels and chi lose meaning (look at `selfhood`).

A mismatch is a finding. Report it; do not average it away.
