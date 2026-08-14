"""Follow the sticker circle frame to frame, once a clip has been seeded.

The owner's hint is the design: "the constellation lies on a perfect circle
which moves little per frame". So tracking never repeats the global search. It
predicts where the circle will be, collects the detections that land on it,
re-fits, and moves on — with the 8-fold lattice carried along as a phase that
also moves little per frame.

Clipping is handled by not caring about it. A sticker off the frame edge simply
yields no detection and its lattice slot stays empty; the fit uses the slots
that are filled.

Two failures the owner found on 2026-08-13, and what they changed here.

**The deadlift corpus lost whole reps.** Coverage sat at 79-88% and the missing
frames were not scattered — they came in runs of ~85 frames, 2.8 s, each
beginning at a rep's descent. Measured: the centre is moving at **19.8-22.9
px/frame** in the frames before each loss, which is the bar being dropped, and
`_gather` looks for detections within a few pixels of a circle predicted from a
damped constant-velocity model. It misses, coasts, damps the velocity toward
zero, and never gets back.

It never gets back because there was nothing to get back with. And the plate was
never hard to find: re-running the lattice search on the LOST frames, restricted
to radii near the lock, returns the true plate as the **top-ranked hypothesis
with 6-8 filled slots and a radius within 0.0-1.7% of the lock**, on every frame
sampled through every dropout. So `_reacquire` below is not a heuristic patch —
the answer was sitting at rank 1 for 2.8 seconds at a time.

Note this is NOT the motion-blur story the drop invites. The stickers on the
dropout frames rank inside the global top 15 with the same detector settings
that track the rest of the clip; detection was never the failing stage.

**`squat_170x1` walked off the plate while reporting 100% coverage.** Coverage
cannot see it: `_step` succeeded on every frame, just on the wrong points. As
the lifter walks out, the plate is **clipped by the left frame edge**, and the
inliers collapse from 8 slots spanning 48 degrees to 5 spanning 183. A circle
fitted freely through a 180-degree arc has a well-determined radius and a badly
determined centre — the fit slides along the arc's perpendicular — so the
reported fore-aft wandered by tens of pixels, and twice jumped by 200, while
every per-frame diagnostic stayed healthy. That is the fore-aft axis, which is
the one carrying a 1 cm spec.

`_fit_centre_lattice` is the fix and it is the owner's prior used directly: with
eight stickers evenly spaced on a circle of known radius, EACH visible sticker
gives a complete estimate of the centre on its own, because its bearing is known
from its slot. Taking the median over the visible ones is well-conditioned at
any arc span, needs no more than two stickers, and does not care that six of
them are off the side of the frame.
"""
from __future__ import annotations

import numpy as np

from . import geom
from .detect import strict_pts, all_pts

# The bar cannot move faster than this between frames. A dropped deadlift
# arrives at roughly 3 m/s, which at ~2 mm/px and 30 fps is about 50 px/frame,
# so this leaves headroom over the fastest thing in the corpus while still
# rejecting the 200 px jumps `squat_170x1` made when its fit was unconstrained.
MAX_STEP_PX = 75.0

# Re-acquisition gates. The radius band is far tighter than the initial search
# because the plate's apparent size is near-constant within a clip — measured
# spread under 2% across every clip in the corpus.
REACQ_AFTER = 3          # consecutive misses before a fresh search
REACQ_STRIDE = 3         # then retry every this many lost frames
REACQ_R_TOL = 0.12       # accept a hypothesis within this fraction of the lock
REACQ_MIN_SLOTS = 6      # and with at least this many filled lattice slots
REACQ_VERIFY_N = 6       # frames a re-acquisition must survive before it counts
REACQ_VERIFY_OK = 4      # of which this many must hold >= 5 slots

