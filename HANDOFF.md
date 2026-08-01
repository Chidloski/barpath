# Handoff — 2026-07-31, end of the C8/C9/C10/C11 session

Transient file. Everything durable is already in `TASKS.md` (C8, C9, C10, C11
entries), `CLAUDE.md` (P1, P2, P6) and `analysis/README.md`. **Delete this when
the work below is done.**

**Before any of it: you are not alone in this repo.** Agents run concurrently
now. Read `/Users/sam/Desktop/barpath/HEARTBEAT.md`, claim the paths you are
about to write, and if they are already held take other work or stop. Rules in
`CLAUDE.md` under **Concurrency protocol**, added by C13 on 2026-08-01. Several
items below name the same files — B3 and B6 both want `src/correct.py` — so
expect to wait or to pick a different item rather than to queue behind one.

Working tree is clean, suite is **382 passed, 1 skipped, 12 xfailed, 4 xpassed**
(~10 min; there is no `pytest-timeout` plugin, do not pass `--timeout`). The 4
xpassed are expected and documented — they are the four benches that beat the
null model.

Recent commits: C11, `ab1bc6d` C10, `40f8fbc` C9, `34adadc` capture protocol,
`9979006` C8.

## Done since this file was written

**Item 1 (bench as the impact-free control) — done, and it went further than
planned.** `metrics.momentum_closure`, `analysis/31`, `run.py --closure`, three
new gates. The deficit is the floor landing and nothing else: bench closes over
44 intervals of real lifting, **and so do the deadlift's own pulls** — the dwell
detector splits a rep at the lockout, so floor→lockout and lockout→floor are
separate intervals of the same capture, and only the half with the landing in it
loses anything. That is a within-capture control, stronger than the
bench-vs-deadlift comparison this item asked for. B5 is reconciled rather than
contradicted: its 1.04 is an AMPLITUDE, the deficit is in the NET (0.41 on the
same 15 impacts), and the difference is B6's ringing. See TASKS.md C11.

**Item 3 (`beats_null` as a gate) — done.** Per-capture non-regression floor at
20% headroom, plus an xfail carrying `beats_null > 1`.

Items 2, 4 and 5 below are untouched and still in the order given.

## Read this first: the referee is broken where it matters most

**C12, 2026-07-31, found by the owner from `analysis/33` rather than by any
gate.** The deadlift video truth traces a flat ~10 cm fore-aft line at the top of
the pull. A deadlift lockout holds the bar against the thighs; it is the tracker
moving, not the bar. Top-of-travel NCC is 0.371/0.395/0.440 against whole-clip
medians of 0.830/0.846/0.937, and 97-100% of frames in the top 10 cm of travel
score below `GOOD_SCORE` against 0% at the floor.

It flatters the pipeline: the invented motion inflates `null_h_rms`, so deadlift
`beats_null` is 0.59/0.21/0.07, not the 0.70/0.35/0.13 quoted below. Horizontal
magnitudes barely move, so P2's 5-15x stands.

**The lesson is bigger than the bug.** `validate` checked a whole-clip median
and lockout is 8-15% of a clip. That is the fourth time this project has been
caught by an aggregate that passes while the thing fails exactly where it
matters — milestones 1-6, C8's peak-height threshold, C10's clip composition,
now this. **Check a referee where it is used, not on average.**

`truth.top_of_travel_score` and `vs_truth`'s `video_top_ncc` measure it now.
The fix is the camera, not code: shrinking the template raises NCC and makes the
track worse (ROM 60.5 -> 74.1 cm).

## Read this second: the one number that reframes everything

`metrics.vs_truth` reports `beats_null` — the pipeline's horizontal error
against the error from drawing **no fore-aft motion at all**. Six of ten
captures lose to that flat line, including **all three deadlifts** (0.70x,
0.35x, 0.13x). Only `bench_90x4_2` and `_3` clearly win, by ~4x.

So "5-15x outside spec" is the generous framing. Measured against doing nothing,
most of the horizontal reconstruction subtracts information. **Quote
`beats_null` alongside any horizontal number**, and do not report an improvement
that still loses to the flat line as progress.

## What the video is and is not

Verified structurally this session: **no pipeline module imports `truth` or
`metrics`.** `pipeline.py` touches video only after all nine steps. Delete
`data/video/` and every reconstruction is byte-identical. Keep it that way.

Two standing cautions:

- **Never fit a pipeline parameter to the video.** B2 tried for `d` and the fit
  was ill-conditioned — 21, 60, 64 and 129 cm against a real 10-15 cm, because
  P3 is nearly degenerate with `d`. `d` wants a tape measure.
- **`bench_sync` is the one place the referee touches the reconstruction**, using
  `result["velocity"]` to fit its clock offset. Mitigated (one scalar, vertical
  channel, horizontal metric, validated on deadlift to 18 ms) but it is a
  coupling deadlift does not have. Do not let it spread to anything else.

`metrics.momentum_closure` (C11) reads the video too and is still not a
violation: it is a DIAGNOSTIC, nothing in the pipeline calls it, and it uses the
video only to place its endpoints in time. Its own docstring says why the
alternatives were rejected — the reconstruction's rep boundaries would be
circular, and bench has no raw-signal anchor available even in principle.

The bigger risk is not video leakage, it is that **every tuned constant in this
project was chosen on the same 17 captures it is evaluated on** — cadence
tolerance 1.45, the ROM bands, `SEEDS`, `PERIOD_TOL`, `RIVAL_FRAC`. Nothing is
held out. Worth fixing the discipline before adding more constants.

## Pre-gym work, in order

### 2. ~~B6's splice~~ — DONE, and rejected on measurement

