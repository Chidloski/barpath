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

All nine steps now run, on every capture — step 8 was implemented on
2026-07-30 and nothing raises. **That is coverage, not correctness.** The
reconstruction is still 5-15x outside its horizontal spec where anything can
measure it, the display axis's sign is unresolved, and 6 of 17 sets do not earn
enough axis confidence to be drawn stretched. It is being rebuilt after the
original version passed every synthetic gate and failed in the gym by two
orders of magnitude, and a completing pipeline is not a working one.

`TASKS.md` is the working list — what is done, what is not, and the measurement
behind each. `CLAUDE.md` holds the open problems. `analysis/README.md` holds the
plots and numbers.

One thing works well and is verified against video: the IMU and the video agree
on floor-impact **timing** to 11–16 ms. The same cross-modal agreement is what
calibrates the bench clock sync, which has no such landmark of its own.

Rep segmentation is the other, and it is back to **72/72** with zero false
positives. The 2026-07-30 captures broke it to 71/72 — `bench_spoto_90x5_1`
counted the re-rack as a sixth rep of a five-rep set — and C5 fixed that on
2026-07-31 along with a squat single whose window had landed on the re-rack.
Counts and window *extent* are now clean on all 17 captures. Phase used to be
unverified on both bench and squat; C9 measured bench on 2026-07-31 and **15 of
15 windows hold exactly one video chest touch**, 0.567–0.648 through the window
against a 0.0/1.0 failure mode. **Squat's phase is still unverified** — it has
no external anchor — and a window half a rep out of step has the right count,
duration and amplitude, so do not read 72/72 as more than it says.

The same 2026-07-30 session showed the video ground truth is trustworthy on
timing and horizontal but **not on vertical scale**: per-rep ROM across three
deadlifts by one lifter spreads 47.6–66.8 cm against a measured 61 cm ceiling.
See `CLAUDE.md` P1 and P2.

The sensor is not the problem, which took until 2026-07-30 to establish. On a
watch lying on a table, Core Motion's residual gyro bias is **0.002 °/s**, its
attitude holds to **0.018° over 10 s**, and the accelerometer's own bias is
**0.0025 g**. The 0.1–0.9 °/s this project spent months treating as residual
bias is the lifter's wrist rotating.

Nor is the attitude. A "2° attitude error" was inferred from a 0.035 g residual
and **retracted the same day**: that figure is a *vertical* residual converted
with the *horizontal* leak formula (0.035 g of vertical needs 15.2°, not 2°),
and it does not survive the acceleration sign fix anyway. Measured directly at
the holds bracketing a set, Core Motion's attitude is **0.05° before and 0.14°
after** 40–55 s of lifting.

What is left, per rep: bench and squat leave 0.003 g of residual acceleration —
the sensor's own noise floor — and deadlift leaves 0.010–0.030 g, three quarters
of it injected in the 200 ms around each floor impact. See `CLAUDE.md` P4, P5
and P6.

Since A3 the failure has a measurement rather than an adjective. Against the
video, per rep, on the three deadlifts: **horizontal 5.05, 9.19 and 15.44 cm rms
against a 1 cm spec, and vertical 5.24, 6.60 and 5.24 cm against ±2–3 cm.** So
5–15× out horizontally, and out on vertical too — which is new, because
"vertical comes out fine" had been repeated for a while without anyone
measuring it per rep.

C8 added bench to that list on 2026-07-31, and C10 extended it to all seven
captures: **horizontal 0.64, 0.76, 1.88, 2.63, 2.69, 2.75 and 3.67 cm.** Two of
those are inside the 1 cm spec, the first captures in this project to meet it.
Deadlift's reconstruction also disagrees with itself about which way "forward"
is on 4 of 6, 2 of 6 and 1 of 3 reps; bench does so on 1 of 29.

**But read this before any of those numbers.** C10 measured the pipeline
against the null model — drawing no fore-aft motion at all, a straight vertical
line. On **six of ten captures, including all three deadlifts, the pipeline is
worse than the flat line**: 0.13×, 0.35× and 0.70× on deadlift. Only
`bench_90x4_2` and `_3` clearly beat it, by 4×. So "5–15× outside spec" is the
generous framing; measured against doing nothing, most of the horizontal
reconstruction subtracts information rather than adding it. `metrics.vs_truth`
reports this as `beats_null` on every run.

## Quick start

    pip install -r requirements.txt      # plus ffmpeg on PATH for video
    python run.py                        # run every capture, print a report
    python run.py --plot                 # and write diagnostics to analysis/
    python run.py --truth                # and measure against the video (A3)
    python run.py --stages               # draw the pipeline stage by stage
    python run.py --paths                # step 9: the bar paths themselves
    python run.py --scorecard            # how well it performs, per lift
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
    HEARTBEAT.md               who is writing to what, right now

`HEARTBEAT.md` is not documentation, it is live state. Agents work this repo
concurrently and it is the board that keeps two of them off the same file:
claim the paths you are about to write, release them when you stop, and if
something you need is already held, do other work or stop. The rules are in
`CLAUDE.md` under **Concurrency protocol** and they are binding. Read the board
before your first write.

Nothing raises `NotImplementedError` any more. `correct.apply_offset` is
implemented but OFF by default — the wrist-to-bar offset `d` has never been
measured and B2 showed it cannot be fitted from video. The driver still reports
any stage it cannot run as blocked rather than throwing, on the principle that a
partial result you can see beats an exception.

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
spec. The reason is structural: the dominant error repeats every rep, so it
lands in the mean rep and cancels out of every deviation from it. Where truth
exists to check against, the same pipeline is 5–15× out. Self-consistency is not
accuracy, and this is the third time that has cost this project time.

Bench sharpened this on 2026-07-31 rather than softening it. The old form of the
complaint was "inside spec on lifts where nothing has ever been verified".
Bench is verified now, and dispersion still says under 2 cm on
`bench_spoto_90x5_1` while the video says 3.67 cm. The flattery was never about
the absence of a referee; it is a property of the metric.

## Validation order

Deadlift first. Not because the pipeline differs by lift — it does not — but
because it has the **best** external ground truth: the bar starts at plate
radius and ends at a tape-measurable lockout, and the floor impact gives an
unmistakable timing landmark that no other lift provides. It was the *only* lift
with any until 2026-07-31.

Bench second, and read the qualification before the number. It now tracks on
video and aligns to the IMU clock, but from a hand-placed seed whose radius
carries ~4% of scale, on 3 of 7 captures, through a sync whose accuracy is
inferred from deadlift rather than measured on bench. That is a real referee and
a weaker one; `metrics.bench_sync`'s docstring says exactly where it would
break.

Squat last, and not yet. It is now the only lift with no external horizontal
check at all — the plate leaves the top of frame at lockout, two of the four
2026-07-30 captures do not track, and `metrics.vs_truth` refuses it. What it has
is the same weak check bench had first: per-rep vertical ROM against
`truth.VERTICAL_ROM_M`, which cannot see phase and constrains one axis, but is
not self-referential. That check caught `squat_160x1` reconstructing 18 cm of a
65 cm squat at a correct rep count of 1 of 1 — a defect C5 has since fixed, and
one no count could have found.

Judging a curve by whether it looks plausible is how you convince yourself a
broken pipeline works. Two of the three lifts no longer require it.
