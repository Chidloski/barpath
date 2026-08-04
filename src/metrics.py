"""
A3 — error metrics on real captures.

This module exists because of a specific failure. Milestones 1-6 all passed and
the pipeline was unusable in the gym, and the reason it could happen is that
nothing in the repo measured error. Every stage was judged by whether its own
output looked reasonable, which is exactly the judgement that had already been
fooled once. `tests/test_real_data.py.horizontal_residual` is the closest thing
that existed and its own docstring disclaims it: it tiles 2 s windows and
detrends each, so it conflates real bar movement with error and can only rank
two pipelines against each other.

B2, B3 and B6 are all of the form "change the error model and see whether it
helped". None of them can start without this.

Two metrics, and the difference between them is the whole point.

`dispersion` needs no truth. It measures rep-to-rep spread, which is what
CLAUDE.md says the product is actually about — a path systematically 1.5 cm
forward of truth is fine if it is consistently so.

`vs_truth` needs the video (A2) and measures absolute error against it.

**You need both, and dispersion alone will lie to you.** CLAUDE.md's spec
section spells out why: the "it's common-mode, so it cancels" argument holds
for error that is constant across a set, and fails for error correlated with
the motion. P3 is the second kind — body-frame accel bias projected through a
rotating forearm lands at rep frequency, so it repeats with the rep and the
rep-to-rep comparison preserves it perfectly. A pipeline dominated by P3 scores
*well* on dispersion. Do not report a dispersion number without saying so.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
from scipy.signal import butter, filtfilt, savgol_filter

from . import correct, markers, orient, project, segment, truth

GRID = 100          # samples per rep on the normalised-time grid

# --- bench sync constants, measured 2026-07-31 on the seven bench captures and
# --- calibrated on the three deadlifts, where the true offset is known.
# --- SYNC_MAX_LAG_S was added 2026-08-03 (C25) and is measured on eleven.
SYNC_FS = 200.0         # Hz, the grid both signals are resampled onto
SYNC_BAND = (0.15, 5.0)  # Hz. Below removes the integrator's drift, above the
#                          tremor; a bench rep is 0.3-0.7 Hz and its reversals
#                          carry the harmonics the correlation actually keys on.
# The sync is accepted or refused on the SHAPE of the correlation curve, not on
# the height of its peak. A peak-height threshold was tried first and withdrawn:
# it conflates agreement with what fraction of the clip is lifting, and bench
# clips are 20-30% reps against deadlift's 50-56%. See bench_sync's docstring.
RIVAL_FRAC = 0.70       # a local maximum this close to the peak is a real rival
RIVAL_GUARD_S = 0.4     # ...if it is at least this far from the peak
PERIOD_TOL = 0.15       # rivals must sit within this of a WHOLE rep period.
#                         Measured: all 12 rivals across the 7 bench captures
#                         land at 0.96-1.05 periods, so 0.15 is loose against
#                         the data and still rejects a half-period rival, which
#                         is the case that would actually matter.
MIN_OVERLAP_S = 2.0     # s of shared record below which a lag is not scored
MIN_OVERLAP_REPS = 3.0  # ...and it must also hold this many rep periods. You
#                         cannot identify a periodic alignment from less signal
#                         than a few periods: at 2 s a bench clip and its log
#                         match on noise, which is where the far-field failures
#                         in C25's shift experiment came from.
WIDEN_FACTOR = 1.6      # how fast the sweep grows when the peak is at the edge
STABLE_LAG_S = 0.25     # a widened peak must not move more than this when the
#                         sweep is widened once more, or it was never a peak
SYNC_MAX_LAG_S = 11.75  # s, where the lag sweep STARTS. NOT arbitrary and
#                         NOT free to grow: see bench_sync's search-window
#                         section. Too narrow and the true peak falls outside,
#                         and the sweep returns a sidelobe one rep period away
#                         without any sign that it did — which is what shipped
#                         at 5.0 and mis-synced two captures. Too wide and a
#                         distant coincidence outscores the truth. Every value
#                         in 10.00-13.50 gives the same answer on all eleven
#                         bench captures and the three deadlift controls;
#                         11.75 is the middle of that plateau.


# ------------------------------------------------------------- dispersion --
def _resample(rep: np.ndarray, n: int = GRID) -> np.ndarray:
    """One rep onto `n` points of normalised time. See dispersion's caveat."""
    u = np.linspace(0.0, 1.0, len(rep))
    grid = np.linspace(0.0, 1.0, n)
    return np.column_stack([np.interp(grid, u, rep[:, k]) for k in range(3)])


def dispersion(reps: list[np.ndarray], t: np.ndarray | None = None,
               bounds: list[tuple[int, int]] | None = None,
               n: int = GRID) -> dict:
    """Rep-to-rep spread after start alignment, in cm.

    `reps` is what `correct.detrend_set` returns: a list of (M_i, 3) arrays,
    already aligned so each starts at the origin, and of differing lengths.
    Pass `t` and `bounds` as well to get the tempo diagnostic described below.

    What this measures, and what it cannot
    --------------------------------------
    Deviation of each rep from the set's mean rep, at matched phase. This is
    the closest thing to the product: CLAUDE.md says what matters is
    rep-to-rep difference, not absolute truth.

    It is blind to any error that repeats identically every rep. That is not a
    corner case here — it is P3, the dominant suspect for the horizontal
    failure. Body-frame accelerometer bias projected through a rotating forearm
    varies at REP FREQUENCY, so it lands in the mean rep and subtracts out of
    every deviation from it. A pipeline that is wrong by a metre in a way that
    repeats will report excellent dispersion. Read `vs_truth` before believing
    a good number here.

    The judgement this encodes, and what falsifies it
    ------------------------------------------------
    Reps are compared at the same FRACTION of the rep, not at the same bar
    height and not at the same elapsed time. That conflates tempo variation
    with path variation: a rep performed slower traces the same path and still
    registers deviation, because its phase points land elsewhere.

    The alternative is to compare at matched bar height, which is what the
    overlaid plot shows and what a lifter is actually looking at — but it needs
    the concentric and eccentric split apart to stay monotonic, so it is more
    machinery than this warrants until the confound is shown to bite.

    `tempo_corr` is what would falsify the choice. It correlates each rep's
    deviation magnitude against how far that rep's duration sits from the set
    median. If it comes out strongly positive, the metric is largely measuring
    tempo and should move to matched height.

    Returns cm throughout:
        horizontal_rms, horizontal_p95   deviation magnitude in the xy plane
        vertical_rms, vertical_p95       signed z deviation, absolute
        per_axis_rms                     (3,) x, y, z separately
        worst_rep                        index of the rep furthest from the mean
        durations_s, tempo_corr          the falsification diagnostic
    """
    if len(reps) < 2:
        raise ValueError(f"dispersion needs at least 2 reps, got {len(reps)}")

    stack = np.stack([_resample(r, n) for r in reps])       # (K, n, 3)
    dev = stack - stack.mean(axis=0)                        # (K, n, 3)

    horizontal = np.linalg.norm(dev[:, :, :2], axis=2)      # (K, n)
    vertical = np.abs(dev[:, :, 2])

    out = {
        "n_reps": len(reps),
        "horizontal_rms": float(np.sqrt((horizontal ** 2).mean()) * 100),
        "horizontal_p95": float(np.percentile(horizontal, 95) * 100),
        "vertical_rms": float(np.sqrt((vertical ** 2).mean()) * 100),
        "vertical_p95": float(np.percentile(vertical, 95) * 100),
        "per_axis_rms": np.sqrt((dev ** 2).mean(axis=(0, 1))) * 100,
        "worst_rep": int(np.argmax(horizontal.mean(axis=1))),
    }

    if t is not None and bounds is not None:
        durations = np.array([t[min(b, len(t) - 1)] - t[a] for a, b in bounds])
        out["durations_s"] = durations
        spread = horizontal.mean(axis=1)
        d = np.abs(durations[:len(spread)] - np.median(durations))
        # None rather than a number, when a number would not mean anything: a
        # correlation over 3 or 4 reps is noise, and every rep running the same
        # length makes it a divide by zero. A set is 2-6 reps here, so even the
        # values this does report rest on very few points — treat a single
        # capture's tempo_corr as a hint and look across captures.
        if len(d) >= 5 and d.std() > 1e-9 and spread.std() > 1e-9:
            out["tempo_corr"] = float(np.corrcoef(d, spread)[0, 1])
        else:
            out["tempo_corr"] = None

    return out


