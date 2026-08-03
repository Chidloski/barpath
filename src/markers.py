"""
Video ground truth, mark two — tracking retroreflective stickers.

`truth.py` tracks the plate as a dark disc and matches a template against it.
That referee has two measured defects, and this module exists because both are
defects of the *feature*, not of the code around it:

  - **It is lost at lockout.** 97-100% of the frames in the top 10 cm of a
    deadlift score below `truth.GOOD_SCORE`, against 0% at the floor, and it
    invents ~10 cm of fore-aft motion there. A black plate against a dark gym
    ceiling has no contrast to match on. See `truth.top_of_travel_score`.
  - **Its scale is calibrated once, at the bottom of frame.** Per-rep video ROM
    on three deadlifts came out 59.1 / 66.8 / 47.6 cm for one lifter whose
    anatomy fixes it near 61. See `truth.VERTICAL_ROM_M`.

A sticker fixes the first by construction: it is bright where the plate is dark,
so it is the one feature whose contrast does *not* depend on what is behind the
bar. That much is a clean win and it is measured: 100% of frames tracked on all
five `data_v2` captures, including every lockout.

**Three of them only half fix the second, and the halves are worth separating.**
A rigid constellation measures its own apparent size in every frame, so the
scale is no longer extrapolated from one frame at the bottom of the picture —
that part is genuinely fixed, and measured, and worth 0.6-1.4 cm on deadlift.
It is not worth 20%. The *absolute* scale still rests on a single constant
(`STICKER_RATIO`), so a systematic error in that constant is untouched by any of
this. Do not read "the scale problem is solved" into what follows.

The captures
------------
`data_v2/` holds footage shot from a tripod with markers applied. The layout,
as specified by the owner:

    three stickers on the plate face, as near the circumference as they go,
    spaced approximately every third of the way round;
    one more on the end cap of the bar.

The reflective disc is ~1.5 cm across. At `data_v2`'s 360x640 that is ~5 px,
which is small but is *plenty* for a centroid, and the margin is not close.
Measured over sub-pixel placements of a blurred, noisy 5 px marker, `detect`
locates it to **0.05 px mean and 0.13 px worst** — at these scales 0.12 to
0.30 mm, against a 1 cm spec. Three markers are then averaged, which can only
help. **Resolution is not the limit here**, and that is worth stating plainly
because it is the first thing 360x640 footage invites you to blame; see
`Limits` below for what the real ones are. (A hard-edged synthetic disc scores
0.32 px on the same code, but that is quantisation of the test pattern rather
than of the estimator — optical blur is what makes sub-pixel centroiding work.
See `tests/test_markers.py`.)

Why the rim stickers and the hub sticker are not interchangeable
----------------------------------------------------------------
They are not in the same plane, and it shows up immediately in the data.

The three rim stickers lie on the plate face. The hub sticker lies on the end
cap of the sleeve, which protrudes toward the camera by the better part of a
sleeve's length. The camera is on a tripod above bar height looking down, so the
nearer point is seen at a steeper depression angle and appears *lower* in frame
than the plate centre — by 57 px on `deadlift_150x5`, with the bar on the floor.

That offset is not a constant. Measured over the whole clip it swings from
-111 to +57 px and correlates with the bar's height at **r = 0.949**, which is
what parallax from a protruding point does as the bar rises past the camera.

So the pose fit uses **the three rim stickers only**. The hub is tracked, and
reported, but as a diagnostic of the camera geometry rather than as part of the
path — folding it into a rigid planar fit would drive that parallax straight
into the vertical.

What is measured, and what is assumed
-------------------------------------
Measured per frame: the constellation's position, its rotation, and its apparent
size. Size is the one that earns this module its keep — it is the scale, and it
is now observed at every height instead of extrapolated from one frame.

Assumed, and this is the load-bearing one: **that the three rim stickers are
equally spaced.** Under an affine (weak-perspective) projection the centroid of
three points 120 degrees apart on a circle is exactly the projected circle
centre, and centroids are affine-covariant, so the centroid of the three tracked
stickers is the bar axis. "Approximately every third" is not exactly 120
degrees, and the departure costs a bias.

The bias is bounded and the bound is computed, not hoped for. If the model
centroid sits `e` from the true plate centre in plate coordinates, then as the
plate rotates through an angle the reported centre traces an arc of radius `e`
about the truth. `calibration_report` measures `e` directly, by comparing the
rim centroid against `truth.find_plate`'s independently detected rim circle, and
measures the rotation swing the clip actually contains. A capture with a small
`e`, or with little rotation, is unaffected either way; a capture with both is
the one to distrust. **This is the falsifier for the equal-spacing assumption
and it is reported by `bar_path`, not left to the reader.**

Limits, honestly
----------------
- **No absolute scale of its own, and this is the weakest part of the module.**
  The constellation measures how its size *changes*; something else must say how
  big it is in metres. That is `STICKER_RATIO`, one constant measured on the
  three deadlifts, times `truth.PLATE_DIAMETER_M`. No per-capture rim detection
  is in the path at all — read `STICKER_RATIO` for why, and for the three rim
  detectors that were tried and rejected. On bench the constant is
  **transferred rather than measured**, because that is a different plate
  carrying its own stickers. What this module removes is the *extrapolation* of
  the scale across the frame, not the calibration itself.
- **The fit degrades with height, like the template does — but inside
  tolerance rather than past it, and the distinction is the whole claim of this
  module.** Pooled over the deadlifts the residual runs 0.16 px at the floor to
  0.81 px at lockout; per capture the lockout medians are 0.78, 0.71 and
  **1.60** px, correlation with height +0.24 to +0.93. The marker is smaller and
  dimmer at the top of frame and its centroid is noisier for it. In metres that
  worst case is 0.33 cm against a 1 cm spec, so the tracker never stops being
  usable — where the template's top-of-travel frames are 100% below
  `truth.GOOD_SCORE`, i.e. past the point `truth.py` itself says to stop
  believing it. **Do not restate this as "no height dependence"**; that caption
  was written once, on `analysis/37`, and the scatter falsified it.
  `top_of_travel_residual` measures it and `validate` reports it.
- **The perspective correction assumes the principal point is the frame
  centre.** True enough for a phone, and untested here. `bar_path` returns the
  uncorrected path as well, so the correction's size is always visible rather
  than silently applied — see `x_flat` / `height_flat`.
- **Occlusion is real.** A hand, a thigh or a shin covers a rim sticker for part
  of every deadlift rep. Two visible markers still determine the pose, so the
  tracker rides through it; `n_markers` says how many were actually seen and
  `score` falls when the fit is thin.
- **Rotation about the bar axis is measured; rotation of the bar in any other
  axis is not.** A plate tipping out of its plane changes the constellation's
  apparent shape, and this module reads shape change as scale change. On a
  deadlift the plate stays near its plane; on a lift where it does not, the
  scale would absorb the error silently.
- Lens distortion is uncorrected, exactly as in `truth.py`.

Requires `ffmpeg` on PATH. No new Python dependencies.
"""

from __future__ import annotations

import subprocess
import warnings
from pathlib import Path

import numpy as np
from scipy.ndimage import grey_opening, maximum_filter

from . import truth


