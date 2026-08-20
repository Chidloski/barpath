"""Capture metadata, plate geometry, rep bounds, and the video-to-IMU clock.

**What this is, and what it is NOT.** This was `truth.py`, whose centrepiece was
a matched-filter tracker that followed the plate as a dark disc — the referee
for `data/video/`. **That corpus and that tracker were both deleted on
2026-08-14 on the owner's instruction**, so what survives here is everything the
tracker was sitting on top of and which the rest of the project still needs:

  * which lift a capture is of, and how big the plate in it is;
  * what a plausible rep looks like vertically (`VERTICAL_ROM_M`) and fore-aft
    (`FORE_AFT_ACCEL_MAX`) — the only external bounds bench and squat have;
  * ~~decoding a clip to greyscale frames~~ — **deleted 2026-08-20 (H28)**.
    `probe` and `frames` had used `subprocess` and `json` without importing
    either, so both raised `NameError` if called, and nothing had called them
    since the template tracker went. `src/vtrack/detect.py` decodes now. The
    NCC matcher `ncc_map` went with them for the same reason;
  * `find_plate`, a single-frame rim detector, which `markers.py` used as an
    independent cross-check on its own scale — NOT because anything tracks with
    it. **`markers.py` was deleted on 2026-08-19 (H21), so `find_plate` now has
    NO CALLER**, and neither do `sticker_plate_diameter`,
    `STICKER_PLATE_DIAMETER_M` and `MIN_TRAVEL_M` (that last one already had
    none). **`fore_aft_flags` has none either** — an audit on 2026-08-20 (H28)
    found it uncalled from anywhere, including its own tests, so nothing checks
    the `FORE_AFT_ACCEL_MAX` bound that the block above spends thirty lines
    deriving. Unlike the decode helpers it is sound code and it is kept, but a
    bound nothing evaluates is not a gate. They are recorded as orphaned rather than deleted in the same pass:
    removing them is a separate judgement about what this module is for, and
    H21 was scoped to retiring a REFEREE. Nothing can score with any of them —
    a single-frame rim detector is not a tracker — so leaving them costs
    correctness nothing;
  * **`landings`, `sync` and `to_imu_time` — the deadlift clock match**, which
    is the best-validated sync in the project (video landings against IMU floor
    impacts, offset AND slope, 9-19 ms residual) and is used by every deadlift
    comparison `metrics.py` makes.

**Nothing here tracks a bar.** `src/vtrack/` is the referee for `data_v2/` and,
since 2026-08-19, the only tracker in the repo. The template tracker's
own record — `bar_path`, `SEEDS`, `GOOD_SCORE`, `top_of_travel_score`, and C12's
finding that it lost the plate at lockout on 166/166 frames — is in the git
history and in `TASKS.md`; it is not reproducible now, because the footage it
ran on is gone.

**Findings measured against the deleted v1 corpus are history, not live gates.**
`CLAUDE.md` marks them. Do not treat a number in this file's constants as
re-derivable: `VERTICAL_ROM_M` and `FORE_AFT_ACCEL_MAX` were measured partly on
captures that no longer exist.
"""
from __future__ import annotations

from pathlib import Path

import numpy as np
from scipy.signal import fftconvolve

# Measured 2026-07-30, with a tape, on the actual plates. Replaces a single
# assumed 0.450 that was right only for squat.
#
# The tracker locks onto the largest circle in shot, so what matters per lift is
# the BIGGEST plate loaded, not the nominal one:
#   bench    black notched, 425 mm. Plates under 20 kg are smaller still, so a
#            notched 20 is the outline at any working weight.
#   squat    blue calibrated, 450 mm, with smaller plates outside it.
#   deadlift one black bumper, 445 mm. Above 60 kg black notched plates load
#            outside it, and every notched plate is smaller, so the bumper stays
#            the outline.
PLATE_DIAMETER_M = {"bench": 0.425, "squat": 0.450, "deadlift": 0.445}

# The 2026-08-03 session was filmed on BLUE CALIBRATED discs — 450 mm, the same
# as the squat entry above and 25 mm wider than the black notched plates the
# bench entry was measured on. Keying the table by lift alone was right while
# every capture came from one plate set and became wrong the moment a session
# used another, which is the shape of error this file exists to catch.
#
# It is worth 5.9% of every bench distance in that session, and the sign is the
# one the data showed: marker travel read 9-13% LOW against the IMU's per-rep
# ROM before this, and the clip contains the un-rack, so it should if anything
# read high. Measured with a tape by the owner: blue calibrated 450 mm, black
# bumper 445, black notched 425.
CALIBRATED_SESSIONS = ("20260803",)
CALIBRATED_DIAMETER_M = 0.450