# How far the per-sticker centre estimates may disagree before the lattice fit
# is refused.
#
# **It has to sit between two displacement scales, and 4.0 was too close to the
# lower one.** A wrong slot assignment — the failure this exists to catch —
# displaces an estimate by a good fraction of the radius, 40-90 px here. Motion
# blur during a drop displaces a smeared centroid by a few px: measured on the
# deadlift gaps, lost frames are only 1.1-1.3x less sharp than tracked ones and
# their peak white top-hat is 0.62 against 0.72, so blur THINS and SHIFTS the
# markers rather than erasing them, leaving 5 filled slots whose centres are a
# few pixels off.
#
# At 4.0 the guard was refusing those real frames. It cost `deadlift_150x4_1`
# 7.1% of its frames and a rep — the counter read 3 of 4, because a refused
# stretch landed on a peak. At 8.0, coverage goes 0.929 -> 0.990 and the count
# to 4 of 4, with whole-clip travel **unchanged at 54.0 cm**; on
# `deadlift_160x6_1` 0.983 -> 0.998 at an unchanged 54.3. Disabling the guard
# entirely buys only a further 0.010 and 0.000, so 8.0 is not a slope toward
# having no guard — it is where the real frames stop being refused.
#
# It still protects what it was added for, checked rather than assumed:
# `deadlift_160x4_2` 51.6 cm, `squat_170x1` 58.4 and `bench_92.5x6_2` 27.0 are
# all unmoved at 8.0, against the 58.5 cm and spiked height trace that clip gave
# with no guard at all.
LATTICE_AGREE_PX = 8.0

# Fewest points the lattice fit will accept. THREE is not enough, and the
# failure is quiet: with only three points and 8 px of slack, a lattice-
# consistent fit can be found on clutter at a centre a hundred pixels from the
# truth, and the agreement test cannot object because the three estimates agree
# with each other. Measured on `deadlift_150x4_1`: five frames strayed 10-20 cm
# on the fore-aft axis and every one of them was a 3-slot or 5-slot frame, the
# two worst both being 3. On the 1 cm spec axis that is far worse than the
# frame simply being refused.
LATTICE_MIN_PTS = 4

REACQ_BASE_REACH = 25.0  # px allowed even at zero speed, for detector noise
SPEED_SLACK = 12.0       # px/frame added to the last speed: free fall plus slop
REACQ_MAX_REACH = 450.0  # px, hard ceiling however long the track was lost


def _fit_circle(p, r_hint=None, r_weight=0.0):
    """Kasa circle through points, optionally pulled toward a prior radius."""
    if len(p) < 3:
        return None
    A = np.column_stack([2 * p[:, 0], 2 * p[:, 1], np.ones(len(p))])
    b = (p ** 2).sum(1)
    try:
        sol, *_ = np.linalg.lstsq(A, b, rcond=None)
    except np.linalg.LinAlgError:
        return None
    cy, cx = float(sol[0]), float(sol[1])
    r2 = sol[2] + cy ** 2 + cx ** 2
    if r2 <= 1:
        return None
    return cy, cx, float(np.sqrt(r2))


def _fit_centre_lattice(p, slot, phase, r):
    """Centre from evenly-spaced stickers of known slot, radius held fixed.

    Each sticker's bearing from the centre is `phase + slot * 45 degrees`, so
    each one alone places the centre at `p - r * u(bearing)`. The median over
    the visible stickers is the estimate.

    This is the only fit here that is well-conditioned when the plate is half
    out of frame. A free circle fit through an arc is not: the radius is pinned
    by the arc's curvature but the centre is free to slide along the arc's
    perpendicular, which is exactly the fore-aft axis the spec is about.

    **It is only as good as the slot assignment, so it checks it.** The estimate
    is meaningful because the owner's prior says all eight stickers lie on one
    circle at one radius, evenly spaced — which means the per-sticker estimates
    must AGREE. When the carried phase has drifted, or the points are not the
    plate's stickers at all, they disagree, and returning their median anyway
    puts the centre most of a radius away from the truth while every other
    diagnostic stays healthy. That is what it did on `deadlift_160x4_2` once
    re-acquisition started feeding it four-marker frames: whole-clip travel
    51.5 -> 58.5 cm and a height trace of spikes.

    So the dispersion of the estimates is the test of the assumption that
    licenses the estimator, and it is free.
    """
    if len(p) < LATTICE_MIN_PTS:
        return None
    th = phase + slot * (np.pi / 4)
    ey = p[:, 0] - r * np.sin(th)
    ex = p[:, 1] - r * np.cos(th)
    cy, cx = float(np.median(ey)), float(np.median(ex))
    spread = float(np.median(np.hypot(ey - cy, ex - cx)))
    if spread > LATTICE_AGREE_PX:
        return None
    return cy, cx


