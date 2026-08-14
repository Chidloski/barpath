"""Find and track the sticker circle in data_v2 footage.

The prior this rests on, from the owner (2026-08-12): every `data_v2` plate
carries **8 stickers around its circumference**, some of which may be clipped
by the frame edge, and the plate is a **perfect circle**, so any skew in its
image is perspective or tilt.

That prior is much stronger than the one `markers.py` was built on (three
stickers plus a hub, with an ellipse path bolted on later), and it licenses a
different shape of algorithm: never rank a marker by how it looks, only by
whether it sits on a circle that the other seven also sit on.

Two design decisions worth stating, because both are choices against something
that was already tried and recorded.

**Detections are never suppressed for being static.** C31 (2026-08-07) traced
the squat failures to `markers.static_points` suppressing the *bar's own*
stickers, because a squat single leaves the bar motionless for most of the clip,
and found no `recur_max` that works on all three squats — the admissible values
were 0.70 / 0.90 / 1.01, disjoint. So recurrence cannot be a per-detection
filter. Motion enters here one level up, as a term in the score of a whole
*hypothesis*, where a static hypothesis is furniture and a moving one is a
barbell. That is also the fix for C31's other finding — `_trial_merit` rewarded
rigidity, and gym furniture is maximally rigid.

**The circle is fitted, not the appearance.** `candidates` in `markers.py` has
three admission gates on brightness and triangle shape, all three of which C21
found sitting at zero margin on the footage they were tuned against. None of
them appear here. Eight points on a common circle is a coincidence background
clutter does not supply, and it needs no threshold on how bright a sticker is.
"""
from __future__ import annotations

import numpy as np

# The sticker circle's radius, as a fraction of the plate's outer radius, is
# NOT used to find anything here — it only converts pixels to metres at the
# end. `markers.STICKER_RATIO` is 0.858, measured on 2026-08-01 footage and
# flagged there as transferred rather than measured for other plates.
# Kept as a parameter so the caller decides.

# A detection counts as on the circle if it is within this many pixels of it.
# At 360x640 a sticker is ~5 px across and `detect` locates it to well under a
# pixel, so this is dominated by how non-circular the projection is (tilt), not
# by detection noise.
RING_TOL = 3.0

# The sticker circle's radius in pixels, searched over this band. The plates run
# 150-220 px across in this footage, so the sticker circle sits near 65-110 px;
# the band is deliberately wider than that on both sides.
R_MIN, R_MAX = 45.0, 145.0


# ------------------------------------------------------------- geometry --
def _ring_offsets(radii, step=1.0):
    """Pre-computed integer (dy, dx) rings, one per radius, for the vote."""
    out = []
    for r in radii:
        n = max(8, int(2 * np.pi * r / step))
        t = np.linspace(0, 2 * np.pi, n, endpoint=False)
        out.append((np.round(r * np.sin(t)).astype(np.int32),
                    np.round(r * np.cos(t)).astype(np.int32)))
    return out