# ------------------------------------------------------------- bench sync --
def _band(y: np.ndarray) -> np.ndarray:
    lo, hi = SYNC_BAND
    b, a = butter(2, [lo / (SYNC_FS / 2), hi / (SYNC_FS / 2)], btype="band")
    return filtfilt(b, a, y)


def bench_sync(path: dict, log: dict, velocity_z: np.ndarray,
               cadence_s: float, max_lag_s: float | None = None) -> dict:
    """Align a bench video to the IMU clock. Returns offset and correlation.

    THE PROBLEM, STATED PLAINLY
    ---------------------------
    A deadlift syncs on the floor impact: the video sees the plate land, the IMU
    sees a 15-21 g spike, and matching six of them fits an offset AND a slope
    with an 11-16 ms residual. Bench has no floor impact. Without a landmark a
    bench video is a curve with no known time alignment to the IMU, and a
    per-rep error metric against it means nothing. Solving that is the whole
    difficulty; tracking the plate is the easy half.

    WHAT THIS DOES INSTEAD
    ----------------------
    Cross-correlates the video's vertical bar velocity against the
    reconstruction's, both band-passed, and takes the lag at the peak. One
    scalar, no slope.

    WHY IT IS TRUSTED: THE DEADLIFT CONTROL
    ---------------------------------------
    The method is not asserted, it is calibrated on the one lift where the true
    offset is independently known. Run this same correlation on the three
    deadlifts and compare its peak against the offset that `truth.sync` fits
    from landings matched to floor impacts (measured 2026-07-31):

        capture             peak corr    peak lag - true lag
        deadlift_155x6_1      0.774              +3 ms
        deadlift_155x6_2      0.708             -14 ms
        deadlift_180x3        0.595             -18 ms

    **The correlation finds a known-correct offset to within 18 ms.** That is
    what licenses using it where no landmark exists. Note the correlation VALUE
    is modest even when the lag is exactly right — 0.595 on a sync that is
    correct to 18 ms — which is why the threshold is where it is.

    THE SEARCH WINDOW IS LOAD-BEARING (C25, 2026-08-03)
    ---------------------------------------------------
    `max_lag_s` bounds the sweep, and it shipped at **5.0 s** — a number nobody
    had checked against a capture. On two of the four `data_v2` benches the
    true peak sits **outside** it, at −6.37 s and −7.08 s, so the sweep
    returned the best point it could see: a sidelobe exactly one rep period
    late, at 0.44 and 0.38 of correlation against the true peaks' 0.66 and
    0.67. Both good captures were unaffected — their peaks are at −0.08 and
    −0.44 — so the failure was invisible in aggregate and total on two clips.

    **It presented as a segmentation fault, and that is the part worth
    keeping.** In `analysis/41` the IMU's first rep window held no video chest
    touch and the video's last rep fell outside every window, which reads
    exactly like a segmenter counting the un-rack and dropping the last rep.
    It is not: the segmenter had four rep-sized concentric lobes on each
    capture and chose all four, and there is no fifth candidate it could have
    missed. **A whole-period sync error and a whole-period segmentation error
    produce an identical table of touch-minus-window offsets**, so that table
    cannot tell them apart and neither can the figure drawn from it. What
    separates them is any anchor outside the periodicity — here, the
    correlation curve itself, once the sweep was wide enough to contain its
    own peak. Corrected, all 14 touches land one per window at 0.53-0.69
    through it, which independently reproduces C9's 0.567-0.648 chest-touch
    phase on a different dataset and a different tracker.

    **The window cannot just be removed, and that is the other half.** Sweep
    wider than 13.50 s and `bench_92.5x2` prefers a spurious peak at +13.59 s
    scoring **0.44 against its true peak's 0.37** — a distant coincidence that
    genuinely correlates better than the truth. At 20 s two more captures
    acquire fractional-period rivals and refuse outright. So the window is
    doing real work in both directions: wide enough to contain the true
    offset, narrow enough to exclude coincidences. Measured over all eleven
    bench captures and the three deadlift controls, **every value in
    10.00-13.50 s gives the same answer on all fourteen**; below 10.00 the
    boundary guard below starts firing and below 7.00 the two captures above
    go silently wrong. `SYNC_MAX_LAG_S` is 11.75, the middle of that plateau.

    Note the plateau's upper edge rests on one capture whose true peak is
    LOWER than a coincidence 13.6 s away. That is a thin margin, and it is a
    fact about `bench_92.5x2` rather than about the method — it is a two-rep
    set, so it has the least periodic structure to correlate.

    SO THE WINDOW IS A STARTING POINT, NOT A BOUND
    ----------------------------------------------
    A constant wide enough for eleven captures is still a bet that the twelfth
    behaves. The owner put exactly that to C25 — *what happens if there's a new
    set with a bigger lag* — and the honest answer, measured rather than
    argued, was that the constant alone is not good enough. Shifting each
    bench video's clock by 0-30 s and asking for the offset back gives, over
    121 trials:

        variant                              ok   refused   SILENTLY WRONG
        fixed 11.75 s                        39      70          12
        widen until the peak is interior     71      32          18
        ...plus the stability check          71      35          15
        ...plus a 3-rep overlap floor        72      34          15

    So widening nearly doubles the range over which the sync is RIGHT, and
    naive widening buys that by turning refusals into silent errors, which is
    the wrong direction. The two guards below pay most of that back.

    `max_lag_s=None` (the default) now means: start at `SYNC_MAX_LAG_S` and
    widen by `WIDEN_FACTOR` until the peak is interior, capped by how far these
    two records can slide and still share `need` seconds. Passing a number
    pins a single sweep, which is what the tests use to reproduce the old
    failure.

    **Where the residual 15 live, and why they are not a search problem.**
    Seven of the fifteen are `bench_92.5x2` alone. Excluding it, fixed and
    adaptive both leave **8** — identical — while correct answers roughly
    double. That capture is a two-rep set whose correlation cannot identify
    its lag once perturbed at all; it is the same capture that caps the
    plateau above. The rest sit at 25-30 s of shift, where the records barely
    share a set. **Every capture's unshifted answer is bit-identical to the
    fixed-window one**, so this changes what happens to a capture we do not
    have, and nothing about the eleven we do.

    THE TWO GUARDS
    --------------
    *Stability.* A peak found only by widening must survive one more widening,
    or it was never a peak — it was the best point inside an arbitrary box, and
    a bigger box prefers somewhere else. This is what stops naive widening
    walking onto a distant coincidence, and it is applied ONLY when widening
    happened: a peak interior to the starting window is accepted exactly as
    before, which is what keeps the eleven captures unmoved.

    *Overlap.* A lag is only scored where the records share
    `MIN_OVERLAP_REPS` rep periods. You cannot identify a periodic alignment
    from less signal than a few periods; at the old flat 2 s floor a clip and
    its log will match on noise, which is where the far-field failures were.

    AND THE PEAK MUST NOT SIT AGAINST THE BOUNDARY
    ----------------------------------------------
    The peak is required to have a full rep period of curve beyond it on both
    sides. With the default that is what triggers widening; with an explicit
    `max_lag_s` there is nowhere to widen to, so it raises.

    The reason is the acceptance rule rather than the peak. This method accepts
    because every rival above `RIVAL_FRAC` sits a whole rep period away — and a
    peak within one period of the boundary is one whose ±1 P rival is off the
    end of the sweep and cannot be looked at. Accepting there is accepting on a
    test that did not run, which is this project's recurring failure shape:
    C12's whole-clip NCC median that passed while lockout failed, C17's
    whole-clip marker residual. The guard would have caught the shipped defect
    on both captures without knowing what the right answer was.

    Measured at 11.75 s, the tightest capture (`bench_92.5x4_3`, peak −7.08 s,
    cadence 2.68 s) clears the boundary by **1.74 rep periods**, and the rest
    by 2.05-5.45.

    WHAT IT ACCEPTS ON, AND WHY NOT PEAK HEIGHT
    -------------------------------------------
    **Two peak-height thresholds were tried and both were wrong.** 0.70 came
    first, from a docstring claiming bench correlations of 0.96-1.00; measured,
    they are 0.367-0.696, so it rejected all seven captures. Then 0.55, from the
    gap between the highest bench (0.509) and the lowest known-correct deadlift
    (0.595); that admitted three of seven.

    **That gap was an artefact.** Peak height conflates two things — how well
    the signals agree, and what fraction of the record contains lifting at all,
    since the correlation runs over the whole overlap. Bench clips are 20-30%
    reps; deadlifts are 50-56%. Restrict the correlation to the rep span and
    every bench rises to 0.886-0.996 while deadlift moves only to 0.883-0.892:
    the ordering that justified 0.55 disappears. Peak height was largely
    measuring clip composition.

    Restricting is NOT the fix, and this is the useful half: **the non-rep time
    is what breaks the degeneracy.** Throw away the setup and the rest and bench
    sidelobes climb to 0.86-0.99 — `bench_90x4_1` reaches 0.985, a coin flip —
    because "align rep n with rep n" stops being distinguishable from "align rep
    n with rep n+1". Deadlift survives restriction (sidelobes 0.55-0.76) because
    it has genuinely aperiodic structure. Dilution is the price of
    identification, and it should be paid.

    So accept on the SHAPE of the curve instead. Every rival above `RIVAL_FRAC`
    of the peak must sit within `PERIOD_TOL` of a whole rep period. Measured on
    all seven captures, as offsets from the peak in units of that capture's own
    cadence:

        bench_90x4_1        2.13 s   0.80@-1.03P   0.78@+1.05P
        bench_90x4_2        2.46 s   0.80@+1.05P   0.73@-1.05P
        bench_90x4_3        2.31 s   0.75@-1.04P
        bench_92.5x2        4.55 s   0.80@+0.97P
        bench_spoto_90x5_1  2.96 s   0.81@-0.96P   0.76@+0.96P
        bench_spoto_90x5_2  3.23 s   0.82@-0.99P   0.81@+0.98P
        bench_spoto_90x5_3  2.76 s   0.80@-1.04P   0.78@+1.04P

    **Twelve rivals, seven captures, every one within 5% of exactly one rep
    period.** Bench's lag is identified modulo one rep, always, and never worse
    than that. All seven sync.

    *Re-measured at the 11.75 s window (C25); it was eleven rivals at 5.0 s,
    `bench_spoto_90x5_2`'s −0.99 P having been just off the end of the old
    sweep. The span is unchanged and the claim is one capture stronger.* The
    four `data_v2` benches add no rivals at all — none of them has a local
    maximum above `RIVAL_FRAC` of its peak, which is a cleaner curve than any
    capture this rule was written on, and their peaks run 0.45-0.88.

    WHY A WHOLE-REP AMBIGUITY IS HARMLESS FOR THE TWO THINGS IT WAS WEIGHED
    AGAINST, AND NOT IN GENERAL
    -----------------------------------------------------------------------
    Because both things measured through this sync WHEN THIS WAS WRITTEN are
    invariant to it. Horizontal rms scored at the rival lag rather than the
    peak: 3.11, 3.23 and 2.44 cm against 3.67, 2.69 and 2.63 — no worse, and
    lower on two of three. And rep-window PHASE is invariant by construction, a
    periodic set looking identical shifted by one rep; C9's three captures
    agree to 0.03 despite offsets of +0.040, -2.320 and -0.585 s.

    **Do not read that as a general licence — C24 added a quantity that is not
    invariant, and C25 found it broken.** Anything that PAIRS a video rep with
    an IMU window rather than overlaying two whole curves is destroyed by a
    whole-rep shift, because the pairing is exactly what shifts. `analysis/41`
    measures per-rep video ROM inside each IMU window, and under the one-rep
    error the first window reported **2.4 and 1.4 cm of a ~25 cm rep** — it
    covered the un-rack — while a real rep fell outside every window and was
    scored not at all. `vs_truth`'s `covered` flag and its per-rep table are in
    the same class.

    So the ambiguity is harmless where it was measured to be harmless, and the
    two invariance results above are the boundary of the claim rather than the
    claim itself. Anything new that indexes reps must be checked against a
    whole-rep shift before it is trusted, not assumed into the same box.

    A FRACTIONAL-period rival would not be harmless, and that is what this
    refuses on. None exists at the shipping window on any of the eleven bench
    captures, so **that branch is unexercised by what we sync — it is a guard,
    not a measurement.** It is not untestable, though: sweeping to 20 s gives
    `bench_90x4_2` and `bench_92.5x2` fractional rivals above `RIVAL_FRAC` and
    both refuse, so the branch is known to fire on real footage rather than
    only in principle.

    **A bench single cannot be synced by this route at all**, since a cadence
    needs two reps. That is a real limit and it raises rather than guessing.

    WHY THAT IS NOT CIRCULAR, AND WHERE IT IS
    -----------------------------------------
    It fits ONE scalar from the VERTICAL channel and the metric it enables is
    about the HORIZONTAL. A reconstruction can have correct vertical timing and
    still be centimetres out fore-aft — that is exactly the state deadlift is in,
    where vertical ROM comes out at a plausible 53-61 cm while horizontal is
    5-15x out of spec. So this does not fit the answer it is used to check.

    What it genuinely cannot see is a uniform time shift of the reconstruction:
    that is the one degree of freedom it absorbs by construction. What bounds
    the cost of getting it wrong is the sensitivity, measured 2026-07-31 by
    deliberately offsetting the fitted lag by +/-100 ms and re-scoring:

        capture               h rms swing    v rms swing
        bench_spoto_90x5_1       0.11 cm        0.83 cm
        bench_spoto_90x5_2       0.27 cm        0.63 cm
        bench_spoto_90x5_3       0.33 cm        1.00 cm

    **Quote bench horizontal freely; quote bench vertical only with this
    attached.** A tenth of a second of sync error costs a third of a centimetre
    horizontally, because the bench bar's fore-aft speed is a few cm/s — small
    against the 2.6-3.7 cm the horizontal error actually is. Vertically it costs
    up to a full centimetre against a +/-2-3 cm spec, because the bar is doing
    ~0.5 m/s, and the lag was fitted on that same channel.

    THE LOAD-BEARING ASSUMPTION
    ---------------------------
    **Bench sync's validation is TRANSFERRED from deadlift, not measured on
    bench.** The deadlift control shows the method recovers a known offset; it
    does not show that it does so on bench, and no bench capture carries an
    independent landmark to check against. The judgement being encoded is that
    a cross-correlation which is accurate to 18 ms on one lift's vertical
    velocity is accurate on another's. What would falsify it is a bench capture
    whose correlation clears 0.55 and whose lag is demonstrably wrong — which
    needs a bench video with a visible clock, a clapperboard, or any synchronous
    event in both modalities. Nothing in `data/raw/` can currently test it.

    AND THE PEAK IS ONLY WEAKLY ISOLATED ON BENCH
    ---------------------------------------------
    Measured 2026-07-31, comparing each peak against the best local maximum more
    than 0.4 s away. Deadlift's runner-up sits at **0.51-0.74** of the peak;
    bench's at **0.80, 0.81, 0.80** — outside the range where the method has
    been shown to pick correctly.

    The reason is structural and it is worth understanding rather than
    thresholding: **a bench set's sidelobes sit at multiples of the rep period**
    — measured, all eleven of them at 0.96-1.05 P. The alternative alignment
    pairs rep n with rep n+1, and touch-and-go reps resemble each other closely,
    so it genuinely does correlate almost as well. It is not noise; it is the
    set being periodic. That is why this refuses on WHERE the rivals sit rather
    than on how tall the peak is.

    What that costs is smaller than it sounds, and the reason is the one thing
    here that IS reassuring. Scoring at the runner-up lag instead of the peak
    moves per-rep horizontal rms to 3.11, 3.23 and 2.44 cm against 3.67, 2.69
    and 2.63 — **no worse, and lower on two of three.** So the horizontal number
    this function exists to enable does not depend on resolving the ambiguity.
    That is not special pleading for bench: shift a DEADLIFT by a full 3 s and
    its horizontal rms goes 5.05 -> 4.62, 9.19 -> 7.23, 15.44 -> 15.17, while
    its vertical explodes from 5.24/6.60/5.24 to 19.08/20.19/32.41. Horizontal
    rms is insensitive to gross time alignment on every lift, because the
    fore-aft signal is a few centimetres and looks much the same rep to rep.

    Two consequences, and the second is a caution about this whole metric:

    - **Quote bench horizontal.** It survives a sync error of seconds, so the
      0.55 threshold and the rep-period ambiguity are not what it rests on.
    - **`vs_truth`'s horizontal rms is not testing time alignment, on ANY lift.**
      It is a magnitude comparison between two paths that happen to be paired in
      time. Do not read agreement there as evidence that the reps line up; that
      is what `analysis/17` and the deadlift lockout-containment gate are for.

    THE RE-RACK ANCHOR, AND WHY IT IS NOT USED
    ------------------------------------------
    The obvious independent check is the re-rack: the video sees the bar stop
    dead in the J-hooks, the IMU sees a transient. That was implemented, and
    then tested on deadlift where the answer is known. It fails:

        deadlift_155x6_1    +615 ms
        deadlift_155x6_2    +660 ms
        deadlift_180x3      +510 ms

    A systematic half-second bias, in the same direction every time — the video's
    "last motion" and the IMU's "last transient above 3 g" are simply not the
    same event. On bench it appeared to disagree with the correlation by 53-706
    ms, which read as evidence against the sync; the deadlift control shows the
    disagreement is almost entirely the anchor's own error. It was removed
    rather than kept as a warning, because a check that is wrong by 0.6 s
    cannot bound a quantity that matters at 0.1 s. **Do not re-propose it
    without a way to separate the two events.** `analysis/29`.
    """
    # A precondition, checked before the expensive sweep: without a cadence
    # there is no way to tell a harmless whole-rep rival from a real one.
    if not np.isfinite(cadence_s) or cadence_s <= 0:
        raise ValueError(
            "bench sync: needs the rep cadence to tell a whole-rep ambiguity "
            "from a real one, and this capture has fewer than two reps. A "
            "bench single therefore cannot be synced by this route.")

    t_v = path["t"]
    ok = np.isfinite(path["height"])
    if ok.sum() < 100:
        raise ValueError("bench sync: the video track is too sparse to correlate")

    lo, hi = float(t_v[ok][0]), float(t_v[ok][-1])
    grid = np.arange(lo, hi, 1.0 / SYNC_FS)
    v_video = _band(np.gradient(
        np.interp(grid, t_v[ok], truth._smooth(path["height"], 9)[ok]), grid))

    t_i = np.arange(float(log["t"][0]), float(log["t"][-1]), 1.0 / SYNC_FS)
    v_imu = _band(np.interp(t_i, log["t"], velocity_z))

    need = max(MIN_OVERLAP_S, MIN_OVERLAP_REPS * cadence_s)

    def sweep(half_width: float):
        """Correlation against lag over +/-half_width. NaN where overlap is thin."""
        lags = np.arange(-half_width, half_width, 1.0 / SYNC_FS)
        curve = np.full(len(lags), np.nan)
        for j, lag in enumerate(lags):
            g = grid + lag
            m = (g >= t_i[0]) & (g <= t_i[-1])
            if m.sum() < need * SYNC_FS:
                continue
            a = v_video[m] - v_video[m].mean()
            b = np.interp(g[m], t_i, v_imu)
            b = b - b.mean()
            curve[j] = a @ b / (np.linalg.norm(a) * np.linalg.norm(b) + 1e-12)
        return lags, curve

    # How far the two records can slide and still share `need` seconds. Beyond
    # this there is nothing left to correlate, so it is the honest ceiling on
    # the search — a property of these two recordings, not a tuned number.
    reach = max(abs(t_i[0] - hi), abs(t_i[-1] - lo)) - need
    widening = max_lag_s is None
    half = SYNC_MAX_LAG_S if widening else max_lag_s
    widened = False

    while True:
        lags, curve = sweep(half)
        if not np.isfinite(curve).any():
            raise ValueError("bench sync: no lag gives enough overlap to correlate")

        pk = int(np.nanargmax(curve))
        corr, lag = float(curve[pk]), float(lags[pk])

        # The peak must have a full rep period of curve beyond it on BOTH sides,
        # or the rival test below is running on a truncated curve and cannot
        # mean what it says. This is the exact defect that shipped at 5.0 s, and
        # it presented as a segmentation fault.
        if abs(lag) + cadence_s > half:
            if not widening or half >= reach:
                raise ValueError(
                    f"bench sync: the peak is at {lag:+.2f} s, within one rep "
                    f"period ({cadence_s:.2f} s) of the +/-{half:.2f} s search "
                    f"boundary. Its whole-period rival lies outside the sweep, "
                    f"so the rule this method accepts on — every rival is a "
                    f"whole rep away — cannot be evaluated, and a peak against "
                    f"the boundary may itself be the rival of a true peak the "
                    f"sweep never saw."
                    + ("" if widening else
                       " Pass max_lag_s=None to let the sweep widen itself.")
                    + (f" Widened to the {reach:.1f} s these two records share "
                       f"and it is still against the edge; they may not cover "
                       f"the same set." if widening else ""))
            half = min(half * WIDEN_FACTOR, reach)
            widened = True
            continue

        # An interior peak inside the STARTING window is accepted as it always
        # was, which is what keeps the eleven measured captures bit-identical.
        # A peak we had to widen to find is held to a stricter test, because
        # widening is what exposes distant coincidences: it must survive one
        # more widening. If the answer moves when you look further, the lag was
        # not identified — it was the best thing inside an arbitrary box.
        if not widened or half >= reach:
            break
        lags2, curve2 = sweep(min(half * WIDEN_FACTOR, reach))
        if not np.isfinite(curve2).any():
            break
        lag2 = float(lags2[int(np.nanargmax(curve2))])
        if abs(lag2 - lag) <= STABLE_LAG_S:
            break
        raise ValueError(
            f"bench sync: the peak moved from {lag:+.2f} s to {lag2:+.2f} s "
            f"when the sweep was widened from {half:.1f} to "
            f"{min(half * WIDEN_FACTOR, reach):.1f} s, so it is not a peak — "
            f"it is the best point inside an arbitrary box, and a wider box "
            f"prefers somewhere else. The lag is not identified on this "
            f"capture and every number measured through it would be arbitrary.")

    # Every rival worth taking seriously must be a WHOLE-REP restatement of the
    # same alignment. See the docstring: that is the ambiguity this method
    # cannot resolve and does not need to.
    rivals = []
    for i in range(1, len(curve) - 1):
        if not np.isfinite(curve[i]) or abs(lags[i] - lag) <= RIVAL_GUARD_S:
            continue
        if curve[i] >= curve[i - 1] and curve[i] >= curve[i + 1] \
                and curve[i] >= RIVAL_FRAC * corr:
            k = (lags[i] - lag) / cadence_s
            rivals.append((float(lags[i]), float(curve[i] / corr), float(k)))

    stray = [r for r in rivals if abs(r[2] - round(r[2])) > PERIOD_TOL]
    if stray:
        worst = max(stray, key=lambda r: r[1])
        raise ValueError(
            f"bench sync: a rival alignment at {worst[0]:+.2f} s reaches "
            f"{worst[1]:.2f} of the peak and sits {worst[2]:+.2f} rep periods "
            f"away, not a whole number. A whole-period rival is harmless — it "
            f"is the same alignment restated — but a fractional one means the "
            f"lag is genuinely not identified, and every number measured "
            f"through it would be arbitrary.")

    return {
        "method": "vertical cross-correlation, whole-rep ambiguity permitted",
        "offset": lag,          # video t + offset = IMU t
        "corr": corr,
        "cadence_s": float(cadence_s),
        # (lag, height as a fraction of the peak, offset in rep periods)
        "rivals": rivals,
    }