def _fit_ellipse(p):
    """Direct least-squares conic through >=5 points; None if not an ellipse."""
    if len(p) < 5:
        return None
    y, x = p[:, 0], p[:, 1]
    my, mx = y.mean(), x.mean()
    s = max(1e-6, np.sqrt(((y - my) ** 2 + (x - mx) ** 2).mean()))
    Y, X = (y - my) / s, (x - mx) / s
    D = np.column_stack([X ** 2, X * Y, Y ** 2, X, Y, np.ones(len(p))])
    try:
        _, _, V = np.linalg.svd(D, full_matrices=False)
    except np.linalg.LinAlgError:
        return None
    a, b, c, d, e, f = V[-1]
    disc = b ** 2 - 4 * a * c
    if disc >= 0:
        return None
    x0 = (2 * c * d - b * e) / disc
    y0 = (2 * a * e - b * d) / disc
    num = 2 * (a * e ** 2 + c * d ** 2 + f * b ** 2 - b * d * e - 4 * a * c * f)
    root = np.sqrt(max(1e-12, (a - c) ** 2 + b ** 2))
    den1, den2 = disc * ((a + c) + root), disc * ((a + c) - root)
    if num / den1 <= 0 or num / den2 <= 0:
        return None
    ax1, ax2 = np.sqrt(num / den1), np.sqrt(num / den2)
    th = 0.5 * np.arctan2(-b, c - a)
    semi_major, semi_minor = max(ax1, ax2), min(ax1, ax2)
    if ax2 > ax1:
        th += np.pi / 2
    return (y0 * s + my, x0 * s + mx, semi_major * s, semi_minor * s, float(th))


def _gather(pts, cy, cx, r, tol):
    d = np.hypot(pts[:, 0] - cy, pts[:, 1] - cx)
    return np.nonzero(np.abs(d - r) < tol)[0]


