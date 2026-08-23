# barpath

Reconstruct barbell path from a single Apple Watch IMU and render it as an
overlaid 2D plot. Proof of concept only — not an app, not a product.

**This file holds the working protocols and nothing else.** It is loaded into
every session's context, so anything that is a *finding* rather than a *rule*
lives elsewhere. Three documents, three jobs:

| file | holds | read it |
|---|---|---|
| `CLAUDE.md` | the protocols. How to work here, what the pipeline is, what the spec is. | always |
| `FINDINGS.md` | **what works and what does not**, one entry per mechanism, with the number that decided it. | before proposing anything measurable |
| `TASKS.md` | what is open right now, and the capture protocol. | before choosing what to do |

`analysis/README.md` captions every figure; `src/README.md` covers the video
referee in depth. Derivations live in the docstring of the code they justify,
not in a document beside it.

**`NON_GOALS.md` and `HANDOFF.md` were DELETED on 2026-08-23 (H32), on the
owner's instruction, and nothing replaces them.** `NON_GOALS.md`'s Scope section
had been binding and is not any more: front/lateral rendering, on-watch
processing, ML, accounts and backends are no longer forbidden, they are simply
not what anyone is working on — and the one-line framing at the top of this file
(*proof of concept, not an app, not a product*) is the whole of the scope now.
The owner's reason was that the file was throttling rather than protecting. If
you want the old tables, `git show fa7588d:NON_GOALS.md`.

**A claim in this file that you cannot find evidence for is a bug.** Every rule
below either states an obligation or cites `FINDINGS.md` for why it exists.

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
- **Claim the shared docs late and briefly.** `CLAUDE.md`, `FINDINGS.md`,
  `TASKS.md`, `README.md`, `analysis/README.md` and `src/README.md` are touched
  by nearly every task, so an agent holding them for the length of its work
  blocks everyone. Do the code and the measurement under a narrow claim, then
  take the docs in a short window at the end and release them straight after.
  This does not weaken the same-commit docs rule below: it still requires the
  docs in the same commit, it just does not require holding them throughout.
- **Reserve `analysis/NN_*.png` numbers by claiming the filename** before you
  generate it. Two agents will otherwise both take the next free number.
- **`data_v2/raw/` is read-only for everyone**, so it never needs claiming, and
  a claim on it should be refused.
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

Nine steps, one module each, numbered to match. This is what the code does; why
each step is shaped the way it is, and what was tried instead, is in
`FINDINGS.md`.

0. `io.py` — load log. Never assume fixed dt. Core Motion reports g, not m/s².
   Captures from 2026-07-30 on carry a `phase` column (0 opening hold, 1 reps,
   2 closing hold) — use it rather than searching for stillness where it exists.
1. `calibrate.py` — gyro bias from the stillest window in the pre-set pause.
   **Not applied by default** (B1): there is essentially no bias to remove, and
   applying the pause estimate was worse on 13 of 13 captures.
2. `orient.py` — correct attitude by that bias.
3. `orient.py` — rotate acceleration into the world frame.
4. `integrate.py` — cumulative trapezoidal, twice.
5. `segment.py` — stationary detection, then rep boundaries by vertical position.
   **Split by lift class**: deadlift segments on `impact_anchors` from raw
   acceleration, smooth lifts on integrated velocity.
5b. `correct.fit_drift_tilt` — a world-horizontal attitude drift rate, fitted
   against the set's own rep-to-rep dispersion, then applied back at step 2-3
   and steps 3-4 re-run. **ON as of 2026-08-16 (H8).** Numbered 5b because it
   corrects the ATTITUDE but needs rep windows to fit, so it cannot precede
   step 5. Not gated on the lift: it is self-limiting, finding |beta| of
   0.001-0.008 deg/s on bench and squat against 0.008-0.051 on deadlift.
6. `correct.py` — subtract the wrist-to-bar offset R(t)·d. **ON as of
   2026-08-06.** See *Reading a number* below before quoting anything measured
   before that date.
