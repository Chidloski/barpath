"""Reject the frames the tracker got wrong, then smooth what is left.

The referee's job is to be believed, and a per-frame path straight out of
`track.summarise` is not yet in a state to be believed twice over.

**It contains frank teleports, and the existing gate cannot see them.**
`path.IMPLAUSIBLE_FRAC` and `path.IMPLAUSIBLE_MULT` test WHOLE-CLIP travel
against the lift's range of motion, which catches a track that is rigid and
wrong — the failure `vtrack` was built for — and is blind to a track that is
right for 1600 frames and jumps 33 cm in one. Measured over the 36 committed
CSVs on 2026-08-22, as peak apparent bar speed:

    capture                          max vz    max vx   travel gate
    bench_spoto_95x5_1_20260813       20.61     25.23   FLAGGED
    bench_spoto_95x5_2_20260813       12.98     12.48   FLAGGED
    squat_pause_140x4_3_20260806       7.94      9.93   passes
    deadlift_150x4_1_20260808          6.99      2.06   passes
    ---- every other capture ----     <=2.68    <=4.02   passes

m/s. The two flagged benches are H16's, already known bad and already caught.
**The next two are the point of this module**: both pass every check the repo
has, and both contain motion no barbell performs. A squat bar does not move
horizontally at 9.93 m/s, and 6.99 m/s downward beats free fall from a 1.3 m
lockout, which is 5.05 m/s — so it is not a fast drop, it is a wrong frame.
`deadlift_150x4_1` is separately recorded in `TASKS.md` for segmenting 5 reps
against a labelled and video-confirmed 4 at 30.11 cm vertical rms; nobody had
connected that to its referee containing an impossible frame.

**And it is jagged at a scale that matters.** Frame-to-frame |dx| runs a median
of 0.05 cm against a horizontal spec of ~1 cm, so the per-frame noise is small,
but it is not negligible against the quantity being refereed and it propagates
into every derivative the display layer takes.

WHAT THIS DOES NOT DO, AND THE DISTINCTION IS THE WHOLE DESIGN
--------------------------------------------------------------
**Conditioning must never repair a broken track.** Smoothing a path that jumps
20 m/s produces a smooth path that is still not the bar, and it would destroy
the one signal — visible wrongness — that made the failure findable at all.
So rejection is capped: past `CONDEMN_FRAC` of the clip the verdict flips from
"these frames are bad" to "this track is bad", `condemned` is set, and nothing
is interpolated. The two 2026-08-13 benches must come out of here still
obviously broken, and `tests/test_vtrack.py` gates exactly that.

Nothing here re-tracks, re-seeds or changes which constellation was chosen. It
reads a finished path and marks or filters its samples.
"""
from __future__ import annotations

import warnings

import numpy as np
from scipy.signal import savgol_filter

# The fastest a barbell in this corpus can be moving, m/s.
#
# **Derived, not tuned.** The bar's fastest legitimate motion is a deadlift
# dropped from lockout, and that is free fall: sqrt(2 * 9.81 * 1.3) = 5.05 m/s
# from the highest lockout the corpus holds. Nothing a lifter does beats
# gravity, so a frame implying more than this is a tracking error and not a
# fast rep.
#
# Read the margin honestly, the way `IMPLAUSIBLE_MULT` records its own. Over
# the 36 committed CSVs the fastest CLEAN capture peaks at 2.68 m/s vertical
# and 4.02 m/s horizontal; the four suspect ones at 6.99, 7.94, 12.98 and
# 20.61. The gap is [4.02, 6.99] and 5.0 sits 24% above the worst clean figure
# and 28% below the worst suspect — near the middle of a real gap, which is the
# property that makes it believable. It is applied per axis rather than to the
# resultant, so a clean vertical drop cannot mask a horizontal teleport.
V_MAX_MS = 5.0

# Cut on the lattice fit's own residual, as the position error it implies in
# CENTIMETRES rather than in pixels or in MADs.
#
# **A robust per-clip cut was tried first and was wrong** (2026-08-22). At 6
# MADs above each clip's median residual it rejected 92 frames of
# `squat_140x4_1` and 145 of `deadlift_160x5_2` — clips with no kinematic
# defect at all — and condemned 18 of the 36 captures. The residual
# distribution is heavy-tailed by nature: the marker subtends fewer pixels at
# lockout and its centroid is noisier there, which `path.top_of_travel_residual`
# documents and measures directly. A MAD cut reads that tail as anomaly when it
# is the instrument behaving normally.
#
# So the cut is absolute and tied to the constant the repo already uses for
# this quantity. `path.MAX_TOP_RESIDUAL_CM` is 0.5 cm, the referee's own fit
# error where it is worst; four times that is 2.0 cm, past anything a working
# fit produces and inside a broken one. Measured as the 99th percentile of
# implied error over the corpus: clean captures run 0.16-0.98 cm, the two
# known-broken benches reach 2.9 cm.
MAX_RESID_CM = 2.0

