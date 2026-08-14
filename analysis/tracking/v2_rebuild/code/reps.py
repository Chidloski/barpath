"""Does the tracked path contain the reps the filename says it does?

Whole-clip travel is a weak gate: it is one number and a track can lose whole
reps while keeping it — `deadlift_160x6_1` reported 54.0 cm, inside the band,
from a trace holding **four** of its six reps, because the missing two were
dropouts between two surviving lockouts and the extremes were untouched.

The rep count is the gate that sees that, and it is free: every capture is
labelled in its own filename. This is the video-side twin of the segmenter's
count gate, and it needs no IMU, no sync and no referee.

Counting is deliberately crude — peaks in the height trace, separated by at
least a second, prominent against the lift's own range of motion. A crude
counter that is right is worth more here than a tuned one, because the failures
it must catch are whole reps missing, not boundaries being a few frames out.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

import numpy as np
from scipy import ndimage, signal

sys.path.insert(0, str(Path(__file__).parent))
import run_all as R

VIDEO = Path("/Users/sam/Desktop/barpath/data_v2/video")


def labelled_reps(name):
    """`deadlift_160x6_1_20260804` -> 6.  `squat_170x1_20260806` -> 1."""
    m = re.search(r"_[\d.]+x(\d+)", name)
    return int(m.group(1)) if m else None


def count_peaks(sm, rom_lo, lift, fps=30.0):
    """Count reps in the height trace: peaks on a deadlift, troughs otherwise.

    The sign is not cosmetic. A deadlift starts on the floor, so each rep is a
    peak; a bench or a squat starts at the top, so each rep is a DIP and the
    peaks are the rests BETWEEN reps. Counting peaks on a bench therefore gives
    exactly one fewer than the truth, which is what the first run of this gate
    showed on all six smooth captures — 6->5, 5->4, 5->4, 4->3, 4->3, 1->0.
    That clean off-by-one was the counter being wrong, and it doubles as
    evidence the traces held the right number of reps all along.
    """
    h = sm["height_m"].copy()
    ok = ~np.isnan(h)
    if ok.sum() < 10:
        return 0, np.array([])
    # Fill gaps so a dropout cannot manufacture or hide a rep, then smooth
    # over a third of a second.
    idx = np.arange(len(h))
    h = np.interp(idx, idx[ok], h[ok])
    h = ndimage.uniform_filter1d(h, int(round(fps / 3)))
    if lift != "deadlift":
        h = -h
    pk, _props = signal.find_peaks(h, prominence=0.45 * rom_lo,
                                   distance=int(round(fps * 1.0)))
    return len(pk), pk


def main(names):
    print(f"{'capture':32s} {'said':>5} {'found':>6} {'cov':>6} "
          f"{'travel':>7}  verdict")
    bad = 0
    for n in names:
        lift = R.lift_of(n)
        lo, _hi = R.ROM[lift]
        res = R.run_one(VIDEO / f"{n}.mov")
        if not res["ok"]:
            print(f"{n:32s}  {res['reason']}")
            bad += 1
            continue
        sm = res["summary"]
        said = labelled_reps(n)
        got, _pk = count_peaks(sm, lo, lift)
        v = "ok" if said == got else "MISMATCH"
        bad += said != got
        print(f"{n:32s} {said!s:>5} {got:6d} {sm['coverage']:6.3f} "
              f"{sm['travel_m']*100:7.1f}  {v}")
    print(f"\n{len(names) - bad} of {len(names)} captures count correctly")


if __name__ == "__main__":
    names = sys.argv[1:] or sorted(p.stem for p in VIDEO.glob("*.mov"))
    main(names)