# The plate the STICKERS are on, which is not always the largest plate in shot,
# and on a deadlift is not (C27, 2026-08-04). `plate_diameter` above answers
# "what is the outline the template tracker sees", and for a deadlift that is
# the 445 mm bumper because it is the widest thing on the bar. `markers.py`
# asks a different question — how big is the disc the stickers were stuck to —
# and on the 2026-08-04 session the answer is the 425 mm black notched plate
# loaded OUTBOARD of the bumper. Owner, 2026-08-04: "one bumper plate of
# diameter 44.5 and then black notched plates after with a diameter of 42.5".
#
# Using 445 there overstates every marker distance in the session by 4.7%. Note
# the bar still starts at 22.25 cm off the ground — that is set by the bumper,
# which is the plate carrying the load, and is unaffected by which plate the
# stickers went on.
#
# **ASKED AND ANSWERED (owner, 2026-08-17).** C32's question below was "which
# physical plate carries the stickers on each bar", and the answer is that each
# lift uses one plate set and always has: **bench loads ONLY black notched
# (425), squat ONLY blue calibrated (450), and a deadlift is black notched
# loaded around black bumpers**, so the stickered plate is the notched 425 on
# both bench and deadlift and the blue 450 on squat. Nothing was moved between
# bars, so the 5.9% squat risk this comment raised did NOT happen and the
# fall-through values were right — by luck rather than by evidence, which is
# exactly the distinction the comment was drawing. They are now a decision.
#
# Two things that answer does NOT settle, recorded so they are not assumed:
#
#   * **It contradicts `CALIBRATED_SESSIONS` above**, which records the
#     2026-08-03 bench session as filmed on blue calibrated discs. Those
#     captures were deleted with v1, so this is a conflict between the owner's
#     general statement and one session's history rather than a live defect.
#     Left as history; do not reconcile by deleting either.
#   * **A cross-check that PASSED, recorded because it is the only independent
#     check these diameters have ever had.** The owner first said the notched
#     plate clears the floor by 2 cm, which would put the bumper at 465 mm and
#     contradict the 445 above — and then corrected the arithmetic to 1 cm,
#     unprompted. 1 cm is exactly (445 - 425) / 2, so the two tape measurements
#     agree with a third observation taken a fortnight later. The bar's start
#     height of 22.25 cm is unaffected and remains the bumper's radius.
#
# The scale question this table fed is now moot for `vtrack`, which no longer
# derives the sticker circle from a plate diameter at all: the circle is
# measured (`vtrack.STICKER_CIRCLE_M`, plate less 2 cm). This table still keys
# `markers.py` and stays as the record.
STICKER_PLATE_DIAMETER_M = {"20260804": 0.425}


def sticker_plate_diameter(name: str | Path) -> float:
    """Diameter in metres of the plate the retroreflective stickers are on.

    Defaults to `plate_diameter`, which is what every capture before
    2026-08-04 implicitly assumed — `STICKER_RATIO` was calibrated through that
    same call, so the two errors cancel there and must keep cancelling. Only a
    session known to have stickered something other than the widest plate
    appears in the table.
    """
    stem = Path(name).stem
    for tag, diam in STICKER_PLATE_DIAMETER_M.items():
        if tag in stem:
            return diam
    return plate_diameter(name)

