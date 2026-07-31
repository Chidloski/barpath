# Handoff — 2026-07-31, end of the C8/C9/C10 session

Transient file. Everything durable is already in `TASKS.md` (C8, C9, C10
entries), `CLAUDE.md` (P1, P2) and `analysis/README.md`. **Delete this when the
work below is done.**

Working tree is clean, suite is **359 passed, 1 skipped, 6 xfailed** (~6.5 min;
there is no `pytest-timeout` plugin, do not pass `--timeout`).

Recent commits: `ab1bc6d` C10, `40f8fbc` C9, `34adadc` capture protocol,
`9979006` C8.

## Read this first: the one number that reframes everything

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

The bigger risk is not video leakage, it is that **every tuned constant in this
project was chosen on the same 17 captures it is evaluated on** — cadence
tolerance 1.45, the ROM bands, `SEEDS`, `PERIOD_TOL`, `RIVAL_FRAC`. Nothing is
held out. Worth fixing the discipline before adding more constants.

## Pre-gym work, in order

### 1. Bench as the impact-free control (P3/P6) — highest value

C8, C9 and C10 set this up and it has not been run. The setup:

- Deadlift loses **-0.37 to -1.48 m/s** of vertical impulse per rep, on 8 of 9
  intervals, measured between `segment.rest_instants`.
- P6 puts three quarters of deadlift's per-rep error in the +/-100 ms around
  each floor impact — 6% of the samples.
- **Bench has no floor impact**, is out by 0.6-3.7 cm against deadlift's
  5.05-15.44, and disagrees with itself on fore-aft sign on 1 of 29 reps against
  deadlift's 4/6, 2/6, 1/3.

The measurement nobody has made: **bench's vertical momentum closure.**
`rest_instants` and the closure gate (`tests/test_real_data.py`, search
`momentum`) are deadlift-only because `rest_instants` was validated against
deadlift video. Bench now has video, so it can be validated the same way and the
closure measured.

If bench closes and deadlift does not, the deficit is *conclusively* the impact
rather than anything pipeline-wide. C9 removed the last confound: bench windows
are now known to be correctly placed, so a bench-vs-deadlift difference cannot
be blamed on segmentation.

### 2. B6's splice — integrate across the impact, not through it

The only surviving item in B6's own plan. **Note `TASKS.md` B6 still says "#14
first, not as a side quest... now on the critical path" — that is stale.** #14's
strap-resonance detector was REMOVED as undetectable at 100 Hz (post-impact
spectrum has no repeatable peak, 10-47.5 Hz across 15 impacts, and Nyquist is
50 Hz). Fix that sentence when you touch B6.

The state on both sides of the impact is known and validated at |v| < 0.10 m/s.
The constant-bias family is arithmetically ruled out — a constant cannot
represent an impulse; see the table in B6 and `analysis/25`. Splice, do not
model. Item 1 above should be done first because it tells you whether this is
the whole story.

### 3. Make `beats_null` a gate

It is reported but nothing asserts on it. Mirror
`test_horizontal_meets_the_spec`: an xfail carrying the target (`beats_null > 1`
on every capture) so the number is executable and visible on every run, plus a
non-regression ceiling per capture. This is the cheapest guard in the project
against reporting a change as an improvement when it still loses to a flat line.

### 4. B4 — the axis sign

Step 8's eigenvector sign is arbitrary and unresolved. It now has evidence it
lacked: bench disagrees with itself on **1 of 29** reps against deadlift's 4/6,
2/6, 1/3. Product-facing — step 9's overlay needs a stable sign.

### 5. A holdout discipline, before adding more constants

Cheap version: nominate two captures (one bench, one deadlift) as held out,
never looked at while tuning, and check them only at the end of a change. Would
have caught nothing so far as far as anyone knows — which is exactly the problem,
because nobody can currently say.

## Explicitly NOT pre-gym

- **B3 (rework the per-rep detrend).** Worth 2-4 cm, measurable now, but
  CLAUDE.md is right that it is "the thing that was supposed to hide" the error.
  Do it after B6 so it fixes a premise rather than compensating for one.
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
2. **A sessionless capture with 30+ s of wrist-down** — the falsifier for C7's
   deletion of the workout session, which was only measured to 20 s. If the rate
   drops, every capture since C7 is suspect. Never collected.
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
