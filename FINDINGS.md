# Findings — what works and what does not

**This file is a VERDICT LIST, not a diary.** One entry per mechanism, saying
whether it earned its place and what it cost. If you want to know why the
pipeline is shaped the way it is, or whether an idea has already been tried and
lost, it is here. If it is not here, it has not been measured.

Rewritten on 2026-08-23 (H32) on the owner's instruction. It had reached 9,407
lines, 6,800 of them a reverse-chronological log with one entry per task — an
account of *when* things were learned, which nobody needs, wrapped around the
verdicts, which everybody does. The verdicts are below. **The narrative is in
`git log` and in the module docstrings**, which is where a reader who needs the
derivation of one mechanism will actually look; `git show` the commits named
here for the full working.

**Do not turn this back into a diary.** No dated task entries, no "H29 said X
then H30 said Y". When a finding is overturned, rewrite the entry and say what
it replaced in a sentence — the correction belongs in the verdict, not stacked
beneath it. `tests/test_docs.py` gates the shape.

---

## Reading a number here

Eight standing facts. A figure taken before one of them is measuring a different
quantity, so check the date before you quote.

1. **Step 6 (`R(t)·d`, the wrist-to-bar offset) has been ON since 2026-08-06.**
   Anything earlier scores the reconstructed **watch** path. Reproduce an old
   figure with `wrist_offset=None`.
2. **The video referee's absolute scale changed on 2026-08-17**: +4.9% bench,
   +6.1% deadlift, +11.4% squat. Every metre figure against video before that
   date is on the old ruler. It cut median vertical error 3.92 → 2.71 cm.
3. **The video path has been CONDITIONED since 2026-08-22** — impossible frames
   rejected, light order-2 smoothing. `bar_path(condition=False)` reproduces the
   old behaviour. It moved no vertical figure (travel median −0.004 cm).
4. **The v1 corpus was deleted on 2026-08-14** — `data/raw/`, `data/video/`,
   `data/synthetic/`, `truth.py`. Findings measured on it **cannot be
   re-derived** and cannot referee a change.
5. **There is one video referee, `src/vtrack/`**, since 2026-08-19. `markers.py`
   and `truth.py` are gone; nothing scored under them can be re-run.
6. **The corpus is 34 captures** (2026-08-23). Nearly every corpus-wide median
   below is the 29-capture figure from 2026-08-17 and has not been re-measured.
7. **`deadlift_160x6_1_20260818` was captured wearing lifting straps and should
   referee nothing.** The watch moved: it invents 19.9–27.9 cm of per-rep
   fore-aft where its unstrapped same-day twin invents 5.4–7.7 and the bar
   really moved 4.4–6.0. Nothing in the repo marks it — exclude it by hand and
   say so.
8. **Check a `run.py` command exists before quoting it as reproduction.**
   `run.py` carries `FLAGS` and `RETIRED` tables and refuses both cases by name.

---

## What ships

Nine steps, one module each. `CLAUDE.md` has the mechanism; this is the verdict.

| step | module | state |
|---|---|---|
| 0 load log | `io.py` | — |
| 1 gyro bias | `calibrate.py` | **OFF by default.** There is essentially nothing to remove, and applying the pause estimate was worse on 13 of 13 captures. |
| 2–3 attitude, world frame | `orient.py` | — |
| 4 double integrate | `integrate.py` | — |
| 5 segment | `segment.py` | Split by lift class: deadlift on `impact_anchors` from raw acceleration, smooth lifts on integrated velocity. |
| 5b drift tilt | `correct.fit_drift_tilt` | **ON since 2026-08-16.** Self-limiting. |
| 6 wrist→bar offset | `correct.apply_offset` | **ON since 2026-08-06.** |
| 7 per-rep detrend | `correct.detrend` | **ON**, order 1. Load-bearing for its per-rep INDEPENDENCE. |
| 8 display axis | `project.py` | From ATTITUDE, via `anatomical_axis`. Sign from `FORE_AFT_SENSE`. |
| 9 overlay plot | `plot.py` | Horizontal stretched 4×. |
| 10 product view | `display.py` | Not a pipeline step. A layer after 9. |

