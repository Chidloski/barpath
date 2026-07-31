# analysis — real-data diagnostics (2026-07-26/27)

Graphs from running the current pipeline on the first real watch captures, plus
an off-pipeline reconstruction experiment. Generating scripts live in the
session scratchpad (not the repo). Data in `data/raw/`.

## Room mimics (2026-07-26, no barbell)
- `01_room_captures_accel_vel_pos.png` — vertical accel / velocity / position for
  the room deadlift + squat. Reps present but buried in drift.
- `02_room_stationarity_diagnostic.png` — rolling accel/gyro variance vs the
  stationarity thresholds. Only the calibration hold is quiet.
- `03_room_relaxed_thresholds.png` — segmentation with relaxed thresholds:
  deadlift marginally recovers 3, squat does not.

## Loaded lifts (2026-07-27)
- `04_loaded_squats_roughvert_segmentation.png`,
  `05_loaded_benches_roughvert_segmentation.png` — rough vertical with detected
  ZUPTs (blue) and rep bounds (red). Squats: 1 rep, wrong place. Benches: 0.
- `06_loaded_squats_velocity_vs_truth.png`,
  `07_loaded_benches_velocity_vs_truth.png` — drift-removed vertical velocity per
  set with truth rep count vs pipeline count. Reps are clear velocity
  oscillations the segmenter misses.

## Paused bench (`bench_92.5x2`, 2 reps, 2-count chest pause)
- `08_paused_bench_overview.png` — velocity + position, poly-detrended.
- `09_paused_bench_zoom_raw.png` — 22–36 s, minimal processing; shows drift
  dominates locally.
- `10_paused_bench_highpass_reps.png` — high-pass isolates the reps; the two
  paused reps sit at ~27 s and ~32 s (peak → pause → trough).
- `11_paused_bench_residual_bias.png` — reconstructed vertical velocity doesn't
  return to 0 at the holds: ~−0.35 m/s² (−0.035 g) residual accel bias.
  **This is the 0.035 g that P4 later reinterpreted as a 2° attitude error, and
  C6 retracted. Two things to know before quoting it: it is VERTICAL, and
  vertical leaks g·(1−cos θ) not g·sin θ; and it predates the acceleration sign
  fix (`3c2cbed`), which this reconstruction is upstream of. Through the current
  pipeline the same capture reads 0.0005 g. See the C6 section.**
- `12_paused_bench_motion_energy.png` — under load the only quiet window is the
  pre-set pause; stationarity can't find the holds.
- `13_paused_bench_reconstruction.png` — off-pipeline best-effort recon: vertical
  velocity, vertical displacement, and side-on path (two reps coloured).
  Vertical timing/structure recovered; side-on is drift-dominated (~1 m fore-aft
  vs ~0.1–0.2 m real) and NOT trustworthy.

See the session memory notes `segmentation-real-data-anchors` and
`drift-residual-orientation-dependent` for the conclusions.

## Pipeline rebuild (2026-07-28)
- `14_b1_gyro_bias_harm.png` — B1. Applying `calibrate.gyro_bias` was worse than
  bias=0 on every capture. Median per-rep-scale horizontal residual 71.5 cm ->
  4.2 cm (17x), better on 10/10, worse on 0/10. The correction is now opt-in.
- `15_a1_rep_segmentation.png` — A1. Rep windows (green) and floor impacts (red
  dotted) on all 10 captures. 44/44 reps, zero false positives, against the old
  segmenter's 0/14 bench and 1/15 squat. Note the setup burst at 5-15 s in every
  capture is correctly rejected despite being LARGER than the reps.

Caveat on both: measured with the 2 s tiled-window proxy in
`tests/test_real_data.py`, which conflates real bar movement with error. It
ranks two pipelines reliably; the absolute centimetres are not error. Rep
BOUNDARY accuracy is likewise unvalidated — counts cannot confirm placement.
Both need the video ground truth (A2).
- `16_a1_rep_windows_inspection.png` — A1 rep windows for inspection, 3 captures
  per lift, start/end marked. Every rep now contains both a concentric and an
  eccentric phase of comparable size (0/44 unbalanced, was 9/15 deadlift reps
  holding only the pull). Reps 2..n are well placed; the FIRST rep of each set
  over-extends backwards because its own eccentric is under-measured — on
  squat_130x5 rep 1 the descent registers -12.8 cm against a +57.8 cm ascent, so
  the balance search runs back to the walkout. Not a filter artefact: the median
  eccentric/concentric ratio at the 0.12 Hz corner is 0.9-1.3 across captures.
  Unresolved, and left for A2.
- `17_a2_video_ground_truth.png` — A2. Plate tracked from video on all three
  deadlifts (red), against IMU floor impacts (orange) and A1 rep windows
  (green). Sync residual 11-16 ms rms, clock drift <0.25%. This is the first
  external truth for the horizontal axis in the project.

  **It immediately found a bug in A1.** The rep windows start at the video
  lockout peak every time (16.42 vs 16.23, 19.21 vs 19.23, 22.64 vs 22.33,
  25.91 vs 25.70, 29.48 vs 29.23, 34.60 vs 34.27 on deadlift_155x6_1), so each
  window runs lockout to lockout — the descent of one rep followed by the
  ascent of the next. Half a rep out of phase, i.e. what the pipeline calls the
  concentric is the eccentric. Owner predicted this from the plots before the
  video existed. Not yet fixed.

## A4 — the driver (2026-07-28)
`python run.py` runs every capture and prints what happened; `--plot` writes
per-run diagnostics (gitignored). Two things it made visible on its first run:

- **`quality_flags` rejects 12 of 44 reps for strap resonance, wrongly.**
  *(Later 33 of 73, and the flag was removed entirely on 2026-07-30 — see #14
  in TASKS.md. It fired hardest on bench, which has no floor impact at all.)* It
  thresholds the FRACTION of accel energy above 10 Hz, so a quiet rep fails for
  having little signal at all. The rejected bench reps carry 13-18k of absolute
  high-frequency energy against 0.9-2.9M in accepted deadlift reps — 50-200x
  LESS. Its own docstring intends absolute energy.
