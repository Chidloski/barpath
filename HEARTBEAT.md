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

*(none)*

## Waiting

*(none)*

## Released — recent

Trim to the last dozen. The durable record of what was done goes in `TASKS.md`,
not here; this log exists only to show a waiting agent that a lock was let go
deliberately rather than abandoned.

*(none yet — this file was empty until the protocol landed on 2026-08-01)*
