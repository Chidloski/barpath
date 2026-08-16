"""The product view — smoothing, speed colour and the average rep.

Everything upstream of this file answers "where was the bar". This file answers
"what should a gym-goer be shown", and those are different questions with
different tolerances. Nothing here changes the reconstruction: it consumes
`pipeline.run`'s `planar` (or `vs_truth`'s `curve_pipeline`) and returns curves
to draw. Run it on the video's tracked path and it does exactly the same thing,
which is how every claim below is checked.

Three things the app wants and the pipeline does not supply:

1. **A simplified path.** The raw per-rep curve carries 100 Hz sensor detail
   nobody can read and, on this corpus, a good deal of invented fore-aft. A
   plot of it looks like a diagnostic, not a coaching cue.
2. **Speed within the rep**, because "how fast did the bar move, and how much
   did the set slow down" is most of what a bar-path display is for once the
   shape is legible.
3. **One average path**, with the odd rep left out, so a set reads as a set
   rather than as six overlaid squiggles.

The currency for smoothing, and why it is not "window = 15 samples"
-------------------------------------------------------------------
Four smoothers with four different parameters cannot be compared, so `strength`
here is **the fraction of the rep the kernel spans**, and every method converts
it to its own units. A rep is 2-6 s in this corpus, so strength 0.10 is a
~0.3-0.6 s window whichever smoother you pick. That makes the sweep in
`analysis/64` a comparison of METHODS at matched span, rather than a comparison
of arbitrary constants.

It is a nominal currency, not a measured one — a boxcar and a Savitzky-Golay
filter of the same span do not attenuate the same frequencies. The measured
currency is `truth_cost`: run the smoother on the VIDEO path and ask how far it
moved the real bar. That is the number which says when smoothing has started
destroying form rather than noise, and it is the one to plot against.

What the shipped defaults are, and what chose them
---------------------------------------------------
Measured on the 13 refereed `data_v2` captures, 61 reps, against the video put
through the identical treatment (`analysis/64`, `analysis/65`):

* **`savgol`, `strength = 0.20`.** Savitzky-Golay costs the real bar less than
  the other three at EVERY level tried — at strength 0.20 its 90th-percentile
  distortion of the video path is 0.17 cm horizontal and 0.65 cm vertical,
  against a boxcar's 0.50 and 2.79. The level is the strongest one whose
  worst-case cost stays inside half of each axis's spec (0.5 cm of the 1 cm
  horizontal, 1.0 cm of the +/-2-3 cm vertical). At 0.30 the vertical fails
  that rule at 1.24 cm, because a smoother long enough to help visibly is long
  enough to start rounding off the lockout.
* **`turnaround` alignment, `median` averaging.** Alignment is the whole
  result: against the video's own average rep, turnaround alignment scores
  1.52 cm horizontal and 3.00 vertical where time alignment scores 1.64 and
  **8.30**. The averager barely matters (mean 1.56, median 1.52, trimmed 1.52),
  so the median ships because it is free insurance.

**Smoothing does not change accuracy, at all.** Median horizontal error against
the video is 2.07 cm unsmoothed and 2.07 cm at every method and every level up
to 0.30. That is not a null result, it is a diagnosis: the reconstruction's
horizontal error is entirely at rep frequency (P3), so there is no
high-frequency component for a smoother to remove. Smoothing here buys
legibility and costs accuracy nothing — and it fixes nothing either.

**Averaging DOES change accuracy**, which smoothing does not: the average rep
lands at 1.52 cm against the video's average where a single rep is 1.95 cm
against its own (medians over the 13 captures). Roughly a fifth of the per-rep
error is rep-to-rep scatter
that averaging cancels, which is the same "rep-to-rep difference is the
product" argument the spec is built on, arriving from the other direction.

What the video corroborates, and what it refuses
-------------------------------------------------
Every quantity this file offers was scored against the video on all 61 reps
before it was offered. Correlation, median absolute error, and whether the two
records rank the reps of a set the same way:

    quantity                r        median err    within-set ranking
    mean concentric vel   +0.970      0.020 m/s     13 of 13
    concentric duration   +0.977      0.020 s       13 of 13
    peak speed            +0.974      0.022 m/s     11 of 13
    turnaround phase      +0.900      0.012 rep     10 of 13
    vertical ROM          +0.989      3.7 cm         9 of 13
    ---------------------------------------------------------------
    fore-aft SWEEP        -0.031      2.2 cm         8 of 13
    stall phase           +0.28       degenerate    undefined

The within-set column is the sharper test and is the reason it is there:
a correlation over 61 reps can be carried entirely by the three lifts having
different tempos, and it is rep-to-rep difference INSIDE one set that the
product claims to show. Chance agreement on the worst rep is 22%.

The line in that table is the design of the whole display. **Everything about
tempo and vertical travel agrees with the video; nothing about fore-aft
MAGNITUDE does.** So the path is drawn with its horizontal axis unlabelled
(which `plot.py` already required for a different reason), the speed colour is
scaled within the rep rather than to an absolute scale, and neither
`fore_aft_m` nor a sticking-point cue is offered as a number to a user.
`stall_phase` was built, measured at r = +0.28 with its argmin sitting on a
window edge most of the time, and removed rather than shipped with a caveat.

What this file must not be read as fixing
------------------------------------------
Smoothing cannot recover information. On a capture where the horizontal channel
is worse than a flat line (P2 — every deadlift here), a smoothed path is a
prettier wrong answer, and `truth_cost` will happily stay small while
`fidelity` sits at 5 cm. The honest use of the sweep is to pick the strongest
smoothing that costs the real bar nothing, and then to read the accuracy
numbers separately and unflattered.
"""