- **Horizontal excursion is 66-253 cm** where real is 10-20 cm, quantifying the
  drift problem through the actual pipeline rather than a proxy.
  **Superseded — this number predates the acceleration sign fix (`3c2cbed`),
  which changed segmentation and so changed the reps this is measured over. It
  is 3.4-35.9 cm now.** Excursion is also a whole-set quantity that counts
  between-rep divergence, so it overstates per-rep error; use `metrics.vs_truth`
  for error and read excursion as "how much fore-aft travel the pipeline
  claims" (18-36 cm on deadlift, where the video says 8.5-15 cm).

`io.check_log` and `segment.quality_flags` were both dead code before this —
written, sound, and called by nothing but a test.

## Rep-window phase (2026-07-28)
The A2 video showed A1's windows were half a rep out of phase. Root cause is
not segmentation: band-passed IMU vertical correlates **-0.82** with video bar
height, with **145 cm of in-band error against a 69 cm signal**, and the
correlation is already only -0.16 at the ACCELERATION stage. That is P3 —
body-frame accel bias through a rotating forearm lands at rep frequency, where
no filter can reach it. The segmenter was finding genuine structure in the
error signal, which is why 44/44 counts coexisted with wrong phase.

Deadlift boundaries now come from floor impacts alone (raw acceleration
magnitude, no attitude, no integration, matched to video at 13.5 ms rms). All
15 windows contain exactly one video lockout. Bench and squat still segment on
the corrupted velocity and their phase remains unverified.

## The sign inversion (2026-07-29)
**Core Motion's `userAcceleration` is the negative of physical acceleration.**
`io.load_log` now negates it at the boundary.

Missed for months because at rest `userAcceleration` is zero, so its sign is
invisible — and every check that had been run was at the calibration pause, or
averaged over a whole pull, where the term vanishes or nets to zero. `synth.py`
encoded the same wrong convention and `orient.to_world` was built to match it,
so generator and pipeline agreed with each other and disagreed with the watch.
Exactly the failure a synthetic gate cannot see.

Caught two independent ways:
- integrating world acceleration over 0.2-0.3 s windows correlates **-0.76**
  with the video-tracked bar and **+0.76** negated. The short window is the
  point: bias contributes ~0.07 m/s there against true steps of 0.5-1.5 m/s,
  so it tests SIGN, not drift.
- the floor impact gave a **negative** velocity step on all 9 impacts across
  two captures, where a floor decelerating a falling bar demands positive.
  After the fix, 14 of 15 are positive.

Owner called this from the velocity plots — squat and bench begin with an
eccentric and deadlift with a concentric, and all three showed the opposite
sign. An earlier session had attributed it to bias instead; that was wrong,
and the tests it rested on could not have distinguished the two.
- `18_a1_rep_windows_corrected.png` — rep windows after the sign fix, same
  layout as `16`. The physical structure is now visible directly: squat and
  bench reps begin with a NEGATIVE velocity lobe (the descent) and deadlift reps
  begin POSITIVE (the pull), each closing on a floor impact. Under the old
  inverted sign every one of these was the wrong way round, which is what the
  owner spotted from plot 16. 44/44 on all ten captures.

## A3 — error, measured at last (2026-07-29)
- `19_a3_metrics.png` — `metrics.vs_truth` on all three deadlifts. Top row:
  reconstructed rep paths (grey) against the video (red), same axes, equal
  aspect. Middle row: horizontal error against the video across each rep, with
  the ±1 cm spec band. Bottom row: the three numbers side by side.

**Horizontal error as the pipeline ships it: 5.1, 9.2 and 15.4 cm rms per rep**
against a 1 cm spec. **Vertical: 6.8, 8.7 and 3.2 cm rms** against ±2–3 cm.

The middle row is the one to look at. The error is not noise and not a ramp —
it is a **single smooth arch across each rep, peaking 0.5–0.7 of the way
through**. That is P3 made visible: a body-frame accel bias projected through a
rotating forearm arrives at rep frequency, which is the one shape a per-rep
line cannot subtract and no filter can reach. It had been inferred from a
correlation before; here it is the plot.

Three things this changed:

- **The scale of the failure was overstated.** 5–15×, not two orders of
  magnitude. The older figure was whole-set excursion, which includes
  between-rep divergence that per-rep error does not.
- **Vertical is out of spec too**, on all three captures. "Vertical timing and
  structure come out fine" had been repeated since plot 13 and had never been
  measured per rep.
- **The per-rep detrend is not the problem.** Applying step 7's closure to the
  *video* as well moves the error by 0.2–0.9 cm. Its premise really is violated
  — the tracked bar misses closing horizontally by 1.9–4.3 cm — but fixing that
  buys a few centimetres out of fifteen. B3 demoted, B6 promoted.
- **The fore-aft direction is not stable within a set.** `vs_truth` picks one
  axis sign per set, as step 8 would, then counts reps preferring the other:
  **4 of 6, 2 of 6, 1 of 3**. Near a coin flip on the first. This is not a path
  with a scale error; rep to rep it disagrees with itself about which way is
  forward. New evidence for B4, and a reason to doubt that a per-set axis is
  the right object.

And the trap this metric is built to expose: **dispersion reports 0.7–1.3 cm on
bench and squat**, comfortably inside spec, where nothing whatsoever has been
verified. Error that repeats every rep lands in the mean rep and cancels out of
every deviation from it, so a pipeline dominated by P3 scores well on
rep-to-rep spread. On deadlift, where there is truth to check against,
dispersion says 4.3 cm and the video says 5.1 cm.

## The pipeline, stage by stage (2026-07-29)
- `21_pipeline_stages.png` — one column per lift, one row per stage, raw
  acceleration through to the bar path. Regenerate with `python run.py
  --stages`; it lives in `plot.plot_stages` rather than a scratch script
  because B2/B3/B6 will all change what the middle rows look like.

Read top to bottom. Four things it makes obvious that no table does:

- **Row 0 — nothing is "up" yet.** The watch's axes are glued to the case and
  tumble with the wrist, so all three body-frame traces look alike. The blue
  band is the pre-set calibration hold, where every bias estimate is made.
- **Row 2 — reps are unmistakable in velocity**, on all three lifts, which is
  why A1's segmenter works at 44/44. The deadlift's trace sliding to −6 m/s
  across the set is the drift, in plain view.
