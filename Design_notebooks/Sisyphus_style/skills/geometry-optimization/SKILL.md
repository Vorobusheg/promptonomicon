---
name: geometry-optimization
description: Tune chip geometry in a Sisyphus-style design notebook until simulated parameters (qubit Ec and frequency, resonator frequencies, couplings g, external Q / kappa, chi, Purcell limits) meet targets - which geometry knob moves which quantity, the order of tuning, how to iterate with coarse HFSS/Q3D runs and correct for the coarse-mesh offset, when to stop, when to ask before a long run, and how to record the iterations. Use when asked to optimise, tune, retarget or "make the design hit" some values.
---

# Geometry optimisation loop

Needs: a notebook that already runs (skill `design-notebook-workflow`), and targets.

## 1. Fix the targets first

Write them as a table before any run and confirm with Andrei if he did not give
tolerances:

| Quantity | Target | Tolerance | From block |
|---|---|---|---|
| f01, alpha (or `Ec`) | | 1 % on `Ec` | Q3D |
| resonator frequencies, or their detuning | | 10-20 MHz absolute, or the detuning | bare eigenmode |
| `g` or chi | | 5 % | BBQ, Summary |
| `Qc` / kappa | | 10 % | pin S-parameter |
| Purcell limit | at least ... ms | | Summary |

`Ej_dict['T']` is an input. If a target cannot be met by geometry at the given `Ej`
(f01 at fixed alpha), say so; do not change `Ej` without asking.

## 2. Knob -> quantity map (Sisyphus-type device)

| Knob (drawing variable) | Main effect | Side effects |
|---|---|---|
| pad size `pad_R_mm`, `pad_height_top/bot`; `pad_gap_mm` | `Ec` (so f01, alpha) | every `g` of the transmon, `pin_q`; taper geometry follows the pad (`l`, `k`) |
| `Ej_dict['T']` -> `JJ_width` (input, ask) | f01 at fixed `Ec` | chi, Purcell through detunings |
| `total_length` of a `RouteMeander` | that resonator's frequency (`f` ~ `1/length`) | detunings, so chi and Purcell; slightly its `g` and `Qc` |
| transmon position `T_y` | `g` transmon-storage; `pin_q` | `g` transmon-readout (distance to the resonator end) |
| position of a resonator end (`read_reso_pad_A` `pos_y`) relative to a transmon pad | `g` transmon-resonator | resonator frequency |
| distance between the two resonators' ends | `g` readout-filter | both frequencies a little |
| `CirclePad` `R`, pad position relative to the pin (`pin_y`) | filter `Qc` | filter frequency |
| template variables (`pin_h`, `hhh`, `drift`, `narrow_pin_h`) | `Qc`, `pin_q` | these are the cavity, not the chip: change only if Andrei asks |

Constraints that are easy to break: components inside the chip box and the pocket;
the meander must still fit (`design.components[name].options._actual_length` equals the
requested `total_length`); the chip box must not overlap template solids.

## 3. Order of tuning

Each step uses the cheapest block that sees the quantity, and earlier steps are
disturbed least by later ones.

1. **`Ec`**: pads, with the Q3D block (coarse run, 1 min, `Ec` good to 3 digits).
2. **Resonator frequencies**: lengths, with the bare eigenmode (coarse, under 1 min).
3. **Couplings `g`**: positions and distances, with the BBQ blocks (coarse, 1-3 min plus
   1-2 min fit).
4. **`Qc`**: pad near the pin, with the pin S-parameter block (coarse, 2 min).
5. **Summary**: chi and Purcell from the dictionaries (seconds). Chi depends on `g` and
   on detunings, so step 5 may send you back to 2 or 3.
6. Repeat 1-5 once: steps 3 and 4 moved the frequencies and `Ec` a little.

Change **one knob per run** while you are learning the sensitivities. Once you have
them, several independent knobs can move together (pad size for `Ec` and a resonator
length do not interact strongly).

## 4. One iteration

1. Change the variable in its drawing cell. Keep the previous value as a trailing
   comment (`R = 0.7#0.8`).
2. Re-run that cell and `gui.rebuild()`. Save and look at the picture.
3. Cleanup of the target design if needed, connect, render, coarse settings, analyze,
   extract, process, cleanup.
4. Add a row to the log (section 6).
5. Compute the next value:
   * proportional quantities directly: `L_new = L_old * f_sim / f_target`;
     for `Ec` with total capacitance, `C_new/C_old = Ec_old/Ec_new`
     (`tul.C_of_Ec`, `tul.Ec_of_C`);
   * otherwise a secant step from the last two points:
     `x_new = x1 + (y_t - y1)*(x1 - x0)/(y1 - y0)`. Limit the step to a factor of 2 in
     the quantity and stay inside the geometric constraints;
   * for a coupling through a gap, work with `log(g)` against distance: it is closer to
     a straight line.
6. Stop when inside tolerance, or after 5 runs of one knob without progress: then
   report what limits it.

`scipy.optimize` on top of HFSS is not needed for one or two knobs and wastes runs. If
a real multi-parameter problem appears, propose the approach to Andrei first.

## 5. Coarse runs and their offset

