# barpath

Reconstruct barbell path from a single Apple Watch IMU and render it as an
overlaid 2D plot. Proof of concept only — not an app, not a product.

Read `NON_GOALS.md` before proposing anything. Its Scope section is binding.
Its Estimation and Sensing rejections were deleted on 2026-07-28 because they
rested on synthetic evidence — recover them with `git show HEAD:NON_GOALS.md`
if you want to re-argue one, but do not treat them as still in force.

## Concurrency protocol

**Binding, and it comes before everything else in this file, because it governs
whether you may write at all.**

Agents run this repo concurrently and independently. You may not assume you are
alone in it. `HEARTBEAT.md` is the board that keeps two agents off the same file;
its header states the claim format, this section states the rules.

**The board is at `/Users/sam/Desktop/barpath/HEARTBEAT.md` — the shared
checkout — always.** If you are in a worktree, that is *not* the copy beside you.
Read and write the absolute path. A claim in a worktree copy is invisible to
every other agent and is therefore not a claim.

### The loop

1. **Read the board before your first write of the session.** Not before your
   first commit, not when you get to a file that looks contended — before the
   first edit you make to anything.
2. **Claim, then edit.** Append one block naming every path you intend to write,
   including files you are about to create and plots you are about to number.
   Then re-read the board: if someone else appended an overlapping claim in the
   meantime, the **earlier `since:` wins** and the later agent withdraws its block
   and treats the paths as taken. That is the whole race resolution; it works
   because blocks are only ever appended, never rewritten.
3. **If an active claim overlaps what you need, you may not write those paths.**
   Not one line, not a docstring, not "just the test". Do other work if you have
   some — a different problem entirely, on paths you *can* claim.
4. **If you have no other work, stop.** Append a block with `status: waiting`
   naming the paths and who holds them, say so plainly in your final message, and
   end the turn. Do not poll, do not sit in a loop, and do not start something
   marginal to look busy.
5. **Release the moment you stop writing** — success, failure or abandonment.
   Set `status: released`, move the block to the log. An agent that finishes
   without releasing has left a lock nobody can safely break.

### Rules that follow from it

- **Reads are free.** Locking reads would deadlock the repo instantly, since
  every agent must read `CLAUDE.md` and `TASKS.md` to start. You may read a file
  another agent holds; expect it to change under you.
- **Never break, edit or shorten another agent's claim.** If one looks abandoned
  — a stale `since:` and no sign of progress — you still do not take it. Say in
  your final message that it looks stale and let the owner adjudicate. A wrongly
  broken lock loses work silently, which is worse than a stall the owner can see.
- **Claim the shared docs late and briefly.** `CLAUDE.md`, `TASKS.md`,
  `README.md`, `HANDOFF.md`, `analysis/README.md` and `src/README.md` are touched
  by nearly every task, so an agent holding them for the length of its work
  blocks everyone. Do the code and the measurement under a narrow claim, then
  take the docs in a short window at the end and release them straight after.
  This does not weaken the same-commit docs rule below: it still requires the
  docs in the same commit, it just does not require holding them throughout.
- **Reserve `analysis/NN_*.png` numbers by claiming the filename** before you
  generate it. Two agents will otherwise both take the next free number.
- **`data/raw/` is read-only for everyone**, so it never needs claiming, and a
  claim on it should be refused.
- **Claims are never committed.** The header is a normal tracked file and is
  amended like any other doc; the claim sections are live state and stay as
  working-tree changes, so that the file preventing conflicts does not generate a
  merge conflict on every branch. Expect `HEARTBEAT.md` to show as modified in
  the shared checkout indefinitely — that is it working — and never `git stash`,
  `git checkout .` or `git reset --hard` there, which silently destroys every
  live claim in the repo, other agents' included.
- **`git add -A` in the shared checkout stages the board, and nothing can stop
  it.** `HEARTBEAT.md` is tracked, so no `.gitignore` rule reaches it — the
  protection has to be the habit. Stage explicitly; if you have already run it,
  plain `git reset` unstages everything and destroys nothing. **Do not reach for
  `git checkout .` or `git reset --hard` to tidy up afterwards**, which is the
  line above and is how a fumble becomes lost work. Learned on 2026-08-02, when
  one `git add -A` staged the board, four capture CSVs and an agent worktree as
  an embedded git repository. `.gitignore` now covers the last two; the board is
  the one that needs you.
- `tests/test_heartbeat.py` checks the board parses and that no two active claims
  overlap. It is a format gate, not a lock manager; passing it does not mean you
  hold what you think you hold.

### What this does not do

It is advisory. Nothing enforces it at the filesystem, so it fails exactly when
an agent skips step 1 — and a skipped claim is invisible until two edits collide.
It also cannot see work in progress that was never claimed. Treat a clean board
as "nobody has told me otherwise", not as "the repo is free".

## Branches, commits and pull requests

**Work on `main`, in the shared checkout, and do not open pull requests.**
Added 2026-08-03 by C20 after five agents in a row branched and opened one.

The board above is why. `HEARTBEAT.md` already does the job a branch and a PR
would do here — it keeps concurrent agents off the same files and surfaces a
collision before it happens. A branch on top adds merge ceremony to a mechanism
that has already handled the conflict, and with one human in the loop a review
step reviews nothing. Every branch also has to be landed by hand, and one left
behind after a merge diverges and stops fast-forwarding.

### The rule

1. **Commit to `main`. Do not push.** Edit, run the suite, commit with the docs
   in the same commit (see the same-commit rule below). Then **stop and say what
   you committed.** The owner pushes. Never `git push origin main`, never
   force-push, never merge on their behalf.
2. **Take a branch for the reconstruction modules, and only those.** The line is
   one the repo already draws: no pipeline module imports `truth` or `metrics`,
   so the reconstruction and the things that referee it are already separate.

   | branch | main |
   |---|---|
   | `io.py`, `calibrate.py`, `orient.py`, `integrate.py`, `segment.py`, `correct.py`, `project.py`, `pipeline.py` | `metrics.py`, `capture.py`, `vtrack/`, `plot.py`, `synth.py`, `run.py`, `tests/`, `analysis/`, all docs |

   Anything that changes the bar path gets a branch, because it can be measured
   and rejected — B3's quadratic detrend and B6's splice both were, and both
   deserved somewhere to fail. Anything that only measures or describes the
   reconstruction goes straight to `main`.
3. **A branch is still not a PR.** Push the branch, say its name, and let the
   owner land it. Open a pull request only if they ask.

### If you are a background job

The harness may tell you to call `EnterWorktree` before editing and to open a
draft PR without asking. **`.claude/settings.json` sets
`"worktree": {"bgIsolation": "none"}` for this repo so the first half no longer
applies** — you can edit the shared checkout directly. Ignore the second half:
this file outranks it. Nothing fails if a PR is skipped.

If isolation is somehow still enforced, note that the guard covers the Edit and
Write tools but **not Bash**, which is how `HEARTBEAT.md` stays writable at the
shared path — that is a necessity of the protocol above, not a licence to route
ordinary edits around the guard.

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
5b. `correct.fit_drift_tilt` — a world-horizontal attitude drift rate, fitted
   against the set's own rep-to-rep dispersion, then applied back at step 2-3
   and steps 3-4 re-run. **ON as of 2026-08-16 (H8).** Numbered 5b because it
   corrects the ATTITUDE but needs rep windows to fit, so it cannot precede
   step 5. Not gated on the lift: it is self-limiting, finding |beta| of
   0.001-0.008 deg/s on bench and squat against 0.008-0.051 on deadlift.
6. `correct.py` — subtract the wrist-to-bar offset R(t)·d. **ON as of
   2026-08-06 — read the banner immediately below before quoting any number
   from this file.**
7. `correct.py` — per-rep linear detrend so each rep closes.
8. `project.py` — **the display axis comes from the ATTITUDE as of 2026-08-16
   (H9)**, via `anatomical_axis`: the hand is clamped to the bar, so fore-aft is
   a fixed direction in watch coordinates and one angle (`BAR_ANGLE_DEG`) fixes
   it. PCA on horizontal displacement is still computed and still supplies
   `ratio` and `excursion` for `confidence`, but **it is no longer the axis** —
   H2 measured it sitting 4 degrees from the axis of the INVENTED parabola, with
   11 of 13 captures outside this module's own 20-degree tolerance. **And the
   SIGN is resolved too (B4, closed 2026-08-16)**: `FORE_AFT_SENSE` turns the
   line into a direction from the wrist, the grip and the attitude, checked
   against the video through `tracked.CAMERA_SIDE` on 8 of 9 checkable captures.
   A path can no longer silently mirror unless the lift cannot be named.
   **THE CAMERA-SIDE STEP OF THAT DERIVATION NOW HAS EVIDENCE AGAINST IT (H15,
   2026-08-17).** The first capture ever filmed from the other side —
   `squat_145x4_2_20260817`, mirrored in the footage against its own
   session-mates — was predicted to invert every sign while
   `sign_agrees_with_geometry` stayed TRUE. It did not invert, and the flag now
   reads FALSE. The flip also clusters by SESSION rather than by camera side:
   all three 2026-08-13 squats flip while being filmed from the usual side.
   **Read the caveat before quoting it** — that capture is the only squat in the
   corpus that loses to the flat-line null (`beats_null` 0.83), so its fore-aft
   may be mostly invented, which would make the test compromised rather than
   decisive. It is the first evidence either way, not a closed case.
9. `plot.py` — overlay reps, aligned by start point, horizontal stretched 4x.

### Step 10, which is not a step: `display.py`, the product view (H13, 2026-08-16)

**A layer AFTER step 9, not a change to any of the nine.** It consumes
`planar` / `vs_truth`'s `curve_pipeline` and returns curves to draw: a smoothed
path, a speed to colour it by, and one average rep with the odd one labelled.
No reconstruction module was touched and **no shipped number moved**. Run it on
the video's tracked path and it does the identical thing, which is how every
claim below was checked — 13 refereed captures, 61 reps.

