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

**Then the video showed the velocity signal cannot be trusted at all.**

Segmenting on band-passed vertical velocity found 44 of 44 reps and put every
window half a rep out of phase — lockout to lockout, holding one rep's descent
followed by the next one's ascent. Against video truth the band-passed IMU
vertical correlates **-0.82** with real bar height, and the in-band error is
145 cm against a 69 cm signal. It is already there at the acceleration stage
(correlation -0.16), so it is not an integration or filtering artefact. It is
P3: body-frame accel bias projected through a rotating forearm lands at REP
FREQUENCY, so no filter can remove it. The segmenter was finding real structure
in the error — hence the right count and the wrong phase.

So where the bar sets down, boundaries now come from the impacts alone and the
velocity signal is not consulted. Impacts use raw acceleration magnitude: no
attitude, no integration, no filtering, and they match video to 13.5 ms rms.
All 15 deadlift windows contain exactly one video lockout, at 0.58-0.84 through
the window.

**And then the sign turned out to be inverted.** Core Motion's
`userAcceleration` is the negative of physical acceleration, so every velocity
this module ever saw pointed the wrong way. `io.load_log` negates it now. Once
corrected, what the module calls the concentric really is the concentric — but
the selection had been tuned against the inverted signal, so three of four
bench captures over-detected until cadence selection was added.

**Cadence is the third discriminator, and it was in the plan from the start.**
Reps come at a regular interval; an unrack does not belong to that rhythm. On
`bench_90x4_1` the four reps sit 2.16, 2.13 and 2.33 s apart while the unrack
is 15.9 s before the first — obvious in the gaps, invisible to shape and to
size. Gaps are compared to EACH OTHER rather than to their own median: against
a median, 6.6 s and 12.9 s both fall inside a wide band and a bad run of three
survives.

Honest limit: **bench and squat have no impact anchor and still segment on the
integrated velocity**, which carries 145 cm of in-band error against a 69 cm
signal. Their counts are right; their boundaries are only as good as that
signal. Fixing it is B2 and B6 — removing the in-band error — not a change
here.

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

from . import io


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


def rest_instants(log: dict, impacts: list[int] | None = None,
                  look_s: float = 1.00, window_s: float = 0.05,
                  max_accel: float = 8.0) -> list[int]:
    """The moment the bar is at REST after each floor impact. B7.

    Not the impact index. `impact_anchors` marks the onset of the spike, and
    against video the bar is still moving at 0.4-1.0 m/s there — it has hit the
    floor but not finished stopping. A near-zero crossing follows within
    ~150 ms of every impact.

    Found from raw acceleration and gyro only: no attitude, no integration, no
    filtering. That is the whole point. This exists to correct the drift, so it
    must not be derived from anything carrying it.

    Both channels matter. A wrist at rest has stopped rotating as well as
    translating, and an early version of this scored on acceleration alone and
    landed where the bar was still moving at 0.50 m/s with 0.02 available in the
    same window. Gyro variance is what distinguishes "the accelerometer is
    briefly quiet mid-bounce" from "the arm has stopped".

    `max_accel` REJECTS an instant rather than returning a bad one. A false
    anchor asserts a velocity the bar did not have and injects the error it
    exists to remove, so silence is the safer failure — the same argument
    `rep_bounds` makes about false positives. Against video the two rejected
    cases are both the FINAL impact of a set, where the lifter releases the bar
    and walks away: mean |accel| there is 12.2 and 16.7 m/s² against 1.3-6.3
    for the thirteen good ones, so the gate separates them cleanly.

    Be suspicious of that threshold. It is set from two bad points across three
    captures and is the weakest part of B7. Note also that the "good" anchors
    average 2.6 m/s², so this is not stillness in any absolute sense — a wrist
    under a loaded bar never is. It is a rejection rule, not a claim.

    Returns [] when there are no impacts, which is the right answer for bench
    and squat and lets the caller apply this unconditionally.
    """
    if impacts is None:
        impacts = impact_anchors(log)
    if not impacts:
        return []

    t, fs = log["t"], log["fs"]
    w = max(int(round(window_s * fs)), 3)
    mag = np.linalg.norm(log["accel"], axis=1)
    av = _rolling_var(mag, w)
    gv = _rolling_var(np.linalg.norm(log["gyro"], axis=1), w)

    # Scale the two channels by their own spread over the record so neither
    # dominates the sum by unit choice alone.
    score = av / (np.median(av) + 1e-12) + gv / (np.median(gv) + 1e-12)

    out = []
    for k in impacts:
        stop = int(np.searchsorted(t, t[k] + look_s))
        seg = score[k:stop]
        if not len(seg):
            continue
        j = k + int(np.argmin(seg))
        if mag[max(j - w, 0):j + w].mean() <= max_accel:
            out.append(j)
    return out