from __future__ import annotations

import numpy as np
from scipy.interpolate import LSQUnivariateSpline
from scipy.ndimage import gaussian_filter1d, uniform_filter1d
from scipy.signal import savgol_filter

# The phase grid every rep is resampled onto before it can be averaged or
# compared. 100 points over a 2-6 s rep is 20-50 Hz of retained phase
# resolution, which is finer than any smoothing level worth shipping, so the
# grid is never the limiting factor.
GRID = 100

METHODS = ("boxcar", "gaussian", "savgol", "spline")

# The shipped display defaults. Chosen by the sweep in `analysis/64`, under a
# rule written down before the level was picked: the strongest smoothing whose
# 90th-percentile distortion of the VIDEO path stays inside half of each
# axis's spec. The METHOD ordering does not depend on that rule — savgol costs
# least at every level tried — so only the number 0.20 is the rule's to defend.
SMOOTH_METHOD = "savgol"
SMOOTH_STRENGTH = 0.20


# --------------------------------------------------------------------------
# 1. smoothing
# --------------------------------------------------------------------------

def _span_samples(t: np.ndarray, strength: float) -> int:
    """`strength` as a whole number of samples, odd, at least 3.

    Taken as a fraction of the rep's SAMPLE COUNT rather than of its duration,
    which is the same thing at a constant rate and is the right thing when the
    rate wobbles — the watch does not always honour the requested rate, and a
    kernel specified in seconds would then span a different number of samples
    at each end of a capture.
    """
    n = len(t)
    w = int(round(strength * n))
    if w % 2 == 0:
        w += 1
    return max(3, min(w, n if n % 2 else n - 1))


