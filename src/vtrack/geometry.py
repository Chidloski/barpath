"""Where along the bar the referee is actually looking, and what that costs.

The tracker measures the centre of the eight-sticker circle. That circle is on
the outer face of one plate near one end of the bar, so the point being
refereed is not the bar's centre — it is a point on the bar AXIS, offset
axially by `marker_plane_m`.

**THE CONSEQUENCE IS SMALLER THAN IT LOOKS, AND SAYING WHY IS THE POINT OF THIS
MODULE.** An axial offset is along the bar. The two quantities the referee
reports — height, and fore-aft — are both PERPENDICULAR to the bar. So for a
bar that is level, the sticker-circle centre and the bar centre have exactly
the same height and exactly the same fore-aft position, and no conversion is
needed at all. The entire difference between "the path at the plate" and "the
path at the bar centre" is the TILT term:

    error at the bar centre  =  L * sin(theta)

with `L = marker_plane_m(lift, kg)` and `theta` the bar's tilt out of level, in
the plane concerned. Converting to the bar centre is therefore not a geometry
problem — the geometry here is three lines — it is entirely the problem of
measuring `theta`. See `analysis/79_endcap_parallax.py` for what that costs on
this footage, and the caveat below.

    lift/load          L (m)    a (m)   L/a
    bench 92.5         0.735    0.365   2.01
    bench 117.5        0.785    0.315   2.49
    squat 140-170      0.745    0.355   2.10
    deadlift 150-160   0.865    0.235   3.68
    deadlift 185-210   0.915    0.185   4.95

`a = BAR_HALF_M - L` is the axial baseline from the sticker plane to the sleeve
endcap, which is the only other marked point on the bar and therefore the only
available tilt sensor. `L/a` is what it costs: the lever from the sticker plane
to the bar centre is 2 to 5 times the baseline the tilt is measured over, so
**every millimetre of error in locating the endcap marker becomes 2 to 5 mm of
error at the bar centre.** That ratio, not the tracking, is what decides whether
a tilt correction can meet the 1 cm spec.

WHAT IS MEASURED AND WHAT IS ASSUMED
------------------------------------
Measured (owner, 2026-08-22, by tape at the gym pending): bar 2200 mm overall,
415 mm sleeve. Plate thicknesses black bumper 80, black notched 50, blue
calibrated 20 mm — **the owner's word is "approximate" and they are the
dominant uncertainty in `L`.** A 5 mm error in the notched thickness moves a
three-plate deadlift's `L` by 10 mm, which is 1.2%; the same error moves `a` by
10 mm on a 185 mm baseline, which is 5.4%. So the thicknesses matter far more
for the tilt SENSITIVITY than for the lever.

Assumed, and it is the one assumption worth stating because a frame appears to
contradict it: **plates seat against the sleeve shoulder, not against the
collar.** Looking down the bar axis the sleeve appears to protrude only a few
centimetres past the outermost plate, which would put the stack at the far end
of the sleeve. That reading is foreshortening — the camera looks almost exactly
along the sleeve, so 21 cm of bare sleeve projects to nearly nothing. Plates are
loaded inward until they butt against the shoulder, which is how a barbell
works, and `L` is computed on that basis. If the owner's tape says otherwise,
`SHOULDER_M` is the one number to change.
"""
from __future__ import annotations

# Bar, in metres (owner, 2026-08-22).
BAR_LENGTH_M = 2.200
SLEEVE_M = 0.415
BAR_MASS_KG = 20.0

BAR_HALF_M = BAR_LENGTH_M / 2.0                 # centre to the sleeve end
SHOULDER_M = BAR_HALF_M - SLEEVE_M              # centre to where plates seat

# Plate thickness in metres, by type (owner, 2026-08-22, APPROXIMATE).
PLATE_THICKNESS_M = {
    "black_bumper": 0.080,
    "black_notched": 0.050,
    "blue_calibrated": 0.020,
}

# Which plate a lift loads, innermost first. A deadlift takes a single black
# bumper against the shoulder and black notched outside it; bench is notched
# throughout; squat is blue calibrated throughout (owner, 2026-08-22).
LIFT_PLATES = {
    "deadlift": ("black_bumper", "black_notched"),
    "bench": ("black_notched",),
    "squat": ("blue_calibrated",),
}

# The plate the markers are on. Always the OUTERMOST plate of this mass, with
# the bar loaded heaviest-inward.
MARKER_PLATE_KG = 20.0

# Denominations available per side, heaviest first — "loaded optimally".
DENOMINATIONS_KG = (20.0, 15.0, 10.0, 5.0, 2.5, 1.25)


def per_side_kg(total_kg: float, bar_kg: float = BAR_MASS_KG) -> float:
    """Plate mass on one sleeve."""
    return (float(total_kg) - bar_kg) / 2.0


