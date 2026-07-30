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
| `phase` | the app's own state | `0` opening hold, `1` reps, `2` closing hold |

`phase` is new as of 2026-07-30 and is **optional** on the Python side, so every
earlier capture still loads — `io.load_log` gives `log["phase"]` or `None`.

**Why log the phase.** It tells the pipeline where the anchors are instead of
making it guess. `calibrate.stillest_window` hunts the quietest second in the
opening 3 s, which is exactly when a finger is on the Calibrate button: on a
stationary test capture it picked a window with 1.8× the motion of the genuinely
quiet part, and the ~0.002 m/s² bias error that caused produced 38 cm of drift
over 19 s on a watch that never moved.

The cleanest stillness in any capture is the **tail of phase 2**, because it is
the only quiet window not followed by a screen tap — the closing hold saves
itself. You cannot find that without knowing the phases. Using it is the first
thing to try with a capture that has a real closing anchor.

### C2 was abandoned — raw gyro is not available on watchOS

An earlier build logged raw `CMGyroData` in four extra columns
(`rgt rgx rgy rgz`) so that its difference from the bias-corrected
`rotationRate` would expose Core Motion's internal estimate (`CLAUDE.md` P5).
**`CMMotionManager.isGyroAvailable` returns false on watchOS.** The raw gyro
service simply is not offered — tried on one motion manager and on two, and the
badge reported no hardware. There is no public-API route to it.

It costs less than it sounds. A stationary capture put the residual *after*
Core Motion at **0.002 °/s**, so there was never much for its estimate to
explain. Two diagnostic captures from 2026-07-30 carry those columns, always
empty; `io.load_log` still reads them so those files load, and nothing writes
them.

**The CSV stores exactly what the watch reported — do not convert here.**
Core Motion's `userAcceleration` is the *negative* of the device's physical
acceleration: move the watch up and the reported z goes negative. `io.load_log`
converts units and sign together, once, at the boundary. That inversion went
unnoticed for months because at rest `userAcceleration` is zero, so its sign is
invisible in every still-hold check. See the `src/io.py` docstring.

The watch does not perfectly honour 100 Hz, so we log the **real per-sample
timestamp** and let the pipeline use `dt = diff(t)`. Do not resample.

## Why the two pieces

- **Watch app** — records. Nothing else: no workout session, no HealthKit, no
  background mode. See below for what was removed and why.
- **iPhone app** — receives each finished log over `WatchConnectivity` and
  writes it to its Documents folder, which is exposed to the Files app. Grab
  it from **Files → On My iPhone → BarpathLogger**, or plug the phone into the
  Mac and pull it from the container.

### The workout session that was removed (C7, 2026-07-30)

This app used to hold an `HKWorkoutSession` while recording. The reasoning, held
for as long as the app existed: Core Motion stops delivering the moment watchOS
suspends the app, watchOS suspends it seconds after the wrist drops, and an
`HKWorkoutSession` with the Workout Processing background mode is Apple's
documented way to prevent that. All of it read off the documentation. None of it
measured.

**It cost something real.** watchOS permits exactly one PRIMARY workout session
per device — `HKErrorAnotherWorkoutSessionStarted` is "by this or another
application" — so taking one ended whatever workout the owner had started in the
Workout app before walking into the gym. Reported as *"logging data stops my
workout"*.

The first fix ran the other way: keep the session, save it to Health as a
Traditional Strength Training workout, and have this app **replace** the Workout
app — paged live metrics, an effort rating, ring credit — so nothing was lost by
the switch. It worked. It was also a workflow change imposed on the owner to
solve a problem nobody had checked was real.

**So it was checked.** Two captures with no session at all:

| capture | duration | rate | gaps |
|---|---|---|---|
| `drop_test_20260730_183925` | 47.08 s | 100.06 Hz | zero > 15 ms |
| `better_drop_test_20260730_184839` | 58.78 s | 100.06 Hz | **zero at any threshold** |

The second settled it: a **19.9 s** span and a **16.5 s** span with the wrist
still and the screen dimmed, plus a notification raised and dismissed
mid-capture, and not one sample lost. Zero repeated rows in either, unit
quaternions, `io.check_log` clean.