def smooth(curve: np.ndarray, t: np.ndarray, method: str = SMOOTH_METHOD,
           strength: float = SMOOTH_STRENGTH) -> np.ndarray:
    """One (M, 2) rep curve, smoothed. Columns are (along-axis, vertical).

    `strength` is the fraction of the rep the kernel spans; see the module
    docstring for why that and not a sample count. Both columns get the same
    treatment — smoothing the horizontal harder than the vertical would change
    the SHAPE of the path, which is the one thing the display exists to show.

    The four methods, and what each is actually for:

    * `boxcar` — a moving average. The obvious thing, and the one that blunts
      turnarounds worst: it is a rectangular window, so it has the ugliest
      frequency response of the four and it flattens the peak of every rep.
      Kept in the sweep as the baseline anyone would write first.
    * `gaussian` — the same idea with a kernel that does not ring. `sigma` is
      set to a quarter of the span so that +/-2 sigma covers it.
    * `savgol` — least-squares quadratic over the window. It is the one that
      preserves an extremum's height, because a parabola can represent a peak
      and a constant cannot, which matters here: the top and bottom of the rep
      are where the lifter's attention goes.
    * `spline` — a least-squares cubic B-spline with knots spaced `strength`
      apart. Not a filter at all but a re-description: the output is a smooth
      curve with a handful of degrees of freedom, which is the closest thing
      here to "a simplified view" in the sense the brief asks for.

    Edges: the two `ndimage` filters hold the end sample (`mode="nearest"`)
    rather than reflecting it, because a rep window starts and ends at a
    turnaround where the bar really is nearly still, and mirroring there
    invents a reversal that did not happen. `savgol` extrapolates its own fit
    instead, for a reason measured rather than argued — see below.
    """
    curve = np.asarray(curve, dtype=float)
    if curve.ndim != 2 or curve.shape[1] != 2:
        raise ValueError(f"expected an (M, 2) curve, got {curve.shape}")
    if strength <= 0:
        return curve.copy()

    w = _span_samples(t, strength)
    if method == "boxcar":
        return np.column_stack([uniform_filter1d(curve[:, i], w, mode="nearest")
                                for i in range(2)])
    if method == "gaussian":
        return np.column_stack([gaussian_filter1d(curve[:, i], w / 4.0,
                                                  mode="nearest")
                                for i in range(2)])
    if method == "savgol":
        # polyorder must be under the window; at the shortest windows this
        # degrades to a straight-line fit, which is the correct behaviour.
        #
        # `interp` rather than `nearest`, and it is the one edge choice here
        # that was decided by measurement: it fits the polynomial to the end
        # window and evaluates it, instead of padding with a repeated sample.
        # On the 61 refereed reps that takes the 90th-percentile vertical cost
        # to the real bar from 0.835 cm to 0.651 (`mirror` is worse still at
        # 1.443). It also makes savgol and `spline` the only two methods that
        # reproduce a straight line EXACTLY — a padded filter cannot, because
        # the pad is not on the line — which matters on the horizontal axis,
        # where bending a straight path is inventing a fault.
        return np.column_stack([savgol_filter(curve[:, i], w, min(2, w - 1),
                                              mode="interp")
                                for i in range(2)])
    if method == "spline":
        return _spline(curve, strength)
    raise ValueError(f"unknown smoothing method {method!r}; have {METHODS}")


def _spline(curve: np.ndarray, strength: float) -> np.ndarray:
    """Least-squares cubic B-spline, knots spaced `strength` of the rep apart.

    Fitted against the sample index rather than time so that it matches the
    other three methods' currency exactly. Falls back to the input when the rep
    is too short to carry even one interior knot, rather than raising: a display
    layer that throws on a short rep is worse than one that draws it unsmoothed.
    """
    n = len(curve)
    x = np.arange(n, dtype=float)
    n_knots = max(0, int(round(1.0 / strength)) - 1)
    if n_knots == 0 or n < 8:
        return curve.copy()
    knots = np.linspace(0, n - 1, n_knots + 2)[1:-1]
    out = np.empty_like(curve)
    for i in range(2):
        out[:, i] = LSQUnivariateSpline(x, curve[:, i], knots, k=3)(x)
    return out


# --------------------------------------------------------------------------
# 2. speed
# --------------------------------------------------------------------------