def _all_lobes(v: np.ndarray, t: np.ndarray,
               min_area: float) -> list[tuple[int, int, int, float]]:
    """Every velocity lobe carrying at least `min_area` of displacement.

    Both signs, in time order. Filtering by area here is what makes the
    boundary search in `_full_cycles` trustworthy: the raw zero crossings
    include ringing and tremor, so extending a rep to the nearest crossing
    stops at a noise blip instead of the real turnaround. Working on
    significant lobes means "the turnaround before this concentric" is the
    physical one.

    Returns (peak_index, start, stop, signed_area).
    """
    sign = np.sign(v)
    sign[sign == 0] = 1
    edges = np.r_[0, np.flatnonzero(np.diff(sign)) + 1, len(v)]

    out = []
    for a, b in zip(edges[:-1], edges[1:]):
        if b - a < 5:
            continue
        area = float(np.trapezoid(v[a:b], t[a:b]))
        if abs(area) < min_area:
            continue
        extreme = a + int(np.argmax(v[a:b]) if area > 0 else np.argmin(v[a:b]))
        out.append((extreme, a, b, area))
    return out


def _concentric_lobes(v: np.ndarray, t: np.ndarray,
                      min_area: float = 0.08) -> list[tuple[int, int, int, float]]:
    """Upward lobes big enough to be a lift.

    Every rep of every lift has exactly one upward phase — the deadlift pull,
    the squat ascent, the bench press — so working on positive lobes gives one
    candidate per rep without needing to know which lift it is.
    """
    return [l for l in _all_lobes(v, t, min_area) if l[3] > 0]


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
    if len(anchors) >= 3:
        return _cycles_from_impacts(t, anchors)

    chosen = _similar_cluster(v, t, lobes, similarity, peak_ratio)
    return _full_cycles(_all_lobes(v, t, min_area), chosen, False, len(v))


def _cycles_from_impacts(t: np.ndarray, anchors: list[int]) -> list[tuple[int, int]]:
    """Rep windows straight from the floor impacts. Floor to floor, one per rep.

    This ignores the velocity signal entirely, and that is the point.

    Segmenting on band-passed vertical velocity looked right — it found 44 of
    44 reps — and was keying off the wrong thing. Against video truth the
    band-passed IMU vertical correlates **-0.82** with the real bar height, and
    the in-band error is 145 cm against a 69 cm signal. The corruption is
    already there at the acceleration stage (correlation -0.16), so it is not
    an integration or filtering artefact: it is P3, the body-frame accel bias
    projected through a rotating forearm, which lands at REP FREQUENCY and
    therefore cannot be filtered out. The segmenter was finding real structure
    in the error, which is why it got the count right and the phase half a rep
    wrong.

    The impacts are not affected. They come from raw acceleration magnitude —
    no attitude, no integration, no filtering — and match the video to 13.5 ms
    rms. A deadlift rep runs floor to floor, so consecutive impacts bound it
    exactly, and the first rep starts one median rep-gap before the first
    impact.

    Bench and squat have no such anchor and still segment on the corrupted
    velocity. Their windows find the right NUMBER of reps; their phase is
    unverified and probably wrong the same way. That needs B2 and B6, not a
    change here.
    """
    gaps = np.diff([t[k] for k in anchors])
    lead = float(np.median(gaps)) if len(gaps) else 3.0

    bounds = []
    start = int(np.searchsorted(t, t[anchors[0]] - lead))
    for k in anchors:
        stop = min(int(k) + 1, len(t))
        if stop > start:
            bounds.append((start, stop))
        start = stop
    return bounds


