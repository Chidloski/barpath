# Handoff — 2026-08-07, end of the C31/C31a/C31b/C32/C33 session

Transient file. Everything durable is in `TASKS.md`, `CLAUDE.md`,
`analysis/README.md` and **`analysis/C31b_STATE.md`**, which is the fullest
single summary of where this stands. **Delete this when the work below is done.**

**You are not alone in this repo.** Read
`/Users/sam/Desktop/barpath/HEARTBEAT.md`, claim the paths you are about to
write, release when you stop. Rules in `CLAUDE.md` under **Concurrency
protocol**.

## Where the work is — READ THIS BEFORE ANYTHING ELSE

**ALL OF IT IS ON `main` NOW, AND THE BRANCHES ARE GONE (2026-08-14).** The
owner merged `c29-jump-state` via PR #6 and then deleted every working branch —
`c29-jump-state`, `c34-tidy` and `c28-imu-video-oracle`. `main` is the only
branch, local and remote. Anything below that tells you to look on a branch is
telling you where the work was DONE, not where it is.

Two things landed on top of that merge and are described nowhere below, because
they postdate this file: **`src/vtrack/`** replaced `markers.py` as the referee
for `data_v2/`, and **v1 was deleted outright** — `data/raw/`, `data/video/`,
`data/synthetic/`, `truth.py`'s plate-template tracker and `analysis/tracking/v1/`.
`src/capture.py` holds what survived `truth.py`. See `TASKS.md` entries F1.

*This paragraph replaced one saying everything was on `c29-jump-state`, unmerged,
with `main` at `ae14c40`. The rule it stated still holds and is worth repeating:
`segment.py`, `correct.py` and `pipeline.py` are branch work under CLAUDE.md's
reconstruction-modules rule, and **the owner lands it** — do not merge on their
behalf and do not push `main`.*

Seven commits, oldest first: `a2494b4` `7bc4bcb` `bc66fb1` `18501a3` `70b2a63`
`cba3e1b` `cc86651` `ff89c41` (eight, counting `ff89c41`).

Working tree clean apart from `HEARTBEAT.md`, which is normal and permanent.
Suite is **525 passed, 1 skipped, 8 xfailed, 7 xpassed**, ~23 minutes.
The 7 xpassed are expected and are *good news*: all seven template-refereed
benches now beat the flat-line null, where four used to.

## Newest first: the corpus is fully refereed as of 2026-08-15

**16 of 16 captures now score.** G2 lifted `vs_truth`'s squat refusal and G3
added `src/shortset.py`, a variant clock for sets too short for the periodic
machinery — the three SINGLES (`bench_117.5x1`, `deadlift_200x1`,
`squat_170x1`) had never been refereed by anything. They come in at h 0.96 /
2.66 / 2.05 cm, all three beating the flat-line null.

Three things to carry forward rather than rediscover:

- **The singles never had a segmentation problem** — only a sync one. The
  proposed "maximum displacement between IMU dwells" rule was built and lost to
  the existing segmenter, because integration drift produces more apparent
  displacement than a rep does. Don't re-propose it without removing the drift.
- **`deadlift_170x4_3` is scored through a clock fitting 22.8% drift** (slope
  0.7715, 216 ms residual, against ~0.4% and ~9 ms everywhere else). Nothing
  gates on `drift_pct` or `rms_ms`. Unfixed, pinned by a test.
- **`capture.sync` and `metrics.bench_sync` return `fit["offset"]` with
  opposite signs.** Safe until someone compares them; it caught G3 mid-measure.

Still open and worth a capture: **a real deadlift double.** A deadlift set has
no gap between reps, so no truncation of a longer set can imitate one, and
deadlift doubles are the one short-set case still unvalidated end to end.

**The suite no longer skips 121 tests (G5, 2026-08-16).** 51 test functions
were removed because they could never run again — every one selected a v1
capture F1 deleted. The pass count did not move (381 full suite), skips went
167 -> 4, failures unchanged at 4. **No speedup: the suite is 24m44s before and
after**, because a skipped test never decoded anything in the first place; the
long pole is `test_vtrack::test_every_clip_tracks_plausibly` over sixteen clips,
which is live and correctly slow. Two things to know: the three sensor
noise-floor tests went with them and are **restorable by recording one
stationary capture** (nothing gates that finding until someone does), and
deadness was decided by "every parametrisation skipped" rather than by name —
matching names statically deleted three live tests before that was caught.

