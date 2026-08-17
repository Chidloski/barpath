"""`bar_path` for eight-sticker footage — the third video referee.

`capture.bar_path` matches a template to the dark plate and referees
`data/video/`. `markers.bar_path` fits a rigid constellation and refereed
`data_v2/`. This is the referee for `data_v2/` now, and it exists because
`markers.py` was not good enough on that footage: six of eleven squat clips were
unusable, `squat_170x1` and `squat_pause_140x4_3` reporting 14.0 and 24.7 cm of
whole-clip travel for 60-70 cm squats, behind coverage of 96-100% and healthy
residuals (C31, D2).

**What is different, in one sentence: this one uses the owner's prior that the
eight stickers lie on a CIRCLE AT EVEN SPACING, and uses it in the search rather
than only in the fit.** C26 established that a conic fit "never asks how the
stickers are spaced" and read that as the whole advantage of the eight-sticker
layout. That is true of the fit and false of the search — a gym frame is full of
bright points, and 8-fold rotational symmetry is the strongest thing separating
a plate from rack holes, ceiling strips and the lifter's shoes. See
`geom.symmetry8`.

Three further departures, each forced by a measured failure:

  * **Detection is on WHITENESS, `value * (1 - saturation)`, not brightness.**
    The stickers are white and every plate they sit on is strongly coloured or
    black, so on brightness alone only 4-6 of 8 stickers survive ranking.
    `markers.py` decodes greyscale and cannot make the distinction at all.
  * **Loss of lock is recovered from, not coasted through.** The deadlift
    dropouts ran ~85 frames each from a rep's descent; the plate was never hard
    to find there, ranking top-1 on a restricted search throughout. See
    `track._reacquire`.
  * **A hypothesis proves itself by trial-tracking, never by per-frame score.**
    That is C23's lesson applied to re-acquisition AND to the multi-start seeds
    — the latter is what removed a 14 cm fore-aft artifact on
    `deadlift_150x4_1`. See `track._start_ok`.

Measured over all sixteen `data_v2` clips: **16 of 16 track**, coverage
0.97-1.00, eight filled lattice slots median on every one, none flagged
implausible, and **16 of 16 rep counts match the label**. Per-rep video fore-aft
comes out 4.4-6.0 cm on all six deadlifts, against C27's independently measured
4.3-6.2 on three of them — a replication on three captures C27 never saw.
Evidence and the full comparison: `analysis/tracking/v2_rebuild/REPORT.md`.

**`markers.py` is untouched and still reachable.** It remains the referee for
anything scored with `tracker="markers"`, and its `calibration_report`,
`top_of_travel_residual` and conic machinery carry findings this module does not
reproduce. Nothing here deletes that record.

**THE ABSOLUTE SCALE IS MEASURED AS OF 2026-08-17 (H14), AND EVERY METRE FIGURE
IN THIS MODULE'S HISTORY PREDATES IT.** This used to say the scale was
`STICKER_RATIO = 0.858`, transferred from `markers.py` and not measured, and
that "a tape across the sticker circle settles all sixteen clips at once and is
the highest-value measurement available to this module". The owner supplied that
tape: the stickers are 2.0 cm across and are placed with their outer edge
against the plate rim, so the sticker circle is the plate diameter less 2.0 cm.
See `STICKER_CIRCLE_M`. It moved the scale +4.9% on bench, +6.1% on deadlift and
+11.4% on squat, so **no video-refereed number recorded before that date is
comparable to one recorded after it.**
"""
from __future__ import annotations

from pathlib import Path

import numpy as np

from .detect import detect_clip
from .seed import candidates, choose, prefer_sticker_ring, score_track
from .track import summarise
from .track import track_clip as _follow

# Per-rep vertical range of motion used to RANK candidate constellations.
#
# **Deliberately tighter than `capture.VERTICAL_ROM_M`, and it must not be widened
# to match it.** That constant is a per-capture gate on a finished measurement
# and is wide on purpose — bench (0.20, 0.35) admits both instruments while they
# disagree by 20% (C24). This one is a SCORING prior over rival hypotheses in a
# single frame's search, where the question is "which of these circles moves
# like the lift" and a wide band stops discriminating. Widening it changes which
# hypothesis wins and therefore invalidates every number measured with it.
ROM = {"bench": (0.24, 0.31), "squat": (0.61, 0.68), "deadlift": (0.53, 0.61)}

