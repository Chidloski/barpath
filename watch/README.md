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

- **Watch app** — records, and holds a `HKWorkoutSession` for the duration so
  watchOS keeps the app (and the sensors) alive when your wrist drops mid-set.
  Without it, capture silently stops when the screen sleeps. **Start that
  session from this app, not the Workout app** — see below.
- **iPhone app** — receives each finished log over `WatchConnectivity` and
  writes it to its Documents folder, which is exposed to the Files app. Grab
  it from **Files → On My iPhone → BarpathLogger**, or plug the phone into the
  Mac and pull it from the container.

### The workout session, and why it replaces the Workout app

**watchOS allows exactly one workout session on the device.** `HKError`'s own
wording for the collision: `errorAnotherWorkoutSessionStarted` is "Another
primary workout session has started or is already ongoing by this or another
application." So this app and the Workout app cannot both hold one, and until
2026-07-30 pressing **Calibrate** created a session unconditionally — which
ended whatever workout you had started before walking into the gym. Nothing said
so, because the session had no delegate attached and nobody was listening.

**There is no way to coexist.** All three escapes were checked against the
watchOS 26.5 SDK headers and none exist:

- *Join the Workout app's session.* No API. `recoverActiveWorkoutSession` is
  documented as "Recovers an active workout session after a client crash" — it
  gives **your** app back **your** session. `workoutSessionMirroringStartHandler`
  is cross-*device* within one app. Nothing even reports that another app holds
  a session, so the collision cannot be detected, let alone joined.
- *Start no session and lean on theirs.* Background execution is granted per
  app, not per device. Their session keeps their app alive, not ours.
- *`WKExtendedRuntimeSession` instead.* Rejected without testing, deliberately:
  it needs a `WKBackgroundModes` key this app does not have and Apple gates to
  mindfulness / physical-therapy apps, the ungated session types are invalidated
  with `resignedFrontmost` (exactly the wrist-drop case we must survive), and
  nothing documents that Core Motion keeps streaming at 100 Hz under one.
  Swapping a keep-alive that works for one that might costs gym captures.

**So the app stopped competing and became the workout.** The session drives an
`HKLiveWorkoutBuilder`, and **End Workout & Save** finishes it into Health with
heart rate and energy, as a Traditional Strength Training workout with ring
credit. Start it from the app; there is then no second session to preempt.

### The screens

Giving up the Workout app is only acceptable if nothing is lost with it, so the
app shows what that app showed. Two pages while a workout is running, paged with
the crown or a swipe:

| page | when you want it |
|---|---|
| **Workout** (swipe up) | between sets. Elapsed clock, live heart rate with workout average, active and total calories. |
| **Record** (default) | during a set. The calibrate / start / finish buttons, and nothing else. |

Paged rather than one long scroll on purpose: scrolling past live metrics to
reach **Finish Set** at the end of a hard rep is the wrong shape. The Record
page is the default because it is why the app exists.

**Rate your effort** (watchOS 11+; silently absent below, see the deployment
target note). Ending a workout shows a 1–10 effort dial — Apple's own
scale and wording (Easy / Moderate / Hard / All Out), driven by the crown or the
slider. It writes an `HKQuantityTypeIdentifierWorkoutEffortScore` sample **and**
calls `relateWorkoutEffortSample` to attach it to that workout; saving the sample
alone leaves a free-floating number the Fitness app will not show against the
session. **Skip** is a first-class option — an unrated workout is still a saved
workout, and a rating should not be the price of the Health record.

Metrics are best-effort throughout. A HealthKit type you denied simply never
arrives and its field stays at `--`; none of it touches the CSV, which comes
from Core Motion and depends on none of it.

### The one test that could delete all of this

Everything above rests on an assumption nobody has measured: **that the workout
session is what keeps Core Motion delivering once your wrist drops.** It is
Apple's documented mechanism and it is why the session exists — but it has never
been checked on this watch, this watchOS, this app.

The idle screen carries a **Test: no workout session** toggle for exactly that.
With it on, Calibrate records with no session at all. Do one wrist-down set,
then check the capture:

