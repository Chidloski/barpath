"""Track every data_v2 clip and report whether the result is usable.

The usability test is the one C31 established and it is the reason this work
exists: a clip whose whole-clip vertical travel falls below the lift's own
`truth.VERTICAL_ROM_M` is not tracking the bar, however healthy its coverage
and residual look. Six squat clips fed travel figures of 0.2 to 24.7 cm into
scored comparisons behind 96-100% coverage.
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).parent))
sys.path.insert(0, "/Users/sam/Desktop/barpath/src")

from detect import detect_clip
import seed as S
import track as T

CACHE = "/Users/sam/.claude/jobs/b4b2d95a/tmp/dets6"
VIDEO = Path("/Users/sam/Desktop/barpath/data_v2/video")

# Per-rep vertical range of motion, metres, from `truth.VERTICAL_ROM_M`.
ROM = {"bench": (0.24, 0.31), "squat": (0.61, 0.68), "deadlift": (0.53, 0.61)}

# Plate the stickers are ON, in metres. The owner's diameters (2026-08-12):
# black notched 42.5, black bumper 44.5, blue calibrated 45.
PLATE_M = {"bench": 0.45, "squat": 0.45, "deadlift": 0.445}

STICKER_RATIO = 0.858     # markers.STICKER_RATIO, transferred not measured


def lift_of(name):
    return name.split("_")[0]


def run_one(path, verbose=False, reacquire=True, robust=True):
    """Two passes: the 8-fold prior first, symmetry-free only if it fails.

    The corpus is mixed. The four 2026-08-03 benches carry the old THREE-sticker
    plate at 129/102/129 degrees (C23), which has no 8-fold lattice at all, so
    the strong prior must be allowed to fail rather than be weakened for
    everybody. Pass 2 is `markers.py`'s premise — points on a common circle,
    nothing about spacing — and is strictly weaker, so it is only reached when
    pass 1 finds nothing that tracks.
    """
    name = Path(path).stem
    dets, fps, shape = detect_clip(path, cache_dir=CACHE)
    lift = lift_of(name)

    # Screening uses two starts and the winner is re-tracked with six. The
    # trial-track is run once per shortlisted candidate, so a thorough track
    # there costs 8x what it buys — coverage only has to be good enough to rank.
    layout, scored = "8-sticker", None
    cands = S.candidates(dets, shape, lattice=True, min_slots=4)
    if cands:
        scored = S.choose(dets, shape, cands,
                          lambda d, sh, c: T.track_clip(
                              d, sh, c, lattice=True, n_starts=2,
                              reacquire=reacquire, robust=robust),
                          verbose=verbose, plate_m=PLATE_M[lift],
                          sticker_ratio=STICKER_RATIO, rom_lo=ROM[lift][0],
                          rom_hi=ROM[lift][1])
    # Accept pass 1 whenever it tracked acceptably, and do NOT compare its score
    # against pass 2's. The two scores are not commensurable: pass 2's `slots`
    # counts any angularly distinct inlier, so it is systematically larger than
    # a lattice slot count, and comparing them hands 8-sticker clips to the
    # weaker model. That is exactly what happened to `bench_spoto_95x5_1`, which
    # has 8 stickers and was scored at r=117.8 px on a plate whose sticker
    # circle is 85.8 — a circle sitting off the plate entirely by frame 678,
    # with a whole-clip travel of 25.3 cm that looked perfectly plausible.
    # Seven, not five or six. Every genuine 8-sticker clip in the corpus tracks
    # at a median of EIGHT filled slots once multi-start tracking is used, while
    # a three-sticker plate can accumulate six spurious ones from clutter that
    # happens to land near the lattice — `bench_92.5x4_1` did exactly that, at
    # r=128.3 px with 6 slots and 52.5 cm of travel on a bench whose real travel
    # is 27.8. So the gap between a real 8-fold plate and a faked one is 8 vs 6,
    # and the gate goes between them.
    # Re-track pass 1's winner properly BEFORE testing the gate. The screening
    # track uses two starts, which under-reports coverage badly on deadlifts —
    # the floor patch that multi-start exists to cross. Gating on the screening
    # number sent `deadlift_160x6_1/2` and `deadlift_150x4_1` down the
    # symmetry-free path, where they returned 104, 128 and 79 cm of travel.
    # Re-track the top THREE, not just the top one. The screening pass is
    # deliberately cheap and does mis-rank: `deadlift_160x6_1/2` had the correct
    # candidate at rank 2 or 3, so re-tracking only rank 1 left the gate testing
    # a hypothesis that was never going to pass, and both fell through to the
    # symmetry-free path despite being 8-sticker captures.
    if scored:
        redone = []
        for s_, c_, _t in scored[:3]:
            trk_ = T.track_clip(dets, shape, c_, lattice=True, n_starts=6,
                                reacquire=reacquire, robust=robust)
            sc_ = S.score_track(trk_, c_["r"],
                                m_per_px=(PLATE_M[lift] * STICKER_RATIO / 2.0) / c_["r"],
                                rom_lo=ROM[lift][0], rom_hi=ROM[lift][1])
            # Carry the appearance measurement across: `score_track` builds a
            # fresh dict and the tie-break below needs it. Recomputing it here
            # would give the same answer at the cost of another pass over the
            # detections, since it depends only on the candidate.
            sc_["blob"] = s_.get("blob", 0.0)
            redone.append((sc_, c_, trk_))
        redone.sort(key=lambda t: -t[0]["score"])
        redone = S.prefer_sticker_ring(redone)
        scored = redone + list(scored[3:])
    good = scored and scored[0][0]["slots"] >= 7 and scored[0][0]["coverage"] >= 0.6
    if not good:
        cands2 = S.candidates(dets, shape, lattice=False, min_slots=3)
        if cands2:
            sc2 = S.choose(dets, shape, cands2,
                           lambda d, sh, c: T.track_clip(d, sh, c, lattice=False,
                                                         n_starts=2),
                           verbose=verbose, plate_m=PLATE_M[lift],
                           sticker_ratio=STICKER_RATIO, rom_lo=ROM[lift][0],
                          rom_hi=ROM[lift][1])
            if sc2:
                scored, layout = sc2, "3-sticker"
    if not scored:
        return dict(name=name, ok=False, reason="no candidates")
    s, c, trk = scored[0]
    if layout != "8-sticker":
        trk = T.track_clip(dets, shape, c, lattice=False, n_starts=6)
        s = S.score_track(trk, c["r"],
                          m_per_px=(PLATE_M[lift] * STICKER_RATIO / 2.0) / c["r"],
                          rom_lo=ROM[lift][0], rom_hi=ROM[lift][1])
    summ = T.summarise(trk, fps, c["r"], PLATE_M[lift], STICKER_RATIO)
    lo, hi = ROM[lift]
    # Flag only GROSS failures. The video referee legitimately reads a squat at
    # 57.5-58.1 cm against the IMU's 66-69 (CLAUDE.md, C31), so a flag at the
    # band's own lower edge would condemn a correct track. The failures this is
    # for are 14.0 and 24.7 cm on a 61-68 cm squat: 0.23 and 0.40 of rom_lo,
    # against 0.95 for the correct one.
    return dict(name=name, lift=lift, ok=True, trk=trk, summary=summ,
                r_px=c["r"], score=s, layout=layout,
                runner_up=scored[1][0] if len(scored) > 1 else None,
                implausible=summ["travel_m"] < 0.6 * lo)


if __name__ == "__main__":
    names = sys.argv[1:] or sorted(p.stem for p in VIDEO.glob("*.mov"))
    print(f"{'capture':34s} {'layout':>10} {'r_px':>5} {'cov':>5} {'slot':>4} "
          f"{'rms':>5} {'jit':>5} {'travel_m':>8} {'verdict':>11}")
    for n in names:
        try:
            res = run_one(VIDEO / f"{n}.mov")
        except Exception as e:                       # noqa: BLE001
            print(f"{n:38s} ERROR {type(e).__name__}: {e}")
            continue
        if not res["ok"]:
            print(f"{n:38s} {res['reason']}")
            continue
        s, sm = res["score"], res["summary"]
        verdict = "IMPLAUSIBLE" if res["implausible"] else "ok"
        print(f"{n:34s} {res['layout']:>10} {res['r_px']:5.1f} "
              f"{sm['coverage']:5.2f} {s['slots']:4.1f} {sm['median_rms']:5.2f} "
              f"{s['jitter']:5.2f} {sm['travel_m']:8.3f} {verdict:>11}")
