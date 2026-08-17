"""Seed and track the plate over a whole clip.

Single frames are not decidable. Measured on 2026-08-12: ranking circle
hypotheses by filled 8-fold slots gets the plate right in 8 of 10 sampled
frames, and the two it misses are not marginal — on `bench_92.5x4_1` it takes a
114 px circle of rack clutter over the 85 px plate beside it, and on
`deadlift_185x3` it takes a plate stacked on a rack in the background over the
loaded bar in the foreground. Both are perfectly good circles of bright points.

What separates them from the bar is available only across frames:

  - the bar's plate is in EVERY frame, at a radius that barely changes;
  - the bar MOVES, and gym furniture does not.

The second is the one that fixes C31's recorded failure. C31 found
`markers._trial_merit` rewarding rigidity, which furniture maximises, and could
not find any constant that separated them. Motion is used here at the level of
a whole-clip hypothesis, never as a per-detection filter — the latter is what
C31 measured to be unfixable, since a squat single leaves the bar motionless
for most of its clip and its stickers then look exactly as static as a rack.
"""
from __future__ import annotations

import numpy as np

from . import geom
from .detect import strict_pts


def sample_frames(n_frames, n=48):
    return np.unique(np.linspace(0, n_frames - 1, min(n, n_frames)).astype(int))


def _pool(dets, shape, idxs, radii, rings, top=8, scan=800, max_dets=80,
          lattice=True, min_slots=4):
    pool = []
    for i in idxs:
        pts = strict_pts(dets[i], max_dets)
        for h in geom.frame_hypotheses(pts, shape, radii, rings, top=top,
                                       scan=scan, min_inliers=4,
                                       lattice=lattice, min_slots=min_slots):
            h["frame"] = int(i)
            pool.append(h)
    return pool


def candidates(dets, shape, radii=None, rings=None, n_sample=48, r_tol=7.0,
               keep=8, lattice=True, min_slots=4):
    """Shortlist of radius clusters, each a plausible plate, best evidence first.

    No motion term and no attempt to decide here. Deciding needs the tracker —
    see `choose`.
    """
    if radii is None:
        radii = np.arange(geom.R_MIN, geom.R_MAX, 1.5)
    if rings is None:
        rings = geom._ring_offsets(radii)
    idxs = sample_frames(len(dets), n_sample)
    pool = _pool(dets, shape, idxs, radii, rings, lattice=lattice,
                 min_slots=min_slots)
    if not pool:
        return []
    out = []
    for r0 in np.arange(geom.R_MIN, geom.R_MAX, 2.0):
        grp = [h for h in pool if abs(h["r"] - r0) <= r_tol]
        if not grp:
            continue
        best = {}
        for h in grp:
            f = h["frame"]
            if f not in best or h["merit"] > best[f]["merit"]:
                best[f] = h
        frames = sorted(best)
        if len(frames) < 3:
            continue
        slots = np.array([best[f]["nslot"] for f in frames])
        rr = np.array([best[f]["r"] for f in frames])
        out.append(dict(r=float(np.median(rr)), frames=frames, best=best,
                        coverage=len(frames) / len(idxs),
                        slots_mean=float(slots.mean()),
                        evidence=float(np.clip(slots - (min_slots - 1),
                                              0, None).sum()),
                        n_sampled=len(idxs)))
    out.sort(key=lambda c: -c["evidence"])
    # Drop near-duplicate radii, keeping the strongest of each.
    kept = []
    for c in out:
        if all(abs(c["r"] - k["r"]) > 8 for k in kept):
            kept.append(c)
        if len(kept) >= keep:
            break
    return kept


def rom_plausibility(travel_m, rom_lo, rom_hi=None, hi_slack=1.5):
    """One-sided prior: over a whole clip the bar moves at least one rep's ROM.

    Deliberately one-sided. Travel ABOVE the per-rep range is normal and is not
    penalised — a squat clip contains the walkout, a bench clip the un-rack, and
    C24 measured that un-rack adding about 3 cm to whole-clip travel. Travel
    BELOW it is the failure this whole exercise is about: C31 found six squat
    clips reporting 0.2 to 24.7 cm of travel for 65-70 cm squats, behind
    coverage of 96-100% and healthy residuals.

    Used to CHOOSE among hypotheses, which is a stronger use than C31's
    post-hoc `implausible` flag, and worth being explicit about: it means the
    tracker is told what lift it is looking at. That is information the file
    name already carries and that `truth.VERTICAL_ROM_M` already encodes. It
    cannot manufacture a good track — it only breaks ties between hypotheses
    that already survived coverage, slot count and smoothness.
    """
    if rom_lo is None:
        return 1.0
    p = 1.0 if travel_m >= rom_lo else max(1e-3, (travel_m / rom_lo) ** 2)
    # And a generous ceiling. Purely one-sided was not enough: nothing then
    # penalises a hypothesis that sweeps far MORE than the lift allows, and
    # `bench_92.5x6_2` was handed a 91.6 px candidate reporting 50.6 cm of
    # travel over a 27.0 cm one that was right. Whole-clip travel is the rep's
    # ROM plus the un-rack, so 1.5x the band's top is loose enough for a squat
    # walkout and still refuses a 50 cm bench.
    if rom_hi is not None and travel_m > hi_slack * rom_hi:
        p *= max(1e-3, (hi_slack * rom_hi / travel_m) ** 2)
    return float(p)


