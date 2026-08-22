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
is one spike per rep — it gets 6/6, 6/6 and 3/3 on the three deadlift captures
including one rep that shape-matching misses. This is not a per-lift lookup
table: the anchors are used when the physics provides them and ignored when it
does not, which the signal decides for itself. Bench and squat produce at most
one spurious impact (the re-rack).

*This paragraph said "a 15-21 g spike ... and unmistakable" until 2026-08-15.
It is neither. The 2026-08-08 captures hold real landings at 6.69 and 8.18 g,
and a wrist swing on `deadlift_150x4_1` that reaches 7.01 g with the bar
provably still on the floor. Height does not separate them; see
`impact_anchors`.*

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

**Two failures the 2026-07-30 captures added, both fixed 2026-07-31 (C5), and
they do not share a mechanism.**

`bench_spoto_90x5_1` counted six reps in a five-rep set. The cadence tolerance
was 1.6 and admitting the first post-set movement needed 1.573, so a sloppy run
of six outgrew the true run of five on length alone. C5 set the tolerance to
1.45, the middle of a 1.35–1.55 plateau bounded by real data at both ends.
Worth noting what did NOT catch it: the two spurious windows are 2.1 and 2.6 s
against real reps of 2.5–2.9 s, so duration is blind to them. Only their 45.7
and 88.7 cm of vertical, against a 35 cm bench bound, gives them away.

**That plateau closed to nothing on 2026-08-06 (C31a) and the RULE was replaced
rather than the constant.** The four paused squats of that day are the first
captures here with a deliberate dwell at the bottom of every rep, and two of
them counted 3 of 4. The cause is this same function: a paused set's cadence
lengthens rep by rep — `squat_pause_140x4_3`'s gaps are 5.43, 5.85, 8.53 s —
so measured by the run's global spread it is indistinguishable from a set with
a post-set movement tacked on. It needs tol >= 1.574 where `bench_spoto_90x5_1`
needs tol <= 1.572: **disjoint, so no tolerance existed at all.** Comparing each
gap to its NEIGHBOUR separates them (1.460 against 1.531), and breaking
length ties on cadence evenness before lateness widens the plateau to 4.74%.
All 30 labelled captures count correctly, and across all 34 CSVs in the two
raw directories every window that was already correct is bit-identical. See
`_longest_cadence`.

`squat_160x1` counted its one rep correctly and put the window on the re-rack —
18.0 cm of a ~65 cm squat. A single leaves the cluster ranking degenerate: every
candidate is a cluster of one, so the lateness tie-break decides alone, and the
latest movement in any capture is the re-rack. Singletons now rank by
displacement instead. See `_similar_cluster`, which records why that rule is
unfalsified on bench rather than verified there.

Neither is helped by the C3 `phase` column: the lifter re-racks before pressing
"Finish Set", so both spurious windows sit inside `phase == 1`.

**Two defects the 2026-08-08 captures added, fixed 2026-08-15 (G1), and the
second one needed a FOURTH discriminator rather than a better constant.**

`deadlift_150x4_1` counted five. `impact_anchors` reads acceleration magnitude,
and a wrist rotation arrested hard enough clears 6 g on the watch's ~9.5 cm
lever. No threshold separates it from a real landing; the wrist's rotation rate
in the second BEFORE the spike does. See `impact_anchors`.

`bench_117.5x1` counted two, and it is the corpus's first bench SINGLE. All
three discriminators above compare candidates with EACH OTHER — shape, size,
cadence — so each needs a majority of real reps to out-vote the setup. A single
has no majority, and its real press clusters with a setup arm movement at 0.80
correlation and near-identical displacement. The fourth discriminator does not
compare candidates at all: it asks whether the window's bar path is VERTICAL,
which a loaded bench or squat rep is and an arm reach is not. See `_upright`,
including why it abstains on deadlift and why raising `similarity` is a trap.

