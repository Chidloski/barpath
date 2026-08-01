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

- **Watch app** — records, and holds the HealthKit workout session that keeps it
  recording once the wrist drops. Two screens: **Workout** and **Capture**. See
  below for why the session was removed and then put back.
- **iPhone app** — receives each finished log over `WatchConnectivity` and
  writes it to its Documents folder, which is exposed to the Files app. Grab
  it from **Files → On My iPhone → BarpathLogger**, or plug the phone into the
  Mac and pull it from the container.

### The workout session: removed on measurement (C7), restored on measurement (C16)

The session has been argued both ways and it is worth keeping both, because the
mistake was the same shape each time.

**The original belief.** This app held an `HKWorkoutSession` while recording,
because Core Motion stops delivering the moment watchOS suspends the app,
watchOS suspends it seconds after the wrist drops, and a workout session with
the Workout Processing background mode is Apple's documented way to prevent
that. All of it read off the documentation. None of it measured.

**It cost something real.** watchOS permits exactly one PRIMARY workout session
per device — `HKErrorAnotherWorkoutSessionStarted` is "by this or another
application" — so taking one ended whatever workout the owner had started in the
Workout app before walking into the gym. Reported as *"logging data stops my
workout"*.

**C7 checked whether the session was needed at all**, on 2026-07-30, with no
session running:

| capture | duration | rate | gaps |
|---|---|---|---|
| `drop_test_20260730_183925` | 47.08 s | 100.06 Hz | zero > 15 ms |
| `better_drop_test_20260730_184839` | 58.78 s | 100.06 Hz | **zero at any threshold** |

A **19.9 s** span and a **16.5 s** span with the wrist still and the screen
dimmed, a notification raised and dismissed mid-capture, and not one sample
lost. Zero repeated rows in either, unit quaternions, `io.check_log` clean. On
that evidence the session, the workflow change, the metrics screens and the
effort rating were all deleted.

#### C16 — that was wrong, and C7 named the reason itself

C7 wrote down its own falsifier: *"the app being genuinely REPLACED mid-capture
— the watch face returning, or another app opened — for longer than the ~6.5 s
the first drop test covered."* It went on the shot list in `TASKS.md` and
`HANDOFF.md` as never collected. **It has now been collected, by accident, in a
real gym session**, and it came back the other way:

- captures stopped surviving the wrist going down, and
- a workout already running in the **Workout app** took priority while the wrist
  was down, so this app was the one that got suspended.

Too few samples to use. That session's raw data is unusable.

**What the drop tests actually proved is narrower than what was concluded from
them.** Both were taken with the app **frontmost** and the screen merely
**dimmed**. That is a real state, and Core Motion does keep streaming through it
— the table above is not in dispute. It is simply not the gym state. In the gym
the wrist drops, watchOS returns to the clock or hands the foreground to
whichever app has a live workout, and a backgrounded app with no session of its
own is suspended. *Frontmost-and-dimmed* and *replaced* are different cases, and
only the first was ever tested.

This is the project's recurring failure shape once more: **an aggregate that
passes while the thing fails exactly where it matters.** It is the same error as
`truth.validate` checking a whole-clip median while the tracker was lost at
lockout. Measure the case you care about, not the neighbouring one that is
easier to stage.

**So the session is back, and it is the workout of record again.** One session
per device means this app and the Workout app cannot both hold one, and there is
no API to share, join or even detect the other's — see `MotionRecorder.swift`
for the three routes that do not exist. Taking it quietly would end the owner's
workout, which was the original bug. So this app does not compete with the
Workout app, it **replaces** it for a lifting session: live metrics on a screen
of its own, saved to Health as Traditional Strength Training with ring credit,
and an effort rating afterwards.

**The trade, plainly.** Start the workout *here*. If the Workout app is opened
during a recording it preempts us and the capture can truncate — watchOS gives
no way to prevent that, only to notice it, which is what the session delegate
does: the status line says so and the watch plays a failure haptic.

**What would falsify the restoration.** If a capture taken with a session of
ours running still truncates when the wrist drops, the session is not what keeps
Core Motion alive and the problem is elsewhere. Check `dt` for gaps, below — not
the sample counter.

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

## The two screens

Paged with the crown. It opens on **Workout**, because the recurring failure is
a capture taken with no session; it pages itself to **Capture** as soon as one
is running.

**Workout** — reserved for the workout and nothing else. Elapsed clock, heart
rate with average and peak, active and total calories, and the number of
captures saved so far this workout. `Start Workout` / `End Workout & Save`.
Ending is disabled while a capture is running, because ending drops the
keep-alive with the recording still going — the exact failure this build exists
to prevent. Finish the capture, then end the workout.

**Capture** — the capture protocol, unchanged. Name, opening anchor, reps,
closing anchor. It warns in red if no workout session is running while a
recording is in progress.

