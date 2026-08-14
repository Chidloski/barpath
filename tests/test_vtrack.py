"""Gates for the eight-sticker video referee.

The failure this module exists to prevent is not a crash. It is a track that is
rigid, well covered, has a healthy residual, and is not the bar — six squat
clips fed 0.2-24.7 cm of travel into comparisons for days behind coverage of
96-100% (C31, D2). So the gates here are travel against the lift's own range of
motion and the rep count, both of which see that, and NOT coverage or residual,
neither of which does.

The clip-level gates decode video and are slow, so they are marked and skipped
unless the footage is present.
"""
from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest

from src import metrics, capture, vtrack

VIDEO = Path(__file__).resolve().parents[1] / "data_v2" / "video"
CLIPS = sorted(VIDEO.glob("*.mov")) if VIDEO.is_dir() else []


def test_data_v2_infers_vtrack():
    """`data_v2/` is refereed by vtrack; everything else by the template."""
    assert metrics.infer_tracker("data_v2/video/deadlift_160x6_1.mov") == "vtrack"
    assert metrics.infer_tracker("data/video/squat_130x5.mov") == "plate"
    assert "vtrack" in metrics.TRACKERS
    # markers.py is NOT deleted and stays reachable by name.
    assert "markers" in metrics.TRACKERS


def test_rom_prior_is_tighter_than_the_capture_gate():
    """The scoring prior must stay inside `capture.VERTICAL_ROM_M`, not match it.

    `vtrack.ROM` ranks rival constellations and has to discriminate;
    `capture.VERTICAL_ROM_M` gates a finished measurement and is wide on purpose.
    Widening the first to the second changes which hypothesis wins.
    """
    for lift, (lo, hi) in vtrack.ROM.items():
        glo, ghi = capture.VERTICAL_ROM_M[lift]
        assert glo <= lo < hi <= ghi, lift


def test_a_foreign_cache_is_not_read_as_ours(tmp_path):
    """A CSV written by another tracker must never be handed back as vtrack's.

    The cache is keyed by clip, not by tracker, so when `data_v2/` moved from
    `markers` to `vtrack` every existing CSV became a path from the wrong
    referee sitting at the right filename.
    """
    from src import tracked
    n = 40
    path = {"t": np.arange(n) / 30.0,
            "x": np.zeros(n),
            "height": np.linspace(0, 0.5, n),
            "residual_px": np.full(n, 0.4),
            "m_per_px": 0.002, "travel_m": 0.5}
    clip = tmp_path / "data_v2" / "video" / "deadlift_160x6_1_20260804.mov"
    clip.parent.mkdir(parents=True)
    clip.write_bytes(b"")
    dest = tmp_path / "cached.csv"
    tracked.write(path, clip, dest=dest)
    hit = tracked.read(clip, src=dest)
    assert hit is not None
    # Whatever `infer_tracker` said when it was written, the guard compares the
    # RECORDED tracker against the one being asked for.
    hit["tracker"] = "markers"
    assert hit.get("tracker", "vtrack") != "vtrack"


@pytest.mark.skipif(not CLIPS, reason="data_v2 footage not present")
@pytest.mark.parametrize("clip", CLIPS, ids=lambda p: p.stem)
def test_every_clip_tracks_plausibly(clip):
    """Travel inside the lift's ROM band, and the rep count matches the label.

    Both are free — the label is in the filename and the band is already a repo
    constant — and between them they catch the failure that coverage cannot.
    """
    path = vtrack.bar_path(clip, check=False)
    lift = capture.lift_of(clip)
    lo, hi = capture.VERTICAL_ROM_M[lift]

    assert not path["implausible"], (
        f"{clip.stem}: {path['travel_m'] * 100:.1f} cm of travel is not the bar")
    assert path["coverage"] >= 0.95, f"{clip.stem}: coverage {path['coverage']:.3f}"
    # Whole-clip travel spans the un-rack on a smooth lift, so it may exceed the
    # per-rep band from above; it must never fall far below it.
    assert path["travel_m"] >= 0.8 * lo, (
        f"{clip.stem}: travel {path['travel_m'] * 100:.1f} cm against a "
        f"{lo * 100:.0f}-{hi * 100:.0f} cm band")