# ---------------------------------------------------------------- vs truth --
TRACKERS = ("plate", "markers")


def resolve_path(video: str | Path | dict, tracker: str | None = None) -> dict:
    """Get a tracked bar path, from either referee, or accept a ready-made one.

    THIS PROJECT HAS TWO VIDEO REFEREES AND WHICH ONE APPLIES IS DECIDED BY THE
    FOOTAGE, NOT BY PREFERENCE. `truth.bar_path` matches a template to the dark
    plate and is the referee for `data/video/`. `markers.bar_path` fits a rigid
    constellation of retroreflective stickers and is the referee for `data_v2/`,
    which is filmed from a tripod with markers applied. A capture cannot be
    scored by the tracker its footage was not shot for: the template does not
    find the plate on marker-less bench reliably, and the constellation cannot
    find stickers that were never applied.

    Three ways to say which:

    * pass a **dict** — an already-tracked path from either module, used as-is.
      This is how a caller tracks once and scores several ways without paying
      for the decode twice, and how the tests feed synthetic paths in.
    * pass **`tracker=`** explicitly, one of `TRACKERS`.
    * pass **neither** and it is inferred from the location: anything under a
      `data_v2` directory is marker footage, everything else is not.

    The inference is deliberately about WHERE THE FILE IS rather than what is
    in it, because that is the fact that is actually known. Sniffing the footage
    for markers would be a second tracker running on every call and a new way to
    be wrong; the directory layout already records the answer, and `data_v2/`
    exists precisely because the capture protocol changed.

    Back-compatible by construction: a plain path outside `data_v2` resolves to
    `truth.bar_path` with its own defaults, so every pre-existing call is
    unchanged. `tests/test_video_truth.py` pins that.
    """
    if isinstance(video, dict):
        return video

    tracker = infer_tracker(video) if tracker is None else tracker
    if tracker not in TRACKERS:
        raise ValueError(f"tracker must be one of {TRACKERS}, got {tracker!r}")

    return markers.bar_path(video) if tracker == "markers" else truth.bar_path(video)