Built, measured against a rule fixed in advance, rejected. `analysis/32`,
`python run.py --splice`, TASKS.md B6. It removes the vertical momentum deficit
completely (−0.778 → −0.049 m/s) and loses on horizontal in every variant,
including the one where it *replaces* the detrend rather than stacking on it.

**Two findings from it that change what comes next**, both in TASKS.md B6:

- **No vertical-only fix can satisfy a horizontal decision rule.**
  `pipeline_h_rms` reads columns 0 and 1, so a column-2 correction is
  bit-identical. Obvious in hindsight; it was not obvious when the rule was
  written, and it made the rule partly mis-specified.
- **Step 7's detrend is linear and cannot absorb a correction localised in
  time.** Removing an error `e` over a window `T` injects `e·T/2` of position —
  enough to push vertical ROM to 82.6 cm against a 61 cm physical ceiling.
  **Every remaining B6 idea inherits this, so B3 now comes first.**

### 3. B3 — rework the per-rep detrend  ← NOW FIRST

Promoted from "explicitly NOT pre-gym" by the splice's rejection. Its value is
no longer its own 2–4 cm; it is that **it unblocks every localised correction
after it**, B6's included.

Two constraints on it, both measured rather than argued:

- It cannot simply be dropped. B7: closing vertical only, with nothing in its
  place, gives 495/522/337 cm. The splice is not a good enough replacement
  either (28.5/18.0/61.4). The detrend is knowingly wrong *and* load-bearing.
- Whatever replaces it must be able to absorb a quadratic, or the localised
  corrections it exists to unblock will break the ROM bound exactly as the
  splice did.

### 4. B4 — the axis sign

Step 8's eigenvector sign is arbitrary and unresolved. It now has evidence it
lacked: bench disagrees with itself on **1 of 29** reps against deadlift's 4/6,
2/6, 1/3. Product-facing — step 9's overlay needs a stable sign.

### 5. A holdout discipline, before adding more constants

Cheap version: nominate two captures (one bench, one deadlift) as held out,
never looked at while tuning, and check them only at the end of a change. Would
have caught nothing so far as far as anyone knows — which is exactly the problem,
because nobody can currently say.

C11 added to the pile rather than reducing it: `BEATS_NULL` and `NULL_FLOOR`,
and the closure gates' 0.15 m/s bounds, are all pinned from the same 17
captures. In mitigation the closure thresholds sit in a wide gap — 0.102 against
0.361 — rather than being fitted, and the amplitude gate reuses B5's existing
`IMPACT_STEP_RATIO` instead of introducing a constant. But they are not held
out, and the honest statement is that nothing here is.

## Explicitly NOT pre-gym

- ~~**B3 (rework the per-rep detrend).**~~ **Moved to item 3 above and promoted
  to first.** The reasoning here was "do it after B6 so it fixes a premise
  rather than compensating for one". B6's splice was then measured and rejected,
  and the reason it lost is the detrend — so the order is the other way round.
- **B2 / step 6.** Blocked on taping `d`. Already proven not identifiable from
  video.
- **Anything squat.** Two of four 2026-07-30 captures do not track; `vs_truth`
  refuses squat; squat is the only lift whose phase is unverified. Needs a wider
  shot, not code.
- **Any vertical-error work measured against the video.** The video's vertical
  scale is wrong by up to +/-20% per capture and the metre rule supersedes it.
  Horizontal and timing are not implicated and are safe to work on.

## Gym shot list (unchanged, all still pending)

In `TASKS.md` under Capture protocol. Summarised:

1. **Deadlift with a metre rule in shot** — fixes the per-capture video vertical
   scale error. Highest value; no code can repair it.
2. **A capture WITH the session running and 30+ s of wrist-down** — this asked
   for a *sessionless* one until 2026-08-01, as the falsifier for C7 deleting the
   workout session. **It was collected by accident and C7 lost:** captures
   truncated, and a Workout-app session took priority while the wrist was down.
   C16 restored the session, so the open test is the same one *with* it. Every
   capture taken between C7 and C16 is suspect.
3. **Camera stepped back** — converts squat to truth; lets bench drop its hand
   seeds and the ~4% scale the hand-read radius carries.
4. **A bench single** — C5's singleton rule is predicted to segment onto the
   unrack (`bench_92.5x2`'s unrack moves the bar 0.433 m against 0.295 and 0.239
   for its real reps). Also note a bench single **cannot be synced** by
   `bench_sync` at all, since the whole-rep-period rule needs a cadence.
5. **Tape the deadlift lockout height, and the wrist-to-bar offset `d`** — `d`
   unblocks step 6, which is implemented and off by default purely for want of
   that number.

## Things that will bite you

- **`truth.SEEDS` is hand-placed**, one row per bench capture. A new bench
  capture raises until you add a row. The `radius` in that row *is* the
  pixels-to-metres scale — read it carelessly and every distance from that
  capture is wrong by the same fraction (~4% at +/-2 px on ~48).
- **`vs_truth`'s horizontal rms does not test time alignment on any lift.**
  Shift a deadlift by a full 3 s and horizontal moves 5.05 -> 4.62, 9.19 ->
  7.23, 15.44 -> 15.17 while vertical explodes to 19/20/32. It is a magnitude
  comparison. Phase evidence comes from `analysis/17`, `analysis/30` and the
  containment gates.
- **Auto-seeding bench is not a tuning problem.** Four seeders were tried and
  all four preferred the bench-and-lifter silhouette. Do not re-propose without
  a genuinely new idea.
- **The re-rack anchor is disproven**, not merely unused: tested on deadlift
  where truth is known it misses by +615, +660, +510 ms. Do not re-propose
  without a way to separate the bar hitting the uprights from it dropping into
  the hooks.