def speed(curve: np.ndarray, t: np.ndarray, smooth_strength: float = 0.05
          ) -> np.ndarray:
    """Speed along the path, m/s, one value per sample.

    Differentiated from the DISPLAYED curve rather than taken from
    `pipeline.run`'s `velocity`, and the reason is a display argument rather
    than a physics one: the colour has to agree with the line it is painted on.
    Take the velocity from the integrator and a smoothed path is coloured by a
    speed it does not have — a stall the eye can see in the geometry would be
    painted fast. It also means the same function colours the video path,
    which is what makes the two comparable at all.

    The cost is that differentiation amplifies whatever the smoother left, so
    the derivative gets a light second pass of its own. `smooth_strength` is in
    the same currency as `smooth`.

    This is 2D speed in the display plane, so it is dominated by the vertical.
    On this corpus that is the right dominance — the fore-aft channel is the
    one that is 5-15x outside spec (P2), and a speed colour driven by it would
    be colouring noise.
    """
    curve = np.asarray(curve, dtype=float)
    t = np.asarray(t, dtype=float)
    v = np.gradient(curve, t, axis=0)
    s = np.hypot(v[:, 0], v[:, 1])
    if smooth_strength > 0 and len(t) > 4:
        s = gaussian_filter1d(s, _span_samples(t, smooth_strength) / 4.0,
                              mode="nearest")
    return s


def turnaround(curve: np.ndarray) -> int:
    """Index of the rep's turnaround, without being told which lift it is.

    The furthest the bar gets, vertically, from where the window started. A
    bench window runs top -> chest -> top so that is the bottom; a deadlift
    window runs floor -> lockout -> floor so it is the top. Naming the lift
    would work too and would be one more place for the lift to be named wrong.

    Returns an interior index: a rep whose extreme is at an endpoint is a
    window that spans half a rep, and clamping keeps the callers below from
    dividing by zero rather than hiding it — `rep_stats` reports the phase so a
    degenerate window is visible in the output.
    """
    z = np.asarray(curve, dtype=float)[:, 1]
    i = int(np.argmax(np.abs(z - z[0])))
    return int(np.clip(i, 1, len(z) - 2))


CONCENTRIC_V_MIN = 0.05


def concentric(curve: np.ndarray, t: np.ndarray,
               v_min: float = CONCENTRIC_V_MIN) -> tuple[int, int]:
    """The window's ascent: the longest run where the bar is actually going up.

    **The obvious definition — lowest point to highest point — is the one this
    replaced, and replacing it is worth more than any other line in this file.**
    Measured against the video on all 61 refereed reps, mean concentric velocity
    under the extremes definition agrees at r = +0.53, and within a set it ranks
    the reps in the same order on only 8 of 13 captures. Under this one it is
    **r = +0.971, median error 0.020 m/s, and the within-set ranking agrees on
    13 of 13.** Same paths, same smoothing, same video: the entire disagreement
    was the boundary, not the instrument.

    The mechanism is why it generalises. A paused squat or a spoto bench sits
    still at the bottom for a second or more, so the lowest SAMPLE in that dwell
    is picked out by noise — a millimetre of wobble moves it half a second, and
    half a second on a 1.7 s ascent is a 30% error in the denominator. A
    velocity threshold does not care where inside the dwell the true minimum is,
    because the dwell is below the threshold either way.

    `v_min` sits on a broad plateau: 0.02 to 0.12 m/s all give r >= 0.959 and a
    median error of 0.016-0.021 m/s, so it is a round number in the middle of a
    6x range rather than a tuned constant. Falls back to the extremes when
    nothing clears the threshold, which is what a rep spanning half a window
    looks like — that is a segmentation defect and the fallback keeps it
    visible rather than raising on it.
    """
    curve = np.asarray(curve, dtype=float)
    t = np.asarray(t, dtype=float)
    z = curve[:, 1]
    rising = np.gradient(z, t) > v_min
    if rising.sum() >= 3:
        idx = np.flatnonzero(rising)
        runs = np.split(idx, np.flatnonzero(np.diff(idx) > 1) + 1)
        run = max(runs, key=len)
        if len(run) >= 3:
            return int(run[0]), int(run[-1])
    lo, hi = int(np.argmin(z)), int(np.argmax(z))
    a, b = (lo, hi) if lo < hi else (hi, lo)
    return (0, len(z) - 1) if b - a < 2 else (a, b)