7. `correct.py` — per-rep detrend. Linear on every lift; **plus a quadratic
   term on BENCH, fore-aft only, as of 2026-08-25 (H40)** — see
   `correct.QUAD_LIFTS`. C19 built the same quadratic, applied it to all three
   axes, and was right to reject it there: a deadlift's `dv` is a landing
   impulse and spreading it wrecks the vertical and the ROM. The axis
   restriction is what is new, not the term. Bench 1.81 -> 1.53 cm
   leave-one-capture-out and 6 of 7 -> 7 of 7 beating the null; squat and
   deadlift are bit-identical to the linear detrend and gated as such.
   **Load-bearing because of its per-rep INDEPENDENCE, not its closure** — two
   free parameters per rep with no continuity between them. Making it
   continuous costs 8.21 -> 17.00 cm.

   **It is a DRIFT REMOVER, and "reps start and end in the same place" is not
   why it is there.** That sentence is false and was never load-bearing:
   measured 2026-08-23 over 111 refereed reps, the real bar misses closing
   horizontally by a median of 1.61 cm and only a third of reps close inside
   the 1 cm spec. Keep the operation and drop the belief. What justifies the
   operation is that **97-100% of what it removes is integration drift** —
   50-454 cm of it per rep against 1.4-1.8 cm of real motion — and that an
   oracle given the true non-closure gains nothing (-0.18 cm corpus-wide,
   better on 50% of reps). So do not "fix" the closure assumption, and do not
   cite closure as the reason for the step. The error it leaves behind is a
   BULGE at mid-rep, not a misplaced endpoint; see `FINDINGS.md` P3.
8. `project.py` — the display axis comes from the ATTITUDE (H9), via
   `anatomical_axis`: the hand is clamped to the bar, so fore-aft is a fixed
   direction in watch coordinates and one angle (`BAR_ANGLE_DEG`) fixes it. PCA
   on horizontal displacement is still computed and still supplies `ratio` and
   `excursion` for `confidence`, but it is no longer the axis. The SIGN comes
   from `FORE_AFT_SENSE` (B4). **One step of that derivation has evidence
   against it** — see P2 and `FINDINGS.md` H15 before relying on the sign.
9. `plot.py` — overlay reps, aligned by start point, horizontal stretched 4x.

**Step 10, which is not a step:** `display.py`, the product view (H13). A layer
*after* step 9 that returns curves to draw — a smoothed path, a speed to colour
it by, one average rep with the odd one labelled. It touches no reconstruction
module and moved no shipped number. Defaults: `savgol` at `strength = 0.20`,
`turnaround` alignment, `median` averaging. The one rule to carry: **the odd rep
ships as a LABEL, never as a deletion** — excluding it makes the average worse,
because it is usually a real rep. Evidence in `FINDINGS.md`, "What works".

**`metrics.py` is not one of the steps. It judges them:** `dispersion` for
rep-to-rep spread, `vs_truth` for absolute error against the video. Read its
module docstring before quoting a number from it — `dispersion` needs no truth
and is blind to exactly the error that dominates, so the two are not
interchangeable. Quote `beats_null` alongside any horizontal number.

### Two classes of lift: IMPACT and SMOOTH

The owner's framing, and it is sound. **Deadlift is an IMPACT lift — the bar is
dropped to the floor between reps. Bench and squat are SMOOTH.** Both classes
run the same nine steps; impact lifts need supplementary ones, and two steps'
premises break on impact:

- **6 `apply_offset`** assumes `d` is rigid in body coordinates, which fails
  during strap ringing.
- **7 `detrend`** is the real fault line. Nearly adequate on smooth lifts;
  on impact lifts **no per-rep line beats the flat-line null on any deadlift**,
  whoever estimates it.

The sharpest statement of the split is `beats_null` against the video: **bench
beats the flat-line null on 6 of 7, squat on 9 of 10, deadlift on 1 of 10** —
and that one is a single, so every multi-rep deadlift loses. *(29-capture
corpus, H17. The per-rep excursion-growth statistic this split used to be quoted
for no longer separates the classes, because step 5b fixes what it measured —
H18.)* Evidence, and the corrections it has been through, in `FINDINGS.md`
Part 5.

### The video referee, and the tracking protocol

**There is one video referee: `src/vtrack/`.** `metrics.TRACKERS` is
`("vtrack",)`; `markers.py` and `truth.py` are both deleted and nothing scored
under them can be re-run.

**The moment a video is supplied: track it, cache the path to CSV beside the
capture, and render a review figure. Then LOOK at the figure.** `src/tracked.py`,
`python run.py --track`. Figures land in `analysis/tracking/v2` — the "v2" names
the CORPUS `data_v2/`, not a tracker. The CSVs are committed, so a clip is
tracked once for the life of the repo.