**The defaults, and what chose them.** `savgol` at `strength = 0.20` (the
fraction of the rep the kernel spans), `turnaround` alignment, `median`
averaging. Savitzky-Golay costs the real bar less than a boxcar, a Gaussian or
a spline at **every** level tried; the level is the strongest whose
90th-percentile distortion of the VIDEO path stays inside half of each axis's
spec (0.17 cm horizontal, 0.65 cm vertical, against a boxcar's 0.50 / 2.79).

**Three results worth carrying, and the first is the one to remember:**

- **Smoothing does not change accuracy at all** — 2.07 cm median horizontal
  error against the video, unmoved by any method at any level to 0.30. That is
  P3 restated from the display side: the error is at rep frequency, so there is
  no high-frequency component for a smoother to reach. Smoothing is free and it
  fixes nothing.
- **Averaging does.** 1.95 -> 1.52 cm, and the whole of it is the ALIGNMENT:
  resampling each rep about its own turnaround rather than on a uniform time
  grid takes the vertical from 8.30 cm to 3.00. The averager barely matters.
- **Excluding the anomalous rep does NOT improve the average** (1.52 -> 1.70),
  because the odd rep is usually real: 5 IMU flags against 6 video flags, 4 the
  same rep, and on every set where the IMU fires the video fires on that rep
  too. Ship the flag as a LABEL, not as a deletion.

**What the video corroborates, which is the design of the whole display.**
Mean concentric velocity r = +0.97 (median error 0.020 m/s, and it ranks the
reps of a set the way the video does on **13 of 13**), peak speed +0.97,
concentric duration +0.98, vertical ROM +0.99, turnaround phase +0.90. Fore-aft
**magnitude** r = -0.03. So tempo and vertical travel are showable as numbers
and fore-aft distance is not — the product view draws the path with an
unlabelled horizontal axis, which `plot.py`'s display rules already required
for a different reason. A sticking-point cue was built, measured at r = +0.28
with its argmin on a window edge, and deleted rather than shipped.

One definition earned its own function and is worth knowing about. `concentric`
is the longest run where the bar is actually rising (v > 0.05 m/s), **not** the
rep's lowest point to its highest. Under the extremes definition MCV agrees
with the video at r = +0.53 and ranks a set's reps correctly on 8 of 13; under
the threshold it is +0.97 and 13 of 13. Same paths, same smoothing, same video
— a paused rep's bottom is flat, so the lowest SAMPLE is chosen by noise and
lands anywhere inside a second-long dwell. `v_min` is a round number in the
middle of a 0.02–0.12 plateau, not a tuned constant.
*Evidence:* `analysis/64`–`66`, TASKS.md H13, `tests/test_display.py`.

### Two classes of lift: IMPACT and SMOOTH (owner, 2026-08-07)

The owner's framing. **Deadlift is an IMPACT lift — the bar is dropped to the
floor between reps. Bench and squat are SMOOTH.** Both classes run the same
nine steps; impact lifts need supplementary ones. The class split is sound and
is evidenced throughout this section; **what changed is the STATISTIC that used
to be quoted for it, and the correction is below rather than a deletion.**

**THE GROWTH STATISTIC NO LONGER SEPARATES THE CLASSES IN THE SHIPPING
PIPELINE, BECAUSE STEP 5b FIXES WHAT IT MEASURED (H18, 2026-08-17).** This
section used to open "the measurement behind it is the sharpest lift-level
split in the project" and give per-rep fore-aft excursion growth, as a
percentage of the set mean, IMU only, no video:

    class                 n    median growth   range              (2026-08-07)
    deadlift (impact)     6      +29.2 %/rep   +4.4 to +65.2, 6 of 6 POSITIVE
    bench (smooth)       11       +0.3 %/rep   -25.9 to +12.0
    squat (smooth)        9       +1.9 %/rep   -10.5 to +22.8

**That measurement was RIGHT, and the deadlift half of it reproduces exactly.**
Re-run on the 29-capture corpus with `drift_tilt=False`, i.e. the pipeline as it
stood when the table was taken, the deadlift compounding is still there and is
still universal — and turning step 5b back on is what removes it:

    lift        5b OFF                          5b ON (ships)
    deadlift    +21.5 %/rep,  8 of 8 POSITIVE   +6.6 %/rep, 6 of 8
    bench        +4.6 %/rep,  6 of 8            +5.7 %/rep, 7 of 8
    squat       +12.2 %/rep,  5 of 7            -2.1 %/rep, 3 of 7

Both columns are today's 29-capture corpus. The OFF column is not the 2026-08-07
measurement re-read — it is the same statistic on different captures with the
intervening change reverted, which is why the deadlift row agreeing in SHAPE
(universally positive, same order of magnitude) is the result and the 21.5
against 29.2 is not a discrepancy to explain.

So the split's collapse is **step 5b `fit_drift_tilt` (H8) doing its job**, not
the original finding being noise. `deadlift_160x6_1` is the flagship example and
it makes the point on its own: this file recorded it running **8, 10, 13, 14,
19, 35 cm** across its six reps while the video stayed flat, and it now runs
**7.2, 7.0, 7.1, 5.2, 7.5, 6.7 cm**. The compounding is gone, not damped.

The rest of the original observation went with it and is kept for the trail: the
accumulation *reset between sets*, every deadlift starting with a small rep-0
excursion, so whatever built up was re-anchored at the opening hold. That was
true of the OFF state and there is now nothing accumulating for it to describe.

**Read that with the circularity stated, because it is close to tautological.**
5b fits a world-horizontal attitude drift rate **against the set's own
rep-to-rep dispersion**, and this statistic IS a rep-to-rep dispersion measure.
5b reducing it is very nearly what 5b is defined to do, so **the table above is
not independent evidence that 5b removed a real error.** What is: 5b is
self-limiting, finding on this corpus a median |beta| of **0.029 °/s on
deadlift against 0.006 on both bench and squat** (`correct.fit_drift_tilt`
returns rad/s; H8 recorded 0.008-0.051 against 0.001-0.008), and H8 scored it
against the video, where 5b ALONE took the deadlift median horizontal
4.97 -> 3.78 cm. *(The 4.97 -> 2.26 quoted in `pipeline.run`'s docstring is 5b
AND H9's axis together — do not attribute it to 5b.)*

**One half does NOT reproduce, and it is the smooth half.** "Scatters around
zero on smooth ones" is a property of the corpus that measured it, not of the
lift class: with 5b OFF, squat sits at **+12.2 %/rep, 5 of 7 positive** on this
corpus, nothing like the +1.9 recorded above. Part of that is corpus turnover —
the original spanned v1, which F1 deleted — so the bench and squat rows cannot
be re-derived and cannot referee anything.

**Two agents found the collapse independently before its cause was known, and
neither could see it from where they stood.** H1 measured deadlift 1.2-35.0
%/rep against bench+squat 1.3-22.8, "overlapping completely", while looking for
a gate to separate R4 and V3 (`analysis/H1_STATE.md`, TASKS.md). H17 measured
+6.6 / +5.7 / -2.1 while scoring the whole corpus. Both were right that the
statistic no longer separates; **neither tried it with 5b off**, which is the
one experiment that distinguishes "the finding was wrong" from "the pipeline
fixed it". Prefer that experiment whenever a statistic quietly stops working.

**And the split it was quoted for is now carried by a better number.** H17's
`beats_null` across all 29 captures is a sharper lift-level split than this ever
was, it is scored against the video rather than against the set's own
self-consistency, and no correction in the pipeline is fitted to it: **bench
beats the flat-line null on 6 of 7, squat on 9 of 10, deadlift on 1 of 10** —
and that one is a single, so every multi-rep deadlift loses. Quote that.
*Evidence:* `analysis/68`, TASKS.md H17 and H18.

**Steps shared by both classes:** 0 `io`, 1 `calibrate`, 2 attitude, 3
`to_world`, 4 `integrate`, 5b `fit_drift_tilt`, 8 `project`, 9 `plot`. These are
algebra or bookkeeping and carry no lift assumption. *5b and 8 are shared by
CONSTRUCTION rather than by accident — 5b is self-limiting where nothing drifts
and 8 is geometric — but both were built from deadlift evidence, and 5b's
premise (that a set's reps should agree) is the one to re-examine first if a
smooth lift ever regresses.* Note step 4 is not where impact damage
happens — its INPUT is corrupted, which is a different thing and decides where
you intervene.

**Step 5 `segment` is already split, and the polarity is the opposite of what
you would guess.** Deadlift segments on `impact_anchors`, from raw acceleration
alone, matching video to 13.5 ms with phase verified; smooth lifts segment on
integrated velocity and **squat's phase is still unverified** for want of any
external anchor. The impact is a liability for reconstruction and simultaneously
the best-instrumented moment in the project.

**Steps shared but whose premise breaks on impact:**

- **6 `apply_offset`** assumes `d` is rigid in body coordinates. During strap
  ringing the watch is not rigidly indexed to the wrist, and `|d/dt(R.d)|` peaks
  at the impact at 7.8x the rep median with ~90% of the angular motion being
  oscillation rather than reorientation. The premise fails exactly where the
  term is largest, on impact lifts only.
- **7 `detrend`** is the real fault line. On smooth lifts it is nearly adequate —
  B3's oracle puts the best per-rep quadratic at **0.25-0.55 cm on bench, inside
  spec**. On impact lifts **no per-rep line beats the flat-line null on any
  deadlift**, whoever estimates it. Same code, opposite verdict.

**Supplementary steps for impact lifts, ranked by what is measured:**

1. **Rest-to-rest detrend windows (C29).** Move step 7's boundaries off the
   impacts so the impact falls INSIDE a window as a kink rather than at its edge
   as a slope. 10.66 -> 3.93 cm, `beats_null` 0.21 -> 0.69. Deadlift-only by
   construction: smooth lifts have no raw-signal rest anchor and cannot be given
   one.
2. **Per-rep parabola detrend (D1).** All six deadlifts improve and excursion
   lands within ~1 cm of the video on the three marker-refereed ones. Must be
   gated to impact lifts — it costs four of six benches. See `oracle.parabola_detrend`
   for the argument that it may be removing fiction rather than recovering truth.
3. **Not these**, all measured and rejected: constant-bias estimation (C28),
   velocity splice (B6), quadratic detrend (C19), impact position anchor (B7),
   constant-per-interval (C28b).

**The wrinkle, recorded rather than smoothed:** the three paused squats show
+11.5 to +22.8 %/rep, the highest of any smooth capture. n=3, so possibly noise —
but a pause is not an impact, and if it survives more data the discriminator is
not impact per se.

*Re-measured 2026-08-17 (H18), and it reproduces before 5b and is removed by
it.* The same three paused squats give **+9.7, +12.2 and +19.8 %/rep with
`drift_tilt=False`** — inside the range recorded above, on the same captures —
and **-2.1, -3.8 and +3.8 with 5b on**. So the wrinkle was real rather than
noise, and step 5b treats a paused squat's accumulation the same way it treats a
deadlift's. That is mild evidence AGAINST "impact per se" being the
discriminator and for it being anything that lets a set drift between reps, a
pause included. Still n=3, and still not a reason to change any gate.

### The tracking protocol (C31, 2026-08-07)

**The moment a video is supplied: track it, cache the path to CSV beside the
capture, and render a review figure. Then LOOK at the figure.** `src/tracked.py`,
`python run.py --track`. Figures land in `analysis/tracking/v2` — **the "v2"
names the CORPUS `data_v2/`, not a tracker, and this sentence used to say
otherwise** (corrected 2026-08-19, H21). It read that figures land in
`analysis/tracking/v1` "the plate template's corpus" and `analysis/tracking/v2`
"the markers' corpus", split because the two are scored by different referees.
Both halves have since gone: v1 and its tracker were deleted on 2026-08-14 and
`analysis/tracking/v2/` has held `vtrack`'s figures ever since, under a caption
naming the referee it replaced. The directory was NOT renamed — it is keyed by
dataset, `tracked.DATASET_DIR` says so, and renaming to fix a caption would
break every path recorded in `TASKS.md` and on the board.
`analysis/tracking/v2_rebuild/` is a different thing: F1's dated report on the
rebuild with its own frozen copy of the tracker code, not an output directory
anything writes to. The CSVs are committed, so a clip is tracked once for
the life of the repo rather than once per analysis — `metrics.resolve_path`
reads the cache and a scored comparison went from minutes to milliseconds.

The second half is the half that mattered. **Six squat clips had been feeding
travel figures of 0.2 to 24.7 cm — for 65-70 cm squats — into comparisons behind
coverage of 96-100% and healthy residuals**, because the tracker had locked onto
gym furniture (D2). Every summary statistic said fine. `tracked.review` flags
`implausible` when whole-clip travel falls below the lift's own
`VERTICAL_ROM_M`, which is the one statistic that catches it, and the figure
shows a path no human would mistake for a barbell.

Two costs of reading the cache, both real: the CSV carries per-frame arrays and
scalars but **not** the tracker's own diagnostics, and **a cached read does not
run `vtrack.validate`, so its per-capture warnings do not fire** — notably the
`implausible` flag, which is the one statistic that catches a rigid, well-covered
track that is not the bar. Use `resolve_path(use_cache=False)` or
`run.py --track --force` when you want the tracker to speak up, and after ANY
change under `src/vtrack/` or to `capture.py`, because a cached path is only
valid for the tracker code that produced it. *(This named `markers.validate`,
`markers.py` and `truth.py` until 2026-08-19; both of those modules have been
deleted and `src/vtrack/` is the only tracker left — H21.)*

**AND `run.py --track --force` DID NOT DO THAT UNTIL 2026-08-17 (H14).**
`tracked.ensure(force=True)` skipped its own `read` and then called
`metrics.resolve_path(video)` with `use_cache` defaulted TRUE, so it rewrote
each cache from itself with a fresh commit stamp and re-tracked nothing. The
instruction in the paragraph above has therefore been a no-op for the whole life
of the cache, and any change to a tracker made since C31 was scored on paths
produced by the code that preceded it. Fixed by passing `use_cache=not force`;
found because H14's scale change came back bit-identical on all sixteen clips.
**If you are re-reading an old result that depended on a re-track, check the
date.**

**THE VIDEO REFEREE'S ABSOLUTE SCALE CHANGED ON 2026-08-17 (H14), AND EVERY
METRE FIGURE MEASURED AGAINST VIDEO IN THIS FILE, IN `TASKS.md` AND IN
`analysis/README.md` PREDATES IT.** The owner tape-measured the sticker
geometry: a sticker is 2.0 cm across overall and is placed with its outer edge
against the plate rim, so its centre sits 1.0 cm inboard and **the sticker
circle is the plate diameter less 2.0 cm**. That replaces
`STICKER_RATIO = 0.858`, which was calibrated on the old three-sticker plate
(31.6 mm inset) and which no capture in the live corpus was stickered by. Two
entries of `vtrack.PLATE_M` were wrong with it — bench at 0.45 for a 425 notched
plate, deadlift at 0.445, the bumper rather than the stickered plate. Net:
**+4.9% bench, +6.1% deadlift, +11.4% squat.**

What it moved, on all sixteen captures, verified as a pure rescale with **0 of
16 seeds changed**: the **VERTICAL error against the video falls from a median
3.92 to 2.71 cm, better on 14 of 16** — a third of it was the ruler. The
horizontal does not move (2.17 -> 2.26 cm, `beats_null` 1.25 -> 1.26), which is
P3 restated: a scale error is not what the horizontal is made of. The
corroboration is independent of the tape — the video read BELOW the IMU's per-rep
ROM on **16 of 16** captures beforehand, median 0.93 on every lift, and C27 had
measured the deadlift third of that gap at 4.6-9.3% from the other side, which
brackets the tape's +6.07%. Afterwards the three medians are 0.971 / 1.029 /
0.993. **Read the residual honestly:** a common bias is removed and a wider
between-lift spread is left (0.012 -> 0.058). *Evidence:* `analysis/67`,
TASKS.md H14, `vtrack.STICKER_CIRCLE_M`.

**STEP 6 IS ON BY DEFAULT (C31, 70b2a63, 2026-08-06), AND THAT INVALIDATES
EVERY HORIZONTAL AND VERTICAL NUMBER RECORDED IN THIS FILE, IN `TASKS.md` AND
IN `analysis/README.md`.** `pipeline.run(wrist_offset=)` defaults to `"auto"`,
which looks `d` up by lift from `correct.WRIST_OFFSET_M` — the owner's tape,
below — and applies it. Everything written here before that date was measured
with step 6 OFF, i.e. against the reconstructed *watch* path. **To reproduce an
old number you must pass `wrist_offset=None`, or you are comparing two
different quantities.** Where a post-`d` figure exists it is recorded beside
the old one; where it does not, this file says so rather than implying the old
one still holds. Do not assume a number survived the change because nobody
crossed it out.

*Why it is on, and the reason is not the metric (owner's call).* This project
reconstructs the **bar** path and the sensor is on the **wrist**; `R(t)·d` is
the only term between the two. Omitting a measured geometric term does not
produce a more cautious answer, it produces an answer to a different question.
The metric was ambivalent — see the mixed table in P2 — and the geometry is not.

**`d` is measured, and B2 is superseded as to availability but NOT as to
fitting.** The owner tape-measured it on 2026-08-06, watch-face centre to bar
centre in watch body axes:

    squat            5 cm toward the crown, 4 cm UP OUT of the case    |d| = 6.4 cm
    bench, deadlift  9 cm toward the crown, 3 cm DOWN INTO the case    |d| = 9.5 cm

`apply_offset` computes `p_bar = p_watch − R(t)·d`, so **its `d` points
BAR→WATCH and is the negative of what the tape reads from the watch**; a sign
error here is invisible, since it produces a plausible curve of the right size
pointing the wrong way. The constant's docstring carries the derivation.

It was corroborated, not fitted. Sweeping `d`'s direction over a 300-point
sphere grid (neighbours ~12°) at the measured magnitude and scoring by C30's
acceleration correlation, the tape value sits within **0.02–0.03** of the best
achievable value on all three `data_v2` deadlifts — within ONE grid cell,
identically on all three. On bench the optimum is 50–64° away but worth only
0.02–0.06 on a baseline already at 0.81–0.94, so **bench does not identify
`d`'s direction at all**; the tape is corroborated on deadlift and merely not
contradicted on bench. B2 stands: `d` still cannot be FITTED from video, and
anyone tempted to refine it on bench should read B2 first. *Evidence:*
`correct.WRIST_OFFSET_M`, TASKS.md C31, `analysis/48`.

`metrics.py` is not one of the steps. It judges them: `dispersion` for
rep-to-rep spread, `vs_truth` for absolute error against the video. Read its
module docstring before quoting a number from it — `dispersion` needs no truth
and is blind to exactly the error that dominates, so the two are not
interchangeable.

**THERE IS ONE VIDEO REFEREE AS OF 2026-08-19 (H21): `src/vtrack/`.** This
project has had three, and the other two are deleted — the plate template with
the v1 corpus on 2026-08-14 (F1), and `markers.py` on 2026-08-19.
`metrics.TRACKERS` is `("vtrack",)`, `resolve_path(tracker="markers")` raises,
`metrics.infer_tracker` returns `"vtrack"` for `data_v2/` and raises for
anything else, and there is no second tracking path in the repo that can be run
— the last one was `run.py --dlconic`, which called `markers.bar_path` directly
and went with the module.

**The consolidation moved NO number and was gated on it.** Every one of the 31
captures in `data_v2/raw/` was scored before and after — the tracked path itself
(per-frame arrays hashed), `_video_quality`, `vs_truth`, `shortset.run`, the
segmenter's windows — and every one is bit-identical. That is what a correct
consolidation had to look like, since `infer_tracker` had already returned
`"vtrack"` for the whole corpus since 2026-08-14; anything that moved would have
meant something was still reaching the old referee. `markers.py`'s one live
dependency, `top_of_travel_residual` and `MAX_TOP_RESIDUAL_CM`, moved into
`vtrack.path` unchanged (with `capture.TOP_FRAC`), and its gates moved to
`tests/test_vtrack.py`. Recover the module with `git show 0e87f28:src/markers.py`.
**Everything recorded under it below stands as history and none of it can be
re-run.**

*The paragraph this replaces, true from 2026-08-14 to 2026-08-19:* **THERE ARE
NOW THREE VIDEO REFEREES, AND `data_v2/` CHANGED HANDS ON 2026-08-14 (F1).**
`src/vtrack/` replaces `markers.py` as the referee for `data_v2/`;
`metrics.infer_tracker` returns `"vtrack"` there. `markers.py` is **not deleted,
not edited, and still reachable** by passing `tracker="markers"`.

Why it changed hands: `markers.py` was not good enough on that footage. Six of
eleven squat clips were unusable, `squat_170x1` and `squat_pause_140x4_3`
reporting **14.0 and 24.7 cm of whole-clip travel for 60-70 cm squats** behind
coverage of 96-100% and healthy residuals (C31, D2). `vtrack` tracks **16 of 16
clips** at 0.97-1.00 coverage with eight filled lattice slots median on every
one, and **16 of 16 rep counts match the label**.

**The strongest evidence for it is a replication rather than a self-report.**
Per-rep video fore-aft comes out **4.4-6.0 cm on all six deadlifts** against
C27's independently measured 4.3-6.2 — and three of those six are 2026-08-08
captures C27 never saw.

**What it did NOT do, recorded so nobody infers it:** re-refereeing did not
rescue deadlift's horizontal, which stays at `beats_null` 0.14-0.38 against the
0.14-0.35 recorded here. It moved **one** of P2's two dissenting paused benches
— `bench_spoto_95x5_2` 0.72 -> 1.52, crossing the null — while
`bench_spoto_95x5_1` reproduced the old referee to 0.01 (0.88 -> 0.89) and still
loses. So half of P2's referee-versus-pause tension was a referee artefact and
half is real, which names `bench_spoto_95x5_1` as the capture to explain.
*Evidence:* `analysis/tracking/v2_rebuild/REPORT.md`, `src/vtrack/path.py`.

*The paragraph below is kept as written and describes the arrangement before
2026-08-14.*

There were **two video referees**, and which one applies is decided by the
footage, not by preference. `truth.py` tracks the plate as a dark disc and is
the referee for everything in `data/video/`. `markers.py` (C15, 2026-08-01)
tracks retroreflective stickers and was the referee for `data_v2/`, which is
filmed from a tripod with markers on the plate. **The four bench captures of
2026-08-03 are refereed by `markers.py` as of C23, and the three 8-sticker
deadlifts of 2026-08-04 as of C27**; everything else is scored by `truth.py`,
because `data/video/` has no markers. The deadlifts are the first captures
refereed by the CONIC path, and the first marker footage of a lift other than
bench. See the C21/C23 note below.
*(That whole paragraph describes the arrangement of 2026-08-01 to 2026-08-14.
`markers.py` was deleted on 2026-08-19 and `truth.py` on 2026-08-14; a "future
capture" is judged by `src/vtrack/`.)*
`markers.py` is what a future capture should be judged by: on the same five
clips it tracks 100% of frames where the plate template loses the bar at every
lockout and reports 0.2 cm of travel on one bench set. See `src/README.md` and
`analysis/35`–`37`. It is not immune to what breaks `truth.py`, only better
behaved: its fit residual also degrades with height, 0.16 to 0.81 px, but stays
inside tolerance instead of crossing it — worst case 0.33 cm against the 1 cm
spec, measured by `markers.top_of_travel_residual` and gated per capture (C17).

**THE CAMERA GEOMETRY, and it is a confound in every bench and squat number
here (owner, 2026-08-06; recorded by C31 in bc66fb1).** Nothing in this repo
had written it down: **squat and bench are filmed from the lifter's RIGHT,
deadlift from the LEFT, and the watch is on the LEFT wrist.**

So **on bench and squat the referee tracks the plate on the OPPOSITE END OF THE
BAR from the sensor.** Bar tilt or an uneven press moves the right plate and
the left wrist differently, and that difference is scored as pipeline error.
**Deadlift is the only lift in the corpus where camera and watch are on the
same side** — so on top of its landmark-matched sync (9–19 ms) it is also the
only geometrically clean comparison available.

What it does *not* do, checked rather than assumed: it cannot touch `d`, which
lives in the watch body frame, and it cannot corrupt the fore-aft sign, because
`vs_truth` picks one sign per set from the correlation and reports
`reps_disagreeing_on_sign`. Untested and testable: a bar tilting through a
press should show up as a bench-only, load-dependent residual that no
wrist-frame correction can reach.

**The scoring path takes either referee as of C17 (2026-08-02).**
`metrics.resolve_path` picks the tracker from where the clip lives — anything
under `data_v2/` is marker footage — or takes an explicit `tracker=`, or takes
an already-tracked path dict. `vs_truth` and `momentum_closure` both accept it.
`pipeline.find_video` pairs a capture within its own dataset, so a `data_v2/raw`
CSV never reaches across to `data/video`.

**C17 said "the day a marker capture arrives with an IMU log beside it there is
nothing to build." Six arrived on 2026-08-03 and that was wrong (C21).** The
plumbing was indeed ready; the tracker was not. It failed to seed on all six —
`bench_95x2` reported 0.4 cm of travel against a 29.5 cm rep.

**C23 fixed the four benches (2026-08-03), and they are the first captures this
project has ever had refereed by markers.** They track at 98-100% three-marker
coverage and 0.13-0.38 px median residual. `seed_frame` now decides by
VERIFICATION — trial-track a shortlist, keep what actually follows the bar —
with per-frame appearance demoted to a filter.

C23 reported that video and IMU now agreed — whole-clip marker travel against
the IMU's per-rep ROM at **-1.6%, -1.8%, -1.6% and -6.1%** — and called it the
first independent confirmation of anything here. **C24 retracts that (2026-08-03).
The two quantities are not the same quantity.** Whole-clip travel spans the
un-rack, where the bar is held ~3 cm above lockout, so it is a per-*clip* range
being compared against a per-*rep* one, and the ~3 cm it adds is about the size
of the disagreement it was hiding. Measured per rep, with the video finding its
own reps by peak detection — no IMU, no sync, so it can referee both sides —
the video says **23.3-26.7 cm** across all 14 reps where the reconstruction says
**28.4-30.7**. The instruments disagree by **~20% on every rep of all four
captures**, not by 1.6%.

**Do not read that as the IMU reading high; C24 cannot assign it, and says so.**
`markers.calibration_report` declares a spacing bias of **7.3-11.2 cm** on these
same four clips — the rim centroid sits 63-94 px off the detected plate centre
and the plate turns 32-33° over the clip — which is larger than the ~5 cm being
argued over. The marker path is not currently clean enough to convict the
reconstruction. What is settled is that the agreement was an artefact of the
comparison. *Evidence:* `analysis/41`, `python run.py --v2rom`.

The scale bug C23 found is untouched by this and still stands, and the WRONG
SIGN is still what exposed it — travel read 9-13% low when the clip contains an
un-rack and should read high. `truth.plate_diameter` keys on the lift and
returned the notched plates' 425 mm for a session shot on 450 mm blue calibrated
discs. `truth.CALIBRATED_SESSIONS` now carries the exception.

**All four are now scored by `metrics.vs_truth`, where only `bench_95x2` had
been (C24).** Horizontal rms, against the marker referee:

    capture           h rms   null   beats_null   sign
    bench_95x2        1.46    4.33      2.96      0/2
    bench_92.5x4_1    3.08    2.20      0.71      0/4
    bench_92.5x4_2    1.12    2.74      2.44      0/4
    bench_92.5x4_3    1.39    2.29      1.65      0/4

*The bottom two rows are C25's, 2026-08-03. C24 measured them through a broken
sync and said so; at 1.86/2.89/1.55 and 1.66/2.42/1.46 they were scored against
the wrong reps. Nothing else in the table moved, which is the check that the
correction touched only what was broken.*

`bench_92.5x4_1` is the one that **loses to the flat-line null**, and it is also
the capture whose travel dissents at -6.1% where the other three agree to under
two percent. Two independent metrics now finger the same capture; neither is
explained. C25 sharpens this rather than settling it — the other three now beat
the null by 1.65-2.96, so `_1` is alone on both counts instead of one of two.

**Two of the four WERE synced a full rep out, and C25 fixed it (2026-08-03).**
On `bench_92.5x4_2` and `_3` the IMU's window 0 held no video chest touch at
all, while the video's last rep fell outside every window. All 14 windows now
hold exactly one touch.

**C24 correctly localised this to the sync and then misattributed it, and the
misattribution is the part to learn from.** It read as the whole-rep ambiguity
`metrics.bench_sync`'s docstring says it cannot resolve — peak and sidelobe of
comparable height, a periodic set looking the same shifted by one rep. It was
not. The true correlation peaks sit at **-6.37 s and -7.08 s, outside the
+/-5.0 s `max_lag_s` the sweep searched**, so the sweep returned the best point
it could see and that point happened to be one rep period late. Given the whole
curve the true peaks win by **50% and 76%** (0.66 vs 0.44, 0.67 vs 0.38), so
this was never the inherent ambiguity — it was a truncated search, and it was
fixable.

**And the replacement is a starting point rather than a bound, because a
constant would only have moved the cliff (C25 part 2).** `SYNC_MAX_LAG_S` is
11.75 s, the middle of a 10.00-13.50 s plateau measured over all eleven bench
captures and the three deadlift controls — but the sweep now WIDENS from there
until the peak has a full rep period of curve beyond it, capped by how far the
two records can slide and still share signal. That cap is a property of the
recordings rather than a tuned number.

The owner asked what happens to a capture whose lag is bigger still, and the
answer was measured rather than argued: shift each bench video's clock by
0-30 s and ask for the offset back, 121 trials.

    variant                              ok   refused   SILENTLY WRONG
    fixed 11.75 s                        39      70          12
    widen until the peak is interior     71      32          18
    ...plus the stability check          71      35          15
    ...plus a 3-rep overlap floor        72      34          15

So a fixed window does **not** merely refuse a bigger lag — twelve of those
come back silently wrong — and the usable headroom was ~9 s rather than 11.75,
`bench_92.5x4_3` refusing at a 2 s shift because its true lag of -7.08 leaves
only 2 s of margin. Naive widening then buys correctness with silent errors,
which is the wrong direction, so two guards pay it back: a peak found only by
widening must survive one MORE widening, and a lag is scored only where the
records share three rep periods.

**Seven of the residual fifteen are `bench_92.5x2` alone.** Excluding it, fixed
and adaptive both leave eight while correct answers roughly double — so what is
left is a capture whose lag is not identifiable, not a search that is too
narrow. It is a two-rep set, and it is the same capture whose true peak loses
to a coincidence 13.6 s away. Not fixed, and not fixable by widening.

Every capture's unshifted answer is bit-identical, which is what licensed
shipping this: an interior peak is accepted exactly as a single fixed sweep
would accept it, and none of the eleven takes the new path.
*Evidence:* `metrics.bench_sync`, `tests/test_video_truth.py`.

Touch minus window-centre, per rep, corrected:

    bench_95x2       +0.47 +0.57                 mean +0.52 s   (period 4.75)
    bench_92.5x4_1   +0.25 +0.09 +0.41 +0.19     mean +0.24 s   (period 2.83)
    bench_92.5x4_2   +0.47 +0.12 +0.11 +0.32     mean +0.26 s   (period 2.63)
    bench_92.5x4_3   +0.23 +0.32 +0.17 +0.53     mean +0.31 s   (period 2.68)

The bad two read +2.97 and +3.35 before — 1.10 and 1.14 rep periods out — and
now sit with the other two at +0.24 to +0.52 s. That is not an error either:
C9 measured the chest touch at 0.567-0.648 through a window rather than 0.5, so
a small positive offset is what a correctly synced bench gives, and all four
captures now agree with C9 and with each other. Per-rep, the 14 touches fall at
**0.53-0.69 through their windows**, on a different dataset and a different
tracker from C9's.

**Counting was never in question here and still is not.** 14 of 14, and the
segmenter's own candidate list holds exactly four rep-sized concentric lobes on
each capture — it chose all four and there was no fifth to drop.

**What this cost, and why the figure could not settle it.** A whole-rep sync
error and a whole-rep segmentation error produce an *identical* table of
touch-minus-window offsets, so `analysis/41` showed a real defect in the right
place while being unable to say which stage owned it; C24 read it as the sync's
inherent ambiguity and the owner read the same panel as the segmenter dropping
the last rep. Only an anchor outside the periodicity separates them. **The
lesson generalises past this bug:** `bench_sync`'s "a whole-rep ambiguity is
harmless" was established for horizontal rms and for window phase, both
invariant to it. Anything that PAIRS a video rep with an IMU window is not —
`analysis/41`'s window bars read 2.4 and 1.4 cm of a ~25 cm rep, having landed
on the un-rack. Check a new rep-indexed quantity against a whole-rep shift
before assuming it inherits that invariance.

**The squats could not be fixed and were deleted, and the blocker was the plate
rather than the code:** its three stickers sit at 94.9/111.4/153.7 degrees,
which `_triangle_ok` rejects outright, and whose centroid falls 18.4% of the
radius (~2.8 cm) from the true plate centre against a 1 cm spec. Bench's plate
is 129/102/129, i.e. 8.6%, which is the whole difference between the two lifts.
C23 concluded: sticker the next squat plate at 120 degrees, a tape measure
rather than code.

**C26 supersedes that advice (2026-08-04), and the replacement is easier rather
than harder.** Put **eight** stickers on, at whatever angles are convenient, all
at the same distance from the rim. A circle projects to a conic and five points
determine a conic wherever they sit, so `markers.fit_ellipse` never asks how the
stickers are spaced. The 8.6% and 18.4% centroid offsets that decided which of
the two lifts could be refereed lose their spacing term entirely: synthetically
the centroid is out 7.4 px on bench's spacing and 13.6 on squat's, where the
conic is out 1.7 px on **both**. What replaces the even-spacing requirement is a
common RADIUS, which a tape gives you directly.
It also fixes a second and larger term the three-sticker layout could not:
`track`'s similarity fit reads foreshortening as distance, costing the scale
11.2% at 40 degrees of tilt, where a conic's semi-major axis holds to 0.09%.

Do not read that as a perspective fix — on ideal spacing the old centroid is the
better centre estimator, 0.86 px against 1.72 at 20 degrees of tilt. The conic
removes SPACING and TILT-SCALE, not perspective. See TASKS.md C26 and
`src/README.md`.

**C26 shipped ungated and C27 gated it on 2026-08-04, on three 8-sticker
deadlifts. Four defects surfaced, and the shape of them is the lesson.** The
conic MATHS was right; everything around it that still assumed three markers was
not. `_reacquire` returns a triangle and `_best_correspondence` fitted it against
the model, so the tracker crashed — and could never have worked anyway, because
`_reacquire` gates on `_triangle_ok(tol=0.22)` and eight evenly spaced stickers
have no admissible triple. **The 0.255-against-0.25 that motivated C26 recurs one
function further down**, because C26 fixed the seeder and did not grep for the
other consumers of triangle geometry. `layout="auto"` never reached the conic at
all, falling through only on an EMPTY triangle list while `candidates` returned
clutter triples, so `vs_truth` silently scored these captures on a three-marker
model riding two markers for 37% of frames. And the detector fires more than
once per sticker — 9 and 10 model slots for 8 stickers, extras 0.07-0.26 px
apart — which double-weights a sticker in an unweighted least-squares fit;
deduplicating moved whole-clip travel 76.2 to 57.5 cm and 95.6 to 55.2.

**The stickered plate is not the widest plate, and on a deadlift it is not.**
`truth.plate_diameter` answers "what outline does the template tracker see" —
the 445 mm bumper — and `markers.py` needs the disc the stickers are ON, a
425 mm notched plate loaded outboard (owner, 2026-08-04). Worth 4.7% of every
marker distance. `truth.sticker_plate_diameter` splits the two. The bar still
starts 22.25 cm up; that is set by the bumper, which carries the load.

What C21 established, and the second point is the one that saves the next
agent's time. Three admission gates in `candidates` each rejected the true
constellation, and **all three were already at zero margin on the footage they
were tuned against** — the third sticker ranks 48th against a `max_dets` of 30
(old footage: 24th), the end-cap sticker sits at 0.55 of the circumradius
against a 0.45 gate (old: 0.41), and the triple ranks 9th in its own frame
against a `top` of 5 (old: 3rd). C21 fixed those three and they were necessary
but **not sufficient**.

**And `track` is not implicated at all.** Handed the correct constellation by
hand, it follows `bench_95x2` through the whole clip at 100% coverage and a
0.11 px median residual — better than on any capture it was originally tuned
against. The entire remaining failure is `seed_frame` picking the wrong
hypothesis, and the specific open defect is that groups are pooled by
circumradius alone, so the true constellation is absorbed into a size bucket
with spurious ones and the representative is then reselected by appearance
score. Gated by `tests/test_markers.py`; see `analysis/39` and TASKS.md C21.
*(That test file was deleted with the module on 2026-08-19 — H21. Its algebraic
gates, on a tracker nothing can run, were unit tests for dead code; the two that
gate a LIVE function, `top_of_travel_residual`, moved to `tests/test_vtrack.py`
with it. `git show 0e87f28:tests/test_markers.py`.)*

Two things that made this small, and one that is still unmeasured. The path
dicts were already compatible — `markers.bar_path` returns a superset of
`truth.bar_path`'s keys — and `truth.landings`, `truth.sync`, `truth.to_imu_time`
and `bench_sync` read only `t` and `height`, so the whole sync apparatus was
tracker-agnostic before anyone tried. What is **not** checked: whether a landing
found on marker footage falls at the same instant as one on template footage.

**C27 unblocked this on 2026-08-04 and it is now simply UNDONE rather than
unrunnable.** The three 8-sticker deadlifts are marker-filmed deadlifts with a
watch on — exactly the capture this asked for — and their landings sync at
19.2 / 16.0 / 9.3 ms. What has not been done is the comparison itself: whether a
landing found on marker footage falls at the same instant as one found on
template footage, against the deadlift sync's 13.5 ms. Nothing blocks it now.

*The paragraph below is C24's and is kept because its reasoning is still the
record of why this waited.*

**That check WAS blocked, then unrunnable, which was worse (C24).**
This used to say the six paired captures of 2026-08-03 were the first that could
test it, against the deadlift sync's 13.5 ms, and that the seeding defect was in
the way. C23 cleared the seeding defect and deleted the two squats, so **four
remain and all four are bench, which has no floor landing to find.** Nothing in
the corpus can run this comparison. It needs a marker-filmed *deadlift* with a
watch on — which is one more reason for the capture-protocol item that already
asks for markers on a lift other than bench.

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
- **`data/` NO LONGER EXISTS.** The v1 corpus — `data/raw/`, `data/video/` and
  `data/synthetic/` — was deleted on 2026-08-14 on the owner's instruction,
  together with `truth.py`'s plate-template tracker. `data/raw/` was gitignored,
  so those 17 labelled captures and 4 diagnostic logs are **unrecoverable**; the
  10 tracked `.mov` files remain in git history, which was NOT rewritten.
  The immutability rule this bullet used to state — "`data/raw/` is immutable
  and gitignored, re-deriving from raw is trivial, re-collecting from a gym is
  not" — now applies to **`data_v2/raw/`**, and applies with more force, because
  it is the only corpus left.

## Working style

- Use plan mode for anything changing the pipeline's shape, or changing an
  assumption about the error model rather than the code implementing it.
- **Stay on the task you were given.** Work one open problem at a time and name
  it at the start; a change not attached to that problem does not belong in the
  diff, however obviously right it looks. This repo is unusually full of
  inviting tangents, and the cost of taking one is not the time — it is that the
  owner now has to review a change nobody asked for in order to get the one they
  did. Specifically:
  - Something broken that you find on the way gets **recorded, not fixed** — a
    line in `TASKS.md`, or say so in your reply. That is not the lesser outcome
    here; the record is what this project runs on.
  - Do not refactor, rename, re-tune or tidy code you merely had to read.
  - Finish the task before starting anything else, and finish it *completely*:
    the docs it falsifies are part of it, not a tangent from it. See the
    same-commit rule below.
  - If you think the task is the wrong thing to do, say so in a sentence or two
    and then do it anyway unless it is unsafe. Do not silently substitute your
    own better idea — an unrequested change is the one the owner cannot check.
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

**READ THIS BEFORE ANY PROBLEM BELOW — v1 WAS DELETED ON 2026-08-14 (F1).**
The owner had `data/raw/`, `data/video/`, `data/synthetic/`, `src/truth.py`'s
plate-template tracker and `analysis/tracking/v1/` removed. Three consequences,
and the third is the one that changes what you should do next.

**Every finding measured on the v1 corpus is now HISTORY, not a live gate.**
P2's C10 and C12 tables, P3's oracle work, P4's stationary-watch bias figures,
P6's momentum closure and B5/B6's impact measurements were all measured on
captures that no longer exist. They are kept below because what was believed and
why is the record this project runs on — but **none of them can be re-derived**,
and a number you cannot re-derive cannot be used to referee a change.

**`truth.py` is gone; `src/capture.py` holds what survived it** — `lift_of`, the
plate diameters, `VERTICAL_ROM_M`/`rom_flags`, `FORE_AFT_ACCEL_MAX`, the decode
helpers, `find_plate` as a rim detector only — **which has had no caller at all
since `markers.py` was deleted on 2026-08-19, along with `sticker_plate_diameter`
and `STICKER_PLATE_DIAMETER_M`; recorded as orphaned rather than removed, since
nothing can score with them** — and `landings`/`sync`/
`to_imu_time`, which are the deadlift clock match at 9-19 ms. `metrics.TRACKERS`
is `("vtrack",)` as of 2026-08-19 — it was `("markers", "vtrack")` when this was
written; the `"plate"` referee no longer exists and `infer_tracker` raises
outside `data_v2/` rather than falling back to it.

**AND THE SUITE HAD NOT BEEN RUNNING ON THE NEW CAPTURES.** Every gate in
`tests/test_real_data.py` and `tests/test_segmentation.py` globbed `data/raw`,
so the 2026-08-08 session had **never been segmented under test**. Repointing
them at `data_v2/raw` took the suite from 109 passing to 311 and immediately
exposed defects nobody had seen — see P1. This is the project's oldest failure
shape (an aggregate that passes while the thing fails) in its purest form: a
suite reporting success by not running.


The milestone table is gone. Milestones 1–6 all passed and the project does
not work; a schedule that reports success while the artefact fails is worse
than no schedule. What survived it is real: the watch logger works, and
`data/raw/` holds 17 captures, all labelled with rep counts and totalling 72
reps (7 bench, 7 squat, 3 deadlift), plus two stationary diagnostic logs. The
2026-07-30 session added seven of those and every one carries the C3 `phase`
column, including a real 3.0 s closing hold. The room and warm-up captures were
removed in `7004c32` because no video exists for them; measurements made
before that commit say 13 captures, and measurements between it and 2026-07-30
say 10 and 44 reps. Both are correct as of when they were taken.

**A second dataset opened on 2026-08-03 and has grown twice since**: `data_v2/raw/`
holds **thirteen captures (52 reps)**, each with a marker clip beside it in
`data_v2/video/` — the first IMU logs ever paired with marker footage, and the
first captures in this project refereed by `markers.py`:

    2026-08-03   four benches                     14 reps
    2026-08-04   three 8-sticker deadlifts        15 reps
    2026-08-06   two spoto benches, four squats   23 reps

*The 2026-08-06 six ran clean through the IMU pipeline and their per-rep
vertical ROM is inside `truth.VERTICAL_ROM_M` (C31). Two of the four paused
squats short-counted on arrival and C31a fixed it in the segmenter — see P1.*
The four benches carry the `phase` column with a
~3.0 s closing hold, count 14 of 14, sit inside `truth.VERTICAL_ROM_M`
(28.4–30.7 cm), and replicate C6's attitude bound independently (0.010–0.058°
opening, 0.062–0.146° closing, against 0.39–1.05° of gyro-only drift).

Read that 28.4–30.7 as passing a *bound*, not as agreeing with the video. The
marker footage puts the same 14 reps at 23.3–26.7 cm — also inside the band,
since bench's is 24–31 — so both instruments clear it while disagreeing with
each other by ~20%. That the band admits both is the band being wide, and it is
the clearest illustration available of what `VERTICAL_ROM_M` is for and what it
cannot do. See the C24 note under the two referees above, and `analysis/41`.

The session also produced two squats. **They were deleted on 2026-08-03** —
video and log, four gitignored files, unrecoverable — because that plate's
stickers are placed too unevenly to referee (C23). They had supplied a rep
count of 9 of 10 and squat's first replication of the attitude bound; both are
gone with them, and C22's fatigue finding is measured on data that no longer
exists. **THE CORPUS IS 31 LABELLED CAPTURES IN `data_v2/raw/` (2026-08-18).**
Two deadlifts arrived on 2026-08-18 — `deadlift_160x6_1_20260818` and
`deadlift_190x3_20260818` — both tracking cleanly (99.8% / 99.7% coverage, rep
counts matching their filenames) and both already cached in `data_v2/tracked/`.
**Nothing else in this file has been re-measured on 31**; every count and every
corpus-wide median below is the 29-capture figure, including H17's scorecard.
The one thing measured on all 31 is H19's deadlift work, and it found that
`deadlift_160x6_1_20260818` reconstructs at **14.91 cm horizontal — the worst in
the corpus — where the same lift, load and rep count on 2026-08-04 gives 1.97**.
A 7.6x session-to-session difference on a clean track, and the
sharpest restatement yet of H17's finding that the velocity channel repeats
across sessions while the horizontal position channel does not. See TASKS.md H19.

**IT IS NO LONGER UNEXPLAINED, AND THE OWNER SUPPLIED THE FACT THAT EXPLAINS IT
(H20, 2026-08-18).** He wore **lifting straps** for this capture, which put the
watch further up the forearm and let it move. No measurement in this repo could
have produced that, and it is the third time asking has beaten inferring from
frames — see the capture-protocol note about the physical rig.

**STRAPS ARE A PER-CAPTURE FACT, NOT A SESSION ONE (owner, correcting H20 the
same day).** `deadlift_160x6_1_20260818` is **the only strapped deadlift in the
corpus**. `deadlift_190x3_20260818` was shot the same day on the same rig
WITHOUT straps. H20 first read the two as a session effect and that was wrong —
and being wrong made the evidence weaker than it is, because the unstrapped
session-mate is a **within-day control** with everything but the straps held
fixed. Read every comparison below as strapped-versus-control, not day-versus-day.

**Read the mechanism carefully, because the owner's own phrasing contains two
hypotheses and only one of them survives.**

* **"Further up the wrist", as GEOMETRY — FALSIFIED, twice.** Lengthening `d`
  along the forearm buys `160x6_1` 6% at a physically absurd 15 cm of
  displacement and makes `190x3` *worse*, while the unstrapped `185x3_20260804`
  improves most of all — so the response to lever length is not session-specific.
  And the watch's roll about the arm, read off the GYRO with no video in it,
  puts `160x6_1_20260818` about **20 degrees** from the −3…+8 degree cluster
  every other well-conditioned capture sits in. Real, in the predicted
  direction, and worth `1 − cos 20° ≈ 6%`. Not 7.6x.
* **"Moving around more" — THIS IS THE ONE.** Per-rep horizontal spread,
  measured AXIS-FREE so no projection choice can flatter it: `160x6_1_20260818`
  sweeps **19.9–27.9 cm** where its own twin sweeps **5.4–7.7** and the video
  says the bar moved 4.4–6.0. **A rotation cannot manufacture that** — it
  redistributes signal between the two horizontal components and leaves the
  total spread alone — so the excess is real motion in the reconstruction. The
  watch experienced accelerations the bar never did.

So this is P6's strap-ringing mechanism — the watch not rigidly indexed to the
wrist — **escaping the floor impact and contaminating the whole set.** Step 6's
premise (`d` rigid in body coordinates) fails for the entire capture rather than
for 6% of the samples.

**Corroborated with no video in it at all.** The RAW pre-detrend double
integration runs away far faster on the strapped capture: per-rep horizontal
spread of the uncorrected path grows **831 → 2744 cm** across its six reps
against **150 → 579** on its own unstrapped twin, same lift, same load, same rep
count — and it is the highest of any deadlift at **every** rep index, including
rep 1. So the signature is present before the referee, before step 7 and before
any projection choice.

**Two qualifications, both load-bearing.** `deadlift_190x3_20260818` — the
unstrapped control — is itself elevated at 7.22 cm, and **straps do not explain
it**: it invents no travel (6.9–12.0 cm, ordinary) and its raw drift is ordinary
too. Part of it is that the bar really did move more, the video reading
8.7/10.2/4.9 cm of fore-aft against a corpus norm of 4.4–6.0, which lifts its
null; `beats_null` is 0.43. It is left open rather than attributed.

And **a video-fitted roll is DISCOUNTED by the control.** Sweeping `angle_deg`,
both 2026-08-18 captures minimise at ≈ −50 degrees, ~73 from the shipped
`BAR_ANGLE_DEG`. If that were a strap effect the unstrapped control would not
share it, and it does — so it is one parameter fitted against the answer, not a
measurement. The gyro says ~20 degrees and the gyro is the one to believe. Under
the fitted angle `190x3` would cross the null at 1.44 while `160x6_1` reaches
only 0.35, so **even the best possible axis does not rescue the strapped
capture**, which is itself evidence the axis is not its problem.

**What follows for the corpus, and it is a capture rule rather than a code
change.** `deadlift_160x6_1_20260818` should not referee anything, and nothing
in the repo currently marks it.

**THE OWNER'S CALL, 2026-08-19: NO STRAPS, from now on.** H20 recommended
*recording* straps per capture; the owner went further and removed them from the
protocol, which is the better answer — the effect is large, it is invisible in
both the IMU log and the video, and a recorded-but-present confound still has to
be excluded from every corpus median by hand. See TASKS.md, Capture protocol,
where it is now the first rule. **Whether to exclude the one strapped capture
from scoring IN CODE is NOT decided** — that changes what every corpus-wide
median means. Until it is, exclude it by hand and say so.
*Evidence:* `analysis/70`, TASKS.md H20.

*The 29-capture statement it replaces:* **THE CORPUS IS 29 LABELLED CAPTURES IN `data_v2/raw/` (2026-08-17).** Thirteen
arrived on 2026-08-17 — five from 2026-08-13, five from 2026-08-15 and three
squats from 2026-08-17 — taking it from 16. Eleven of the thirteen are clean;
three miscount on the IMU (see P1), two 2026-08-13 bench clips do not track, and
three could not be paired with their video because the IMU log and the clip
disagreed about the filename, two of them about the REP COUNT — **fixed by the
owner the same day (H16), IMU label right on both, so all 29 now pair and 27 of
29 are scoreable.** The two 2026-08-13 spoto benches are the exceptions and they
are a FOOTAGE problem: 94.1 and 72.2 cm of whole-clip travel on a bench press.
**Fixing the filenames removed the only flag that was catching one of them** —
its rep count had disagreed with its own name — which is why
`vtrack.IMPLAUSIBLE_MULT` exists as of H16 and why the flag is now two-sided.
A detector that fires because two records disagree stops firing when somebody
correctly reconciles them. One of them,
`squat_145x4_2_20260817`, is the first capture in the project filmed from the
lifter's LEFT on a lift other than deadlift. **Everything about them is measured
under H14's corrected scale and is not comparable to a number taken before
2026-08-17.** See TASKS.md H15.

*The statement it replaces:*
**THE CORPUS IS 16 LABELLED CAPTURES IN `data_v2/raw/` (2026-08-14).** The v1
half was deleted; every count below that includes `data/raw/` is history. The
paragraph as written said: **the corpus is 30 labelled captures and 124 reps** — 17 in `data/raw/`
(72 reps) and 13 in `data_v2/raw/` (52), plus four unlabelled diagnostic logs in
`data/raw/` that no count gate sees. It reached 24 and 101 with the three
8-sticker deadlifts of 2026-08-04 (6, 6 and 3 reps, the first captures in this
project refereed by the conic marker path, C27), and 30 and 124 with the six of
2026-08-06. **Every one of the 30 counts correctly (C31a, a2494b4)** — see P1.

*Numbers taken before those dates read differently and were all correct when
taken: 13 captures before `7004c32`, then 10 and 44 reps, then 17 and 72, then
21 and 86, then 24 and 101.*

Work the problems instead. Each is stated with the evidence that it is real,
so it can be closed by evidence rather than by opinion.

**P1 IS REOPENED AGAIN (H15, 2026-08-17), BY DATA RATHER THAN BY CODE.**
Thirteen captures arrived, the corpus is **29**, and **three of the new ones
miscount**: `deadlift_210x1_20260815` gives 2 windows for a labelled single
(27.1 cm and 66.3 cm, both outside the 40-61 band), `squat_140x4_1_20260813`
gives 3 of 4, and `squat_140x4_2_20260813` gives 2 of 4 with a 9.5 s hole
mid-set. **The video counts all three correctly**, so the labels are right and
the segmenter is wrong. The deadlift single is the `squat_160x1` /
`bench_117.5x1` shape once more; the two squats are dropped reps across long
cadence gaps, which is C31a's mechanism in the opposite direction from the
paused-squat fix. Left RED in the suite rather than xfailed, per F1's
precedent. See TASKS.md H15.

*The G1 statement it replaces, true of the 16-capture corpus:*
**P1's REOPENING IS CLOSED (G1, 2026-08-15). Counting is 16/16 captures and
64/64 reps on the live corpus, and both defects below are fixed.** F1's
diagnosis was right that the captures had never been under test; what it got
wrong is stated at the end of this block, because two of its three structural
claims do not survive being measured.

  * **`deadlift_150x4_1`'s fifth window** was `impact_anchors` reading a setup
    wrist swing as a floor landing. The video settles it: the bar is flat on
    the floor at 1.4–1.5 cm from 0 to 11 s, and the extra anchor is at 7.03 s.
    A threshold could never have separated it — the counterfeit peaks at
    7.01 g and the weakest REAL landing in the corpus is 6.69 g. What separates
    them is the second BEFORE the spike: 28 real landings sit at 0.39–0.98
    rad/s of wrist rotation, 4 setup swings at 1.65–2.83. See
    `segment.impact_anchors`.
  * **`bench_117.5x1`'s second window** was a real press at 21.9 s clustering
    with a setup arm movement at 10.6 s — correlation 0.80, displacement 0.290
    against 0.304 m. Split by whether the window's bar path is VERTICAL: 36
    real bench and squat reps score 3.64–15.08 on vertical-over-fore-aft and
    that setup movement scores 1.00. See `segment._upright`.
  * **A third defect, not in F1's list, found by checking the second fix's own
    work: `deadlift_200x1` counted 1/1 with its window on the DROP.** The video
    puts the pull at 15.7–17.5 s; the window was 18.97–19.92 s, at a plausible
    43.8 cm inside a 40–61 band. Two causes, both needed. The singleton cluster
    was ranked by DISPLACEMENT, and the drop carries 0.529 m against the pull's
    0.280 because the reconstruction invents velocity there; singletons now
    rank by verticality, which is 3 of 3 correct on the corpus's three singles
    where displacement is 1 of 3. And `_full_cycles` was passed a hardcoded
    `sets_down=False` despite documenting that it comes from the signal "so the
    lift is never named", so a lift resting on the FLOOR got the bench
    convention; it is now `len(anchors) == len(chosen)`. Window 15.51–19.43 s
    at 55.0 cm. **That is the third capture in this project's history to count
    correctly with the wrong window, after `squat_160x1` and `bench_117.5x1`,
    and no count gate can see any of them.**

**Two of F1's structural claims are WRONG, and the corrections matter more than
the fixes.**

*"C31a's plateau has closed."* It has not. `tol=1.47` failed only because
`bench_117.5x1` miscounted for an unrelated reason and because
`test_segmentation.py` had `RAW` and `RAW_V2` both pointing at `data_v2/raw`,
counting every capture TWICE — hence "28/32" for a 16-capture corpus. With the
segmenter fixed, every tolerance from 1.46 upward counts 16/16. **What actually
happened is worse and nobody had noticed: the plateau's CEILING is gone.** It
came from `bench_spoto_90x5_1`, which F1 deleted with v1. Swept to `tol=1e6`,
which disables the cadence rule outright, all 16 still count correctly — so the
constant is admissible, unfalsifiable from above, and its discriminator is
currently unexercised. A capture with a post-set movement inside the rep
cluster is the most valuable thing that could be filmed for this module.

*"P1 predicted exactly this"* — for the bench single, the prediction was right
about the CAPTURE and wrong about the MECHANISM, and the difference is
load-bearing. The prediction was that a bench single leaves every cluster at
size 1 so the tie-break picks the re-rack. Measured, `bench_117.5x1`'s winning
cluster has size **2** and the singleton branch never runs; the false window is
a setup movement 11 s BEFORE the press, not the re-rack after it. And the
tempting fix is a trap: raising `similarity` to 0.83 does break the false pair,
after which the singleton rule picks the 5.4 s unrack at 0.455 m — the right
count on the wrong window, `squat_160x1`'s failure again, and invisible to
every count gate. That plateau ([0.798, 0.872]) is real and it measures the
wrong thing.

F1's third claim stands: `deadlift_170x4_3` rep 4 is wrong EXTENT without a
miscount, at 67.5 cm against 40–61. It is the last entry in
`KNOWN_ROM_FAILURES` and it is a reconstruction defect, not a window defect.
*Evidence:* TASKS.md G1, `analysis/53`.

The reopening as F1 recorded it, kept because the reasoning trail is the point:

**P1 WAS REOPENED (F1, 2026-08-14). COUNTING IS NOT CLEAN — IT WAS UNTESTED.**
The heading below says 124/124 across 30 captures. That was true of the corpus
it was measured on, and the 2026-08-08 session was never in it: every gate
globbed `data/raw`, which no longer exists, so those captures had never been
segmented under test at all. Pointed at `data_v2/raw`, two of the sixteen
miscount immediately:

    deadlift_150x4_1_20260808   5 windows for a labelled 4
    bench_117.5x1_20260808      2 windows for a labelled SINGLE

**The video agrees with the labels on both** — `vtrack` counts 4/4 and 1/1 on
the same clips — so this is the segmenter, not the labels. `deadlift_150x4_1`'s
vertical rms against the video is 27.6-30.1 cm where every other deadlift is
1.7-4.9, which is what one spurious window does to a per-rep comparison.

**The bench single was PREDICTED here and the prediction is below, unchanged.**
This file already said `_similar_cluster`'s lateness tie-break picks the latest
movement when every cluster is size 1, that on a bench single the latest
movement is the re-rack, and "if you capture a bench single, expect this to
fail." One was captured. It failed. That is the prediction being right, not a
new mechanism.

Three more gates went red with them, and two are structural rather than
per-capture:

  * `test_cadence_tolerance_is_a_plateau_not_a_point` — **C31a's plateau has
    closed.** It recorded 1.4598-1.5306 and warned the 2.4% margin was thin and
    two-sided. tol=1.47 now gives 28/32.
  * `test_only_a_single_has_a_degenerate_cluster` — `deadlift_200x1` now reaches
    the displacement fallback, which C5 built for `squat_160x1` alone.
  * per-rep vertical ROM is out of band on `bench_117.5x1` (42.1 cm against
    20-35), `deadlift_150x4_1` (67.8 against 40-61) and `deadlift_170x4_3`
    (68.0) — the third counts 4/4, so that one is wrong EXTENT without a
    miscount, the `squat_160x1` shape.

Recorded in `tests/test_real_data.py`'s `WRONG_REP_COUNT` and
`KNOWN_ROM_FAILURES` with per-capture reasons. The two structural failures are
deliberately left RED rather than xfailed: they are the finding, and burying
them under an expected-failure mark is how the previous ones stayed invisible.
*Evidence:* TASKS.md F1.

**P1 — Counting and extent are clean at 124/124; phase is now verified on
deadlift and bench, and open only on squat.** *(The heading read 72/72 until
2026-08-06; it is 124 reps over 30 labelled captures now — C31a, a2494b4.)*
Rewritten 2026-07-31 by C5, and
again the same day by C9, which answered the phase question this heading used
to call untouched. Bench: 15 of 15 windows in phase. See *Window extent* below.

*Counting:* A1 closed this at 44/44 with zero false positives, against the old
stationary detector's 0 of 14 bench and 1 of 15 squat. That was true on the ten
captures then held. The 2026-07-30 session broke it to 71/72 —
`bench_spoto_90x5_1` segmented a 5-rep set into **6** windows, the re-rack
counted as a rep — hidden because `REP_LABEL` did not match the `spoto` variant
token, so `expected_reps` was `None` and every count gate silently skipped all
three new benches.

C5 fixed it on 2026-07-31 and counting was **72/72** on `data/raw` —
`_longest_cadence`'s tolerance was 1.6, admitting a post-set gap and growing a
run of six that beat the true five on length alone. C5 set it to 1.45,
mid-plateau of a 1.35–1.55 band, and this paragraph then warned that "a
rest-pause or cluster set has a real mid-set gap above 1.45 and would be split.
No such capture exists."

**One arrived on 2026-08-06, the plateau turned out to have closed to NOTHING,
and the fix is a new RULE rather than a new constant (C31a, a2494b4).** Two of
the four paused squats counted 3 of 4 — `squat_pause_140x4_2` dropped its FIRST
rep, `_3` its LAST — and both are real reps, sitting in `_similar_cluster`'s
winning cluster with their siblings at 0.75–0.97 shape correlation and
reconstructing 65.4 and 69.7 cm. This was C5's function and C5's mechanism in
the *opposite* direction: the tolerance was too TIGHT for a real set, not too
loose for a post-set gap. It is **not** C22's chain-versus-cluster failure —
the cluster is correct on both captures and holds all four reps.

A paused squat's cadence LENGTHENS rep by rep as the lifter takes longer to
re-breathe and re-brace:

    squat_pause_140x4_3   gaps 5.43, 5.85, 8.53 s   spread 1.573
    squat_pause_140x4_2   gaps 4.88, 5.53, 7.27 s   spread 1.490
    squat_pause_145x4_1   gaps 6.08, 6.32, 6.53 s   spread 1.074  (counts 4/4)

Measured by the run's GLOBAL max/min spread — what the old rule tested — a
drifting set is indistinguishable from a set with a post-set movement tacked on,
and **the two constraints are DISJOINT**: `bench_spoto_90x5_1` is correct only
for tol ≤ 1.572, `squat_pause_140x4_3` only for tol ≥ 1.576. **No constant could
count both, so a re-tune was never available** — which is the durable part, and
the reason the fix is structural.

`_longest_cadence` now admits a run on **LOCAL drift** — each gap against its
NEIGHBOUR rather than against the run's extremes — and breaks length ties on
cadence **EVENNESS** before lateness. Both halves are needed:

    rule                              admissible tol      width
    global spread + lateness (old)    none - disjoint         -
    global spread + evenness          none - disjoint         -
    local drift   + lateness          [1.4598, 1.4882]     1.93%
    local drift   + evenness (ships)  [1.4598, 1.5306]     4.74%

Evenness is needed because under local admission `bench_spoto_90x5_1` grows a
post-set run of five that ties the true five on length and wins on lateness
alone, despite cadence 44% worse (1.488 against 1.036). Lateness is kept as the
last key, so `bench_92.5x2` — the capture it exists for — is decided exactly as
before. **The tolerance is 1.50**, the round value nearest the midpoint 1.495;
the 1.45 and the 1.35–1.55 plateau this file used to quote are superseded.

**Read the new margin honestly: 2.4% either side, against the 8–11% the old
constant enjoyed before these captures existed.** It is two-sided and measured
on two different captures on two different lifts, but it is thin, and a capture
that pauses harder will push the floor into the ceiling. A count-only gate would
have hidden all of this — at tol 1.573 `bench_spoto_90x5_1` still counts 5, but
they are the WRONG 5 (ROM 88.7 and 62.9 cm on a bench press). This repo's
recurring shape once more: the count is right and the windows are not.
`tests/test_segmentation.py` gained `ALL_CAPTURES` so the plateau gate finally
sees `data_v2/` — being blind to it is how the plateau closed unnoticed — plus a
test asserting the old rule's emptiness so nobody re-tunes their way back in.
*Evidence:* `analysis/47`, `python run.py --pausedsquat`, TASKS.md C31a.

**Counting is 30 of 30 labelled captures, 124 of 124 reps** — the 24/101 above
plus the six of 2026-08-06, and across all 34 CSVs every window that was already
correct is **bit-identical** under C31a's rule. C27 had added three deadlifts at
6/6, 6/6 and 3/3 with every floor impact found. The two captures that ever broke
it were deleted (see above), so this remains a smaller claim than 22/23 rather
than a strictly better one.

*Unexplored, and recorded by C31a rather than chased: a discriminator that is
not a gap ratio at all is available.* Both paused squats have a rejected
low-velocity lobe INSIDE the long gap (at 43.20 s and 44.61 s) and
`bench_spoto_90x5_1`'s post-set gaps have none — which would separate the two
cases without any tolerance.

**What the deleted squat taught, kept because the mechanism will recur (C22).**
`squat_150x5` segmented 4 of 5, and the cause was **not** the cadence tolerance
this paragraph had been warning about — that was checked first and
`_longest_cadence` never sees the fifth rep. It is
`_similar_cluster`: across a heavy set the velocity profile drifts with fatigue,
so the fifth rep correlates **0.518** with the first and 0.859 with the fourth.
**The reps of a fatiguing set form a chain, not a cluster**, and the clustering
tests for a cluster. Two fix families were measured and rejected — single-
linkage chaining (over-counts `bench_spoto_90x5_1` to 11) and extending the
cadence run by size (no setting on a 4×5 tolerance grid beats shipping). See
TASKS.md C22 for what a fix would have to do.

Two things that fix taught us, both about how a right-ish count hides errors.
The old segmenter was *also missing rep 1* there — 4 real plus 2 spurious, not
5 plus 1. And duration was blind to it: the spurious windows ran 2.1 and 2.6 s
against real reps of 2.5–2.9 s, and only their 45.7 and 88.7 cm of vertical gave
them away. *Mechanism and plateau margins:* TASKS.md C5.

*Window extent, which is new.* Counts cannot see phase — the segmenter scored a
perfect 44/44 while every window ran lockout-to-lockout, half a rep out of step.
Deadlift boundaries come from floor impacts, which use raw acceleration alone,
match video to 13.5 ms, and put exactly one video lockout in each of the 15
deadlift windows. **Squat still has no phase anchor** and still segments on
integrated velocity carrying 145 cm of in-band error against a 69 cm signal, so
its phase stays unverified until P3 is fixed.

**Bench acquired one on 2026-07-31 (C8) and C9 used it the same day. Bench
windows are IN PHASE.** All **15 of 15** windows on the three synced captures
hold exactly one video chest touch, and the touch falls 0.567–0.648 of the way
through — nowhere near the 0.0/1.0 that the half-a-rep-out failure mode would
give, and which is where deadlift's old 44/44 segmenter actually sat.

The touch sits at ~0.60 rather than 0.50, and that is the bar's behaviour, not
a bias: measured in the **video alone**, with no IMU and no sync, the descent
takes 0.573/0.590/0.582 of a rep, against the IMU windows' 0.593/0.613/0.619.
A bench descent is controlled and a press is not — 1.6–1.9 s down against
1.2–1.3 s up. The two modalities agree to 0.02–0.04 of a rep, i.e. 60–100 ms.

Note this survives `bench_sync`'s known weakness rather than depending on it. A
whole-rep-period sync error is invisible to a phase test by construction, since
a periodic set looks the same shifted by one rep — so the ambiguity bench_sync
cannot resolve is exactly the one that cannot corrupt this. A *fractional*-period
error would show, and does not: all three agree to 0.03 despite offsets of
+0.040, −2.320 and −0.585 s.

**Squat's phase is still unverified and now the only unverified case.** It has
no external anchor of any kind, and two of its four 2026-07-30 captures do not
track. *Evidence:* `analysis/30`, `tests/test_real_data.py`.

But they now have a *partial* external check: per-rep vertical ROM against
`truth.VERTICAL_ROM_M`. It cannot see phase either — a window half a rep out of
step has the right amplitude — but it does see a window that spans too much or
too little, which counting cannot. It found `squat_160x1` reconstructing 18.0 cm
for a 160 kg single at a correct count of 1 of 1: the first time a gate in this
project caught a right-count-wrong-window failure.

C5 fixed that one too, and its cause is worth keeping because it is a hole in an
argument rather than a bad constant. `_similar_cluster`'s lateness tie-break
encodes "a lifter sets up first and lifts second", which correctly rejects
everything *before* the reps and says **nothing about what comes after them, and
something always does.** On a multi-rep set size decides first, so it never
bites; on a *single* every cluster is size 1, lateness decides alone, and the
latest movement in any capture is by construction the re-rack. Singletons now
rank by concentric displacement — an argmax, no threshold — and it reads 67.0 cm.

**That rule is unfalsified on bench rather than verified there, and the
distinction is load-bearing.** It claims a working rep moves the bar further
than the movements bracketing it. That is measurably false on bench:
`bench_92.5x2`'s unrack carries 0.433 m against 0.295 and 0.239 for its two real
reps. Clustering saves every bench capture we hold (winning cluster size 4+), and
`squat_160x1` is the only one of 17 whose winning cluster is size 1 — but **a
bench single would enter this branch and pick the unrack.** Duration does not
rescue it either. If you capture a bench single, expect this to fail.

The C3 `phase` column cannot help either defect, which was checked rather than
assumed: the lifter re-racks *before* pressing "Finish Set", so both spurious
windows sat entirely inside `phase == 1`. **The column marks the closing hold,
not the end of lifting.**

*Evidence:* `analysis/04`–`07`, `12` for the old failure; `15`–`18` for A1;
`17` and `src/README.md` for the phase bug; `23` and `analysis/README.md` for
the ROM bounds; `tests/test_segmentation.py` and `28` for C5.

**P2 — READ THIS FIRST (C31, 2026-08-06). EVERY NUMBER BELOW WAS MEASURED WITH
STEP 6 OFF, AND STEP 6 IS NOW ON.** See the banner in the Pipeline section. The
whole of P2 — every `h rms`, every `beats_null`, every excursion figure, and the
tables C10, C12, C24, C25, C27, C29 and C30 contributed — describes the
reconstructed **watch** path. To reproduce any of them, pass
`wrist_offset=None`. Where a post-`d` figure exists it is given below beside the
old one; where none is given, none has been measured, and the old figure should
be read as history rather than as the pipeline's current output.

**And C30's headline is OVERTURNED — the deadlift horizontal channel was never
empty, it was masked by the uncorrected wrist lever (C31, 7bc4bcb).** Re-running
C30's own acceleration-error correlation with step 6 ON:

    lift        best-dir horizontal corr, d OFF -> d ON
    deadlift        0.118-0.232  ->  0.432-0.641
    bench           0.798-0.919  ->  0.814-0.937   (6 of 6 improve)
    vertical        0.967-0.994, unmoved either way (the control)

The vertical control not moving is what says this is a real recovery on the
horizontal rather than a global rescaling. **The term that did it is the one
C30 itself named as prime suspect while lacking `d`.** *Note C30's measurement
code was never committed — `ceba50a` holds only the docs and the PNG — so C31
reimplemented it from the method in that commit message; it reproduces C30's own
baseline to within 0.03. Commit the code that makes a headline.*

**AND IT DOES NOT CASH OUT IN POSITION. That gap is the finding, not a
footnote.** `metrics.vs_truth`, step 6 off → on, on the nine marker-refereed
captures:

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

Deadlift horizontal improves on 3 of 3 but only ~5–8%, and `beats_null` stays at
0.14–0.35. Bench horizontal is a coin flip. **Bench VERTICAL is the one clean
consistent effect: better on 6 of 6, by ~20–25%.** Correlation is shape
agreement and blind to gain; rms after double integration is not.

**Under the TEMPLATE referee it is unambiguously good, and that is the strongest
single piece of evidence for the default.** Three captures crossed
`beats_null = 1.0` and **all seven template-refereed benches now beat the flat
line**, where C10's table below had **three of the seven losing** — and they are
exactly the three that crossed: the 2026-07-30 paused benches at 0.72, 0.80 and
0.92. *(C31's commit message says "four of them"; C10's own table shows three
benches under 1.0, and six of ten only when the three deadlifts are counted in.
Three is what the table supports.)* The three deadlifts still lose and stay
`xfail`.

**The cost, recorded rather than absorbed:** `bench_90x4_2` and `_3`, the only
two captures in the life of this project where the horizontal reconstruction
demonstrably carried information, fall **4.80 → 3.45** and **4.03 → 2.25**
against the null. Both still beat it comfortably. Those two were re-recorded in
`tests/test_real_data.py` with the old values kept beside them; every other
capture stayed inside the existing 20% headroom. *The post-`d` `beats_null` for
the other five template benches has not been written down anywhere — only that
all seven now exceed 1.0. Do not infer values for them from this table.*

**AN UNRESOLVED TENSION, and it must not be smoothed over.** C32 nominated the
PAUSE as the explanation for the bench dissent, because both `data_v2` captures
where `d` hurt are paused benches. Switching step 6 on falsified the simple
version of that: **`d` fixed all three paused benches under the TEMPLATE referee
while still hurting the paused benches under the MARKER referee.**

    data/video,  truth.py template    d helps uniformly (7 of 7 beat null now)
    data_v2,     markers.py conic     d mixed (3 better, 3 worse)

**The surviving split is by REFEREE, not by pause** — and neither referee has
been shown right. C24 already had them disagreeing ~20% on ROM. This is the
highest-value open question in the project now. Two confounds were checked:

- **DEAD — the scale.** C32 swept `bench_spoto_95x5_1`'s referee scale over a
  47% span (ratio 0.681 to 1.000); `d` is worse at **every** point and
  `beats_null` with `d` on never exceeds 0.92. The dissent is scale-invariant,
  so it is not the ruler. That capture's 0.68-of-plate-radius warning is
  `truth.find_plate` mis-detecting the rim on all six `data_v2` benches, not the
  stickers, and the capture is fit to referee — 100% coverage, 0.260 px median
  residual, 0.158 px over the top 15% of travel, five of five video chest
  touches one per IMU window at 0.543–0.651 through them. `bench_spoto_95x5_2`
  reports 0.692 on the same plate, so nothing singles `_1` out. *Evidence:*
  TASKS.md C32, 18501a3.
- **OPEN — the camera side.** The regressing benches are filmed from the side
  opposite the watch, so the referee tracks the far end of the bar. See the
  camera-geometry note in the two-referees section.

Also untested: whether `d` is right in DIRECTION and wrong in effective
MAGNITUDE, because wrist extension under load changes the lever arm. Against it,
C31b measured position rms to be **monotone in |d| out to 3× the tape**, so
there is no interior optimum for that to hide in. The acceleration correlation
*does* have one, at 0.5–0.75× the tape on all six benches and nowhere on
deadlift — consistent with wrist extension shortening the effective lever, and
unresolved. See `analysis/48` and `python run.py --dpaths`.

**Squat is no longer the lift with no external horizontal check (C31,
2026-08-06), and `metrics.vs_truth`'s refusal of it is now STALE.** The
8-sticker squat plate tracks — **but only on TWO of the four clips, and the
first version of this paragraph said all four (C31, corrected 2026-08-07).**

    squat_pause_145x4_1   100%   0.88 px   travel 59.4 cm   good
    squat_pause_140x4_2   100%   0.69 px   travel 60.1 cm   good
    squat_170x1          97.8%   1.11 px   travel 14.0 cm   MIS-TRACKED
    squat_pause_140x4_3  96.7%   1.12 px   travel 24.7 cm   MIS-TRACKED

14 cm of travel for a 65 cm squat is not the bar. Note the failure shape, which
is this project's recurring one: **coverage and residual look HEALTHY on the bad
clips** because the constellation is fitting *something* rigidly, frame after
frame. The error was measuring `squat_pause_145x4_1` and generalising to the
session. So squat had a PARTIAL external check — the first in this project —
rather than the whole one claimed here. And `vs_truth` refused squat by a
hardcoded check whose stated reason (median NCC ~0.40, plate clipping the
frame, two of four captures not tracking) described the OLD template footage in
`data/video/` and did not describe `data_v2/`.

**THE REFUSAL IS GONE (G2, 2026-08-15), AND SQUAT IS REFEREED.** Two things
that were open when the paragraph above was written have closed. F1's
`src/vtrack/` tracks all four squat clips — the two "MIS-TRACKED" rows above
are fixed, and that table is history rather than current state. And
`bench_sync`, which `_video_on_imu_clock` has always routed non-deadlift lifts
to, turns out to work BETTER on a paused squat than on any bench: correlation
0.73–0.76 against bench's 0.46–0.63, with **no whole-rep rival on any of the
three** where every bench has two to four.

    squat_pause_140x4_2   h 1.88 cm   v 5.20   beats_null 1.71
    squat_pause_140x4_3   h 2.97 cm   v 8.26   beats_null 1.24
    squat_pause_145x4_1   h 2.65 cm   v 8.05   beats_null 1.50

**All three beat the flat-line null**, which no deadlift does, and squat's
horizontal is second only to `bench_92.5x6_1/2`. C31's exploratory bypass
predicted this closely — it had 2.00 and 2.95 cm against the 1.88 and 2.65
measured properly — and it was right to call those indicative: run through the
correct `d` for squat rather than bench's, they move by ~10%.

**What made it a result rather than a bypass is `metrics.pause_landmark`.**
`bench_sync` identifies a lag only up to a whole rep and its validation is
transferred from deadlift, and `vs_truth`'s per-rep table is exactly the kind of
quantity a whole-rep error destroys. The bottom of each rep is now named twice
independently — by the raw IMU (`segment.dwell_instants`) and by the video —
and the two agree to 0.003–0.083 of a rep on all seven multi-rep bench and
squat captures. `_video_on_imu_clock` refuses when they disagree by more than
0.25 rep; injecting a whole-rep error catches 14 of 14.

~~`squat_170x1` is still refused, for a reason that is not about squat: it is a
single, so there is no cadence, exactly as for `bench_117.5x1`.~~ See TASKS.md
G2 and `analysis/55`.

**CLOSED 2026-08-15 (G3). The corpus is 16 of 16 scored.** The three singles —
`bench_117.5x1`, `deadlift_200x1`, `squat_170x1` — score at h 0.96 / 2.66 /
2.05 cm and all three beat the flat-line null. `src/shortset.py` supplies a
clock a one-rep capture can support: the same correlation with the cadence
precondition removed and **the sweep bounded by overlap rather than by lag**,
because on a single `bench_sync`'s widening search picks a lag 10–19 s wrong and
scores it HIGHER than the truth. Accuracy 7.5 ms median against twelve known
answers, and +10.9 ms on `deadlift_200x1` against its own floor impact.
`pipeline.py` and `segment.py` are untouched; the thirteen multi-rep captures
are bit-identical. See TASKS.md G3 and `analysis/56`.

**The task's premise did not survive measurement, and that is the part to
remember.** It assumed singles need a new SEGMENTER; they do not — the segmenter
gets 1/1 on all three real singles and on thirteen truncated ones. The proposed
"maximum displacement between IMU dwells" rule was built and lost to the
existing segmenter on every reading, because **integration drift produces more
apparent displacement than a rep does** (86.8 cm claimed on a 27 cm bench
press). Do not re-propose displacement as a selection rule without removing the
drift first.

**Two pre-existing defects were found in passing and are NOT fixed:**
`deadlift_170x4_3` is scored through a landing-to-impact fit with slope 0.7715
— a 22.8% clock drift, 216 ms residual — and nothing gates on `drift_pct` or
`rms_ms`; and `capture.sync` and `metrics.bench_sync` return `fit["offset"]`
with **opposite signs**, which is safe as long as nobody compares them and
silently wrong the moment somebody does.

*The C30b entry below is kept in full, and one of its two arguments has since
been falsified — see the bracketed note inside it.*

**P2 (C30b, 2026-08-05): C30's headline was WRONG, and the
correction is more useful than the claim was.** C30 measured the acceleration
error as a time series on three deadlifts, found the reconstruction's fore-aft
uncorrelated with the bar's, and concluded "the horizontal channel is empty".
**The owner pushed back — the deadlift is not like the other lifts — and was
right.** The same test on bench:

    lift        corr(recon, video) HORIZONTAL   best over all dirs   VERTICAL
    bench            +0.68 .. -0.91                0.79 - 0.94        0.99
    deadlift         -0.08 .. -0.16                0.10 - 0.23        0.97-0.99

**The horizontal channel is not empty. On bench it carries strong signal.** Both
referees agree — the four marker-refereed benches give |r| = 0.68-0.86 and the
seven template-refereed ones up to 0.94 — so it is not a tracker artefact, and
it cannot be the sync either, since deadlift's sync is the BETTER one
(landmark-matched at 9-19 ms) and correlates worse.

**And the mechanism C30 proposed is also wrong.** C30 blamed the wrist lever arm
`R(t).d`. But the wrist swing per rep is **17.3 deg on bench against 21.8 on
deadlift** — nearly the same, sweeping 3.6 vs 4.5 cm for |d| = 12 cm. If the
lever were the dominant contaminant, bench would be almost as broken. It is not.

> **THIS PARAGRAPH IS FALSIFIED (C31, 2026-08-06), and the way it failed is
> worth more than the claim.** The owner measured `d` the next day; applying it
> took the deadlift horizontal correlation from 0.118–0.232 to 0.432–0.641 while
> moving bench only 0.798–0.919 → 0.814–0.937. **The lever arm WAS the dominant
> contaminant on deadlift**, exactly as C30 said, and C30b's symmetry argument
> was the thing that was wrong. Where it went wrong is instructive: it computed
> the lever's ABSOLUTE contamination (swing angle × |d|, ~3.6 vs 4.5 cm) and
> inferred equal DAMAGE. Damage is contamination measured against what is left
> after it, and the two lifts differ there — bench's correlation was already
> 0.80–0.92 with the lever uncorrected, deadlift's was 0.12–0.23. Why the same
> absolute term is near-fatal on one lift and not the other is **not explained**
> and is open. *Do not read the sentence below as still standing on this
> argument.*

**What actually separates them is the FLOOR IMPACT.** Peak |a| is 15.3-21.8 g on
deadlift against 2.1-6.4 g on bench; peak gyro 595-1034 deg/s against 229-428.
That is the one thing deadlift has and bench does not, and it is the same event
C11, B6 and P6 already localise the VERTICAL momentum deficit to. Nobody had
connected it to the horizontal channel.

*The impact remains a live suspect, but it is no longer supported by the
argument above; it now stands on its own evidence (C11, B6, P6, C28b, C29) and
must share the field with the lever arm rather than replacing it. And C31's
result narrows what is left to explain: with `d` applied, deadlift's remaining
horizontal correlation gap is 0.43–0.64 against bench's 0.81–0.94, so there IS
still a deadlift-specific deficit — just a much smaller one than C30 measured.*

So P2 is a DEADLIFT problem, not a horizontal-axis problem, and the impact is
one of two prime suspects on both axes. *Evidence:* TASKS.md C30b and C31,
`analysis/46`, `analysis/48`.

*What C30 did establish, and it stands:* on deadlift the fore-aft acceleration
is uncorrelated with the bar's even optimising the projection direction post
hoc; step 7 cannot touch any of it, since removing a linear function of t leaves
the second derivative unchanged; and the flat-line null wins precisely because
predicting the mean is optimal when you have no information. The original C30
text follows.

**C30 (2026-08-05, branch `c29-jump-state`) — the deadlift horizontal, measured
as a time series for the first time — differentiating the marker path twice and putting the
reconstruction through the identical filter — and found:

    capture            corr(recon, video)   best over ALL dirs   VERTICAL
    deadlift_160x6_1         -0.077               -0.103           0.990
    deadlift_160x6_2         -0.156               -0.233           0.975
    deadlift_185x3           -0.102               -0.115           0.971

The vertical is the positive control: same clip, same filter, same code, r =
0.97-0.99. The horizontal, optimised post-hoc over all 90 directions so B4's
unresolved axis cannot be blamed, reaches -0.10 to -0.23. **The reconstruction's
fore-aft acceleration is uncorrelated with the bar's, at comparable magnitude.**

P3's stated mechanism is not it either: regressing the error on `R(t)^T axis` —
the exact model "body-frame bias through a rotating forearm" implies — explains
17-23% and needs |b| = 0.42-1.25 g against P4's 0.0025 g.

**Why this axis and not the other.** The bar's true horizontal acceleration is
0.13-0.21 m/s^2, **6-7x smaller than its own vertical** (0.86-1.27). So any
wrist-versus-bar term is 6-7x more damaging horizontally, and that ratio needs
nothing known about `d`. The lever arm `R(t).d` is the obvious candidate — the
bar is constrained to move nearly vertically while the forearm rotates about it
— and **step 6, which would remove it, is OFF because `d` has never been
measured**. Order of magnitude only: ~1.9-3.3 m/s^2 for |d| = 12 cm, and the
vertical's r = 0.976 bounds the true term below that.

**This reframes everything below from quantitative to qualitative.** It explains
why `beats_null` is under 1 everywhere (a flat line necessarily beats
uncorrelated motion), why five corrections failed (B7, B6, C19, C28b, C29 were
rearranging noise), why C28's oracle capped at the null (nothing to recover),
and why C29 cut `h_rms` 44% without touching excursion. **`d` is the highest
value measurement available now** — a tape from watch centre to bar centre, in
watch axes. B2 priced it at 1-2 cm by its effect on position after the detrend;
in acceleration, before anything, it is plausibly the dominant term on the one
axis the spec is about. *Evidence:* TASKS.md C30, `analysis/46`.

> **C30's call was RIGHT and the owner acted on it the next day (C31,
> 2026-08-06).** `d` was tape-measured, step 6 is on, and the acceleration
> correlation this section reports as -0.10 to -0.23 is **0.432-0.641** with it
> applied. So the paragraph above is the best prediction anyone made in this
> problem — including against C30b, which argued the day before that the lever
> could not be the discriminator.
>
> **But read the reframing carefully, because it does NOT all survive.** "Five
> corrections were rearranging noise" and "C28's oracle capped at the null
> because there was nothing to recover" were inferences from an empty channel,
> and the channel is not empty. What was actually re-measured: C31 re-ran C28's
> ladder with `lever` PINNED at the tape and **C28's negative result still
> stands** (see P3), and C28b's/C29's impact results have NOT been re-run with
> `d` — that is open work, listed in `analysis/C31b_STATE.md` item B. Treat the
> "qualitative" reframing as retracted where it rests on emptiness and intact
> where it rests on its own measurement.
>
> And the last sentence is now measurable rather than plausible: `d` recovers
> most of the deadlift acceleration correlation and **almost none of the
> position rms** (7.22/4.55/11.44 → 6.65/4.39/10.61, `beats_null` 0.14–0.35
> throughout). Correlation is blind to gain; rms after double integration is
> not. See the C31 block at the top of P2.

**P2 (as measured before C30) — Horizontal is 5–15× outside spec; vertical is
out too, but the ruler that says so is itself broken on two captures of three.** Measured against
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

**READ THIS FIRST OF ALL — 2026-08-04 (C27). Deadlift now has a referee that
does NOT fail at lockout, and it makes the verdict below worse rather than
better.** Three 8-sticker deadlifts, tracked by the conic path: coverage
99.2-100%, median residual 0.28-0.59 px, and **every marker found in every
decile of travel, floor to lockout**, against the plate template's 166/166
top-of-travel frames below `GOOD_SCORE`.

Per-rep video ROM comes out **51.4 / 51.9 / 51.5 cm — a 0.5 cm spread** — where
the three template-refereed deadlifts give 59.1 / 66.8 / 47.6, a 19 cm spread on
a range of motion fixed by the lifter's own limbs. That is the "do not quote the
spread" problem below, fixed by the referee rather than by code.

    capture            h rms   null   beats_null   v rms   sign
    deadlift_160x6_1    7.22   1.65      0.23      3.45    1/6
    deadlift_160x6_2    4.55   1.55      0.34      3.70    1/6
    deadlift_185x3     11.44   1.60      0.14      1.76    0/3

**All three are 3-7x worse than drawing no fore-aft motion at all.** The video
puts the bar inside 4.3-6.2 cm of fore-aft; the reconstruction sweeps 20-35.
**These REPLACE the 0.70 / 0.35 / 0.13 below rather than confirming them** — C12
showed those were measured through a tracker inventing ~10 cm of fore-aft at
lockout, which inflates `null_h_rms` and therefore flattered the pipeline. These
are the first deadlift `beats_null` figures that mean what they say.

Two things did improve: sign disagreement is 1/6, 1/6, 0/3 against 4/6, 2/6, 1/3,
and `deadlift_185x3`'s vertical at 1.76 cm is inside the +/-2-3 cm spec.

*Open:* the absolute scale still rests on `STICKER_RATIO = 0.858`, borrowed from
the old three-sticker plate, and against it the video reads 4.6-9.3% BELOW the
reconstruction. A ratio of ~0.92 would close it exactly and must not be adopted
by fitting it; the sticker-circle diameter with a tape settles it, into
`bar_path(sticker_diameter_m=)`. `beats_null` barely moves under it, so the
horizontal verdict does not depend on the open question. *Evidence:*
`analysis/42`, `python run.py --dlconic`, TASKS.md C27.

**CLOSED 2026-08-17 (H14), BY THE TAPE, AND THE PREDICTION HELD.** See the
banner at the top of this file. The correction on deadlift is **+6.07%**, inside
the 4.6-9.3% measured here and derived from geometry rather than fitted to it.
It was NOT adopted as a ratio, which is the part this paragraph got slightly
wrong: the sticker inset is an absolute 1.0 cm, so the equivalent ratio is 0.953
on a 425 plate and 0.956 on a 450 — no single number is right for both, and
`vtrack.STICKER_CIRCLE_M` holds the measured circle instead. `beats_null`'s
invariance held exactly as claimed (median 1.25 -> 1.26 corpus-wide).

**C32 tried to close that without a tape on 2026-08-06 and FAILED
instructively — the ratio is still open and the answer is still a tape.**
Re-measuring the rim with no matched filter (per-ray intensity edge outward
from the tracked centre, median over 720 rays and 25 frames) gives 0.936–0.947
on the five eight-sticker captures against 0.907–0.926 on the old three-sticker
ones, which looked like a 9% error in `STICKER_RATIO` until it was run on the
constant's OWN source footage: **this is the radial-gradient search `markers.py`
already tried and rejected**, whose recorded failure is 0.928/0.938/0.929 on
those clips with the overlay showing it sitting on the bumper's inner step, and
today it returns 0.919/0.922/0.926 there. It reproduces its own rejection, so
it carries a positive bias of unknown size and cannot set a scale. What survives
is only the DIFFERENCE between plates — the eight-sticker circle sits perhaps
1.5–3% closer to the rim than the old one, C27's direction but nowhere near
enough to confirm C27's size. **Nothing was re-tuned, deliberately:**
`STICKER_RATIO` and `truth.sticker_plate_diameter` cancel one another on the
older captures, so moving one alone silently rescales all of them.

Two negative controls recorded with it, because both look like confirmation and
are not. Scaling the referee up improves `pipeline_v_rms` on every bench capture
*including the three-sticker ones*, so that is the known IMU-vs-video vertical
disagreement (C24) and says nothing about the sticker circle. And the
2026-08-03 benches are light blue calibrated discs, so a dark-plate edge test
barely applies to them. Also verified in passing: `bar_path` still reproduces
`STICKER_RATIO`'s calibration on its own source footage after four rewrites of
the seeder — 0.861/0.877/0.898 today against the recorded 0.862/0.878/0.834.
*Evidence:* TASKS.md C32.

**A second scale question, OPEN and one question to the owner rather than a
code change (C32).** `truth.STICKER_PLATE_DIAMETER_M` has no 2026-08-06 entry,
so bench falls through to 0.425 m and squat to 0.450 m **by accident rather
than by decision**. If one stickered 425 mm plate was moved between the two
bars, squat is 5.9% out. Noted in `truth.py`; nobody has asked.

**READ THIS SECOND — 2026-07-31 (C12). The deadlift PLATE-TEMPLATE referee is
lost at lockout, and every deadlift number below that predates C27 is measured
through it.** Spotted by the owner from `analysis/33`: the video traces a flat ~10 cm
fore-aft line at the top of the pull, which is against the physics of the lift —
the bar is held against the thighs at lockout and is very nearly still. It is
the tracker moving, not the bar.

Measured, and it is total and perfectly stratified by height. Frames in the top
10 cm of travel scoring below `truth.GOOD_SCORE`: **166/166, 149/149, 146/150.**
Frames in the bottom 10 cm: **1/743, 0/780, 0/588.** Median NCC over the top 15%
of travel is **0.371 / 0.395 / 0.440** against whole-clip medians of
0.830 / 0.846 / 0.937. Bench is the control and holds up at 0.563–0.850.

**`truth.validate` could never see it**, because it checked the whole-clip
median and lockout is only 8–15% of a clip. That is this project's recurring
failure shape once more: an aggregate that passes while the thing fails exactly
where it matters. `truth.top_of_travel_score` now measures it and `vs_truth`
reports `video_top_ncc`.

**What it costs is not what you would guess.** The invented fore-aft motion goes
into `null_h_rms`, which is what `beats_null` divides by — so the referee's
failure was *flattering* the pipeline. Restricted to frames scoring above
GOOD_SCORE (56–67% of each rep):

    capture             h rms           null           beats_null
    deadlift_155x6_1    5.05 -> 4.00    3.55 -> 2.36   0.70 -> 0.59
    deadlift_155x6_2    9.19 -> 9.76    3.23 -> 2.03   0.35 -> 0.21
    deadlift_180x3     15.44 -> 16.91   1.96 -> 1.18   0.13 -> 0.07

So the horizontal MAGNITUDES below stand — P2 is still 5–15× out — but **the
deadlift `beats_null` figures are too generous by 15–45%.** Not the template
size, which was the first guess: shrinking `half` raises NCC to 0.69 and makes
the track worse, inflating ROM from 60.5 to 74.1 cm. The fix is a wider shot,
not code. *Evidence:* `analysis/34`, `tests/test_video_truth.py`.

**READ THIS THIRD — 2026-07-31 (C10). Against the null model, most of the
pipeline is worse than useless on the horizontal.** `metrics.vs_truth` now
reports `null_h_rms`: what you score by drawing **no fore-aft motion at all**, a
straight vertical line. `beats_null` is that over the pipeline's error.

    bench_90x4_2         0.64 cm vs 3.08    4.80x   better
    bench_90x4_3         0.76 cm vs 3.06    4.03x   better
    bench_92.5x2         2.75 cm vs 3.13    1.14x   better
    bench_90x4_1         1.88 cm vs 2.07    1.10x   better
    bench_spoto_90x5_3   2.63 cm vs 2.42    0.92x   WORSE
    bench_spoto_90x5_2   2.69 cm vs 2.16    0.80x   WORSE
    bench_spoto_90x5_1   3.67 cm vs 2.63    0.72x   WORSE
    deadlift_155x6_1     5.05 cm vs 3.55    0.70x   WORSE
    deadlift_155x6_2     9.19 cm vs 3.23    0.35x   WORSE
    deadlift_180x3      15.44 cm vs 1.96    0.13x   WORSE

**Six of ten, including all three deadlifts, are beaten by a flat line.** The
"5–15× outside spec" framing below is measured against the spec; measured
against doing nothing, deadlift is 1.4–7.9× worse than useless on the one axis
this project exists to draw. `bench_90x4_2` and `_3` are the only captures where
the horizontal reconstruction demonstrably carries information.

This check is one line of arithmetic and nobody had run it in the life of the
project. Quote `beats_null` alongside any horizontal number.

**A fourth measurement, 2026-07-31 (C8, extended by C10): bench is out by
0.6–3.7 cm, and it agrees with itself about direction.** Horizontal rms on all
seven captures: **0.64, 0.76, 1.88, 2.63, 2.69, 2.75 and 3.67 cm**. Two of them
are inside the 1 cm spec — the first captures in this project to meet it — and
those two are also the ones that beat the null by 4×, on 5.4 and 5.6 cm of real
fore-aft travel, so it is not the flat-line artefact. Two things
follow. The magnitude says the deadlift numbers are not the whole story of P2 —
whatever dominates there is either weaker on bench or partly absent. And
`reps_disagreeing_on_sign` is **0 on 28 of 29 bench reps**, against deadlift's
4 of 6, 2 of 6 and 1 of 3, which is the sharper contrast: the fore-aft
instability P2 reports below is a deadlift phenomenon on the evidence held, not
a pipeline-wide one. The obvious suspect is the floor impact, which P6 already
locates as where three quarters of the deadlift per-rep error enters and which
bench does not have. *Read the bench numbers through
`metrics.bench_sync`'s docstring first* — hand seed, ~4% scale on every bench
distance, and a sync calibrated on deadlift rather than verified on bench.

*C8 originally reported this on three captures, because its peak-height
threshold refused the other four. C10 showed that threshold was measuring what
fraction of each clip contained lifting — bench clips are 20–30% reps against
deadlift's 50–56% — rather than how well the signals agreed. All seven sync now,
and the four it had been refusing are the better half.*

**A caution about this whole metric, found while checking C8 and applying to
every number in P2.** `vs_truth`'s horizontal rms is insensitive to gross time
misalignment. Shift a deadlift's video by a full 3 s and horizontal rms moves
5.05 → 4.62, 9.19 → 7.23, 15.44 → 15.17, while vertical explodes from
5.24/6.60/5.24 to 19.08/20.19/32.41. The fore-aft signal is a few centimetres
and looks much the same rep to rep, so mis-pairing reps barely moves it. **The
horizontal numbers are magnitude comparisons, not evidence that the reps line
up in time.** Phase evidence comes from `analysis/17` and the deadlift
lockout-containment gate. This was always true and nobody had measured it.

**A third correction, 2026-07-30: do not quote the spread.** The video's
vertical scale is wrong per capture. Per-rep video ROM on the three deadlifts is
59.1, **66.8** and **47.6 cm** against a measured 61 cm ceiling — a 19 cm spread
on a range of motion fixed by the lifter's own limbs, from footage where two of
the three captures found an identical plate radius. Plate diameter, radius
quantisation and tracker drift were each tested and each ruled out; what is left
is that the scale is calibrated on a plate resting on the floor and applied to
travel reaching the top of frame.

**That last guess was right, and C12 gives it a mechanism (2026-07-31.)** The
tracker does not merely misapply a floor-calibrated scale at the top of frame —
it *loses the plate* there entirely (see the C12 note at the top of P2). Per-rep
ROM is the highest tracked point minus the lowest, so the highest is measured
exactly where the tracker is least reliable. That explains a 19 cm spread on a
fixed anatomy better than a scale subtlety does, and it predicts the spread is
worst where lockout tracks worst. **Unproven** — unlike the three ruled-out
candidates, testing it needs footage that tracks at lockout.

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

**C28 measured the ceiling on 2026-08-04 and it is at the null.** *(This read
"branch `c28-imu-video-oracle`, not landed" until 2026-08-14. It DID land —
`d329a2a` reached `main` via `c29-jump-state` — and all three working branches
have since been deleted. Every "Branch ..." line in `TASKS.md` is provenance for
where work was done, not a place you can still check out; the commits are on
`main`.)* Every physically-named CONSTANT error
model — body-frame accel bias, world-frame tilt, accelerometer scale, the step-6
lever arm `d`, and an attitude error growing with |a| — fitted directly against
C27's marker paths, i.e. against the answer:

    model                        ceiling   leave-one-out
    baseline                      4.00          4.00
    +tilt                         2.00          4.07
    +tilt+scale+lever             1.45          4.55
    all five (15 params)          1.23          3.47

The flat-line null is 1.54-1.68 cm. **Fifteen parameters fitted on the answer
reach 1.23, and nothing transfers** — every model collapses to 3.3-4.6 under
leave-one-out and two make the held-out capture worse. So **P3's error is not a
constant in ANY frame**, and no estimator for one was going to pay off. This
also reproduces B2 independently: `lever` fits at a plausible 10.6/10.0/21.7 cm
here, unlike B2's 21/64/60, and still loses under LOO.

**C31 re-ran the whole ladder on 2026-08-06 with `lever` PINNED at the tape `d`,
and C28's conclusion SURVIVES `d` being known (70b2a63).** This was a real test,
not a formality: C28 fitted `lever` as three free parameters, so those three
degrees of freedom could have been absorbing P3 and making the family look worse
than it is. Decision rule fixed in writing first. Three `data_v2` deadlifts,
median ceiling and leave-one-out:

    rung                     arm     nfree  ceiling   LOO
    baseline                 free      0     7.22    7.22
    baseline                 PINNED    0     6.65    6.65
    bias                     free      3     2.06    6.50
    bias                     PINNED    3     2.14    5.72
    bias+tilt                free      6     2.02    6.61
    bias+tilt                PINNED    6     1.62    5.60
    bias+tilt+scale          free      9     1.80    6.36
    bias+tilt+scale          PINNED    9     1.42    5.71
    bias+tilt+scale+lever    free     12     1.29    6.59
    bias+tilt+scale+lever    PINNED    9     1.42    5.71
    ...+gravref              free     15     1.92    4.25
    ...+gravref              PINNED   12     2.16    4.34

*(These are on C27's three deadlifts and are not directly comparable to the
four-row table above, which is C28's own summary of the same experiment.)*

**Pinning PASSES the transfer test: leave-one-out improves on 4 of the 5 fitted
rungs** (6.50→5.72, 6.61→5.60, 6.36→5.71, 6.59→5.71; only `+gravref` went the
other way, 4.25→4.34). So the three `lever` degrees of freedom really were
absorbing something real, and C28's ladder was handicapped by not knowing `d`.
Pinning also removes 3 dof, so the *ceiling* could only worsen — and on two
rungs it improved anyway (2.02→1.62, 1.80→1.42).

**And the family is still dead, which is the finding.** The best LOO anywhere is
**4.25 cm**, against a `d`-only baseline of **6.65 with nothing fitted at all**
and a flat-line null of **~1.6**. Every model, pinned or free, still loses badly
to drawing no fore-aft motion. Held-out `deadlift_185x3` is destroyed by most
rungs (11–25 cm). **Knowing the lever arm makes the failure less bad; it does
not fix it. P3's error is not a constant in any frame, and that conclusion did
not depend on `d` being unknown.**

**B2 is re-confirmed rather than corroborated.** Fitting `lever` ON TOP of the
tape gives residuals of **47.9 / 17.7 / 2.4 cm** — totals 44.0 / 17.8 / 11.8 cm
at **108 / 74 / 4 degrees** from the tape. Only one capture stays near it: B2's
ill-conditioning, intact. What *does* corroborate the tape is the direction
sweep against C30's ACCELERATION correlation (optimum within one grid cell on
all three deadlifts). **The position-domain objective cannot identify `d`; the
acceleration-domain one can.** That is C30's point restated — double integration
and the detrend destroy the conditioning. Full tables in
`analysis/C31b_STATE.md`. *Evidence:* TASKS.md C31, `src/oracle.py`.

Two findings inside that negative result, both in TASKS.md C28. `calibrate.accel_bias`
subtracts a body-frame quantity in the WORLD frame, which helps deadlift on 5 of
6 and hurts bench on 10 of 11 — a mixture, exactly as C6's `anchor_tilt`
docstring says. And **two still holds can never separate the tilt leak from the
accel bias**: `R_open - R_close = R_open(I - Delta)` and the relative rotation
fixes its own axis, so the difference of two rotation matrices is always rank
<= 2, exactly. Where the holds differ by more than ~30 degrees the observable
part recovers P4's table value of 0.0245 m/s^2 — the first on-wrist measurement
of the accelerometer bias. **Three holds at different postures would close it,
which is a five-second capture change and no code.**

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

**Reordered 2026-07-31: B3 now comes first, and not for its own 2–4 cm.** B6's
splice was the attempt to fix the error upstream and it was rejected — see P6.
Two of its findings bear on B3 rather than on B6. The detrend is doing *more*
work than "hiding" suggests: replacing it with the splice's true constraint
costs 3–5×, so it is load-bearing as well as wrong, which B7 also found. And
because it is **linear**, it cannot absorb a correction localised in time — the
splice's `e·T/2` position artefact pushed vertical ROM to 82.6 cm against a
61 cm ceiling. So B3 is not just a correctness fix now; it is the thing that
unblocks every localised correction after it.

**That last sentence was measured on 2026-08-02 (C19) and it is FALSE.** The
reordering assumed the blocker was that the detrend could not *represent* a
quadratic. It can now — `correct.detrend_rep(order=2)`, pinned by the rep's own
velocity closure and needing no new anchor — and **nothing is unblocked.** Under
it the splice breaks the ROM ceiling harder, 78.1 / 70.4 / 116.4 cm, and loses
more horizontally, 16.41 / 19.27 / 24.87 against the linear detrend's
10.09 / 5.90 / 14.61. Rejected; `order` defaults to 1 and is bit-identical.

**The reason generalises and is the durable part.** B6 measured that a constant
acceleration correction cannot represent an impulse. C19 measures that a
quadratic cannot either. The obstacle was never the detrend's ORDER — any basis
smooth across the whole rep spreads a landing-localised error across the whole
rep, and raising the order raises what it spreads. What B6 needs is a detrend
**local in time**, and B3 and B6 may be one problem rather than two.

**What survives is the oracle, and it caps the family the way B6's capped
constant-bias.** The best line and the best line-plus-quadratic, fitted against
the video so that they bound every possible estimator: median over the ten
scoreable captures, shipping 2.72 cm → best line 1.04 → best quadratic 0.33,
null 2.85. Two things follow, and the split by lift is the point.

*There is real headroom, and more than this file has claimed* — B3 has been
described as worth 2–4 cm and the linear family alone holds ~10 cm on the worst
capture, `deadlift_180x3` going 15.44 → 4.89. Today's endpoint line is simply
not the best line.

*But it is a BENCH result, not a P2 fix.* On bench the best quadratic reaches
0.25–0.55 cm, inside spec. On deadlift the best **line** is 3.64 / 3.78 / 4.89
against nulls of 3.55 / 3.23 / 1.96 — **no per-rep line, however estimated,
beats a flat vertical line on any deadlift** — and the best quadratic only just
does. Per-rep polynomial detrending cannot bring deadlift near spec, whoever
writes the estimator. *Evidence:* `analysis/38`, `python run.py --b3oracle`,
TASKS.md B3, `tests/test_real_data.py`.

**P6 — The floor impact is trustworthy, INFORMATIVE, and misspent by every
correction tried.** Closed as a worry by B5, opened as an opportunity, and
sharpened by C28b on 2026-08-05.

**EVERY NUMBER IN P6, INCLUDING C28b's r = 0.772 AND C29's 10.66 → 3.93, WAS
MEASURED WITH STEP 6 OFF (C33, 2026-08-06).** `d` was not known when any of it
was run, and it is the term that recovers most of the deadlift horizontal
ACCELERATION channel (see P2). **Nobody has re-run C28b or C29 with `d` applied,
so it is not known whether the two compose or correct the same thing twice** —
that is the highest-priority open item in `analysis/C31b_STATE.md` (item B).
Until it is done, read this section as measured on the watch path.

**C28b measured what the impact actually tells you about the horizontal, and
the answer is: a lot.** At a rest instant the bar's true velocity is zero, so
the reconstruction's velocity there IS its velocity error — readable without
the video, from `segment.rest_instants`, which is placed on raw acceleration
and gyro alone. The reconstruction claims **0.17-1.28 m/s of horizontal
velocity at moments the bar is provably still**, and over 20 rest-to-rest
intervals on all six deadlifts that observable predicts the per-rep horizontal
error at **r = +0.772**, partial +0.472 controlling for interval length. The
reverse does not hold — span predicts nothing once you know it (+0.184) — and
the VERTICAL velocity error is a clean negative control at -0.254.

**And using it still loses.** The minimal correction it licenses, a constant
horizontal acceleration per interval sized to zero the observed velocity change
and with zero free parameters, is worse on 4 of 6: median 8.21 -> 8.99 cm.

**The two together are the finding, and it is the fourth instance of one
pattern.** B7 anchored position at the impacts, B6 spliced velocity across them,
C19 raised the detrend to a quadratic, C28b applied a constant per interval —
all four lost, and all four impose a correction SMOOTH ACROSS THE REP where B6
measured the error to be LOCALISED AT THE LANDING. C19 generalised half of this
(the obstacle is not the detrend's order); C28b extends it past step 7 to every
correction anyone has applied. **The bottleneck is the correction's shape in
time, not the measurement.**

*For anyone reaching for a Kalman filter:* a random-walk bias state distributes
its correction smoothly by construction and would reproduce this exactly. C28b
pointed at a jump state AT the impact instead — **and C29 built it, on
2026-08-05, and it is ANNIHILATED BY CONSTRUCTION.**

`segment.rep_bounds` ends every rep at a floor impact, so a velocity error that
steps at the impact is constant within each rep, its position error is linear in
t, and `correct.detrend_rep` removes a line. **The correction lands exactly in
the detrend's null space** — gated as algebra, not measured. Widening the window
to the [impact -> rest] span looks like a 16% win per capture and is regression
to the mean: per rep it improves 10 of 20, the median gets worse, and the
baseline SCREENS OFF the observable (partial +0.184 for the observable against
+0.272 for the baseline), which is the exact inverse of C28b's structure.

**C29 THEN FIXED IT, and both changes are needed.** Keep step 7's machinery —
independent endpoint lines — and move its windows to rest-to-rest so the impact
falls INSIDE a window as a kink rather than at its edge as a slope. Measured on
all six deadlifts, correcting all three axes, against the control that moves the
windows and applies no correction:

    arm                              h rms   beats_null   v rms
    SHIPPING (impact windows)         8.21      0.29       4.90
    rest windows, NO correction      10.66      0.21      11.92   <- CONTROL
    rest windows + 0.20 s             3.93      0.69       3.22

**Moving the windows alone is WORSE than shipping, and the correction alone is
annihilated. Only together do they work.** All six captures improve;
`deadlift_155x6_1` and `deadlift_180x3` cross `beats_null = 1.0` for the first
time in this project. The window width is a broad plateau 0.10-0.50 s, which is
where B6 independently measured the strap ringing.

**It improves TRACKING, not invented travel, and that is the qualification that
matters.** Per-rep fore-aft excursion, median: video 7.2 cm, shipping 12.4,
fixed **14.4**. On the three marker-refereed captures alone, video 5.4, shipping
14.4, fixed 13.8. So the path follows the video's shape and timing far better
point-for-point while still sweeping ~2.5x the fore-aft range the bar really
moved through. `h_rms` improves on 6 of 6; excursion on only 3 of 6.

**Read the caveats before quoting it.** Dropping the first and last rep from
SHIPPING too puts it at 7.05 rather than 8.21, so the like-for-like gain is
7.05 -> 3.93. Zero reps are under 1 cm in either arm. The rest-window frame
scores 19 of 30 reps — so the honest
number is the frame-internal 10.66 -> 3.93, NOT 8.21 -> 3.93. Deadlift-only,
six captures, and 0.70 median `beats_null` is still below a flat line. A large
step, not an arrival. Nothing is proposed for the pipeline yet.

**THE CAUSE OF THAT REP LOSS WAS MISDIAGNOSED HERE, AND THE LARGER HALF IS
FIXABLE (H22, 2026-08-19).** This sentence read "`rest_instants` rejects the
final impact of each set", naming ONE cause. There are two, and the one it named
is the smaller:

* **The missing FIRST boundary.** `rest_instants` answers "when did the bar come
  to rest AFTER each landing", so n impacts give n rest instants and
  `oracle.rest_windows` pairs them into **n-1** windows — rep 1 of every set is
  never inside one. **This is fixable and H22 fixed it.** `oracle.prepull_rest`
  finds the quietest sample in the 3 s before the first pull, on the same raw
  accel-plus-gyro score, and on **9 of 9** deadlifts it is quieter than every
  post-impact rest that frame already uses (0.04-0.71 against 0.17-7.15).
  Prepending it is exactly additive, gated bit-identical on every later window.
* **The final rep, which is NOT fixable** and is the half this sentence named.
  The lifter releases the bar, so no rest-to-rest window can close on the last
  rep. Three independent detectors agree. That is a property of the lift.

Coverage goes 23 of 36 -> 31 of 36 on today's corpus. **Read what it costs**:
the recovered rep 1 is the hardest window in the set on 4 of 6, so part of
C29's headline was a COVERAGE effect — 2.00 -> 2.77 cm, bought back to 2.14 by
averaging the velocity correction over the still period rather than taking it at
the instant. The gain over shipping is smaller than C29 looked (2.78 -> 2.14)
and it is now like-for-like, because the null inflation goes 1.28x -> 0.97x.
*Evidence:* `analysis/72`, TASKS.md H22, `oracle.jump_period_windows`.

**AND THE OWNER HAS NOW RULED THE WHOLE FRAME OUT (H23, 2026-08-19): "do not
lose the last rep of every set, again this is unacceptable."** So C29 and
`jump_period_windows` are closed as SHIPPING candidates, though not as
measurements — their evidence stands and they remain the sharpest deadlift
result here. The last rep is the half that cannot be recovered: a rest-to-rest
window must close on a moment when the bar is at rest AND the watch is still
indexed to it, and after the final rep the lifter releases the bar. A property
of the lift, not of the code.

**There are now THREE requirements on any deadlift correction, where this file
recorded two.** Local in time (B6, C19, C28b each failed this); boundaries not
on the impacts, or step 7 annihilates it (C29's discovery); and **new: it must
cover every rep** — a correction that improves the median by dropping the reps
it cannot handle is not a correction. H22's honest accounting is what made the
third visible, by reporting the null inflation rep-dropping causes: C29 looked
like `beats_null` 0.68 -> 0.95 and was 0.68 -> 0.84 once coverage was paid for.

*Not ruled out, and nobody has tried it:* requirement 2 is about where the
detrend's BOUNDARIES sit and requirement 3 is about which samples are COVERED.
Nothing says one implies the other — a detrend whose knots move off the impacts
while every rep stays covered would satisfy both. See TASKS.md H23.

*And one thing the failed first attempt taught:* a CONTINUOUS piecewise-linear
detrend cost 8.21 -> 17.00 with ROM at 70-138 cm. Step 7 is load-bearing because
of its per-rep INDEPENDENCE — two free parameters per rep, no continuity — not
because of the closure. That had never been named.

**The bind part 1 established, which the fix confirms by escaping it:** "Use the impact,
the one externally true instant" and "close each rep with a line whose
boundaries are the impacts" are not merely hard to combine — any correction
localised at the boundary is invisible to what follows it. B7's ablation already
showed the detrend cannot just be dropped (error goes to 3-5 m). So the
remaining move is a detrend whose BOUNDARIES do not sit on the impacts, or a
constraint that replaces closure entirely. Nothing has tried that. Five
corrections have now failed: B7, B6, C19, C28b, C29. *Evidence:* TASKS.md C29,
`analysis/44`. A smoother is the right
class of tool; the default process model is the wrong instance of it. And a
filter inherits C28's observability limit rather than escaping it — adding
states does not create observability. It is also deadlift-only and always will
be: bench and squat have no raw-signal rest anchor and cannot be given one.
*Evidence:* TASKS.md C28b, `oracle.rest_observables`, `oracle.impact_correction`.


The worries were saturation and lost impulse, and neither survived measurement.
Nothing in `data/raw/` clips — `deadlift_180x3`'s 21.78 g peak is a genuine
reading, hit by one sample, not a rail. And the impulse survives 100 Hz despite
the event spanning 2–3 samples: the IMU/video velocity-step ratio is median
**1.04** over 15 impacts. `analysis/20`.

So the impact is the one place in this pipeline where the IMU demonstrably
agrees with external truth — 13.5 ms on timing, ~1.0 on the velocity step — and
the pipeline spends it entirely on segmentation. The bar's state there is
*known*: velocity zero, height at plate radius. It is the only externally true
constraint available; step 7's closure is an assumption by comparison.

**Spending it has now been tried twice and failed twice, and the second failure
explains the first.** B7 anchored position at the impacts and lost. B6's splice
removed the velocity error across the impact window and lost too — even though
it *worked*, taking the vertical momentum deficit to −0.05 m/s. The common
reason: **the impact is one instant per rep, and the detrend it would replace
constrains position across the whole rep. A sparse true constraint does not
substitute for a dense false one.** Row 4 of B6's table is the direct test —
splice everything, close vertical only — and it gives 28.5/18.0/61.4 cm against
shipping's 5.05/9.19/15.44.

And any correction localised in time now has a second obstacle to clear:
removing an error `e` over a window `T` injects about `e·T/2` of position, and
step 7's detrend is **linear**, so it cannot remove a quadratic. The splice
pushed per-rep vertical ROM to 82.6 cm against a 61 cm physical ceiling. **B6 is
blocked on B3.** *Corrected 2026-08-02 (C19): it is not.* B3 built the
quadratic detrend this asked for and the splice got WORSE under it, not better
(ROM 78.1 / 70.4 / 116.4 cm). Raising the order does not help, because a
quadratic spreads a landing-localised error just as a constant does. B6 needs a
correction **local in time**, not a higher-order detrend to clean up after a
global one. See P3. *Evidence:* `analysis/32`, `38`, `python run.py --splice`,
`tests/test_real_data.py`.

One capture dissents. `deadlift_180x3` over-reads its impact step by 58–72%,
alone among the three, and is also the worst by horizontal error. Heaviest bar,
hardest landing — probably strap ring. That was tracked as #14, whose detector
has since been REMOVED: it could not see the phenomenon and never could. The
suspicion about this capture stands; the flag that was going to confirm it does
not exist. See #14 in TASKS.md.

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

**And vertical momentum does not close.** Measured between
`segment.rest_instants`, which are validated against video at |v| < 0.10 m/s so
the bar really is at rest at both ends: ∫a_z dt between them must be zero and is
**−0.37 to −1.48 m/s, negative on 8 of 9 intervals**. The reconstruction loses
about a metre per second of upward impulse every rep, on the axis this project
has assumed was fine.

*Corrected 2026-07-30, later the same day.* This first read −0.05 to −2.36 m/s
on 15 of 15, measured over impact-to-impact rep windows. Those are the wrong
windows: every rep boundary sits exactly 10 ms after its impact, one sample into
a 2–3 sample spike, so part of one impulse falls outside and the number inherits
the boundary placement. The defect and its direction survive; the range
overstated it.

This does not contradict B5's 1.04. That ratio is the velocity STEP measured
locally across the impact against video, over a few hundred milliseconds, and it
is right. C11 below states exactly why the two coexist — B5's is an AMPLITUDE
and this is a NET — which is sharper than "local versus global" and is what
tells B6 what to preserve. Step 7's detrend hides the deficit completely, which
is why vertical ROM comes out at a plausible 53–61 cm either way, and it is the
sharpest available statement of why "the detrend is carrying vertical entirely".

**C11 closed the attribution on 2026-07-31: the deficit is the landing, and
only the landing.** The measurement is an identity — between two moments the
video says the bar was still, the integral of vertical acceleration must be
zero — with nothing tunable in it, and it is immune to the video's per-capture
vertical scale error because a scale cannot move a zero crossing.

    bench, real lifting                   44 intervals   median -0.013  worst 0.102
    deadlift, floor->lockout (the pull)    8 intervals   median -0.010  worst 0.063
    deadlift, interval with a landing      9 intervals   median -0.589  worst -1.428

**The middle row is the strongest and the least obvious.** Those are 55-66 cm
loaded pulls *from the same captures as the failing row* — the dwell detector
splits a deadlift rep at the lockout, so the concentric and the
descent-plus-landing are separate intervals of the same thirty seconds of tape.
Same lift, load, wrist and calibration; only the landing differs. Bench then
confirms it independently, on a lift with no landing anywhere in it. As residual
acceleration: 0.0019 g and 0.0008 g against 0.0300 g, the first two being the
0.0025 g measured on a table.

*Do not judge these intervals by peak acceleration.* A 155 kg pull leaves the
wrist's total |accel| at 0.6-1.1 g, indistinguishable from resting — reading
that number is how these were twice mistaken for the bar sitting on the floor.

**This reconciles with B5 rather than contradicting it, and the distinction is
what B6 needs.** B5's velocity-step ratio of 1.04 is min-to-max AMPLITUDE within
±0.3 s, and its docstring warns off net-change windows. C11 measures the NET,
which is what the closure identity constrains. Both on the same 15 impacts:
amplitude 1.10, net 0.41. **The spike's size is captured; where the velocity
settles afterwards is not.** So a fix must preserve the amplitude B5 measured
while correcting the settling point — which is another reason a constant bias
cannot do it. *Evidence:* `metrics.momentum_closure`, `analysis/31`,
`python run.py --closure`, gated in `tests/test_real_data.py`.

**B6 then found where the deficit is injected, and it is not distributed.**
Cumulative vertical velocity across a rest-to-rest interval is smooth and
physical through the pull and the descent, then rings violently for several
hundred milliseconds at the floor impact and settles short. The ringing is the
watch still moving when the bar has stopped — strap compliance. That pointed at
#14, and #14 turned out to be undetectable: the post-impact spectrum has no
repeatable peak (10-47.5 Hz across 15 impacts, peak/median 2.7-12.5) and Nyquist
here is 50 Hz, so a watch-on-strap resonance aliases to an arbitrary bin. The
ringing is real and is where the error enters; it is simply not resolvable as a
resonance at 100 Hz, and rejecting the rep was never the right response. The fix
belongs in the reconstruction. **Every
constant-bias correction tried against this makes it worse**, because a constant
cannot represent an impulse: see P3 and `analysis/25`.
*Evidence:* `analysis/24` and `25`, gated in `tests/test_real_data.py`.

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

*Wrong projection.* The 0.035 g is a **vertical** residual, and a tilt θ leaks
g·sin(θ) into horizontal but only g·(1−cos θ) into vertical — see `orient.py`'s
docstring. Converting a vertical number with the horizontal formula is what
produced "2 degrees"; done correctly it needs **15.2°**.

*Wrong number.* That 0.035 g predates the acceleration sign fix (`3c2cbed`) and
does not survive it. The capture it was measured on now reads **0.0005 g**.

*And measured directly:* attitude at a still hold is 0.05°/0.14° (P5), which
excludes 15° by two orders of magnitude and 2° with it.

So P3 is **not** redirected at attitude. What survives is that its error is real,
sits at rep frequency, and now has a location: see P6. *Evidence:*
`stationary_table_20260730`, `analysis/24`, TASKS.md C6.

The original framing, still true as far as it goes: the "stillest" window
carries 7.2 °/s peak-to-peak of ~6.5 Hz physiological tremor; the bias being
extracted from it is 0.1–0.9 °/s. Block-resampled standard error of the mean
is 0.16–0.36 °/s, and the observed spread was 0.33–0.47 °/s across the 13
captures held when this was measured — meaning the capture-to-capture variation
is tremor, not bias. More captures will not help; the estimator is the limit.

**P5 — CLOSED 2026-07-30. Apple's residual gyro bias is unobservable, and
also negligible.** Both halves matter, and they arrived from opposite
directions.

*Unobservable:* **`CMMotionManager.isGyroAvailable` returns false on watchOS**,
so raw `CMGyroData` cannot be logged alongside the already-corrected
`dm.rotationRate`. Tried on one motion manager and on two. There is no
public-API route — **do not re-propose this.**

*Negligible:* P4's stationary captures put the residual *after* Core Motion at
**0.002 °/s**, unresolvable above its own noise. There was never much for the
internal estimate to explain.

**What replaced it: does attitude survive a working set?** Everything above was
measured at rest. C6 answered it on 2026-07-30 and **a set does no lasting
damage** — across all seven captures with both holds, attitude error at a still
hold bounds at **0.05° opening, 0.14° closing**, worst case 0.27°, over 39–56 s
of loaded lifting, while the logged gyro propagated alone drifts 0.35–1.49°.
Core Motion's fusion is winning, through the impacts rather than despite them.

**Read those as upper bounds, and do not read the change between them at all.**
The world-frame residual is the tilt leak plus the body-frame accel bias rotated
into the world, and the watch's posture differs at the two anchors. Decisively:
0.0025 g of accel bias is g·sin(0.143°), the closing-anchor median itself. "It
degraded from 0.05 to 0.14 across the set" was claimed here in error.

**This measures two of three attitude degrees of freedom.** Gravity constrains
roll and pitch, not yaw, and the logger requests `.xArbitraryZVertical`, so no
absolute yaw reference exists in the system. Yaw is bounded only indirectly, by
gyro-vs-Core-Motion divergence of 0.0–1.4° per set — enough to close it, since
1.4° moves a point on a 10 cm excursion by 2.4 mm, under spec and nothing like
the 180° disagreement P2 reports on fore-aft sign.

Two things follow, the second mattering more. *B1's default is confirmed on the
evidence `calibrate.py`'s docstring asked for:* the implied drift is 0.69° over
~50 s ≈ **0.014 °/s** against a pause estimate of 0.1–0.9. Never apply it. And
*C1 cannot see P3's error, by construction* — the anchors sample attitude at the
two moments it is most likely to be right, still and unaccelerated, while P3
lives DURING the rep. What sees it is the per-rep mean: bench and squat leave
**0.003 g**, deadlift **0.010–0.030 g**. See P6.

*Evidence:* `analysis/24`, `calibrate.anchor_tilt`, TASKS.md C6 for the full
derivation of the bounds and the posture argument behind them.

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

**Bench then went further, on 2026-07-31 (C8), and the qualifications matter
more than the headline.** It has real video truth now: horizontal error of 3.67,
2.69 and 2.63 cm rms per rep. But rank it below deadlift deliberately, on three
counts. The seed is placed by hand and its radius *is* the pixels-to-metres
scale, so every bench distance carries ~4% that nothing checks. Only 3 of 7
captures have an identified clock sync. And that sync is a cross-correlation
whose accuracy was measured on **deadlift** — where it recovers a known offset
to 18 ms — and then assumed to hold on bench, which no bench capture can
currently test. It is a referee; it is not the referee deadlift is.

**This used to end "squat is now the only lift with no external horizontal
check, and its footage got worse rather than better: two of the four 2026-07-30
captures do not track at all; `metrics.vs_truth` refuses it; that wants a wider
shot, not code." It got the wider shot, and it is FALSE as of 2026-08-06
(C31).** The four `data_v2` squats are filmed from a tripod on an 8-sticker
plate and **two of the four clips track cleanly** (100% coverage, 0.69-0.88 px,
travel 59-60 cm against a ~65-70 cm squat) while **two do not** — `squat_170x1`
and `squat_pause_140x4_3` report 14.0 and 24.7 cm of travel, which is not the
bar. It was the shot, largely as predicted, and the prediction is the part worth
keeping; the over-claim that all four track was C31's and is corrected here
(2026-08-07).

What remained true was narrower and was a code problem rather than a footage
one: `metrics.vs_truth` refused squat by a hardcoded check whose stated reason
described the old `data/video/` template footage and not `data_v2/`.

**That is closed (G2, 2026-08-15).** The refusal is removed, squat scores
h 1.88–2.97 cm with all three paused captures beating the flat-line null, and
the sync it rests on is corroborated by a landmark the correlation cannot see —
`metrics.pause_landmark`. The two objections this paragraph raised were
answered rather than waived: `bench_sync` is no longer unvalidated on squat
(the landmark agrees to 0.003–0.036 of a rep on the three), and the phase
anchor squat lacked is the bottom dwell itself. Full numbers at the top of P2.