def rep_stats(curve: np.ndarray, t: np.ndarray) -> dict:
    """Per-rep numbers a set summary would show. SI units, seconds and m/s.

    Each of these was scored against the video on 61 reps before it was put
    here, and what did NOT survive that is recorded in the module docstring —
    a display that shows a number the video does not corroborate is inventing
    coaching advice, which is the display-layer version of this project's
    oldest failure.

    `mean_concentric_v` is the one number here with a meaning outside this
    project: it is what velocity-based training calls MCV. Read `concentric`
    for why its boundaries are a velocity threshold and not the rep's extremes.
    """
    curve = np.asarray(curve, dtype=float)
    t = np.asarray(t, dtype=float)
    z = curve[:, 1]
    a, b = concentric(curve, t)
    dt = float(t[b] - t[a])
    con = speed(curve, t)[a:b + 1]
    return {
        "duration_s": float(t[-1] - t[0]),
        "rom_m": float(z.max() - z.min()),
        "fore_aft_m": float(curve[:, 0].max() - curve[:, 0].min()),
        "concentric_s": dt,
        "mean_concentric_v": float(abs(z[b] - z[a]) / dt) if dt > 0 else np.nan,
        "peak_v": float(con.max()) if len(con) else np.nan,
        "turnaround_phase": float(turnaround(curve) / (len(curve) - 1)),
    }


# --------------------------------------------------------------------------
# 3. the average rep
# --------------------------------------------------------------------------

def resample_phase(curve: np.ndarray, n: int = GRID, align: str = "turnaround"
                   ) -> np.ndarray:
    """One rep onto a common (n, 2) phase grid, so reps can be averaged.

    Two alignments, and the difference between them is the whole reason this
    function has an argument:

    * `time` — a uniform grid over the window. Simple, and wrong for a set
      whose tempo changes: a paused squat's later reps sit longer at the bottom
      (C31a measured the gaps lengthening 5.4 -> 8.5 s within one set), so the
      turnarounds land at different phases and the average smears the bottom of
      the rep into a vertical blur.
    * `turnaround` — descent and ascent resampled to half the grid each, split
      at `turnaround`. The one landmark every rep of every lift has, found from
      the path's own geometry. The turnarounds then coincide by construction,
      which is what makes an average of four reps still look like a rep.

    `turnaround` is the default and the sweep in `analysis/65` is what chose it.
    Neither is a time axis afterwards — the grid is phase, so speed must be
    computed BEFORE resampling, not after.
    """
    curve = np.asarray(curve, dtype=float)
    m = len(curve)
    if align == "time":
        src = np.linspace(0, 1, m)
        dst = np.linspace(0, 1, n)
        return np.column_stack([np.interp(dst, src, curve[:, i])
                                for i in range(2)])
    if align != "turnaround":
        raise ValueError(f"unknown alignment {align!r}")

    k = turnaround(curve)
    half = n // 2
    out = np.empty((n, 2))
    for i in range(2):
        out[:half, i] = np.interp(np.linspace(0, 1, half),
                                  np.linspace(0, 1, k + 1), curve[:k + 1, i])
        out[half:, i] = np.interp(np.linspace(0, 1, n - half),
                                  np.linspace(0, 1, m - k), curve[k:, i])
    return out


