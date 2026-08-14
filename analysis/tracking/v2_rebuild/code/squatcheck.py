"""Squat against the rebuilt referee — INDICATIVE ONLY, not a result.

`metrics.vs_truth` refuses squat outright. Its stated reason — median NCC ~0.40,
the plate clipping frame at lockout, two of four captures not tracking — is a
description of the OLD `data/video/` template footage. It does not describe
`data_v2/`, where all four squats now track at 1.000 coverage with eight filled
slots. So the refusal is stale, and CLAUDE.md says so.

Stale is not the same as safe to lift, and this script does NOT lift it. It
patches `truth.lift_of` in-process so a squat routes through the bench branch,
which is exactly C31's exploratory bypass, and everything it prints inherits
three unresolved problems:

  * `bench_sync` is UNVALIDATED on squat. It is a vertical cross-correlation
    calibrated against deadlift and merely not contradicted on bench. Nothing
    here tests it on a squat, and a squat's walkout gives the correlation a
    large non-rep feature that a bench does not have.
  * Squat has NO PHASE ANCHOR (P1). Bench windows were verified in phase by
    video chest touches and deadlift by floor impacts; squat has neither, so a
    window half a rep out of step would be invisible to every number below.
  * Video ROM reads 57.5-58.1 cm against the IMU's 66-69 (C31). The two
    instruments disagree by ~15% on the vertical before any of this starts.

Patching `lift_of` also makes `truth.rom_flags` score a 60 cm squat against
bench's 24-31 cm band, so `video_rom_flags` is meaningless here and is not
printed.
"""
from __future__ import annotations

import sys
import warnings
from pathlib import Path

import numpy as np

import os                                                 # noqa: E402

SRC_ROOT = os.environ.get("BARPATH_SRC_ROOT", "/Users/sam/Desktop/barpath")

sys.path.insert(0, str(Path(__file__).parent))
sys.path.insert(0, f"{SRC_ROOT}/src")
sys.path.insert(0, SRC_ROOT)

import run_all as R                                       # noqa: E402
from src import metrics, pipeline, truth                  # noqa: E402
from vspipe import as_path_dict                           # noqa: E402

RAW = Path("/Users/sam/Desktop/barpath/data_v2/raw")
VIDEO = Path("/Users/sam/Desktop/barpath/data_v2/video")

_real_lift_of = truth.lift_of


def _as_bench(name):
    """Route squat down the bench branch; leave every other lift alone."""
    lift = _real_lift_of(name)
    return "bench" if lift == "squat" else lift


def main():
    print("INDICATIVE ONLY — bench_sync is unvalidated on squat and squat has "
          "no phase anchor.\n")
    print(f"{'capture':30s} {'reps':>6} {'h_rms':>7} {'null':>7} {'beats':>7} "
          f"{'v_rms':>7} {'sign':>5} {'vidROM':>7} {'imuROM':>7} {'vidFA':>6}")
    truth.lift_of = _as_bench
    try:
        for csv in sorted(RAW.glob("squat*.csv")):
            stem = csv.stem.rsplit("_", 1)[0]
            clip = VIDEO / f"{stem}.mov"
            if not clip.exists():
                print(f"{stem:30s}  no clip")
                continue
            try:
                trkres = R.run_one(clip)
                path = as_path_dict(trkres)
                with warnings.catch_warnings():
                    warnings.simplefilter("ignore")
                    res = pipeline.run(csv, video=None)
                    vt = metrics.vs_truth(res, path)
            except Exception as e:                          # noqa: BLE001
                print(f"{stem:30s}  REFUSED {type(e).__name__}: {e}")
                continue
            # The IMU's own per-rep vertical range, for the disagreement that
            # C31 measured and that no sync can explain away.
            imu_rom = np.median([float(r[:, 2].max() - r[:, 2].min())
                                 for r in res["reps"]]) * 100
            print(f"{stem:30s} {vt['n_compared']:2d}/{vt['n_reps']:<3d} "
                  f"{vt['pipeline_h_rms']:7.2f} {vt['null_h_rms']:7.2f} "
                  f"{vt['beats_null']:7.2f} {vt['pipeline_v_rms']:7.2f} "
                  f"{vt['reps_disagreeing_on_sign']:5d} "
                  f"{vt['video_rom_cm']:7.1f} {imu_rom:7.1f} "
                  f"{vt['video_fore_aft_cm']:6.1f}")
    finally:
        truth.lift_of = _real_lift_of


if __name__ == "__main__":
    main()