def infer_tracker(video: str | Path) -> str:
    """Which referee a clip belongs to, from where it lives.

    Split out from `resolve_path` so it can be tested without decoding a video,
    which is the only reason it is separate.
    """
    parts = {p.lower() for p in Path(video).resolve().parts}
    return "markers" if any(p.startswith("data_v2") for p in parts) else "plate"


def _video_quality(path: dict) -> dict:
    """The referee's own health, measured WHERE IT IS USED.

    Each tracker gets the statistic that means something for it, and NaN for the
    other, rather than one field that silently means two things. Both are
    top-of-travel figures over `truth.TOP_FRAC`, because lockout is where both
    referees are weakest and where C12 found the template failing while its
    whole-clip median passed.

    `top_ncc` — template only. Below `truth.GOOD_SCORE` the tracker has lost the
    plate at lockout and the fore-aft motion it reports there is invented.

    `top_residual_cm` — markers only. The constellation cannot lose the bar the
    way a template can, so what is reported is fit quality in the unit of the
    spec. Above `markers.MAX_TOP_RESIDUAL_CM` its distances near lockout are not
    good enough to referee a 1 cm target.
    """
    if "residual_px" in path:
        top = markers.top_of_travel_residual(path)
        return {"tracker": "markers", "top_ncc": float("nan"),
                "top_residual_cm": top["median_cm"]}
    return {"tracker": "plate", "top_ncc": truth.top_of_travel_score(path),
            "top_residual_cm": float("nan")}


