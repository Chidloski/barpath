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
Evidence: `FINDINGS.md`, and this package's own docstrings — the derivations
live beside the code they justify. The rebuild's dated report and its frozen
copy of this tracker were deleted on 2026-08-23; `git show fa7588d` has them.

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
from .condition import condition as _condition

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

# And ABOVE this multiple of the lift's own UPPER ROM bound, likewise. **This
# half was missing until 2026-08-17 (H16) and the omission was not academic.**
# `IMPLAUSIBLE_FRAC` was written for squat clips reading 14 cm on a 65 cm lift,
# so it only ever looked DOWNWARD, and two 2026-08-13 bench clips reported 94.1
# and 72.2 cm of whole-clip travel — for a bench press — at 89.8% and 100%
# coverage with 1.23 and 1.72 px residuals, flagged by nothing.
#
# **What forced it is worth recording, because it is a trap rather than an
# oversight.** One of the two was caught, for a while, by its rep count
# disagreeing with its filename (5 found, 6 in the name). Then the owner
# corrected the filename — the IMU log said 5 and was right — and the count
# matched, and the last automated objection to a track claiming 94 cm on a
# bench press disappeared. A correct relabelling silently removed a defect
# detector. Nothing was wrong with the relabelling; the gate was leaning on a
# coincidence.
#
# Measured on all 29 clips, as travel over `ROM[lift]`'s ceiling — this module's
# own tight band, which is what the flag is computed against here:
#
#     GOOD (27 clips)   bench 0.883-0.947   squat 1.032-1.195   deadlift 0.879-0.978
#     BROKEN (2 clips)  2.328 and 3.034
#
# The gap is [1.195, 2.328] and **1.5 sits 26% above the worst good clip and 55%
# below the best broken one**. Whole-clip travel legitimately EXCEEDS per-rep ROM
# — every clip contains an un-rack or a walkout — which is why the ceiling is a
# multiple above 1.0 rather than the band's own top. Scored against
# `capture.VERTICAL_ROM_M` instead, which `tracked.review` uses, the same 1.5
# separates 0.782-1.069 from 2.062-2.687; the constant is comfortable under
# either band, which is the reason to believe it is not tuned to one.
IMPLAUSIBLE_MULT = 1.5


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
            "implausible": bool(summ["travel_m"] < IMPLAUSIBLE_FRAC * rom_lo
                                or summ["travel_m"] > IMPLAUSIBLE_MULT * rom_hi),
            "runner_up": scored[1][0] if len(scored) > 1 else None}


