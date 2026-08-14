"""The IMU reconstruction against the REBUILT video tracking.

Every `beats_null` in `CLAUDE.md` was measured through a referee that has since
been rebuilt, so this re-scores the pipeline against the corrected paths. The
comparison is run through the project's own `metrics.vs_truth` rather than a
private reimplementation, so the numbers here are directly comparable to the
ones already recorded — the only thing that changes is which video path goes in.

`vs_truth` accepts a ready-made path dict, which is the documented way to score
an already-tracked path. So the rebuilt tracker's per-frame output is wrapped in
the key set `markers.bar_path` returns, and nothing in `src/` is touched.

Two limits, both the project's and neither introduced here:

  * `vs_truth` still REFUSES squat, by a hardcoded check whose stated reason
    describes the old `data/video/` template footage. Lifting it is real work
    (squat has no phase anchor, and `bench_sync` is unvalidated on squat), so
    the four squats are reported as tracked-but-unscored rather than forced.
  * step 6 is ON by default, so these are bar-path numbers, not watch-path
    ones. `wrist_offset=None` would reproduce the older figures.
"""
from __future__ import annotations

import sys
import warnings
from pathlib import Path

import numpy as np

import os                                                 # noqa: E402

# Which checkout's `src/` to score with. The audit worktree sits at ae14c40,
# which predates BOTH C31a's segmenter and step 6 being on by default, so a
# comparison run there is a watch-path number scored with the old rep windows.
# Point this at an export of `c29-jump-state` to get the pipeline CLAUDE.md
# describes. `git archive c29-jump-state src | tar -x -C <dir>`.
SRC_ROOT = os.environ.get("BARPATH_SRC_ROOT", "/Users/sam/Desktop/barpath")

sys.path.insert(0, str(Path(__file__).parent))
sys.path.insert(0, f"{SRC_ROOT}/src")
sys.path.insert(0, SRC_ROOT)

import run_all as R                                       # noqa: E402
from src import metrics, pipeline, truth                  # noqa: E402

print(f"# scoring with src/ from {SRC_ROOT}", flush=True)
print(f"# step 6 default: {pipeline.run.__defaults__[0]!r}", flush=True)

RAW = Path("/Users/sam/Desktop/barpath/data_v2/raw")
VIDEO = Path("/Users/sam/Desktop/barpath/data_v2/video")


def as_path_dict(res):
    """The rebuilt tracker's output in `markers.bar_path`'s key set."""
    sm, trk = res["summary"], res["trk"]
    rms = np.array([t["rms"] if t is not None else np.nan for t in trk])
    n = len(sm["t"])
    return {
        "t": sm["t"],
        "x": sm["fore_aft_m"],
        "height": sm["height_m"],
        "residual_px": rms,
        "m_per_px": sm["m_per_px"],
        "m_per_px_t": np.full(n, sm["m_per_px"]),
        "travel_m": sm["travel_m"],
        "fps": 1.0 / float(np.median(np.diff(sm["t"]))),
    }


def main():
    csvs = sorted(RAW.glob("*.csv"))
    print(f"{'capture':30s} {'lift':>8} {'reps':>5} {'h_rms':>7} {'null':>7} "
          f"{'beats':>7} {'v_rms':>7} {'sign':>5} {'vidROM':>7} {'vidFA':>6} "
          f"{'cov':>6}")
    rows = []
    for csv in csvs:
        stem = csv.stem.rsplit("_", 1)[0]
        clip = VIDEO / f"{stem}.mov"
        if not clip.exists():
            print(f"{stem:30s}  no clip")
            continue
        lift = truth.lift_of(stem)
        try:
            trkres = R.run_one(clip)
            path = as_path_dict(trkres)
        except Exception as e:                              # noqa: BLE001
            print(f"{stem:30s}  TRACK {type(e).__name__}: {e}")
            continue
        cov = trkres["summary"]["coverage"]
        if lift == "squat":
            print(f"{stem:30s} {lift:>8} {'-':>5} {'refused by vs_truth':>39} "
                  f"{cov:9.3f}")
            continue
        try:
            with warnings.catch_warnings():
                warnings.simplefilter("ignore")
                res = pipeline.run(csv, video=None)
                vt = metrics.vs_truth(res, path)
        except Exception as e:                              # noqa: BLE001
            print(f"{stem:30s} {lift:>8}  SCORE {type(e).__name__}: {e}")
            continue
        print(f"{stem:30s} {lift:>8} "
              f"{vt['n_compared']:2d}/{vt['n_reps']:<2d} "
              f"{vt['pipeline_h_rms']:7.2f} {vt['null_h_rms']:7.2f} "
              f"{vt['beats_null']:7.2f} {vt['pipeline_v_rms']:7.2f} "
              f"{vt['reps_disagreeing_on_sign']:5d} {vt['video_rom_cm']:7.1f} "
              f"{vt['video_fore_aft_cm']:6.1f} {cov:6.3f}")
        rows.append((stem, lift, vt))
    return rows


if __name__ == "__main__":
    main()