def _step(pts, cy, cx, r, phase, tol, r_lock, slot_tol=13.0, lattice=True,
          robust=True):
    """One frame: collect points on the predicted circle, re-fit, return state."""
    idx = _gather(pts, cy, cx, r, tol)
    if len(idx) < 3:
        return None
    p = pts[idx]
    if not lattice:
        a = np.arctan2(p[:, 0] - cy, p[:, 1] - cx)
        order = np.argsort(a)
        keep, last = [], -np.inf
        for i in order:
            if np.degrees(a[i] - last) >= 20.0:
                keep.append(i)
                last = a[i]
        p = p[keep]
        if len(p) < 3:
            return None
        fit = _fit_circle(p)
        if fit is None:
            return None
        ncy, ncx, nr = fit
        if r_lock is not None and (nr < 0.75 * r_lock or nr > 1.33 * r_lock):
            ncy, ncx, nr = cy, cx, r
        d = np.hypot(p[:, 0] - ncy, p[:, 1] - ncx)
        return dict(cy=ncy, cx=ncx, r=nr, phase=phase, n=len(p),
                    slots=np.arange(len(p)),
                    rms=float(np.sqrt(np.mean((d - nr) ** 2))), pts=p)
    # Assign to the 8-fold lattice using the CARRIED phase, not a fresh fit:
    # with only three or four stickers visible a fresh phase estimate is
    # ambiguous, and the plate cannot have rotated far since the last frame.
    a = np.arctan2(p[:, 0] - cy, p[:, 1] - cx)
    step = np.pi / 4
    k = np.round((a - phase) / step)
    resid = (a - phase) - k * step
    keep = np.abs(np.degrees(resid)) < slot_tol
    if keep.sum() < 3:
        return None
    p, k, resid = p[keep], k[keep], resid[keep]
    # One detection per slot: the brightest is already first in `pts` order.
    _, first = np.unique(k % 8, return_index=True)
    p, k, resid = p[first], k[first], resid[first]

    slots = (k % 8).astype(int)
    nphase = phase + float(np.mean(resid))

    # Which fit? A free circle is the better estimator when the stickers ring
    # the centre, because it assumes nothing about the spacing and so absorbs
    # tilt. It is the worse one when they do not, and the switch is the arc they
    # span rather than how many there are: five stickers evenly spread pin the
    # centre, five bunched into 180 degrees do not.
    spread = geom.angular_spread(p, cy, cx) if len(p) >= 3 else 360.0
    well_conditioned = len(p) >= 5 and spread <= 100.0
    fit = _fit_circle(p) if well_conditioned else None
    if fit is not None:
        ncy, ncx, nr = fit
        if r_lock is not None and (nr < 0.75 * r_lock or nr > 1.33 * r_lock):
            ncy, ncx, nr = cy, cx, r
    elif robust and r_lock is not None:
        lat = _fit_centre_lattice(p, slots, nphase, r_lock)
        if lat is None:
            return None
        ncy, ncx, nr = lat[0], lat[1], r_lock
    else:
        fit = _fit_circle(p)
        if fit is None:
            return None
        ncy, ncx, nr = fit
        if r_lock is not None and (nr < 0.75 * r_lock or nr > 1.33 * r_lock):
            ncy, ncx, nr = cy, cx, r

    # A barbell cannot teleport. Before this gate `squat_170x1` twice moved its
    # centre 200 px in one frame while reporting a healthy residual.
    if np.hypot(ncy - cy, ncx - cx) > MAX_STEP_PX:
        return None

    d = np.hypot(p[:, 0] - ncy, p[:, 1] - ncx)
    return dict(cy=ncy, cx=ncx, r=nr, phase=nphase, n=len(p),
                slots=np.sort(slots), spread=float(spread),
                rms=float(np.sqrt(np.mean((d - nr) ** 2))), pts=p)


def _reacquire(pts, shape, r_lock, radii, rings, last_cy, last_cx, gap,
               speed):
    """Fresh lattice search near the locked radius, after the track let go.

    Gated three ways: the radius must be within `REACQ_R_TOL` of the lock, the
    hypothesis must fill at least `REACQ_MIN_SLOTS` of the eight, and the centre
    must lie inside a reach window. Without that last gate a background plate on
    a rack is a perfectly good 8-fold hypothesis, and it is the one that gets
    picked.

    **The reach is scaled by how fast the bar was going when the track let go,
    not by a constant, and that distinction is the whole gate.** A constant wide
    enough for a dropped deadlift — lost at 20 px/frame and still accelerating —
    is wide enough to cross a bench press's entire frame, and a first attempt
    using `MAX_STEP_PX * gap` did exactly that: `bench_92.5x6_2` re-acquired a
    plate racked in the background and reported 50.6 cm of travel on a bench
    press, against 27.0 before the fix. The bar's own speed separates the two
    cases without a threshold on the lift, because a bench bar that has just
    been lost was moving slowly and a dropped deadlift was not.

    `SPEED_SLACK` is what a frame of free fall adds (about 0.33 m/s, ~7 px at
    this scale) plus room for the estimate itself being stale.
    """
    hyp = geom.frame_hypotheses(pts, shape, radii, rings, top=4,
                                min_inliers=4, lattice=True,
                                min_slots=REACQ_MIN_SLOTS)
    if not hyp:
        return None
    reach = min(REACQ_MAX_REACH, gap * (speed + SPEED_SLACK) + REACQ_BASE_REACH)
    for h in hyp:
        if abs(h["r"] - r_lock) / r_lock > REACQ_R_TOL:
            continue
        if h["nslot"] < REACQ_MIN_SLOTS:
            continue
        if np.hypot(h["cy"] - last_cy, h["cx"] - last_cx) > reach:
            continue
        return h
    return None