**The figures are NOT committed, as of 2026-08-23 — `analysis/tracking/` is
gitignored.** They regenerate from the cached CSVs in seconds and nothing reads
them back, so committing them cost forty PNGs of churn on every tracker change
for no recoverable information. This changes the storage and not the protocol:
render the figure and look at it, every time.

Looking is the half that matters. Six squat clips once fed travel figures of 0.2
to 24.7 cm — for 65-70 cm squats — into comparisons behind coverage of 96-100%
and healthy residuals, because the tracker had locked onto gym furniture (D2).
Every summary statistic said fine. `tracked.review` flags `implausible` when
whole-clip travel falls below the lift's own `VERTICAL_ROM_M`, and the figure
shows a path no human would mistake for a barbell.

**Two costs of reading the cache, both real.** The CSV carries per-frame arrays
and scalars but **not** the tracker's own diagnostics, and **a cached read does
not run `vtrack.validate`, so its per-capture warnings do not fire** — notably
`implausible`. Use `resolve_path(use_cache=False)` or `run.py --track --force`
when you want the tracker to speak up, and after ANY change under `src/vtrack/`
or to `capture.py`, because a cached path is only valid for the tracker code
that produced it. *`--force` did not actually re-track until 2026-08-17 (H14),
so if you are re-reading an old result that depended on a re-track, check the
date.*

**`pipeline.find_video` returns `None` for six captures whose `.mov` is no
longer on disk** (noticed 2026-08-20). All six still score, because the tracked
path is cached and committed — so anything iterating the corpus should pair
through `data_v2/tracked/` rather than through the video. `analysis/78_set_paths.py`
shows the pattern.

## Reading a number

Seven standing facts. A figure that predates one of them is measuring a
different quantity. `FINDINGS.md` mostly does **not** cross out the superseded
figure — it records it beside the new one, because what was believed and why it
was wrong is the record this project runs on. **So check the date before you
quote, and say which side of the change you are on.**

1. **Step 6 is ON (2026-08-06).** Every horizontal and vertical figure taken
   before that scores the reconstructed **watch** path, not the bar.
   `pipeline.run(wrist_offset="auto")` looks `d` up by lift. To reproduce an old
   number you must pass `wrist_offset=None`, or you are comparing two different
   quantities.
2. **The video referee's absolute scale changed (H14, 2026-08-17):** +4.9%
   bench, +6.1% deadlift, +11.4% squat. It cut the median vertical error against
   video from 3.92 to 2.71 cm and left the horizontal alone. Every metre figure
   measured against video before that date is on the old ruler.
3. **The v1 corpus was deleted (F1, 2026-08-14)** — `data/raw/`, `data/video/`,
   `data/synthetic/` and `truth.py`. Findings measured on it **cannot be
   re-derived**, so they cannot referee a change.
4. **One referee, `src/vtrack/` (H21, 2026-08-19).** Nothing scored under
   `markers.py` or `truth.py` can be re-run.
5. **The corpus is 36 captures (2026-08-20), and nearly every corpus-wide median
   in the docs is the 29-capture figure** from 2026-08-17. Nothing has been
   re-measured on 36.
6. **`deadlift_160x6_1_20260818` was captured wearing lifting straps and should
   referee nothing.** The watch moved, and it invents 19.9-27.9 cm of per-rep
   fore-aft where its own unstrapped same-day twin invents 5.4-7.7 and the bar
   really moved 4.4-6.0. Nothing in the repo marks it — **exclude it by hand and
   say so.** Whether to exclude it in code is the owner's open decision, because
   it changes what every corpus median means.
7. **Check a `run.py` command exists before quoting it as reproduction.** Five
   cited in these docs no longer do; `run.py` carries a `FLAGS` table and a
   `RETIRED` table and refuses both cases by name. Until 2026-08-20 typing a
   retired one silently ran the whole corpus and looked like it had worked.

### The one measured constant you should not re-fit

`correct.WRIST_OFFSET_M`, the wrist-to-bar offset `d`, tape-measured by the
owner on 2026-08-06 — watch-face centre to bar centre, in watch body axes:

    squat            5 cm toward the crown, 4 cm UP OUT of the case    |d| = 6.4 cm
    bench, deadlift  9 cm toward the crown, 3 cm DOWN INTO the case    |d| = 9.5 cm

