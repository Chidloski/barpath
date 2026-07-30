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
   Captures from 2026-07-30 on carry a `phase` column (0 opening hold, 1 reps,
   2 closing hold) — use it rather than searching for stillness where it exists.
1. `calibrate.py` — gyro bias from the stillest window in the pre-set pause.
2. `orient.py` — correct attitude by that bias.
3. `orient.py` — rotate acceleration into the world frame.
4. `integrate.py` — cumulative trapezoidal, twice.
5. `segment.py` — stationary detection, then rep boundaries by vertical position.
6. `correct.py` — subtract the wrist-to-bar offset R(t)·d.
7. `correct.py` — per-rep linear detrend so each rep closes.
8. `project.py` — PCA on horizontal displacement picks the display axis.
9. `plot.py` — overlay reps, aligned by start point, horizontal stretched 4x.

`metrics.py` is not one of the steps. It judges them: `dispersion` for
rep-to-rep spread, `vs_truth` for absolute error against the video. Read its
module docstring before quoting a number from it — `dispersion` needs no truth
and is blind to exactly the error that dominates, so the two are not
interchangeable.

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
`data/raw/` holds 17 captures, all labelled with rep counts and totalling 52
reps (7 bench, 7 squat, 3 deadlift), plus two stationary diagnostic logs. The
2026-07-30 session added seven of those and every one carries the C3 `phase`
column, including a real 3.0 s closing hold. The room and warm-up captures were
removed in `7004c32` because no video exists for them; measurements made
before that commit say 13 captures, and measurements between it and 2026-07-30
say 10 and 44 reps. Both are correct as of when they were taken.

Work the problems instead. Each is stated with the evidence that it is real,
so it can be closed by evidence rather than by opinion.

**P1 — Rep counting is 51/52, not solved; window extent is now checkable on
every lift.** Reopened 2026-07-30 by the new captures.

*Counting:* A1 closed this at 44/44 with zero false positives, against the old
stationary detector's 0 of 14 bench and 1 of 15 squat. That was true on the ten
captures then held. The 2026-07-30 session broke it: `bench_spoto_90x5_1`
segments a 5-rep set into **6** windows, the extra one running 88.7 cm of
vertical against a 35 cm bench bound — the re-rack counted as a rep. It had gone
unnoticed because `REP_LABEL` did not match the `spoto` variant token, so
`expected_reps` was `None` and every count gate silently skipped all three new
benches. The regex is fixed and the failure is xfailed with its evidence.

*Window extent, which is new.* Counts cannot see phase — the segmenter scored a
perfect 44/44 while every window ran lockout-to-lockout, half a rep out of step.
Deadlift boundaries come from floor impacts, which use raw acceleration alone,
match video to 13.5 ms, and put exactly one video lockout in each of the 15
deadlift windows. **Bench and squat still have no phase anchor** and still
segment on integrated velocity carrying 145 cm of in-band error against a 69 cm
signal, so their phase stays unverified until P3 is fixed.

But they now have a *partial* external check: per-rep vertical ROM against
`truth.VERTICAL_ROM_M`. It cannot see phase either — a window half a rep out of
step has the right amplitude — but it does see a window that spans too much or
too little, which counting cannot. It found `squat_160x1` reconstructing 18.0 cm
for a 160 kg single at a correct count of 1 of 1. That is the first time a gate
in this project has caught a right-count-wrong-window failure.
*Evidence:* `analysis/04`–`07`, `12` for the old failure; `15`–`18` for A1;
`17` and `src/README.md` for the phase bug; `23` and `analysis/README.md` for
the ROM bounds.

**P2 — Horizontal is 5–15× outside spec; vertical is out too, but the ruler
that says so is itself broken on two captures of three.** Measured against
video by A3, per rep, on the three deadlifts: horizontal **5.05, 9.19 and
15.44 cm rms** against a 1 cm spec, and vertical **5.24, 6.60 and 5.24 cm rms**
against ±2–3 cm. (Re-measured 2026-07-30 against the 445 mm bumper; the
previously recorded 5.1/9.2/15.4 and 5.2/6.8/4.9 used an assumed 450 mm plate
and the correction is worth under 1%.)

Two corrections to what this problem used to say. It is 5–15×, not the two
orders of magnitude claimed from off-pipeline reconstructions and from
whole-set excursion — excursion counts between-rep divergence, which per-rep
error does not. And **"vertical comes out fine" is false**; vertical was never
measured per rep before A3 and it misses its own looser spec on all three
captures.

