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

## NOT DONE — in priority order, with what is already known

**A. The C28 oracle ladder with `lever` PINNED at the measured `d`.** This is
the highest-value item left. C28 fitted `lever` as three FREE parameters and
found the whole family capped at the null with nothing transferring under
leave-one-out (1.23 cm with 15 params; every model 3.3-4.6 under LOO). Fixing
`lever` at the tape value removes three degrees of freedom that were absorbing
P3, so the LOO question is genuinely re-opened. `src/oracle.py` has the ladder;
`TERMS` and `fit` are the entry points.

**B. C29's rest-window jump correction WITH `d`.** C29 took deadlift h_rms
10.66 -> 3.93 (frame-internal; NOT 8.21 -> 3.93, see CLAUDE.md's caveats) with
step 6 OFF. Do the two compose, or correct the same thing twice? Two captures
crossed `beats_null = 1.0` under C29 for the first time in the project.

**C. Explain the bench dissent.** `d` helps acceleration on 6 of 6 and position
on 3 of 6. Hypothesis not yet tested: `d` is right in DIRECTION and wrong in
effective MAGNITUDE, because the bar is gripped and wrist extension under load
changes the lever arm — which `apply_offset`'s own docstring names as the thing
it cannot model. Sweeping |d| at the measured direction tests it cheaply.
**Confounder to clear first:** `markers.validate` warns that
`bench_spoto_95x5_1` puts the sticker circle at 0.68 of the plate radius
against the 0.858 `STICKER_RATIO` scales by, so that capture's absolute scale
is unconfirmed. The capture where `d` "hurt" most is the one whose ruler is
least trusted. Do not conclude anything about paused bench until that is
settled — a tape on the sticker circle settles it.

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