Honest limit: **bench and squat have no impact anchor and still segment on the
integrated velocity**, which carries 145 cm of in-band error against a 69 cm
signal. Their counts are right; their boundaries are only as good as that
signal. Fixing it is B2 and B6 — removing the in-band error — not a change
here.

Second honest limit, and it is new: **the cadence discriminator is currently
unexercised.** Every capture that constrained it lived in v1, which was deleted
on 2026-08-14, and on the live corpus disabling the cadence rule outright still
counts 16/16. It is kept because its evidence was real, not because anything
here still tests it. See `_longest_cadence` and TASKS.md G1.

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

from . import correct, io


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


def _quiet_before(log: dict, k: int, look_s: float = 1.00,
                  settle_s: float = 0.25, span_s: float = 0.30) -> float:
    """Median wrist rotation rate in the second before the spike at `k`.

    `settle_s` stops short of the spike itself, because the impact JOLTS the
    wrist and the gyro peaks at 9-51 rad/s at every real landing — measuring
    across the peak would score a collision the same as a swing. `span_s` is
    the window the peak sample is located in, so the lead-in is measured from
    the top of the spike rather than from its onset.
    """
    t, fs = log["t"], log["fs"]
    mag = np.linalg.norm(log["accel"], axis=1)
    rate = np.linalg.norm(log["gyro"], axis=1)

    w = int(round(span_s * fs))
    lo, hi = max(k - w, 0), min(k + w, len(t))
    peak = int(np.argmax(mag[lo:hi])) + lo

    lead = slice(max(peak - int(round(look_s * fs)), 0),
                 max(peak - int(round(settle_s * fs)), 1))
    return float(np.median(rate[lead]))


def impact_anchors(log: dict, threshold_g: float = 6.0,
                   refractory_s: float = 1.5,
                   skip_s: float = 5.0,
                   max_wrist_rate: float = 1.3) -> list[int]:
    """Indices of floor impacts — one per rep, on lifts where the bar is set down.

    A deadlift lands with a 7-24 g spike. `refractory_s` collapses the ringing
    that follows into one event, and `skip_s` ignores the calibration pause and
    walk-in.

    Returns [] on lifts that never touch down, which is the correct answer for
    bench and squat and is why the caller can apply this unconditionally.

    **A WRIST SWING COUNTERFEITS A LANDING, and `max_wrist_rate` is what
    rejects it (G1, 2026-08-15).** `deadlift_150x4_1` reported five impacts in
    a four-rep set, and the video is unambiguous: the bar sits flat on the floor
    at 1.4-1.5 cm from 0 s to 11 s, and the extra anchor is at 7.03 s. Read off
    the raw samples it is not a collision at all but a 250 ms RAMP — |a| climbs
    0.7 -> 1.6 -> 3.6 -> 6.9 g while |omega| climbs to 27 rad/s and then snaps
    to a stop. The watch sits ~9.5 cm from the wrist axis (`correct.
    WRIST_OFFSET_M`), so a rotation arrested that hard puts alpha * r = 6.3 g at
    the sensor against the 6.9 g measured. The lifter set their grip; the
    accelerometer cannot tell that from the bar hitting the floor, because on
    magnitude alone it isn't.

    **The threshold could never have separated them.** That is why the rule is
    not a higher `threshold_g`: the counterfeit peaks at 7.01 g and the weakest
    REAL landing in the corpus is 6.69 g. Disjoint, like C31a's cadence
    tolerance before it. The docstring above used to claim "a 15-21 g spike that
    nothing else in a gym produces" — the 2026-08-08 captures falsify it in both
    directions, with real landings at 6.69 and 8.18 g and a non-landing at 7.01.

    **What separates them is the second BEFORE the spike.** A bar in free
    descent hangs off a passive arm: across 28 video- and label-confirmed
    landings the median wrist rate in that second is **0.39-0.98 rad/s**. A
    counterfeit is a movement the lifter is already making, and it is moving
    beforehand. Measured, the whole class:

        28 real floor landings, 6 captures        0.39 - 0.98 rad/s
        5 genuine rack collisions (bench, squat)  0.33 - 0.56   (kept, correctly)
        4 setup wrist swings, 4 captures          1.65 - 2.83   (rejected)

    The rack collisions matter: they are the control. This gate rejects a
    ROTATION, not a quiet impact, so a bar meeting a rack still reads as the
    collision it is. Rep counting is correct across the corpus for any gate in
    [0.98, 2.83]; 1.3 is 33% above the busiest real landing and 21% below the
    quietest counterfeit, and is deliberately below 1.65 so the three bench
    setup swings are rejected too — they change no count today, only because
    they never reach the three anchors `rep_bounds` requires.

    **Three other discriminators were measured and are worse.** Peak-to-
    precursor ratio separates by only 1.41x (1.87 against a worst real 2.64).
    High-frequency energy fraction looks good on the deadlift (0.040 against
    0.112-0.383) and inverts on the control: it flags the squat rack collision
    at 0.030 while passing all four setup swings. And the rotational term
    evaluated AT the peak does not separate at all (0.45-1.64 real against 0.53)
    because the impact itself spins the wrist.

    This stays on raw accelerometer and gyro — no attitude, no integration, no
    filtering — which is the property that makes an anchor worth having. Note
    what it costs: the gate is one-sided, and a lifter who resets their grip in
    the last second of a descent would be refused a real landing.
    """
    t, fs = log["t"], log["fs"]
    mag = np.linalg.norm(log["accel"], axis=1) / 9.80665
    start = int(skip_s * fs)

    peaks: list[int] = []
    for i in np.flatnonzero(mag[start:] > threshold_g) + start:
        if not peaks or t[i] - t[peaks[-1]] > refractory_s:
            peaks.append(int(i))

    if max_wrist_rate is None:
        return peaks
    return [k for k in peaks if _quiet_before(log, k) < max_wrist_rate]


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