**A third correction, 2026-07-30: do not quote the spread.** The video's
vertical scale is wrong per capture. Per-rep video ROM on the three deadlifts is
59.1, **66.8** and **47.6 cm** against a measured 61 cm ceiling — a 19 cm spread
on a range of motion fixed by the lifter's own limbs, from footage where two of
the three captures found an identical plate radius. Plate diameter, radius
quantisation and tracker drift were each tested and each ruled out; what is left
is that the scale is calibrated on a plate resting on the floor and applied to
travel reaching the top of frame.

So: the horizontal numbers stand — fore-aft travel is a few centimetres, well
inside the frame region the plate calibrates, and the sync still matches to
11–16 ms. The **vertical** numbers and the **ranking** do not. The error order
tracks the ROM error exactly, the capture nearest a plausible ROM scoring best.
`metrics.vs_truth` now returns `video_rom_flags` and `pipeline.summary` prints
the warning; a flagged capture's vertical must never be quoted unqualified. The
fix is footage with a known vertical reference in shot, not code. *Evidence:*
`analysis/23`, `truth.VERTICAL_ROM_M`.

Note this cuts the other way for the IMU. Judged by the same bounds the
reconstruction passes on all 17 captures bar two known defects — deadlift 53–61,
squat 61–68, bench 24–31 cm. On vertical ROM the reconstruction is currently
more self-consistent than the video it is scored against.

Still true, and now with a number on it: the reconstruction invents fore-aft
travel. Excursion is 18–36 cm on deadlift where the video says the bar moved
8.5–15 cm.

Worse than magnitude, though — **the direction is not stable across a set.**
`vs_truth` picks one fore-aft sign per set, as step 8 would, then counts the
reps that individually prefer the other: **4 of 6, 2 of 6, 1 of 3.** On the
first capture that is nearly a coin flip. The horizontal reconstruction is not
a good path with a scale error; rep to rep it does not agree with itself about
which way forward is.

*Evidence:* `analysis/19`, `metrics.vs_truth`. `analysis/13` is the older
off-pipeline version. Note the "66–253 cm" figure in the A4 section of
`analysis/README.md` predates the acceleration sign fix; it is 3.4–35.9 cm now.

**P3 — The error sits at rep frequency, where no filter or line can reach it.**
The accel bias is fixed in the *body* frame and the forearm rotates through the
rep, so in the world frame that error is periodic **at rep frequency** — the
one shape a per-rep line cannot separate from real motion.
`calibrate.accel_bias`'s own docstring says so. A3 shows it directly: the
horizontal error against video is a single smooth arch across each rep, peaking
around 0.5–0.7 through it, not noise and not a ramp (`analysis/19`, middle row).

**What A3 changed here.** The detrend's *premise* is violated — the real
deadlift bar misses closing horizontally by 1.9–4.3 cm, so forcing closure does
destroy real motion. But the detrend is **not** where P2 lives. Removing the
closure from both sides of the comparison moves the error by only 0.2–0.9 cm,
against a 5–15 cm total. So B3 is a real correctness fix worth ~2–4 cm and it
will not by itself bring the pipeline near spec. The bulk of the error is
upstream, in the acceleration that reaches the integrator. Fix the error, not
the thing that was supposed to hide it.

**P6 — The floor impact is trustworthy, and unused.** Closed as a worry and
opened as an opportunity, by B5.

The worries were saturation and lost impulse, and neither survived measurement.
Nothing in `data/raw/` clips — `deadlift_180x3`'s 21.78 g peak is a genuine
reading, hit by one sample, not a rail. And the impulse survives 100 Hz despite
the event spanning 2–3 samples: the IMU/video velocity-step ratio is median
**1.04** over 15 impacts. `analysis/20`.

So the impact is the one place in this pipeline where the IMU demonstrably
agrees with external truth — 13.5 ms on timing, ~1.0 on the velocity step — and
the pipeline spends it entirely on segmentation. The bar's state there is
*known*: velocity zero, height at plate radius. Using it as an anchor is B7,
and it is the only externally true constraint available; step 7's closure is an
assumption by comparison.

One capture dissents. `deadlift_180x3` over-reads its impact step by 58–72%,
alone among the three, and is also the worst by horizontal error. Heaviest bar,
hardest landing — probably strap ring, which is #14.

*Caution, from getting this wrong once:* the bar is **lowered under control** on
a touch-and-go deadlift and arrives at ~2 m/s. Do not predict its arrival from
`sqrt(2gh)`, which gives 3.3 and makes the impulse look 80% missing.