# Diameter in metres of the plate the stickers are ON. The owner's measurements
# (2026-08-12): black notched 42.5, black bumper 44.5, blue calibrated 45.
#
# **WHICH PLATE EACH LIFT USES IS NOW ANSWERED (owner, 2026-08-17), AND TWO OF
# THESE THREE ENTRIES WERE WRONG AGAINST THIS TABLE'S OWN DEFINITION.** The
# owner: bench loads ONLY black notched, squat ONLY blue calibrated, and a
# deadlift is black notched loaded around black bumpers — so the stickered
# plate is the 425 notched on bench and deadlift, and the 450 blue disc on
# squat. This table said 0.45 for bench (a 425 plate, 5.9% out) and 0.445 for
# deadlift (the BUMPER, which is not the plate the stickers are on — the exact
# error `capture.STICKER_PLATE_DIAMETER_M` was created to fix for the
# 2026-08-04 session, reintroduced here when F1 gave this module its own
# table). Squat's 0.45 was right.
#
# It is kept here rather than routed through `capture.sticker_plate_diameter`
# for the reason F1 gave — that function falls through to `plate_diameter`,
# which answers a different question — but the VALUES are now the owner's
# rather than a fall-through. Reconciling the two tables is still open.
PLATE_M = {"bench": 0.425, "squat": 0.45, "deadlift": 0.425}

# The diameter in metres of the circle the sticker CENTRES sit on. This is what
# the tracker actually measures — `c["r"]` is the fitted radius of the detected
# constellation — and it is now DERIVED FROM A TAPE rather than fitted.
#
# THE GEOMETRY (owner, 2026-08-17). A sticker is 2.0 cm across overall, with a
# 1.3 cm reflective disc inside it, and **it is always placed with its outer
# edge against the outer edge of the plate**. So the centre sits one sticker
# RADIUS — 1.0 cm — inboard of the rim, and the circle is the plate diameter
# less 2.0 cm, on every plate, by construction. The 1.3 cm reflective diameter
# does not enter: it sizes the blob the detector finds, not where its centre is,
# because the reflective disc is concentric with the sticker.
#
# **This replaces `PLATE_M[lift] * STICKER_RATIO` and it is the measurement
# three modules asked for.** `STICKER_RATIO = 0.858` was calibrated on the old
# THREE-sticker plate, whose stickers sat 31.6 mm in from the rim (see
# `markers.STICKER_RATIO`); the eight-sticker plates that make up the ENTIRE
# live corpus are stickered to a different rule and sit 10 mm in. Expressing
# the scale as a fraction of the plate was always the wrong shape for it — the
# inset is an absolute distance, so the fraction differs per plate (0.953 on a
# 425 plate, 0.956 on a 450) and no single ratio can be right for both.
#
#     lift       was: plate x 0.858    now: plate - 2 cm     scale change
#     bench      0.45  x 0.858 = 0.3861    0.425 - 0.020 = 0.405    +4.90%
#     squat      0.45  x 0.858 = 0.3861    0.450 - 0.020 = 0.430   +11.37%
#     deadlift   0.445 x 0.858 = 0.3818    0.425 - 0.020 = 0.405    +6.07%
#
# **What corroborates it, and the check is independent of the tape.** Before
# this change the video read BELOW the IMU's per-rep vertical ROM on 16 of 16
# captures — median ratio 0.926 bench, 0.924 squat, 0.936 deadlift, i.e. a
# systematic ~7% that no per-lift explanation covers. C27 measured the deadlift
# half of it from the other side (video 4.6-9.3% below the reconstruction) and
# said "~0.92 would close it exactly". The tape predicts +6.07% on deadlift,
# inside that range and nowhere near a free parameter. Applied, the three
# medians become 0.971 / 1.029 / 0.993.
#
# **Read the residual honestly.** The correction removes a common bias and
# leaves a WIDER spread between lifts than it found (0.012 -> 0.058). If the
# truth were instead "the IMU reads ~7% high on ROM for all three lifts", this
# change would be double-counting — but that hypothesis has to explain away a
# direct measurement of the referee's own geometry, which this is and which the
# 0.858 never was. The video/IMU ratio is the CHECK here, not the source.
STICKER_CIRCLE_M = {lift: d - 0.020 for lift, d in PLATE_M.items()}

