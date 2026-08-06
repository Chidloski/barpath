"""
Video ground truth — the referee.

Everything else in this project measures the bar path by integrating an IMU
twice and hoping. This module measures it by looking at it. It is the only
source of external truth for the HORIZONTAL axis, which is the axis the 1 cm
spec is written about and the one with no other check.

Why it works here
-----------------
The captures are filmed from the end of the barbell, so the plate presents as
a circle and the camera axis lies along the bar. That is the fortunate case:

  in-frame horizontal  = fore-aft, the axis the spec is about
  in-frame vertical    = up/down
  depth from camera    = along the bar, which barely moves

The plate supplies the scale: it is a circle of known diameter, so detecting it
calibrates pixels to metres from the footage.

That calibration was believed to be a single constant — "pixels to metres is
one number, not a function of height in frame" is what this docstring used to
say, on the argument that the bar travels in a plane at roughly constant
distance so the pinhole projection collapses to one scale. **That is false, and
the ROM bounds are what caught it.** See `VERTICAL_ROM_M` below for the
measurement. The plate is detected with the bar on the floor, so the scale is
calibrated at the BOTTOM of frame and then applied to travel that reaches the
top of it.

Parallax was expected to be the hard part and is not, for the same reason. It
would matter if the camera were beside the lifter looking across, where fore-aft
becomes depth.

Accuracy
--------
Sync against the IMU on `deadlift_155x6_1`: six floor impacts matched to six
video landings at an offset of 0.759 s with 14 ms standard deviation and 38 ms
total spread, clock drift +0.076%. Two unrelated sensing modalities agreeing to
that tolerance is the strongest validation in the project.

Limits, honestly
----------------
- **Deadlift: automatic. Trustworthy on timing and horizontal, NOT on vertical
  scale.** No seeding, no clicking; median NCC 0.83-0.94, sync to the IMU at
  11-16 ms. But the 49-70 cm of travel this used to quote as a sign of health is
  the symptom: it is one lifter, one lift, three captures, and a real deadlift
  ROM does not vary by 19 cm. See `VERTICAL_ROM_M`.
- **Squat: not truth, and `metrics.vs_truth` refuses it.** The 2026-07-27
  captures track at median NCC ~0.40 because the plate clips the top of frame
  at lockout and the template only partly matches; a warning is raised. The
  four from 2026-07-30 are worse: two raise outright and two report ~12.5 cm of
  travel against a 45-76 cm band. `find_plate`'s in-frame fix (below) stopped
  three of those crashing with a numpy broadcast error, which is worth having
  and is **not** the same as making them trackable — it converted a crash into
  an honest refusal. Needs a wider shot, not code.
- **Bench: works, from a HAND-PLACED seed.** See `SEEDS`. All seven bench
  captures now track at 0.75-0.95 median NCC with 21.8-29.8 cm of whole-clip
  vertical travel, inside `VERTICAL_ROM_M["bench"]`, and the video's own rep
  count matches the label on 7 of 7. Auto-seeding still does not work and is not
  close: the plate is small, sits against a dark ceiling and abuts the
  lifter-and-bench silhouette, which is a larger dark blob, so the dark-disc
  matched filter prefers the clutter. It tracked motionless background at 0.907
  median NCC reporting 0.0 cm of travel before `validate` existed. Four
  automatic seeders were tried on 2026-07-31 and all four preferred the clutter
  — dark disc, circular-edge (radial gradient) matched filter, dark disc
  weighted by temporal motion energy, and a dark-annulus rim filter. This is not
  a tuning problem; the plate is simply not the darkest or the most circular
  thing in a bench frame.
- **The template must fit INSIDE the plate.** `track`'s default `half=48` makes
  a 97x97 px template, which is larger than the inscribed square of a bench
  plate (r~48 px, so `template_half` returns 31 — the inscribed 33 less a 2 px
  margin, then truncated). The corners then hold
  static ceiling, and the tracker part-anchors to the gym instead of the bar:
  on `bench_90x4_1` whole-clip travel reads 16.8 cm at half=48, 22.4 at 40,
  30.9 at 32 and 31.0 at 24. Only the last two are a bench ROM. `SEEDS` sets
  `half` from the seed radius for this reason. Note deadlift is over the same
  line (r=64 gives an inscribed half of 43, against the 48 in use) and has NOT
  been changed, because moving it would move every A3 number pinned in
  `tests/test_real_data.py`; whether it would help is untested and is a lead,
  not a finding.
- Lens distortion is uncorrected. A phone wide lens bows straight lines, and
  the bar crosses much of the frame vertically. It is one candidate for the
  scale error below, and it wants a checkerboard, or at least a plumb line.
- **The vertical scale is wrong by up to ±20%, per capture.** This is now the
  largest known error in the module and it is described at `VERTICAL_ROM_M`.
  The horizontal and the timing are not implicated; the sync still matches the
  IMU to 11-16 ms and `x` moves only a few centimetres, well inside the frame
  region the plate calibrates.
- `PLATE_DIAMETER_M` was assumed at 450 mm for every lift and is now measured
  per lift. It is no longer the dominant scale error, and it never was.

Requires `ffmpeg` on PATH. No new Python dependencies.
"""