**Added by C6, 2026-07-30 — the impact is also where the error enters, and P3
finally has a location.** Both halves are true and they are not in tension.

A rep starts and ends at rest, so its mean world acceleration must be zero.
Bench and squat leave **0.003 g** of horizontal, which is the 0.0025 g accel
bias measured on a table — there is nothing there to explain. Deadlift leaves
**0.010–0.030 g**, and excluding ±100 ms around each floor impact — **6% of the
samples** — takes it to 0.006–0.010 g. So roughly three quarters of the
deadlift's per-rep error is injected in a fifth of a second per rep, at the one
moment when the signal is largest and Core Motion's gravity reference is most
corrupted. The residual points the same way rep after rep (direction coherence
0.60–0.88), which is P3's signature exactly: error that repeats with the rep and
which a rep-to-rep comparison therefore preserves perfectly.

**And vertical momentum does not close.** Deadlift windows run impact to impact
with exactly one impact each, so ∫a_z dt across a window must be zero. It is
**−0.05 to −2.36 m/s, negative on 15 of 15 reps**, median about −1.5. The
reconstruction loses ~1.5 m/s of upward impulse every rep, on the axis this
project has assumed was fine.

This does not contradict B5's 1.04. That ratio is the velocity STEP measured
locally across the impact against video, over a few hundred milliseconds, and it
is right. The deficit is in what the rest of the rep does. Step 7's detrend
hides it completely, which is why vertical ROM comes out at a plausible 53–61 cm
either way — and it is the sharpest available statement of why "the detrend is
carrying vertical entirely". *Evidence:* `analysis/24`, gated in
`tests/test_real_data.py`.

**P4 — There is almost no gyro bias to calibrate.** Rewritten 2026-07-30, after
a stationary capture measured what no on-wrist capture could.

On a watch lying on a table — same sensor, same Core Motion — the residual gyro
bias is **0.002 °/s**, and it is not resolvable above its own noise (|mean|/SEM
of 0.28–1.33 per axis). Core Motion's attitude holds to **0.018° over 10 s**
(~6.6 °/hour). Body-frame accel bias is **0.0025 g**.

Against the on-wrist calibration-pause figures this problem was built on —
0.93–1.05 °/s — that is a factor of ~500. **The on-wrist number is not bias. It
is the lifter's own slow wrist rotation**, which a 1–3 s hold cannot separate
from anything. B1's default (never apply the pause estimate) is right for a
better reason than B1 recorded: there is essentially nothing there to remove.

**RETRACTED, later the same day — the two-degree attitude error.** This section
used to say: the ~0.035 g "residual accel bias" seen on-wrist is g·sin(2.0°), so
it is the size an attitude error of two degrees would leak, and that redirects
P3 at attitude rather than at sensor bias. C6 measured it and **both halves of
that inference are wrong.**

*Wrong projection.* The 0.035 g comes from `analysis/11`, and it is a
**vertical** residual. `orient.py`'s docstring states the asymmetry that makes
this matter: a tilt θ leaks g·sin(θ) into horizontal but only g·(1−cos θ) into
vertical. Converting a vertical number with the horizontal formula is what
produced "2 degrees". Done correctly, 0.035 g of vertical needs **15.2°** — and
a genuine 2° tilt puts 0.0006 g into vertical, 58× less than what was seen.

*Wrong number.* That 0.035 g is an off-pipeline figure from before the
acceleration sign fix (`3c2cbed`), and it does not survive it. `bench_92.5x2`,
the very capture it was measured on, now reads **0.0005 g** of per-rep vertical
residual; bench overall runs 0.0003–0.0014 g.

*And the direct measurement.* Core Motion's attitude at a still hold is
**0.05° before a set and 0.14° after** — see P5. 15° is excluded by two orders
of magnitude, and so is 2°.

So P3 is **not** redirected at attitude. What survives is that P3's error is
real, is at rep frequency, and now has a location: see P5 and P6.
*Evidence:* `stationary_table_20260730` and `analysis/24`, both gated in
`tests/test_real_data.py`.

The original framing, still true as far as it goes: the "stillest" window
carries 7.2 °/s peak-to-peak of ~6.5 Hz physiological tremor; the bias being
extracted from it is 0.1–0.9 °/s. Block-resampled standard error of the mean
is 0.16–0.36 °/s, and the observed spread was 0.33–0.47 °/s across the 13
captures held when this was measured — meaning the capture-to-capture variation
is tremor, not bias. More captures will not help; the estimator is the limit.

**P5 — CLOSED 2026-07-30. Apple's residual gyro bias is unobservable, and
also negligible.** Both halves matter, and they arrived from opposite
directions.