def _video_on_imu_clock(result: dict, video: str | Path | dict,
                        tracker: str | None = None) -> tuple[np.ndarray, np.ndarray, np.ndarray, dict]:
    """Tracked bar path resampled onto the IMU clock.

    Returns (t_imu, fore_aft, height, sync_fit), NaN samples dropped.

    Two routes, because the two lifts offer different evidence.

    **Deadlift** matches the IMU's floor impacts to the video's landings. They
    are the same physical events seen by unrelated sensors, so the match fits
    offset AND slope and measures clock drift rather than assuming it: 11-16 ms
    residual, drift under 0.25%.

    **Bench** has no floor impact and therefore no such match. `bench_sync`
    aligns on vertical velocity, using a correlation calibrated against the
    deadlift offsets above. Read its docstring before quoting anything measured
    through it: it fits one scalar from the vertical channel, so bench VERTICAL
    error partly inherits that and bench horizontal does not, and its validation
    is transferred from deadlift rather than measured on bench.

    **Both routes work unchanged on a marker path, and that is a fact about the
    path dicts rather than luck.** `truth.landings` reads only `t` and `height`,
    and both trackers zero `height` at the lowest tracked point and report
    seconds from the clip start — so landings, `truth.sync`, `truth.to_imu_time`
    and `bench_sync` are all tracker-agnostic already. `markers.bar_path`
    returns a superset of `truth.bar_path`'s keys for the same reason. The only
    thing that ever had to know the difference was which tracker to call, which
    is now `resolve_path`.

    What has NOT been checked, because nothing in `data_v2/` has an IMU log
    beside it: whether a deadlift landing detected on marker footage lands at
    the same instant as one detected on template footage. The two trackers agree
    on the bar to 4.8 cm of travel against 10.7 (`analysis/37`), so a landing
    disagreement large enough to matter at 13.5 ms would be surprising — but
    surprising is not measured, and the first paired capture should test it.
    """
    log = result["log"]
    path = resolve_path(video, tracker)
    result.setdefault("_video_quality", _video_quality(path))

    if truth.lift_of(Path(result["path"]).name) == "deadlift":
        impacts = np.array([float(log["t"][k]) for k in segment.impact_anchors(log)])
        landings = truth.landings(path)
        if len(landings) < 2 or len(impacts) < 2:
            raise ValueError(
                f"cannot sync: {len(landings)} video landings against "
                f"{len(impacts)} IMU impacts, need >=2 of each")
        fit = truth.sync(landings, impacts)
        fit["method"] = "floor impacts matched to video landings"
        t_imu = truth.to_imu_time(path, fit)
    else:
        # Cadence from the IMU's own rep starts. It is used only to ask whether
        # a rival alignment is a whole rep away, so a rough median is enough —
        # and it is IMU-side, so it does not borrow anything from the video the
        # sync is being fitted against.
        starts = [float(log["t"][a]) for a, _ in result["bounds"]]
        cadence = float(np.median(np.diff(starts))) if len(starts) > 1 else np.nan
        fit = bench_sync(path, log, result["velocity"][:, 2], cadence)
        # One fitted scalar, so there is no residual and no slope, and neither
        # is claimed. Both are NaN rather than filled with a stand-in: an
        # earlier version put the re-rack disagreement in `rms_ms`, which
        # reported a bench sync as accurate to tens of ms using an anchor since
        # measured to be wrong by 0.5-0.7 s. A field that cannot be measured
        # should read NaN, not a number from somewhere else.
        fit["rms_ms"] = float("nan")
        fit["drift_pct"] = float("nan")
        fit["n"] = 1
        t_imu = path["t"] + fit["offset"]

    ok = np.isfinite(path["x"]) & np.isfinite(path["height"]) & np.isfinite(t_imu)
    return t_imu[ok], path["x"][ok], path["height"][ok], fit


def _close(arr: np.ndarray, t: np.ndarray,
           axes: tuple[int, ...] = (0, 1)) -> np.ndarray:
    """Subtract the endpoint-to-endpoint line, per column. Step 7's operation.

    Routed through correct.detrend_rep rather than reimplemented, so that when
    B3 changes what closure means this follows automatically — the point of
    applying it to the truth as well is to measure what step 7 does, and a
    private copy here would quietly stop measuring the real thing.

    `arr` is the 2-column video path (along-axis, vertical), so vertical is
    column 1 here where it is column 2 in the pipeline. If detrend_set is ever
    called with restricted axes, map them onto that layout here or this stops
    measuring the same operation.
    """
    return correct.detrend_rep(arr, 0, len(arr), t, axes=axes)


