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
| `gx gy gz` | `rotationRate` | rad/s |

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
   floor). This is the pre-set pause calibration reads its gyro/accel bias
   from; it must be at the *start* and genuinely still.
3. **Start Set** — do your reps. (Recording is continuous; this just flips the
   on-screen prompt — the CSV is one stream.)
4. **Finish Set** — stops, writes `⟨name⟩_⟨timestamp⟩.csv`, and sends it to the
   phone.

Then, on the Python side: drop the CSV into `data/raw/`, and
`io.load_log(path)` gives you the same dict the synthetic tests use. Run
`io.check_log(log)` first — it flags irregular sampling, non-unit quaternions,
and saturation.

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

## Sanity check before a real set

Record a 10 s clip holding the watch still on a table. `load_log` +
`check_log` should report no warnings, `fs ≈ 100`, and `accel` norm ≈ 0 (g
removed). If the quaternions aren't unit-norm or `fs` is far off, fix that
before trusting a lift.
