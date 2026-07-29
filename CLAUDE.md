# barpath

Reconstruct barbell path from a single Apple Watch IMU and render it as an
overlaid 2D plot. Proof of concept only — not an app, not a product.

Read `NON_GOALS.md` before proposing anything. Its Scope section is binding.
Its Estimation and Sensing rejections were deleted on 2026-07-28 because they
rested on synthetic evidence — recover them with `git show HEAD:NON_GOALS.md`
if you want to re-argue one, but do not treat them as still in force.

## Spec

The number that decides every engineering question:

**Horizontal accuracy target: ~1 cm.**

It comes from the display, not the physics. Horizontal excursion is a few
centimetres against half a metre of lift, so the plot stretches the
horizontal axis ~4x — which magnifies error by the same factor. Above ~1 cm
you stop showing someone their bar path and start inventing faults for them.

Vertical: ±2–3 cm. Rep timing: ±50 ms. Absolute position in the room: not
needed, ever.

What matters is **rep-to-rep difference**, not absolute truth. A path
systematically 1.5 cm forward of truth is fine if it is consistently so.

That argument is load-bearing and it has a known hole. It holds for error
that is constant across a set, which largely cancels in the comparison. It
does **not** hold for error correlated with the motion — the body-frame accel
bias projected through a rotating forearm, or Core Motion's gravity reference
cutting out at the same phase of every rep. That error repeats with the rep,
so the comparison preserves it perfectly. Do not invoke "it's common-mode"
without saying which of the two you mean.

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

`synth.py` generates logs from a known bar path with injected bias. It was
the keystone and is no longer. Its model of lifting is wrong in ways real
captures have now measured — it emits stationary windows between reps, which
loaded lifting does not have, and a constant accel bias, which the real one is
not. Every stage passed against it and several fail on real data, so as a
referee it certifies broken stages.

What it is still good for is algebraic identities that hold regardless of how
lifting behaves: round-tripping `to_world`, integrating a known acceleration,
recovering an injected bias. Those catch sign and frame-convention bugs that
no gym capture can see. Use it for that and let real data judge whether the
pipeline works.

## Learning contract

The owner is learning this domain. That is a goal of the project, not an
obstacle to it.

**Every file is collaborative.** `orient.py`, `integrate.py`, `correct.py` and
`project.py` used to be reserved for the owner; that restriction is lifted as
of 2026-07-28. There is nothing you may not edit.

The learning goal survives the lockout that used to enforce it, and it changes
*how* you work in those modules rather than *whether* you do:

- Explain the mechanism before or alongside changing it, not instead of.
- When a change encodes a judgement about the physics — what error model, what
  assumption about the motion — say what the judgement is and what would
  falsify it. A diff that silently picks one is worse than no diff.
- Prefer handing back a diagnosis with a plot over a fix the owner cannot
  evaluate. Speed is not the constraint here; understanding is.
- Conceptual questions still get a conceptual answer. Do not answer "why does
  this drift" with a patch.

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

- Use plan mode for anything changing the pipeline's shape, or changing an
  assumption about the error model rather than the code implementing it.
- Work one open problem at a time, and state which one. A change that is not
  attached to a problem in the list below needs a reason.
- A gate only counts if it runs on real captures. Synthetic gates are unit
  tests now, not evidence.
- Commit when a problem's status changes — including to "worse" — plots
  included. The record of what was tried and failed is worth as much as the
  fix.
- Prefer deleting code to adding it. That still holds, but it is no longer a
  licence to keep rejections alive past their evidence: `NON_GOALS.md` lost its
  Estimation and Sensing tables on 2026-07-28 for exactly that reason.
- When a concept or bug is hard to see in numbers, **plot the data**. A graph
  of the intermediate signal — per-rep overlays, drift vs signal, before/after
  a stage — routinely makes clear in seconds what a table of numbers hides. The
  owner is learning the domain, so reach for a plot at troublesome spots rather
  than only explaining in prose. Render to the scratchpad and view it.
