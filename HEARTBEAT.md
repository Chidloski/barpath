# Heartbeat — who is writing to what, right now

Several agents may work this repo at the same time, on independent problems,
without knowing about each other. This file is the only thing that stops two of
them editing the same file at once. **Read it before your first write. Claim
before you edit. Release when you stop.**

The protocol is in `CLAUDE.md` under **Concurrency protocol**, and it is binding.
The short version:

1. Read this file.
2. If nothing active overlaps the paths you need, append a claim block and edit.
3. If something does overlap, you may **not** edit those paths. Take other work
   if you have it; otherwise append a `status: waiting` block and stop.
4. When you finish, set your block to `status: released` and move it to the log.

Reads are always free. Claims are write locks only.

**This file lives in the shared checkout**, at
`/Users/sam/Desktop/barpath/HEARTBEAT.md`. Read and write it at that path even
when you are working inside a worktree — a claim written into a worktree copy is
invisible to everyone else and is not a claim. Its churn is deliberately left
uncommitted; see the protocol.

## Claim format

One `###` block per claim, appended to the end of **Active**. Never rewrite
another agent's block. The four fields are required and are checked by
`tests/test_heartbeat.py`.

```
### C13 — B3, rework the per-rep detrend
- since: 2026-08-01T15:40Z
- paths: src/correct.py, tests/test_real_data.py, analysis/35_b3_detrend.png
- status: active
- note: shared docs claimed separately at the end, expect ~10 min.
```

`since` is UTC, minute resolution. `paths` are repo-relative; a directory claims
everything under it. `status` is one of `active`, `waiting`, `released`. `note`
is free text, and it is where you say what you are doing and roughly how long you
expect to hold the paths — the agent reading this is deciding whether to wait or
go and find other work, and it cannot decide without that.

A claim on a file that does not exist yet is how you reserve a name. Do that for
the next `analysis/NN_*.png` number **before** you generate the plot; otherwise
two agents both take `35` and one silently overwrites the other.

## Active

## Waiting

*(none)*

## Released — recent

Trim to the last dozen. The durable record of what was done goes in `TASKS.md`,
not here; this log exists only to show a waiting agent that a lock was let go
deliberately rather than abandoned.

### C18 — add the `git add -A` hazard to the concurrency protocol
- since: 2026-08-02T20:25Z
- paths: CLAUDE.md
- status: released
- note: .gitignore cannot stop `add -A` staging HEARTBEAT.md, which is tracked.
  Documenting it beside the existing stash/reset warning. Two-minute window.
  RELEASED 2026-08-02T20:35Z — commit fce10dc on branch
  `worktree-markers-as-referee`, pushed, not merged. 22 tests passed.

### C18 — .gitignore the worktrees and the non-gym captures
- since: 2026-08-02T20:15Z
- paths: .gitignore, .DS_Store
- status: released
- note: `git add -A` in the shared checkout staged the worktree as an embedded
  git repo, HEARTBEAT.md (which must never be committed) and four capture CSVs.
  Adding the two missing ignore rules and retiring the tracked .DS_Store.
  Short window, worktree `markers-as-referee`.
  RELEASED 2026-08-02T20:35Z — commit fce10dc on branch
  `worktree-markers-as-referee`, pushed, not merged. 22 tests passed.

### C17 — shared docs for the scoring-path dispatch (part 2)
- since: 2026-08-02T19:10Z
- paths: CLAUDE.md, TASKS.md, src/README.md
- status: released
- note: short window. CLAUDE.md's "two video referees" paragraph and the C17
  entry both need the dispatch recorded. Committing with the code, releasing
  straight after.
  RELEASED 2026-08-02T19:45Z — C17 done, both parts. Commits 2f2243b and
  ed850f8 on branch `worktree-markers-as-referee`, draft PR #4. Full suite
  451 passed / 11 xfailed / 4 xpassed. analysis/38 was claimed and NOT
  used, so 38 is free again — next free number is 38.

### C17 — extend the claim to tests/test_pipeline.py
- since: 2026-08-02T18:55Z
- paths: tests/test_pipeline.py
- status: released
- note: gate for the find_video dataset pairing changed above. find_video has
  no test today.
  RELEASED 2026-08-02T19:45Z — C17 done, both parts. Commits 2f2243b and
  ed850f8 on branch `worktree-markers-as-referee`, draft PR #4. Full suite
  451 passed / 11 xfailed / 4 xpassed. analysis/38 was claimed and NOT
  used, so 38 is free again — next free number is 38.