**The standing failure count is 4, not 6 (G4, 2026-08-16).** Two of the six were
stale TESTS rather than defects, both left by F1's deletion of the v1 corpus: a
registry of "known mis-tracked" clips of which two were deleted and the other two
now track fine, and an assertion that `infer_tracker` returns `"plate"` for a
tracker that no longer exists. Both fixed. Watch for the same shape elsewhere —
two further tests in the same file had been **skipping silently** on a deleted
capture since 2026-08-14, so they were not failing and nobody noticed; a skip is
not a pass. The four that remain are real defects, and `deadlift_170x4_3` is in
two of them.

## The one thing that changes how you read every number here

**Step 6 is ON by default.** `pipeline.run(wrist_offset=)` defaults to `"auto"`
and applies the tape-measured `d` from `correct.WRIST_OFFSET_M`. The owner
ruled on it, and the reason is not the metric: this project reconstructs the
**BAR** path and the sensor is on the **WRIST**, so omitting a measured
geometric term answers a different question.

**Every number recorded in the docs before 2026-08-06 was measured with step 6
OFF.** Pass `wrist_offset=None` to reproduce any of them. Every figure in
`analysis/` numbered below 48 shows a different quantity.

`d` (owner's tape, from the middle of the watch face to the bar centre, in watch
axes): squat 5 cm toward the crown + 4 cm out of the case; bench and deadlift
9 cm toward the crown + 3 cm into the case. `apply_offset`'s `d` is BAR→WATCH,
the **negative** of that. B2 still stands: `d` cannot be *fitted* from video.

## What this session established

- **C30's "the horizontal channel is EMPTY" is overturned.** It was an artefact
  of step 6 being off. Deadlift accel correlation 0.12–0.23 → **0.43–0.64**.
- **C31a fixed the paused-squat short-count.** `_longest_cadence` now admits on
  LOCAL drift, not global spread. Counting was **30/30 captures, 124/124 reps**.
  No constant could have counted both binding captures — they were disjoint.
  *Superseded twice since: F1 deleted v1 and found the 2026-08-08 captures had
  never been under test (two miscounted), and G1 fixed both on 2026-08-15.
  Counting is **16/16 captures, 64/64 reps** on the live corpus. Note C31a's
  disjointness no longer reproduces — the capture that made it disjoint went
  with v1. See TASKS.md G1.*
- **C28's ladder survives `d` being known.** Pinning `lever` improves
  leave-one-out on 4 of 5 rungs, but the family is still dead: best LOO 4.25 cm
  against a null of ~1.6.
- **C32 cleared `bench_spoto_95x5_1`.** Its 0.68 warning is `truth.find_plate`
  mis-detecting the rim, not the stickers. Scale swept 47% — dissent is
  scale-invariant.
- **C33 paid down 41 hours of doc debt** after the owner released C30b's stale
  claim.
- **The pause hypothesis is half right** (`analysis/49`). Core Motion really does
  lean on the accelerometer for gravity when still — tilt/yaw rises when
  quasi-static on 22 of 30. But it separates the two LIFTS, not the two STYLES:
  a paused squat concentrates the correction mid-rep, a paused bench does not.
- **C29's impact correction and `d` do NOT compose** (`analysis/51`): control
  10.66 → C29 3.93 → both 3.89 cm. Both target the same instant.

## Two claims of ours that are WRONG and are not yet fixed in the docs

**1. "The 8-sticker squat footage tracks at 100%."** It does not. Measured:

    squat_pause_145x4_1   100%   0.88 px   travel 59.4 cm   (good)
    squat_pause_140x4_2   100%   0.69 px   travel 60.1 cm   (good)
    squat_170x1          97.8%   1.11 px   travel 14.0 cm   MIS-TRACKED
    squat_pause_140x4_3  96.7%   1.12 px   travel 24.7 cm   MIS-TRACKED