**What it scores, against the video, 29-capture corpus (2026-08-17).** Quote
`beats_null` alongside any horizontal number:

    lift        beats the flat-line null on
    bench                 6 of 7
    squat                 9 of 10
    deadlift              1 of 10      <- and that one is a single

Median vertical error against video: 2.71 cm, inside the ±2–3 cm spec.
Horizontal is the problem, and it is a deadlift problem.

---

## What works

**Step 5b, the fitted drift tilt.** A world-horizontal attitude drift rate,
fitted against the set's own rep-to-rep dispersion. Self-limiting rather than
gated on the lift: it finds |β| of 0.001–0.008 °/s on bench and squat against
0.008–0.051 on deadlift. It also *removed* the per-rep excursion-growth
statistic that used to be the sharpest IMPACT/SMOOTH split — deadlift compounded
at +29.2 %/rep against bench's +0.3 and squat's +1.9, and 5b is what fixes it.
Do not quote the growth statistic as a live class separator.

**Step 6, the wrist-to-bar offset.** Deadlift's horizontal acceleration
correlation goes 0.12–0.23 → 0.43–0.64 with `d` applied; bench improves on 6 of
6; the vertical control does not move, which is what makes it a real recovery
rather than a rescaling. **It does not cash out in position**, and that gap is
itself a finding, not a footnote.

**Step 7's per-rep INDEPENDENCE, not its closure.** Two free parameters per rep
with no continuity between them. Making it continuous across the set costs
8.21 → 17.00 cm. This is the single most load-bearing property in `correct.py`.

**Step 8's attitude-derived axis.** The hand is clamped to the bar, so fore-aft
is a fixed direction in watch coordinates and one angle fixes it. The rotation
axis is **3–25× more reproducible** than the video-identified reference it was
originally scored against — which means the corpus has no referee sharp enough
to measure its accuracy, and that its old "41° median error" was substantially
the referee's noise. Precise is not the same as right; the evidence it is also
roughly right is deadlift h_rms 4.97 → 3.85 cm, under its own null.

**The video referee, `src/vtrack/`.** Uses the owner's prior that the eight
stickers lie on a circle at even spacing **in the search**, not only in the fit —
8-fold rotational symmetry is the strongest thing separating a plate from rack
holes and ceiling strips. Detection is on *whiteness*, `value × (1 − saturation)`,
not brightness. 16 of 16 clips tracked at 0.97–1.00 coverage, 16 of 16 rep
counts matching the label. **The strongest evidence is a replication, not a
self-report**: per-rep video fore-aft came out 4.4–6.0 cm on all six deadlifts
against an independent 4.3–6.2, three of them captures the earlier measurement
never saw.

**The tape-measured sticker circle.** The plate diameter less 2.0 cm, by
construction — a 2.0 cm sticker placed with its outer edge on the rim puts its
centre 1.0 cm inboard. It replaced a transferred ratio of 0.858 that was
calibrated on a *three*-sticker plate stickered to a different rule.
Corroborated independently of the tape: the video read below the IMU's per-rep
vertical ROM on 16 of 16 captures at medians 0.926 / 0.924 / 0.936, and the
correction takes those to 0.971 / 1.029 / 0.993.

**`seed.prefer_sticker_ring`.** A plate carries several rings of eight evenly
spaced features — cutouts, bolt circle, and both ends of each sticker — so the
8-fold prior cannot break the tie, and the radius *is* the pixels-to-metres
scale. The sticker ring's blob-ness beats every rival by 3.6–5×. Applied as a
tie-break inside a score window only, never as an admission gate.

**Path conditioning.** Rejecting frames that imply motion faster than free fall
found four broken tracks in 36, **two of which nothing in the repo could see** —
whole-clip travel cannot detect one bad frame inside a sound track. Travel
changes by a median of −0.004 cm, so the measurement did not move.

**The display layer's averaging.** 1.95 → 1.52 cm, and the whole of it is the
ALIGNMENT, not the averaging.