There is deliberately **no pause control**, though the Workout app has one. A
paused session is not a running session, and "the session is running" is the
whole reason this app can record with the wrist down — a pause button is a
one-tap way to silently break a capture.

**Rate your effort** appears full-screen once the workout is saved: 1–10 on
Apple's own wording, crown or slider, `Skip` a first-class option. An unrated
workout is still a saved workout.

## Usage (on the fly)

0. **Start Workout**, on the Workout screen — **not** in the Workout app. One
   session exists per device, so a workout started over there takes ours and the
   captures truncate. That is C16, above. (If you forget, `Calibrate` starts one
   for you.)
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
5. Between sets, swipe up for the Workout screen. Repeat 1–4 for each set — one
   workout spans the whole gym session, so do **not** end it between sets.
6. **End Workout & Save** when you leave, then rate the effort. This is what
   puts the workout in Health with its ring credit; it is the other half of
   taking the device's only session.

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
3. **Capabilities** — these are load-bearing now, unlike between C7 and C16.
   - Both targets get **WatchConnectivity** automatically (no toggle).
   - Watch target: **HealthKit**, and tick **Workout Processing** under it.
     That background mode is what lets the app keep running with the wrist down.
     Without it the session starts and the capture still truncates, which looks
     identical to the bug C16 fixed.
   - Watch target: **Background Modes → Workout processing** if your Xcode does
     not add it with the HealthKit capability.
4. **Info.plist keys**
   - Watch: `NSMotionUsageDescription`, `NSHealthShareUsageDescription` and
     `NSHealthUpdateUsageDescription`. The app will crash on first launch
     without the two HealthKit strings.
   - Phone: `UIFileSharingEnabled = YES` and
     `LSSupportsOpeningDocumentsInPlace = YES` (so logs show in the Files app).
5. **Watch deployment target: watchOS 11.0 or newer.** Pick your team for
   signing on *both* targets, then build the **watch** scheme to your paired
   watch.

   The floor is watchOS 11 and it is exactly four symbols, all in the effort
   rating: `HKQuantityTypeIdentifier.workoutEffortScore`,
   `HKUnit.appleEffortScore()`, and
   `HKHealthStore.relateWorkoutEffortSample(_:with:activity:completion:)`.
   Verified rather than assumed — the sources typecheck clean at
   `-target arm64_32-apple-watchos11.0`, `...12.0` and `...26.0`, and fail at
   `...10.0` on those four and nothing else.

   Earlier builds guarded them with `#available` to hold the target at 10.0.
   That is no longer done: watchOS 11+ is the supported floor, so the guard buys
   nothing. Remember why the guard ever existed, because the mistake recurs —
   **availability is checked against the deployment target, not against your
   watch.** A watchOS 26 wrist does not make a watchOS 11 symbol legal in a
   target that says 10.0; the compiler has no idea which device you will install
   on.

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
3. **First launch on the watch: a motion prompt and a HealthKit prompt.** Grant
   both. If no HealthKit prompt appears, the capability is missing from the
   watch target — add it (step 3 of setup), or the session will never start and
   the captures will truncate exactly as before.
4. **Check it took.** Three things. The app opens on a **Workout** screen with
   an elapsed clock and a `Start Workout` button; if it opens straight onto the
   movement field with no page above it, the C7 build is still installed. There
   is a **Capture** screen below it, reached by swiping down. And "Finish Set"
   is **orange** rather than red, showing a `HOLD STILL / closing anchor`
   countdown instead of saving immediately.
5. **Check the phase column arrived.** `head -1` the CSV: the header should end
   `...,gx,gy,gz,phase`, and `io.check_log` will tell you if the closing hold ran
   for less than 2 s.

If the install fails, in this order — this is what cost time last time:

- **Watch target's minimum deployment must be watchOS 11.0 or newer, and must
  not exceed your watch's watchOS.** Too low and the effort rating will not
  compile (step 5 of setup names the four symbols). Too high — or an Xcode whose
  bundled SDK is older than the watch's OS — and the install fails; that was the
  actual cause before, with Xcode 15.4. The sources typecheck clean against the
  watchOS 26.5 SDK here.
- **Signing team set on *both* targets**, phone and watch.
- **Ghost placeholder icon that survives restarts, with the iPhone Watch app
  only offering "Install":** delete the *parent iOS app* from the iPhone. The
  watch app is embedded in it, so removing the phone app takes the watch
  companion with it on the next sync. Then rebuild.

## Sanity check before a real set

Record a 10 s clip holding the watch still on a table — press Calibrate, Start
Set, Finish Set, and let the closing hold run out. **Then end the workout**, or
`Calibrate`'s auto-start leaves a strength workout accruing in Health all
afternoon; that is the cost of C16 putting the session back, and it is a
deliberate one. Then:

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