from __future__ import annotations

import json
import subprocess
import warnings
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
SEEDS = {
    "bench_90x4_1_20260727": (530, 192, 197, 48),
    "bench_90x4_2_20260727": (562, 176, 200, 48),
    "bench_90x4_3_20260727": (628, 176, 202, 47),
    "bench_92.5x2_20260727": (1216, 178, 198, 48),
    "bench_spoto_90x5_1_20260730": (690, 65, 115, 51),
    "bench_spoto_90x5_2_20260730": (763, 66, 104, 51),
    "bench_spoto_90x5_3_20260730": (685, 55, 112, 51),
}


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


def track(stack: np.ndarray, seed: int, cy: int, cx: int,
          half: int = 48, search: int = 45) -> np.ndarray:
    """Follow a patch through the clip, forwards and backwards from `seed`.

    Returns (N, 3) of (row, col, score), sub-pixel, NaN where not tracked.
    Template matching rather than optical flow: the plate is rigid, high
    contrast and barely rotates, and a fixed template cannot accumulate the
    drift that frame-to-frame differencing does.

    `half` sets the template size and it matters more than it looks. The
    template must lie INSIDE the plate; a plate of radius r inscribes a square
    of half-width r/sqrt(2), and anything larger puts static background in the
    corners so the tracker part-anchors to the gym. Measured on `bench_90x4_1`:
    whole-clip travel 16.8 / 22.4 / 30.9 / 31.0 cm at half = 48 / 40 / 32 / 24,
    against a real bench ROM of ~29 cm. See the module docstring.
    """
    if not (half <= cy < stack.shape[1] - half and half <= cx < stack.shape[2] - half):
        raise ValueError(
            f"template box of half-width {half} centred at (y={cy}, x={cx}) does "
            f"not fit inside the {stack.shape[1]}x{stack.shape[2]} frame. The "
            f"seed is off the picture — find_plate has locked onto an edge "
            f"artefact, or a hand-placed seed_yx is in full-resolution "
            f"coordinates rather than decoded ones."
        )
    tpl = stack[seed, cy - half:cy + half + 1, cx - half:cx + half + 1].copy()
    out = np.full((len(stack), 3), np.nan)
    margin = half + search

    for step in (1, -1):
        y, x = float(cy), float(cx)
        i = seed
        while 0 <= i < len(stack):
            iy, ix = int(round(y)), int(round(x))
            y0, y1 = max(0, iy - margin), min(stack.shape[1], iy + margin)
            x0, x1 = max(0, ix - margin), min(stack.shape[2], ix + margin)
            region = stack[i, y0:y1, x0:x1]
            if min(region.shape) <= tpl.shape[0]:
                break
            c = ncc_map(region, tpl)
            py, px = np.unravel_index(int(np.argmax(c)), c.shape)
            dy, dx = _parabolic(c, py, px)
            y, x = y0 + py + dy, x0 + px + dx
            out[i] = (y, x, c[py, px])
            i += step
    return out


# ------------------------------------------------------------------ path --
MIN_TRAVEL_M = 0.10   # a tracked barbell moves. Less than this means it did not.
GOOD_SCORE = 0.60     # median NCC a clean deadlift track gives; squats sit at 0.40.


def template_half(radius: int, cap: int = 48) -> int:
    """Template half-width for a plate of `radius` px: the inscribed square.

    A square of half-width r/sqrt(2) is the largest that fits inside a circle of
    radius r, so this is the largest template guaranteed to contain no
    background.

    Applied only where it has been measured, which is bench (`SEEDS`). Deadlift
    is over the same line — r=64 px inscribes 43, against the 48 in use — and is
    deliberately left alone: it tracks at 0.83-0.94 median NCC as it is, and
    every A3 number in `tests/test_real_data.py` is pinned against the current
    track, one of them (`VIDEO_ROM_CM`) to within 1 cm. Whether shrinking
    deadlift's template helps is an untested lead, not a finding.
    """
    return int(min(cap, radius / np.sqrt(2) - 2))