def _full_cycles(all_lobes: list, chosen: list, sets_down: bool,
                 n: int, balance: float = 0.5) -> list[tuple[int, int]]:
    """Extend each concentric to a whole rep, rest position to rest position.

    A rep must start and end at the same place for the detrend in step 7 to
    mean anything, and the concentric alone does not — it runs bottom to top.

    Which side the eccentric sits on depends on where the bar rests. A deadlift
    rests on the floor, so the cycle is pull-then-drop and the eccentric
    FOLLOWS. A bench or squat rests at lockout, so the cycle is descend-then-
    press and the eccentric PRECEDES. `sets_down` comes from whether the signal
    contained floor impacts, so the lift is never named.

    The eccentric is taken from the significant-lobe list rather than from raw
    zero crossings. Crossings include ringing and tremor, so the nearest one is
    often a noise blip a few samples away — which silently truncated reps to
    the concentric alone and produced 2.78 s and 0.96 s windows for two reps of
    the same set.
    """
    starts = [l[1] for l in all_lobes]
    limits = [l[0] for l in chosen]          # never absorb a neighbouring rep

    out = []
    for idx, (peak, a, b, area) in enumerate(chosen):
        k = starts.index(a) if a in starts else None
        if k is None:
            out.append((a, b))
            continue

        before = limits[idx - 1] if idx > 0 else -1
        after = limits[idx + 1] if idx + 1 < len(limits) else n
        out.append(_absorb(all_lobes, k, a, b, area, sets_down, before, after,
                           balance))

    return _clip_overlaps(out, n)


def _absorb(all_lobes, k, a, b, area, sets_down, before, after, balance):
    """Widen one concentric until the window holds a matching eccentric.

    A rep starts and ends in about the same place, so it must contain both an
    up phase and a down phase of comparable size. That is a physical fact about
    lifting, not a tuning parameter, and it is the criterion used here: absorb
    adjacent lobes outward until the accumulated opposite-sign displacement
    reaches `balance` times the concentric's.

    Taking only the single adjacent lobe is not enough. A heavy pull often
    breaks into two positive lobes at the knee, so the lobe next to the chosen
    one is itself positive and no eccentric is ever picked up — which left 9 of
    15 deadlift reps containing zero downward travel.

    A pause inside a rep is absorbed rather than avoided. The bar is barely
    moving, so it contributes almost nothing to either total, and including it
    keeps the window closed at both ends.

    Absorption stops at the neighbouring rep's peak, so a window can never
    swallow the rep next to it.
    """
    start, stop = a, b
    gathered = 0.0
    step = 1 if sets_down else -1
    j = k

    while gathered < balance * abs(area):
        j += step
        if j < 0 or j >= len(all_lobes):
            break
        peak_j, aj, bj, area_j = all_lobes[j]
        if sets_down and peak_j >= after:
            break
        if not sets_down and peak_j <= before:
            break
        if sets_down:
            stop = bj
        else:
            start = aj
        if area_j < 0:
            gathered += abs(area_j)
    return (start, stop)


def _clip_overlaps(bounds: list[tuple[int, int]], n: int) -> list[tuple[int, int]]:
    """Reps must be disjoint. Where two windows meet, split at the boundary."""
    out = []
    for i, (a, b) in enumerate(bounds):
        if out and a < out[-1][1]:
            a = out[-1][1]
        out.append((a, min(b, n)))
    return [(a, b) for a, b in out if b > a]


def _lobes_before(lobes, anchors, t) -> list:
    """Pair each floor impact with the concentric lobe that precedes it.

    The bar goes up, then it comes down and lands. So the rep owning an impact
    is the last concentric before it.

    A heavy pull sometimes breaks into two lobes at the knee, and this then
    anchors on the lockout half rather than the whole pull, which is why rep
    durations within a deadlift set are uneven. Taking the FIRST concentric
    since the previous impact was tried and is worse: with no previous impact
    to bound it, rep 1 reaches back into the walkout. Neither is right, and
    choosing between them needs the video (A2) rather than another guess.
    """
    chosen = []
    for k in anchors:
        prior = [l for l in lobes if l[0] < k]
        if prior and (not chosen or prior[-1] is not chosen[-1]):
            chosen.append(prior[-1])
    return chosen