def dwell_instants(log: dict, bounds: list[tuple[int, int]],
                   interior: float = 0.6, window_s: float = 0.10) -> list[int]:
    """The quietest instant inside each rep — the bottom of a paused rep. G2.

    The bench and squat analogue of `rest_instants`, and it exists for the same
    reason: to give a lift with no floor impact a LANDMARK, an instant both the
    IMU and the video can name independently. `metrics.pause_landmark` matches
    these against the video's per-rep lowest point, and
    `metrics._video_on_imu_clock` uses the match to corroborate `bench_sync`'s
    correlation — which until now was validated only by transfer from deadlift.

    Found from raw acceleration and gyro only: no attitude, no integration, no
    filtering, the same discipline `impact_anchors` and `rest_instants` keep.
    A landmark derived from the reconstruction could not check a sync that the
    reconstruction is scored through.

    **`interior` is the whole trick and it was found by the rule failing
    without it.** Searched over the WHOLE window this returns the standing
    brace at the window edge rather than the bottom — the lifter holding a
    racked bar is quieter than the same lifter braced at depth under it. On the
    three paused squats that happened on 4 of 12 reps, at phase 0.02-0.16, and
    it wrecked the fit: residual 55-677 ms and an implied clock drift of
    1.6-5.3% where the deadlift's landmark sync measures under 0.25%.
    Restricted to the middle 60% the instants land at phase 0.31-0.54, where
    the video puts the bottom. Every value in 0.4-0.6 gives bit-identical
    answers on all three captures; 0.7 and above lets the brace back in.

    **What this is NOT.** It is not as sharp as a floor impact. Against the
    video's bottoms the per-rep scatter is 83-223 ms, where matched landings
    give the deadlift 11-16 ms. So it corroborates a correlation and bounds a
    whole-rep error; it does not replace `capture.sync` and must not be used to
    fit a slope. `pause_landmark` fits an offset only, for that reason.

    Returns one index per window, so the caller can pair them with rep windows
    positionally. Empty windows are skipped rather than filled.
    """
    fs = log["fs"]
    w = max(int(round(window_s * fs)), 3)
    av = _rolling_var(np.linalg.norm(log["accel"], axis=1), w)
    gv = _rolling_var(np.linalg.norm(log["gyro"], axis=1), w)

    # Scale each channel by its own spread over the record, exactly as
    # `rest_instants` does, so neither dominates the sum by unit choice.
    score = av / (np.median(av) + 1e-12) + gv / (np.median(gv) + 1e-12)

    out = []
    for a, b in bounds:
        n = b - a
        if n < 3:
            continue
        margin = (1.0 - interior) / 2.0
        lo, hi = a + int(margin * n), a + int((1.0 - margin) * n)
        if hi <= lo:
            lo, hi = a, b
        out.append(int(lo + int(np.argmin(score[lo:hi]))))
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
               min_area: float = 0.08,
               position: np.ndarray | None = None) -> list[tuple[int, int]]:
    """Rep boundaries, as [start, stop) index pairs into the log.

    `vertical_velocity` is the world-frame vertical velocity from step 4. It
    may drift by metres; it is band-passed here.

    Two mechanisms, in priority order:

    1. Floor impacts, if the lift has them. Exact on all six deadlift
       captures and immune to every setup false positive.
    2. Otherwise the largest cluster of mutually similar concentric lobes,
       compared in fixed-duration windows so a brief sharp unrack cannot
       masquerade as a broad slow rep.

    `peak_ratio` additionally rejects candidates whose peak speed differs from
    the cluster median by more than this factor. A grinding rep is slower and
    weaker than a fresh one but not by 3x; an unrack is (1.88 m/s against
    0.26 m/s in `bench_92.5x2`). Physical, not fitted.

    `position` is the step-4 integrated position, and supplying it turns on the
    fourth discriminator — how VERTICAL each candidate window is — which acts in
    two places: `_upright` filters a cluster with it, and `_similar_cluster`
    ranks a degenerate cluster by it. It is optional because the three above
    need only the vertical channel, and a caller with nothing but that still
    gets the old behaviour rather than an exception.

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

    all_lobes = _all_lobes(v, t, min_area)
    upright = _upright_ratios(all_lobes, lobes, position, t, len(v))
    chosen = _similar_cluster(v, t, lobes, similarity, peak_ratio, upright)
    chosen = _upright(chosen, upright)

    # ONE IMPACT PER REP means the bar is set down every rep, which decides
    # which side of the concentric the eccentric sits on. `_full_cycles` has
    # always documented `sets_down` as coming from the signal — "so the lift is
    # never named" — and this call site passed a hardcoded False, so on the
    # velocity path it never did (G1, 2026-08-15). Harmless while only bench and
    # squat reached here, and wrong the moment a deadlift did: `deadlift_200x1`
    # has one impact and one rep, and under the bench convention its window ran
    # 13.17-16.97 s at 28.1 cm — the approach plus half a pull, cut off before
    # lockout, against a 40-61 cm band. Under the right one it is 15.51-19.43 s
    # at 55.0 cm, and the video has the pull at 15.7-17.5 s with the bar back
    # down by 19.8.
    #
    # The count comparison is what keeps bench out of it. `bench_92.5x6_1` fires
    # one anchor — the re-rack — against six reps, so it is not one per rep and
    # the bench convention stands. Anything with three or more anchors never
    # reaches this line; it segments on the impacts themselves.
    sets_down = bool(anchors) and len(anchors) == len(chosen)
    return _full_cycles(all_lobes, chosen, sets_down, len(v))


def _upright_ratios(all_lobes: list, lobes: list, position: np.ndarray | None,
                    t: np.ndarray, n: int) -> dict[int, float] | None:
    """Verticality of the window each concentric lobe would produce, by start.

    Computed once and shared, because both users of it — `_similar_cluster`'s
    degenerate-cluster key and `_upright`'s filter — are asking the same
    question of the same windows, and a rule applied twice from two
    computations is a rule that can disagree with itself.
    """
    if position is None:
        return None

    starts = [l[1] for l in all_lobes]
    out = {}
    for peak, a, b, area in lobes:
        k = starts.index(a) if a in starts else None
        window = (a, b) if k is None else _absorb(
            all_lobes, k, a, b, area, False, -1, n, 0.5)
        out[a] = _verticality(position, t, window)
    return out


def _upright(chosen: list, upright: dict[int, float] | None,
             min_ratio: float = 2.0) -> list:
    """Drop cluster members whose window is not a near-vertical bar path.

    **The fourth discriminator, and the first one that is not a property of the
    vertical channel alone (G1, 2026-08-15).** Shape, size and cadence all
    compare candidates with each other, so all three need a MAJORITY of real
    reps to out-vote the setup. `bench_117.5x1` is the corpus's first bench
    single and there is no majority: its winning cluster is the real press at
    21.9 s together with a setup arm movement at 10.6 s, the two correlating
    0.80 in fixed-duration shape and carrying 0.304 and 0.290 m of displacement.
    Nothing that ranks candidates against each other can split that pair.

    **This capture is the one `_similar_cluster` predicted.** That docstring
    records the singleton displacement rule as "unfalsified on bench rather than
    verified there", and says a bench single would land there and pick the
    unrack. It arrived on 2026-08-08 and the prediction held exactly: raising
    `similarity` to 0.83 breaks the false pair and then the singleton rule picks
    the 5.4 s unrack, which carries 0.455 m — the RIGHT COUNT on the WRONG
    WINDOW, `squat_160x1`'s failure again and invisible to a count gate. Do not
    re-try the tolerance; the plateau [0.798, 0.872] is real and it is measuring
    the wrong thing.

    **What separates them is a fact about lifting, not about the signal.** A
    loaded bench or squat rep is a closed kinematic chain — the bar is
    constrained to travel up and down — while setting up is an arm reaching
    freely through as much fore-aft as vertical. Per candidate window, detrended
    by step 7's own `correct.detrend_set` so the drift is not counted as
    excursion:

        36 real bench and squat reps, 9 captures    3.64 - 15.08
        setup movement, bench_117.5x1 at 10.6 s     1.00

    Correct counts hold for `min_ratio` anywhere in [1.02, 3.62] — a 255%
    plateau, bounded below by that setup movement and above by the least
    vertical real rep in the corpus (`bench_92.5x6_2`, 3.64). 2.0 is the round
    value nearest the geometric midpoint, 1.96x clear of the floor and 1.81x
    clear of the ceiling. Within that whole span it changes exactly one capture.

    **It abstains rather than guessing.** When no member of a cluster clears
    `min_ratio` the rule has nothing to say about that capture and returns the
    cluster untouched, on this module's standing preference for silence over a
    false assertion. Nothing in the corpus currently exercises the abstention —
    the only capture that did was `deadlift_200x1`, and it did so because the
    cluster it was handed was the WRONG LOBE. See `_similar_cluster`.

    *An earlier draft of this docstring justified the abstention by claiming
    "`deadlift_200x1`'s real pull scores 2.13, below several of its own
    non-reps". That was wrong, and it was wrong because the lobe at 19.8 s had
    been assumed to be the pull without checking the video. The real pull is at
    16.6 s and scores 2.59 — the HIGHEST of that capture's ten lobes. Verticality
    ranks it correctly; it was the displacement rule that did not. The
    abstention is kept because a deadlift's fore-aft is genuinely real and a
    future capture may need it, not because this one did.*

    **A deadlift is still the lift to watch here.** A pull sweeps the bar in to
    the shins and its fore-aft also carries the invented excursion C12 found, so
    its margins are the corpus's thinnest: 2.59 against a 2.13 runner-up, where
    bench and squat run 4.4x and 12.6x clear. Deadlifts otherwise never reach
    this path at all; they segment on impacts.

    **Measure it on POSITION, not on velocity.** Integrating the band-passed
    velocity inside the window instead — which needs no `position` argument and
    was tried first — collapses the separation to overlapping (worst real 1.69
    against best non-rep 2.35). The detrend is doing the work.
    """
    if upright is None or len(chosen) < 2:
        return chosen

    keep = [upright.get(a, 0.0) >= min_ratio for _, a, _, _ in chosen]
    if all(keep) or not any(keep):
        return chosen
    return [l for l, k in zip(chosen, keep) if k]


def _verticality(position: np.ndarray, t: np.ndarray,
                 window: tuple[int, int]) -> float:
    """Vertical travel over horizontal travel, for one candidate rep window."""
    reps = correct.detrend_set(position, [window], t)
    if not reps:
        return 0.0
    rep = reps[0]
    horizontal = float(np.hypot(np.ptp(rep[:, 0]), np.ptp(rep[:, 1])))
    return float(rep[:, 2].max() - rep[:, 2].min()) / max(horizontal, 1e-9)


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


def _drift(gaps: np.ndarray) -> float:
    """Worst ratio between two ADJACENT gaps. 1.0 means a perfectly even set.

    Symmetric, so a gap that suddenly halves scores the same as one that
    doubles. An empty or single-gap run has no adjacency to score and is 1.0.
    """
    if len(gaps) < 2:
        return 1.0
    return float(np.maximum(gaps[1:] / gaps[:-1], gaps[:-1] / gaps[1:]).max())


def _longest_cadence(chosen, t, tol=1.50):
    """Keep the longest run of candidates that share a cadence.

    Reps in a set come at a regular interval; the unrack does not belong to
    that rhythm and sits seconds away from it. On bench_90x4_1 the four reps
    are 2.16, 2.13 and 2.33 s apart while the unrack sits 15.9 s before the
    first — obvious in the gaps, invisible to shape and to size.

    **A run is admitted on LOCAL drift, not on its global spread (C31a,
    2026-08-06), and ties are broken on cadence QUALITY before lateness.**
    Both changes were forced by the same capture and neither is sufficient
    alone; the history is below because it is the evidence for both.

    Until 2026-08-06 a run was admitted when `gaps.max() / gaps.min() <= tol`
    — the spread of the whole run — and ties went to the later run on the
    grounds that a set is always set up first and lifted second. That rule
    **has no admissible tolerance any more.** The two paused squats of
    2026-08-06 and `bench_spoto_90x5_1` constrain it from opposite sides and
    the constraints are DISJOINT:

        bench_spoto_90x5_1        correct only for tol <= 1.572
        squat_pause_140x4_3       correct only for tol >= 1.574

    So this stopped being a constant that needed re-tuning and became a rule
    that needed replacing, which is what `test_cadence_tolerance_is_a_plateau`
    said to do if it ever failed at an interior value.

    **Why the global spread fails.** A fatiguing set does not keep its cadence;
    it lengthens, rep after rep, as the lifter takes longer to re-breathe and
    re-brace. `squat_pause_140x4_3` is a paused squat and its four reps sit
    5.43, 5.85 and 8.53 s apart — monotonically growing, ratio 1.573 end to
    end, which is *larger* than the 1.573 that the post-set movement of
    `bench_spoto_90x5_1` needs. Measured against the run's global spread the
    two are indistinguishable. Measured against the NEIGHBOURING gap they are
    not: the squat's worst adjacent step is 8.53/5.85 = **1.460**, while the
    bench's post-set gap arrives as a step of 4.50/2.94 = **1.531**. Comparing
    each gap to its neighbour tolerates drift that ACCUMULATES over a long set
    while still refusing a gap that JUMPS.

    **The judgement that encodes:** a lifter's cadence changes gradually within
    a set and discontinuously when the set ends. Falsified by a true rest-pause
    or cluster set, where the lifter deliberately racks and re-breathes mid-set
    — that gap is a genuine jump and this rule will still split it. The paused
    squats are not that; the pause is at the bottom of each rep, inside it.

    **Why lateness alone then mis-ranks.** With local admission,
    `bench_spoto_90x5_1` grows a POST-SET run of five — 39.96, 44.45, 48.23,
    50.77, 53.95 s — that ties the true five on length. Its cadence is 44%
    worse (worst adjacent step 1.488 against the true run's 1.036) and it wins
    anyway, because "set up first, lift second" says nothing about what happens
    AFTER the reps and something always does. That is the same half-argument
    `_similar_cluster` already records for the singleton tie-break. Ranking on
    (length, then evenness, then lateness) puts the true run first and widens
    the usable plateau from 1.93% to 4.74%. Lateness is kept as the last key,
    so `bench_92.5x2` — two reps and two setup events, each a clean pair with
    no adjacency to score — is decided exactly as before, and its admissible
    range is unchanged at [1.02, 1.97].

    **The margin, measured over both raw directories** — the rep-COUNT gate on
    the 30 captures whose filename carries a rep count, plus the stricter
    requirement that across all 34 CSVs every window already correct stays
    bit-identical:

        rule                              admissible tol      width
        global spread + lateness (old)    none — disjoint         —
        global spread + evenness          none — disjoint         —
        local drift   + lateness          [1.4598, 1.4882]     1.93%
        local drift   + evenness (this)   [1.4598, 1.5306]     4.74%

    The edges are two different captures on two different lifts:
    `squat_pause_140x4_3` sets the floor at 1.460 and `bench_spoto_90x5_1` the
    ceiling at 1.531. Every other capture is far from both — the nearest are
    `squat_140x4_3` at >= 1.170 and `bench_92.5x2` at <= 1.970. 1.50 is the
    round value nearest the midpoint of 1.495, 2.7% clear of the floor and
    2.0% clear of the ceiling.

    Read that margin honestly: it is real and bounded by data on both sides,
    but it is thinner than the 8-11% the old constant enjoyed before the paused
    squats existed. A capture that pauses harder than these will push the floor
    up into the ceiling, and the answer then is a discriminator that is not a
    gap ratio at all — the rejected low-velocity lobe that sits inside the long
    gap on both paused squats, and inside neither of `bench_spoto_90x5_1`'s
    post-set gaps, is the obvious unexplored candidate.
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
            # Compare each gap to its NEIGHBOUR, not to the run's own spread
            # and not to its median. Against the median, 6.6 s and 12.9 s both
            # sit inside a +/-60% band and a run of three survives with gaps
            # differing by 2x — which is how bench_92.5x2 kept an extra rep.
            # Against the spread, a set whose cadence drifts monotonically is
            # indistinguishable from one with a post-set gap tacked on.
            if gaps.min() <= 0 or _drift(gaps) > tol:
                break
            j += 1
        span = np.diff(times[i:j])
        runs_found.append((j - i, -_drift(span), float(np.median(times[i:j])),
                           i, j))
        i += 1

    best = max(runs_found, key=lambda r: (r[0], r[1], r[2]))
    return chosen[best[3]:best[4]]


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


def _similar_cluster(v, t, lobes, similarity, peak_ratio, upright=None) -> list:
    """Largest mutually-similar set of lobes, by fixed-duration shape.

    Every candidate is tried as a seed and the clusters are ranked by size,
    then by how late they occur. The tie-break is not arbitrary: a set is
    always set up first and lifted second, so when two equally good clusters
    compete the later one is the reps and the earlier one is the approach.

    `bench_92.5x2` is why this exists. Its unrack and its two paused reps each
    form a clean, internally consistent pair, so size alone picks whichever was
    seeded first — and picking the unrack yields exactly the right rep COUNT
    with entirely the wrong reps.

    **Lateness is only half an argument, and a single exposes it.** "Set up
    first, lift second" correctly rejects everything BEFORE the reps — the
    approach, the unrack, the walkout. It says nothing about what comes AFTER
    them, and something always does: the re-rack, the walk back, setting the
    bar down. On a multi-rep set that never bites, because the reps are the
    largest cluster and size decides before lateness is consulted. On a SINGLE
    there is no cluster to be largest — every candidate is a cluster of one, so
    lateness alone decides, and the latest movement in a capture is by
    construction the re-rack.

    That is exactly how `squat_160x1` failed: a correct count of 1, on the
    re-rack at 37.7 s, giving an 18.0 cm window of a ~65 cm squat, while the
    real rep sat at 33.6 s and yields 67.0 cm. `squat_160x1` is the only
    capture of the 17 whose winning cluster has size 1 — every other has 4 or
    more — so ranking singletons differently cannot disturb the other sixteen.

    **The judgement for singletons WAS concentric displacement** — a working rep
    moves the bar further than the movements that bracket it. On `squat_160x1`
    the rep carried 0.602 m against 0.384 for the walkout and 0.170 for the
    re-rack. It was an argmax, so there was no threshold to fit.

    **It was predicted to fail on bench, it does, and it also fails on a
    deadlift single (G1, 2026-08-15). It is replaced by VERTICALITY.** The
    prediction, kept because it was right: the claim fails wherever the unrack
    lifts the bar further than the rep does, `bench_92.5x2`'s unrack carried
    0.433 m against 0.295 and 0.239 for its two real reps, and "a bench SINGLE
    would land here and this rule would pick the unrack".

    Measured on the three singles the live corpus now holds, against the cached
    video track, displacement gets ONE of three right:

        capture           real rep   argmax displacement   argmax verticality
        squat_170x1         35.0 s   35.0 s  correct       35.0 s  correct
        bench_117.5x1       21.9 s    5.4 s  the unrack    21.9 s  correct
        deadlift_200x1      16.6 s   19.8 s  the DROP      16.6 s  correct

    `deadlift_200x1` is the one that was shipping wrong and nobody had looked:
    the video has the pull at 15.7-17.5 s and the bar back down by 19.8 s, and
    the chosen lobe at 19.77 s carried the largest displacement of the ten
    because the reconstruction invents velocity across the drop. Right count,
    wrong window, `squat_160x1`'s shape exactly.

    So singletons now rank by `_upright_ratios` — the same quantity `_upright`
    filters clusters with, computed once and shared. Still an argmax, still no
    threshold. Margins over the runner-up: 12.6x on the squat, 4.4x on the
    bench, and **1.22x on the deadlift**, which is thin and is the value to
    watch. Displacement remains the fallback when no `position` is supplied.

    **`phase` cannot help.** The C3 column marks the closing hold, not the
    re-rack, and the lifter re-racks before pressing "Finish Set" — so on both
    defective captures every spurious window sits entirely inside `phase == 1`
    (`squat_160x1`'s re-rack at 37.7 s against phase 1 running to 39.3 s).
    Checked, and it separates nothing here.
    """
    shapes = np.array([_shape(v, t, i) for i, _, _, _ in lobes])
    peaks = np.array([np.abs(v[a:b]).max() for _, a, b, _ in lobes])
    times = np.array([t[i] for i, _, _, _ in lobes])
    areas = np.array([abs(a) for _, _, _, a in lobes])

    best, best_score = None, None
    for seed in range(len(lobes)):
        keep = _grow(shapes, peaks, seed, similarity, peak_ratio)
        if not keep.any():
            continue
        n = int(keep.sum())
        # Clusters are only ever compared at equal `n`, so the second key
        # never mixes units across a comparison.
        if n > 1:
            second = float(np.median(times[keep]))
        elif upright is not None:
            second = upright.get(lobes[int(np.argmax(keep))][1], 0.0)
        else:
            second = float(areas[keep].sum())
        score = (n, second)
        if best_score is None or score > best_score:
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
    in the reconstruction. See `FINDINGS.md` P6 and `analysis/25`.
    """
    out = []
    for a, b in bounds:
        seg = log["accel"][a:b]
        clipped = io.clipped_runs(seg) > 0
        out.append({"rep": (a, b), "clipped": clipped, "ok": not clipped})
    return out