def bar_path(video, cache_dir=None, check: bool = True,
             condition: bool = True) -> dict:
    """Tracked bar path, in `markers.bar_path`'s key set.

    Key-compatible by design, so `metrics.vs_truth`, `capture.landings`,
    `capture.sync` and `metrics.bench_sync` consume it without knowing which
    tracker produced it — the same property that let `markers.py` slot in beside
    `capture.py` (C17). `residual_px` is present, which is what makes
    `metrics._video_quality` report this as a marker-style referee and score its
    top-of-travel fit in centimetres rather than as an NCC.

    `x` is fore-aft in metres about the clip median; `height` is metres above
    the lowest tracked point, both on the clip's own clock in `t`.

    **`condition=True` is the default as of 2026-08-22 (H30)** — impossible
    frames are rejected and the path is lightly smoothed, per `condition.py`,
    which also adds `x_raw`, `height_raw`, `rejected` and `condemned`. Pass
    `condition=False` to reproduce a figure measured before that date. It
    changes `travel_m` by a median of -0.002 cm and at most 0.27 cm over the 33
    captures it does not condemn, so no vertical number moves; what it moves is
    the four captures that contained motion no barbell performs.
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
    if condition:
        path = _condition(path, name=Path(video).name)
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


# ----------------------------------------------- the referee's own fit --
# `TOP_FRAC`, `MAX_TOP_RESIDUAL_CM` and `top_of_travel_residual` MOVED HERE FROM
# `markers.py` ON 2026-08-19 (H21), UNCHANGED. `markers.py` was deleted when
# `vtrack` became the only tracker that can run, and this was its one live
# dependency: `metrics._video_quality` calls it on every scored capture,
# whichever tracker produced the path. It is geometry over `height`,
# `residual_px` and `m_per_px_t` and never touched a constellation, so it reads
# a `vtrack` path exactly as it read a `markers` one — which is why the move is
# numerically inert and was gated as such.
#
# `TOP_FRAC` lived in `capture.py` so that BOTH trackers meant the same span of
# travel by "at lockout" and their top-of-travel figures stayed comparable. With
# one referee left there is nothing to keep comparable, so it belongs to the
# referee that measures it. The value is unchanged.
#
# `validate` above does NOT gate on `MAX_TOP_RESIDUAL_CM`, where `markers.validate`
# did. That is deliberately left alone rather than carried over: adding a warning
# would be a behaviour change, and H21 was a consolidation gated on moving no
# number. `metrics.vs_truth` still REPORTS the figure as `video_top_residual_cm`.
TOP_FRAC = 0.15       # "at lockout" = the top this fraction of vertical travel

MAX_TOP_RESIDUAL_CM = 0.5   # the referee's own fit error, where it is worst


def top_of_travel_residual(path: dict, frac: float = TOP_FRAC) -> dict:
    """How well the rigid model fits WHERE THE FIT IS WORST, not on average.

    The exact counterpart of `capture.top_of_travel_score` — the plate template's
    version, deleted with that tracker on 2026-08-14 — and it exists for the
    same reason that one did. This project has now been bitten five times by an
    aggregate that passes while the thing fails exactly where it matters —
    milestones 1-6, C8's peak-height threshold, C10's clip-composition artefact,
    C12's whole-clip NCC median, and this. **A referee needs checking where it
    is used.**

    `frac` was `capture.TOP_FRAC` until H21 (2026-08-19), so that "at lockout"
    meant the same span of travel for both trackers and the two remained
    comparable. There is one tracker now and the constant moved here with the
    function; the value did not change.

    What it found, measured 2026-08-02 over all five `data_v2` captures THEN
    HELD, through `markers.py`, which was the referee at the time and has since
    been deleted (H21). The rows are history and cannot be re-derived — three of
    the five captures no longer exist and the tracker that produced them is
    gone — but the SHAPE is what the function is for. The whole-clip median is
    the quantity the old gate tested:

        capture                whole    top 15%    ratio
        deadlift_150x5         0.519      0.775      1.5
        deadlift_160x5         0.611      0.724      1.2
        deadlift_190x1         0.150      1.595     10.6
        bench_85x6             1.096      1.311      1.2
        bench_110x1            1.066      1.075      1.0

    all in px, and the third row is the point. **`deadlift_190x1` has the
    lowest whole-clip residual of the five and the highest at lockout** — the
    old gate ranked it the best-fitting capture we hold while it was the worst
    where the measurement is taken. It passed at 0.150 against a 1.5 px limit
    with a tenfold margin, and its lockout sits at 1.595, over the line.

    **But read the pixels in metres before alarming anyone**, which is why this
    reports both. Converted through each frame's own scale the same column is
    0.177 / 0.168 / **0.333** / 0.279 / 0.226 cm. The worst lockout fit in the
    set is a third of the 1 cm spec, so the stratification is real and the
    tracker is still comfortably inside tolerance — which is exactly the
    distinction C15 drew against the template, and it survives being measured
    properly. The template does not degrade, it *fails*: 100% of its top-10 cm
    frames fall below `capture.GOOD_SCORE`.

    Why the residual degrades with height at all: the marker is further from the
    camera at lockout and subtends fewer pixels, so its centroid is noisier.
    Correlation with height is +0.24 to +0.93 across the five.

    Conservative by about sqrt(3). The residual is the misfit of three markers
    to a rigid triangle; the CENTROID those markers determine is better
    conditioned than any one of them. So this over-states the position error,
    and is the right way round for a gate.

    **That last paragraph was written for `markers.py`'s three-marker similarity
    fit and does not describe this module's `residual_px` (H21, 2026-08-19).**
    Here the residual is the rms of the eight-slot lattice fit at a held radius
    (`track.summarise`), so the averaging is over up to eight points rather than
    three and the conditioning argument is different in size, not in direction:
    a centre determined by N points is still better conditioned than any one of
    them, so this still over-states the position error. The sqrt(3) is NOT a
    number to quote for a `vtrack` path; nobody has measured the equivalent
    factor for the lattice fit. It is kept because it is the derivation of a
    threshold — `MAX_TOP_RESIDUAL_CM` — that is still in force.
    """
    h, r = path["height"], path["residual_px"]
    mpp = path["m_per_px_t"]
    ok = np.isfinite(h) & np.isfinite(r)
    if not ok.any():
        return {"median_px": float("nan"), "median_cm": float("nan"),
                "whole_px": float("nan"), "whole_cm": float("nan"),
                "ratio": float("nan"), "n": 0}

    top = np.nanmax(h[ok])
    span = top - np.nanmin(h[ok])
    near = ok & (h > top - frac * span)
    cm = r * mpp * 100.0

    whole_px = float(np.nanmedian(r[ok]))
    med_px = float(np.nanmedian(r[near])) if near.any() else float("nan")
    return {
        "median_px": med_px,
        "median_cm": float(np.nanmedian(cm[near])) if near.any() else float("nan"),
        "whole_px": whole_px,
        "whole_cm": float(np.nanmedian(cm[ok])),
        "ratio": med_px / whole_px if whole_px > 0 else float("nan"),
        "n": int(near.sum()),
    }