def _longest_cadence(chosen, t, tol=1.6):
    """Keep the longest run of candidates that share a cadence.

    Reps in a set come at a regular interval; the unrack does not belong to
    that rhythm and sits seconds away from it. On bench_90x4_1 the four reps
    are 2.16, 2.13 and 2.33 s apart while the unrack sits 15.9 s before the
    first — obvious in the gaps, invisible to shape and to size.

    Ties go to the later run, because a set is always set up first and lifted
    second. That is what resolves bench_92.5x2, where two reps and two setup
    events each form a pair and no cadence argument can separate them.
    """
    if len(chosen) < 3:
        return chosen

    times = [t[l[0]] for l in chosen]
    runs_found = []
    i = 0
    while i < len(chosen):
        j = i + 1
        while j < len(chosen):
            gaps = np.diff(times[i:j + 1])
            # Compare the gaps to EACH OTHER, not to their own median. Against
            # the median, 6.6 s and 12.9 s both sit inside a +/-60% band and a
            # run of three survives with gaps that differ by 2x — which is how
            # bench_92.5x2 kept an extra rep.
            if gaps.min() <= 0 or gaps.max() / gaps.min() > tol:
                break
            j += 1
        runs_found.append((j - i, float(np.median(times[i:j])), i, j))
        i += 1

    best = max(runs_found, key=lambda r: (r[0], r[1]))
    return chosen[best[2]:best[3]]


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
    chosen = _longest_cadence(([l for l, k in zip(lobes, best) if k]), t)

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
    form breakdown. A rail is outside what any sensor can report. A grind is
    ugly but physically plausible: keep it.

    Clipping is now the only check, and it delegates to `io.clipped_runs`,
    which tests for an actual rail — consecutive samples pinned at one value.
    This used to threshold |accel| against 0.95 * 16 g, an assumption about a
    sensor nobody had checked; B5 measured `deadlift_180x3`'s 21.78 g peak as a
    genuine reading hit by a single sample and replaced the same assumption in
    `io.check_log`. This copy survived it by a day.

    THE STRAP-RESONANCE FLAG WAS REMOVED, 2026-07-30 (#14)
    ------------------------------------------------------
    It claimed that energy above ~10 Hz is strap ring, "where barbell motion
    has essentially none". Three measurements killed it:

    *It fired where resonance cannot be.* Rejection rate by lift: bench 26/30
    (86.7%), deadlift 6/15 (40.0%), squat 1/28 (3.6%). Hard landings happen on
    deadlift and nowhere else, so the flag was ANTI-correlated with the
    phenomenon it claimed to detect — it fired hardest on the quietest lift.

    *Neither formulation can work.* As a FRACTION of band energy it flags quiet
    reps for having little signal at all, which is the bug the task recorded.
    As ABSOLUTE energy — what this docstring used to intend — it separates by
    lift and nothing else: squat 3e3-4e4, bench 6e3-1.4e5, deadlift 5.8e5-7.4e6.
    An absolute threshold is a deadlift detector, because the floor impact is
    real broadband signal.

    *There is no resonance to find at 100 Hz.* The spectrum of the 400 ms after
    each of the 15 floor impacts peaks at 10, 12.5, 15, 20, 22.5, 27.5, 30,
    32.5, 35, 42.5 and 47.5 Hz — no repeatable frequency — with peak/median
    ratios of 2.7-12.5, which is not narrowband. Nyquist is 50 Hz here, and a
    watch-on-strap resonance is plausibly above it, so whatever exists aliases
    to an arbitrary bin. You cannot detect what you cannot resolve.

    None of this says the ringing is imaginary. B6 measured it in integrated
    velocity, decaying over several hundred ms after each impact and leaving the
    rep 0.4-1.5 m/s short of closing, and that is where the deadlift's error
    enters. But a broadband transient is not a detectable resonance, and
    throwing away the rep was never the right response to it — the fix belongs
    in the reconstruction. See CLAUDE.md P6 and `analysis/25`.
    """
    out = []
    for a, b in bounds:
        seg = log["accel"][a:b]
        clipped = io.clipped_runs(seg) > 0
        out.append({"rep": (a, b), "clipped": clipped, "ok": not clipped})
    return out
