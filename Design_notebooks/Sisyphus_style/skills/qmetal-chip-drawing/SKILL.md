---
name: qmetal-chip-drawing
description: Draw the chip in Qiskit Metal for a Sisyphus-style design notebook - design and chip setup, layers, the transmon with tapers and a Manhattan junction, CPW meander resonators with open or circle-pad ends, using qiskit_metal.qlibrary and Andrei's extra_elements. Use when writing or changing the "Wafer drawing" section, when a geometry parameter must be changed, or when you need to check what the drawing looks like and what the HFSS objects will be called.
---

# Drawing the chip in Qiskit Metal

Cell layout and code style: `sisyphus_style.md`, section 4. Reference:
`Sisyphus_A.ipynb`, section `## Wafer drawing`.

## Design and chip

```python
# metal GUI initialization
design = metal.designs.DesignPlanar()
gui = metal.MetalGUI(design)
design.overwrite_enabled = True
```
```python
# setup basic chip parameters
design._variables = {'cpw_width':'50um', 'cpw_gap':'10um'}
chip_x = 2500
chip_y = 18800
design.chips.main.size.size_x = f'{chip_x}um'
design.chips.main.size.size_y = f'{chip_y}um'
design.chips.main.size.size_z = '-500um'
design.chips.main.size.center_y = '-1.75mm'
design.chips.main
```

* `design.overwrite_enabled = True` lets you re-run a component cell after changing a
  number; the component is replaced. `design.delete_all_components()` in its own cell
  gives a clean start.
* The chip box is what HFSS gets as the silicon solid `main` (rendering with
  `box_plus_buffer=False` uses exactly this size and centre). **It must fit the
  template design.** The chip must not overlap any solid that is already in the template
  (in Sisyphus: `wafer_edge`, silicon, y from -16 to -11.0 mm). With `chip_y = 18800`
  and `center_y = '-1.75mm'` the chip starts at y = -11.15 mm, overlaps `wafer_edge` by
  0.15 mm, and HFSS stops with "Parts main and wafer_edge intersect" (Q3D still solves).
  `chip_y = 18500` makes them touch. Ask Andrei which one is right for the design; do
  not change the template.
* The chip sits in a 3D cavity: there is no ground plane on it. Components still create
  "subtract" shapes (the transmon pocket, the CPW gap `cut_*`); they only matter because
  the renderer makes a ground sheet from them, which the simulation cells delete.
* Coordinates: x across the chip, y along it, the chip surface at z = 0, silicon below.

## Components used so far

Imports:

```python
from qiskit_metal.qlibrary.tlines.meandered import RouteMeander
from qiskit_metal.qlibrary.tlines.straight_path import RouteStraight
from qiskit_metal.qlibrary.tlines.framed_path import RouteFramed
from qiskit_metal.qlibrary.terminations.open_to_ground import OpenToGround

from extra_elements.jjs import Patch
from extra_elements.jjs import JunctionManhattan_cross
from extra_elements.jjs import Taper
from extra_elements.cpw import CirclePad
from extra_elements.general import TransmonPocketTeethCustom
```

| Component | Role in Sisyphus_A | Options that are tuned |
|---|---|---|
| `TransmonPocketTeethCustom` (`T`) | two pads with round ends in a pocket; no connection pads, `draw_jj=False`, `round_edges=True` | `pad_gap` (distance between pads), `pad_height_top/bot`, `edge_rad_top` (pad radius), `pad_width_*` (`'0.mm'` = pure round pad), `pocket_width/height` |
| `Taper` (`taper_p1`, `taper_p2`, `draw='out'`, reso layer) | the part of the lead from pad to junction area that is in the base metal; rendered to HFSS | `width_in`, `width_out`, `length`, `length_cut`, `slope`, `end_slope` |
| `Taper` (`taper_j1`, `taper_j2`, `draw='in'`, JJ layer + undercut layer, with `holes`) | the junction-layer part of the same lead; lithography only | same numbers as the `p` taper plus `undercut`, `holes` |
| `Taper` (`*_shift_1`, `*_shift_2`, demo layers) | copies shifted by the two evaporation angles to check the shadow compensation; lithography check only | `evaporation_angle='-45'/'+45'`, `evaporation_shift` |
| `Patch` (`patch_1`, `patch_2`) | bandage between junction layer and base metal | `width`, `height`, `height_extra`, `holes` |
| `JunctionManhattan_cross` (`jj`) | the cross; arm width = `JJ_width` | `width`, `length`, `x_cross`, `undercut`, `undercut_big` |
| `OpenToGround` (`read_reso_pad_A/B`) | open ends of the readout resonator, give the pin `open` | `pos_y`, `orientation`, `width_in='cpw_width'` |
| `CirclePad` (`filter_reso_pad_A/B`) | round capacitor pads at the ends of the filter resonator, pin `in` | `R`, `length`, `merging`, `pos_y` |
| `RouteMeander` (`read_reso`, `filter_reso`) | the CPW resonator between two pins | `total_length`, `fillet`, `meander.spacing`, `meander.asymmetry`, `lead.start_straight/end_straight` |