def vs_truth(result: dict, video: str | Path | dict,
             tracker: str | None = None) -> dict:
    """Reconstructed rep paths against the video, in cm. Deadlift and bench.

    `result` is a `pipeline.run` dict. **Squat still raises** — it tracks at
    median NCC ~0.40 with the plate leaving frame at lockout, and two of the
    four 2026-07-30 captures do not track at all. Returning a number from that
    would be inventing the ground truth this module exists to supply.

    Bench was refused for the same reason until 2026-07-31 and no longer is,
    but the two lifts are not equally well founded and the difference is worth
    carrying in your head when reading the output:

    - **Deadlift** syncs on floor impacts matched to video landings — two
      unrelated sensors seeing the same events, fitting offset AND slope to an
      11-16 ms residual. `sync_rms_ms` and `sync_drift_pct` are real.
    - **Bench** syncs on `bench_sync`'s vertical cross-correlation, one fitted
      scalar with no residual, on a method calibrated against deadlift rather
      than verified on bench. `sync_rms_ms` and `sync_drift_pct` are NaN, and
      that is not an omission — nothing here measures them. Three of the seven
      bench captures clear the correlation floor; the other four raise.

    READ `beats_null` BEFORE READING ANY OTHER NUMBER HERE
    ------------------------------------------------------
    `null_h_rms` is what you score by drawing **no fore-aft motion at all** —
    a straight vertical line, start-aligned, per rep. `beats_null` is that over
    the pipeline's error, so above 1 the reconstruction adds information about
    the horizontal and below 1 it subtracts it.

    Measured 2026-07-31 on every capture with video, and it is the least
    comfortable number in the project:

        bench_90x4_2         0.64 cm vs 3.08    4.80x   better
        bench_90x4_3         0.76 cm vs 3.06    4.03x   better
        bench_92.5x2         2.75 cm vs 3.13    1.14x   better
        bench_90x4_1         1.88 cm vs 2.07    1.10x   better
        bench_spoto_90x5_3   2.63 cm vs 2.42    0.92x   WORSE
        bench_spoto_90x5_2   2.69 cm vs 2.16    0.80x   WORSE
        bench_spoto_90x5_1   3.67 cm vs 2.63    0.72x   WORSE
        deadlift_155x6_1     5.05 cm vs 3.55    0.70x   WORSE
        deadlift_155x6_2     9.19 cm vs 3.23    0.35x   WORSE
        deadlift_180x3      15.44 cm vs 1.96    0.13x   WORSE

    **Six of ten, including all three deadlifts, are worse than a flat line.**
    P2's "5-15x outside spec" is measured against the spec; measured against
    doing nothing, the deadlift reconstruction is 1.4-7.9x worse than useless on
    the axis the whole project is about. Two bench captures are the only place
    the horizontal reconstruction demonstrably works.

    This check cost nothing and nobody had run it. It is the cheapest guard in
    the file against the failure this project keeps repeating — a number that
    looks like progress because it is finite.

    Three errors per rep, and the gaps between them are the point
    -------------------------------------------------------------
    `raw` — neither side closed, start alignment only. Dominated by drift
    accumulated since the beginning of the capture: the bar position entering
    rep 5 is already metres out, and subtracting its value at the rep start
    does not remove the velocity error carried in with it. This is not a
    within-rep number and should not be read as one. It is here because it is
    what the integration alone produces, and it is why step 7 exists.

    `pipeline` — the reconstruction closed exactly as the pipeline ships it,
    the video untouched. **This is the honest product error.** It is the only
    one of the three that compares what the pipeline would draw against what
    the bar actually did, and it is the number the ~1 cm spec is about.

    `closed` — step 7's line subtracted from the VIDEO as well, so both sides
    carry the same constraint. Pure shape error, with the closure's cost
    removed from both sides.

    `pipeline` minus `closed` is therefore what the closure assumption costs,
    and `video_closure` measures its premise directly: how far the tracked bar
    is from ending each rep where it started. The owner has confirmed the
    deadlift bar does not land where it was pulled from, so a non-zero
    horizontal closure is real motion that step 7 destroys. That is B3's
    evidence, and the reason the truth is never quietly detrended into
    agreement and reported alone.

    The horizontal axis, and the sign
    ---------------------------------
    The video's fore-aft is a camera axis; the reconstruction's horizontal is
    world x/y with heading unknown until step 8. So the reps are projected onto
    `project.principal_axis`, whose eigenvector sign is arbitrary and currently
    unresolved (B4). Vertical needs none of this.

    The sign is chosen ONCE for the set, from the summed correlation against
    the video, and reported as `axis_flipped`. Once, deliberately: the axis is
    a per-set quantity and step 8 will resolve its sign per set, so letting
    each rep pick its own would measure something the pipeline cannot do — and
    would flatter the result, since a rep reconstructed mirrored would be
    silently corrected instead of counted as the error it is.

    `reps_disagreeing_on_sign` then reports how many reps would individually
    have preferred the other sign. That is not a knob; it is B4 evidence. A
    non-zero count means the reconstruction's fore-aft direction is not even
    self-consistent across one set, so no per-set sign convention can be right
    for all of it.
    """
    log, bounds, reps = result["log"], result["bounds"], result["reps"]
    name = Path(result["path"]).name

    if truth.lift_of(name) == "squat":
        raise ValueError(
            f"{name}: vs_truth refuses squat. It tracks at median NCC ~0.40 "
            f"with the plate clipping the top of frame at lockout, and two of "
            f"the four 2026-07-30 captures do not track at all. Returning a "
            f"number from that would invent the ground truth this module "
            f"exists to supply. Needs a wider shot, not code. See "
            f"src/README.md.")
    if not reps:
        raise ValueError(f"{name}: no reps to compare")

    t_vid, fore_aft, height, fit = _video_on_imu_clock(result, video, tracker)

    axis = np.real(project.principal_axis(reps)[0])
    raw_pos = result["bar_position"]
    t = log["t"]

    # Pass 1: build each rep's three curves, and accumulate the evidence for
    # the SET's axis sign. Nothing is compared yet.
    windows = []
    for k, (a, b) in enumerate(bounds):
        tt = t[a:b]
        if tt[0] < t_vid[0] or tt[-1] > t_vid[-1]:
            windows.append(None)
            continue

        # Truth, on the IMU's own sample times, start-aligned like the reps.
        vid = np.column_stack([np.interp(tt, t_vid, fore_aft),
                               np.interp(tt, t_vid, height)])
        vid = vid - vid[0]

        # Reconstruction. `reps[k]` is already closed and start-aligned by
        # correct.detrend_set; raw_pos is the same window before step 7.
        recon_raw = raw_pos[a:b] - raw_pos[a]
        rec = np.column_stack([recon_raw[:, :2] @ axis, recon_raw[:, 2]])
        rec = rec - rec[0]

        # As the pipeline ships it: step 7 applied to the reconstruction only.
        pipe = np.column_stack([reps[k][:, :2] @ axis, reps[k][:, 2]])
        pipe = pipe - pipe[0]

        agree = float(np.dot(pipe[:, 0] - pipe[:, 0].mean(),
                             vid[:, 0] - vid[:, 0].mean()))
        windows.append({"k": k, "tt": tt, "vid": vid, "rec": rec,
                        "pipe": pipe, "agree": agree})

    live = [w for w in windows if w is not None]
    if not live:
        raise ValueError(f"{name}: no rep window falls inside the video's coverage")

    # One sign for the whole set — see the docstring on why not per rep.
    flip = sum(w["agree"] for w in live) < 0
    disagreeing = sum((w["agree"] < 0) != flip for w in live)

    # Pass 2: apply that one sign, then measure.
    per_rep = []
    for w in windows:
        if w is None:
            per_rep.append({"rep": len(per_rep), "covered": False})
            continue
        k, tt, vid, rec, pipe = w["k"], w["tt"], w["vid"], w["rec"], w["pipe"]
        if flip:
            rec = rec * [-1, 1]
            pipe = pipe * [-1, 1]
        closed_vid = _close(vid, tt)

        def rms(a, b):
            return float(np.sqrt(((a - b) ** 2).mean()) * 100)

        per_rep.append({
            "rep": k,
            "covered": True,
            "raw_h_rms": rms(rec[:, 0], vid[:, 0]),
            "raw_v_rms": rms(rec[:, 1], vid[:, 1]),
            "pipeline_h_rms": rms(pipe[:, 0], vid[:, 0]),
            "pipeline_h_max": float(np.abs(pipe[:, 0] - vid[:, 0]).max() * 100),
            "pipeline_v_rms": rms(pipe[:, 1], vid[:, 1]),
            "pipeline_v_max": float(np.abs(pipe[:, 1] - vid[:, 1]).max() * 100),
            "closed_h_rms": rms(pipe[:, 0], closed_vid[:, 0]),
            "closed_v_rms": rms(pipe[:, 1], closed_vid[:, 1]),
            # B3's premise, measured: how far the real bar is from closing.
            "video_closure_h": float(abs(vid[-1, 0] - vid[0, 0]) * 100),
            "video_closure_v": float(abs(vid[-1, 1] - vid[0, 1]) * 100),
            "video_rom_cm": float((vid[:, 1].max() - vid[:, 1].min()) * 100),
            "video_fore_aft_cm": float((vid[:, 0].max() - vid[:, 0].min()) * 100),
            # The null model: what you score by drawing NO fore-aft motion at
            # all. Any reconstruction that does not beat this is adding noise
            # rather than information. See `beats_null` below.
            "null_h_rms": float(np.sqrt((vid[:, 0] ** 2).mean()) * 100),
            # The curves themselves, (along-axis, up) in metres, sign already
            # applied. Carried so a plot can draw the comparison without
            # re-projecting by hand — `plot`'s module docstring records what
            # that cost last time: step 8 was on screen in two figures while
            # the stage had never executed.
            "curve_video": vid,
            "curve_pipeline": pipe,
            # The same window BEFORE step 7, sign already applied. Carried for
            # B3: an oracle over the detrend basis has to start from what the
            # detrend is handed, not from what it produced. Without this a
            # caller re-projecting `bar_position` by hand would have to
            # re-derive the axis and the set's sign, which is exactly the
            # duplication that put step 8 on screen before it ran — see
            # `plot`'s module docstring.
            "curve_raw": rec,
        })

    good = [r for r in per_rep if r["covered"]]

    def med(key):
        return float(np.median([r[key] for r in good]))

    _q = result.pop("_video_quality", {})

    return {
        "capture": name,
        "n_reps": len(bounds),
        "n_compared": len(good),
        "sync_rms_ms": fit["rms_ms"],
        "sync_drift_pct": fit["drift_pct"],
        "axis_flipped": bool(flip),
        "reps_disagreeing_on_sign": int(disagreeing),
        "axis": axis,
        "per_rep": per_rep,
        "raw_h_rms": med("raw_h_rms"),
        "raw_v_rms": med("raw_v_rms"),
        "pipeline_h_rms": med("pipeline_h_rms"),
        "pipeline_h_max": med("pipeline_h_max"),
        "pipeline_v_rms": med("pipeline_v_rms"),
        "pipeline_v_max": med("pipeline_v_max"),
        "closed_h_rms": med("closed_h_rms"),
        "closed_v_rms": med("closed_v_rms"),
        "video_closure_h": med("video_closure_h"),
        "video_closure_v": med("video_closure_v"),
        "video_rom_cm": med("video_rom_cm"),
        "video_fore_aft_cm": med("video_fore_aft_cm"),
        "null_h_rms": med("null_h_rms"),
        # >1 means the reconstruction is better than drawing a flat line; <1
        # means it is worse. Measured 2026-07-31 on all ten captures with video:
        # 4.80 and 4.03 on bench_90x4_2 and _3, 1.10-1.14 on two more benches,
        # and BELOW 1 on the other six INCLUDING ALL THREE DEADLIFTS — 0.70,
        # 0.35 and 0.13. Read that before quoting any horizontal number.
        "beats_null": float(med("null_h_rms") / med("pipeline_h_rms")),
        # Median NCC over the top 15% of travel. Below truth.GOOD_SCORE means
        # the referee lost the plate at LOCKOUT, where the bar is nearly still,
        # so the fore-aft motion it reports there is invented — and since
        # `null_h_rms` is the rms of exactly that signal, it is INFLATED and
        # `beats_null` above is correspondingly too generous. Measured on the
        # three deadlifts, restricting to well-tracked frames takes beats_null
        # from 0.70/0.35/0.13 down to 0.59/0.21/0.07. All three deadlifts fail
        # this; all seven benches pass. See truth.top_of_travel_score.
        "video_top_ncc": _q.get("top_ncc", float("nan")),
        # Markers only, NaN for the template. The constellation cannot lose the
        # bar the way a template can, so this is fit quality rather than a
        # tracking failure — reported in cm because that is the unit of the spec
        # it is refereeing. See markers.top_of_travel_residual.
        "video_top_residual_cm": _q.get("top_residual_cm", float("nan")),
        # Which referee produced the numbers above. `data/video/` has no markers
        # and `data_v2/` is filmed for them, so this is decided by the footage.
        "video_tracker": _q.get("tracker", "plate"),
        # The referee, checked against the same table as the reconstruction.
        # Non-empty means this capture's video vertical scale is wrong and its
        # vertical numbers — video_rom_cm, pipeline_v_rms, raw_v_rms — carry it.
        # Horizontal and sync are not implicated. See truth.VERTICAL_ROM_M.
        "video_rom_flags": truth.rom_flags(
            truth.lift_of(name), [r["video_rom_cm"] / 100 for r in good]),
    }