- **A change is not finished until every document it falsifies is fixed, in the
  same commit.** The docstring is part of the diff, not a follow-up. This is not
  tidiness: the failure that costs time here is a claim that outlives its
  evidence, and the claim is usually in prose. Milestones 1–6 passed on gates
  that no longer tested anything; `NON_GOALS.md` kept rejections whose evidence
  had expired; the reserved-module banners survived the lockout being lifted by
  a day and the disproved `correct.py` premises by longer. When you change
  behaviour or learn a fact, grep for what now reads false — module docstrings
  first, then `CLAUDE.md`, `TASKS.md`, `README.md`, `analysis/README.md`,
  `src/README.md`, `watch/README.md`, test docstrings. Correct the old reasoning
  rather than deleting it; what was believed and why it was wrong is the record
  this project runs on.

## Open problems

The milestone table is gone. Milestones 1–6 all passed and the project does
not work; a schedule that reports success while the artefact fails is worse
than no schedule. What survived it is real: the watch logger works, and
`data/raw/` holds 10 captures, all labelled with rep counts and totalling 44
reps (4 bench, 3 squat, 3 deadlift). The room and warm-up captures were
removed in `7004c32` because no video exists for them; measurements made
before that commit say 13 captures and are correct as of when they were taken.

Work the problems instead. Each is stated with the evidence that it is real,
so it can be closed by evidence rather than by opinion.

**P1 — Rep counting is solved; boundary phase is verified only on deadlift.**
*Counting:* closed by A1. 44/44 reps across all 10 captures with zero false
positives, against the old stationary detector's 0 of 14 bench and 1 of 15
squat. That detector assumed a quiet window between reps and loaded lifting has
none — only 13.5% of a deadlift capture qualifies, essentially all of it the
pre-set pause.

*What is still open:* where each window sits, not how many there are. Counts
cannot see phase — the segmenter scored a perfect 44/44 while every window ran
lockout-to-lockout, half a rep out of step. Deadlift boundaries now come from
floor impacts, which use raw acceleration alone and match video to 13.5 ms, and
all 15 deadlift windows contain exactly one video lockout. **Bench and squat
have no such anchor.** They still segment on integrated velocity carrying 145 cm
of in-band error against a 69 cm signal, so their phase is unverified and will
stay that way until P3 is fixed. This is not a segmentation problem.
*Evidence:* `analysis/04`–`07`, `12` for the old failure; `15`–`18` for A1;
`17` and `src/README.md` for the phase bug.

**P2 — Horizontal is drift-dominated by two orders of magnitude.** Paused
bench reconstructs to ~1 m fore-aft against a real 0.1–0.2 m. The spec is
1 cm. Vertical timing and structure come out fine; the side-on view is not
trustworthy at all. Since A4 the same failure is measured through the pipeline
itself rather than off-pipeline: horizontal excursion comes out at **66–253 cm**
where real is 10–20 cm. *Evidence:* `analysis/13`, and the A4 section of
`analysis/README.md`.

**P3 — The per-rep linear detrend's premise is violated.** It was justified on
errors being smooth and monotonic while true motion is periodic and closes.
But the accel bias is fixed in the *body* frame and the forearm rotates
through the rep, so in the world frame that error is periodic **at rep
frequency** — the one shape a per-rep line cannot separate from real motion.
`calibrate.accel_bias`'s own docstring says so. P2 most likely lives here.

**P4 — Calibration is below its own noise floor.** The "stillest" window
carries 7.2 °/s peak-to-peak of ~6.5 Hz physiological tremor; the bias being
extracted from it is 0.1–0.9 °/s. Block-resampled standard error of the mean
is 0.16–0.36 °/s, and the observed spread was 0.33–0.47 °/s across the 13
captures held when this was measured — meaning the capture-to-capture variation
is tremor, not bias. More captures will not help; the estimator is the limit.

**P5 — Apple's residual gyro bias is unobservable with what we log.**
`dm.rotationRate` is already bias-corrected by Core Motion, so the logger
records the residual after an opaque, time-varying internal estimate. Logging
raw `CMGyroData` alongside would expose that estimate directly by difference.
Raw accelerometer adds nothing — `userAccel + R⁻¹·g` already reconstructs it
exactly (9.8065 m/s² measured at rest against 9.80665 expected).

Validate on **deadlift** first — not because the pipeline differs by lift
(it does not) but because it is the only lift with external ground truth:
the bar starts at plate radius (22.5 cm to bar centre) and ends at a
tape-measurable lockout height. Bench and squat offer nothing to check
against but your own judgement of whether a curve looks plausible, which is
exactly how you convince yourself a broken pipeline works.
