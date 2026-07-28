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
(IMU and video agree on floor-impact timing to 11–16 ms). The horizontal axis —
the one the spec is actually about — is still drift-dominated by an order of
magnitude.

## Quick start

    pip install -r requirements.txt      # plus ffmpeg on PATH for video
    python run.py                        # run every capture, print a report
    python run.py --plot                 # and write diagnostics to analysis/
    pytest tests/ -q

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
    src/truth.py               video ground truth — see src/README.md
    src/synth.py               synthetic generator
    watch/                     Xcode project

`correct.apply_offset`, `project.project_to_plane` and `project.confidence`
still raise `NotImplementedError`. The driver reports them as blocked stages
rather than throwing, so the eight stages that do work still produce output.

## What this project has learned the hard way

Both of these cost real time, and both are the same mistake:

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

## Validation order

Deadlift first. Not because the pipeline differs by lift — it does not — but
because it is the only lift with external ground truth: the bar starts at plate
radius and ends at a tape-measurable lockout, and the floor impact gives an
unmistakable timing landmark that no other lift provides. Bench and squat offer
nothing to check against but your own judgement of whether a curve looks
plausible, which is exactly how you convince yourself a broken pipeline works.