# --------------------------------------------------------------- decoding --
def _grey(frame: np.ndarray) -> np.ndarray:
    """A frame as float in [0, 1], whatever it arrived as.

    Every threshold in this module — `MIN_RESPONSE`, `candidates`' `dark_max`,
    `truth.find_plate`'s scores — is written in [0, 1], so the conversion has to
    happen somewhere. It happens here, per frame, rather than once over the
    whole clip, and that is a memory decision rather than a stylistic one: see
    `_frames_u8`. Public functions therefore accept either dtype and scratch
    scripts holding a `truth.frames` float stack keep working unchanged.
    """
    return frame.astype(np.float32) / 255.0 if frame.dtype == np.uint8 else frame


def _frames_u8(path: str | Path, scale: float) -> tuple[np.ndarray, float]:
    """Decode the whole clip to greyscale **uint8** (N, H, W), and the fps.

    `truth.frames` does the same thing and returns float32 in [0, 1]. This
    module cannot use it, and the reason is worth recording because it cost the
    owner a machine.

    This tracker needs full resolution — the stickers are ~5 px at 360x640 and
    halving that throws away the sub-pixel accuracy the module rests on — and it
    holds the whole clip while it tracks. Measured on `deadlift_150x5`, 759
    frames at 640x360: the float32 stack is 699 MB, and `truth.frames` peaks at
    **1936 MB** producing it, 2.8x the array it returns. The raw bytes, the
    `astype` copy and the `/255` temporary are all live at once. Several such
    tracks running side by side exhaust an 8 GB machine, which is not a
    hypothetical — it happened on 2026-08-01.

    Holding uint8 and converting one frame at a time removes the multiplied
    peak, because the array is a view onto the decoded bytes and nothing larger
    is ever built. The *whole track* of that clip then peaks at 610 MB, under a
    third of what the old decode cost before tracking had begun. Nothing
    downstream sees uint8; `_grey` converts at each of the three places that
    read pixel values.
    """
    w, h, fps = truth.probe(path)
    W, H = int(w * scale) // 2 * 2, int(h * scale) // 2 * 2
    raw = subprocess.run(
        ["ffmpeg", "-loglevel", "error", "-i", str(path),
         "-vf", f"scale={W}:{H}", "-pix_fmt", "gray", "-f", "rawvideo", "-"],
        capture_output=True, check=True).stdout
    n = len(raw) // (W * H)
    return np.frombuffer(raw[:n * W * H], dtype=np.uint8).reshape(n, H, W), fps

# The sticker circle's radius as a fraction of the plate's. This one constant
# carries the whole absolute scale, so it is worth being clear about where it
# comes from and what it is worth.
#
# Measured on the three 2026-08-01 deadlifts, by detecting the plate rim with
# `truth.find_plate` and dividing the tracked constellation's circumradius by
# it: **0.862, 0.878, 0.834** — mean 0.858, spread +/-2.6%. Each was checked by
# eye, by drawing the detected circle back over the frame; the rim detection sits
# on the rim on both deadlifts in `analysis/35`.
#
# Why a constant rather than a per-capture detection, which is what `truth.py`
# does. Because the detection is not reliable enough to be worth the risk, and
# that was measured rather than assumed. Three ways of finding the rim were
# tried on this footage:
#
#   `truth.find_plate`, globally. Correct on deadlift, verified visually. On
#   bench it returns r=124 px against a plate of about 94, because a dark-disc
#   matched filter against a DARK background grows without limit — the same
#   failure `truth.py` records for its own bench seeding.
#   A radial intensity-gradient rim search. Beautifully consistent on deadlift
#   at a ratio of 0.928/0.938/0.929 — and wrong: it locks onto the bumper's
#   inner step, not its outer edge, which the overlay shows plainly. Consistency
#   is not accuracy, and this is the sharpest example of it in the project.
#   Floor contact, scanning down for where the plate meets the floor, which
#   should give the radius directly since a resting bar's centre is one plate
#   radius up. It gives 79.7 / 56.9 / 100.8 px on three captures of the same
#   plate. It is catching the shadow and the floor markings.
#
# So: one number, measured where it can be, applied everywhere, and flagged.
#
# **On bench this is transferred, not measured, and that is the weakest claim in
# this module.** The bench plate is a different plate (425 mm notched against
# the 445 mm bumper) and carries its own set of stickers, so the ratio holds
# only if they were applied with the same inset. Transferring by constant INSET
# instead — 31.6 mm measured on deadlift, giving 0.851 on the bench plate —
# agrees to 0.8%, so the choice between the two models does not matter; whether
# either applies to a plate the owner stickered on a different day is exactly
# what is untested. Treat every bench distance as carrying an unquantified
# scale error on top of the +/-2.6% deadlift spread, and read `sticker_ratio`
# in the calibration report, which reports what the rim detector made of the
# capture without letting it set anything.
STICKER_RATIO = 0.858

# Top-hat response below this is not a sticker. Set from the separation actually
# present in the footage rather than by taste: on `deadlift_150x5` frame 300 the
# four stickers score 0.651 / 0.604 / 0.561 / 0.557 and the brightest thing that
# is not a sticker — a ceiling light — scores 0.525. The margin is thin, which is
# why detection is never asked to pick the stickers out on brightness alone; the
# constellation geometry does that. This threshold only keeps the candidate list
# short.
MIN_RESPONSE = 0.05

# A tracked frame needs this many of the three rim markers. Two determines a
# similarity transform (4 degrees of freedom from 4 equations), so two is not a
# degraded mode, it is the minimum well-posed one.
MIN_MARKERS = 2

# ------------------------------------------------------------- detection --
def response(frame: np.ndarray, size: int = 7) -> np.ndarray:
    """White top-hat: how much brighter each pixel is than its neighbourhood.

    `frame - opening(frame)` keeps bright features smaller than the structuring
    element and removes everything larger, which is precisely the sticker-versus-
    gym discrimination: a 5 px reflective disc survives, a ceiling strip light,
    a window and a mirror do not survive intact.

    A square structuring element rather than a disc, because scipy's grey
    morphology is separable over a box and is not over a disc — 640x360 by ~760
    frames makes that the difference between seconds and minutes. The shape of
    the element does not matter here; only its size does, and at `size=7` it is
    comfortably larger than the ~5 px sticker and far smaller than any gym
    fixture.
    """
    frame = _grey(frame)
    return frame - grey_opening(frame, size=(size, size))


def _centroid(resp: np.ndarray, y: int, x: int, r: int = 3) -> tuple[float, float]:
    """Intensity-weighted centroid of the response around an integer peak.

    This is where the sub-pixel accuracy comes from, and it is the reason a
    5 px blob is enough. Weighting by the top-hat response rather than by raw
    brightness matters: raw brightness carries the plate's own gradient, which
    pulls the centroid off the sticker and toward whatever is locally lighter.
    """
    y0, y1 = max(0, y - r), min(resp.shape[0], y + r + 1)
    x0, x1 = max(0, x - r), min(resp.shape[1], x + r + 1)
    w = np.maximum(resp[y0:y1, x0:x1], 0.0)
    total = w.sum()
    if total <= 0:
        return float(y), float(x)
    yy, xx = np.mgrid[y0:y1, x0:x1]
    return float((w * yy).sum() / total), float((w * xx).sum() / total)