Coarse settings (measured on Sisyphus_A, 2026-11-13; details in each block's skill):

| Block | Coarse settings | Time | Coarse minus fine |
|---|---|---|---|
| Q3D | `PerError=2`, 2-6 passes | 48 s | `Ec` 0 %, f01 -6 MHz, `pin_q` +30 % |
| bare eigenmode (filter) | trace mesh 100 um, 2-4 passes | 17 s | f -1.0 % (-83 MHz), Q +12 % |
| qubit BBQ to storage | 4 passes, 100 um | 45 s + fit | `g` +2 %, f -0.3 %, `C_T` -5 % |
| pin S-parameter (filter) | 5 passes, 100 um | 92 s | `fr` -2 % (-160 MHz), `Qc` -1.5 % |

(The HFSS coarse tests were run with `chip_y = 18500` instead of 18800, to avoid the
overlap with `wafer_edge`; the silicon end is far from all three structures, so the
differences above are mesh effects.)

Use them like this:

* **Compare like with like.** A trend is only valid between runs with identical mesh and
  pass settings. Write the settings into the log.
* **Calibrate once.** If a fine result for some geometry exists (from Sisyphus_A's saved
  dictionaries, or one fine run you asked for), the offset `fine - coarse` at that
  geometry carries over to nearby geometries. Aim the coarse runs at
  `target - offset`.
* **Do not tune below the noise.** Coarse frequencies are good to about 1 %, so a
  detuning of 50 MHz between two 8 GHz resonators cannot be set with separate coarse
  runs. Either simulate both resonators in one model (same mesh, the difference is
  better than the absolute values), or go fine.
* Small quantities (`pin_q`, a 1 MHz coupling, `Qc` of 1e6) need fine settings from the
  start.
* Mark coarse values in the cell the way Andrei does:
  `maximum_length="100um", #"10um",` and `setup.update_property('Passes', '4') # '20'`.
  Restore pass settings that no cell sets (eigenmode, Q3D) in the cleanup cell, with the
  known template numbers written out, not with values read back from `setup.props`
  (that view shows the last saved project, not the live one).

## 6. Log of iterations

Keep the history in a dictionary that is saved like the others, and show it as a plot
(style rule: plots before big tables) under `# Summary` -> `## Optimization log`:

```python
opt_dict.setdefault('log', [])
opt_dict['log'].append({'step': 3, 'knob': 'filter total_length, mm', 'value': 3.84,
                        'quantity': 'filter_bare, GHz', 'result': 8.261, 'target': 8.344,
                        'settings': 'coarse: 100um, 4 passes'})
```
```python
log = pd.DataFrame(opt_dict['log'])
for q, part in log.groupby('quantity'):
    plt.figure(figsize=(8, 6))
    plt.plot(part['step'], part['result'], 'o-', color='blue', alpha=0.5, label='result')
    plt.axhline(part['target'].iloc[-1], color='black', linestyle='dashed', label='target')
    plt.xlabel('step')
    plt.ylabel(q)
    plt.title(f"{q} vs {', '.join(part['knob'].unique())}")
    plt.grid(True, alpha=0.3)
    plt.legend()
    plt.tight_layout()
    plt.show()
display(log.tail(5))
```
```python
with open(data_path + '<Design>_opt_dict.pkl', 'wb') as f: pickle.dump(opt_dict, f)
```

`opt_dict` is not in Sisyphus_A: it was added for agent-run optimisation and Andrei
accepted it on 2026-11-13 on the condition that it stays small. Initialise it in the
second setup cell with the other dictionaries. The notebook itself always shows only
the current geometry; the log is the memory of how it got there.

### Keeping the log small

A row as above costs about 53 bytes in the pickle (measured: 1000 rows = 53 kB,
10000 rows = 0.5 MB). It stays that way only under these rules:

* **A row holds Python numbers and short strings, nothing else.** No numpy arrays, no
  frequency sweeps, no Y or S traces, no capacitance matrices, no DataFrames, no fit
  objects, no copies of `design` options or of other dictionaries. Convert numpy scalars
  with `float(...)` before appending.
* **One row per finished simulation run and per quantity looked at.** Not one per
  adaptive pass, not one per point of a frequency sweep, not one per re-run of a
  Summary cell.
* **Bulk data goes to its own file, the row gets the file name.** If a run produced a
  trace worth keeping, save it as Sisyphus_A does for sweep data
  (`data_path + '<Design>_<what>.pkl'` or `.npy`) and add `'data': '<file name>'` to the
  row. Overwrite the trace file of a knob at each step unless the old trace is needed;
  do not keep one trace per step by default.
* **One file, overwritten.** Always dump to the same `<Design>_opt_dict.pkl`; never
  write `..._step3.pkl` copies or time-stamped backups.
* **One log per design.** Do not carry the log of design A into the notebook of
  design B; start an empty one and name the parent design in the first row's
  `settings`.
* **Plot, then a short tail.** The display cell plots each quantity against the step
  and shows only the last 5 rows as a table, so the notebook output does not grow with
  the log. The full table is one line away: `pd.DataFrame(opt_dict['log'])`.
* A repeated identical run (same knob value, same settings) replaces its old row; it
  does not add one.

If a log passes about 500 rows, something is wrong with the search (see section 4):
stop and report instead of appending further.

## 7. Time budget and asking

* Coarse runs: free. Keep a running total and mention it in the report.
* Ask before any single run or loop expected above about 30 min. That includes: the
  fine verification of each block, the complete eigenmode (10 h), any template-variable
  sweep, any loop over chip geometry with more than a handful of points.
* When you ask, give: what, why now, expected time (use the table in
  `design-notebook-workflow`), and what you will do meanwhile.
* While a long run is going, the kernel is busy and AEDT is solving. Do not start a
  second kernel against the same AEDT session.

## 8. Final verification

After the coarse loop converged:

1. Put production settings into the cells (the commented values become active, the
   coarse ones are removed).
2. Ask, then run the blocks in pipeline order with fine settings. Save after each.
3. Re-run Summary. Compare with targets and with the coarse prediction.
4. If a fine result misses its tolerance, do one corrected iteration with the offset now
   known exactly.
5. Report coarse and fine values side by side.