# Gaps up to this long, in seconds, are bridged; longer ones stay NaN.
#
# 0.20 s is six frames at 30 fps. The justification is what the bar can do
# inside the gap rather than what looks tidy: over 0.2 s a bar moving at a
# realistic 1 m/s travels 20 cm, and a linear bridge across a turnaround that
# fast would invent up to several cm of error. Below that the bridge is within
# the referee's own noise. A dropout longer than this is missing data and is
# reported as missing.
MAX_GAP_S = 0.20

# Savitzky-Golay smoothing, specified in SECONDS so it is frame-rate
# independent, and at order 2 so that curvature survives.
#
# **Order matters more than length here.** The quantity most easily damaged by
# smoothing is the turnaround — the bottom of a squat, the chest touch on a
# bench — and a turnaround is locally parabolic. A second-order Savitzky-Golay
# filter reproduces a parabola exactly, so it removes noise there without
# clipping the extremum, which a moving average or a Gaussian would. 0.167 s is
# five frames at 30 fps: the lightest window that averages more than a pair.
SMOOTH_S = 0.167
SMOOTH_ORDER = 2

# Exceed this fraction of frames failing the SPEED test and the CLIP is
# condemned rather than repaired.
#
# Over the 36 committed CSVs the speed fraction is 0.00-0.14% on every capture
# that tracks, and 2.2% and 10.0% on the two 2026-08-13 benches that do not.
# The gap spans two orders of magnitude and 2% sits inside it; nothing about
# the constant is delicate. What it buys is the distinction the module exists
# for — `deadlift_150x4_1` and `squat_pause_140x4_3` each contain exactly ONE
# impossible frame in a sound track and are repaired, while a path that is
# wrong throughout is left visibly wrong. See the module docstring.
CONDEMN_FRAC = 0.02


def _mad(a):
    a = a[np.isfinite(a)]
    if a.size == 0:
        return np.nan
    return float(np.median(np.abs(a - np.median(a))))


def anomalies(path: dict, v_max: float = V_MAX_MS,
              max_resid_cm: float = MAX_RESID_CM) -> dict:
    """Which frames are not to be believed, and which test said so.

    Returns a dict of boolean masks over the clip's frames — `speed`, `resid`,
    `missing` and their union `bad` — plus the counts. Reports rather than
    filters, so a caller can look at WHY a frame was dropped, and so the review
    figure can draw the rejected samples instead of hiding them.

    The two tests are deliberately independent. `speed` is physics and needs no
    reference to the tracker's own opinion of itself; `resid` is the tracker's
    self-report and catches errors too small to violate physics. A frame failing
    either is dropped, because both failure modes have been seen alone.
    """
    t = np.asarray(path["t"], float)
    x = np.asarray(path["x"], float)
    h = np.asarray(path["height"], float)
    n = len(t)

    missing = ~(np.isfinite(x) & np.isfinite(h))

    # --- physics: no sample may imply motion faster than free fall ----------
    # Differences are taken across the NEAREST FINITE neighbour rather than the
    # adjacent index, so a dropout does not manufacture a false teleport out of
    # the legitimate motion either side of it.
    speed = np.zeros(n, bool)
    fin = np.nonzero(~missing)[0]
    if fin.size >= 2:
        dt = np.diff(t[fin])
        dt[dt <= 0] = np.nan
        vx = np.abs(np.diff(x[fin])) / dt
        vz = np.abs(np.diff(h[fin])) / dt
        over = (vx > v_max) | (vz > v_max)
        # An over-speed edge condemns the sample the run of motion ARRIVES at.
        # A single bad frame therefore produces two over-speed edges and one
        # rejected sample, which is the intent; a step change between two good
        # stretches produces one edge and drops the first sample of the second,
        # which is conservative in the right direction.
        bad_edge = np.nonzero(over)[0]
        for e in bad_edge:
            speed[fin[e + 1]] = True
        # ... and if the sample before it is ALSO an over-speed edge, it was the
        # outlier, so prefer it and release its neighbour.
        for e in bad_edge:
            if e > 0 and over[e - 1]:
                speed[fin[e]] = True
                speed[fin[e + 1]] = False

    # --- the tracker's own residual, read in centimetres --------------------
    resid = np.zeros(n, bool)
    r = np.asarray(path.get("residual_px", np.full(n, np.nan)), float)
    mpp = np.asarray(path.get("m_per_px_t", np.full(n, np.nan)), float)
    if mpp.shape != r.shape:
        mpp = np.full(n, float(path.get("m_per_px", np.nan)))
    if np.isfinite(r).any() and np.isfinite(mpp).any():
        resid = (r * mpp * 100.0) > max_resid_cm

    bad = missing | speed | resid
    return {"bad": bad, "speed": speed, "resid": resid, "missing": missing,
            "n_bad": int(bad.sum()), "n_speed": int(speed.sum()),
            "n_resid": int(resid.sum()), "n_missing": int(missing.sum()),
            "frac": float(bad.mean()) if n else 0.0,
            # Condemnation reads the SPEED fraction alone, and the two things
            # it deliberately excludes were both tried and both wrong.
            #
            # Residual: a high count means the fit is loose, which is a quality
            # to report; a high speed count means the path is not a trajectory
            # at all, which is a verdict. Conflating them condemned 18 of 36.
            #
            # Missing: a dropout is what bridging is FOR, and `validate`
            # already warns below 90% coverage. Counting it here condemned
            # `deadlift_150x4_1` — 18 untracked frames out of 705 and exactly
            # one impossible one — and condemning it means refusing to repair
            # the single frame that is actually wrong with it.
            #
            # The separation is wide either way. Over the 36 CSVs the speed
            # fraction is 0.00-0.14% on every clean capture and 2.2% and 10.0%
            # on the two known-broken benches.
            "speed_frac": float(speed.mean()) if n else 0.0}