def detect(frame: np.ndarray, thresh: float = MIN_RESPONSE,
           max_n: int = 200) -> np.ndarray:
    """Candidate sticker positions in one frame: (K, 3) of (y, x, strength).

    Sub-pixel, strongest first. This deliberately over-detects — a gym is full
    of small bright things and `max_n` candidates typically hold a dozen lights
    and reflections alongside the four stickers. Choosing among them is
    `candidates`' job, on geometry, because geometry separates them and
    brightness does not (see `MIN_RESPONSE`).
    """
    resp = response(frame)
    peak = (resp == maximum_filter(resp, size=5)) & (resp > thresh)
    ys, xs = np.nonzero(peak)
    if len(ys) == 0:
        return np.empty((0, 3))
    strength = resp[ys, xs]
    keep = np.argsort(-strength)[:max_n]
    out = np.empty((len(keep), 3))
    for i, k in enumerate(keep):
        cy, cx = _centroid(resp, int(ys[k]), int(xs[k]))
        out[i] = (cy, cx, strength[k])
    return out


# ----------------------------------------------------------- constellation --
def _similarity(src: np.ndarray, dst: np.ndarray) -> tuple[float, float, np.ndarray]:
    """Least-squares similarity src -> dst. Returns (scale, angle_rad, offset).

    The closed-form Umeyama solution restricted to a similarity, which is what a
    rigid planar constellation viewed under weak perspective undergoes: it may
    translate, rotate in its own plane, and change apparent size as its distance
    from the camera changes. It may not shear, and refusing to fit shear is what
    keeps a mis-associated marker from quietly deforming the model to suit
    itself.
    """
    mu_s, mu_d = src.mean(axis=0), dst.mean(axis=0)
    s0, d0 = src - mu_s, dst - mu_d
    var = (s0 ** 2).sum()
    if var <= 0:
        return 1.0, 0.0, mu_d - mu_s
    # Complex-number formulation: a similarity is multiplication by one complex
    # number. Cleaner than assembling and SVD-ing a 2x2, and exactly equivalent.
    zs = s0[:, 1] + 1j * s0[:, 0]
    zd = d0[:, 1] + 1j * d0[:, 0]
    k = (zd * np.conj(zs)).sum() / (np.abs(zs) ** 2).sum()
    scale, angle = float(np.abs(k)), float(np.angle(k))
    # points are (y, x); the complex form above is (x + iy), so rotate in (x, y)
    off = mu_d - _apply_yx(scale, angle, mu_s[None, :])[0]
    return scale, angle, off


def _apply_yx(scale: float, angle: float, pts: np.ndarray,
              off: np.ndarray | None = None) -> np.ndarray:
    """Apply a similarity to (N, 2) points stored as (y, x)."""
    z = pts[:, 1] + 1j * pts[:, 0]
    w = z * (scale * np.exp(1j * angle))
    out = np.column_stack([w.imag, w.real])
    return out if off is None else out + off


def _triangle_ok(p: np.ndarray, tol: float = 0.25) -> float:
    """How equilateral a triangle is, in [0, 1]. 0 means reject.

    The three rim stickers are "approximately every third of the circumference",
    so their triangle is near-equilateral, and near-equilateral is a strong
    filter — three unrelated ceiling lights almost never are. `tol` is
    deliberately loose because "approximately" is the owner's word for the
    placement and the tracker must not be fussier than the stickers are.
    """
    d = np.array([np.hypot(*(p[0] - p[1])), np.hypot(*(p[0] - p[2])),
                  np.hypot(*(p[1] - p[2]))])
    if d.min() <= 0:
        return 0.0
    spread = (d.max() - d.min()) / d.mean()
    return float(max(0.0, 1.0 - spread / tol))


def candidates(frame: np.ndarray, dets: np.ndarray | None = None,
               top: int = 20, max_dets: int = 30, dark_max: float = 0.45,
               radius_band: tuple[float, float] = (28.0, 150.0),
               require_hub: bool = True, hub_frac: float = 0.80) -> list[dict]:
    """The best few sticker-triangle hypotheses in one frame, unaided.

    Unaided is the point. The first version of this anchored the search to the
    plate `truth.find_plate` detects, and `truth.find_plate` does not find the
    plate on bench footage — `truth.py`
    says so outright and records four auto-seeders that all preferred the
    lifter-and-bench silhouette. Anchoring to it on `bench_110x1` seeded the
    tracker on the bench frame and the floor shadow, 40 cm below a plate that
    was in clear view with all three stickers on it, and it sat there for 19 s.

    So this uses only what the markers themselves supply, and the fourth sticker
    turns out to be the thing that makes it work. A triple of bright specks that
    is near-equilateral and dark inside is common enough in a gym; a triple that
    *also* has a fourth bright speck sitting at its centroid is not. That is the
    end-cap marker, and requiring it is what separates the plate from the bench.

    **`hub_frac` is 0.80 of the circumradius, not the 0.45 this shipped with
    until C21 (2026-08-03), and the old value was a model error rather than a
    tight constant.** The end cap protrudes toward the camera by most of a
    sleeve, so where it projects is set by PARALLAX — this module's own header
    measures that offset swinging -111 to +57 px and correlating with bar height
    at r = 0.949. A gate expressed as a fraction of the plate's apparent size
    does not track that at all. What is physically true is only that the cap
    projects somewhere inside the plate disc, i.e. within one circumradius.
    On the 2026-08-03 bench captures the true hub sits at 0.55 of the
    circumradius and 0.45 rejected the real constellation in every frame; 0.80
    keeps a margin on both sides. The old value survived because it was never
    stressed: on `deadlift_150x5` the hub sits at 30.8 px against a 37.6 px
    gate, inside it by 18%.

    Returns up to `top` hypotheses, best first, as
    `{"rim", "hub", "centre", "circumradius", "score"}`. Several rather than one
    because the winner in any single frame may be wrong — `seed_frame` decides
    between them using evidence one frame does not have.

    **`top` is 20, raised from 5 by C21**, for the same reason `seed_frame` now
    suppresses static detections: per-frame appearance is a weak discriminator
    and it was being asked to make the final cut. The real constellation on
    `bench_95x2` ranks 8th to 10th in its own frame — it is genuinely less
    equilateral (0.42) than the ceiling grid — so a pool of 5 threw it away
    before the motion test that identifies it correctly ever ran.

    A second thing the unanchored version had to drop: any preference for a
    LARGE triangle. Scoring triples on regularity, brightness and size, the
    winner on `deadlift_150x5` frame 300 was one real sticker plus two ceiling
    lights — more equilateral than the truth (0.97 against 0.94) and nearly
    twice the size. A gym ceiling is a grid of bright rectangles and it makes
    better triangles than a barbell does.
    """
    if dets is None:
        dets = detect(frame)
    if len(dets) < 3:
        return []
    pts = dets[:, :2]
    n = min(len(dets), max_dets)
    out = []
    for i in range(n):
        for j in range(i + 1, n):
            for k in range(j + 1, n):
                tri = pts[[i, j, k]]
                reg = _triangle_ok(tri)
                if reg <= 0:
                    continue
                cen = tri.mean(axis=0)
                circ = float(np.hypot(*(tri - cen).T).mean())
                if not (radius_band[0] <= circ <= radius_band[1]):
                    continue
                if _interior_mean(frame, tri) > dark_max:
                    continue
                d = np.hypot(*(pts - cen).T)
                near = np.nonzero(d < hub_frac * circ)[0]
                hub = pts[near[np.argmin(d[near])]] if len(near) else None
                if require_hub and hub is None:
                    continue
                out.append({"rim": tri, "hub": hub, "circumradius": circ,
                            "centre": cen,
                            "score": reg * float(dets[[i, j, k], 2].mean())})
    out.sort(key=lambda c: -c["score"])
    return out[:top]