def _verify_reacq(dets, f0, direction, got, r_lock, tol, max_dets, lattice,
                  robust):
    """Does the re-acquired circle survive being tracked on from?

    A single frame cannot tell the bar's plate from a plate racked behind it or
    from a chance constellation on the lifter's shorts — all three are eight
    bright points on a circle of about the right size, and the first version of
    `_reacquire` accepted the latter two. `deadlift_160x4_2` was the cost:
    coverage went 0.837 -> 1.000 and the height trace turned to spikes, with the
    circle sitting on the lifter's shorts at frame 471, while whole-clip travel
    (59.7 cm) and the rep count (4 of 4) both still looked right.

    So make it prove itself. The bar's plate keeps its markers over the next few
    frames; clutter picked up mid-drop does not. This is C23's decide-by-
    verification, which the seeder already uses, applied to re-acquisition —
    and it is the same lesson as C31's, that a per-frame score cannot referee a
    hypothesis about a moving object.
    """
    cy, cx, r = got["cy"], got["cx"], got["r"]
    phase = got.get("phase", 0.0)
    n_ok = 0
    for j in range(1, REACQ_VERIFY_N + 1):
        f = f0 + direction * j
        if not (0 <= f < len(dets)):
            break
        pts = strict_pts(dets[f], max_dets)
        st = _step(pts, cy, cx, r, phase, tol * 1.8, r_lock, lattice=lattice,
                   robust=robust)
        if st is None:
            continue
        if len(st["slots"]) >= 5:
            n_ok += 1
        cy, cx, phase = st["cy"], st["cx"], st["phase"]
    return n_ok >= REACQ_VERIFY_OK


def _start_ok(dets, f0, h, r_lock, tol, max_dets, lattice, robust):
    """Does a multi-start seed survive the same test a re-acquisition must?

    `_reacquire` is verified by trial-tracking and the STARTS are not, which is
    an asymmetry with no argument behind it: both are hypotheses about which
    circle in a frame is the bar, and a start is trusted for a whole direction
    of travel rather than a few frames. `deadlift_150x4_1` is the cost — its
    worst frame (+14.0 cm, six dim inliers on the rack uprights) is the last
    frame of the clip, reached by a backward pass from a start planted where
    the lifter is already re-racking, and nothing ever tested it.

    Verification needs room to run, so it is tried in whichever direction has
    `REACQ_VERIFY_N` frames left. A start too close to both ends to verify is
    accepted rather than refused: the check is meant to catch a start that is
    demonstrably wrong, not to require proof that a short clip cannot supply.
    """
    n = len(dets)
    tried = False
    for direction in (+1, -1):
        if 0 <= f0 + direction * REACQ_VERIFY_N < n:
            tried = True
            if _verify_reacq(dets, f0, direction, h, r_lock, tol, max_dets,
                             lattice, robust):
                return True
    return not tried