- **Row 3 — the runaway.** Two integrations turn a ~0.02 m/s² bias into 4.6 m
  of position on the squat, 1.5 m on the bench and **57.7 m** on the deadlift,
  against a lift that travels 0.6 m. The video truth is on the deadlift panel
  and looks like a flat line because the reconstruction is 82× its size.
- **Rows 4–5 — what step 7 buys back.** After the per-rep detrend the reps are
  recognisable lifts again. That is the detrend doing real work, and it is also
  why the pipeline looked fine for months: this row is convincing and the
  horizontal error is still 5× the spec.

## The watch logger, second pass (2026-07-30)
C1 (closing hold) and C3 (`phase` column) are built and typecheck clean; neither
is validated on a lift yet. **C2 is abandoned: `isGyroAvailable` is false on
watchOS**, so raw gyro cannot be logged at all and P5 is closed as permanently
unobservable. Two diagnostic captures carry its four empty columns.

## The stationary table captures (2026-07-30)
`stationary_table_20260730_000757.csv` and `stable_2_20260730_003335.csv` — a
watch on a table, recorded to verify the new logger. C2 failed on both, and they
turned out to be the most informative captures in the project anyway: the first
measurement of the sensor's own noise floor with no wrist involved, and it
**replicates across the two**.

Quiet window 6–16 s, away from the button presses at each end:

| quantity | on a table | on a wrist, calibration pause |
|---|---|---|
| gyro \|mean\| | **0.002 / 0.001 °/s** | 0.93–1.05 °/s |
| gyro p-p | 0.18 °/s | 4.2–6.0 °/s |
| block SEM | 0.0012–0.0015 °/s | 0.07–0.32 °/s |
| \|mean\|/SEM | 1.80 / 0.57 | — |
| body-frame accel bias | **0.0025 / 0.0029 g** | 0.003 g per rep, bench/squat (C6) |
| attitude drift | 0.018° / 0.071° per 8 s | — |

**Two conclusions, and they reframe P3, P4 and P5.**

The residual gyro bias is ~500× smaller than the on-wrist figure this project
has been treating as bias. It is not resolvable above its own noise. So the
0.1–0.9 °/s in P4 is the lifter's own rotation, and B1's "never apply it" is
right for a stronger reason than B1 recorded.

~~The 0.035 g on-wrist "accel bias" equals g·sin(2.0°). It is the size of a **two
degree attitude error**, not of an accelerometer bias measured at 0.0025 g. That
points the dominant error at attitude, which no constant-bias estimator can fix
— consistent with B6's oracle recovering only ~30%.~~

**RETRACTED by C6 the same day.** Two independent errors. The 0.035 g is the
*vertical* residual from `analysis/11`, and vertical leaks g·(1−cos θ), not
g·sin θ — so it implies 15.2°, not 2.0°. And it is a pre-sign-fix off-pipeline
number that does not survive: `bench_92.5x2`, the capture it came from, now
reads 0.0005 g. Core Motion's attitude measured directly at the holds is 0.05°
and 0.14°. See the C6 section below.

**A near miss worth recording.** `calibrate.stillest_window` searches the first
3 s, which is exactly when a finger is on the Calibrate button. It picked
1.55–2.54 s here, with 1.8× the motion of the genuinely quiet part, and the
resulting ~0.002 m/s² bias error produced **38 cm of horizontal drift over 19 s
on a watch that never moved** (0.48 m → 0.07 m with a clean window). On the real
deadlifts, though, it changes nothing: 5.1/9.2/15.4 → 5.1/9.1/15.1, because
step 7's per-rep detrend already absorbs exactly that quadratic. Left alone —
one capture improving is not evidence.

## B7 — the floor-impact anchor, rejected (2026-07-29)
- `22_b7_anchor_rejected.png` — the detector, the ablation, and the reason.

The idea: the bar's state at the floor is *known* (velocity zero, same height
every rep), so anchor the integration to it instead of to step 7's assumption
that the bar returns where it started. Built, measured against a decision rule
fixed in advance, and rejected.

| variant | horizontal, per capture (cm) |
|---|---|
| shipping | **5.1 / 9.2 / 15.4** |
| anchor + all-axis closure | 10.4 / 7.4 / 10.2 |
| anchor + vertical-only closure | 19.2 / 29.2 / 46.9 |
| vertical-only closure, no anchor | 495 / 522 / 337 |

**The detector is fine** (left panel). `rest_instants` puts 13 of 15 anchors
within 0.05 m/s of true rest, against 0.4–1.0 m/s at `impact_anchors` — which
marks the spike *onset*, not rest, a distinction worth 500 ms.

**The constraint is in the wrong place** (right panel). The A3 error is a
smooth arch peaking mid-rep; an impact anchor acts only at the rep boundaries,
where the error is already ~0 by construction. No amount of tuning fixes a
constraint that is true but does not reach the error.

**And the ablation found something worth more than the feature.** Row 4: the
horizontal closure that A3 called false is carrying **metres**. Remove it with
nothing in its place and error goes to 3–5 m. It is wrong *and* essential, so
B3 cannot simply drop it — the task is finding a replacement, not a deletion.

A win was claimed here and has been retracted. Fitting the detrend line through
a 5-sample median appeared to take horizontal from 5.1/9.2/15.4 to 4.6/7.8/13.4;
B2 found the gain came from a 1.7% scale error in how the drift baseline was
measured, not from the median. With the baseline fixed the median is worth
nothing. What the accident did reveal is that the closure OVER-corrects — a
deliberate 1% shrinkage gives 4.8/7.5/13.1 — which matches A3's 1.9-4.3 cm of
true non-closure. Sharp and inconsistent across captures, so not usable as a
global constant, but it is a lead for B3.

## B5 — no saturation, and a correction (2026-07-29)
- `20_b5_impact_impulse.png` — the floor impact examined four ways.

**The accelerometer does not clip.** `deadlift_180x3` peaks at 21.78 g and used
to trip a 16 g threshold that was an assumption about a sensor nobody had
checked. Bottom-right panel: the magnitude tail thins out smoothly and the peak
is hit by exactly one sample. A rail piles up at one value. `check_log` now
tests for an actual rail (`io.clipped_runs`) rather than for a large number.