def stack(total_kg: float, bar_kg: float = BAR_MASS_KG) -> list[float]:
    """Plate masses on one sleeve, innermost first, loaded heaviest-inward.

    Greedy over `DENOMINATIONS_KG`, which is what "loaded optimally" means on a
    rack that holds all of them: the fewest plates, biggest inside. Returns []
    for a bare bar and ignores any remainder it cannot make, which only happens
    for loads this corpus does not contain.
    """
    left = per_side_kg(total_kg, bar_kg)
    out: list[float] = []
    for d in DENOMINATIONS_KG:
        while left >= d - 1e-9:
            out.append(d)
            left -= d
    return out


def n_marker_plates(total_kg: float, bar_kg: float = BAR_MASS_KG) -> int:
    """How many 20 kg plates sit on one sleeve — the markers are on the last."""
    return sum(1 for m in stack(total_kg, bar_kg) if abs(m - MARKER_PLATE_KG) < 1e-9)


def marker_plane_m(lift: str, total_kg: float,
                   bar_kg: float = BAR_MASS_KG) -> float:
    """`L`: bar centre to the OUTER FACE of the outermost 20 kg plate, metres.

    The markers sit on that face, so this is the axial position of the point
    the referee tracks. Only the 20 kg plates enter — anything smaller is
    loaded outboard of the markers and cannot move them.
    """
    seq = LIFT_PLATES[lift]
    n = n_marker_plates(total_kg, bar_kg)
    if n == 0:
        raise ValueError(
            f"{lift} at {total_kg} kg carries no 20 kg plate per side, so there "
            f"is no plate for the markers to be on")
    total = 0.0
    for i in range(n):
        kind = seq[min(i, len(seq) - 1)]
        total += PLATE_THICKNESS_M[kind]
    return SHOULDER_M + total


def endcap_baseline_m(lift: str, total_kg: float,
                      bar_kg: float = BAR_MASS_KG) -> float:
    """`a`: sticker plane to the sleeve endcap, metres. The tilt baseline."""
    return BAR_HALF_M - marker_plane_m(lift, total_kg, bar_kg)


def lever_ratio(lift: str, total_kg: float, bar_kg: float = BAR_MASS_KG) -> float:
    """`L/a` — how much an endcap position error is magnified at the bar centre.

    This is the number that decides feasibility. An endcap marker located to
    within `e` metres yields a bar-centre correction good to `e * L/a`, so on a
    deadlift at 210 kg a 1 mm endcap error is a 5 mm bar-centre error, before
    any error in `L` itself.
    """
    return marker_plane_m(lift, total_kg, bar_kg) / endcap_baseline_m(
        lift, total_kg, bar_kg)


def centre_error_m(lift: str, total_kg: float, tilt_rad: float,
                   bar_kg: float = BAR_MASS_KG) -> float:
    """How far the tracked point sits from the bar centre, for a given tilt.

    `L * sin(theta)`, in the plane the tilt is measured in. Positive means the
    tracked end is HIGHER than the bar centre (for a tilt measured as the
    tracked end rising).
    """
    import math

    return marker_plane_m(lift, total_kg, bar_kg) * math.sin(tilt_rad)


def bar_centre_path(path: dict, lift: str, total_kg: float,
                    tilt_rad, bar_kg: float = BAR_MASS_KG) -> dict:
    """Shift a tracked path from the sticker plane to the bar centre.

    `tilt_rad` is per-frame bar tilt in the vertical plane containing the bar,
    signed so that positive raises the tracked end. Subtracting `L*sin(theta)`
    from `height` is the whole conversion; `x` is untouched, because a tilt in
    the vertical plane does not move the bar centre fore-aft.

    **Nothing in `src/` calls this, and that is deliberate as of 2026-08-22
    (H30): no estimator of `tilt_rad` on this footage is good enough to use.**
    See `analysis/79_endcap_parallax.py` — the only available tilt sensor is the
    endcap marker, its residual after a quadratic perspective model is 2.0-2.7
    px, and `lever_ratio` turns that into 1.1-1.7 cm at the bar centre against a
    ~1 cm spec. Worse, that residual is still SHRINKING as the perspective model
    improves, so it bounds tilt rather than measuring it, and a correction built
    on it would be fitting the model's own error into the bar path. The function
    is here so the conversion is written down and testable the day a real tilt
    estimate exists, not because one does.
    """
    import numpy as np

    out = dict(path)
    L = marker_plane_m(lift, total_kg, bar_kg)
    out["height"] = np.asarray(path["height"], float) - L * np.sin(
        np.asarray(tilt_rad, float))
    out["bar_centre"] = True
    out["marker_plane_m"] = L
    return out
