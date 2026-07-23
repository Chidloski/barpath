# barpath

Barbell path reconstruction from a single Apple Watch IMU.

Proof of concept: can one wrist-worn sensor produce a bar path good enough
that a lifter can see form anomalies in it? Not an app. Not yet.

## Why this is hard

An accelerometer does not measure acceleration. It measures specific force,
`a - g`, so recovering motion means subtracting a gravity vector you only
know through your attitude estimate — which you are deriving from the same
corrupted stream. A 1° attitude error injects 0.17 m/s², which over a 2 s
rep integrates to about 34 cm.

Sensor *noise* is a non-problem: double integration is a 1/n² low-pass, so
50 Hz noise is suppressed ~10⁴× relative to 0.5 Hz bar motion. Everything
here is about bias, and about exploiting the one fact you get for free —
each rep begins and ends in the same place.

## Quick start

    pip install -r requirements.txt
    python src/synth.py            # generate a set, print its dimensions
    pytest tests/ -v               # milestone gates

Gates 1–2 pass out of the box. The rest fail until the reserved modules in
`src/` are implemented — that is the intended working loop. Pick the first
failing test, make it pass, commit.

## Layout

    src/synth.py       known bar path -> corrupted IMU log   [keystone]
    src/io.py          CSV load/save, timestamp handling
    src/calibrate.py   step 1  gyro bias from the pre-set pause
    src/orient.py      steps 2-3  attitude correction, world frame   *
    src/integrate.py   step 4  double integration                    *
    src/segment.py     step 5  stillness detection, rep boundaries
    src/correct.py     steps 6-7  wrist offset, per-rep detrend      *
    src/project.py     step 8  PCA display axis                      *
    src/plot.py        step 9  rendering
    watch/             Xcode project (milestone 7)

    * written by the project owner, not by an assistant — see CLAUDE.md

## Development order

Everything through milestone 6 runs on synthetic data. No watch, no gym, no
barbell. Build against known ground truth first, because on real data you
can only tell that something is wrong, never what.