# ------------------------------------------------------- momentum closure --
def _video_zero_dwells(t: np.ndarray, v: np.ndarray, v_thresh: float,
                       min_dwell_s: float) -> np.ndarray:
    """Midpoints of every interval where the video says the bar is not moving.

    A DWELL, not an instant. The bar passes through zero velocity at the bottom
    of every touch-and-go rep too, and those are useless here: at a turnaround
    the acceleration is at its largest, so an endpoint placed there moves by
    a*dt for a sync error of dt and the measurement inherits the sync. A dwell
    is flat by construction — shift the clock inside it and v is still ~0 — so
    the endpoint survives the sync error the bench correlation cannot rule out.
    Measured: +/-100 ms of deliberate sync error moves the bench figure from
    0.102 to 0.090/0.127 m/s, and only at +/-200 ms does it break (0.44).
    """
    slow = np.abs(v) < v_thresh
    out, i = [], 0
    while i < len(slow):
        if not slow[i]:
            i += 1
            continue
        j = i
        while j + 1 < len(slow) and slow[j + 1]:
            j += 1
        if t[j] - t[i] >= min_dwell_s:
            out.append(0.5 * (t[i] + t[j]))
        i = j + 1
    return np.array(out)


def momentum_closure(result: dict, video: str | Path | dict,
                     v_thresh: float = 0.10, min_dwell_s: float = 0.20,
                     tracker: str | None = None) -> dict:
    """Vertical impulse between two moments the bar is known to be still.

    THE IDENTITY
    ------------
    Between two instants where the bar's velocity is zero, the integral of its
    vertical acceleration must be zero. No model, no assumption about lifting,
    nothing tunable — it is the definition of acceleration. Whatever the
    reconstruction leaves here is error, and unlike every other number in this
    module it is not scored against a distance the video has to measure
    correctly.

    **This is immune to the defect that flags half the vertical numbers in this
    project.** `truth.VERTICAL_ROM_M` catches the video's per-capture vertical
    SCALE being wrong by up to 20%. A scale error cannot move a zero crossing,
    so the video is used here only to say WHEN the bar was still, never how far
    it went. A flagged capture's closure is quotable; its ROM is not.

    WHY THE ENDPOINTS COME FROM THE VIDEO
    -------------------------------------
    `segment.rest_instants` places them from raw acceleration and gyro alone,
    which is what a CORRECTION must do. It only works where there is a floor
    impact to seed the search, so it is deadlift-only, and the deadlift-only
    measurement it supports could never say whether the deficit was the impact
    or the pipeline.

    Bench has no raw-signal anchor and cannot be given one. A bar descending at
    constant velocity reads |a| = g with a quiet gyro, exactly as a bar at rest
    does — that ambiguity is inertial sensing itself, not a detector that needs
    work. Measured: seeding the same score-minimum search from bench rep
    boundaries lands 7 of 34 anchors mid-descent at 0.4-0.5 m/s.

    The remaining candidate was the reconstruction's own rep boundaries, and
    that is circular in the exact way that matters: `segment` places them at
    zero crossings of the integrated velocity, so the integral between two of
    them is near zero by construction and the test would pass on a pipeline
    with any amount of drift. The video is the only endpoint source that is
    neither unavailable nor question-begging.

    That makes this a DIAGNOSTIC, not a correction. Nothing in the pipeline may
    call it.

    WHAT IT MEASURED, 2026-07-31
    ----------------------------
    Ten captures, 61 intervals, identical treatment for both lifts:

        bench, lifting            44 intervals   median -0.013   |dv| <= 0.102
        deadlift, pull only        8 intervals   median -0.010   |dv| <= 0.063
        deadlift, impact inside    9 intervals   median -0.589   -1.43 .. -0.36

    **The deficit is the floor impact and nothing else.** Nine of nine
    impact-spanning intervals lose vertical impulse and every one is negative,
    while 52 intervals of loaded lifting without one scatter around zero. As a
    residual acceleration: 0.0019 g on bench, 0.0008 g on the deadlift pulls,
    both at the 0.0025 g accel bias measured on a table, against 0.0300 g
    across an impact.

    **The middle row is the strongest of the three and it took two wrong
    readings to see it.** Those eight intervals run floor to lockout — 55-66 cm
    of bar travel by the video, a full loaded pull — and they are in the SAME
    CAPTURES as the nine that fail. Same lift, same load, same wrist, same
    calibration. The dwell detector splits a deadlift rep at the lockout, so
    the concentric and the descent-plus-landing are measured separately, and
    only the half with the landing in it loses anything. That is a within-
    capture control, which the bench-versus-deadlift comparison this was built
    to make is not. (They were first misread as the bar resting on the floor,
    on a max-|accel| of 0.6-1.1 g. A 155 kg pull is gentle: the wrist's total
    acceleration barely leaves 1 g, so that number does not distinguish pulling
    from resting. The video's bar travel does.)

    Bench then confirms it independently, on a lift with no landing anywhere in
    it, and is what rules out "deadlift descents are simply harder to
    reconstruct than deadlift pulls".

    This is P6's horizontal result (bench and squat 0.003 g, deadlift
    0.010-0.030 g) reproduced on the vertical axis, on a quantity with no
    tunable in it, with the cause isolated rather than inferred.

    Durations rule out the obvious confound: the closing intervals run
    1.04-3.09 s against the failing ones' 1.60-3.42, so they do not pass by
    being short.

    WHERE IT ENTERS, AND WHY B5 IS NOT CONTRADICTED
    -----------------------------------------------
    Split each impact-spanning interval at the impact and compare against the
    video on both sides. Before the impact the reconstruction tracks the
    video's descent velocity to +0.14..+0.71 m/s — small, and POSITIVE, the
    opposite sign to the deficit. The error in the step across the impact is
    -0.11..-1.54 m/s and tracks the interval total. The deficit is injected at
    the impact; it does not accumulate through the descent.

    That sits alongside B5's velocity-step ratio of 1.04 rather than against
    it, and the distinction is the useful part. B5 measures min-to-max
    AMPLITUDE within +/-0.3 s, and deliberately so — its docstring warns off
    net-change windows. Measured both ways on the same 15 impacts: amplitude
    ratio median 1.10, net-change ratio median 0.41.

    **The spike's size is captured. Where the velocity settles afterwards is
    not.** B6 found the mechanism already — several hundred ms of ringing as
    the watch keeps moving after the bar stops — and this says the ringing is
    not cosmetic: it is the whole deficit. A net-change ratio measured at a
    fixed offset oscillates with the ring (0.72, 0.49, 0.76, 0.54 at 50, 100,
    150, 200 ms), which is why B5 was right to refuse that window and why the
    quantity to fix is the settled velocity, not the peak.

    Returns per-interval detail plus medians. `spans_impact` is False on every
    bench interval because `segment.impact_anchors` correctly returns [] there.

    One assumption, shared with step 6 and `rest_instants`: the video sees the
    BAR and this integrates the WATCH. They are the same rest only where the
    hand is on the bar, which it is at a bench lockout and at a touch-and-go
    floor rest. It would not be after the lifter lets go, and the final impact
    of a set is excluded for other reasons anyway.
    """
    log = result["log"]
    t = log["t"]
    world = orient.to_world(log["accel"], log["quat"], log["quat"])

    t_imu, _, height, fit = _video_on_imu_clock(result, video, tracker)
    v_video = np.gradient(savgol_filter(height, 9, 3), t_imu)

    bounds = result["bounds"]
    first, last = float(t[bounds[0][0]]), float(t[bounds[-1][1] - 1])
    mids = _video_zero_dwells(t_imu, v_video, v_thresh, min_dwell_s)
    mids = mids[(mids >= first - 0.5) & (mids <= last + 0.5)]
    if len(mids) < 2:
        raise ValueError(
            f"{Path(result['path']).name}: {len(mids)} video dwells inside the "
            f"rep span, need >=2. Nothing here can be measured without two "
            f"moments the bar is known to be still.")

    idx = [int(np.searchsorted(t, m)) for m in mids]
    impacts = segment.impact_anchors(log)

    intervals = []
    for a, b in zip(idx, idx[1:]):
        intervals.append({
            "t_start": float(t[a]),
            "duration_s": float(t[b] - t[a]),
            # The whole measurement. Must be zero; is not.
            "dv": float(np.trapezoid(world[a:b, 2], t[a:b])),
            "spans_impact": any(a <= k < b for k in impacts),
        })

    dv = np.array([iv["dv"] for iv in intervals])
    spans = np.array([iv["spans_impact"] for iv in intervals])
    return {
        "capture": Path(result["path"]).name,
        "sync_offset": fit["offset"],
        "n_intervals": len(intervals),
        "intervals": intervals,
        "median_dv": float(np.median(dv)),
        "max_abs_dv": float(np.abs(dv).max()),
        "median_dv_with_impact": (float(np.median(dv[spans]))
                                  if spans.any() else float("nan")),
        "median_dv_no_impact": (float(np.median(dv[~spans]))
                                if (~spans).any() else float("nan")),
        "n_with_impact": int(spans.sum()),
    }