14 cm of travel for a 65 cm squat is not the bar. Coverage and residual look
healthy because the constellation is fitting *something* rigidly — the same
shape of failure as C12. **This overstatement is committed and pushed**, in
`analysis/50`'s caption, `analysis/README.md` and the docs C33 wrote. Fixing it
is the first job for the next agent.

**FIXED, BY THE TRACKER RATHER THAN THE DOCS (measured 2026-08-16, G4).** The
rebuilt `src/vtrack/` referee tracks both of these correctly now — `squat_170x1`
at **63.7 cm** and `squat_pause_140x4_3` at **65.8 cm**, against the 14.0 and
24.7 above. All sixteen cached clips are plausible: travel 26.1-65.8 cm against
floors of 18.0-40.5, coverage >=97.4%, every rep count matching. The claim above
was true of `markers.py` on 2026-08-07 and is false of the referee that ships.

The paragraph that followed said `bench_sync` refused those two clips *because*
they were mis-tracked, and that turned out to be wrong in both directions. Both
now track, and both were still refused — because `squat_170x1` is a SINGLE and
has no cadence (G3 gave it one, `src/shortset.py`), and `squat_pause_140x4_3`
was refused by a blanket squat gate that G2 removed. Neither refusal was about
the path being wrong.

**2. "The largest wrist rotation in a deadlift is the turnaround at the floor."**
Written into `ff89c41` and `analysis/51`. The owner challenged it and was right.
The arms hang near-vertical through a deadlift, so there is no reorientation.
Measured: 53–67% of the swept angle per rep IS in the outer 20% of phase, and
`|d/dt(R·d)|` peaks at phase 0.03 at 7.8× the rep median — but swept angle is
**193–311°/rep against a net wrist swing of ~22°**, so ~90% of it is
back-and-forth. It is **strap ringing**, which B6 already identified: the watch
moving after the bar has stopped. The *watch* rotates; the wrist does not.

**That carries a consequence nobody has followed up.** Step 6 assumes `d` is a
rigid constant in body coordinates. During ringing the watch is not rigidly
indexed to the wrist, so at exactly the instant `R(t)·d` moves most, step 6's
premise is false. Applying it there may be actively wrong, not merely useless.
This is the most interesting open thread in the session.

## Suggested next jobs, in order

1. **Fix the two wrong claims above** in `analysis/50`'s caption,
   `analysis/README.md`, `CLAUDE.md` and `TASKS.md`. Small, and it is the class
   of error this project treats as most expensive.
2. **Why do two of four squats mis-track?** Suspect `seed_frame` locking onto a
   rigid non-bar constellation — the C21/C23 failure mode. Fixing it is what
   turns squat into a refereed lift for the first time.
3. **Then lift `metrics.vs_truth`'s squat refusal**, whose stated reason
   describes the OLD template footage and is stale. It needs a validated squat
   sync first; the paused squats' bottom dwell is a candidate landmark anchor
   that would not inherit `bench_sync`'s untested transfer.
4. **The referee split** — `d` helps uniformly under the template referee and is
   mixed under markers, and C24 already had them ~20% apart on ROM. Neither has
   been shown right, and P2's verdict depends on which is.
5. **Test whether step 6 should be suppressed during strap ringing**, per the
   consequence above.

## Open questions for the owner

- `truth.STICKER_PLATE_DIAMETER_M` has no 2026-08-06 entry, so bench falls
  through to 0.425 m and squat to 0.450 m **by accident rather than decision**.
  If one stickered 425 mm plate moved between the bars, squat is 5.9% out.
- The sticker-circle diameter still wants a tape measure, into
  `bar_path(sticker_diameter_m=)`. C32 tried to derive it and correctly refused
  to ship the result.

## Practicalities

- Tracked-path cache for all 13 `data_v2` clips (slow to rebuild, ~1–2 min each)
  was in the previous session's scratch and **will not survive**. Re-tracking is
  the main cost of any video work.
- 8 GB of RAM: do not run many concurrent full-res clip decodes. Disk got tight
  during this session.
- Drivers added: `--pausedsquat` (47), `--dpaths` (48), `--pauseattitude` (49),
  `--pipelinenow` (50), `--jumpd` (51). *Since: `--dlparabola` (52), and G1's
  `--segfixes` (53) and `--vstracked` (54). Next free analysis number is
  **55**.*