`apply_offset` computes `p_bar = p_watch − R(t)·d`, so **its `d` points
BAR→WATCH and is the negative of what the tape reads from the watch**; a sign
error here is invisible, since it produces a plausible curve of the right size
pointing the wrong way. **`d` cannot be fitted from the video** — B2 established
it and C31 re-confirmed it twice. Do not re-open the fit.

## Conventions

- SI internally. Convert Core Motion's units of g at the I/O boundary, once.
- World frame: x, y horizontal (heading unknown until step 8), z up.
- Attitude quaternions stored **w, x, y, z**. SciPy uses x, y, z, w — convert
  at every boundary. This has bitten before.
- Use the per-sample `dt` array. The watch does not always honour the
  requested rate, and a baked-in interval is an invisible scale error.
- **`data_v2/raw/` is immutable, gitignored, and the only corpus left.**
  Re-deriving from raw is trivial; re-collecting from a gym is not. `data/` no
  longer exists — v1 went on 2026-08-14 and its 17 labelled captures are
  unrecoverable, which is why this rule now has more force than when it was
  written for them.

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
  licence to keep rejections alive past their evidence: the old non-goals file
  lost its Estimation and Sensing tables on 2026-07-28 for exactly that reason,
  and lost the rest of itself on 2026-08-23.
- **"No caller" is not the same as "dead". Before deleting something with no
  callers, ask which rule stops being reproducible.** `src/oracle.py` is the
  standing counter-example (H28): `src/` imports it nowhere, so nothing in it
  can reach the bar path, and everything in it was built to be rejected — so
  unused is its normal state. What it buys is that a dozen claims in these docs
  are **re-runnable** rather than merely written down, which is the property
  the deleted non-goals file lost. The real risk is the opposite one, a claim
  whose driver has quietly rotted, and the answer to that is a gate, not a
  deletion.
- When a concept or bug is hard to see in numbers, **plot the data**. A graph
  of the intermediate signal — per-rep overlays, drift vs signal, before/after
  a stage — routinely makes clear in seconds what a table of numbers hides. The
  owner is learning the domain, so reach for a plot at troublesome spots rather
  than only explaining in prose. Render to the scratchpad and view it.
- **A change is not finished until every document it falsifies is fixed, in the
  same commit.** The docstring is part of the diff, not a follow-up. This is not
  tidiness: the failure that costs time here is a claim that outlives its
  evidence, and the claim is usually in prose. Milestones 1–6 passed on gates
  that no longer tested anything; the old non-goals file kept rejections whose
  evidence had expired; the reserved-module banners survived the lockout being lifted by
  a day and the disproved `correct.py` premises by longer. When you change
  behaviour or learn a fact, grep for what now reads false — module docstrings
  first, then `CLAUDE.md`, `FINDINGS.md`, `TASKS.md`, `README.md`,
  `analysis/README.md`, `src/README.md`, `watch/README.md`, test docstrings. Correct the old reasoning
  rather than deleting it; what was believed and why it was wrong is the record
  this project runs on.
- **`FINDINGS.md` is a VERDICT LIST and updating it is part of the change, not
  a follow-up.** If your work established that something works, or that it does
  not, the entry goes in the same commit. Three rules on how, because the file
  reached 9,407 lines by ignoring them:
  - **Rewrite the entry, do not append to it.** State the finding once, in the
    present tense, and say in a sentence what it replaced. A verdict with four
    dated qualifications stacked under it is a verdict nobody can read.
  - **No dated task entries.** `### H28 — ... (2026-08-20)` is a diary; the
    chronology is in `git log`, which is better at it. What belongs here is
    *what is true now and what it cost*.
  - **Derivations go in the docstring of the code they justify**, not in
    `FINDINGS.md` and not in a document beside it. The verdict is the finding;
    the working is where the reader of that function will look for it.

  `tests/test_docs.py` gates the shape of this mechanically — no diary headers,
  a line budget, the load-bearing sections still present, no pointers at
  deleted files, and no `src/` module missing from the prose. **The rule alone
  was not enough** — it is a good rule, it is followed most of the time, and
  what it produced was documentation that was correct until somebody was in a
  hurry. If a gate fires, fix the docs; raising the budget is not the fix.