# The old fitted constant, kept only so `calibration_report`-style diagnostics
# and the historical record still resolve. NOT used to scale anything here.
STICKER_RATIO = 0.858       # markers.STICKER_RATIO — the THREE-sticker plate

# Below this fraction of the lift's own lower ROM bound the track is not the
# bar. Gross failures only: the video referee legitimately reads a squat 15%
# below the IMU, so a flag at the band's edge would condemn a correct track.
# The failures this is for are 14.0 and 24.7 cm on a 61-68 cm squat.
IMPLAUSIBLE_FRAC = 0.6


def _lift_of(name) -> str:
    return Path(name).stem.split("_")[0]


def track_clip(video, cache_dir=None, verbose=False, reacquire=True,
               robust=True):
    """Seed, track and summarise one clip. Returns the internal result dict.

    Two passes: the 8-fold prior first, the symmetry-free model only if it
    fails. The corpus is mixed — the 2026-08-03 benches carry the old THREE
    sticker plate at 129/102/129 degrees, which has no 8-fold lattice at all —
    so the strong prior must be allowed to fail rather than be weakened for
    everybody.

    **Pass 1's score is never compared against pass 2's.** They are not
    commensurable: pass 2's `slots` counts any angularly distinct inlier, so it
    is systematically larger than a lattice slot count, and comparing them hands
    8-sticker clips to the weaker model. `bench_spoto_95x5_1` was exactly that —
    8 stickers, scored at r = 117.8 px on a plate whose sticker circle is 85.8.
    """
    video = Path(video)
    dets, fps, shape = detect_clip(video, cache_dir=cache_dir)
    lift = _lift_of(video)
    circle_m, (rom_lo, rom_hi) = STICKER_CIRCLE_M[lift], ROM[lift]

    layout, scored = "8-sticker", None
    cands = candidates(dets, shape, lattice=True, min_slots=4)
    if cands:
        scored = choose(
            dets, shape, cands,
            lambda d, sh, c: _follow(
                d, sh, c, lattice=True, n_starts=2, reacquire=reacquire,
                robust=robust),
            verbose=verbose, circle_m=circle_m,
            rom_lo=rom_lo, rom_hi=rom_hi)

    # Re-track the top THREE properly before testing the gate. Screening uses
    # two starts and under-reports coverage badly on deadlifts — the floor patch
    # multi-start exists to cross — and it does mis-rank: `deadlift_160x6_1/2`
    # had the correct candidate at rank 2 or 3, so re-tracking only rank 1 sent
    # both down the symmetry-free path at 104 and 128 cm of travel.
    if scored:
        redone = []
        for s_, c_, _t in scored[:3]:
            trk_ = _follow(dets, shape, c_, lattice=True, n_starts=6,
                                     reacquire=reacquire, robust=robust)
            sc_ = score_track(
                trk_, c_["r"],
                m_per_px=(circle_m / 2.0) / c_["r"],
                rom_lo=rom_lo, rom_hi=rom_hi)
            sc_["blob"] = s_.get("blob", 0.0)
            redone.append((sc_, c_, trk_))
        redone.sort(key=lambda t: -t[0]["score"])
        scored = prefer_sticker_ring(redone) + list(scored[3:])

    # Seven filled slots, not five or six. Every genuine 8-sticker clip tracks
    # at a median of EIGHT once multi-start is used, while a three-sticker plate
    # can accumulate six spurious ones from clutter near the lattice.
    good = scored and scored[0][0]["slots"] >= 7 and scored[0][0]["coverage"] >= 0.6
    if not good:
        cands2 = candidates(dets, shape, lattice=False, min_slots=3)
        if cands2:
            sc2 = choose(
                dets, shape, cands2,
                lambda d, sh, c: _follow(d, sh, c, lattice=False,
                                                   n_starts=2),
                verbose=verbose, circle_m=circle_m,
                rom_lo=rom_lo, rom_hi=rom_hi)
            if sc2:
                scored, layout = sc2, "3-sticker"
    if not scored:
        raise ValueError(f"{video.name}: no candidate constellation tracked")

    s, c, trk = scored[0]
    if layout != "8-sticker":
        trk = _follow(dets, shape, c, lattice=False, n_starts=6)
        s = score_track(
            trk, c["r"], m_per_px=(circle_m / 2.0) / c["r"],
            rom_lo=rom_lo, rom_hi=rom_hi)

    summ = summarise(trk, fps, c["r"], circle_m)
    return {"name": video.stem, "lift": lift, "trk": trk, "summary": summ,
            "r_px": c["r"], "score": s, "layout": layout, "fps": fps,
            "implausible": summ["travel_m"] < IMPLAUSIBLE_FRAC * rom_lo,
            "runner_up": scored[1][0] if len(scored) > 1 else None}