**Validating on deadlift first.** Not because the pipeline differs by lift — it
does not — but because deadlift has the most external ground truth: the bar
starts at the bumper's radius, 22.25 cm to bar centre, and ends at a
tape-measurable lockout. Bench and squat offer `VERTICAL_ROM_M` bounds on
per-rep travel, which is a bound and not a measurement — it constrains one axis
and cannot see phase — but it is the difference between an unfalsifiable claim
and a weak one. Bench has real video truth too; rank it below deadlift, because
its clock sync is a cross-correlation whose accuracy was measured **on deadlift**
and then assumed to hold. `src/plot.py` cites this rule.

---

## What does not work

Do not re-propose these without new evidence. Each cost a session.

**Fitting `d` from the video.** Established once and re-confirmed twice. `d` is
tape-measured and is not a free parameter. Do not reopen the fit.

**Any constant error model, in any frame.** Body-frame accel bias, world-frame
tilt, accelerometer scale, the lever arm, an attitude error growing with |a| —
fitted *directly against the answer*, fifteen parameters reach 1.23 cm against a
flat-line null of 1.54–1.68. **Nothing transfers**: every model collapses to
3.3–4.6 cm under leave-one-out and two make the held-out capture worse. Re-run
with the lever pinned at the tape `d`, the conclusion survives. This is P3, and
it is why no estimator for a constant was ever going to pay off.

**A quadratic per-rep detrend.** Implemented, measured, rejected.

**A continuous (set-wide) detrend.** 8.21 → 17.00 cm. See step 7 above.

**Splicing the floor impact.** The deadlift vertical momentum deficit is
localised to the floor landing alone and a splice does fix it — and still loses,
because the linear detrend cannot absorb a localised correction.

**A per-set tilt correction from the pull anchors.** Built and measured: 2.78 →
5.01 cm, `beats_null` 0.68 → 0.33. The mechanism was right and the correction
loses anyway.

**Applying the ZUPT velocity correction to all three axes.** It damaged the
vertical. The horizontal ceiling it reaches is `beats_null` 0.77, and it cannot
go further because half the horizontal error is present in the impact-free pull,
so nothing sized at the landing can reach it.

**Excising the impact ring on the VERTICAL.** Forbidden: closure error 0.128 →
0.653, worse on 23 of 24. That impulse is real and the IMU captures it at a
ratio of 1.04. On the *horizontal* the same excision is licensed but not proven
— 0.256 → 0.153, better on 15 of 24, a 1.7× median improvement and not a
universal one.

**The anatomical cone as a clamp on the display axis.** There is an interior
optimum in the corpus median (2.97 → 2.66 cm at 20–30°) and **it should not be
read**: it is a trade, not a win. Deadlift is best at 0°, bench best unclamped,
and per capture it is mixed.

**Bar tilt from the endcap marker, as a correction.** The endcap offset is real
and large, and 81–96% of it is *perspective* — the bar crosses most of the frame
each rep and the endcap sits nearer the camera. What survives a quadratic
perspective model is 2.0–2.7 px, and the lever from the sticker plane to the bar
centre magnifies that by 2.0–3.7: **1.1–1.7 cm against a ~1 cm spec**. Worse,
the residual is still shrinking as the model improves, so it *bounds* bar tilt
rather than measuring it. Useful as a bound; not a correction.

**The 8-point conic's orientation as a tilt cue.** Unusable in principle, not
for want of a better fit. A circle tilted by θ projects to an ellipse of aspect
cos θ, which at the 1–3° a barbell tilts is 0.01–0.11 px on an 85 px radius.
Second order in the angle. Only the parallax, which is first order, carries
signal.

**Smoothing, as a way to improve accuracy.** 2.07 cm median horizontal error
against the video, unmoved by any method at any level. This is P3 restated from
the display side: the error is at rep frequency, so there is no high-frequency
component for a smoother to reach. Smoothing is free and it fixes nothing.

**Excluding the odd rep from the average.** It makes the average worse, because
the odd rep is usually a real rep. It ships as a **label**, never as a deletion.

**Raw gyro on watchOS.** `CMMotionManager.isGyroAvailable` returns false. Tried
on one motion manager and on two. There is no public-API route — **do not
re-propose this.**

