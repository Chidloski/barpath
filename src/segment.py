"""
Step 5 — rep segmentation.

The original design anchored reps on stationary windows between them. Real
captures killed it: under load there is no such window. Only ~13% of a
deadlift capture is quiet enough to qualify and essentially all of that is the
pre-set pause, so the old detector found 0 of 14 bench reps and 1 of 15 squat
reps, in the wrong place. The ZUPT reasoning below is still correct — it is
just about an event that does not occur during a working set.

What replaced it, and why.

**Detection is easy; rejection is the whole problem.** Reps are obvious
velocity oscillations. So is walking to the bar, bending to grip it, unracking,
walking out, and re-racking. Worse, those are LARGER: setup peaks reach
1.5-2.0 m/s against 0.3-0.6 m/s for a bench rep, so any amplitude threshold
picks the wrong events. `bench_92.5x2` has an unrack bigger than either of its
two reps.

**Reps are distinguished by shape, not size.** Setup movements are sharp and
brief (~0.5 s); reps are broad and slow (~1.0-1.5 s). Comparing candidates in a
fixed-DURATION window preserves that difference, where resampling each
candidate to a fixed sample count destroys it. Within a set the reps are
near-identical to each other and the setup matches nothing, so the reps are the
largest mutually-similar cluster.

**Where the bar hits the floor, use that instead.** A deadlift's floor impact
is a 15-21 g spike, exactly one per rep, and unmistakable — it gets 6/6, 6/6
and 3/3 on the three deadlift captures including one rep that shape-matching
misses. This is not a per-lift lookup table: the anchors are used when the
physics provides them and ignored when it does not, which the signal decides
for itself. Bench and squat produce at most one spurious impact (the re-rack).

Shape clustering alone is NOT sufficient and it is worth recording why, so this
is not re-litigated. On `deadlift_155x6_1` two setup lobes correlate 0.73-0.82
with the rep cluster while a genuine late rep correlates 0.27. No threshold
separates those. The impact anchors do.

Honest limit: this is validated against rep COUNTS from filenames. Counts
cannot confirm the boundaries are in the right places, only that the right
number of things were found. Boundary accuracy needs the video ground truth
(A2) and is not claimed here.

---

The original reasoning, still true, still worth keeping:

ZUPT (zero-velocity update). Knowing that true velocity is zero at a given
instant is powerful, because any velocity you have accumulated by then is
pure error.

A false positive is worse than a miss: you assert something about the motion
that is not true, injecting error rather than removing it. That is why the
selection below is conservative and why the gate counts false positives.
"""

from __future__ import annotations

import numpy as np
from scipy.signal import butter, filtfilt


def _rolling_var(x: np.ndarray, w: int) -> np.ndarray:
    """Centred rolling variance of a 1-D signal, same length as input."""
    pad = w // 2
    xp = np.pad(x, (pad, w - 1 - pad), mode="edge")
    c1 = np.concatenate([[0.0], np.cumsum(xp)])
    c2 = np.concatenate([[0.0], np.cumsum(xp**2)])
    n = len(x)
    s1 = c1[w:w + n] - c1[:n]
    s2 = c2[w:w + n] - c2[:n]
    return np.maximum(s2 / w - (s1 / w) ** 2, 0.0)


def stationary_mask(log: dict, window_s: float = 0.25,
                    accel_var_max: float = 0.05,
                    gyro_var_max: float = 0.002,
                    min_duration_s: float = 0.20) -> np.ndarray:
    """Boolean mask of samples where the watch is judged stationary."""
    fs = log["fs"]
    w = max(int(round(window_s * fs)), 3)

    av = _rolling_var(np.linalg.norm(log["accel"], axis=1), w)
    gv = _rolling_var(np.linalg.norm(log["gyro"], axis=1), w)
    quiet = (av < accel_var_max) & (gv < gyro_var_max)

    return _drop_short(quiet, int(round(min_duration_s * fs)))


def _drop_short(mask: np.ndarray, min_len: int) -> np.ndarray:
    """Remove runs of True shorter than min_len."""
    out = mask.copy()
    for a, b in runs(mask):
        if b - a < min_len:
            out[a:b] = False
    return out


def runs(mask: np.ndarray) -> list[tuple[int, int]]:
    """Contiguous [start, stop) index pairs where mask is True."""
    if not mask.any():
        return []
    d = np.diff(mask.astype(np.int8))
    starts = list(np.flatnonzero(d == 1) + 1)
    stops = list(np.flatnonzero(d == -1) + 1)
    if mask[0]:
        starts.insert(0, 0)
    if mask[-1]:
        stops.append(len(mask))
    return list(zip(starts, stops))