# Per-rep vertical range of motion, (floor, ceiling) in metres.
#
# The ceilings are measured for this lifter: bench 0.35 (0.32 typical), squat
# 0.76, deadlift 0.61, each from the start position to the far end of the range.
# The floors are NOT measured. They are set at ~60-65% of the ceiling as a
# sanity bound, because an upper bound alone cannot see a truncated rep window —
# `squat_160x1` reconstructs 18.0 cm for a 160 kg squat and passes any ceiling.
# Treat a floor violation as "this window is not a whole rep", not as a claim
# about the lifter.
#
# What the ceilings caught, and it was not the pipeline. Per-rep video ROM on
# the three deadlifts — same lifter, same lift, 155/155/180 kg:
#
#     deadlift_155x6_1   59.8 cm   plate found at 64 px
#     deadlift_155x6_2   67.5 cm   plate found at 64 px   over the 61 cm bound
#     deadlift_180x3     48.1 cm   plate found at 56 px   implausibly low
#
# A 19 cm spread on a range of motion fixed by the lifter's own limbs. Three
# explanations were tested and none survives:
#
#   Plate diameter. Captures 1 and 2 found the SAME radius, so no diameter
#   explains a 13% gap between them; 450 -> 445 mm moves everything ~1%.
#   Radius quantisation. `find_plate` searches a 4 px grid. Re-run at 1 px the
#   radii are 64/65/54 and the ROMs 61.2/69.2/50.8 — under 2% of movement.
#   Tracker drift. The floor baseline holds to 0.4 cm across every clip and the
#   per-capture lockouts are internally consistent (61/60/60, 70/69/64,
#   49/49/48). `deadlift_180x3` has the BEST median NCC, 0.94, and the worst ROM.
#
# What is left is the geometry: the scale is calibrated on a plate sitting on
# the floor and then applied to travel reaching the top of frame. That is the
# assumption the module docstring used to state outright. It does not hold
# between captures, and re-filming with a known vertical reference in shot — a
# metre rule against the rack — is the fix. Until then every A3 number carries
# an unmeasured per-capture scale error, `vs_truth` flags it, and P2's 5-15 cm
# SPREAD is partly this rather than the IMU.
VERTICAL_ROM_M = {"bench": (0.20, 0.35), "squat": (0.45, 0.76), "deadlift": (0.40, 0.61)}

# The HORIZONTAL analogue, and the first external bound the fore-aft channel has
# ever had (E1, 2026-08-07). Read `VERTICAL_ROM_M`'s block above first: this is
# the same construction, with the same standing and the same limits.
#
# What it bounds. D1's `oracle.parabola_fit` fits `c * tau(tau - T)/2` to one
# rep's along-axis path after step 7's endpoint line has been removed, so `c` is
# "what CONSTANT fore-aft acceleration would draw this rep", in m/s^2. Fitted to
# the VIDEO's own path — closed exactly as step 7 closes the reconstruction, so
# the two are the same quantity — the real bar gives, PER REP:
#
#     lift       n    min      median   p90      MAX      bound = MAX x 1.5
#     bench     53   0.0100    0.0354   0.0677   0.0983   0.1475
#     deadlift  30   0.0003    0.0073   0.0151   0.0268   0.0402
#
# **A deadlift bar produces about a fifth of the constant fore-aft acceleration
# a bench bar does** — median 0.0073 against 0.0354. That is the J-curve, and it
# is the first time this project has put a number on how much fore-aft the bar
# is entitled to.
#
# *Per REP the two lifts OVERLAP* (bench reaches down to 0.0100, deadlift up to
# 0.0268) even though per CAPTURE they do not — bench's smallest capture median
# is 2.1x deadlift's largest. Everything below is stated per rep, because that is
# how `fore_aft_flags` applies it; an earlier draft of this block set the bound
# from per-capture medians and then checked every rep against it, which is the
# aggregate-versus-where-it-is-used mistake this project keeps making, and the
# gate in tests/test_video_truth.py caught it on four captures.
#
# What the reconstruction does against it, per rep:
#
#     lift        min      median   MAX      flagged
#     bench      0.0023    0.0341   0.0802    0 of 53 reps,  0 of 13 captures
#     deadlift   0.0052    0.0527   0.1602   21 of 30 reps,  6 of  6 captures
#
# **No false positives on the lift where the horizontal reconstruction
# demonstrably works, and it fires on 70% of the reps on the lift where it
# demonstrably does not.** Bench clears the bound with 1.8x of margin. It also
# separates the lifts WITHOUT A SYNC — `c` is a per-rep shape coefficient, not a
# point-by-point comparison, so a whole-rep timing error cannot move it. That
# matters because CLAUDE.md warns that `vs_truth`'s horizontal rms is nearly
# blind to gross misalignment.
#
# FIVE LIMITS. The first four are the ones `VERTICAL_ROM_M` carries.
#
# 1. It is a BOUND, not a measurement. A rep inside it can still be wrong — the
#    coefficient can be right while the shape and timing are not, which is
#    exactly what E1 measured happening on deadlift (rep identification at
#    chance). Passing says only "this much fore-aft acceleration is physically
#    possible for this lift".
# 2. One lifter, one gym, 6 deadlift and 13 bench captures. `squat` has NO entry
#    rather than a guessed one, because no squat capture in this project has ever
#    been refereed. A missing key raises; see `fore_aft_flags`.
# 3. It inherits the referee. These pool `truth.py`'s template on `data/video`
#    and `markers.py`'s conic on `data_v2`, and those two disagree by ~20% on ROM
#    (C24) with no adjudication. Pooling is deliberate, so the spread includes
#    the disagreement rather than hiding it.
# 4. The ceiling is the observed per-rep maximum plus 50%. Tighten it only when
#    more captures exist, and never to make a result appear.
# 5. NEW, and specific to this one: it does not catch 9 of 30 deadlift reps. The
#    bound is set by `deadlift_160x6_1`'s worst video rep at 0.0268, which is
#    2.8x that capture's own median — so one unusually mobile real rep sets the
#    ceiling for the whole lift. More deadlift footage would probably lower it.
FORE_AFT_ACCEL_MAX = {"bench": 0.1475, "deadlift": 0.0402}