def track_clip(dets, shape, seed, tol=6.0, max_dets=80, damp=0.6,
               lattice=True, n_starts=6, reacquire=True, robust=True,
               relaxed=True):
    """Track from several confident frames and merge, keeping the best per frame.

    A single start point loses the whole clip beyond its first bad patch. On
    deadlifts that patch is reliably the floor, where the plate is clipped by
    the bottom of the frame and half its markers are gone, and one start gave
    coverage of 0.55-0.70 on captures the old tracker held at 99-100%.

    Restarting from several independent seed frames fixes it without any
    re-acquisition logic: the frames the forward pass could not reach from one
    start are reached from another, and where two tracks overlap the one seeing
    more markers wins. Starts are spread across the clip rather than taken as
    the top-N by merit, which would cluster them in the same easy stretch.

    Multi-start is not a substitute for `_reacquire`, which is why both are
    here: multi-start crosses a bad patch only if some OTHER start happens to
    reach the far side of it, and on a six-rep deadlift every start meets the
    same six drops.
    """
    n = len(dets)
    out = [None] * n
    ranked = sorted(seed["frames"], key=lambda f: -seed["best"][f]["merit"])
    starts, r_lock = [], seed["r"]
    for f in ranked:
        if all(abs(f - g) > n / (n_starts + 1) for g in starts):
            starts.append(f)
        if len(starts) >= n_starts:
            break
    radii = rings = None
    if reacquire and lattice:
        radii = np.arange(r_lock * (1 - REACQ_R_TOL),
                          r_lock * (1 + REACQ_R_TOL), 1.5)
        rings = geom._ring_offsets(radii)
    chosen = starts or ranked[:1]
    if lattice and len(chosen) > 1:
        kept = [f for f in chosen
                if _start_ok(dets, f, seed["best"][f], r_lock, tol, max_dets,
                             lattice, robust)]
        # Never refuse every start. If none verifies, the clip is hard rather
        # than the starts being wrong, and returning an empty track would turn
        # a degraded capture into a missing one.
        chosen = kept or chosen
    for best_f in chosen:
        _track_from(dets, seed["best"][best_f], best_f, r_lock, out, tol,
                    max_dets, damp, lattice, shape, radii, rings, robust,
                    relaxed)
    return out


def _track_from(dets, h, best_f, r_lock, out, tol, max_dets, damp, lattice,
                shape=None, radii=None, rings=None, robust=True, relaxed=True):
    phase0 = h.get("phase", 0.0)
    n = len(dets)

    for direction in (+1, -1):
        cy, cx, r, phase = h["cy"], h["cx"], h["r"], phase0
        vy = vx = 0.0
        f = best_f
        misses = 0
        lost_speed = 0.0
        while 0 <= f < n:
            pts = strict_pts(dets[f], max_dets)
            pcy, pcx = cy + vy * direction, cx + vx * direction
            st = None
            for t in (tol, tol * 1.8, tol * 3.0):
                st = _step(pts, pcy, pcx, r, phase, t, r_lock, lattice=lattice,
                           robust=robust)
                if st is not None and len(st["slots"]) >= 3:
                    break
                st = None
            if st is None and relaxed:
                # Only now bring in the smear-tolerant detections. They are a
                # noisier list, so they are asked last and only about a circle
                # whose position is already known to within a few pixels.
                wide = all_pts(dets[f], max_dets)
                for t in (tol, tol * 1.8, tol * 3.0):
                    st = _step(wide, pcy, pcx, r, phase, t, r_lock,
                               lattice=lattice, robust=robust)
                    if st is not None and len(st["slots"]) >= 3:
                        break
                    st = None
            # Retry on every third lost frame rather than every one. A rejected
            # re-acquisition costs a Hough over the frame and the dropouts it
            # exists for run 85 frames, so recovering two frames later is free
            # and the clip tracks in a third of the time.
            if (st is None and radii is not None
                    and misses + 1 >= REACQ_AFTER
                    and (misses + 1 - REACQ_AFTER) % REACQ_STRIDE == 0):
                # The prediction has failed for several frames running. Ask the
                # frame directly, rather than coasting on a velocity estimate
                # that was already wrong when the track let go. The reach is
                # scaled by the speed AT THE MOMENT OF LOSS, not the current
                # one, because `vy`/`vx` are damped toward zero on every miss
                # and would understate a drop by the time this fires.
                got = _reacquire(pts, shape, r_lock, radii, rings, cy, cx,
                                 misses + 1, lost_speed)
                if got is not None:
                    cand = _step(pts, got["cy"], got["cx"], got["r"],
                                 got.get("phase", phase), tol * 1.8, r_lock,
                                 lattice=lattice, robust=robust)
                    # Commit only if the re-acquired circle survives a normal
                    # step AND goes on holding its markers for several frames.
                    # Assigning the state first and checking afterwards leaves
                    # the tracker sitting on a rejected hypothesis.
                    if cand is not None and len(cand["slots"]) >= 4 and \
                            _verify_reacq(dets, f, direction, got, r_lock, tol,
                                          max_dets, lattice, robust):
                        cy, cx, r = got["cy"], got["cx"], got["r"]
                        phase = got.get("phase", phase)
                        vy = vx = 0.0
                        st = cand
            if st is None:
                if misses == 0:
                    lost_speed = float(np.hypot(vy, vx))
                misses += 1
                out[f] = out[f] or None
                if misses > 25:
                    break
                cy, cx = pcy, pcx
                vy *= damp
                vx *= damp
            else:
                misses = 0
                nvy = (st["cy"] - cy) * direction
                nvx = (st["cx"] - cx) * direction
                vy = damp * vy + (1 - damp) * nvy
                vx = damp * vx + (1 - damp) * nvx
                cy, cx, phase = st["cy"], st["cx"], st["phase"]
                r = 0.9 * r + 0.1 * st["r"]
                if out[f] is None or len(st["slots"]) > len(out[f]["slots"]):
                    st["frame"] = f
                    out[f] = st
            f += direction
    return out


