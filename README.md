# barpath

Barbell path reconstruction from a wrist-worn wearable — initially developed for
an Apple Watch.

A proof of concept, which may later be incorporated into a workout app.

## Why this is hard

An accelerometer does not measure acceleration. It measures specific force,
`a - g`, so recovering motion means subtracting a gravity vector you only know
through your attitude estimate — which you are deriving from the same corrupted
stream. A 1° attitude error injects 0.17 m/s², which over a 2 s rep integrates
to about 34 cm.

Sensor *noise* is a non-problem: double integration is a 1/n² low-pass, so 50 Hz
noise is suppressed ~10⁴× relative to 0.5 Hz bar motion. Everything here is
about bias, and about exploiting the one fact you get for free — each rep begins
and ends in the same place.

## State

The pipeline does not complete. It is being rebuilt after the original version
passed every synthetic gate and failed in the gym by two orders of magnitude.

`TASKS.md` is the working list — what is done, what is not, and the measurement
behind each. `CLAUDE.md` holds the open problems. `analysis/README.md` holds the
plots and numbers.

Two things work well and are verified against video: rep segmentation (44/44
reps across 10 captures, zero false positives) and the video ground truth itself
(IMU and video agree on floor-impact timing to 11–16 ms).

The sensor is not the problem, which took until 2026-07-30 to establish. On a
watch lying on a table, Core Motion's residual gyro bias is **0.002 °/s**, its
attitude holds to **0.018° over 10 s**, and the accelerometer's own bias is
**0.0025 g**. The 0.1–0.9 °/s this project spent months treating as residual
bias is the lifter's wrist rotating, and the ~0.035 g "accel bias" seen on-wrist
is the size of a **2° attitude error**, not of a sensor bias. Whatever is wrong
is attitude, during motion — see `CLAUDE.md` P3 and P4.

Since A3 the failure has a measurement rather than an adjective. Against the
video, per rep, on the three deadlifts: **horizontal 5.1, 9.2 and 15.4 cm rms
against a 1 cm spec, and vertical 6.8, 8.7 and 3.2 cm against ±2–3 cm.** So
5–15× out horizontally, and out on vertical too — which is new, because
"vertical comes out fine" had been repeated for a while without anyone
measuring it per rep.

## Quick start

    pip install -r requirements.txt      # plus ffmpeg on PATH for video
    python run.py                        # run every capture, print a report
    python run.py --plot                 # and write diagnostics to analysis/
    python run.py --truth                # and measure against the video (A3)
    python run.py --stages               # draw the pipeline stage by stage
    pytest tests/ -q

`--stages` is the one to start with if you are new to this: `analysis/21` shows
raw acceleration turning into a bar path, one column per lift, with what each
module does to it.

`tests/test_pipeline.py` holds algebraic identities against the synthetic
generator — round trips, integration schemes — things true regardless of how
lifting behaves. `tests/test_real_data.py` holds claims about the gym, and skips
cleanly when `data/raw/` is absent.

## Layout

    src/io.py          step 0  CSV load/save, units AND sign conversion
    src/calibrate.py   step 1  gyro bias from the pre-set pause
    src/orient.py      steps 2-3  attitude correction, world frame
    src/integrate.py   step 4  double integration
    src/segment.py     step 5  rep boundaries
    src/correct.py     steps 6-7  wrist offset, per-rep detrend
    src/project.py     step 8  PCA display axis
    src/plot.py        step 9  rendering
    src/pipeline.py            the driver; run.py is the CLI
    src/metrics.py             error, measured — not a step; it judges them
    src/truth.py               video ground truth — see src/README.md
    src/synth.py               synthetic generator
    watch/                     Xcode project

`correct.apply_offset`, `project.project_to_plane` and `project.confidence`
still raise `NotImplementedError`. The driver reports them as blocked stages
rather than throwing, so the eight stages that do work still produce output.

## What this project has learned the hard way

All three cost real time, and all three are the same mistake — checking a claim
somewhere it cannot fail:

**Synthetic gates cannot catch an assumption the generator shares.** Milestones
1–6 all passed while the pipeline was unusable. `synth.py` encoded Core Motion's
acceleration sign backwards and `orient.to_world` was built to match, so the two
agreed with each other and disagreed with the watch for months. `synth.py` is
now for algebraic identities only; real captures are the referee.

**Check a convention where it is observable.** At rest `userAcceleration` is
zero, so its sign is invisible. Every check that had been run — gravity at the
calibration pause, `to_world` returning ~0 while still, the synthetic round trip
— was evaluated exactly where the term vanishes. It took video, and a 0.2 s
integration window during a moving pull, to see it.

**A metric that needs no ground truth will flatter you.** `metrics.dispersion`
measures rep-to-rep spread, which is close to what the product is about and
requires nothing external. It reports 0.7–1.3 cm on bench and squat — inside
spec, on lifts where nothing has ever been verified. The reason is structural:
the dominant error repeats every rep, so it lands in the mean rep and cancels
out of every deviation from it. Where truth exists to check against, the same
pipeline is 5–15× out. Self-consistency is not accuracy, and this is the third
time that has cost this project time.

## Validation order

Deadlift first. Not because the pipeline differs by lift — it does not — but
because it is the only lift with external ground truth: the bar starts at plate
radius and ends at a tape-measurable lockout, and the floor impact gives an
unmistakable timing landmark that no other lift provides. Bench and squat offer
nothing to check against but your own judgement of whether a curve looks
plausible, which is exactly how you convince yourself a broken pipeline works.
