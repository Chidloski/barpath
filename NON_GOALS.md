# Non-goals

Binding. Do not implement, do not suggest, do not "leave a hook for".

Each of these was considered properly and rejected for a reason. The reason
is given so that the decision can be revisited on evidence rather than
re-argued from scratch.

## Estimation

| Rejected | Because |
|---|---|
| Custom attitude filter (gated accel updates) | Core Motion's is good enough once the gyro bias is removed. Revisit only if milestone 3 fails. |
| Kalman filter, factor graph, batch smoother | The per-rep linear detrend does the same job in three lines. Errors are smooth and monotonic; true motion is periodic and closes. Subtracting a line separates them. |
| B-spline or Fourier trajectory fitting | Solves a noise problem that does not exist. Double integration is a 1/n² low-pass — realistic sensor noise contributes ~1.6 mm over a rep. Fourier additionally leaks via Gibbs, since a(0) ≠ a(T). |
| Accelerometer scale-factor estimation | Cancels when reps are aligned by start point. If ever needed, it comes free from comparing integrated deadlift ROM against a tape measure. |
| Functional PCA motion prior | Needs a labelled dataset that does not exist yet, and a stiff prior erases the anomalies that are the entire point. |
| Zeroing net horizontal across the set | Redundant. Per-rep detrend already removes cumulative drift. |

## Sensing

| Rejected | Because |
|---|---|
| Phone as UWB beacon (Nearby Interaction) | Its only unique contribution was scale factor, which the tape measure supplies free. NI sessions also suspend when the watch screen sleeps, and it locks the app to Series 6+. |
| Acoustic ranging | Same, plus gym noise. |
| Second calibration pose | Separates tilt from accel bias, which manifests as a constant ramp — and the detrend already removes ramps. |
| Magnetometer / magnetic north reference | A gym is hundreds of kilos of steel. Use `.xArbitraryZVertical` and derive heading from PCA. |
| Any second sensor, bar-mounted or otherwise | The premise of the project is one wrist-worn device. |
| Camera as a runtime input | Camera is ground truth during validation only. |

## Scope

Not in this project at all: front/lateral view rendering. Live on-watch
processing. AI coaching or any ML. Accounts, sync, backend, cloud. Exercise
recognition. Rep counting as a shipped feature. Anything for lifts other
than squat, bench and deadlift. Per-exercise axis locking across sessions.
UI beyond a matplotlib figure.

## The escape hatch

If the per-rep detrend genuinely proves insufficient — meaning milestone 6
fails on synthetic data with realistic bias — **say so and stop.** Do not
build a replacement. The right response is to find out which stage is
actually wrong, and the synthetic generator exists precisely so that
question has an answer.
