# barpath watch logger

Records Apple Watch IMU at 100 Hz and gets it off the device as a CSV the
pipeline reads directly — same format as `synth.py`, defined once in
`src/io.py` (`COLUMNS`).

(This was "Milestone 7" under a schedule that no longer exists. Milestones 1–6
all passed while the pipeline failed in the gym, so the table was replaced by
the open problems in `CLAUDE.md` and the work list in `TASKS.md`. The logger
itself is one of the few parts that plainly works.)

## What it captures

Core Motion `deviceMotion`, `.xArbitraryZVertical` reference frame (z up,
heading arbitrary — `src/project.py` resolves heading by PCA at step 8):

| CSV column | source | units |
|---|---|---|
| `t` | `deviceMotion.timestamp` | s since boot (rebased on load) |
| `qw qx qy qz` | `attitude.quaternion` | body→world, w first |
| `ax ay az` | `userAcceleration` | **g**, and **Core Motion's sign** |
| `gx gy gz` | `rotationRate` | rad/s, **already bias-corrected** |
| `rgt rgx rgy rgz` | `CMGyroData` | s, rad/s — **raw**, not corrected (C2) |

The last four are new as of 2026-07-29 and are **optional** on the Python side,
so the ten captures recorded before them still load. `io.load_log` exposes them
as `log["raw_gyro"]` and `log["raw_gyro_lag"]`, or `None` when absent.

**Why log the gyro twice.** `deviceMotion.rotationRate` has already had Core
Motion's own bias estimate subtracted, by an opaque and time-varying internal
filter, so what we were recording is only the residual after it. `CMGyroData` is
uncorrected, so the difference between them *is* that estimate — see
`io.core_motion_gyro_bias`, and `CLAUDE.md` P5. The two streams arrive on
separate callbacks, so `rgt` is logged as well and `check_log` warns if the
pairing lag exceeds ~15 ms; beyond that the difference is real rotation rather
than bias.

**The CSV stores exactly what the watch reported — do not convert here.**
Core Motion's `userAcceleration` is the *negative* of the device's physical
acceleration: move the watch up and the reported z goes negative. `io.load_log`
converts units and sign together, once, at the boundary. That inversion went
unnoticed for months because at rest `userAcceleration` is zero, so its sign is
invisible in every still-hold check. See the `src/io.py` docstring.

The watch does not perfectly honour 100 Hz, so we log the **real per-sample
timestamp** and let the pipeline use `dt = diff(t)`. Do not resample.

## Why the two pieces

- **Watch app** — records, and holds a `HKWorkoutSession` for the duration so
  watchOS keeps the app (and the sensors) alive when your wrist drops mid-set.
  Without it, capture silently stops when the screen sleeps.
- **iPhone app** — receives each finished log over `WatchConnectivity` and
  writes it to its Documents folder, which is exposed to the Files app. Grab
  it from **Files → On My iPhone → BarpathLogger**, or plug the phone into the
  Mac and pull it from the container.

## Usage (on the fly)

1. Type the movement name (e.g. `deadlift_80`).
2. **Calibrate** — starts recording. Hold the bar still ~3 s (racked / on the
   floor). This is the *opening anchor*; it must be at the start and genuinely
   still.
3. **Start Set** — do your reps. (Recording is continuous; this just flips the
   on-screen prompt — the CSV is one stream.)
4. **Finish Set** — does **not** stop. It begins a **3-second closing hold**
   with a countdown on screen. Set the bar down, keep your wrist still, and let
   it run out — it **saves itself**. Do not reach for the watch, because tapping
   it is exactly the motion that ruins the anchor. There is a "Save now" button
   if you must, and the status line then flags the capture as single-anchor.

**Why the closing hold matters more than the opening one.** With one anchor, gyro
bias must be estimated from a single 1–3 s window, and the residual we are
chasing (0.1–0.9 °/s) is *smaller than the physiological tremor it sits in*
(~7 °/s peak-to-peak at 6.5 Hz). Block-resampled, the standard error on that
estimate is the same size as the estimate — which is why `calibrate.gyro_bias`
refuses to apply it by default: doing so was worse than doing nothing on 13 of
13 captures. Two anchors ~40 s apart measure **drift over a long baseline**
instead, where the lifter's own slow wrist rotation largely cancels and a genuine
bias does not. That is the one available change that could get under this noise
floor. See `CLAUDE.md` P4.

Zero of the first thirteen captures had any end-of-record stillness, so this has
never been possible. `io.check_log` now warns when it is missing.

