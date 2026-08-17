"""The eight-sticker video referee for `data_v2/` footage.

Read `path.py`'s docstring first — it says what this is, why `markers.py` was
not enough on this footage, and what was measured. The layout mirrors the
pipeline's own habit of one concern per module:

    detect.py   bright compact blobs, on whiteness rather than brightness
    geom.py     circle/lattice geometry, and the 8-fold symmetry score
    seed.py     which constellation in the clip is the plate — by trial-track
    track.py    follow it frame to frame, re-acquire when the lock is lost
    path.py     `bar_path`, in `markers.bar_path`'s key set

`markers.py` is untouched and still reachable as `tracker="markers"`.
"""
from .path import (bar_path, track_clip, validate, ROM, PLATE_M,
                   STICKER_CIRCLE_M, STICKER_RATIO)

__all__ = ["bar_path", "track_clip", "validate", "ROM", "PLATE_M",
           "STICKER_CIRCLE_M", "STICKER_RATIO"]
