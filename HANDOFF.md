# Handoff — 2026-08-03, end of the C21/C22/C23 session

Transient file. Everything durable is in `TASKS.md` (C21, C22, C23), `CLAUDE.md`
(the two-referees section, P1) and `analysis/README.md` (39, 40). **Delete this
when the work below is done.**

**You are not alone in this repo.** Read
`/Users/sam/Desktop/barpath/HEARTBEAT.md`, claim the paths you are about to
write, release when you stop. Rules in `CLAUDE.md` under **Concurrency
protocol**. And **work on `main` and do not open a pull request** — see
**Branches, commits and pull requests**, added by C20.

Working tree is clean apart from `HEARTBEAT.md`, which is normal and permanent.
Suite is **468 passed, 1 skipped, 11 xfailed, 4 xpassed**, ~17 minutes. The 4
xpassed are expected: the benches that beat the null model.

**Three commits are on `main` and NOT pushed.** The owner pushes.
`2bae05e` C23, `0a2d359` a figure correction, `ebbedc7` C21/C22.

## What changed, in one paragraph

`markers.py` went from refereeing nothing to refereeing the four bench captures
of 2026-08-03 — the first captures in this project scored by markers rather than
by `truth.py`'s plate template, and the first time `metrics.vs_truth` has run on
marker footage end to end. `seed_frame` now decides by **verification**
(trial-track a shortlist, keep what actually follows the bar) instead of by
per-frame appearance. Both squats from that session were deleted; their plate
cannot be refereed at all.

## Read this first: the corpus shrank, and the counting claim shrank with it

`data_v2/raw` is **four bench captures**. The two squats were deleted on the
owner's instruction — video and IMU log, gitignored and untracked, so they are
gone. The corpus is **21 captures and 86 reps**, counted 86/86.

That is a **smaller** claim than the 22/23 captures it replaces, not a better
one: the capture that broke counting was removed rather than fixed. And **C22's
finding is measured entirely on `squat_150x5` and cannot be re-run.** Its
numbers are kept in `TASKS.md` as the record. Do not treat them as reproducible,
and do not be surprised when nothing in `data_v2` matches them.

## Read this second: the first independent confirmation in the project

Whole-clip marker travel against the IMU's per-rep ROM, same set, two
instruments sharing no component:

    bench_92.5x4_1   27.8 cm vs 29.6   -6.1%
    bench_92.5x4_2   28.9 cm vs 29.4   -1.6%
    bench_92.5x4_3   29.5 cm vs 30.1   -1.8%
    bench_95x2       29.0 cm vs 29.5   -1.6%

Three of four inside two percent. **`bench_92.5x4_1`'s -6.1% is unexplained**
and is the loose thread here; the gate is deliberately left at +/-15% rather
than tightened onto a residual nobody has run down.

That agreement only appeared after a scale bug, and **the wrong SIGN is what
exposed it** — travel read 9-13% low when the clip contains an un-rack and
should read high. `truth.plate_diameter` keyed on the lift alone and returned
the black notched plates' 425 mm for a session shot on 450 mm blue calibrated
discs. `truth.CALIBRATED_SESSIONS` now carries the exception, keyed on the date
in the filename. **If a future session uses another plate set, that table is the
first thing to check.**

## Pre-gym work, in order

### 1. The squat plate needs re-stickering — and it is the owner's job, not code

`squat_140x5` and `squat_150x5` could not be tracked, and after a long
investigation the cause is not in the tracker. That plate's three stickers sit
at **94.9 / 111.4 / 153.7 degrees** rather than ~120. Two consequences:
`_triangle_ok` scores the true constellation 0.000 and rejects it, and — the one
that matters — the centroid the whole method rests on falls **18.4% of the
radius** from the true plate centre, about 2.8 cm, against a 1 cm spec. Bench's
plate is 129/102/129, i.e. 8.6%, which is the entire difference between the two
lifts working and not.

**Do not try to fix this in code.** Loosening `_triangle_ok` was measured and
admits the constellation without making it track, and no tolerance repairs the
centroid bias. Sticker the next squat plate at 120 degrees with a tape measure.

### 2. `bench_92.5x4_1`'s -6.1%

Cheap, self-contained, and the only anomaly left in the bench numbers. The other
three agree to under 2% with the same code and the same plate.

### 3. B4 — the axis sign, and B6/B3