def anomaly_scores(grid: np.ndarray) -> np.ndarray:
    """How far each rep is from the set's typical rep, in cm.

    `grid` is (n_reps, n_points, 2). The reference is the POINTWISE MEDIAN of
    the set, not its mean, so one wild rep does not drag the reference towards
    itself and thereby hide itself. With four reps and one bad one the mean sits
    a quarter of the way to the outlier; the median does not move at all.

    The score is the rms distance from that reference over the whole path, in
    centimetres, so it is readable directly — "rep 4 was 6 cm off the others"
    is a sentence, where a unitless z-score is not.
    """
    grid = np.asarray(grid, dtype=float)
    ref = np.median(grid, axis=0)
    return np.sqrt(((grid - ref) ** 2).sum(axis=2).mean(axis=1)) * 100


def flag_anomalies(grid: np.ndarray, k: float = 3.5,
                   floor_cm: float = 1.0) -> np.ndarray:
    """Boolean mask, True where a rep is an outlier and should be left out.

    Modified z-score on `anomaly_scores`: deviation from the median score over
    the MAD of the scores, which is the standard robust screen and needs no
    distributional assumption. `k = 3.5` is Iglewicz and Hoaglin's usual value.

    Two guards that matter more than the threshold:

    * `floor_cm` — a set can be so consistent that its MAD is a millimetre, and
      then a rep 3 mm off the others scores z = 20 and gets thrown out for
      being fractionally less perfect. Nothing is flagged unless it is at least
      `floor_cm` from the median rep in absolute terms. Without this the
      detector fires on every tight set in the corpus.
    * Nothing is ever flagged in a set of three or fewer. Two reps have no
      majority to be an outlier from, and with three the MAD is one number.

    **Never flags more than half the set**, as a belt-and-braces invariant. It
    is worth knowing that this guard appears to be UNREACHABLE and is kept
    anyway: the reference is the pointwise median, which by construction sits
    inside the majority, so the majority cannot be far from it. Sets designed
    to break it — two clusters far apart, four wild reps against two tight ones
    — all put the median inside one cluster or between them with every score
    equal, and neither flags a majority. Kept because it costs a comparison and
    the alternative is a display that silently deletes most of a set; recorded
    as unreachable so nobody writes a test for it and concludes the guard is
    broken.

    WHAT THIS IS FOR, AND WHAT IT IS NOT FOR
    -----------------------------------------
    Measured on the 13 refereed captures, and the result is not the one the
    feature was asked for:

    * **It agrees with the video about which rep is odd, with one false
      positive.** Counted per rep rather than per set, because per set flatters
      it: the IMU flags **5 reps across 4 sets**, the video flags **6 across
      5**, and **4 are the same rep**. On every set where the IMU fires the
      video fires on that same rep too (4 of 4), so the odd rep is a REAL
      anomaly — on the deadlifts it is the last rep, which the video sees as
      well. The residue is one FALSE POSITIVE (`deadlift_160x6_2` rep 1) and
      two MISSES (`bench_spoto_95x5_1` rep 2, `squat_pause_145x4_1` rep 3).
      On worst-rep agreement across all 13 captures it is 8 of 13 against a 22%
      chance rate.
    * **Excluding it does not make the average more accurate.** Against the
      video's own average rep, the IMU average scores 1.52 cm with everything in
      and 1.70 cm with the flagged rep dropped. That follows from the first
      point: the deviation is real and shared, so removing it from one side
      removes signal rather than error, and a median over n-1 reps is noisier
      than over n.
    * **It does earn its place against a MIS-SEGMENTED rep**, which is the
      failure it should really guard. Substituting one rep with a half-rep
      window moves a `mean` average by 4.74 cm median (9.16 worst) and exclusion
      takes that to 0.88; the detector catches the substitution in 10 of 12
      sets. A `median` average is already immune at 0.61 cm with no exclusion.

    So the two defences are largely redundant and the honest reading is that
    `median` is doing the work. The value of this function is the LABEL — tell
    the lifter rep 6 was the different one — rather than the deletion.
    """
    grid = np.asarray(grid, dtype=float)
    scores = anomaly_scores(grid)
    n = len(scores)
    if n <= 3:
        return np.zeros(n, dtype=bool)
    med = float(np.median(scores))
    mad = float(np.median(np.abs(scores - med)))
    if mad <= 0:
        # No spread to normalise by — the majority of the set is IDENTICAL.
        # Returning "nothing is an outlier" here was wrong and was caught by a
        # synthetic set of four identical reps and one wild one, where the MAD
        # is exactly zero and the wild rep is as obvious as an outlier can get.
        # With no scale available, the absolute floor is the whole test.
        mask = scores - med > floor_cm
        return mask if mask.sum() <= n // 2 else np.zeros(n, dtype=bool)
    z = 0.6745 * (scores - med) / mad
    mask = (z > k) & (scores - med > floor_cm)
    if mask.sum() > n // 2:
        return np.zeros(n, dtype=bool)
    return mask