```bash
python -c "from src import io; l=io.load_log('data/raw/YOURFILE.csv'); \
print(l['fs'], l['t'][-1], len(l['t']))"
```

If it holds ~100 Hz for the whole set, **the session is not load-bearing**, the
collision with the Workout app never mattered, and the right change is to stop
starting one — which deletes the workflow change, the delegate, and most of this
section. If it truncates when your wrist drops, that is the assumption
confirmed and the section stands.

Expect it to truncate. That IS the result — name the capture something you will
recognise and do not use it as lifting data.

*The tradeoff.* This is a workflow change, not a repair — the collision is still
there, it is just no longer provoked. If you open the Workout app **during** a
recording it preempts *us*, Core Motion stops the next time your wrist drops, and
the capture truncates. That cannot be prevented, only noticed: the session now
has a delegate, so the watch shows **NO WORKOUT — may stop early** in red and
plays a failure haptic instead of failing silently.

*What would falsify all of this:* record a wrist-down set with **no** workout
session running and check `log["fs"]` and the sample count. If it holds ~100 Hz
to the end, the session is not load-bearing and the app should simply stop
starting one. That test costs one set and has never been run.

## Usage (on the fly)

0. **Start Workout** (idle screen) — instead of starting one in the Workout app.
   Once per gym session, not per set. If you forget, **Calibrate** starts one for
   you and says so on the status line; losing a capture to a suspended app is the
   worse failure. Once it is running, **swipe up** for the workout page — elapsed,
   heart rate, calories — and back down for the recording controls. At the end of
   the session, **End Workout & Save** writes it to Health and asks you to rate
   the effort 1–10 (crown or slider; **Skip** is fine, the workout is already
   saved by then).
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
     `NSHealthUpdateUsageDescription`. Both HealthKit strings are load-bearing
     now, not formalities — the app writes a real workout and reads heart rate
     and energy into it.
   - Phone: `UIFileSharingEnabled = YES` and
     `LSSupportsOpeningDocumentsInPlace = YES` (so logs show in the Files app).
5. Set the deployment targets to your OS versions, pick your team for signing,
   build the **watch** scheme to your paired watch.

   **The watch target's minimum deployment must be watchOS 10.0 or later.**
   `.tabViewStyle(.verticalPage)` and `onChange(of:initial:_:)` are watchOS 10,
   and they are not guarded — the paged layout is the design, not an extra.

   The effort rating needs watchOS 11 (`HKQuantityTypeIdentifierWorkoutEffortScore`,
   `relateWorkoutEffortSample`) and **is** guarded, so a 10.0 target builds and
   simply has no rating screen. Raise the target to 11.0 to get it.

   **Availability is checked against this setting, not against your watch.** A
   watchOS 26 wrist does not make a watchOS 11 symbol legal in a target that
   says 10.0 — the compiler has no idea which device you will install on. That
   mismatch is what broke the build on 2026-07-30. Sources typecheck clean at
   `-target arm64_32-apple-watchos10.0`, `...11.0` and `...26.0`.

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
3. **First launch on the watch: expect a HealthKit prompt, and grant it.** The
   app now asks for **heart rate**, **active/resting energy**, **walking +
   running distance** and, on a watchOS 11+ target, **workout effort score** on
   top of Workouts, because
   it saves a real workout rather than holding an unsaved session. Denying them
   does not stop recording — the keep-alive and the CSV are unaffected — it only
   thins the saved workout and blanks the metrics screen.
4. **Check it took.** Three things. On the idle screen there is now a **Start
   Workout** button (and, once running, "End Workout & Save"); if the only
   button is Calibrate, the old build is running. Once a workout is running,
   **swiping up shows the metrics page** — elapsed clock, heart rate, calories.
   And the "Finish Set" button is **orange** rather than red, showing a
   `HOLD STILL / closing anchor` countdown instead of saving immediately.
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
Set, Finish Set, and let the closing hold run out. Then press **End Workout &
Save**: Calibrate starts a workout session if none is running, and it stays
running until you end it, so a bench-test clip otherwise leaves a strength
workout accruing in Health all afternoon. Then:

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