**Discard** now genuinely discards. It used to call the same path as finish and
wrote a CSV, which is not what the label says.

Then, on the Python side: drop the CSV into `data/raw/`, and
`io.load_log(path)` gives you the same dict the synthetic tests use. Run
`io.check_log(log)` first — it flags irregular sampling, non-unit quaternions,
genuine clipping, and high-g transients at the limit of what 100 Hz represents.

## Xcode setup (once)

The `.xcodeproj` isn't checked in (it's machine-specific); create it and drop
these sources in.

1. **New Project → iOS → App**, name `BarpathLogger`, SwiftUI. This is the
   companion phone app — add `PhoneApp/*.swift`.
2. **File → New → Target → watchOS → Watch App for iOS App** (embeds a watch
   app in the same project). Add `WatchApp/*.swift` to that target.
3. **Capabilities**
   - Watch target: **HealthKit** (turn on "Workout Processing" background
     mode), and **Background Modes → Workout processing**.
   - Both targets get **WatchConnectivity** automatically (no toggle).
4. **Info.plist keys**
   - Watch: `NSMotionUsageDescription`, `NSHealthShareUsageDescription`,
     `NSHealthUpdateUsageDescription`.
   - Phone: `UIFileSharingEnabled = YES` and
     `LSSupportsOpeningDocumentsInPlace = YES` (so logs show in the Files app).
5. Set the deployment targets to your OS versions, pick your team for signing,
   build the **watch** scheme to your paired watch.

## Loading an updated build onto the watch

The Xcode project is not checked in, so you already have one — this is the
update path, not first-time setup.

1. **Open your existing `BarpathLogger` project** in Xcode. The Swift files are
   referenced from `watch/`, so if they were added as file references the edits
   are already there. If they were *copied* into the project, re-add or replace
   `WatchApp/MotionRecorder.swift` and `WatchApp/ContentView.swift` — those are
   the two that changed.
2. **Build the Watch App scheme, targeting the watch.** Select the watch app
   scheme (not the phone app) and your watch as the destination. That installs
   the phone app and the embedded watch app in one shot; you do not need a
   separate phone install.
3. **First launch on the watch: expect a permissions prompt.** Nothing new is
   requested — raw gyro is covered by the existing `NSMotionUsageDescription` —
   but if you reinstall rather than update, motion and HealthKit will ask again.
4. **Check it took.** On the watch, the "Finish Set" button is now **orange**
   rather than red, and pressing it shows a `HOLD STILL / closing anchor`
   countdown instead of saving immediately. If you still get an instant save,
   the old build is running.
5. **Check C2 is live.** While calibrating or recording the screen shows a green
   `✓ raw gyro` badge. If it reads orange `NO raw gyro`, the C2 columns will be
   empty and the capture is worth less — the four columns are optional on the
   Python side, so nothing downstream will complain either. Better to see it in
   the gym than in the CSV that evening.

If the install fails, in this order — this is what cost time last time:

- **Watch target's minimum deployment must not exceed your watch's watchOS.**
  This was the actual cause before: Xcode 15.4's bundled SDK was older than the
  watch's OS. The sources typecheck clean against the watchOS 26.5 SDK here.
- **Signing team set on *both* targets**, phone and watch.
- **Ghost placeholder icon that survives restarts, with the iPhone Watch app
  only offering "Install":** delete the *parent iOS app* from the iPhone. The
  watch app is embedded in it, so removing the phone app takes the watch
  companion with it on the next sync. Then rebuild.

## Sanity check before a real set

Record a 10 s clip holding the watch still on a table — press Calibrate, Start
Set, Finish Set, and let the closing hold run out. Then:

```python
from src import io
log = io.load_log("that_file.csv")
print(io.check_log(log))                       # expect []
print(log["fs"])                               # expect ~100
print(log["raw_gyro"] is not None)             # expect True — C2 is recording
print(io.core_motion_gyro_bias(log).mean(0))   # Core Motion's own estimate
```

Two things to confirm beyond the old checks. `raw_gyro` must not be `None`, or
the C2 columns are not being written. And the bias from the last line should be
of a **plausible order** — 0.1–0.9 °/s is 0.002–0.016 rad/s — and point in a
consistent direction while the watch is motionless.

**The sign of that difference is unverified.** `io.core_motion_gyro_bias`
returns `raw - corrected`, which is right if Core Motion computes
`corrected = raw - bias`. Nobody has checked that against a real log. This
still capture is how to check it, and it should be checked before anything is
built on the sign.
