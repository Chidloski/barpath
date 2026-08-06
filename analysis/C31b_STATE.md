# C31 / C31b — running state, 2026-08-06

Written so a cold agent can resume without re-deriving anything. C31b was
killed mid-flight by the owner's session limit and its transcript is
unrecoverable; C31 released its claims explicitly on the board and finished the
parts that were nearly done. **This file is a checkpoint, not a conclusion.**

## The one new fact everything here rests on

The owner tape-measured step 6's wrist-to-bar offset `d` on 2026-08-06. It is
now `correct.WRIST_OFFSET_M`, and its docstring carries the sign derivation.

    squat            5 cm toward the crown, 4 cm UP OUT of the case    |d| = 6.4 cm
    bench, deadlift  9 cm toward the crown, 3 cm DOWN INTO the case    |d| = 9.5 cm

`apply_offset` computes `p_bar = p_watch - R(t).d`, so its `d` is BAR -> WATCH,
the negative of what the tape reads from the watch. Corroborated, not assumed:
sweeping d's direction over the sphere at the measured magnitude and scoring by
C30's acceleration correlation, the literal tape value lands within 0.02-0.03
of the best achievable value on all three data_v2 deadlifts. It was NOT fitted.

**The shipping default has NOT moved.** `pipeline.run(wrist_offset=)` is still
None. The evidence below is why: `d` is not a clean win on bench horizontal.

## DONE — measured, and reproducible