def bandpass(v: np.ndarray, fs: float, lo: float = 0.12, hi: float = 3.0) -> np.ndarray:
    """Band-pass a signal to the rep band.

    `lo` strips integration drift, which is metres across a set and swamps
    everything. `hi` removes impact ringing, which otherwise puts spurious zero
    crossings inside a deadlift's descent and splits one rep into several.
    """
    b, a = butter(2, [lo / (fs / 2), hi / (fs / 2)], "band")
    return filtfilt(b, a, v)


def impact_anchors(log: dict, threshold_g: float = 6.0,
                   refractory_s: float = 1.5,
                   skip_s: float = 5.0) -> list[int]:
    """Indices of floor impacts — one per rep, on lifts where the bar is set down.

    A deadlift lands with a 15-21 g spike that nothing else in a gym produces.
    `refractory_s` collapses the ringing that follows into one event, and
    `skip_s` ignores the calibration pause and walk-in.

    Returns [] on lifts that never touch down, which is the correct answer for
    bench and squat and is why the caller can apply this unconditionally.
    """
    t, fs = log["t"], log["fs"]
    mag = np.linalg.norm(log["accel"], axis=1) / 9.80665
    start = int(skip_s * fs)

    peaks: list[int] = []
    for i in np.flatnonzero(mag[start:] > threshold_g) + start:
        if not peaks or t[i] - t[peaks[-1]] > refractory_s:
            peaks.append(int(i))
    return peaks


def _concentric_lobes(v: np.ndarray, t: np.ndarray,
                      min_area: float = 0.08) -> list[tuple[int, int, int, float]]:
    """Positive-velocity lobes with enough displacement to be a lift.

    Every rep of every lift has exactly one upward phase — the deadlift pull,
    the squat ascent, the bench press — so working on positive lobes gives one
    candidate per rep without needing to know which lift it is.

    Returns (peak_index, start, stop, area).
    """
    sign = np.sign(v)
    sign[sign == 0] = 1
    edges = np.r_[0, np.flatnonzero(np.diff(sign)) + 1, len(v)]

    out = []
    for a, b in zip(edges[:-1], edges[1:]):
        if b - a < 5:
            continue
        area = float(np.trapezoid(v[a:b], t[a:b]))
        if area > min_area:
            out.append((a + int(np.argmax(v[a:b])), a, b, area))
    return out


def _shape(v: np.ndarray, t: np.ndarray, i: int,
           half_s: float = 1.5, m: int = 120) -> np.ndarray:
    """Unit-norm velocity in a fixed-DURATION window centred on sample `i`.

    Fixed duration is the point. Resampling each candidate to a fixed sample
    count would make a 0.5 s setup spike and a 1.4 s rep look alike, which is
    exactly the confusion to avoid. Unit-norming keeps it insensitive to a
    grinding rep being slower and weaker, while staying sensitive to width.
    """
    grid = np.linspace(t[i] - half_s, t[i] + half_s, m)
    w = np.interp(grid, t, v, left=0.0, right=0.0)
    w = w - w.mean()
    n = np.linalg.norm(w)
    return w / n if n > 0 else w


def rep_bounds(log: dict, vertical_velocity: np.ndarray,
               similarity: float = 0.7,
               peak_ratio: float = 2.5,
               min_area: float = 0.08) -> list[tuple[int, int]]:
    """Rep boundaries, as [start, stop) index pairs into the log.

    `vertical_velocity` is the world-frame vertical velocity from step 4. It
    may drift by metres; it is band-passed here.

    Two mechanisms, in priority order:

    1. Floor impacts, if the lift has them. Exact on all three deadlift
       captures and immune to every setup false positive.
    2. Otherwise the largest cluster of mutually similar concentric lobes,
       compared in fixed-duration windows so a brief sharp unrack cannot
       masquerade as a broad slow rep.

    `peak_ratio` additionally rejects candidates whose peak speed differs from
    the cluster median by more than this factor. A grinding rep is slower and
    weaker than a fresh one but not by 3x; an unrack is (1.88 m/s against
    0.26 m/s in `bench_92.5x2`). Physical, not fitted.

    Boundaries run from the turnaround before each concentric to the turnaround
    after it.
    """
    t = log["t"]
    v = bandpass(vertical_velocity, log["fs"])
    lobes = _concentric_lobes(v, t, min_area)
    if not lobes:
        return []

    anchors = impact_anchors(log)
    sets_down = len(anchors) >= 3
    if sets_down:
        chosen = _lobes_before(lobes, anchors, t)
    else:
        chosen = _similar_cluster(v, t, lobes, similarity, peak_ratio)

    return _full_cycles(v, chosen, sets_down)


