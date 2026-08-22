"""The eight-sticker video referee for `data_v2/` footage — the only one left.

Read `path.py`'s docstring first — it says what this is, why `markers.py` was
not enough on this footage, and what was measured. The layout mirrors the
pipeline's own habit of one concern per module:

    detect.py     bright compact blobs, on whiteness rather than brightness
    geom.py       circle/lattice geometry, and the 8-fold symmetry score
    seed.py       which constellation in the clip is the plate — by trial-track
    track.py      follow it frame to frame, re-acquire when the lock is lost
    path.py       `bar_path`, plus the referee's own top-of-travel fit check
    condition.py  reject impossible frames, then smooth (H30) — ON by default
    geometry.py   where along the BAR the tracked point is, and what tilt costs

**`markers.py` was DELETED on 2026-08-19 (H21) and this is now the only tracker
in the repo.** It had been the referee for `data_v2/` until F1's rebuild landed
on 2026-08-14, after which it was reachable only by passing `tracker="markers"`
and was refereeing nothing. Its one live dependency — `top_of_travel_residual`,
which `metrics._video_quality` calls on every scored capture — moved into
`path.py` unchanged. Recover the module itself with

    git show 0e87f28:src/markers.py

and its gates with `git show 0e87f28:tests/test_markers.py`. What it established
is recorded where findings are recorded, not in the code: C15 (stickers beat the
plate template), C21/C23 (seeding by verification), C26 (a conic never asks how
the stickers are spaced), C27 (the eight-sticker gating), C32 (the scale ratio
it could not measure) and D2/C31 (`static_points` suppressing the bar's own
stickers, the failure this package exists to fix). See `TASKS.md` and
`CLAUDE.md`.
"""
from . import condition, geometry
from .condition import anomalies, CONDEMN_FRAC, V_MAX_MS
from .path import (bar_path, track_clip, validate, top_of_travel_residual,
                   ROM, PLATE_M, STICKER_CIRCLE_M, STICKER_RATIO,
                   MAX_TOP_RESIDUAL_CM, TOP_FRAC)

__all__ = ["bar_path", "track_clip", "validate", "top_of_travel_residual",
           "ROM", "PLATE_M", "STICKER_CIRCLE_M", "STICKER_RATIO",
           "MAX_TOP_RESIDUAL_CM", "TOP_FRAC",
           "condition", "geometry", "anomalies", "CONDEMN_FRAC", "V_MAX_MS"]