*Unobservable:* the plan was to log raw `CMGyroData` alongside the
already-corrected `dm.rotationRate` and take the difference.
**`CMMotionManager.isGyroAvailable` returns false on watchOS** — the raw gyro
service is not offered. Tried on one motion manager and on two; the watch
reported no hardware. There is no public-API route, so do not re-propose this.

*Negligible:* P4's stationary captures put the residual *after* Core Motion at
**0.002 °/s**, unresolvable above its own noise. There was never much for the
internal estimate to explain. Raw accelerometer adds nothing either —
`userAccel + R⁻¹·g` already reconstructs it exactly (9.8065 m/s² measured at
rest against 9.80665 expected) — and B5 showed sample rate is not a limit,
since the floor impulse is already captured at 100 Hz to a median ratio of 1.04
against video.

**What replaced it, and how that came out.** Everything above was measured AT
REST, so the open question became whether Core Motion's attitude survives a
working set — 20 g impacts, fast rotation, its gravity reference corrupted by
the lift's own acceleration. C1's two-anchor protocol was built to answer it and
**C6 measured it on 2026-07-30. The answer is that a set does no lasting damage.**

Across all seven captures with both holds, the attitude error at a still hold
**bounds at 0.05° at the opening anchor and 0.14° at the closing anchor**, worst
case 0.27°, over 39–56 s of loaded lifting. Propagating the logged gyro alone
across the same span drifts **0.35–1.49°**, median 0.69 — so Core Motion's
fusion is doing real work and winning, through the impacts rather than despite
them.

**Read these as upper bounds, not measurements, and do not read the change
between them at all.** The world-frame residual is the tilt leak PLUS the
body-frame accel bias rotated into the world, and the watch is not in the same
posture at the two anchors — measured, it rotates by 3.5–161°, mostly yaw. So
the bias term projects differently at each end. Decisively: 0.0025 g of accel
bias is g·sin(0.143°), which is the closing-anchor median itself. The body-frame
residual is 0.0012–0.0050 g at both anchors, i.e. at that floor throughout. The
true tilt error is somewhere between zero and 0.14°, and nothing here separates
the two. The conclusion survives — it is small either way — but "it degraded
from 0.05 to 0.14 across the set" does not, and was claimed here in error.

**And this measures two of the three attitude degrees of freedom.** Gravity
constrains roll and pitch. It says nothing about yaw, and the logger requests
`.xArbitraryZVertical`, so no absolute yaw reference exists anywhere in the
system. Yaw error is therefore unobservable here — bounded only indirectly, by
the gyro-vs-Core-Motion yaw divergence of 0.0–1.4° per set. That bound is small
enough to close the question: a 1.4° frame rotation moves a point on a 10 cm
excursion by 2.4 mm, under the 1 cm spec, and it is nothing like the 180°
disagreement P2 reports on fore-aft sign.

Two things follow, and the second matters more.

*B1's default is now confirmed on the evidence it asked for.* `calibrate.py`'s
docstring named exactly this test: two anchors 40 s apart, a baseline over which
real rotation cancels and bias does not. The implied drift rate is 0.69° over
~50 s ≈ **0.014 °/s**, against a pause estimate of 0.1–0.9 °/s. The pause
estimate is 10–60× too large. Never apply it.

*C1 cannot see the error it was hoped to find, by construction.* The anchors
sample the attitude at the two moments it is most likely to be right — still,
with no linear acceleration corrupting the gravity reference. P3's error lives
DURING the rep, and a good number at the anchors says nothing about it. What
does see it is the per-rep mean, which must be zero because a rep starts and
ends at rest: bench and squat leave **0.003 g**, indistinguishable from the
0.0025 g accel bias measured on a table, and deadlift leaves **0.010–0.030 g**.
See P6. *Evidence:* `analysis/24`, `calibrate.anchor_tilt`.

Validate on **deadlift** first — not because the pipeline differs by lift
(it does not) but because it has the most external ground truth: the bar starts
at the bumper's radius (22.25 cm to bar centre, measured 2026-07-30) and ends at
a tape-measurable lockout height.

Bench and squat used to offer nothing to check against but your own judgement of
whether a curve looks plausible, which is exactly how you convince yourself a
broken pipeline works. As of 2026-07-30 they offer one thing:
`truth.VERTICAL_ROM_M` bounds their per-rep vertical travel. Do not oversell it
— a bound is not a measurement, it constrains one axis, and it cannot see phase.
It is still the difference between an unfalsifiable claim and a weak one.
