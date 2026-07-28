# Tasks

Working state of the pipeline rebuild started 2026-07-28, after milestones 1–6
all passed on synthetic data while the pipeline failed in the gym by two orders
of magnitude.

Related, and deliberately not duplicated here:

- `CLAUDE.md` — **Open problems** P1–P5, the *problems*. This file holds the
  *work*.
- `analysis/README.md` — the measurements and plots behind each finding.
- `src/README.md` — video ground truth (A2) in depth.

---

## Done

### B1 — stop applying the pause-derived gyro bias `17d5eee`
Applying `calibrate.gyro_bias` was worse than doing nothing on **13 of 13**
captures. Median per-rep horizontal residual **71.5 cm → 4.2 cm (17×)**, better
on 10/10, worse on none. The correction is now opt-in via `apply=True`.

We log `dm.rotationRate`, which Core Motion has already bias-corrected, and the
residual is smaller than the tremor we measure it in: ~7 °/s p-p at 6.5 Hz
against a 0.1–0.9 °/s bias, block-resampled SEM 0.16–0.36 °/s. A significance
gate was tried and rejected — it passed on 4/10 captures and made all 4 worse,
because SNR tests whether a mean is reproducible, not whether it is bias.

### A1 — rep segmentation `e8a8a0b` `efd5f5c`
**44/44 reps across all 10 captures, zero false positives**, against the old
stationarity segmenter's 0/14 bench and 1/15 squat. Shape matching in a
fixed-*duration* window, floor-impact anchors where the lift provides them
(6/6, 6/6, 3/3), and lateness as the tie-break. Every rep window now contains
both a concentric and an eccentric phase of comparable size (0/44 unbalanced,
was 9/15 deadlift reps holding only the pull).

Not finished — see **#13** below.

### A2 — video ground truth `374392b` `f6ff01c` `09c6bfc`
`src/truth.py`. Plate tracked from footage; first external truth for the
horizontal axis. Video landings match IMU floor impacts 6/6, 6/6, 3/3 at
**11–16 ms rms**, clock drift <0.25%. Deadlift is automatic and unattended;
squat warns; bench raises and needs a manual seed. Full detail and ten
drawbacks in `src/README.md`.

### A4 — end-to-end driver `91ed978`
`src/pipeline.py` + `run.py`. The pipeline had never been executed end to end
against a gym capture; every prior real-data result came from scripts outside
the repo. Does not raise on unimplemented stages — records them as blocked and
returns what worked. Surfaced `io.check_log` and `segment.quality_flags`, both
previously dead code.

---

## To do

Ordered by what unblocks the most.

### #13 — fix the A1 rep-window phase error  ← next
Windows run lockout-to-lockout: each holds the descent of one rep followed by
the ascent of the next. **Half a rep out of phase**, so what `segment.py` calls
the concentric is the eccentric. Confirmed against video — window starts
16.42/19.21/22.64/25.91/29.48/34.60 s against video lockout peaks
16.23/19.23/22.33/25.70/29.23/34.27 s on `deadlift_155x6_1`.

Predicted by the owner from the velocity plots before the video existed. Also
the likely cause of the first-rep over-extension that resisted three separate
fixes while unverifiable.

### A3 — real-data error metrics
`src/metrics.py`: `dispersion(reps)` for rep-to-rep spread after start
alignment, and `vs_truth(reps, video)` against A2. **The absence of this is why
every stage could pass while the product failed.** Nothing in B is trustworthy
until it exists. Blocked on #13 for meaningful windows.

### #14 — fix `quality_flags` strap resonance
Rejects 12 of 44 real reps, all on quieter lifts, and is backwards: it
thresholds the *fraction* of accel energy above 10 Hz, so a quiet rep fails for
having little signal at all. Rejected bench reps carry 13–18k absolute HF
energy against 0.9–2.9M in accepted deadlift reps — 50–200× **less**. Its own
docstring intends absolute energy.

### B2 — implement step 6, the wrist-to-bar offset
`correct.apply_offset` raises. `R(t)·d` varies by **8–13 cm horizontally on
every lift including deadlift**, contradicting the docstring's claim that
deadlift is exempt. Largest single unmodelled term in the system. Needs A2 to
establish `d` against video rather than a guess.

### B3 — rework the per-rep detrend
`detrend_rep` fits a line through two endpoint samples, so it is maximally
noise-sensitive at exactly those indices. Its premise — "the bar starts and
ends each rep in the same place" — is false horizontally: the owner confirms
the deadlift bar lands off where it was pulled. Make closure axes explicit;
keep vertical.

### B4 — fix step 8
`project_to_plane` and `confidence` raise. `principal_axis` uses `np.linalg.eig`
on a symmetric matrix instead of `eigh`, and the docstring's sign resolution is
unimplemented — so the path can silently mirror, which the docstring itself
calls worse than no path.

### B5 — resolve accelerometer saturation
`deadlift_180x3` peaks at 21.8 g and trips `check_log`, whose 16 g threshold is
an assumption. Establish the watch's true full-scale range and make clipped
reps a hard reject.

### C1+C2 — watch logger protocol
Three-second stillness hold *after* the last rep (zero of 13 captures have any
end-of-record stillness) giving a second gravity anchor over a ~40 s baseline
where accel-bias tilt error cancels in the difference. Log raw `CMGyroData`
alongside, which exposes Core Motion's internal bias estimate by difference.

### D — replace the remaining synthetic tests
Gates 5 and 6 are already deleted. Keep the algebraic-identity tests; replace
the rest with real-data gates. Largely done incidentally — worth a pass to
confirm nothing behavioural survives.

### B6 — revisit attitude with a working metric
**Only after A3.** Per-rep zero-mean-acceleration constraints first (they hold
during motion and need no stillness), then the two-anchor estimate C1 unlocks,
then time-varying correction if those fail. Do not build a solver before the
metric exists — an oracle fitting constant gyro *and* accel bias directly
against the error recovers only ~30% of the residual, so constant-bias
estimation is capped well short of 1 cm.

---

## Capture protocol

Not code, and the highest value per effort available:

- **Measure a plate.** `truth.PLATE_DIAMETER_M` is assumed at 450 mm and sets
  the video scale directly — a 2% error is 1.2 cm on a 60 cm ROM.
- **Step the camera back.** Squat clips the plate at lockout; bench sits the
  plate against clutter. Both become usable truth with no code.
- **Film a plumb line once**, to put a number on lens distortion — currently the
  largest unquantified error in A2.