### C17 — extend the claim to pipeline.find_video
- since: 2026-08-02T18:45Z
- paths: src/pipeline.py
- status: released
- note: find_video hardcodes data/video, so a data_v2 capture would never find
  its clip and the marker scoring path would be unreachable from pipeline.run.
  Appended rather than rewriting the C17 block above, per the protocol.
  RELEASED 2026-08-02T19:45Z — C17 done, both parts. Commits 2f2243b and
  ed850f8 on branch `worktree-markers-as-referee`, draft PR #4. Full suite
  451 passed / 11 xfailed / 4 xpassed. analysis/38 was claimed and NOT
  used, so 38 is free again — next free number is 38.

### C17 — make the sticker tracker a usable referee for data_v2
- since: 2026-08-02T17:35Z
- paths: src/markers.py, src/metrics.py, src/truth.py, tests/test_markers.py,
  tests/test_video_truth.py, tests/test_real_data.py,
  analysis/38_marker_referee.png
- status: released
- note: two pieces. (1) the marker fit-residual gate tests a whole-clip median
  while lockout medians reach 1.60 px against a 1.5 px limit — same shape as
  C12; make it check where it is used. (2) plumb markers into the scoring path
  so metrics.vs_truth / momentum_closure / bench_sync can be fed either
  tracker, validated by reproducing today's numbers bit-identically from
  truth.bar_path. Working in worktree `markers-as-referee`. Shared docs
  claimed separately at the end. Expect ~90 min.
  RELEASED 2026-08-02T19:45Z — C17 done, both parts. Commits 2f2243b and
  ed850f8 on branch `worktree-markers-as-referee`, draft PR #4. Full suite
  451 passed / 11 xfailed / 4 xpassed. analysis/38 was claimed and NOT
  used, so 38 is free again — next free number is 38.

### C17 — shared docs for the marker-referee gate (part 1)
- since: 2026-08-02T18:05Z
- paths: TASKS.md, src/README.md, analysis/README.md
- status: released
- note: short window. The 1.5 px whole-clip gate described in these three is
  now stratified by height, so their description of it reads false. Committing
  with the code per the same-commit rule, then releasing straight away.
  RELEASED 2026-08-02T18:20Z — landed in 2f2243b with the code, per the
  same-commit rule. Held ~15 min.

### C15 — merge origin/main into the sticker-tracker branch
- since: 2026-08-01T19:10Z
- paths: TASKS.md, CLAUDE.md
- status: released
- note: resolved by keeping BOTH the C14 and C15 sections in TASKS.md; C14's
  CLAUDE.md trim verified intact. Branch `worktree-sticker-tracker` is now a
  fast-forward onto main, 404 passed. main itself was never touched.

### C15 — old-vs-new tracker comparison plot, and src/README
- since: 2026-08-01T18:05Z
- paths: analysis/37_old_vs_new_tracker.png, analysis/README.md, src/README.md
- status: released
- note: pushed to branch `worktree-sticker-tracker`, draft PR #3. analysis/35, 36
  and 37 are all taken; next free number is 38.

### C15 — sticker-based video tracker for `data_v2`
- since: 2026-08-01T16:15Z
- paths: src/markers.py, tests/test_markers.py, analysis/35_markers_detection.png,
  analysis/36_markers_vs_plate.png, data_v2/
- status: released
- note: done and pushed — branch `worktree-sticker-tracker`, draft PR #3. New
  module only; no existing .py touched. Full suite 372 passed / 34 skipped.
  analysis/35 and 36 are taken; next free number is 37.

### C15 — shared docs for the sticker tracker
- since: 2026-08-01T17:05Z
- paths: CLAUDE.md, TASKS.md, README.md, analysis/README.md, src/README.md
- status: released
- note: landed in the same commit as the code, per the same-commit docs rule.
  README.md was claimed but not in the end modified.


### C16 — restore the watch workout session (C7 falsified in the gym)
- since: 2026-08-01T16:40Z
- paths: watch/WatchApp/MotionRecorder.swift, watch/WatchApp/ContentView.swift,
  watch/README.md, TASKS.md, HANDOFF.md
- status: released
- note: done and pushed — branch `worktree-watch-workout-session`, draft PR #2.
  Typechecks clean at watchOS 11/12/26, pytest 49 passed. Not verified on device.
