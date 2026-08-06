# Handoff — 2026-08-07, end of the C31/C31a/C31b/C32/C33 session

Transient file. Everything durable is in `TASKS.md`, `CLAUDE.md`,
`analysis/README.md` and **`analysis/C31b_STATE.md`**, which is the fullest
single summary of where this stands. **Delete this when the work below is done.**

**You are not alone in this repo.** Read
`/Users/sam/Desktop/barpath/HEARTBEAT.md`, claim the paths you are about to
write, release when you stop. Rules in `CLAUDE.md` under **Concurrency
protocol**.

## Where the work is — READ THIS BEFORE ANYTHING ELSE

**Everything below is on branch `c29-jump-state`, which is PUSHED to origin and
is NOT merged.** `main` is still at `ae14c40` (C27) and has none of it. That is
deliberate — `segment.py`, `correct.py` and `pipeline.py` all changed, which is
branch work under CLAUDE.md's reconstruction-modules rule, and **the owner lands
it.** Do not merge on their behalf and do not push `main`.

Seven commits, oldest first: `a2494b4` `7bc4bcb` `bc66fb1` `18501a3` `70b2a63`
`cba3e1b` `cc86651` `ff89c41` (eight, counting `ff89c41`).

Working tree clean apart from `HEARTBEAT.md`, which is normal and permanent.
Suite is **525 passed, 1 skipped, 8 xfailed, 7 xpassed**, ~23 minutes.
The 7 xpassed are expected and are *good news*: all seven template-refereed
benches now beat the flat-line null, where four used to.

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
  LOCAL drift, not global spread. Counting is **30/30 captures, 124/124 reps**.
  No constant could have counted both binding captures — they were disjoint.
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

It also re-explains an earlier claim: `bench_sync` refused `squat_170x1` and
`squat_pause_140x4_3`. That was reported as the guards working correctly. They
were — but those are **exactly the two mis-tracked clips**, so the sync failed
because the path was wrong, not because `bench_sync` is unsuited to squat.

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
  `--pipelinenow` (50), `--jumpd` (51). Next free analysis number is **52**.
