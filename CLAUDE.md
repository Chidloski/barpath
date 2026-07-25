# barpath

Reconstruct barbell path from a single Apple Watch IMU and render it as an
overlaid 2D plot. Proof of concept only — not an app, not a product.

Read `NON_GOALS.md` before proposing anything. It is binding.

## Spec

The number that decides every engineering question:

**Horizontal accuracy target: ~1 cm.**

It comes from the display, not the physics. Horizontal excursion is a few
centimetres against half a metre of lift, so the plot stretches the
horizontal axis ~4x — which magnifies error by the same factor. Above ~1 cm
you stop showing someone their bar path and start inventing faults for them.

Vertical: ±2–3 cm. Rep timing: ±50 ms. Absolute position in the room: not
needed, ever.

What matters is **rep-to-rep difference**, not absolute truth. Error is
common-mode across the reps of one set and largely cancels in the
comparison, so the tight requirement happens to sit on the best-conditioned
quantity. A path systematically 1.5 cm forward of truth is fine if it is
consistently so.

## Pipeline

Nine steps, one module each, numbered to match.

0. `io.py` — load log. Never assume fixed dt. Core Motion reports g, not m/s².
1. `calibrate.py` — gyro bias from the stillest window in the pre-set pause.
2. `orient.py` — correct attitude by that bias.
3. `orient.py` — rotate acceleration into the world frame.
4. `integrate.py` — cumulative trapezoidal, twice.
5. `segment.py` — stationary detection, then rep boundaries by vertical position.
6. `correct.py` — subtract the wrist-to-bar offset R(t)·d.
7. `correct.py` — per-rep linear detrend so each rep closes.
8. `project.py` — PCA on horizontal displacement picks the display axis.
9. `plot.py` — overlay reps, aligned by start point, horizontal stretched 4x.

`synth.py` generates logs from a known bar path with injected bias. It is the
keystone: ground truth on the desk means you can tell which stage broke,
not just that something did.

## Learning contract

The owner is learning this domain. That is a goal of the project, not an
obstacle to it.

**Reserved — the owner writes these. Do not implement them, do not fill in
the stubs, do not write "a quick version to get things running".**

- `src/orient.py`
- `src/integrate.py`
- `src/correct.py`
- `src/project.py`

You may review this code, find bugs in it, explain the concepts behind it,
and write tests against it. When asked a conceptual question, explain the
mechanism and stop there.

Everything else is yours: I/O, plotting, test scaffolding, the Swift logger,
synthetic generator plumbing, refactors.

If a reserved module is blocking progress, say so and wait. Do not route
around it.

## Conventions

- SI internally. Convert Core Motion's units of g at the I/O boundary, once.
- World frame: x, y horizontal (heading unknown until step 8), z up.
- Attitude quaternions stored **w, x, y, z**. SciPy uses x, y, z, w — convert
  at every boundary. This has bitten before.
- Use the per-sample `dt` array. The watch does not always honour the
  requested rate, and a baked-in interval is an invisible scale error.
- `data/raw/` is immutable and gitignored. Re-deriving from raw is trivial;
  re-collecting from a gym is not.

## Working style

- Use plan mode for anything touching a reserved module or changing the
  pipeline's shape.
- One milestone at a time. Each has a numeric gate in `tests/`. Do not start
  the next before the current one passes.
- Commit at every gate, plots included.
- Prefer deleting code to adding it. This project has already discarded
  Kalman filters, factor graphs, spline fits and UWB ranging, and is better
  for it.
- When a concept or bug is hard to see in numbers, **plot the data**. A graph
  of the intermediate signal — per-rep overlays, drift vs signal, before/after
  a stage — routinely makes clear in seconds what a table of numbers hides. The
  owner is learning the domain, so reach for a plot at troublesome spots rather
  than only explaining in prose. Render to the scratchpad and view it.

## Milestones

| # | Deliverable | Gate |
|---|---|---|
| 1 | Synthetic generator + I/O | zero-error log encodes truth exactly |
| 2 | Calibration | injected gyro bias recovered to <0.01 °/s |
| 3 | Orientation | attitude within 0.5°; world accel exact |
| 4 | Integration | clean path recovered to <1 mm |
| 5 | Segmentation | every rep found; turnaround pauses rejected |
| 6 | Detrend + projection | full pipeline <1 cm horizontal |
| 7 | Watch logger | 100 Hz CSV off the device, sane timestamps |
| 8 | Real deadlift | integrated ROM within 3 cm of tape measure |
| 9 | Bench and squat | paths match video |

Milestones 1–6 need no watch and no gym.

Validate on **deadlift** first — not because the pipeline differs by lift
(it does not) but because it is the only lift with external ground truth:
the bar starts at plate radius (22.5 cm to bar centre) and ends at a
tape-measurable lockout height. Bench and squat offer nothing to check
against but your own judgement of whether a curve looks plausible, which is
exactly how you convince yourself a broken pipeline works.