**Synthetic gates as evidence.** A 1 cm synthetic gate was passing only on
seed 0. Synthetic tests are unit tests now; a gate only counts if it runs on
real captures.

**Milestones.** Milestones 1–6 all passed and the project did not work. The
table is gone. A schedule that reports success while the artefact fails is worse
than no schedule.

---

## The open problems

**P1 — counting, extent and phase. REOPENED.** Three captures miscount:
`deadlift_210x1_20260815` gives 2 windows for a labelled single,
`squat_140x4_1_20260813` gives 3 of 4, `squat_140x4_2_20260813` gives 2 of 4
with a 9.5 s hole mid-set. **The video counts all three correctly**, so the
labels are right and the segmenter is wrong. Left red in the suite rather than
xfailed.

**P2 — the horizontal error against video. OPEN, and it is the project.**
Deadlift sits at `beats_null` 0.14–0.38 and a better referee did not rescue it,
so the fault is in the reconstruction. One bench capture,
`bench_spoto_95x5_1_20260806`, is the single capture to explain: a re-referee
moved its session-mate across the null and left this one at 0.89.

**P3 — the error sits at rep frequency, where no filter or line can reach it.**
See "any constant error model" above. This is the load-bearing negative result
of the project and it constrains every proposed fix: an error that repeats with
the rep is preserved perfectly by rep-to-rep comparison, so "it's common-mode"
is not available as a defence.

**P4 — there is almost no gyro bias to calibrate. CLOSED as a problem.** On a
watch lying on a table the residual gyro bias is 0.002 °/s and is not resolvable
above its own noise; attitude holds to 0.018° over 10 s; body-frame accel bias
is 0.0025 g. The on-wrist figures this problem was built on — 0.93–1.05 °/s —
are **the lifter's own slow wrist rotation**, which a 1–3 s hold cannot separate
from bias. A factor of ~500.

*A retraction worth keeping: the "2° attitude error" once inferred from a
0.035 g residual was wrong twice over. Wrong projection — a tilt θ leaks
g·sin θ horizontally but only g·(1−cos θ) vertically, so converting a vertical
residual with the horizontal formula needs 15.2°, not 2°. And wrong number — the
0.035 g predates an acceleration sign fix and reads 0.0005 g after it.*

**P5 — CLOSED.** Apple's residual gyro bias is both unobservable and negligible.
What replaced it: **attitude survives a working set.** Across seven captures with
both holds, attitude error at a still hold bounds at 0.05° opening and 0.14°
closing, worst case 0.27°, over 39–56 s of loaded lifting — while the logged
gyro propagated alone drifts 0.35–1.49°. Core Motion's fusion is winning,
through the impacts rather than despite them. Read those as upper bounds and do
**not** read the change between them as degradation. Yaw is unconstrained by
gravity and bounded only indirectly, at 0.0–1.4° per set, which moves a point on
a 10 cm excursion by 2.4 mm — under spec.

**P6 — the floor impact. HALF the horizontal story, not all of it.**

    interval class                    n   |dv_h| med   implied tilt
    deadlift, PULL only              15     0.144 m/s     0.34 deg
    deadlift, interval WITH impact   24     0.256         0.60
    bench, lifting                   59     0.031         0.13
    squat, lifting                   35     0.070         0.13

The impact roughly **doubles** the horizontal error and does not create it — a
deadlift pull with no impact in it already carries 2–3× bench's error. The other
half is **gravity leaking through attitude**: a third of a degree against the
bar's real 0.13–0.21 m/s² horizontal is a third of the signal, while the same
tilt is 100× smaller on the vertical. That is why one attitude error is fatal on
one axis and invisible on the other.

*And the pre-set pause cannot kill it, because it is already spent.* Two still
instants give two numbers, a line has two parameters, and step 7's closure
already consumes exactly that information. What the pause cannot give is the
SHAPE — a steady tilt and an impulse at the landing produce the same velocity at
the pause and different position curves.