**The premise was false for the case that matters.** A capture is 40-60 s, the
app stays frontmost for that long, and Core Motion keeps streaming at 100 Hz
while frontmost-and-dimmed. So the session, the workflow change, the metrics
screens and the effort rating are all gone, and the watch target no longer needs
HealthKit at all. Start your workout in the Workout app again if you want one;
this app will not touch it.

**What would bring it back.** The untested case is the app being genuinely
REPLACED mid-capture — the watch face returning, or another app opened — for
longer than the ~6.5 s the first test covered. watchOS's *Return to Clock*
default will not fire inside a single set, which is why this is judged safe. If
captures ever start truncating, check that first — and read this section before
re-adding a session, because the fix is not automatically a workout session.

**Check a capture the right way.** The sample counter cannot show a dropout: a
dropout is a gap in the timestamps, and the count keeps rising either way.

```bash
python -c "
import numpy as np; from src import io
l = io.load_log('data/raw/YOURFILE.csv'); dt = l['dt']
print(len(l['t']), 'samples', round(l['t'][-1],1), 's',
      round(len(l['t'])/l['t'][-1],2), 'Hz')
print('max gap ms', round(dt.max()*1000,1), ' gaps>50ms', int((dt>0.05).sum()))"
```

## Usage (on the fly)

0. Start a workout in the **Workout app** if you want one. This app no longer
   holds a session and will not disturb yours — that is C7, above.
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
   - Both targets get **WatchConnectivity** automatically (no toggle).
   - **Nothing else.** No HealthKit, no background modes. If your project still
     carries the HealthKit capability and the Workout Processing background mode
     from before 2026-07-30, remove them — C7 above is why, and leaving them
     asks the owner for permissions the app no longer uses.
4. **Info.plist keys**
   - Watch: `NSMotionUsageDescription`. The two HealthKit strings
     (`NSHealthShareUsageDescription`, `NSHealthUpdateUsageDescription`) can go
     with the capability.
   - Phone: `UIFileSharingEnabled = YES` and
     `LSSupportsOpeningDocumentsInPlace = YES` (so logs show in the Files app).
5. Set the deployment targets to your OS versions, pick your team for signing,
   build the **watch** scheme to your paired watch.

   **No minimum beyond whatever your watch runs.** The sources use no API newer
   than the base SwiftUI/CoreMotion/WatchConnectivity set and typecheck clean at
   `-target arm64_32-apple-watchos9.0`, `...10.0` and `...26.0`. This briefly was
   not true — the effort rating pinned it to watchOS 11 and broke a build set to
   10.0 — and it is worth remembering why: **availability is checked against the
   deployment target, not against your watch.** A watchOS 26 wrist does not make
   a watchOS 11 symbol legal in a target that says 10.0; the compiler has no idea
   which device you will install on.

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
3. **First launch on the watch: only the motion prompt.** There is no longer a
   HealthKit prompt. If you still get one, the old capability is still on the
   target — remove it (step 3 of setup).
4. **Check it took.** Two things. The idle screen shows **only** the movement
   field and **Calibrate**; if there is a Start Workout button or a swipe-up
   metrics page, the pre-C7 build is still installed. And "Finish Set" is
   **orange** rather than red, showing a `HOLD STILL / closing anchor` countdown
   instead of saving immediately.
5. **Check the phase column arrived.** `head -1` the CSV: the header should end
   `...,gx,gy,gz,phase`, and `io.check_log` will tell you if the closing hold ran
   for less than 2 s.

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
Set, Finish Set, and let the closing hold run out. Nothing else to clean up
afterwards: since C7 the app starts no workout session, so a bench-test clip no
longer leaves a strength workout accruing in Health all afternoon. Then:

```python
from src import io
log = io.load_log("that_file.csv")
print(io.check_log(log))          # expect []
print(log["fs"])                  # expect ~100
import numpy as np
print(np.bincount(log["phase"]))  # samples in each phase — expect all three
```

The phase counts are the thing to check: roughly 300 in phase 0, the set in
phase 1, and ~300 in phase 2. A missing phase 2 means the closing hold did not
run, and `check_log` will say so.