**1. C30's headline is overturned.** Re-running C30's acceleration-error
correlation with step 6 ON (its own measurement code was never committed —
`ceba50a` holds only docs and the PNG — so it was reimplemented from the method
in that commit message, and reproduces C30's baseline to within 0.03):

    lift        best-dir horizontal corr, d OFF -> d ON
    deadlift        0.118-0.232  ->  0.432-0.641
    bench           0.798-0.919  ->  0.814-0.937   (6 of 6 improve)
    vertical        0.967-0.994, unmoved either way (the control)

The deadlift horizontal channel was never empty. It was masked by the
uncorrected wrist lever — the term C30 itself named as prime suspect while
lacking `d`. Repro: `/Users/sam/.claude/jobs/366a3089/tmp/dexp2.py`.

**2. It does NOT cash out in position, and that gap is the real finding.**
`metrics.vs_truth`, step 6 off -> on:

    capture              h_rms        beats_null    v_rms
    deadlift_160x6_1     7.22->6.65   0.23->0.25    4.57->4.57
    deadlift_160x6_2     4.55->4.39   0.34->0.35    4.51->4.62
    deadlift_185x3      11.44->10.61  0.14->0.15    2.79->2.78
    bench_92.5x4_1       3.08->1.23   0.71->1.78    3.25->2.46
    bench_92.5x4_2       1.12->1.18   2.44->2.32    3.44->2.62
    bench_92.5x4_3       1.39->1.92   1.65->1.19    3.52->2.69
    bench_95x2           1.46->0.80   2.96->5.39    2.90->2.11
    bench_spoto_95x5_1   1.17->3.54   2.65->0.88    3.72->2.91   (new capture)
    bench_spoto_95x5_2   2.76->4.45   1.16->0.72    3.83->3.02   (new capture)

Deadlift horizontal better on 3 of 3 but only ~5-8%, `beats_null` still
0.14-0.35. Bench horizontal is a coin flip. **Bench VERTICAL is the one clean
consistent effect: better on 6 of 6, ~20-25%.** Correlation is shape agreement
and blind to gain; rms after double integration is not.

**3. analysis/48_bar_path_with_d.png** — `python run.py --dpaths`. Deadlift plus
the bench where `d` helped and the paused bench where it hurt.

**4. The six new captures of 2026-08-06** run clean through the IMU pipeline;
`squat_pause_140x4_2` and `_3` short-counted and C31a fixed that (a2494b4).
Counting is now **30 of 30 labelled captures, 124 of 124 reps**, re-verified
independently.

**5. The 8-sticker squat plate TRACKS** — 100% coverage, 0.883 px median
residual. First squat footage in the project that does.

## THE CAMERA GEOMETRY (owner, 2026-08-06) — new, and it is a confound

**Squat and bench are filmed from the lifter's RIGHT. Deadlift is filmed from
the LEFT. The watch is on the LEFT wrist.** Nothing in the repo recorded this.

What it does NOT do: it cannot touch `d`, which lives in the watch body frame,
and it cannot corrupt the fore-aft sign, because `vs_truth` picks one sign per
set from the correlation and reports `reps_disagreeing_on_sign`.

What it DOES do: **on bench and squat the referee tracks the plate on the
OPPOSITE END OF THE BAR from the sensor.** Any bar tilt or uneven press moves
the right plate and the left wrist differently, and that difference is scored
as pipeline error. Deadlift is the only lift in the corpus where camera and
watch are on the same side — so on top of its landmark-matched sync, it is also
the only geometrically clean comparison here. Untested, and testable: a bar
tilting through a press should show up as a bench-only, load-dependent residual
that no wrist-frame correction can reach.

**How sharply the tape `d` is identified, by lift.** Sweeping d's direction over
a 300-point sphere grid (neighbours ~12 degrees apart) at the measured
magnitude, scoring by C30's acceleration correlation:

    capture              lit    best    gain   angle(lit, best)
    deadlift_160x6_1    0.641  0.664   0.023        16.3 deg
    deadlift_160x6_2    0.579  0.594   0.015        16.3
    deadlift_185x3      0.432  0.465   0.033        16.3
    bench_92.5x4_1      0.888  0.911   0.022        50.6
    bench_92.5x4_2      0.917  0.939   0.022        52.9
    bench_92.5x4_3      0.814  0.875   0.061        60.3
    bench_95x2          0.935  0.960   0.025        50.6
    bench_spoto_95x5_1  0.910  0.934   0.025        60.3
    bench_spoto_95x5_2  0.937  0.960   0.023        64.3

On deadlift the tape sits at the optimum within ONE grid cell, identically on
all three captures, and d is doing the heavy lifting (0.12 -> 0.64). On bench
the optimum is 50-64 degrees away but worth only 0.02-0.06 on a baseline already
at 0.81-0.94: **the objective is flat, so bench does not identify d's direction
at all.** The tape is corroborated on deadlift and merely not contradicted on
bench. Do not "improve" d by fitting it on bench — that is B2's mistake with a
new coat of paint. Repro:
`/Users/sam/.claude/jobs/366a3089/tmp/dsweep_bench.py`.

## NOT DONE — in priority order, with what is already known

**A. DONE 2026-08-06 (C31). The C28 ladder with `lever` pinned at the tape `d`:
pinning improves TRANSFER on 4 of 5 fitted rungs, and C28's negative result
still stands.** Decision rule was fixed in writing first (scratch
`DECISION_RULE_C31.md`), three data_v2 deadlifts, median then per-capture:

    rung                     arm     nfree  ceiling               LOO (held-out)
    baseline                 free      0    7.22 [7.22 4.55 11.44]  7.22
    baseline                 PINNED    0    6.65 [6.65 4.39 10.61]  6.65
    bias                     free      3    2.06                    6.50 [6.50 2.47  6.53]
    bias                     PINNED    3    2.14                    5.72 [5.72 2.78 15.14]
    bias+tilt                free      6    2.02                    6.61 [6.61 2.47 24.85]
    bias+tilt                PINNED    6    1.62                    5.60 [5.60 2.88  5.86]
    bias+tilt+scale          free      9    1.80                    6.36 [6.36 2.54 25.22]
    bias+tilt+scale          PINNED    9    1.42                    5.71 [5.71 2.55 15.00]
    bias+tilt+scale+lever    free     12    1.29                    6.59 [6.59 2.67 14.20]
    bias+tilt+scale+lever    PINNED    9    1.42                    5.71 [5.71 2.55 15.00]
    ...+gravref              free     15    1.92                    4.25 [4.25 2.76  6.69]
    ...+gravref              PINNED   12    2.16                    4.34 [4.34 2.90 11.45]

RULE 1 (ceiling) — pinning removes 3 dof so the ceiling could only worsen, and
on two rungs it IMPROVED anyway (2.02 -> 1.62, 1.80 -> 1.42). On the rung that
contained `lever`, pinning cost 0.13 cm of ceiling and saved 3 parameters.

RULE 2 (transfer, the actual test) — **PASSES as a comparison: pinned beats free
on 4 of the 5 fitted rungs** (6.50->5.72, 6.61->5.60, 6.36->5.71, 6.59->5.71;
only +gravref went the other way, 4.25->4.34). So the three `lever` degrees of
freedom WERE absorbing something real.

**But the family is still dead, and that is the finding.** The best LOO anywhere
is 4.25 cm, against a d-only baseline of 6.65 with NOTHING fitted and a
flat-line null of ~1.6. Every model, pinned or free, still loses badly to
drawing no fore-aft motion at all. Held-out `deadlift_185x3` is destroyed by
most rungs (11-25 cm). **C28's conclusion survives `d` being known: the error is
not a constant in any frame, and knowing the lever arm does not rescue it — it
only makes the failure slightly less bad.**

RULE 3 (corroboration) — **fails to corroborate, and re-confirms B2 instead.**
Fitting `lever` ON TOP of the tape gives residuals of 47.9 / 17.7 / 2.4 cm,
totals 44.0 / 17.8 / 11.8 cm at 108 / 74 / 4 degrees from the tape. Only one
capture stays near it. That is B2's ill-conditioning exactly. The corroboration
that DOES hold is the direction sweep against C30's ACCELERATION correlation
(optimum within one grid cell of the tape on all three) — the position-domain
objective cannot identify `d` because double integration and the detrend destroy
the conditioning, which is C30's point restated. Repro:
`/Users/sam/.claude/jobs/366a3089/tmp/ladder.py` and `residual.py`.

**B. C29's rest-window jump correction WITH `d`.** C29 took deadlift h_rms
10.66 -> 3.93 (frame-internal; NOT 8.21 -> 3.93, see CLAUDE.md's caveats) with
step 6 OFF. Do the two compose, or correct the same thing twice? Two captures
crossed `beats_null = 1.0` under C29 for the first time in the project.

**C. Explain the bench dissent — and the two referees now DISAGREE about it.**
C32 nominated the PAUSE: both `data_v2` captures where `d` hurt are paused
benches, and C10's table ranked the three 2026-07-30 paused benches as the
three worst of seven against the null (0.72 / 0.80 / 0.92).

**Then switching step 6 on falsified the simple version of that.** All three of
those paused benches now BEAT the null, and so do all seven template-refereed
benches — three captures crossed 1.0 that never had before, and the only three
still losing are the deadlifts. So `d` fixed the paused benches under the
TEMPLATE referee while hurting the paused benches under the MARKER referee.

The surviving split is therefore by **referee**, not by pause:

    data/video, truth.py template    d helps uniformly (7 of 7 beat null now)
    data_v2, markers.py conic        d mixed (3 better, 3 worse)

Nobody has shown which referee is right, and they are not interchangeable —
C24 already found them disagreeing ~20% on ROM. **This is the highest-value
open question now.** Note the pause still rhymes with C31a's paused-SQUAT
segmentation failure, so it is not dead as a theme, just not the whole story.

Two confounds checked; one dead, one open.
- **DEAD — the scale.** C32 swept `bench_spoto_95x5_1`'s referee scale over a
  47% span (ratio 0.681 to 1.000) and `d` made it worse at EVERY point,
  `beats_null` never above 0.92. The dissent is scale-invariant. The
  0.68-of-plate-radius warning is `truth.find_plate` mis-detecting the rim on
  all six data_v2 benches, not the stickers; the capture tracks at 100% with
  0.158 px residual over the top of travel and is fit to referee.
- **OPEN — the camera side.** The regressing benches are filmed from the side
  opposite the watch, so the referee tracks the far end of the bar (C31).

Also still untested: whether `d` is right in DIRECTION and wrong in effective
MAGNITUDE because wrist extension under load changes the lever arm — but C31b
measured position rms to be monotone in |d| out to 3x the tape, so there is no
interior optimum, which argues against it.

**Open question for the owner (C32):** `truth.STICKER_PLATE_DIAMETER_M` has no
2026-08-06 entry, so bench falls through to 0.425 m and squat to 0.450 m by
accident rather than by decision. If one stickered 425 mm plate was moved
between the bars, squat is 5.9% out. One question, not a code change.

**D. `metrics.vs_truth`'s hardcoded squat refusal is now stale for `data_v2`.**
Its stated reason describes the OLD template footage. Exploratory bypass
(routing squat through `bench_sync` by patching `truth.lift_of` in a scratch
script) gave `squat_pause_140x4_2` h 2.57->2.00, bn 1.31->1.68 and
`squat_pause_145x4_1` h 3.90->2.95, bn 0.88->1.16 with `d`; `squat_170x1` and
`squat_pause_140x4_3` were REFUSED by the guards working correctly. Those two
numbers are INDICATIVE ONLY — `bench_sync` is unvalidated on squat, and video
ROM reads 57.5-58.1 cm against the IMU's 66.1-69.1.

## Practicalities

- Tracked-path cache (all 13 data_v2 clips), pickled by absolute .mov path:
  `/Users/sam/.claude/jobs/366a3089/tmp/paths.pkl`. `metrics.resolve_path` and
  `metrics.vs_truth` both accept the dict directly. Tracking is ~1-2 min/clip;
  do not re-decode.
- Scratch scripts in `/Users/sam/.claude/jobs/366a3089/tmp/`: `dexp2.py` (the
  correlation test), `dvs2.py` (vs_truth off/on d), `sqscore.py` (the squat
  bypass), `count.py` (rep counting over every capture).

## Doc debt — OWED, and blocked

`CLAUDE.md`, `TASKS.md` and `analysis/README.md` have been held by **C30b**
since 2026-08-05T06:40Z and nothing here could edit them. What now reads false:

- **P2/P3**: C30's "the horizontal channel is EMPTY" and the whole framing built
  on it. It was an artefact of step 6 being off.
- `correct.py`'s old "d cannot be recovered ... until then it stays None" is
  already corrected in the module; CLAUDE.md still repeats it.
- **P1**: "24 of 24 captures, 101 of 101 reps" is now 30 of 30 and 124 of 124,
  and the `_longest_cadence` 1.45 / 1.35-1.55 plateau description is superseded
  by C31a's local-drift rule (plateau 1.460-1.528, ships 1.50).
- The corpus line: `data_v2/raw` now holds 13 captures, not 7.
- P2's note that squat has no external horizontal check — the 8-sticker plate
  tracks now.