def _bridge(t, y, bad, max_gap_s):
    """Linear interpolation across short runs of `bad`; long runs stay NaN."""
    y = y.copy()
    y[bad] = np.nan
    good = np.nonzero(np.isfinite(y))[0]
    if good.size < 2:
        return y
    holes = np.nonzero(~np.isfinite(y))[0]
    if holes.size == 0:
        return y
    # Split the holes into contiguous runs and bridge only the short ones.
    runs = np.split(holes, np.nonzero(np.diff(holes) != 1)[0] + 1)
    for run in runs:
        lo, hi = run[0] - 1, run[-1] + 1
        if lo < 0 or hi >= len(y):
            continue                      # a hole at either end is not a gap
        if t[hi] - t[lo] > max_gap_s:
            continue
        y[run] = np.interp(t[run], [t[lo], t[hi]], [y[lo], y[hi]])
    return y


def _smooth(t, y, window_s, order):
    """Savitzky-Golay over contiguous finite runs, window given in seconds."""
    y = y.copy()
    fin = np.isfinite(y)
    if fin.sum() < order + 2:
        return y
    dt = np.median(np.diff(t))
    if not np.isfinite(dt) or dt <= 0:
        return y
    w = int(round(window_s / dt))
    w = max(order + 1, w)
    if w % 2 == 0:
        w += 1
    idx = np.nonzero(fin)[0]
    for run in np.split(idx, np.nonzero(np.diff(idx) != 1)[0] + 1):
        if len(run) <= order + 1:
            continue
        ww = min(w, len(run) if len(run) % 2 else len(run) - 1)
        if ww <= order:
            continue
        y[run] = savgol_filter(y[run], ww, order)
    return y


def condition(path: dict, v_max: float = V_MAX_MS,
              max_resid_cm: float = MAX_RESID_CM,
              max_gap_s: float = MAX_GAP_S, window_s: float = SMOOTH_S,
              order: int = SMOOTH_ORDER, condemn_frac: float = CONDEMN_FRAC,
              name: str = "") -> dict:
    """Reject, bridge and smooth a tracked path. Returns a NEW dict.

    `x` and `height` are replaced; `x_raw` and `height_raw` keep the originals,
    and `rejected` is the boolean mask, so nothing this does is irreversible and
    the review figure can show what was dropped. `travel_m` is RECOMPUTED from
    the conditioned height, because leaving the header scalar describing the raw
    path while the columns describe the conditioned one is exactly the kind of
    silent inconsistency this repo keeps getting hurt by.

    **A condemned clip is passed through untouched apart from its flag.** See
    the module docstring: repairing a broken track is worse than leaving it
    broken, because the brokenness is the only thing that makes it findable.
    """
    out = dict(path)
    # Idempotence. A conditioned path is cached to CSV with this flag in its
    # header, so a cached read followed by a `condition` call must not smooth
    # twice — that would compound the window silently and shrink the
    # turnarounds, which is precisely the damage the order-2 filter is chosen
    # to avoid.
    if path.get("conditioned"):
        return out
    a = anomalies(path, v_max=v_max, max_resid_cm=max_resid_cm)
    t = np.asarray(path["t"], float)
    x = np.asarray(path["x"], float)
    h = np.asarray(path["height"], float)

    out["x_raw"], out["height_raw"] = x.copy(), h.copy()
    out["rejected"] = a["bad"]
    out["n_rejected"] = a["n_bad"]
    out["reject_frac"] = a["frac"]
    out["condemned"] = bool(a["speed_frac"] > condemn_frac)

    if out["condemned"]:
        warnings.warn(
            f"{name or path.get('video', 'clip')}: {100 * a['speed_frac']:.1f}% "
            f"of frames ({a['n_speed']}) imply motion faster than free fall — "
            f"this is a BROKEN TRACK, not a few bad frames. Left "
            f"unconditioned on purpose; LOOK at the review figure.",
            stacklevel=2)
        out["conditioned"] = False
        return out

    xs = _smooth(t, _bridge(t, x, a["bad"], max_gap_s), window_s, order)
    hs = _smooth(t, _bridge(t, h, a["bad"], max_gap_s), window_s, order)
    out["x"], out["height"] = xs, hs
    out["conditioned"] = True

    # Travel on the same 1st-99th percentile definition `track.summarise` uses,
    # so the conditioned scalar is comparable to the raw one it replaces.
    fin = np.isfinite(hs)
    if fin.sum() > 2:
        lo, hi = np.nanpercentile(hs[fin], [1, 99])
        out["travel_m"] = float(hi - lo)
    return out