# THERE IS NO RESIDUAL FILTER HERE, AND THAT IS A MEASURED DECISION.
#
# A post-filter dropping frames whose fit residual exceeded 2.5x the clip median
# shipped briefly and was removed. It did not work, and the way it failed is
# worth keeping: on `deadlift_150x4_1` the residual correlates with the actual
# fore-aft error at **r = +0.007**, so it selected frames essentially at random
# with respect to the fault it was built for. It dropped 34 frames, 14 of them
# with under 2 cm of deviation, while leaving the worst frame in the clip
# (+14.0 cm, residual 1.87 px, under the cap). On `deadlift_160x4_2` the same
# correlation is +0.505 — so it worked by coincidence on one clip and not the
# other, which is the definition of not being a mechanism.
#
# What it cost was coverage: removing it improved coverage on 8 of 8 clips
# measured, by up to 5.6 points, while changing whole-clip travel by at most
# 0.3 cm and no rep count at all. The gaps it produced were 1-4 frames long and
# scattered through the second half of every clip.
#
# The artifacts it was aimed at are removed at their source instead, by
# `_start_ok` — see there. Radius pinning was also tried and rejected; it helped
# one clip's fore-aft by 0.9 cm and inflated the residual on every clip, 5x on
# `bench_spoto_95x5_1`, whose path it did not change at all.


def summarise(trk, fps, r_px, plate_d_m, sticker_ratio):
    """Per-frame path in metres, plus the diagnostics that decide usability."""
    ok = [t for t in trk if t is not None]
    n = len(trk)
    if not ok:
        return None
    m_per_px = (plate_d_m * sticker_ratio / 2.0) / r_px
    cy = np.array([t["cy"] if t else np.nan for t in trk])
    cx = np.array([t["cx"] if t else np.nan for t in trk])
    good = ~np.isnan(cy)
    # Travel from the 1st-99th percentile, not max minus min. A single stray
    # frame at either extreme stretches the range: `deadlift_185x3` reported
    # 67.0 cm from max-min on a track whose resting and locked-out positions
    # differ by about 54, which is what the plate-template referee measured for
    # the same clip (52.7). The percentile pair is still a whole-clip figure and
    # still catches the failure it is there to catch, since a mis-track reports
    # a few centimetres however it is summarised.
    lo_p, hi_p = np.nanpercentile(cy, [1, 99])
    return dict(
        t=np.arange(n) / fps,
        y_px=cy, x_px=cx, ok=good,
        coverage=float(good.mean()),
        height_m=(np.nanmax(cy) - cy) * m_per_px,
        travel_m=float((hi_p - lo_p) * m_per_px),
        travel_raw_m=float((np.nanmax(cy) - np.nanmin(cy)) * m_per_px),
        fore_aft_m=(cx - np.nanmedian(cx)) * m_per_px,
        median_rms=float(np.median([t["rms"] for t in ok])),
        median_slots=float(np.median([len(t["slots"]) for t in ok])),
        m_per_px=m_per_px, r_px=r_px,
    )