**The impact impulse survives 100 Hz.** Top-left shows the whole event spanning
2–3 samples, which looks unrecoverable. It isn't: the IMU/video velocity-step
ratio is 0.77–1.19 on both 155 kg captures, median 1.04 over all 15 impacts.

**This corrects a wrong result recorded earlier in the same session.** The
first measurement claimed 16–27% of the impulse was lost, from two mistakes:
predicting arrival velocity as `sqrt(2gh)` — a touch-and-go deadlift is lowered
under control and arrives at ~2 m/s, not 3.3 — and measuring the step as a net
change across a window spanning the rise *and* the fall into the next descent.
The top-right panel is what refuted it: the IMU tracks the video straight
through the impact. Drawing the thing settled in seconds what the table of
ratios had got confidently backwards.

**What is real: `deadlift_180x3` over-reads its impact step by 58–72%**, alone
among the three, and it is also the worst capture by horizontal error. Bottom
left: its impacts sit well above the agreement line while the other two scatter
around it. Heaviest bar, hardest landing, and the first specific hypothesis for
why that capture is an outlier — pointing at strap ring, i.e. #14.

Also checked and rejected: per-rep peak g does not predict per-rep error
(correlation +0.17 across all 15 deadlift reps).

## The ROM bounds — the reconstruction passes, the referee does not (2026-07-30)
- `23_rom_bounds.png` — per-rep vertical ROM against what the lifter can
  actually move a bar through. Regenerate with `python run.py --rom`.

Two things arrived on 2026-07-30: seven more captures, and tape measurements
that replaced two standing assumptions. Plate diameters are black notched
425 mm, black bumper 445 mm, blue calibrated 450 mm — so `PLATE_DIAMETER_M`,
assumed at 450 for everything, was wrong on bench and deadlift. And per-rep
vertical ROM has ceilings for this lifter: bench 35 cm (32 typical), squat 76,
deadlift 61.

**The plate diameters were not where the error was.** Correcting deadlift to
445 mm moves the A3 numbers by under 1% — horizontal 5.1/9.2/15.4 → 5.05/9.19/
15.44, vertical 5.2/6.8/4.9 → 5.24/6.60/5.24. Worth fixing, and a useful
negative result: the scale assumption this project has flagged as a risk since
`truth.py` was written is not what makes the reconstruction 5–15× out of spec.

**The reconstruction passes the bounds** (top row). Post-step-7 per-rep ROM is
bench 24–31 cm, squat 61–68, deadlift 53–61 — inside every band, and tight
within each capture. This was the first external check bench and squat had ever
had; every other gate in the project needed floor impacts or trackable video and
they had neither. It is weak, but it is not self-referential, and they clear it.

