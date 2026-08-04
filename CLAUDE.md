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
   | `io.py`, `calibrate.py`, `orient.py`, `integrate.py`, `segment.py`, `correct.py`, `project.py`, `pipeline.py` | `metrics.py`, `truth.py`, `markers.py`, `plot.py`, `synth.py`, `run.py`, `tests/`, `analysis/`, all docs |

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
6. `correct.py` — subtract the wrist-to-bar offset R(t)·d.
7. `correct.py` — per-rep linear detrend so each rep closes.
8. `project.py` — PCA on horizontal displacement picks the display axis.
9. `plot.py` — overlay reps, aligned by start point, horizontal stretched 4x.

`metrics.py` is not one of the steps. It judges them: `dispersion` for
rep-to-rep spread, `vs_truth` for absolute error against the video. Read its
module docstring before quoting a number from it — `dispersion` needs no truth
and is blind to exactly the error that dominates, so the two are not
interchangeable.

There are **two video referees**, and which one applies is decided by the
footage, not by preference. `truth.py` tracks the plate as a dark disc and is
the referee for everything in `data/video/`. `markers.py` (C15, 2026-08-01)
tracks retroreflective stickers and is the referee for `data_v2/`, which is
filmed from a tripod with markers on the plate. **The four bench captures of
2026-08-03 are refereed by `markers.py` as of C23, and the three 8-sticker
deadlifts of 2026-08-04 as of C27**; everything else is scored by `truth.py`,
because `data/video/` has no markers. The deadlifts are the first captures
refereed by the CONIC path, and the first marker footage of a lift other than
bench. See the C21/C23 note below.
`markers.py` is what a future capture should be judged by: on the same five
clips it tracks 100% of frames where the plate template loses the bar at every
lockout and reports 0.2 cm of travel on one bench set. See `src/README.md` and
`analysis/35`–`37`. It is not immune to what breaks `truth.py`, only better
behaved: its fit residual also degrades with height, 0.16 to 0.81 px, but stays
inside tolerance instead of crossing it — worst case 0.33 cm against the 1 cm
spec, measured by `markers.top_of_travel_residual` and gated per capture (C17).

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
- `data/raw/` is immutable and gitignored. Re-deriving from raw is trivial;
  re-collecting from a gym is not.

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

**A second dataset opened on 2026-08-03 and grew on 2026-08-04**: `data_v2/raw/`
holds **four bench captures (14 reps) and three 8-sticker deadlifts (15 reps)**, each with a marker clip beside it in `data_v2/video/` —
the first IMU logs ever paired with marker footage, and the first captures in
this project refereed by `markers.py`. All four carry the `phase` column with a
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
exists. **The corpus is 24 captures and 101 reps** — 21 and 86 plus the three 8-sticker
deadlifts of 2026-08-04 (6, 6 and 3 reps), which count 15 of 15 and are the
first captures in this project refereed by the conic marker path (C27).

Work the problems instead. Each is stated with the evidence that it is real,
so it can be closed by evidence rather than by opinion.

**P1 — Counting and extent are clean at 72/72; phase is now verified on
deadlift and bench, and open only on squat.** Rewritten 2026-07-31 by C5, and
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
run of six that beat the true five on length alone. It is 1.45 now, mid-plateau
of a 1.35–1.55 band bounded by real data on both sides. **The live limitation: a
rest-pause or cluster set has a real mid-set gap above 1.45 and would be split.**
No such capture exists.

**Counting is 24 of 24 captures, 101 of 101 reps** (C27 added three deadlifts at
6/6, 6/6 and 3/3, every floor impact found) — the two captures that broke
it were deleted (see above), so this is a smaller claim than 22/23 rather than
a better one.

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

Squat is now the only lift with no external horizontal check, and its footage
got worse rather than better: two of the four 2026-07-30 captures do not track
at all. `metrics.vs_truth` refuses it. That wants a wider shot, not code.