def _full_cycles(v: np.ndarray, chosen: list,
                 sets_down: bool) -> list[tuple[int, int]]:
    """Extend each concentric to a whole rep, rest position to rest position.

    A rep must start and end at the same place for the detrend in step 7 to
    mean anything, and the concentric alone does not — it runs bottom to top.

    Which side the eccentric sits on depends on where the bar rests. A deadlift
    rests on the floor, so the cycle is pull-then-drop and the eccentric
    FOLLOWS. A bench or squat rests at lockout, so the cycle is descend-then-
    press and the eccentric PRECEDES. `sets_down` comes from whether the signal
    contained floor impacts, so the lift is never named.
    """
    sign = np.sign(v)
    sign[sign == 0] = 1
    crossings = np.flatnonzero(np.diff(sign)) + 1

    out = []
    for _, a, b, _ in chosen:
        if sets_down:
            after = crossings[crossings > b]
            stop = int(after[0]) if len(after) else len(v)
            start = a
        else:
            before = crossings[crossings < a]
            start = int(before[-1]) if len(before) else 0
            stop = b
        out.append((start, stop))
    return out


def _lobes_before(lobes, anchors, t) -> list:
    """Pair each floor impact with the concentric lobe that precedes it.

    The bar goes up, then it comes down and lands. So the rep owning an impact
    is the last concentric before it.
    """
    chosen = []
    for k in anchors:
        prior = [l for l in lobes if l[0] < k]
        if prior and (not chosen or prior[-1] is not chosen[-1]):
            chosen.append(prior[-1])
    return chosen


def _grow(shapes, peaks, seed, similarity, peak_ratio):
    """Grow a cluster from one seed by alternating template fit and membership."""
    keep = (shapes @ shapes[seed]) > similarity
    for _ in range(6):
        template = np.median(shapes[keep], axis=0)
        norm = np.linalg.norm(template)
        if norm == 0:
            break
        template = template / norm
        med_peak = np.median(peaks[keep])
        new = ((shapes @ template) > similarity) & \
              (peaks < med_peak * peak_ratio) & (peaks > med_peak / peak_ratio)
        if np.array_equal(new, keep) or not new.any():
            break
        keep = new
    return keep


def _similar_cluster(v, t, lobes, similarity, peak_ratio) -> list:
    """Largest mutually-similar set of lobes, by fixed-duration shape.

    Every candidate is tried as a seed and the clusters are ranked by size,
    then by how late they occur. The tie-break is not arbitrary: a set is
    always set up first and lifted second, so when two equally good clusters
    compete the later one is the reps and the earlier one is the approach.

    `bench_92.5x2` is why this exists. Its unrack and its two paused reps each
    form a clean, internally consistent pair, so size alone picks whichever was
    seeded first — and picking the unrack yields exactly the right rep COUNT
    with entirely the wrong reps.
    """
    shapes = np.array([_shape(v, t, i) for i, _, _, _ in lobes])
    peaks = np.array([np.abs(v[a:b]).max() for _, a, b, _ in lobes])
    times = np.array([t[i] for i, _, _, _ in lobes])

    best, best_score = None, (-1, -np.inf)
    for seed in range(len(lobes)):
        keep = _grow(shapes, peaks, seed, similarity, peak_ratio)
        if not keep.any():
            continue
        score = (int(keep.sum()), float(np.median(times[keep])))
        if score > best_score:
            best, best_score = keep, score

    if best is None:
        return []
    chosen = [l for l, k in zip(lobes, best) if k]

    # Non-maximum suppression: a pull that breaks into two lobes is one rep.
    if len(chosen) > 2:
        span = np.median(np.diff([t[l[0]] for l in chosen]))
        merged = [chosen[0]]
        for l in chosen[1:]:
            if t[l[0]] - t[merged[-1][0]] < 0.6 * span:
                if l[3] > merged[-1][3]:
                    merged[-1] = l
            else:
                merged.append(l)
        chosen = merged
    return chosen


def quality_flags(log: dict, bounds: list[tuple[int, int]]) -> list[dict]:
    """Per-rep data-quality checks.

    Discriminate on PHYSICAL IMPOSSIBILITY, not on unusualness. The rep you
    most want to discard for looking strange is often the rep with the real
    form breakdown. Strap resonance is energy above ~10 Hz, where barbell
    motion has essentially none. Clipping is a hard rail. Both are outside
    what a barbell can do. A grind is ugly but physically plausible: keep it.
    """
    fs = log["fs"]
    out = []
    for a, b in bounds:
        seg = log["accel"][a:b]
        n = len(seg)
        flags = {"rep": (a, b), "clipped": False, "strap_resonance": False}

        if np.abs(seg).max() > 0.95 * 16 * 9.80665:
            flags["clipped"] = True

        if n > 16:
            mag = np.linalg.norm(seg, axis=1)
            spec = np.abs(np.fft.rfft(mag - mag.mean())) ** 2
            freq = np.fft.rfftfreq(n, 1.0 / fs)
            total = spec.sum()
            if total > 0 and spec[freq > 10.0].sum() / total > 0.25:
                flags["strap_resonance"] = True

        flags["ok"] = not (flags["clipped"] or flags["strap_resonance"])
        out.append(flags)
    return out