def average_rep(reps: list[np.ndarray], t: list[np.ndarray] | None = None,
                method: str = "median", align: str = "turnaround",
                exclude: bool = True, n: int = GRID) -> dict:
    """The one path the app draws for a set.

    `reps` are display-plane (M, 2) curves — `pipeline.run`'s `planar`, or
    `vs_truth`'s `curve_video` for the same set as the bar really moved. `t` is
    unused by the average itself and is accepted so callers can pass what they
    already have without a special case; the phase grid removes time.

    Three averagers, all cheap, and the sweep in `analysis/65` compares them:

    * `mean` — what everybody writes. One anomalous rep moves it by 1/n of that
      rep's deviation, which on a 4-rep set is a quarter, so it is exactly the
      estimator that needs `exclude` to be on.
    * `median` — pointwise. Immune to a minority of bad reps whether or not
      they were flagged, which makes it the safe default: with `median` the
      exclusion step is a second line of defence rather than the only one.
    * `trimmed` — drop the highest and lowest value at each phase point, then
      mean. Between the two, and it needs 4 reps to mean anything.

    Returns the average, the phase grid it was built from, the per-rep scores
    and the exclusion mask, because a display that silently drops a rep is a
    display that will one day drop a good one and never tell anybody.
    """
    grid = np.stack([resample_phase(r, n=n, align=align) for r in reps])
    scores = anomaly_scores(grid)
    mask = flag_anomalies(grid) if exclude else np.zeros(len(reps), dtype=bool)
    kept = grid[~mask] if mask.any() else grid

    if method == "mean":
        avg = kept.mean(axis=0)
    elif method == "median":
        avg = np.median(kept, axis=0)
    elif method == "trimmed":
        if len(kept) >= 4:
            s = np.sort(kept, axis=0)
            avg = s[1:-1].mean(axis=0)
        else:
            avg = np.median(kept, axis=0)
    else:
        raise ValueError(f"unknown averaging method {method!r}")

    return {
        "average": avg,
        "grid": grid,
        "scores": scores,
        "excluded": mask,
        "n_kept": int(len(kept)),
    }


# --------------------------------------------------------------------------
# 4. scoring the display against the video
# --------------------------------------------------------------------------

def compare(recon: np.ndarray, video: np.ndarray) -> dict:
    """Two curves on the same grid, in cm. Horizontal, vertical and both.

    Deliberately the same rms the rest of the project scores in, so a number
    from here is comparable with `metrics.vs_truth`'s. `h` is the one the 1 cm
    spec is about.
    """
    d = (np.asarray(recon, dtype=float) - np.asarray(video, dtype=float)) * 100
    return {
        "h_rms": float(np.sqrt((d[:, 0] ** 2).mean())),
        "v_rms": float(np.sqrt((d[:, 1] ** 2).mean())),
        "rms": float(np.sqrt((d ** 2).sum(axis=1).mean())),
    }
