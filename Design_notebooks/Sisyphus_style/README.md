# Sisyphus_style

Instructions for Claude agents that build, run and optimise chip design notebooks in the
style of `Projects/GKP_cavity/notebooks/Sisyphus_A.ipynb` (Qiskit Metal drawing, Ansys
Q3D/HFSS simulation of a chip in a 3D cavity, analysis with `tiny_useful_lib`).
Extracted from that notebook on 2026-11-13. This folder is self-contained and is used by
pointing an agent at it.

Read in this order:

1. `sisyphus_style.md` : what the notebook must look like.
2. `skills/design-notebook-workflow/SKILL.md` : how to work; it links to the other skills.

| Path | Content |
|---|---|
| `sisyphus_style.md` | style codex |
| `skills/design-notebook-workflow` | pipeline, machine facts, safety rules, running cells, report |
| `skills/qmetal-chip-drawing` | drawing the chip, object names, checking the picture |
| `skills/aedt-render-cleanup` | connect, render, junction sheet, validation, guarded cleanup, template designs |
| `skills/q3d-capacitance-ec` | capacitance matrix -> Ec, pin_q, f01, alpha |
| `skills/hfss-eigenmode-modes` | bare and complete eigenmode, parametric sweeps |
| `skills/hfss-bbq-coupling` | coupling g from a Y-port sweep (qubit BBQ, reso BBQ) |
| `skills/hfss-pin-sparameter-kappa` | S11 at the pin -> f, Qc, Qi, kappa |
| `skills/design-summary-chi-purcell` | chi and Purcell limits from the dictionaries |
| `skills/geometry-optimization` | tuning geometry to targets with coarse runs |
| `skills/tul-and-extra-elements` | map of `tul` and `extra_elements`; rule for new functions |
| `tools/nbrun.py` | run notebook cells in one persistent `metal` kernel |
| `tools/aedt_check.py` | read-only check of the AEDT session before rendering |
| `playground/` | test copy of Sisyphus_A with coarse runs of 2026-11-13; not a design result |

## How to point an agent at this folder

The skills are not installed in `.claude/skills`, so no agent finds them by itself.
Name this README in the first message of the task (in VS Code, `@` + the path attaches
it), then state the task:

```text
Read @Claude/Design_notebooks/Sisyphus_style/README.md and follow it.
Task: make Projects/GKP_cavity/notebooks/Sisyphus_B/Sisyphus_B.ipynb from Sisyphus_A.ipynb with the
readout resonator at 7.9 GHz and chi/2pi of 1 MHz. Coarse runs only.
```

For a narrow job, name the one skill as well, so the agent starts there:

```text
Use Claude/Design_notebooks/Sisyphus_style (start at README.md; the relevant skill is
skills/hfss-bbq-coupling). Task: re-run the qubit BBQ block of Sisyphus_B and tell me g
to the storage.
```

Scope: one transmon and strip-line resonators on a chip inside a 3D cavity, with a
prepared HFSS template project. Planar chips with a ground plane and feedline are not
covered.
