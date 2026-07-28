# Non-goals

Binding. Do not implement, do not suggest, do not "leave a hook for".

The Estimation and Sensing rejections that used to live here were removed on
2026-07-28. They were not wrong when written, but almost every one of them
was justified against a synthetic gate — "revisit only if milestone 3 fails",
"if milestone 6 fails on synthetic data" — and real captures have since shown
those gates do not test the thing they were standing in for. A rejection whose
evidence has expired is not binding. They are recoverable from git history
(`git show HEAD:NON_GOALS.md`) and should be re-argued on real data, not
restored by default.

Scope below is unchanged and still binding.

## Scope

Not in this project at all: front/lateral view rendering. Live on-watch
processing. AI coaching or any ML. Accounts, sync, backend, cloud. Exercise
recognition. Rep counting as a shipped feature. Anything for lifts other
than squat, bench and deadlift. Per-exercise axis locking across sessions.
UI beyond a matplotlib figure.