def score_track(trk, r, m_per_px=None, rom_lo=None, rom_hi=None):
    """Rate a trial track: does it look like a barbell plate being followed?

    The three terms are chosen so that the two things that beat the plate in a
    single frame both fail here. Rack clutter loses SLOTS — it rarely sustains
    eight — and a hypothesis that hops between different bits of furniture
    loses SMOOTHNESS, because a plate at 30 fps moves a couple of pixels a
    frame and a hop moves fifty.
    """
    ok = [t for t in trk if t is not None]
    if len(ok) < 5:
        return dict(score=0.0, coverage=0.0, slots=0.0, jitter=999.0,
                    travel=0.0, rms=999.0)
    cov = len(ok) / len(trk)
    slots = float(np.median([len(t["slots"]) for t in ok]))
    cy = np.array([t["cy"] for t in ok])
    cx = np.array([t["cx"] for t in ok])
    fr = np.array([t["frame"] for t in ok])
    step = np.diff(fr)
    d = np.hypot(np.diff(cy), np.diff(cx)) / np.maximum(step, 1)
    jitter = float(np.median(d))
    travel = float(np.ptp(cy) / max(1e-6, r))
    rms = float(np.median([t["rms"] for t in ok]))
    lo_p, hi_p = np.percentile(cy, [1, 99])
    travel_m = float((hi_p - lo_p) * m_per_px) if m_per_px else None
    plaus = (rom_plausibility(travel_m, rom_lo, rom_hi)
             if travel_m is not None else 1.0)
    score = cov * slots * np.exp(-jitter / 8.0) * np.exp(-rms / 6.0) * plaus
    return dict(score=float(score), coverage=cov, slots=slots, jitter=jitter,
                travel=travel, rms=rms, travel_m=travel_m, plaus=plaus)


def choose(dets, shape, cands, tracker, verbose=False, circle_m=None,
           rom_lo=None, rom_hi=None):
    """Trial-track every shortlisted candidate and keep the one that follows a bar."""
    scored = []
    for c in cands:
        trk = tracker(dets, shape, c)
        mpp = ((circle_m / 2.0) / c["r"]) if circle_m else None
        s = score_track(trk, c["r"], m_per_px=mpp, rom_lo=rom_lo,
                        rom_hi=rom_hi)
        s["r"] = c["r"]
        s["evidence"] = c["evidence"]
        scored.append((s, c, trk))
        if verbose:
            print(f"   r={c['r']:6.1f} ev={c['evidence']:5.1f} -> cov={s['coverage']:.2f} "
                  f"slots={s['slots']:.1f} jit={s['jitter']:5.1f} rms={s['rms']:4.1f} "
                  f"travel={s['travel']:5.2f} tm={s['travel_m'] or -1:5.3f} "
                  f"pl={s['plaus']:.2f} SCORE={s['score']:6.2f}")
    if not scored:
        return None
    for s, c, _t in scored:
        s["blob"] = ring_blob(dets, c)
    scored.sort(key=lambda t: -t[0]["score"])
    return prefer_sticker_ring(scored)


# How close two candidates' scores must be before appearance is allowed to
# decide between them. Wide, because the ties this exists for are ties: on
# `deadlift_185x3` the top three scored 6.782 / 6.768 / 6.118, a 0.2% and a 10%
# gap, while their appearance differed by a factor of 3.6.
TIE_WINDOW = 0.80


def ring_blob(dets, cand, tol=3.0, max_dets=80):
    """Median blob-ness of the detections a candidate's circle sits on.

    `detect` scores every detection for how much it looks like an isolated
    bright disc, and the seeder throws that away, keeping only y and x. For
    finding the plate that is right — eight points on a circle is a coincidence
    clutter does not supply, and needs no threshold on brightness. For choosing
    between CONCENTRIC circles it is not, because the rival rings are real.
    """
    vals = []
    for f in cand["frames"]:
        d = np.asarray(dets[f], float)
        d = d[d[:, 5] == 0][:max_dets] if d.shape[1] >= 6 else d[:max_dets]
        if len(d) == 0:
            continue
        h = cand["best"][f]
        rr = np.hypot(d[:, 0] - h["cy"], d[:, 1] - h["cx"])
        on = np.abs(rr - h["r"]) < tol
        if on.sum() >= 3:
            vals.append(np.median(d[on, 2]))
    return float(np.median(vals)) if vals else 0.0