# ------------------------------------------------------------------ report --
def summary(disp: dict | None = None, truth_result: dict | None = None) -> str:
    """The metrics, as text for pipeline.summary. Carries its own caveats."""
    lines: list[str] = []

    if disp is not None:
        lines.append(
            f"  dispersion  horizontal {disp['horizontal_rms']:.1f} cm rms "
            f"(p95 {disp['horizontal_p95']:.1f}), vertical "
            f"{disp['vertical_rms']:.1f} cm rms, {disp['n_reps']} reps")
        tc = disp.get("tempo_corr")
        if tc is not None and abs(tc) > 0.7:
            lines.append(
                f"  CAVEAT  dispersion correlates {tc:+.2f} with rep duration — "
                f"it is measuring tempo as much as path. Compare at matched bar "
                f"height instead; see the docstring.")
        lines.append(
            "  CAVEAT  dispersion cannot see error that repeats every rep, "
            "which is what P3 is. A good number here is not a working pipeline.")

    if truth_result is not None:
        r = truth_result
        lines.append(
            f"  vs video    {r['n_compared']}/{r['n_reps']} reps, sync "
            f"{r['sync_rms_ms']:.0f} ms, video ROM {r['video_rom_cm']:.0f} cm / "
            f"fore-aft {r['video_fore_aft_cm']:.1f} cm")
        if r.get("video_rom_flags"):
            lines.append(
                f"    FLAGGED  the VIDEO fails the ROM bound on "
                f"{len(r['video_rom_flags'])}/{r['n_compared']} reps "
                f"({r['video_rom_flags'][0]}). Its vertical scale is wrong on "
                f"this capture, so every vertical number below is measured "
                f"against a bad ruler and must not be quoted unqualified. "
                f"Horizontal and sync are unaffected; see truth.VERTICAL_ROM_M.")
        lines.append(
            f"    AS SHIPPED  horizontal {r['pipeline_h_rms']:.1f} cm rms / "
            f"{r['pipeline_h_max']:.1f} cm max, vertical "
            f"{r['pipeline_v_rms']:.1f} cm rms / {r['pipeline_v_max']:.1f} cm max"
            f"   <- the spec is 1 cm horizontal")
        lines.append(
            f"    no closure  horizontal {r['raw_h_rms']:.0f} cm, vertical "
            f"{r['raw_v_rms']:.0f} cm   (drift since the capture began; why "
            f"step 7 exists)")
        lines.append(
            f"    shape only  horizontal {r['closed_h_rms']:.1f} cm, vertical "
            f"{r['closed_v_rms']:.1f} cm   (step 7 applied to the video too)")
        lines.append(
            f"    the real bar misses closing by {r['video_closure_h']:.1f} cm "
            f"horizontally, {r['video_closure_v']:.1f} cm vertically — step 7 "
            f"forces that to zero, so it is destroying real motion (B3)")
        if r["axis_flipped"]:
            lines.append(
                "  NOTE  the PCA axis pointed backwards and was flipped to "
                "match the video — project.principal_axis does not resolve "
                "its sign (B4), so the drawn path would have been mirrored")
        if r["reps_disagreeing_on_sign"]:
            lines.append(
                f"  NOTE  {r['reps_disagreeing_on_sign']}/{r['n_compared']} reps "
                f"individually favour the OPPOSITE fore-aft sign — the "
                f"reconstruction is not self-consistent across one set, so no "
                f"per-set sign convention can be right for all of it (B4)")

    return "\n".join(lines)