def bar_path(video: str | Path, scale: float = 0.5,
             seed_time: float | None = None,
             seed_yx: tuple[int, int] | None = None,
             seed_radius: int | None = None,
             half: int | None = None,
             check: bool = True,
             diameter_m: float | None = None) -> dict:
    """Track the plate and return the bar path in metres.

    Automatic on deadlifts: the plate sits isolated against a bright floor, so
    `find_plate` locks onto it unaided and no seeding is needed.

    NOT automatic on bench, and unattended bench captures are served by the
    hand-placed `SEEDS` table instead — looked up by the video's stem when no
    seed is passed. There the plate is small, against a dark ceiling, and
    adjacent to the lifter-and-bench silhouette, which is a larger dark blob, so
    the matched filter prefers the clutter. It reported a confident 0.907 median
    NCC while tracking a static background patch, and the bar "moved" 0.0 cm. A
    bench clip that is NOT in `SEEDS` still falls through to `find_plate` and so
    still fails loudly; nothing here guesses.

    `seed_yx`/`seed_radius` place the template by hand. The coordinates are in
    the DECODED frame, so at `scale=0.5` they are half the pixel positions you
    would read off the original video.

    `half` is the template half-width, defaulting to `track`'s 48 except for a
    `SEEDS` capture, where it is `template_half(radius)` — the inscribed square
    of the plate. A larger template holds static background in its corners and
    drags the track toward the gym: on `bench_90x4_1` that is the difference
    between 16.8 cm of reported travel and 30.9 cm.

    `check` raises when the tracked bar barely moves. That silent-confident
    failure is the one worth being loud about: a high score means the template
    matched, not that it matched the plate.

    `diameter_m` overrides the plate size. It is otherwise taken from the file
    name via `plate_diameter`, which raises rather than defaulting — so a clip
    named outside the convention fails here instead of being silently scaled by
    somebody else's plate.
    """
    stack, fps, _ = frames(video, scale)

    stem = Path(video).stem
    if seed_time is None and seed_yx is None and stem in SEEDS:
        f, sy, sx, sr = SEEDS[stem]
        seed_time, seed_yx, seed_radius = f / fps, (sy, sx), sr
        if half is None:
            half = template_half(sr)

    if seed_time is not None:
        seed = int(seed_time * fps)
    elif seed_yx is not None:
        seed = len(stack) // 2
    else:
        candidates = range(len(stack) // 4, 3 * len(stack) // 4, max(1, int(fps)))
        seed = max(candidates, key=lambda i: find_plate(stack[i])[3])

    if seed_yx is not None:
        cy, cx = seed_yx
        radius = seed_radius or find_plate(stack[seed])[2]
    else:
        cy, cx, radius, _ = find_plate(stack[seed])

    raw = track(stack, seed, cy, cx, **({} if half is None else {"half": half}))

    m_per_px = (diameter_m if diameter_m is not None
                else plate_diameter(video)) / (2 * radius)
    t = np.arange(len(raw)) / fps
    path = {
        "t": t,
        "x": (raw[:, 1] - np.nanmedian(raw[:, 1])) * m_per_px,   # fore-aft
        "height": -(raw[:, 0] - np.nanmax(raw[:, 0])) * m_per_px,  # image y is down
        "score": raw[:, 2],
        "fps": fps,
        "m_per_px": m_per_px,
        "plate_radius_px": radius,
        "seed_frame": seed,
        "travel_m": float(np.nanmax(raw[:, 0]) - np.nanmin(raw[:, 0])) * m_per_px,
    }
    if check:
        validate(path, video)
    return path


TOP_FRAC = 0.15       # "at lockout" = the top this fraction of vertical travel


def top_of_travel_score(path: dict, frac: float = TOP_FRAC) -> float:
    """Median NCC over the frames where the bar is highest.

    The median over the WHOLE clip cannot see a failure confined to part of
    the movement, and on deadlift there is one. Measured 2026-07-31 on the
    three deadlifts, overall median against this one:

        deadlift_155x6_1    0.830   ->   0.374
        deadlift_155x6_2    0.846   ->   0.397
        deadlift_180x3      0.937   ->   0.432

    Stratified by height it is total: **100%, 100% and 97% of the frames in
    the top 10 cm of travel score below GOOD_SCORE, against 0%, 0% and 0% of
    the frames in the bottom 10 cm.** The tracker is clean on the floor and
    lost at lockout, and `validate`'s median passes at 0.83-0.94 throughout
    because lockout is only 8-15% of a clip.

    Why it matters more than a tracking nicety: the bar at a deadlift lockout
    is held against the thighs and is very nearly still, so the 6-11 cm of
    fore-aft travel the tracker reports there is invented. That inflates
    `metrics.vs_truth`'s `null_h_rms`, which is the yardstick `beats_null`
    divides by — so the pipeline is being flattered by the referee's own
    failure. Restricted to frames scoring above GOOD_SCORE, deadlift
    `beats_null` falls from 0.70/0.35/0.13 to 0.59/0.21/0.07.
    """
    height, score = path["height"], path["score"]
    ok = np.isfinite(height) & np.isfinite(score)
    if not ok.any():
        return float("nan")
    top = np.nanmax(height[ok])
    span = top - np.nanmin(height[ok])
    near = ok & (height > top - frac * span)
    return float(np.nanmedian(score[near])) if near.any() else float("nan")


def validate(path: dict, video: str | Path = "") -> None:
    """Raise if the track cannot be a barbell. Silence here is expensive.

    A high NCC score only says the template kept matching something. On bench
    it matched a motionless piece of background for the whole clip at 0.907
    median and reported 0.0 cm of travel without complaint — which would have
    gone downstream as ground truth.

    Only the no-motion case raises. An out-of-band ROM warns, because the video
    is still the only external check on the horizontal and on the timing, and
    both survive a vertical scale error. Warn, flag, and never quote the number
    unqualified — see `VERTICAL_ROM_M`.

    The median-NCC check below is necessary and NOT sufficient, which is the
    lesson of `top_of_travel_score`: a clip can hold a total tracking failure
    over the top 15% of the movement while the median sits at 0.94. Both are
    checked now, separately, because they fail independently.
    """
    name = Path(video).name or "video"
    if path["travel_m"] < MIN_TRAVEL_M:
        raise ValueError(
            f"{name}: tracked bar moved only {path['travel_m']*100:.1f} cm over "
            f"the whole clip (median NCC {np.nanmedian(path['score']):.3f}). The "
            f"tracker locked onto something static — pass seed_yx to place it on "
            f"the plate by hand."
        )

    score = float(np.nanmedian(path["score"]))
    if score < GOOD_SCORE:
        warnings.warn(
            f"{name}: median NCC {score:.2f}, well below the {GOOD_SCORE:.2f} a "
            f"clean track gives. The template is only partly matching — on the "
            f"squats this is the plate leaving the top of frame at lockout. "
            f"Treat the path as indicative, not as truth.",
            stacklevel=2,
        )

    top = top_of_travel_score(path)
    if np.isfinite(top) and top < GOOD_SCORE:
        warnings.warn(
            f"{name}: NCC over the top {TOP_FRAC:.0%} of travel is {top:.2f}, "
            f"below the {GOOD_SCORE:.2f} a clean track gives, while the "
            f"whole-clip median is {score:.2f}. The tracker is losing the plate "
            f"at LOCKOUT specifically. The bar is nearly still there, so any "
            f"fore-aft motion reported at the top is invented — and it inflates "
            f"null_h_rms, which flatters beats_null. See top_of_travel_score.",
            stacklevel=2,
        )

    # Whole-clip travel stands in for per-rep ROM here, because `validate` has
    # no rep bounds. It reads consistently HIGH — 61.2/70.3/49.0 against per-rep
    # medians of 59.8/67.5/48.1 on the three deadlifts — since it also spans the
    # walk-up and any between-rep excursion. So this warns slightly too eagerly,
    # which is the right way round for a check on the referee. `metrics.vs_truth`
    # applies the same table per rep, and that is the number to act on.
    try:
        lift = lift_of(video)
    except ValueError:
        return
    for flag in rom_flags(lift, [path["travel_m"]]):
        warnings.warn(
            f"{name}: {flag.split(': ', 1)[1]}. The video's vertical scale is "
            f"suspect on this capture, so treat its ROM and any vertical error "
            f"measured against it as flagged. Horizontal and timing are not "
            f"implicated. See truth.VERTICAL_ROM_M.",
            stacklevel=2,
        )


# ------------------------------------------------------------------ sync --
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