# Hand-placed seeds, one per bench capture: (frame, centre y, centre x, radius).
#
# Coordinates are in the DECODED frame at the default `scale=0.5`, so they are
# half what you would read off the original video. Read off by eye on 2026-07-31
# from a frame with the bar out of the rack, by drawing the circle back over the
# frame and adjusting until it sat on the plate rim. There is no cleverness here
# and none is claimed: four automatic seeders were tried first and all four
# preferred the bench-and-lifter silhouette (see the module docstring).
#
# `radius` is doing the load-bearing work, because it is the pixels-to-metres
# scale. Its uncertainty is about +/-2 px on ~48, i.e. ~4% on every bench
# distance reported anywhere downstream, and NOTHING checks it except
# `VERTICAL_ROM_M`. Treat a bench number as carrying that 4% on top of whatever
# else is wrong with it.
#
# The one piece of internal evidence that the radii are not arbitrary: within a
# session the camera and the plate do not change, and the readings agree.
# 2026-07-27 gives 48/48/47/48 px; 2026-07-30 gives 51/51/51. Between the two
# sessions they differ because the phone was closer on the second day, which is
# also visible in the frames.
#
# A capture that is not in this table still RAISES rather than being seeded by
# guesswork — that is the whole point of the table being explicit.
def lift_of(name: str | Path) -> str:
    """The lift a capture or video is of, from the first token of its name.

    Raises on anything else rather than defaulting. A silent default is exactly
    how a 450 mm squat plate went on refereeing bench footage.
    """
    lift = Path(name).name.split("_")[0]
    if lift not in PLATE_DIAMETER_M:
        raise ValueError(
            f"{Path(name).name!r}: cannot tell which lift this is. The first "
            f"name token must be one of {sorted(PLATE_DIAMETER_M)}."
        )
    return lift


def plate_diameter(name: str | Path) -> float:
    """Diameter in metres of the largest plate in shot.

    By lift, because that is what decides which plate is the outline — except
    where a session used a different plate set, which the 2026-08-03 one did.
    See `CALIBRATED_SESSIONS`. The session tag is read from the filename rather
    than the directory so that moving a clip cannot silently change its scale.
    """
    stem = Path(name).stem
    if any(tag in stem for tag in CALIBRATED_SESSIONS):
        return CALIBRATED_DIAMETER_M
    return PLATE_DIAMETER_M[lift_of(name)]


def rom_flags(lift: str, roms_m) -> list[str]:
    """One message per rep whose vertical ROM leaves `VERTICAL_ROM_M[lift]`.

    Deliberately returns messages rather than raising, and is used on BOTH the
    reconstruction and the video, so the two are judged against one table. The
    referee has no standing to be exempt from the check it applies: run against
    the deadlift videos this flags two of the three captures, and the
    reconstruction it was refereeing flags none.
    """
    lo, hi = VERTICAL_ROM_M[lift]
    out = []
    for i, r in enumerate(roms_m, start=1):
        if r > hi:
            out.append(f"rep {i}: vertical ROM {r*100:.1f} cm exceeds the "
                       f"{hi*100:.0f} cm {lift} bound")
        elif r < lo:
            out.append(f"rep {i}: vertical ROM {r*100:.1f} cm is below the "
                       f"{lo*100:.0f} cm sanity floor for {lift} — probably not "
                       f"a whole rep")
    return out