def prefer_sticker_ring(scored):
    """Among near-tied candidates, take the one whose points look like stickers.

    A plate carries more than one ring of eight evenly spaced features — its
    cutouts, its bolt circle, and the two ends of each sticker, since the
    markers have radial extent and a sub-pixel centroid can sit at either. All
    of them are genuine circles, so the 8-fold prior cannot choose, and the
    scores come out within a fraction of a percent of one another.

    **That is not a tie worth leaving to chance, because the radius IS the
    pixels-to-metres scale.** Adding a tracking guard flipped `deadlift_185x3`
    from 81.4 px to 72.0 and moved whole-clip travel 54.6 -> 64.1 cm, against
    the plate template's 52.7 for the same clip. A guard on tracking quality
    must not be able to move the ruler.

    Measured on three deadlifts, the sticker ring's median blob-ness beats every
    rival ring by 3.6x to 5x — 0.339 against 0.077-0.095, 0.267 against
    0.035-0.054, 0.319 against 0.056-0.076 — and in each case the ring it picks
    is the one that agrees with the independent referee. The separation is large
    enough that this is a tie-break rather than a tuned threshold, and it is
    applied only inside `TIE_WINDOW` so it can never overrule a clear winner.
    """
    if len(scored) < 2:
        return scored
    top = scored[0][0]["score"]
    if top <= 0:
        return scored
    near = [t for t in scored if t[0]["score"] >= TIE_WINDOW * top]
    rest = [t for t in scored if t[0]["score"] < TIE_WINDOW * top]
    near.sort(key=lambda t: -t[0].get("blob", 0.0))
    return near + rest


def seed_clip(dets, shape, radii=None, rings=None, n_sample=48, r_tol=7.0):
    """Pick the plate's radius and a set of frames where it is confidently found.

    Returns a dict with the chosen radius, the per-sampled-frame best circle,
    and the diagnostics that decided it — including the runner-up, so a caller
    can see how close the decision was.
    """
    if radii is None:
        radii = np.arange(geom.R_MIN, geom.R_MAX, 1.5)
    if rings is None:
        rings = geom._ring_offsets(radii)
    idxs = sample_frames(len(dets), n_sample)
    pool = _pool(dets, shape, idxs, radii, rings)
    if not pool:
        return None

    # Cluster by radius. The plate's apparent radius changes by a few per cent
    # across a clip (it moves toward and away from the camera); clutter at a
    # different scale lands in a different bin.
    cands = []
    for r0 in np.arange(geom.R_MIN, geom.R_MAX, 2.0):
        grp = [h for h in pool if abs(h["r"] - r0) <= r_tol]
        if not grp:
            continue
        best = {}
        for h in grp:
            f = h["frame"]
            if f not in best or h["merit"] > best[f]["merit"]:
                best[f] = h
        frames = sorted(best)
        if len(frames) < max(3, 0.3 * len(idxs)):
            continue
        cy = np.array([best[f]["cy"] for f in frames])
        cx = np.array([best[f]["cx"] for f in frames])
        slots = np.array([best[f]["nslot"] for f in frames])
        rr = np.array([best[f]["r"] for f in frames])
        # Motion, in units of the plate's own radius, so it is scale free.
        travel = float(np.hypot(np.ptp(cy), np.ptp(cx)) / np.median(rr))
        cands.append(dict(
            r=float(np.median(rr)), frames=frames, best=best,
            coverage=len(frames) / len(idxs),
            slots_mean=float(slots.mean()),
            slot_sum=float(np.clip(slots - 4, 0, None).sum()),
            travel=travel,
            r_spread=float(np.std(rr) / max(1e-6, np.median(rr))),
        ))
    if not cands:
        return None

    for c in cands:
        # Coverage and slot evidence carry the decision; motion is a bounded
        # bonus rather than a gate, because a heavy single really does leave the
        # bar nearly still for most of its clip.
        c["score"] = c["slot_sum"] * (1.0 + min(c["travel"], 1.5)) \
            * (1.0 - min(0.5, c["r_spread"] * 3))
    cands.sort(key=lambda c: -c["score"])
    out = dict(cands[0])
    out["runner_up"] = {k: cands[1][k] for k in
                        ("r", "coverage", "slots_mean", "travel", "score")} \
        if len(cands) > 1 else None
    out["n_sampled"] = len(idxs)
    return out