Not touched this session, and unchanged from the previous handoff.
`reps_disagreeing_on_sign` is 0 on every bench capture now measured, including
the marker-refereed ones, and 4/6, 2/6, 1/3 on deadlift — the instability is a
deadlift phenomenon on the evidence held. See P2. B6 needs a correction **local
in time**; C19 established that raising the detrend's order does not help, so do
not re-propose a higher-order detrend.

### 4. A holdout discipline, before adding more constants

Unchanged and still not done. This session added `CALIBRATED_DIAMETER_M` and a
0.05 rigidity normaliser; both are justified in their docstrings against
measured populations rather than fitted, but the count of hand-set constants
keeps rising.

## Gym shot list

**Corrected — item 3 of the old list was wrong.** "Camera stepped back converts
squat to truth" was written before this session. Stepping back would not have
helped: the squat footage was fine and the plate was the problem.

1. **Re-sticker the squat plate at 120 degrees, then re-shoot a squat.** This is
   the whole squat problem. Highest value on the list.
2. **A capture WITH the session running and 30+ s of wrist-down.** Unchanged.
   C16 restored the workout session; every capture between C7 and C16 is
   suspect.
3. **A bench single.** C5's singleton rule is predicted to segment onto the
   unrack (`bench_92.5x2`'s unrack moves the bar 0.433 m against 0.295 and 0.239
   for its real reps), and a bench single **cannot be synced** by `bench_sync`
   at all, since the whole-rep-period rule needs a cadence.
4. **A deadlift on marker footage.** All three deadlift captures are refereed by
   the plate template, which C12 showed is lost at lockout — 97-100% of
   top-of-travel frames below `GOOD_SCORE`. Markers do not have that failure.
   This is the single change that would most improve the numbers P2 is built on.
5. **Tape the deadlift lockout height, and the wrist-to-bar offset `d`.** `d`
   unblocks step 6, implemented and off by default purely for want of the
   number.
6. **Measure the plates you actually film on**, and record which set was used.
   `truth.PLATE_DIAMETER_M` and `CALIBRATED_SESSIONS` both depend on it, and
   getting it wrong is worth 6% of every distance.

## Things that will bite you

- **`markers.bar_path` is ~25 s per clip now**, up from 15, because seeding
  trial-tracks up to twelve hypotheses. That is why `track` takes a `dets_all`
  cache — if you write anything that tracks repeatedly, pass it, or you will pay
  `detect` over every frame every time.
- **`static_points` suppresses detections that recur at a fixed pixel.** It
  assumes a tripod; a hand-held camera breaks it outright. And a capture where
  the bar is motionless for more than 70% of the clip will have its own stickers
  suppressed — which is why suppression is applied to re-acquisition only and
  not to ordinary association. Applying it everywhere cost `deadlift_190x1` 72%
  of its frames.
- **`_trial_merit` must never reward a low residual on its own.** A two-marker
  fit is exact and reports 0.00 px; that is precisely what the pre-C23 seeder
  did while tracking a bench, reporting "three markers matched, sub-pixel
  residual". The merit leads on the three-marker fraction and multiplies by
  apparent-size rigidity for that reason.
- **`analysis/39` depicts pre-C23 behaviour and cannot be regenerated.** The
  seeder it labels "shipped" now finds the plate.
- **`circumradius` in `markers.py` is a MEAN radius from the centroid, not a
  circumradius.** Correct for the tracker's purposes; wrong to draw a circle
  with. Use `plot._circumcircle` for figures. Two figure versions were published
  wrong before the owner caught it.
- **`truth.SEEDS` is hand-placed**, one row per bench capture in `data/video`.
  The `radius` in that row *is* the pixels-to-metres scale (~4% at +/-2 px on
  ~48). `data_v2` captures do not use it.
- **`vs_truth`'s horizontal rms does not test time alignment on any lift.**
  Shift a deadlift by 3 s and horizontal moves 5.05 -> 4.62 while vertical
  explodes to 19/20/32. It is a magnitude comparison. Phase evidence comes from
  `analysis/17`, `analysis/30` and the containment gates.
- **Auto-seeding bench with `truth.find_plate` is not a tuning problem.** Four
  seeders were tried and all four preferred the bench-and-lifter silhouette. The
  marker tracker sidesteps it by not using `find_plate` at all.
- **The re-rack anchor is disproven**, not merely unused: on deadlift, where
  truth is known, it misses by +615, +660, +510 ms.
- **Check a referee where it is used, not on average.** Milestones 1-6, C8's
  peak-height threshold, C10's clip composition, C12's lockout NCC, and this
  session's three admission gates that were all at zero margin on the footage
  they were tuned against. It keeps happening.