def vote_centres(pts, shape, radii, rings, bin_px=2):
    """Circle-Hough accumulator over candidate centres, one plane per radius.

    Every detection votes for every centre that would put it on a circle of
    radius r — i.e. a ring of radius r about the detection. Eight stickers on a
    common circle put eight votes on the same cell.
    """
    H, W = shape
    hb, wb = int(np.ceil(H / bin_px)), int(np.ceil(W / bin_px))
    acc = np.zeros((len(radii), hb, wb), np.int16)
    py = np.round(pts[:, 0]).astype(np.int32)
    px = np.round(pts[:, 1]).astype(np.int32)
    for k, (dy, dx) in enumerate(rings):
        yy = ((py[:, None] + dy[None, :]) // bin_px).ravel()
        xx = ((px[:, None] + dx[None, :]) // bin_px).ravel()
        ok = (yy >= 0) & (yy < hb) & (xx >= 0) & (xx < wb)
        np.add.at(acc[k], (yy[ok], xx[ok]), 1)
    return acc


def _refine(pts, cy, cx, r, tol=RING_TOL, iters=3):
    """Least-squares circle through the inliers, re-selecting them each pass."""
    for _ in range(iters):
        d = np.hypot(pts[:, 0] - cy, pts[:, 1] - cx)
        inl = np.abs(d - r) < tol
        if inl.sum() < 3:
            return cy, cx, r, inl
        p = pts[inl]
        # Kasa fit: solve for centre and radius linearly.
        A = np.column_stack([2 * p[:, 0], 2 * p[:, 1], np.ones(len(p))])
        b = (p ** 2).sum(1)
        try:
            sol, *_ = np.linalg.lstsq(A, b, rcond=None)
        except np.linalg.LinAlgError:
            return cy, cx, r, inl
        cy, cx = sol[0], sol[1]
        r = np.sqrt(max(1e-6, sol[2] + cy ** 2 + cx ** 2))
    d = np.hypot(pts[:, 0] - cy, pts[:, 1] - cx)
    return cy, cx, r, np.abs(d - r) < tol


def angular_spread(pts, cy, cx):
    """Largest angular gap between consecutive inliers, in degrees.

    This is the check that separates a plate from a row of rack holes. Points
    strung along an arc fit a large circle beautifully and leave a gap of nearly
    360 degrees; eight stickers round a rim leave about 45.
    """
    if len(pts) < 3:
        return 360.0
    a = np.sort(np.arctan2(pts[:, 0] - cy, pts[:, 1] - cx))
    gaps = np.diff(np.concatenate([a, a[:1] + 2 * np.pi]))
    return float(np.degrees(gaps.max()))


def symmetry8(pts, cy, cx):
    """How close the inliers are to lying on an 8-fold evenly spaced circle.

    |mean(exp(8 i theta))| over the inlier bearings: 1.0 when every point sits
    on the same 45-degree lattice, ~0 for points at unrelated bearings.

    **This is the single strongest discriminator in the problem, and no earlier
    version of the tracker used it.** C26 (2026-08-04) established that a conic
    fit "never asks how the stickers are spaced" and treated that as the whole
    advantage of the eight-sticker layout over the three-sticker one. That is
    true of the *fit* and it does not follow for the *search*: the fit does not
    need even spacing, but the search badly wants it, because a gym frame
    supplies co-circular clutter freely and supplies 45-degree-lattice clutter
    essentially never. Measured on `squat_170x1` frame 597, the plate scores
    0.95 where the next six circle hypotheses score 0.17 to 0.72.

    The owner confirmed the layout on 2026-08-12: eight stickers around the
    circumference on every `data_v2` plate. Perspective and tilt do perturb the
    projected bearings — a circle's evenly spaced points do not stay evenly
    spaced under projection — so this is scored, never required exactly, and
    the 0.95 above is with whatever tilt that capture really has.
    """
    if len(pts) < 3:
        return 0.0
    a = np.arctan2(pts[:, 0] - cy, pts[:, 1] - cx)
    return float(np.abs(np.mean(np.exp(8j * a))))


def lattice_fit(pts, cy, cx, tol_deg=13.0):
    """Fit the 8-fold lattice and report how many DISTINCT slots are filled.

    Returns (n_slots, phase_rad, rms_deg, slot_of_each_point, kept_mask).

    Counting distinct slots rather than scoring `symmetry8` directly is what
    stops clutter winning. Several detections at nearly the same bearing — a
    cluster of highlights on one bit of gym furniture that happens to sit on
    the circle — are all mutually coherent, so they drive `symmetry8` towards 1
    exactly as eight real stickers do. They fill ONE slot. Measured on
    `bench_92.5x4_1` frame 600, the winning clutter circle had bearings spaced
    6, 3, 163, 2, 2, 2, 6, 3, 3 and 81 degrees apart and scored 0.68.
    """
    if len(pts) < 3:
        return 0, 0.0, 180.0, np.zeros(len(pts), int), np.zeros(len(pts), bool)
    a = np.arctan2(pts[:, 0] - cy, pts[:, 1] - cx)
    phase = np.angle(np.mean(np.exp(8j * a))) / 8.0
    step = np.pi / 4
    slot = np.round((a - phase) / step).astype(int)
    resid = np.degrees(np.abs((a - phase) - slot * step))
    keep = resid < tol_deg
    if not keep.any():
        return 0, phase, 180.0, slot % 8, keep
    slots = np.unique(slot[keep] % 8)
    rms = float(np.sqrt(np.mean(resid[keep] ** 2)))
    return len(slots), float(phase), rms, slot % 8, keep


def _distinct(pts, cy, cx, min_sep_deg=20.0):
    """Angularly distinct inliers, for plates with no rotational symmetry."""
    a = np.arctan2(pts[:, 0] - cy, pts[:, 1] - cx)
    order = np.argsort(a)
    keep = np.zeros(len(pts), bool)
    last = -np.inf
    for i in order:
        if np.degrees(a[i] - last) >= min_sep_deg:
            keep[i] = True
            last = a[i]
    d = np.hypot(pts[keep, 0] - cy, pts[keep, 1] - cx)
    rms = float(np.sqrt(np.mean((d - d.mean()) ** 2))) if keep.any() else 99.0
    return int(keep.sum()), 0.0, rms, keep


def frame_hypotheses(pts, shape, radii, rings, top=6, bin_px=2,
                     min_inliers=5, max_gap=170.0, scan=400, tol=None,
                     lattice=True, min_slots=4):
    """Best few circle hypotheses in one frame's detections, ranked by merit.

    Merit is `n_inliers * symmetry8`. Ranking on inlier count alone puts the
    plate second or third behind clutter that happens to be co-circular; the
    symmetry term separates them cleanly.
    """
    if len(pts) < min_inliers:
        return []
    acc = vote_centres(pts, shape, radii, rings, bin_px)
    flat = acc.ravel()
    n = min(scan, flat.size)
    idx = np.argpartition(-flat, n - 1)[:n]
    idx = idx[np.argsort(-flat[idx])]
    out, seen = [], []
    for i in idx:
        k, yb, xb = np.unravel_index(i, acc.shape)
        if flat[i] < min_inliers:
            break
        cy, cx, r, inl = _refine(pts, (yb + 0.5) * bin_px,
                                 (xb + 0.5) * bin_px, radii[k],
                                 tol=RING_TOL if tol is None else tol)
        m = int(inl.sum())
        if m < min_inliers or not (R_MIN <= r <= R_MAX):
            continue
        p = pts[inl]
        if angular_spread(p, cy, cx) > max_gap:
            continue
        if any(abs(cy - c[0]) < 6 and abs(cx - c[1]) < 6 and abs(r - c[2]) < 6
               for c in seen):
            continue
        seen.append((cy, cx, r))
        s8 = symmetry8(p, cy, cx)
        if lattice:
            nslot, phase, rms, _, keep = lattice_fit(p, cy, cx)
            if nslot < min_slots:
                continue
        else:
            # Symmetry-free: the four 2026-08-03 benches carry the OLD
            # three-sticker plate at 129/102/129 degrees (C23), so there is no
            # lattice to fit and the 8-fold merit rejects the real plate. Count
            # angularly distinct inliers instead.
            nslot, phase, rms, keep = _distinct(p, cy, cx)
            if nslot < min_slots:
                continue
        # Slots dominate; the residual only breaks ties between equal-slot
        # hypotheses, and inlier count is not in the merit at all — a hypothesis
        # gains nothing by collecting extra detections in slots it already has.
        merit = nslot - rms / 90.0
        out.append(dict(cy=cy, cx=cx, r=r, n=m, sym8=s8, nslot=nslot,
                        rms=rms, phase=phase, merit=merit,
                        idx=np.nonzero(inl)[0][keep]))
    out.sort(key=lambda d: -d["merit"])
    return out[:top]