def plate_radius_near(frame: np.ndarray, centre: np.ndarray,
                      circumradius: float) -> tuple[float, float, int, float]:
    """Detect the plate rim in a window around a known constellation.

    Returns `(centre_y, centre_x, radius_px, score)` in **full-frame**
    coordinates.

    `truth.find_plate` searching a whole frame is a global argmax over a gym,
    and on bench it loses. Searching a window centred on a constellation we have
    already found is a different and much easier problem — the plate is the only
    dark disc in the box, and its radius is known to within a small band before
    we start, because the stickers sit near its rim.

    This is the only place the absolute pixels-to-metres scale comes from, so
    keeping it local is what makes the scale trustworthy on a lift where the
    global detector is not.

    **The centre it returns is weaker evidence than the radius, and
    `calibration_report` leans on it — so note the weakness there.** The window
    is placed using the constellation, so the two are no longer independent:
    a plate centre found inside a box centred on the rim centroid cannot fall
    very far from it. The box is deliberately loose, at 2.2 circumradii against
    a plate of about 1.15, which leaves the detector roughly a full radius of
    freedom either way — enough to disagree, but not the arms-length check a
    global detection would be.
    """
    half = int(round(2.2 * circumradius))
    cy, cx = int(round(centre[0])), int(round(centre[1]))
    y0, y1 = max(0, cy - half), min(frame.shape[0], cy + half)
    x0, x1 = max(0, cx - half), min(frame.shape[1], cx + half)
    crop = _grey(frame[y0:y1, x0:x1])
    lo = max(8, int(0.90 * circumradius))
    hi = max(lo + 2, int(1.45 * circumradius))
    py, px, r, sc = truth.find_plate(crop, radii=range(lo, hi, 2))
    return float(py + y0), float(px + x0), int(r), float(sc)


def _interior_mean(frame: np.ndarray, tri: np.ndarray) -> float:
    """Mean brightness inside a triangle, sampled on its medial points.

    Sampled rather than rasterised: nine points on the segments joining the
    centroid to each vertex and to each edge midpoint. That is enough to tell a
    black plate from a lit ceiling and costs nothing inside a triple loop.
    """
    cen = tri.mean(axis=0)
    probes = [cen]
    for v in tri:
        probes += [cen + f * (v - cen) for f in (0.35, 0.7)]
    for a, b in ((0, 1), (0, 2), (1, 2)):
        mid = 0.5 * (tri[a] + tri[b])
        probes.append(cen + 0.6 * (mid - cen))
    vals = []
    for p in probes:
        y, x = int(round(p[0])), int(round(p[1]))
        if 0 <= y < frame.shape[0] and 0 <= x < frame.shape[1]:
            vals.append(frame[y, x])
    if not vals:
        return 1.0
    m = float(np.mean(vals))
    return m / 255.0 if frame.dtype == np.uint8 else m