**A standing tilt survives step 5b, and it is the live lead.** Mean horizontal
acceleration error over impact-free pull intervals is **negative on 9 of 9
captures, sign test p = 0.002**, across three sessions, 150–190 kg and both
camera sides. Step 5b removes a little under half of it and leaves 55% — a
residual of 0.011–0.070 m/s², median 0.040, i.e. 0.06–0.41°, median 0.23. That is
consistent with 5b fitting a RATE where this is an OFFSET. The pull error and
the landing error are **largely independent** (Spearman r = +0.06, p = 0.83,
n = 15), so they are two causes rather than one seen twice.

*The caveat that decides whether it is buildable:* only 15 intervals carry a
lockout dwell against 24 landings, so the second anchor exists on fewer than half
the reps. That licenses estimating a per-SET standing tilt and applying it to
every rep. It does not license a per-rep correction — and the per-set version
was built and lost (above).

---

## Two classes of lift: IMPACT and SMOOTH

The owner's framing, and it is sound. **Deadlift is an IMPACT lift — the bar is
dropped to the floor between reps. Bench and squat are SMOOTH.** Both run the
same nine steps; impact lifts need supplementary ones, and two steps' premises
break on impact:

- **Step 6** assumes `d` is rigid in body coordinates, which fails during strap
  ringing.
- **Step 7 is the real fault line.** Nearly adequate on smooth lifts; on impact
  lifts **no per-rep line beats the flat-line null on any deadlift**, whoever
  estimates it.

The sharpest statement of the split is `beats_null` against the video — bench 6
of 7, squat 9 of 10, deadlift 1 of 10, and that one a single, so every multi-rep
deadlift loses.

---

## The referee, and what it cannot do

**Track the moment a video is supplied, cache the path to CSV beside the
capture, render a review figure — and then LOOK at the figure.** The looking is
the half that matters. Six squat clips once fed travel figures of 0.2 to 24.7 cm
— for 65–70 cm squats — into comparisons behind coverage of 96–100% and healthy
residuals, because the tracker had locked onto gym furniture. **Every summary
statistic said fine.** Coverage and residual cannot see it; whole-clip travel
against the lift's own range of motion can.

Review figures are **not committed** as of 2026-08-23; they regenerate from the
cached CSVs in seconds and `analysis/tracking/` is gitignored. The protocol is
unchanged, only the storage.

**Two costs of reading the cache, both real.** The CSV carries per-frame arrays
and scalars but **not** the tracker's own diagnostics, and a cached read does not
run `vtrack.validate`, so its per-capture warnings do not fire. Use
`resolve_path(use_cache=False)` or `run.py --track --force` after any change
under `src/vtrack/` — a cached path is only valid for the tracker code that
produced it.

**Known limits.** No per-frame perspective scale: one scale for the whole clip,
because the centre comes from a lattice fit at a held radius, so apparent size is
not independently measured. The predecessor applied one and measured it at
0.6–1.4 cm on deadlift. The footage is **360×640 at 30 fps**, which is the
binding constraint on everything sub-centimetre — it is why the endcap tilt
estimate misses spec by 2–3×, and 1080p would fix that for the cost of a capture
setting. Bench and squat are filmed from the **right** while the watch is on the
**left** wrist, so the referee watches the opposite end of the bar from the
sensor; deadlift is the only lift where they agree.

**`pipeline.find_video` returns `None` for captures whose `.mov` is off disk.**
All of them still score, because the tracked path is cached and committed — so
anything iterating the corpus should pair through `data_v2/tracked/`, not
through the video.

---

## The one measured constant you should not re-fit

`correct.WRIST_OFFSET_M`, tape-measured 2026-08-06 — watch-face centre to bar
centre, in watch body axes:

    squat            5 cm toward the crown, 4 cm UP OUT of the case    |d| = 6.4 cm
    bench, deadlift  9 cm toward the crown, 3 cm DOWN INTO the case    |d| = 9.5 cm

`apply_offset` computes `p_bar = p_watch − R(t)·d`, so **its `d` points BAR→WATCH
and is the negative of what the tape reads from the watch.** A sign error here is
invisible: it produces a plausible curve of the right size pointing the wrong
way.