def fore_aft_flags(lift: str, coeffs) -> list[str]:
    """One message per rep whose fore-aft parabola coefficient is unphysical. E1.

    `coeffs` are `oracle.parabola_fit(...)["c"]` per rep, in m/s^2, from the
    along-axis path AFTER step 7. See `FORE_AFT_ACCEL_MAX` for where the bound
    comes from and for the four limits it carries.

    Deliberately mirrors `rom_flags`, including the two properties that make
    that function worth having. It returns messages rather than raising, and it
    is meant to be run on BOTH the reconstruction and the video — the referee
    has no standing to be exempt from the check it applies. Run against the
    videos it flags nothing, which is what a bound derived from them should do
    and is therefore a consistency check rather than evidence.

    One-sided on purpose. There is no floor: a rep with NO fore-aft acceleration
    is physically fine (it is what a perfect deadlift looks like) and flagging it
    would be flagging the null. Compare `rom_flags`, which needs a floor because
    a too-small vertical ROM means a window that missed part of a rep. Nothing
    equivalent is true here.

    `squat` raises rather than defaulting, and that is the point of the table
    being explicit — no squat capture in this project has ever been refereed, so
    there is no honest bound to apply and a guessed one would be worse than a
    refusal. That is `lift_of`'s rule applied one level up.
    """
    if lift not in FORE_AFT_ACCEL_MAX:
        raise ValueError(
            f"no fore-aft acceleration bound for {lift!r}. Only "
            f"{sorted(FORE_AFT_ACCEL_MAX)} have been measured against video; a "
            f"guessed bound would invent the ground truth this module supplies. "
            f"See FORE_AFT_ACCEL_MAX.")
    hi = FORE_AFT_ACCEL_MAX[lift]
    return [f"rep {i}: fore-aft acceleration {abs(c):.4f} m/s^2 exceeds the "
            f"{hi:.3f} {lift} bound — {abs(c)/hi:.1f}x more fore-aft than the "
            f"bar can produce on this lift"
            for i, c in enumerate(coeffs, start=1) if abs(c) > hi]


# THE DECODE AND TEMPLATE-MATCHING BLOCK WAS DELETED HERE ON 2026-08-20 (H28).
# `probe`, `frames`, `ncc_map` and `_parabolic` — the ffmpeg wrappers and the
# NCC matcher that fed `truth.py`'s plate template. Nothing had called any of
# them since that tracker went on 2026-08-14, and TWO OF THEM COULD NOT HAVE
# RUN: `probe` and `frames` use `subprocess` and `json`, and neither has ever
# been imported by this module, so either one raises `NameError` on the first
# line of its body. No test caught it because no test reaches them.
#
# `src/vtrack/detect.py` carries its own working `probe`, which is what the
# live referee decodes with, so nothing was lost. Recover them with
# `git show 0e87f28:src/capture.py`.
#
# This is a DELETION where the rest of this module's orphans are a RECORD:
# `find_plate`, `sticker_plate_diameter` and `plate_diameter` are kept because
# they document what a referee measured, and a broken ffmpeg wrapper documents
# nothing. See CLAUDE.md's note on what survived `truth.py`.


def _disc(r: int) -> np.ndarray:
    yy, xx = np.mgrid[-r:r + 1, -r:r + 1]
    k = ((xx * xx + yy * yy) <= r * r).astype(float)
    k -= k.mean()
    return k / np.linalg.norm(k)


def find_plate(frame: np.ndarray, radii=range(40, 110, 4)) -> tuple[int, int, int, float]:
    """Locate the dark plate in one frame. Returns (y, x, radius, score).

    A matched filter against a dark disc. This only works where the plate sits
    against a LIGHT background — on the floor, not at lockout against a dark
    ceiling — so seed it from a frame where the bar is down. The radius it
    returns is what sets the pixels-to-metres scale, so the seed frame is doing
    double duty and is worth choosing well.

    Only centres where the whole disc lies inside the frame are considered, and
    that is a correctness fix rather than tidiness. `fftconvolve(mode="same")`
    zero-pads, so a disc hanging off the edge is scored against blackness and
    scores well for being half outside the picture — which is not a measurement
    of anything. On the three 2026-07-30 squats it won outright: r=108 centred
    12, 16 and 38 px from the left edge of a 180 px wide frame. `track` then
    sliced `cx - half : cx + half + 1` with a negative start, numpy wrapped it,
    the template came back EMPTY, and `ncc_map` died with

        ValueError: operands could not be broadcast together with shapes (0,) (186,105)

    which says nothing about the real fault. Three of the four 2026-07-30 squat
    videos could not be tracked at all because of it. The constraint leaves the
    2026-07-27 squats and all three deadlifts on exactly the seed they had.
    """
    best = (0, 0, 0, -np.inf)
    h, w = frame.shape
    for r in radii:
        if 2 * r + 1 > min(h, w):
            continue
        c = fftconvolve(-(frame - frame.mean()), _disc(r)[::-1, ::-1], mode="same")
        inside = np.full_like(c, -np.inf)
        inside[r:h - r, r:w - r] = c[r:h - r, r:w - r]
        i = int(np.argmax(inside))
        y, x = np.unravel_index(i, inside.shape)
        if inside[y, x] > best[3]:
            best = (int(y), int(x), int(r), float(inside[y, x]))
    return best