More classes exist in `extra_elements` (finger and interdigital capacitors, tees, SQUIDs,
other junction types, text, arrows) and in `qiskit_metal.qlibrary`. Look there before
thinking about a new component: skill `tul-and-extra-elements`.

`extra_elements.jjs.manhattan_complete(design, name, x, y, JJ_width, taper_gap,
evaporation_shift, undercut, slope, length, ...)` creates the junction-layer set (two
`Taper` with holes, two `Patch`, one `JunctionManhattan_cross`) in one call and returns
the element names. Prefer it for a new design instead of copying the long taper cells of
Sisyphus_A; the base-metal tapers (`taper_p*`) are still separate components.

## Numbers that tie drawing to physics

```python
JJ_width = np.sqrt(Ej_dict['T']/exp_vars['Ej_to_S'])*1.2     # um; junction area from the target Ej
```

* `exp_vars['Ej_to_S']` is Ej per junction area (GHz/um^2). The factor after the square
  root is a fabrication correction that Andrei sets; keep it visible, do not fold it in.
* `evaporation_shift`, `undercut` come from `exp_vars`.
* Resonator frequency is set by `total_length` of the `RouteMeander`. First guess for a
  half-wave resonator: `tul.f_of_resonator_cpw(L, c, 'open', 'open')` with
  `c = exp_vars['cpw_c_fF/mm']`, or `tul.lambda_of_f(f)/2`. The pads and the cavity
  shift it, so the eigenmode simulation decides.
* Merging a taper into a round pad of radius `R` at depth `h` (from Sisyphus_A):
  `l = np.sqrt(h*(2*R - h))*2` is the chord (`width_out`),
  `k = (R - h)/np.sqrt(h*(2*R - h))` is the pad slope there (`end_slope`).

## What is rendered to Ansys, and under which name

Only base-metal shapes take part in the simulations. In Sisyphus_A the simulation cells
render subsets of:

```
'T', 'taper_p1', 'taper_p2'                                   the transmon
'read_reso', 'read_reso_pad_A', 'read_reso_pad_B'             the readout resonator
'filter_reso', 'filter_reso_pad_A', 'filter_reso_pad_B'       the Purcell filter
```

The junction-layer components (`taper_j*`, `patch_*`, `jj`) are never rendered; the
junction is added in HFSS as a sheet `JJ` (skill `aedt-render-cleanup`).

An HFSS object is named `<qgeometry name>_<component name>`:

| Metal component | HFSS / Q3D objects |
|---|---|
| `T` | `pad_top_T`, `pad_bot_T` (the pocket `rect_pk_T` is consumed by the ground sheet) |
| `taper_p1` | `taper_main_taper_p1` |
| `read_reso` | `trace_read_reso` (`cut_read_reso` is consumed) |
| `filter_reso_pad_A` | `taper_main_filter_reso_pad_A` |
| chip | `main` (silicon box), `ground_main_plane`, and in HFSS `sample_holder` |

Mesh operations, the port cut into a resonator and the Q3D net names all use these
names. If you rename a component, update the simulation cells.

## Checking the drawing (through `nbrun.py code`, not in notebook cells)

Picture of the whole chip or of a region:

```python
gui.autoscale(); gui.figure.savefig(r'<scratch>\chip.png', dpi=150)
```

For a detail, set the view first (`gui.zoom_on_components(['jj'])` or
`gui.canvas`/axes limits) and save again. Then read the PNG.

Component list, object names, layers and extents:

```python
for t in design.qgeometry.get_element_types():
    tab = design.qgeometry.tables[t]
    for _, r in tab.iterrows():
        print(t, r['name'] + '_' + design._components[r['component']].name, r['layer'],
              r['subtract'], [round(x, 4) for x in r.geometry.bounds])
```

Check every time you change geometry:

* every component lies inside the chip box and, for the transmon, inside its pocket;
* shapes that must be one conductor overlap or touch (pad and taper, resonator trace
  and its pad): otherwise Q3D reports extra nets and the lumped JJ sheet does not
  connect the two pads;
* no unintended overlap between different conductors;
* the meander has the length you asked for: `RouteMeander` cannot always fit
  `total_length` between the pins with the given spacing and fillet. Compare
  `design.components['read_reso'].options._actual_length` (a string such as
  `'10.22 mm'`; Sisyphus_A: read 10.22 mm, filter 3.84 mm) with the request;
* `CirclePad` prints "Non-monotonic tail derivative" for some `merging`/`R`/`length`
  combinations. Sisyphus_A runs with this message; look at the pad picture and keep it
  if the outline is smooth.

Rebuild after any option change: re-run the component cell, then `gui.rebuild()`.
A changed drawing is not in AEDT until the next `render_design`.