def static_points(stack: np.ndarray, n_sample: int = 30, radius: float = 3.0,
                  recur_max: float = 0.7) -> np.ndarray:
    """Pixel locations where a detection keeps reappearing: the furniture.

    Added by C21 (2026-08-03). **The camera is on a tripod, so a gym fixture
    projects to the same pixel in every frame and the bar does not.** That is
    the sharpest discriminator available here and it costs one pass of
    `detect`; `seed_frame` has always said so in prose — "the bar is the thing
    in a gym that moves" — but only applied it after `candidates` had already
    pruned each frame to its best few hypotheses on appearance alone. By then
    the real constellation was frequently gone.

    Detections from `n_sample` frames are binned onto a `radius`-pixel grid and
    a bin is called static if it holds a detection in more than `recur_max` of
    those frames. Returns the bin centres, for `_suppress` to subtract.

    Measured on `bench_95x2`, which is why the default is 0.7 and not 0.5: the
    three real stickers recur at **0.19, 0.23 and 0.48** — the 0.48 because the
    bar sits racked for much of the clip, which is the failure mode to respect
    here — while 57% of all detections recur above 0.7. Suppression takes that
    frame from 200 detections to 96 and moves the stickers from ranks 0/22/48
    to 0/4/13, i.e. inside `candidates`' `max_dets` for the first time.

    **The limit this has, and it is the one to watch:** a capture where the bar
    is racked or motionless for more than `recur_max` of its length would have
    its own stickers judged static and suppressed. Nothing here detects that
    happening. `bar_path` raising "no sticker constellation found" on a clip
    with obviously visible markers is what it would look like; the response is
    to raise `recur_max`, not to lower it. A hand-held camera breaks the
    premise outright and this whole function with it.
    """
    stride = max(1, len(stack) // n_sample)
    idx = list(range(0, len(stack), stride))
    return _static_from([detect(stack[i]) for i in idx], radius, recur_max)


def _static_from(per: list[np.ndarray], radius: float = 3.0,
                 recur_max: float = 0.7) -> np.ndarray:
    """`static_points` given the per-frame detections already computed.

    Split out so `seed_frame` runs `detect` over the sampled frames once rather
    than twice; the sampling is the expensive half of seeding.
    """
    per = [d for d in per if len(d)]
    if not per:
        return np.empty((0, 2))
    allp = np.vstack([d[:, :2] for d in per])
    key = np.round(allp / radius).astype(int)
    uniq, inv = np.unique(key, axis=0, return_inverse=True)
    cen = np.zeros((len(uniq), 2))
    cnt = np.zeros(len(uniq))
    np.add.at(cen, inv, allp)
    np.add.at(cnt, inv, 1)
    cen /= cnt[:, None]
    seen = np.zeros(len(uniq))
    off = 0
    for d in per:
        seen[np.unique(inv[off:off + len(d)])] += 1
        off += len(d)
    return cen[seen / len(per) > recur_max]


def _suppress(dets: np.ndarray, static: np.ndarray,
              radius: float = 3.0) -> np.ndarray:
    """Drop detections sitting on a known static point."""
    if not len(dets) or not len(static):
        return dets
    d = np.hypot(dets[:, 0, None] - static[None, :, 0],
                 dets[:, 1, None] - static[None, :, 1]).min(axis=1)
    return dets[d >= radius]


def seed_frame(stack: np.ndarray, n_sample: int = 30) -> tuple[int, dict, tuple]:
    """Find the constellation to track, and the frame to take its shape from.

    Returns `(index, constellation, plate)`, where `plate` is
    `plate_radius_near`'s `(centre_y, centre_x, radius_px, score)`. The plate is
    a **cross-check only** — `calibration_report` reports it and `STICKER_RATIO`
    sets the scale — so a capture where it is wrong is flagged rather than
    mis-scaled.

    **The bar is the thing in a gym that moves, and that is what picks it out
    here.** Per-frame appearance cannot: a bench frame, a rack upright and a
    shadow can all produce a triangle that is regular, dark inside and sized
    like a plate, and on `bench_110x1` one did — for 19 s, while the real plate
    sat in shot with all three markers visible.

    So hypotheses are gathered from frames across the clip, grouped by apparent
    size (rigid, so the true one is consistent), and each group is scored on
    three things a single frame cannot see:

      - **how far it moves** over the clip, which is what a barbell does and
        what the furniture does not;
      - **how many sampled frames it appears in**, since a real marker set is
        visible throughout and a coincidence is not;
      - its mean per-frame quality.

    **C21 (2026-08-03) moved the motion test to the front, and that is the
    substantive change to this function.** The three bullets above ran only on
    what `candidates` had already selected per frame — and `candidates` selects
    on appearance, which is the thing this docstring says does not work. On the
    2026-08-03 paired captures the real constellation was being discarded before
    the group scoring ever saw it, and every one of the six seeded on rack
    holes. `static_points` now removes fixtures first, so the pool the motion
    test scores actually contains the bar. See that function for the measured
    separation and for the racked-bar limit it carries.

    The plate radius is then measured locally, by `plate_radius_near`, around
    the winning constellation — not by a global `truth.find_plate`, which is
    the step that failed on bench in the first place.
    """
    stride = max(1, len(stack) // n_sample)
    idx = list(range(0, len(stack), stride))
    per = [detect(stack[i]) for i in idx]
    static = _static_from(per)
    pool = []
    for i, dets in zip(idx, per):
        for c in candidates(stack[i], dets=_suppress(dets, static)):
            pool.append((i, c))
    if not pool:
        raise ValueError(
            "no sticker constellation found in any sampled frame. Either the "
            "markers are not visible in this capture, or the plate is far "
            "outside the 28-150 px radius band `candidates` searches."
        )

    # Group by apparent size. The constellation is rigid, so the true one holds
    # its circumradius all clip; a coincidence does not recur at a stable size.
    groups: list[list] = []
    for i, c in sorted(pool, key=lambda p: -p[1]["circumradius"]):
        for g in groups:
            if abs(c["circumradius"] - g[0][1]["circumradius"]) < 0.15 * g[0][1]["circumradius"]:
                g.append((i, c))
                break
        else:
            groups.append([(i, c)])

    best = None
    for g in groups:
        cen = np.array([c["centre"] for _, c in g])
        frames_seen = len({i for i, _ in g})
        spread = float(np.hypot(*(cen.max(axis=0) - cen.min(axis=0))))
        quality = float(np.mean([c["score"] for _, c in g]))
        # Movement is in pixels and dominates deliberately; a static hypothesis
        # scores near zero however pretty it is.
        sc = quality * frames_seen * (1.0 + spread)
        if best is None or sc > best[0]:
            best = (sc, g, spread, frames_seen)

    _, g, spread, frames_seen = best
    i, c = max(g, key=lambda p: p[1]["score"])
    plate = plate_radius_near(stack[i], c["centre"], c["circumradius"])
    # `static` rides along in the constellation so `track` gets it without a
    # second pass of `detect` over the sampled frames. It is not part of the
    # constellation's geometry; it is the furniture map that found it.
    c = dict(c, group_spread_px=spread, group_frames=frames_seen, static=static)
    return i, c, plate


# ---------------------------------------------------------------- tracking --
def _reacquire(frame: np.ndarray, dets: np.ndarray, centre: np.ndarray,
               radius: float, search: float, tol: float = 0.22,
               dark_max: float = 0.45) -> np.ndarray | None:
    """Find the constellation afresh within `search` px of `centre`. (3, 2) or None.

    The same geometry as `candidates`, but anchored on the model's own size
    rather than on `truth.find_plate` — which cannot be re-run per frame at
    any sensible cost, and which is unreliable once the bar leaves the floor
    anyway. The known circumradius does the work the plate radius does there,
    and by this point it is known well: it holds to a few percent all clip.

    `search` is where to look, and it is deliberately **not** taken from an
    extrapolated position. Anchoring the search on a predicted centre was the
    first attempt and it fails in the one place it is most needed. On
    `deadlift_150x5` the tracker follows the bar cleanly down to the floor at
    12.03 s — three markers, ~1 px residual — and loses it in the impact, at
    which point it is carrying 15.6 px/frame of downward velocity. Extrapolating
    that walked the search box through the floor and off the bottom of the
    frame, so every one of the 397 re-acquisition attempts that followed looked
    at blank tarmac while the bar sat plainly visible where it had landed. The
    search is therefore centred on the last *known* position and widened as the
    gap grows, which is the opposite trade: slower to follow a genuinely moving
    bar, incapable of running away from a stationary one.
    """
    if len(dets) < 3:
        return None
    pts = dets[:, :2]
    d = np.hypot(pts[:, 0] - centre[0], pts[:, 1] - centre[1])
    near = np.nonzero(d < search + radius * (1 + tol))[0][:28]
    if len(near) < 3:
        return None
    best = None
    for a in range(len(near)):
        for b in range(a + 1, len(near)):
            for c in range(b + 1, len(near)):
                idx = near[[a, b, c]]
                tri = pts[idx]
                cen = tri.mean(axis=0)
                if np.hypot(*(cen - centre)) > search:
                    continue
                circ = float(np.hypot(*(tri - cen).T).mean())
                if abs(circ - radius) > tol * radius:
                    continue
                reg = _triangle_ok(tri)
                if reg <= 0:
                    continue
                if _interior_mean(frame, tri) > dark_max:
                    continue
                sc = reg * float(dets[idx, 2].mean())
                if best is None or sc > best[0]:
                    best = (sc, tri)
    return None if best is None else best[1]


def _best_correspondence(local: np.ndarray, tri: np.ndarray,
                         prev_angle: float) -> tuple:
    """Match a freshly found triangle to the model, resolving the 3-fold tie.

    A near-equilateral triangle looks the same rotated by 120 degrees, so a
    re-acquisition cannot tell which sticker is which from shape alone. It does
    not matter for the path — the centroid is the same whichever labelling is
    chosen, which is the reason the centroid and not a labelled point is what
    this module reports. It matters only for `angle` staying continuous, so the
    labelling is picked to minimise the rotation jump.

    Mirror images are excluded rather than scored: the plate cannot flip.
    """
    best = None
    for perm in ((0, 1, 2), (1, 2, 0), (2, 0, 1),
                 (0, 2, 1), (2, 1, 0), (1, 0, 2)):
        dst = tri[list(perm)]
        s, a, off = _similarity(local, dst)
        r = float(np.hypot(*(_apply_yx(s, a, local, off) - dst).T).mean())
        if r > 0.25 * np.hypot(*local[0]):      # wrong handedness folds badly
            continue
        jump = abs(np.angle(np.exp(1j * (a - prev_angle))))
        if best is None or jump < best[0]:
            best = (jump, s, a, off, r)
    return best[1:] if best else (None, None, None, None)


def track(stack: np.ndarray, seed: int, model: dict, gate: float = 14.0,
          max_scale_step: float = 0.06, max_angle_step_deg: float = 12.0,
          max_jump_px: float = 30.0, max_scale_dev: float = 0.25,
          static: np.ndarray | None = None) -> dict:
    """Follow the constellation through the clip, forwards and backwards.

    Returns per-frame arrays: `centre` (N, 2) as (y, x), `scale`, `angle`,
    `n_markers`, `score`, `hub` (N, 2), `residual_px`.

    `static` is `static_points`' output, and passing it is what stops a lost
    tracker settling on the furniture. **C21 (2026-08-03) added it after fixing
    the seeding alone turned out to fix nothing.** With the seed correct on
    `bench_95x2` — frame 1066, squarely on the plate — the backward pass still
    lost the plate and re-acquired on the bench-and-floor structure, then held
    it for frames 0-950 at a residual of 1.3 px with all three markers
    "matched". That is the same failure `_reacquire`'s docstring describes on
    `bench_110x1`, and it is invisible to every quality number this module
    reports: a rigid triple of gym fixtures fits a rigid model perfectly. Only
    the fact that it does not MOVE gives it away, which is precisely what
    `static_points` measures.

    **It is applied to re-acquisition only, and that boundary was measured
    rather than chosen.** Suppressing static detections everywhere in the loop
    also blindfolds ordinary association, and on `deadlift_190x1` — a single,
    so the bar rests on the floor for most of the clip — the plate's own
    stickers recur past `recur_max` and coverage collapsed from 99.6% to 28.4%.
    Association does not need the help: it matches inside a 14 px gate anchored
    on the previous pose, which no fixture can enter. Re-acquisition is the one
    step with no such anchor.

    The method is predict-associate-fit-**check**, and every one of those four
    words was paid for.

    *Predict, associate, fit.* Each frame's marker positions are predicted from
    the previous pose plus its velocity, detections are associated to those
    predictions inside a tight `gate`, and the pose is re-fitted from whatever
    matched. Markers are never tracked independently. That was tried first and
    fails plainly: with nearest-peak tracking per marker, the triangle's sides —
    which are rigid and cannot change — varied by 69.5% over one clip, because a
    marker that jumps to a ceiling light has nothing to pull it back.

    *Check*, and this is the part that is not obvious. **A two-marker fit is
    exact and therefore proves nothing.** A similarity has four degrees of
    freedom and two points supply four equations, so any pair whatever produces
    a residual of exactly zero. An early version reported `residual 0.00 px` over
    85% of a clip and was tracking the wrong pair of blobs the whole way. The
    residual cannot referee a thin fit, so physics does instead: between adjacent
    frames the plate's apparent size cannot change by more than
    `max_scale_step`, it cannot rotate by more than `max_angle_step_deg`, and its
    centre cannot leave the prediction by more than `max_jump_px`. A fit failing
    any of those is discarded however well it fits.

    `max_scale_dev` is the fourth, and it is not redundant with the first.
    Per-step limits **compound**: 6% a frame is a factor of 5.7 over thirty
    frames, and on `bench_85x6` that is exactly what happened — the fitted
    circumradius wandered from 29 px to 94 px, a threefold change in the
    apparent size of a rigid steel plate, with every individual step legal. The
    absolute bound is available because the camera is on a tripod: the only
    thing that can change the constellation's apparent size is its distance from
    the lens, and a bar whose fore-aft travel is a few centimetres against a
    camera two or three metres away cannot move it by more than a few percent.
    Measured on the three deadlifts it holds to 2-4%; the gate is set at 25%.

    *Re-acquire.* A discarded or impossible frame then triggers `_reacquire`
    around the predicted centre. Without it the tracker was a one-way trip: on
    `deadlift_150x5` it held lock for the 12 s of setup and lost the bar at the
    instant of lift-off, then reported nothing for the remaining 13 s — the only
    part of the clip anybody wants. Detections were never the problem there;
    17-29 strong candidates sat within 140 px of the bar in every lost frame.

    `score` is the fit quality in [0, 1]: the fraction of the three rim markers
    matched, attenuated by the fit residual. **It is not an NCC and it must not
    be compared with `truth.GOOD_SCORE`.**
    """
    n = len(stack)
    rim0 = model["rim"]
    local = rim0 - rim0.mean(axis=0)          # model coordinates, origin at centre
    model_r = float(np.hypot(*local.T).mean())
    max_angle_step = np.deg2rad(max_angle_step_deg)

    centre = np.full((n, 2), np.nan)
    scale = np.full(n, np.nan)
    angle = np.full(n, np.nan)
    nmark = np.zeros(n, int)
    score = np.full(n, np.nan)
    hubs = np.full((n, 2), np.nan)
    resid = np.full(n, np.nan)

    for step in (1, -1):
        s, a, off = 1.0, 0.0, rim0.mean(axis=0)
        vel = np.zeros(2)
        prev_centre = rim0.mean(axis=0)
        gap = 1
        i = seed
        while 0 <= i < n:
            # Extrapolation is capped at two frames. Beyond that the velocity
            # is a guess about a bar that has already done something
            # unaccounted for, and running with it is how the search left the
            # frame entirely — see `_reacquire`.
            pred_centre = prev_centre + vel * min(gap, 2)
            pred = _apply_yx(s, a, local, pred_centre)
            dets = detect(stack[i])
            if len(dets) == 0:
                gap += 1
                i += step
                continue
            pts = dets[:, :2]

            # Widen the gate while lost, and with speed: the prediction is worst
            # right after a gap, which is exactly when it must not be strict.
            g = gate * min(gap, 4) + 0.25 * float(np.hypot(*vel))

            src_l, dst_l, used = [], [], set()
            for m in range(3):
                d = np.hypot(*(pts - pred[m]).T)
                for j in np.argsort(d)[:3]:
                    if d[j] < g and int(j) not in used:
                        used.add(int(j))
                        src_l.append(local[m])
                        dst_l.append(pts[j])
                        break

            ns = na = noff = None
            r = np.nan
            nm = 0
            if len(dst_l) >= MIN_MARKERS:
                cs, ca, coff = _similarity(np.array(src_l), np.array(dst_l))
                cc = _apply_yx(cs, ca, np.zeros((1, 2)), coff)[0]
                if (abs(np.log(cs / s)) < max_scale_step
                        and abs(np.log(cs)) < max_scale_dev
                        and abs(np.angle(np.exp(1j * (ca - a)))) < max_angle_step
                        and np.hypot(*(cc - pred_centre)) < max_jump_px * gap):
                    ns, na, noff = cs, ca, coff
                    nm = len(dst_l)
                    r = float(np.hypot(*(_apply_yx(cs, ca, np.array(src_l), coff)
                                         - np.array(dst_l)).T).mean())

            if ns is None:
                # Suppression applies HERE and nowhere else in the loop. See
                # the `static` note in this function's docstring: association
                # is anchored by a 14 px gate and furniture cannot reach it,
                # so the only step that needs protecting is the one that can
                # teleport. Suppressing everywhere instead cost
                # `deadlift_190x1` 72% of its frames — a heavy single leaves
                # the bar on the floor for most of the clip, so its own
                # stickers recur past `recur_max` and the tracker was
                # blindfolded to the plate it was already holding.
                rdets = dets if static is None else _suppress(dets, static)
                tri = _reacquire(stack[i], rdets, prev_centre, s * model_r,
                                 search=min(45.0 + 30.0 * gap, 260.0))
                if tri is not None:
                    cs, ca, coff, cr = _best_correspondence(local, tri, a)
                    # A re-acquisition gets the SAME plausibility test as an
                    # association, and for a sharper reason. It is the one path
                    # that can teleport: it is not anchored to the previous
                    # marker positions at all, so on `bench_110x1` it lost the
                    # bar at the rack and re-acquired 26 cm away, rotated 62.8
                    # degrees, in a single step. Note what that angle means. The
                    # triangle is near-equilateral, so `_best_correspondence`
                    # can always bring a genuine plate within 60 degrees; a best
                    # correspondence still 63 degrees out is not the same shape,
                    # and the angle gate is what says so.
                    cc = (_apply_yx(cs, ca, np.zeros((1, 2)), coff)[0]
                          if cs is not None else None)
                    if (cs is not None
                            and abs(np.log(cs / s)) < 0.25
                            and abs(np.log(cs)) < max_scale_dev
                            and abs(np.angle(np.exp(1j * (ca - a))))
                                < max_angle_step * gap
                            and np.hypot(*(cc - prev_centre))
                                < max_jump_px * gap):
                        ns, na, noff, r, nm = cs, ca, coff, cr, 3
                        used = set()

            if ns is None:
                gap += 1
                i += step
                continue

            c = _apply_yx(ns, na, np.zeros((1, 2)), noff)[0]
            centre[i] = c
            scale[i] = ns
            angle[i] = na
            nmark[i] = nm
            resid[i] = r
            score[i] = (nm / 3.0) * float(np.exp(-r / 2.0))

            circum = ns * model_r
            d = np.hypot(*(pts - c).T)
            cand = [j for j in np.argsort(d)[:5]
                    if int(j) not in used and d[j] < 0.6 * circum]
            if cand:
                hubs[i] = pts[cand[0]]

            vel = (c - prev_centre) / gap
            prev_centre, s, a, off = c, ns, na, noff
            gap = 1
            i += step

    return {"centre": centre, "scale": scale, "angle": angle,
            "n_markers": nmark, "score": score, "hub": hubs,
            "residual_px": resid, "circumradius_px": scale * model_r}


# -------------------------------------------------------------- calibration --
def calibration_report(stack: np.ndarray, seed: int, model: dict,
                       trk: dict, plate: tuple, m_per_px: float) -> dict:
    """Everything needed to judge whether this track can be believed.

    Four numbers, and each is a falsifier for one of the module's assumptions.

    `centre_offset_px` — the distance between the rim-sticker centroid and the
    detected plate centre at the seed frame. This is `e`, the bias the
    equal-spacing assumption costs: three stickers exactly 120 degrees apart
    have their centroid on the bar axis, and three that are only approximately
    so do not. Read it with `plate_radius_near`'s caveat in mind — the plate was
    detected in a window placed by the constellation, so the two are not fully
    independent and this is a lower bound on the disagreement rather than a
    clean measurement of it.

    `rotation_deg` — the peak-to-peak swing of the plate's rotation over the
    clip. This is what makes `e` matter: a fixed offset in plate coordinates is
    a fixed offset in the image only while the plate holds still, and becomes an
    arc of radius `e` once it turns. A capture with either near zero is safe
    whatever the other does.

    `spacing_bias_cm` — the two multiplied, in the units the spec is written in.
    This is the honest bound on what the equal-spacing assumption may be costing
    this capture, and it is the number to quote against the 1 cm target.

    `sticker_ratio` — the sticker circle's radius over the detected plate
    radius. The owner placed the stickers "as close to the circumference as
    possible", so this should sit a little under 1. Well away from it says the
    rim detection and the constellation are not looking at the same plate.
    """
    py, px, prad, _ = plate
    cen = model["rim"].mean(axis=0)
    offset = float(np.hypot(cen[0] - py, cen[1] - px))
    circum = float(np.hypot(*(model["rim"] - cen).T).mean())

    a = trk["angle"][np.isfinite(trk["angle"])]
    swing = float(np.rad2deg(np.ptp(np.unwrap(a))) if len(a) else np.nan)

    # The arc an offset `e` sweeps when the plate turns through `swing`, capped
    # at the full circle: beyond 2 radians the chord stops growing usefully.
    #
    # Reported only where the rim detection is credible, and NaN otherwise. `e`
    # is measured against the detected plate centre, so a capture where the rim
    # detector has failed produces a large `e` that is the detector's error and
    # not the stickers'. On `bench_110x1` that read 122 px, which would have gone
    # out as a 4.8 cm spacing bias on a lift whose real one is unknown. A
    # diagnostic that cannot tell whose fault it is measuring should say so
    # rather than name the wrong culprit.
    ratio = circum / prad if prad else float("nan")
    credible = abs(ratio - STICKER_RATIO) <= 0.15
    arc = offset * min(np.deg2rad(swing) if np.isfinite(swing) else 0.0, 2.0)

    return {
        "plate_radius_px": int(prad),
        "rim_detection_credible": bool(credible),
        "plate_centre_px": (float(py), float(px)),
        "rim_centroid_px": (float(cen[0]), float(cen[1])),
        "centre_offset_px": offset,
        "circumradius_px": circum,
        "sticker_ratio": ratio,
        "rotation_deg": swing,
        "spacing_bias_cm": float(arc * m_per_px * 100) if credible else float("nan"),
    }


# --------------------------------------------------------------- bar path --
def bar_path(video: str | Path, scale: float = 1.0, check: bool = True,
             diameter_m: float | None = None) -> dict:
    """Track the stickers and return the bar path in metres.

    The returned dict is deliberately key-compatible with `truth.bar_path` — it
    carries `t`, `x`, `height`, `score`, `fps`, `m_per_px` and `travel_m` — so
    `metrics.vs_truth` and the plotting can consume either referee without
    knowing which they were handed. Note that `score` means something different
    here and does not compare with `truth.GOOD_SCORE`; see `track`.

    Beyond those it adds the things the old referee could not measure:

    `x_flat` / `height_flat` are the path under a single fixed scale, the way
    `truth.bar_path` computes it. `x` / `height` are the same path with the
    per-frame scale applied. **Both are returned on purpose**, so that the size
    of the correction is visible from the output rather than asserted here.
    `perspective_shift_cm` is how far apart they end up.

    Measured on the five `data_v2` captures it is **0.6-1.4 cm on deadlift and
    0.1-0.4 cm on bench** — real, and worth having against a 1 cm spec, and much
    smaller than the tracking failures it sits alongside. It is emphatically not
    the ±20% the vertical scale is out by; see the module docstring.

    `calibration` is `calibration_report` — read it before quoting anything.

    Full resolution by default, unlike `truth.bar_path`'s `scale=0.5`. The
    stickers are ~5 px at full size in `data_v2`'s 360x640 footage and halving
    that would throw away the sub-pixel accuracy that is the entire point. That
    is why the clip is held as uint8 and converted per frame — see `_frames_u8`.
    """
    stack, fps = _frames_u8(video, scale)
    seed, model, plate = seed_frame(stack)
    trk = track(stack, seed, model, static=model.get("static"))

    diam = diameter_m if diameter_m is not None else truth.plate_diameter(video)
    # The absolute scale, and note what it does NOT depend on: any per-capture
    # rim detection. The sticker circle's size in metres follows from the plate's
    # known diameter and one measured constant (`STICKER_RATIO`); its size in
    # pixels is measured in every frame by the tracker. The rim detector is still
    # run, but only to be reported in `calibration` as a cross-check — it sets
    # nothing. That is a deliberate reversal of `truth.py`, where the rim
    # detection IS the scale and a bad one is silent.
    sticker_r_m = 0.5 * diam * STICKER_RATIO
    m_per_px_seed = sticker_r_m / model["circumradius"]
    cal = calibration_report(stack, seed, model, trk, plate, m_per_px_seed)

    cen = trk["centre"]
    ok = np.isfinite(cen[:, 0])
    ref = np.nanmax(cen[:, 0])            # lowest point in frame = bar at floor
    refx = float(np.nanmedian(cen[:, 1]))

    # Flat: one scale for the whole clip, the old behaviour.
    x_flat = (cen[:, 1] - refx) * m_per_px_seed
    h_flat = -(cen[:, 0] - ref) * m_per_px_seed

    # Per-frame: the constellation's own apparent size sets the scale in each
    # frame. Distances are measured from the frame centre, which stands in for
    # the principal point — see the module docstring's Limits.
    with np.errstate(invalid="ignore", divide="ignore"):
        m_per_px_t = sticker_r_m / trk["circumradius_px"]
    cy0, cx0 = stack.shape[1] / 2.0, stack.shape[2] / 2.0
    x_m = (cen[:, 1] - cx0) * m_per_px_t
    h_m = -(cen[:, 0] - cy0) * m_per_px_t
    x = x_m - np.nanmedian(x_m)
    height = h_m - np.nanmin(h_m[ok]) if ok.any() else h_m

    travel = float(np.nanmax(height) - np.nanmin(height)) if ok.any() else np.nan
    shift = float(np.nanmax(np.abs((height - (h_flat - np.nanmin(h_flat[ok])))))
                  * 100) if ok.any() else np.nan

    path = {
        "t": np.arange(len(stack)) / fps,
        "x": x,
        "height": height,
        "score": trk["score"],
        "fps": fps,
        "m_per_px": m_per_px_seed,
        "m_per_px_t": m_per_px_t,
        "plate_radius_px": cal["plate_radius_px"],
        "seed_frame": seed,
        "travel_m": travel,
        "x_flat": x_flat - np.nanmedian(x_flat),
        "height_flat": h_flat - (np.nanmin(h_flat[ok]) if ok.any() else 0.0),
        "perspective_shift_cm": shift,
        "n_markers": trk["n_markers"],
        "angle": trk["angle"],
        "hub": trk["hub"],
        "centre_px": cen,
        "residual_px": trk["residual_px"],
        "circumradius_px": trk["circumradius_px"],
        "calibration": cal,
        "sticker_radius_m": sticker_r_m,
    }
    if check:
        validate(path, video)
    return path


MAX_TOP_RESIDUAL_CM = 0.5   # the referee's own fit error, where it is worst


def top_of_travel_residual(path: dict, frac: float = truth.TOP_FRAC) -> dict:
    """How well the rigid model fits WHERE THE FIT IS WORST, not on average.

    The exact counterpart of `truth.top_of_travel_score`, and it exists for the
    same reason that one does. This project has now been bitten five times by an
    aggregate that passes while the thing fails exactly where it matters —
    milestones 1-6, C8's peak-height threshold, C10's clip-composition artefact,
    C12's whole-clip NCC median, and this. **A referee needs checking where it
    is used.**

    `frac` matches `truth.TOP_FRAC` deliberately, so "at lockout" means the same
    span of travel for both trackers and the two remain comparable.

    What it found, measured 2026-08-02 over all five `data_v2` captures. The
    whole-clip median is the quantity the old gate tested:

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
    frames fall below `truth.GOOD_SCORE`.

    Why the residual degrades with height at all: the marker is further from the
    camera at lockout and subtends fewer pixels, so its centroid is noisier.
    Correlation with height is +0.24 to +0.93 across the five.

    Conservative by about sqrt(3). The residual is the misfit of three markers
    to a rigid triangle; the CENTROID those markers determine is better
    conditioned than any one of them. So this over-states the position error,
    and is the right way round for a gate.
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


def validate(path: dict, video: str | Path = "") -> None:
    """Raise or warn on the ways a sticker track can be wrong.

    Modelled on `truth.validate`, and for the same reason: a tracker that fails
    silently is worse than one that fails loudly, and this project has been
    caught by a confident 0.907 median NCC on a motionless piece of background.

    The checks differ because the failure modes do. A constellation tracker
    cannot lock onto static background — the geometry would not fit — but it
    can lose markers, ride on two for long stretches, or be seeded on a triple
    of ceiling lights that happens to be equilateral and dark inside.
    """
    name = Path(video).name or "video"
    ok = np.isfinite(path["height"])
    if not ok.any():
        raise ValueError(f"{name}: constellation never tracked.")

    if path["travel_m"] < truth.MIN_TRAVEL_M:
        raise ValueError(
            f"{name}: tracked bar moved only {path['travel_m']*100:.1f} cm over "
            f"the whole clip. The constellation was found but it is not on a "
            f"barbell — check the seed frame."
        )

    frac = float(ok.mean())
    if frac < 0.9:
        warnings.warn(
            f"{name}: only {frac:.0%} of frames tracked. The rest saw fewer "
            f"than {MIN_MARKERS} rim markers.", stacklevel=2)

    thin = float((path["n_markers"] == 2)[ok].mean())
    if thin > 0.25:
        warnings.warn(
            f"{name}: {thin:.0%} of tracked frames rode on two markers rather "
            f"than three. The pose is still determined but the scale is the "
            f"weakest part of it.", stacklevel=2)

    cal = path["calibration"]
    # A cross-check, not a gate on the scale — `STICKER_RATIO` sets that. This
    # says only whether the rim detector agrees with the constellation on this
    # capture. It does not on bench, which is known and is why it does not vote.
    if abs(cal["sticker_ratio"] - STICKER_RATIO) > 0.15:
        warnings.warn(
            f"{name}: the rim detector puts the sticker circle at "
            f"{cal['sticker_ratio']:.2f} of the plate radius, against the "
            f"{STICKER_RATIO:.3f} this module scales by. The absolute scale is "
            f"unconfirmed on this capture — distances may carry that ratio as a "
            f"multiplicative error. See markers.STICKER_RATIO.", stacklevel=2)

    if np.isfinite(cal["spacing_bias_cm"]) and cal["spacing_bias_cm"] > 1.0:
        warnings.warn(
            f"{name}: the rim centroid sits {cal['centre_offset_px']:.0f} px "
            f"off the detected plate centre and the plate turns "
            f"{cal['rotation_deg']:.0f} deg over the clip, so unequal sticker "
            f"spacing could be moving the reported path by up to "
            f"{cal['spacing_bias_cm']:.1f} cm — at or above the 1 cm spec. See "
            f"calibration_report.", stacklevel=2)

    # Where the fit is worst, not on average. A whole-clip median cannot see a
    # failure confined to part of the movement, and that is the exact defect
    # this module was written to fix in `truth.py` — so it must not be the only
    # thing checked here. See `top_of_travel_residual`.
    top = top_of_travel_residual(path)
    if np.isfinite(top["median_cm"]) and top["median_cm"] > MAX_TOP_RESIDUAL_CM:
        warnings.warn(
            f"{name}: the constellation fit residual over the top "
            f"{truth.TOP_FRAC:.0%} of travel is {top['median_cm']:.2f} cm "
            f"({top['median_px']:.2f} px), above the {MAX_TOP_RESIDUAL_CM} cm "
            f"this module treats as usable, against {top['whole_cm']:.2f} cm "
            f"over the whole clip. Distances near lockout carry that error. "
            f"See markers.top_of_travel_residual.", stacklevel=2)
    elif np.isfinite(top["ratio"]) and top["ratio"] > 4.0:
        warnings.warn(
            f"{name}: the fit residual is {top['ratio']:.1f}x worse over the "
            f"top {truth.TOP_FRAC:.0%} of travel ({top['median_px']:.2f} px) "
            f"than over the whole clip ({top['whole_px']:.2f} px). Still inside "
            f"tolerance at {top['median_cm']:.2f} cm, so this is a note rather "
            f"than a fault — but the whole-clip figure is not representative of "
            f"this capture and should not be quoted alone.", stacklevel=2)

    try:
        lift = truth.lift_of(video)
    except ValueError:
        return
    for flag in truth.rom_flags(lift, [path["travel_m"]]):
        warnings.warn(f"{name}: {flag.split(': ', 1)[1]} (whole-clip travel).",
                      stacklevel=2)
