"""Capture metadata, video decoding, and the video-to-IMU clock.

**What this is, and what it is NOT.** This was `truth.py`, whose centrepiece was
a matched-filter tracker that followed the plate as a dark disc — the referee
for `data/video/`. **That corpus and that tracker were both deleted on
2026-08-14 on the owner's instruction**, so what survives here is everything the
tracker was sitting on top of and which the rest of the project still needs:

  * which lift a capture is of, and how big the plate in it is;
  * what a plausible rep looks like vertically (`VERTICAL_ROM_M`) and fore-aft
    (`FORE_AFT_ACCEL_MAX`) — the only external bounds bench and squat have;
  * decoding a clip to greyscale frames;
  * `find_plate`, a single-frame rim detector, kept because `markers.py` uses it
    as an independent cross-check on its own scale — NOT because anything tracks
    with it any more;
  * **`landings`, `sync` and `to_imu_time` — the deadlift clock match**, which
    is the best-validated sync in the project (video landings against IMU floor
    impacts, offset AND slope, 9-19 ms residual) and is used by every deadlift
    comparison `metrics.py` makes.

**Nothing here tracks a bar.** `src/vtrack/` is the referee for `data_v2/`, and
`markers.py` remains reachable as `tracker="markers"`. The template tracker's
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
from scipy.ndimage import uniform_filter
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
# **The 2026-08-06 session has no entry and nobody has decided whether it needs
# one (C32, 2026-08-06).** It carries the same eight-sticker layout as
# 2026-08-04, so the question this table exists to answer — is the stickered
# plate the widest plate — is live again and is currently being answered by
# fall-through rather than by evidence. Bench falls through to 0.425 and squat
# to 0.450; if the owner moved one stickered 425 mm notched plate between the
# two bars and loaded it outboard, as on 2026-08-04, the squat entry is 5.9%
# out on every marker distance. Not resolved here, and not resolvable from the
# footage: it is one question to the owner, or one tape across the sticker
# circle into `markers.bar_path(sticker_diameter_m=)`, which makes the whole
# table irrelevant for that capture.
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


# ----------------------------------------------------------------- decode --
def probe(path: str | Path) -> tuple[int, int, float]:
    """(width, height, fps) without decoding anything."""
    out = subprocess.run(
        ["ffprobe", "-v", "error", "-select_streams", "v:0",
         "-show_entries", "stream=width,height,r_frame_rate",
         "-of", "json", str(path)],
        capture_output=True, text=True, check=True).stdout
    s = json.loads(out)["streams"][0]
    num, den = s["r_frame_rate"].split("/")
    return int(s["width"]), int(s["height"]), float(num) / float(den)


def frames(path: str | Path, scale: float = 0.5) -> tuple[np.ndarray, float, float]:
    """Decode the whole clip to greyscale (N, H, W) floats in [0, 1].

    Half scale is plenty: the plate is ~250 px across at full resolution, and
    halving it makes a 36 s clip decode in under a second while leaving the
    template far larger than the sub-pixel refinement needs.
    """
    w, h, fps = probe(path)
    W, H = int(w * scale) // 2 * 2, int(h * scale) // 2 * 2
    raw = subprocess.run(
        ["ffmpeg", "-loglevel", "error", "-i", str(path),
         "-vf", f"scale={W}:{H}", "-pix_fmt", "gray", "-f", "rawvideo", "-"],
        capture_output=True, check=True).stdout
    n = len(raw) // (W * H)
    stack = np.frombuffer(raw[:n * W * H], dtype=np.uint8).reshape(n, H, W)
    return stack.astype(np.float32) / 255.0, fps, W / w


# --------------------------------------------------------------- matching --
def ncc_map(img: np.ndarray, tpl: np.ndarray) -> np.ndarray:
    """Normalised cross-correlation of `tpl` over `img`, same shape as `img`.

    Two guards, both learned the hard way on this footage:

    Flat regions are masked. The ceiling and the bare floor are nearly uniform,
    so their local variance approaches zero and the ratio explodes — scores
    above 1.0 in empty sky, which is where the tracker went.

    The border is masked. NCC is only defined where the template lies fully
    inside the image, and `uniform_filter` replicates edge pixels, which made
    the local statistics wrong within half a template of the edge and put a
    1.12 peak in the corner.
    """
    t = tpl - tpl.mean()
    tn = np.linalg.norm(t)
    n = t.size

    num = fftconvolve(img, t[::-1, ::-1], mode="same")
    mu = uniform_filter(img, tpl.shape, mode="nearest")
    mu2 = uniform_filter(img * img, tpl.shape, mode="nearest")
    var = np.maximum(mu2 - mu * mu, 0.0)

    textured = np.sqrt(var) > 0.1 * (tn / np.sqrt(n))
    my, mx = tpl.shape[0] // 2, tpl.shape[1] // 2
    inside = np.zeros_like(textured)
    inside[my:img.shape[0] - my, mx:img.shape[1] - mx] = True

    den = np.sqrt(var * n) * tn
    return np.where(textured & inside, num / np.where(den > 0, den, 1.0), 0.0)


def _parabolic(c: np.ndarray, y: int, x: int) -> tuple[float, float]:
    """Sub-pixel offset of a correlation peak by parabolic interpolation."""
    dy = dx = 0.0
    if 0 < y < c.shape[0] - 1:
        a, b, d = c[y - 1, x], c[y, x], c[y + 1, x]
        if a - 2 * b + d != 0:
            dy = 0.5 * (a - d) / (a - 2 * b + d)
    if 0 < x < c.shape[1] - 1:
        a, b, d = c[y, x - 1], c[y, x], c[y, x + 1]
        if a - 2 * b + d != 0:
            dx = 0.5 * (a - d) / (a - 2 * b + d)
    return dy, dx


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

TOP_FRAC = 0.15       # "at lockout" = the top this fraction of vertical travel


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