def bar_path(video, cache_dir=None, check: bool = True) -> dict:
    """Tracked bar path, in `markers.bar_path`'s key set.

    Key-compatible by design, so `metrics.vs_truth`, `capture.landings`,
    `capture.sync` and `metrics.bench_sync` consume it without knowing which
    tracker produced it — the same property that let `markers.py` slot in beside
    `capture.py` (C17). `residual_px` is present, which is what makes
    `metrics._video_quality` report this as a marker-style referee and score its
    top-of-travel fit in centimetres rather than as an NCC.

    `x` is fore-aft in metres about the clip median; `height` is metres above
    the lowest tracked point, both on the clip's own clock in `t`.
    """
    res = track_clip(video, cache_dir=cache_dir)
    sm, trk = res["summary"], res["trk"]
    n = len(sm["t"])
    rms = np.array([t["rms"] if t is not None else np.nan for t in trk])
    slots = np.array([len(t["slots"]) if t is not None else 0 for t in trk],
                     dtype=float)
    centre = np.column_stack([sm["y_px"], sm["x_px"]])

    path = {
        # Which referee made this. `metrics._video_quality` labels its output
        # from it, and `tracked.write` records the same field in the CSV header
        # so a cached path stays self-describing.
        "tracker": "vtrack",
        "t": sm["t"],
        "x": sm["fore_aft_m"],
        "height": sm["height_m"],
        "fps": res["fps"],
        "m_per_px": sm["m_per_px"],
        # One scale for the whole clip. Unlike `markers.bar_path` this module
        # does NOT apply a per-frame perspective scale: its centre comes from a
        # lattice fit at a held radius on most frames, so a per-frame apparent
        # size is not independently measured. `markers.py` measured that
        # correction at 0.6-1.4 cm on deadlift and 0.1-0.4 on bench.
        "m_per_px_t": np.full(n, sm["m_per_px"]),
        "residual_px": rms,
        "circumradius_px": np.full(n, res["r_px"]),
        "centre_px": centre,
        "n_markers": slots,
        "score": slots,
        "travel_m": sm["travel_m"],
        "coverage": sm["coverage"],
        "plate_radius_px": res["r_px"],
        "sticker_radius_m": 0.5 * STICKER_CIRCLE_M[res["lift"]],
        "layout": res["layout"],
        "implausible": bool(res["implausible"]),
    }
    if check:
        validate(path, video)
    return path


def validate(path: dict, video) -> None:
    """Warn where this referee is not fit to referee. Never silent, never fatal.

    Two checks, and the first is the one that matters. `implausible` catches the
    failure that motivated this module — a track that is rigid, well covered and
    not the bar. Coverage and residual CANNOT catch it, which is exactly why
    six squat clips went unnoticed for days; whole-clip travel against the
    lift's own ROM can.
    """
    import warnings

    name = Path(video).name
    if path["implausible"]:
        warnings.warn(
            f"{name}: whole-clip travel {path['travel_m'] * 100:.1f} cm is far "
            f"below this lift's range of motion. The track is rigid and well "
            f"covered but it is not the bar — LOOK at the review figure before "
            f"using it.", stacklevel=2)
    if path["coverage"] < 0.9:
        warnings.warn(
            f"{name}: only {path['coverage'] * 100:.1f}% of frames tracked.",
            stacklevel=2)