MIN_TRAVEL_M = 0.10   # a tracked barbell moves. Less than this means it did not.

# `TOP_FRAC` MOVED TO `vtrack.path` ON 2026-08-19 (H21). It lived here so that
# both trackers meant the same span of travel by "at lockout" and their
# top-of-travel figures stayed comparable; with one referee left it belongs to
# the referee that measures it, and its only consumer moved there with
# `top_of_travel_residual`. The value did not change.


def landings(path: dict, floor_m: float = 0.05, refractory_s: float = 1.5,
             skip_s: float = 10.0) -> np.ndarray:
    """Times the bar comes to rest on the floor, one per rep.

    The refractory period matters: the bar bounces, so a bare threshold
    crossing fires twice per landing and doubles the event count.
    """
    t, h = path["t"], path["height"]
    low = h < floor_m
    out: list[float] = []
    for i in range(1, len(h)):
        if low[i] and not low[i - 1] and t[i] > skip_s:
            if not out or t[i] - out[-1] > refractory_s:
                out.append(float(t[i]))
    return np.array(out)


# A `rack_impact` used to live here: the last moment the tracked bar's 2-D speed
# exceeded a threshold, meant as the video half of a bench re-rack landmark, to
# be paired with the IMU's last transient above 3 g and used as an INDEPENDENT
# check on `metrics.bench_sync`. It was removed on 2026-07-31 when it was tested
# on deadlift, where the true offset is known from landings matched to floor
# impacts. The anchor missed by +615, +660 and +510 ms — a systematic half-second
# bias, in the same direction every time, because the video's "last motion" and
# the IMU's "last transient" are not the same event. A check wrong by 0.6 s
# cannot bound a quantity that matters at 0.1 s. It is recorded here rather than
# silently dropped because on bench it appeared to DISAGREE with the correlation
# by 53-706 ms, which read as evidence against the sync until the deadlift
# control showed the error was the anchor's own. See `metrics.bench_sync` and
# `analysis/29`.


def _smooth(y: np.ndarray, n: int) -> np.ndarray:
    """Odd-length moving average, NaNs interpolated and the ends edge-padded.

    Edge padding rather than `mode="same"`, which zero-pads: the tracked height
    is 0.2-0.6 m, so a zero-padded end reads as the bar falling half a metre in
    one frame — a fake velocity spike at both ends of every clip. That bit the
    since-deleted `rack_impact`, which is why the padding is spelled out here;
    the current caller is `metrics.bench_sync`, whose correlation would key on
    the same artefact.
    """
    y = np.asarray(y, float)
    ok = np.isfinite(y)
    filled = np.interp(np.arange(len(y)), np.flatnonzero(ok), y[ok])
    pad = n // 2
    padded = np.r_[np.full(pad, filled[0]), filled, np.full(pad, filled[-1])]
    return np.convolve(padded, np.ones(n) / n, mode="valid")


def sync(video_events: np.ndarray, imu_events: np.ndarray) -> dict:
    """Fit video_t = slope * imu_t + offset from matched landmark times.

    Fitting a slope as well as an offset is not pedantry — it measures whether
    the two clocks actually agree, and reports it rather than assuming it.
    """
    n = min(len(video_events), len(imu_events))
    if n < 2:
        raise ValueError(f"need >=2 matched events, got {n}")
    v, m = np.asarray(video_events[:n]), np.asarray(imu_events[:n])
    basis = np.vstack([m, np.ones(n)]).T
    slope, offset = np.linalg.lstsq(basis, v, rcond=None)[0]
    residual = v - basis @ [slope, offset]
    return {
        "slope": float(slope),
        "offset": float(offset),
        "drift_pct": float((slope - 1) * 100),
        "residual_s": residual,
        "rms_ms": float(np.sqrt((residual ** 2).mean()) * 1000),
        "n": n,
    }


def to_imu_time(path: dict, fit: dict) -> np.ndarray:
    """Video timestamps expressed on the IMU clock."""
    return (path["t"] - fit["offset"]) / fit["slope"]