*(As of C8, 2026-07-31, that is no longer bench's only external check — bench
video tracks and syncs, so bench has a horizontal error measurement too. It
remains squat's only one. See the C8 section.)*

Where it is measured matters. Run the same check *before* step 7 and the
numbers are absurd — `deadlift_155x6_1` climbs from 100 cm on rep 1 to 1939 cm
on rep 6. The detrend is what makes vertical dimensionally sane at all, so this
result vouches for the output of step 7 and for nothing upstream of it.

**The video ground truth fails them** (bottom row). Per-rep video ROM on the
three deadlifts, same lifter, same lift:

| capture | video ROM | plate radius | pipeline h_rms |
|---|---|---|---|
| deadlift_155x6_1 | 59.1 cm | 64 px | 5.05 cm |
| deadlift_155x6_2 | **66.8 cm** | 64 px | 9.19 cm |
| deadlift_180x3 | **47.6 cm** | 56 px | 15.44 cm |

A 19 cm spread on a range of motion set by the lifter's own limbs. Three
explanations were tested and none survives:

- **Plate diameter.** Captures 1 and 2 found the *same* radius, so no diameter
  explains a 13% gap between them.
- **Radius quantisation.** `find_plate` searches a 4 px grid. Re-run at 1 px the
  radii are 64/65/54 and the ROMs 61.2/69.2/50.8 at 450 mm — under 2% of
  movement. Not it.
- **Tracker drift.** The floor baseline holds to 0.4 cm across every clip and
  the per-capture lockouts are internally consistent (61/60/60, 70/69/64,
  49/49/48). `deadlift_180x3` has the *best* median NCC, 0.94, and the worst ROM.

What is left is the geometry. The scale is calibrated on a plate sitting on the
floor and then applied to travel reaching the top of frame — which is exactly
the assumption `truth.py`'s docstring used to state outright ("pixels to metres
is one number, not a function of height in frame"). That claim is now marked
false in the module.

**Why this matters more than it looks.** `vs_truth` is the only external judge
of P2, and on one of its three captures it measures the bar moving through
66.8 cm of a 61 cm range. Its vertical numbers on that capture are measured
with a bad ruler. The horizontal and the sync are not implicated — sync still
matches the IMU to 11–16 ms, and fore-aft travel is a few centimetres, well
inside the frame region the plate calibrates — so P2's horizontal result stands.
But P2's *spread* across captures is partly this rather than the IMU, and the
error ranking tracks the ROM error exactly: the capture nearest a plausible ROM
scores best, the two flagged ones score 1.8× and 3× worse.

The fix is footage, not code: re-shoot with a known vertical reference in frame
— a metre rule against the rack — and calibrate the scale over the travel
rather than at the bottom of it.

**One-sided in practice.** `deadlift_180x3` reads 47.6 cm, about 20% low, and
is *not* flagged: the sanity floor is 40 cm and nothing measured justifies
raising it to 50. So a capture can still referee P2 with a scale 20% too small.
That capture is also the worst by horizontal error and the one that over-reads
its impact velocity step by 58–72% (B5). Three independent complaints about the
same capture, still undiagnosed.

**Three defects the bounds found in the pipeline, all in the new captures.**
Two were fixed by C5 on 2026-07-31 — see `28` below — and are kept here as the
record of what the bounds were able to catch.

- `bench_spoto_90x5_1` segmented a 5-rep set into **6** windows; the extra one
  ran 88.7 cm of vertical against a 35 cm bench bound, so it was the re-rack
  being counted, not a rep split in two. It had gone undetected because
  `REP_LABEL`/`REP_COUNT` did not match the `spoto` variant token — so
  `expected_reps` was `None` and *every* count gate silently skipped all three
  of the 2026-07-30 benches. P1's "44/44 with zero false positives" was true
  when measured, went to **51/52**, and is **52/52** since C5.
- `squat_160x1` reconstructed **18.0 cm** for a single at 160 kg, a quarter of
  the ~65 cm the other squat captures give. The count was right, 1 of 1 — this
  is the failure mode P1 warns about, a window in the right number and the
  wrong place, and it is the first time a gate here caught one. **It reads
  67.0 cm since C5.**
- `deadlift_180x3` rep 2 lands at 61.1 cm against the 61 cm bound. A 0.2%
  breach is inside the precision of the bound itself; it is reported and does
  not fail the gate, which allows 2 cm of slack. **This one is not fixed and
  was not touched by C5** — it is the same capture that is worst by horizontal
  error and over-reads its impact step, so treat a drift past ~63 cm as that
  capture degrading rather than as the bound being tight.

## C6 — the two anchors, and the error they cannot see (2026-07-30)
- `24_c6_two_anchors.png` — four panels. Regenerate with `python run.py --anchors`.

C1 built a closing stillness hold so that two anchors 40 s apart could measure
what a working set does to Core Motion's attitude. Seven captures now carry both
holds. This is that measurement.

**The physics, so the number means something.** During a still hold the
world-frame acceleration must be zero. Core Motion removed gravity using its own
attitude, so a tilt error θ leaves g·sin(θ) in the world horizontal — the same
relation `orient.py`'s docstring derives. The anchors therefore read the
attitude error directly, in degrees, at each end of the set.

**Answer: a set does no lasting damage** (top left).

| | opening hold | closing hold | gyro alone over the same span |
|---|---|---|---|
| median | **0.05°** | **0.14°** | **0.69°** |
| worst | 0.07° | 0.27° | 1.49° |

Over 39–56 s of loaded lifting with 20 g impacts in it. Propagating the logged
gyro alone from the opening anchor drifts 0.35–1.49°, so Core Motion's fusion is
doing real work and winning — through the impacts, not despite them.

**Two limits on how far that table can be read, both from the watch not being in
the same posture at the two anchors.** It rotates 3.5–161° between them, mostly
yaw:

*The tilt figures are upper bounds, and the change between them is not a
result.* The world residual is the tilt leak plus the body-frame accel bias
rotated into the world, so a posture change alters the bias term's contribution
at each end. And 0.0025 g of accel bias is g·sin(0.143°) — the closing-anchor
median itself. The body-frame residual is 0.0012–0.0050 g at both anchors, at
that floor throughout. True tilt error is between zero and 0.14° and nothing
here separates them. The conclusion is unaffected, since it is small either way;
an earlier version of this section read the 0.05 → 0.14 as degradation and that
was wrong.

*Only two of three degrees of freedom are measured.* Gravity constrains roll and
pitch. The logger requests `.xArbitraryZVertical`, so no absolute yaw reference
exists anywhere in the system and yaw error is unobservable. It is bounded
indirectly by the gyro-vs-Core-Motion yaw divergence, 0.0–1.4° per set. That is
enough to close it: 1.4° of frame rotation moves a point on a 10 cm excursion by
2.4 mm, under the 1 cm spec — and it is not the 180° disagreement P2 reports on
fore-aft sign, so yaw does not explain that either.

**This confirms B1 on the evidence B1 asked for.** `calibrate.py`'s docstring
named this exact test: two anchors 40 s apart, a baseline over which real
rotation cancels and bias does not. 0.69° over ~50 s is **0.014 °/s** of
effective drift, against a pause estimate of 0.1–0.9 °/s. The pause estimate is
10–60× too large, and "never apply it" now rests on a long-baseline measurement
rather than on an A/B comparison of two bad options.

**It also retracts P4's two-degree attitude error, twice over.** The 0.035 g
that inference rested on is the *vertical* residual from `analysis/11`. Vertical
leaks g·(1−cos θ) where horizontal leaks g·sin θ; converting a vertical number
with the horizontal formula is what produced "2 degrees". Correctly, 0.035 g of
vertical needs **15.2°**, and a real 2° tilt puts 0.0006 g into vertical — 58×
less. Separately, that figure is off-pipeline and pre-sign-fix, and does not
survive: `bench_92.5x2` now reads 0.0005 g. Both 15° and 2° are excluded by the
anchors by two orders of magnitude.

**And C1 cannot see P3's error, by construction.** The anchors sample the
attitude at the two moments it is most likely to be right: still, with no linear
acceleration to corrupt the gravity reference. P3 lives during the rep.

**What does see it** (top right). A rep starts and ends at rest, so its mean
world acceleration must be zero, and whatever remains is error in the same units
as the hold:

| lift | still hold | per rep |
|---|---|---|
| bench | 0.0011 g | **0.0034 g** |
| squat | 0.0009 g | **0.0025 g** |
| deadlift | — | **0.0270 g** |

Bench and squat sit at the 0.0025 g accel bias measured on a table. There is
nothing on those lifts to explain beyond the sensor itself, which is a stronger
statement than this project has been able to make about them before.

**Deadlift's error enters at the floor impact** (bottom left). Excluding ±100 ms
around each impact — **6% of the samples** — takes the per-rep residual from
0.015–0.031 g to 0.006–0.010 g. Three quarters of it is injected in a fifth of a
second per rep, at the moment the signal is largest and the gravity reference
most corrupted. The residual points the same way rep after rep (direction
coherence 0.60–0.88), which is P3's signature: error that repeats with the rep,
and which a rep-to-rep comparison preserves perfectly.

Note this is not an argument for discarding those samples. The impulse there is
real and B5 measured it against video at a ratio of 1.04.

**A new defect, on the axis assumed to be fine** (bottom right). Deadlift
windows run impact to impact and each contains exactly one impact, so the bar is
at rest on the floor at both ends and ∫a_z dt across a window must be zero. It
is **−0.05 to −2.36 m/s, negative on 15 of 15 reps**, median about −1.5. The
reconstruction loses ~1.5 m/s of upward impulse every rep.

B5's 1.04 is not contradicted: that is the velocity step measured locally across
the impact, over a few hundred milliseconds, and it is right. The deficit is
what the rest of the rep does. Step 7's detrend hides it entirely, which is why
vertical ROM comes out at a plausible 53–61 cm either way — and it is the
sharpest available statement of why the detrend is carrying vertical.

## B6 — the constant-bias family is dead, and the error is an impulse (2026-07-30)
- `25_b6_bias_models.png` — three panels. Regenerate with `python run.py --bias`.

B6's stated first move was the per-rep zero-mean-acceleration constraint, and it
looked like the right one. A rep starts and ends at rest, so its mean world
acceleration must be zero — **velocity closure is physically true where step 7's
position closure is measurably false** (A3: the real deadlift bar misses closing
horizontally by 1.9–4.3 cm). Replacing a known-false assumption with a known-true
one is exactly what B3 was looking for.

**It makes things much worse** (left panel), horizontal rms against video:

| variant | deadlift_155x6_1 / _2 / 180x3 |
|---|---|
| shipping | **5.05 / 9.19 / 15.44** |
| zero-mean acceleration per rep | 19.63 / 27.14 / 6.55 |
| zero-mean, no position detrend | 136.07 / 94.80 / 34.64 |
| constant bias from rest-to-rest velocity closure | 15.50 / 11.64 / 29.12 |

A useful control first: per-rep re-integration from v=0 with the existing
detrend reproduces the shipping numbers to the digit. It has to — the two differ
by a linear-in-t term and the detrend removes exactly that — and it confirms the
comparison is measuring the constraint rather than the rebuild.

**Why, and it rules out the family rather than one attempt** (middle panel). A
constant bias `b` leaves `b·T²/8` of position error after a linear detrend
(residual `½b(t²−Tt)`, worst at `t = T/2`). Invert it against what was measured:

| capture | bias implied by the measured error | bias the closure estimates | ratio |
|---|---|---|---|
| deadlift_155x6_1 | 0.0037 g | 0.0266 g | 7.1× |
| deadlift_155x6_2 | 0.0047 g | 0.0089 g | 1.9× |
| deadlift_180x3 | 0.0016 g | 0.0076 g | 4.6× |

The signal does not contain a constant bias of the estimated size. If it did,
0.0266 g over a 3.4 s rep would leave **37.7 cm** of vertical error after the
detrend and the measured vertical is 5.24 cm. So the closure constraint is
absorbing an error that is **localised**, and representing it as a constant
spreads it over the whole rep — injecting a parabola larger than the error it
removes. That is also why TASKS.md's oracle cap holds at ~30%: a constant-bias
model cannot represent an impulse.

**Where the localised error is, shown directly** (right panel). Cumulative
vertical velocity through one rest-to-rest interval, on all three captures. The
bar is validated at rest at both ends (`segment.rest_instants`, |v| < 0.10 m/s
on video), so the trace must return to zero. It rises through the pull to
+0.8 m/s, falls through the descent to −1.2, and is smooth and physical
throughout — then at the floor impact it rings violently for several hundred
milliseconds and settles **0.4–1.5 m/s short of zero**.

The error is injected at the impact and in the ringing that follows it, not
distributed through the rep. The ringing is the signature to chase: the watch is
not rigidly coupled to the bar, so it keeps moving after the bar has stopped and
the accelerometer faithfully records motion the bar did not make. That pointed
at #14, strap resonance, which P6 already suspected for `deadlift_180x3` on
independent evidence — **but #14 was then measured and removed.** The
post-impact spectrum has no repeatable peak (10-47.5 Hz across the 15 impacts,
peak/median 2.7-12.5) and Nyquist here is 50 Hz, so a watch-on-strap resonance
aliases to an arbitrary bin. The ringing is real; it is not resolvable as a
resonance at this sample rate.

**One capture dissents, informatively.** `deadlift_180x3` is the only one the
zero-mean constraint helps, 15.4 → 6.6 cm. It is also the capture that over-reads
its impact velocity step by 58–72% (B5). A constraint that removes part of an
unusually large impact error helping exactly there is consistent with the
diagnosis, not against it.

**Correction to C6, from the same measurement.** C6 reported deadlift vertical
momentum closing at −0.05 to −2.36 m/s, negative on 15 of 15 reps, measured over
impact-to-impact rep windows. Those are the wrong windows: every rep boundary
sits **exactly 10 ms after its impact**, one sample into a 2–3 sample spike, so
part of one impulse falls outside the window and the figure inherits the boundary
placement. Measured between validated rest instants it is **−0.37 to −1.48 m/s,
negative on 8 of 9** intervals, with one +1.19. The defect is real and the
direction holds; the range overstated it.

**What B6 should do instead.** Not a constant, and not a per-rep constant. The
two live candidates are modelling the impact and its ringing directly (#14 was
tried as the way in and removed — the ring is not resolvable at 100 Hz, so this
has to work on the transient itself rather than on a detected resonance), and
integrating across the
impact using the known rest state on both sides instead of through it. Bench and
squat need neither — they have no impact, and their per-rep residual is already
at the sensor's noise floor.

## Where the pipeline stands (2026-07-30)
- `21_pipeline_stages.png` — regenerated on the current pipeline. `run.py --stages`.
- `26_pipeline_scorecard.png` — how well it performs, per lift. `run.py --scorecard`.

Read the two together: 21 is how the pipeline works, 26 is how well.

**The scorecard's uncomfortable shape is the point.** Row 1 is the product —
what step 9 would draw. Squat and bench produce clean, tightly-overlaid,
entirely plausible bar paths. Deadlift produces a mess of rectangles that
nobody would mistake for a bar path.

That ordering is exactly backwards from the evidence. Deadlift is the lift with
the best external truth, and row 2 says what that truth says: **2–8 cm of
horizontal error per rep against a 1 cm spec, and 2–7 cm vertical against 3 cm.**
When 27 was drawn, bench and squat had no video truth at all — bench tracking
raised, squat tracked at ~0.40 median NCC — so their clean-looking output was
unfalsified, not verified, and row 1 labels them as such. "It looks plausible"
is precisely how this project would convince itself a broken pipeline works.

**C8 changed that for bench on 2026-07-31, and the panel labels are now wrong
for it.** Bench has a measured horizontal error of 2.63–3.67 cm on three of its
seven captures; the "NO external horizontal check" annotation still applies to
squat and to the four unsynced benches. Redraw 27 to pick up the change.

Row 3 is the one check that reaches all three lifts: per-rep vertical ROM
against `truth.VERTICAL_ROM_M`, every rep of every capture. When 27 was drawn,
two captures fell outside the bands — `bench_spoto_90x5_1`'s spurious sixth
window and `squat_160x1`'s 18 cm fragment. **C5 fixed both on 2026-07-31**, so
all 52 reps now sit inside the bands bar `deadlift_180x3` rep 2 at 61.1 cm,
which is inside the gate's 2 cm slack. Redraw 27 to see the current state.

**What 21 shows on the current pipeline.** Rows 3 and 4 are the drift: vertical
velocity ramps to −6 m/s on the deadlift and position spans **57.7 m** against a
0.6 m lift, so the video-truth line drawn beside it is visually flat. Row 5 is
what step 7 buys back — and on deadlift the per-rep curves disagree with each
other in the floor-resting portion, which is where B6 found the error enters.

## Step 8 and 9 finally run (2026-07-30)
- `27_bar_paths.png` — the product, every capture. `python run.py --paths`.

`project.project_to_plane` and `project.confidence` raised `NotImplementedError`
until now, so the pipeline had never completed and **every bar path anyone had
looked at was projected by hand inside the plot code**. Both figures that showed
one — `21_pipeline_stages` row 5 and `26_pipeline_scorecard` row 0 — did
`rep[:, :2] @ axis` themselves. Step 8 was the only stage whose output was on
screen while the stage had never executed.

`principal_axis` also called `np.linalg.eig` on a symmetric covariance instead
of `eigh`, which is why every caller wrapped the result in `np.real`. A
workaround that hid the wrong routine being called.

**`confidence` is derived, not tuned.** `min_ratio(n_reps)` inverts Anderson's
asymptotic angular error for a principal eigenvector to get the eigenvalue ratio
that pins the display axis to 20°: 10.1 at one rep, 3.8 at four, 3.0 at six. The
one judgement is that the effective sample size is the REP count rather than the
sample count — the samples in a rep are one smooth excursion at 100 Hz, not
independent draws. That is stated as a judgement and checked by a bootstrap in
`tests/test_projection.py`, written as a distribution statement because it does
not hold on every capture.

**It vouches for 11 of 17 sets** (9 when this was written, before C5).

**Half the evidence for "it discriminates without having been tuned to" has
since evaporated, and that is worth stating rather than quietly restating the
claim.** It used to reject both captures with an independently known
segmentation defect — `bench_spoto_90x5_1` at 91.6 cm excursion and
`squat_160x1` at one rep. C5 fixed both defects on 2026-07-31 and both now pass
comfortably: `bench_spoto_90x5_1`'s excursion falls 91.6 → **9.4 cm** at a ratio
of 20.2, and `squat_160x1` reaches a ratio of **69.7**. So confidence was
agreeing with the segmenter's failures, and when the segmenter stopped failing
it stopped objecting — which is consistent with it working, but is no longer
independent evidence that it does.

What survives intact is the half that was always the stronger one: it rejects
the two deadlifts with the worst measured error (35.9 and 30.0 cm excursion,
9.19 and 15.44 cm rms) and accepts `deadlift_155x6_1`, the best at 5.05 cm.
That comparison is against video, not against another part of this pipeline.

**And treat `squat_160x1`'s 69.7 as weak.** It is a single-rep PCA, where
`min_ratio(1)` is 10.1 — one smooth excursion has little to disagree with
itself about, so a high ratio there is close to structural. Passing on one rep
is not the same evidence as passing on six.

**Vouching for the axis is not vouching for the path.** An error at rep
frequency (P3) lands in the covariance as variance and makes the ratio look
*better*, so no function of ratio and excursion could detect it. Every panel of
27 is therefore labelled with what external evidence exists for that lift —
"NO external horizontal check" on bench and squat, the measured rms on deadlift
— and low-confidence sets are drawn without the 4× stretch, because stretching
noise is how you invent faults.

## C5 — both segmentation defects fixed, and neither by the same mechanism (2026-07-31)
- `28_c5_segmentation.png` — band-passed vertical velocity for the two
  defective captures, old windows above the axis and new below, each labelled
  with its centimetres of vertical.

Counting is **52/52** and every rep of all 17 captures is inside its ROM band
except `deadlift_180x3` rep 2 at 61.1 cm, which is inside the gate's slack and
is a different problem. Fifteen captures are unchanged rep for rep.

**The two defects looked alike and were not.** That was the first useful finding
and it is why no single criterion was allowed to fix both.

`squat_160x1`'s bad window was **1.26 s** against 2.8–3.1 s for every other
squat — anomalous in duration, at a correct count. `bench_spoto_90x5_1`'s two
spurious windows were **2.1 and 2.6 s** against real reps of 2.5–2.9 s, so
duration is blind to them and only their 45.7 and 88.7 cm of vertical gives them
away. Mirror images, and a criterion covering both would have been fitted to the
pair rather than derived from either.

**Bench: a cadence tolerance that was 8% too loose.** The five reps sit 2.78,
2.88, 2.86 and 2.94 s apart (ratio 1.058) and the first post-set movement
follows 4.50 s after the last, so admitting it needs 4.50/2.86 = **1.573**.
`_longest_cadence`'s tolerance was 1.6. That admitted the re-rack and grew a run
of six which beat the true run of five **on length alone**. The plot shows the
consequence the counts hid: the old run of six was *shifted*, missing the real
rep 1 at 26–29 s entirely. It was four real reps plus two spurious, not five
plus one.

*The margin, swept over all 17 captures and confirmed independently.* Every
value in **1.35–1.55** gives 17/17. Below 1.30 `squat_140x4_3` splits to 3 reps,
because its four reps genuinely vary 5.00/5.60/6.55 s (ratio **1.310**) — real
sets vary cadence by a third. At 1.60 the bench failure returns. 1.45 is the
middle: 11% clear of the worst real set, 8% clear of the failure. **This is a
plateau, not a wide one.** A rest-pause or cluster set would have a real mid-set
gap above 1.45 and would be split; no such capture exists in `data/raw/`.

**Squat: a tie-break resting on half an argument.** `_similar_cluster` ranks by
`(size, median_time)`, and the lateness rule encodes "set up first, lift
second". That correctly rejects everything *before* the reps and says nothing
about what follows them — and something always does. On a multi-rep set it never
bites, because size decides first. On a **single** there is no cluster to be
largest: every candidate is size 1, lateness decides alone, and the latest
movement in any capture is by construction the re-rack. Singletons now rank by
concentric displacement — an argmax, no threshold — and the capture reads
**67.0 cm**, separating 0.602 m against 0.384 for the runner-up.

**That rule is unfalsified on bench, not verified there.** It claims a working
rep moves the bar further than the movements bracketing it, and that is
measurably false on bench: `bench_92.5x2`'s unrack carries 0.433 m against 0.295
and 0.239 for its two real reps. Clustering saves every bench capture held
(winning cluster size 4+) and `squat_160x1` is the only one of 17 whose winning
cluster is size 1 — but **a bench single would enter this branch and pick the
unrack**, and duration does not rescue it (area×duration also prefers that
capture's setup, 0.302 against 0.280). A gate pins the containment so a future
capture entering the branch announces itself.

**`phase` cannot help either defect, and this was checked rather than assumed.**
The lifter re-racks *before* pressing "Finish Set", so both spurious windows sat
entirely inside `phase == 1` — `squat_160x1`'s re-rack ends at 38.3 s against
phase 1 running to 39.3 s. **The C3 column marks the closing hold, not the end
of lifting.** Both fixes are therefore phase-independent and apply equally to
the ten older captures.

**What this does not do.** It fixes how many windows there are and how far each
spans. It says nothing about **phase** — whether a bench or squat window starts
where the rep starts. A window half a rep out of step has the right count, the
right duration and the right amplitude.

*Written as "unverifiable until those lifts get an external anchor". Bench got
one the next day: C8's video sync puts a bench clip on the IMU clock, which is
exactly the anchor this sentence was waiting for. The question is now open
rather than closed, and nobody has run it. Squat's half stands.*

## C8 — bench video truth (2026-07-31)

- `29_bench_video_truth.png` — three panels on why a bench clock sync can be
  believed. **Left:** the correlation run on the three deadlifts, plotted
  against the offset `truth.sync` already knows from landings matched to floor
  impacts. The peak sits +3, −14 and −18 ms from it — the method recovers a
  known answer, which is the whole licence for using it where there is no known
  answer. Note the peaks are only 0.774, 0.708 and **0.595** high. **Middle:**
  the same correlation on all seven bench captures. Three clear the floor,
  four do not, and the four that do not are genuinely flat-topped — there is no
  lag to read off them. **Right:** the gap the threshold lives in, 0.509 to
  0.595, with `SYNC_MIN_CORR = 0.55` at its midpoint and ~0.04 of margin either
  side. The dotted line is the 0.70 the function originally shipped with, which
  rejects `deadlift_180x3` — a sync correct to 18 ms.

**The rejected half, kept because it was convincing.** The intended independent
check was the re-rack: video sees the bar stop dead, IMU sees a transient. On
bench it disagreed with the correlation by 53–706 ms, which read as evidence
against the sync. Run on deadlift, where the offset is known, the anchor itself
misses by **+615, +660 and +510 ms** — a systematic half-second, because "last
tracked motion" and "last acceleration transient above 3 g" are not the same
event. The disagreement was almost entirely the check's own error.
`truth.rack_impact` was deleted; a comment marks where it was.

**What bench then measures.** Horizontal 3.67, 2.69 and 2.63 cm rms per rep,
against deadlift's 5.05/9.19/15.44. And `reps_disagreeing_on_sign` is 0 on all
fifteen bench reps, against 4 of 6, 2 of 6 and 1 of 3 on deadlift — the fore-aft
instability in `19_a3_metrics.png` does not reproduce on bench.

**Sensitivity, measured rather than argued.** Offsetting the fitted lag by
±100 ms moves per-rep horizontal rms by 0.11, 0.27 and 0.33 cm, and vertical by
0.83, 0.63 and 1.00 cm. So a sync error costs little horizontally and about a
centimetre vertically — and the lag was fitted on the vertical channel, so bench
vertical is the number to distrust.

**The weakest part, found by reading the middle panel rather than the numbers.**
The bench curves oscillate: their best rival more than 0.4 s from the peak
reaches **0.80, 0.81, 0.80** of it, against **0.74, 0.66, 0.51** on the three
deadlifts where the peak is known correct. Bench is outside the range the method
has been shown to work in. The cause is structural — the rival lags are −2.81,
+0.85 and −3.465 s against a rep cadence near 2.9 s, so the alternative
alignment pairs rep *n* with rep *n+1*, and touch-and-go reps genuinely do
resemble each other. `bench_spoto_90x5_2`'s peak at −2.32 s, which looks like an
outlier beside its siblings' +0.04 and −0.585, is this.

**And what that costs, which is the useful part.** Scoring at the rival lag
instead of the peak gives horizontal **3.11, 3.23 and 2.44 cm** against 3.67,
2.69 and 2.63 — no worse, and *lower* on two of three. The bench horizontal
number does not depend on resolving the ambiguity.

That is not a bench excuse. Shift a **deadlift** by a full 3 s and its
horizontal rms goes 5.05 → 4.62, 9.19 → 7.23, 15.44 → 15.17, while its vertical
explodes from 5.24 / 6.60 / 5.24 to **19.08 / 20.19 / 32.41**. So:
**`vs_truth`'s horizontal rms is not testing time alignment on any lift** — the
fore-aft signal is a few centimetres and looks much the same rep to rep, so
mis-pairing reps barely moves it. It is a magnitude comparison between two paths
that happen to be paired in time. Phase evidence comes from `17` and the
lockout-containment gate, not from this number.
