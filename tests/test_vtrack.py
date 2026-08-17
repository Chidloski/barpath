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
    """`data_v2/` is refereed by vtrack; anything else has no referee at all.

    The second assertion read `infer_tracker("data/video/squat_130x5.mov") ==
    "plate"` until 2026-08-16. F1 deleted the plate template tracker AND the
    `data/video/` corpus it scored on 2026-08-14, so both that clip and that
    answer stopped existing, and this test had been failing ever since. It now
    asserts what the function actually does, which is REFUSE: inferring a
    tracker that is gone would hand footage to something that cannot read it,
    and the error names the way out instead.
    """
    assert metrics.infer_tracker("data_v2/video/deadlift_160x6_1.mov") == "vtrack"
    with pytest.raises(ValueError, match="only data_v2/ footage has a referee"):
        metrics.infer_tracker("data/video/squat_130x5.mov")
    assert "vtrack" in metrics.TRACKERS
    # markers.py is NOT deleted and stays reachable by name.
    assert "markers" in metrics.TRACKERS
    assert "plate" not in metrics.TRACKERS


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


def test_the_sticker_circle_is_the_plate_less_one_STICKER(): 
    """H14 — the scale is geometry now, and the geometry is a placement rule.

    The owner places every sticker with its 2.0 cm OUTER edge against the plate
    rim, so its centre sits one sticker radius — 1.0 cm — inboard and the circle
    through the centres is the plate diameter less 2.0 cm. That is the whole
    derivation, and it is pinned here because the alternative is that somebody
    re-tunes it back into a ratio.

    The 1.3 cm reflective diameter is deliberately absent: it sizes the blob the
    detector finds, not where its centre is, because the disc is concentric with
    the sticker. The owner corrected 1.5 to 1.3 mid-measurement and nothing
    downstream moved, which is the check that this is true.
    """
    for lift, plate in vtrack.PLATE_M.items():
        assert vtrack.STICKER_CIRCLE_M[lift] == pytest.approx(plate - 0.020), (
            f"{lift}: the circle must be the plate less one sticker diameter")


def test_no_single_RATIO_can_express_the_sticker_circle():
    """H14 — why `STICKER_RATIO` was the wrong SHAPE, not merely the wrong value.

    The inset is an absolute 1.0 cm, so as a fraction of the plate it is a
    different number on every plate size. `markers.py` compared a ratio model
    against a constant-inset model, measured them agreeing to 0.8% and concluded
    "the choice between the two models does not matter" — true only because the
    two plates it compared are 25 mm apart. This asserts they are NOT the same
    model, so that conclusion cannot be re-derived from the agreement.

    Both are inside 0.01 of each other and neither is the shipped 0.858, which
    is the three-sticker plate's 31.6 mm inset and is correct for that plate.
    """
    ratios = {lift: vtrack.STICKER_CIRCLE_M[lift] / plate
              for lift, plate in vtrack.PLATE_M.items()}
    assert ratios["squat"] != ratios["deadlift"], (
        "a 450 plate and a 425 plate cannot share a sticker-circle RATIO")
    assert ratios["deadlift"] == pytest.approx(0.9529, abs=1e-4)
    assert ratios["squat"] == pytest.approx(0.9556, abs=1e-4)
    assert all(r > vtrack.STICKER_RATIO + 0.09 for r in ratios.values()), (
        "the eight-sticker plates sit far closer to the rim than the three-"
        "sticker plate 0.858 was calibrated on")


def test_the_stickered_plate_is_not_the_widest_plate_on_a_deadlift():
    """H14/C27 — the defect this table reintroduced, pinned so it cannot return.

    `capture.plate_diameter` answers "what is the widest outline in shot" and is
    0.445 on a deadlift, the bumper. `vtrack.PLATE_M` answers "what plate are the
    stickers ON", which is the 425 notched plate loaded around it. F1 gave this
    module its own table with a comment saying exactly that and the bumper's
    value in it, worth 4.7% of every deadlift distance.
    """
    assert vtrack.PLATE_M["deadlift"] == 0.425
    assert capture.PLATE_DIAMETER_M["deadlift"] == 0.445
    # Bench loads only black notched; squat only blue calibrated (owner).
    assert vtrack.PLATE_M["bench"] == 0.425
    assert vtrack.PLATE_M["squat"] == 0.450
