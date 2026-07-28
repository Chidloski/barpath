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
