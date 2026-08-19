"""H25 — C11's closure identity, run on the HORIZONTAL axis for the first time.

THE IDENTITY. Between two instants where the bar is known to be still, the
integral of its acceleration must be zero — on EVERY axis, not only the
vertical. Nothing tunable, no model of lifting, no distance the video has to
measure correctly: a scale error cannot move a zero crossing, so the video is
used only to say WHEN the bar was still.

C11 ran this on the VERTICAL and localised the deficit entirely to the floor
landing: deadlift pulls -0.010 m/s against -0.589 across a landing, with bench
at -0.013 as an independent control. **Nobody ran it on the axis the project
actually fails on**, and the owner's question is exactly that — does the
horizontal error stem from the impact, or is it there throughout?

**C11'S SHAPE REPRODUCES ON THE LIVE CORPUS; ITS MAGNITUDE DOES NOT.** C11 was
measured on the v1 captures F1 deleted on 2026-08-14, so its numbers are history
and cannot be re-derived. Re-run today through the SHIPPED
`metrics.momentum_closure` — which the vertical panel here reproduces exactly,
n = 15 and 24, medians -0.046 and -0.126 — deadlift landing intervals still lose
vertical impulse, still consistently, and still at a multiple of the pulls
(2.7x). But the deficit is **-0.126 m/s, not -0.589**. The qualitative finding
stands; do not quote the old magnitude against these captures.

The within-capture control is C11's: the dwell detector splits a deadlift rep at
the lockout, so the pull and the descent-plus-landing are separate intervals of
the same tape, same lift, same load, same wrist, same calibration.

THE ANSWER, and it is not the vertical's answer.

    interval class                    n   |dv_h| med   mean |a_h| error   implied tilt
    deadlift, PULL only              15     0.144 m/s     0.059 m/s^2        0.34 deg
    deadlift, interval WITH impact   24     0.256         0.102             0.60
    bench, lifting                   59     0.031         0.021             0.12
    squat, lifting                   35     0.070         0.023             0.13

**The impact roughly DOUBLES the horizontal error and does not create it.** On
the vertical the same split gives a 59x ratio between the two deadlift rows —
the landing is the whole story there. On the horizontal it is 1.8x, and a
deadlift PULL with no impact anywhere in it already carries 2-3x bench's error.

**What the other half is: gravity leaking through attitude error.** World
horizontal acceleration is R(t)*a_body with gravity removed, so a tilt error of
theta leaks g*sin(theta) into the horizontal — against only g*(1-cos theta) into
the vertical, which is why the same attitude error is catastrophic on one axis
and invisible on the other. The implied tilts above are what each row's error
would need, and they are the right size: **C6 measured attitude error at still
holds as 0.05-0.14 deg on bench and squat**, and this measurement — completely
independent, on a different quantity — asks for 0.12-0.13 deg on those lifts.

Why it dominates: gravity is 9.81 m/s^2 and the bar's real horizontal
acceleration is 0.13-0.21. A third of a degree of tilt is a third of the entire
signal.

Excluded by hand: `deadlift_160x6_1_20260818` (straps, H20).
"""
import sys
import warnings
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
warnings.filterwarnings("ignore")

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from scipy.signal import savgol_filter

from src import metrics, orient, pipeline, segment

EXCLUDE = ("deadlift_160x6_1_20260818",)
BAR_REAL_AH = (0.13, 0.21)      # C30: the bar's own horizontal accel, m/s^2
G = 9.81


def collect():
    rows = []
    for csv in sorted((ROOT / "data_v2" / "raw").glob("*.csv")):
        if any(e in csv.stem for e in EXCLUDE):
            continue
        video = pipeline.find_video(csv)
        if video is None:
            continue
        try:
            res = pipeline.run(csv, video=video)
            if res.get("vs_truth") is None or res.get("axis") is None:
                continue
            log = res["log"]
            t = log["t"]
            world = orient.to_world(log["accel"], log["quat"], log["quat"])
            a_h = world[:, :2] @ np.asarray(res["axis"], float)[:2]
            a_v = world[:, 2]
            t_imu, _, height, _ = metrics._video_on_imu_clock(res, video, None)
            v_video = np.gradient(savgol_filter(height, 9, 3), t_imu)
            bounds = res["bounds"]
            lo, hi = float(t[bounds[0][0]]), float(t[bounds[-1][1] - 1])
            mids = metrics._video_zero_dwells(t_imu, v_video, 0.10, 0.20)
            mids = mids[(mids >= lo - 0.5) & (mids <= hi + 0.5)]
            if len(mids) < 2:
                continue
            idx = [int(np.searchsorted(t, m)) for m in mids]
            impacts = list(segment.impact_anchors(log))
            lift = csv.stem.split("_")[0]
            for a, b in zip(idx[:-1], idx[1:]):
                if b - a < 10:
                    continue
                rows.append({
                    "lift": lift,
                    "spans": any(a <= k <= b for k in impacts),
                    "dv_h": float(np.trapezoid(a_h[a:b], t[a:b])),
                    "dv_v": float(np.trapezoid(a_v[a:b], t[a:b])),
                    "dur": float(t[b] - t[a])})
        except Exception:
            continue
    return rows


CLASSES = [
    ("deadlift\nPULL only", lambda r: r["lift"] == "deadlift" and not r["spans"], "#f39c12"),
    ("deadlift\nWITH impact", lambda r: r["lift"] == "deadlift" and r["spans"], "#c0392b"),
    ("bench", lambda r: r["lift"] == "bench", "#3498db"),
    ("squat", lambda r: r["lift"] == "squat", "#27ae60"),
]


def render(rows):
    fig, axes = plt.subplots(1, 3, figsize=(16.5, 6.2))
    groups = [[r for r in rows if f(r)] for _, f, _ in CLASSES]
    names = [n for n, _, _ in CLASSES]
    cols = [c for _, _, c in CLASSES]

    ax = axes[0]
    for i, (g, c) in enumerate(zip(groups, cols)):
        v = np.abs([r["dv_h"] for r in g])
        ax.scatter(np.full(len(v), i) + np.random.uniform(-.13, .13, len(v)),
                   v, s=34, color=c, alpha=0.7, zorder=3)
        ax.hlines(np.median(v), i - .3, i + .3, color="#2c3e50", lw=2.6, zorder=4)
    ax.set_xticks(range(4))
    ax.set_xticklabels(names, fontsize=9)
    ax.set_ylabel("|horizontal velocity the bar did NOT have|, m/s")
    ax.set_title("A · The identity, on the HORIZONTAL.\n"
                 "The impact DOUBLES it (0.144 -> 0.256) — it does not create "
                 "it.", fontsize=11, loc="left")
    ax.grid(alpha=0.25, axis="y")

    ax = axes[1]
    for i, (g, c) in enumerate(zip(groups, cols)):
        v = np.abs([r["dv_v"] for r in g])
        ax.scatter(np.full(len(v), i) + np.random.uniform(-.13, .13, len(v)),
                   v, s=34, color=c, alpha=0.7, zorder=3)
        ax.hlines(np.median(v), i - .3, i + .3, color="#2c3e50", lw=2.6, zorder=4)
    ax.set_xticks(range(4))
    ax.set_xticklabels(names, fontsize=9)
    ax.set_ylabel("|vertical impulse lost|, m/s")
    ax.set_title("B · The SAME intervals, vertical — C11's SHAPE, on today's "
                 "corpus.\nThe landing still dominates (2.7x the pulls). C11's "
                 "-0.589 was v1,\nnow deleted; this is -0.126 and reproduces "
                 "`momentum_closure` exactly.", fontsize=11, loc="left")
    ax.grid(alpha=0.25, axis="y")

    ax = axes[2]
    for i, (g, c, n) in enumerate(zip(groups, cols, names)):
        err = np.median([abs(r["dv_h"]) / r["dur"] for r in g])
        ax.bar(i, err, color=c, width=0.62, zorder=3)
        ax.text(i, err + 0.003, f"{np.degrees(np.arcsin(err / G)):.2f}°",
                ha="center", fontsize=10, fontweight="bold", color=c)
    ax.axhspan(*BAR_REAL_AH, color="#7f8c8d", alpha=0.18, zorder=0)
    ax.text(-0.45, BAR_REAL_AH[1] + 0.004,
            "the bar's REAL horizontal acceleration", fontsize=8.5,
            color="#566573")
    ax.set_xticks(range(4))
    ax.set_xticklabels(names, fontsize=9)
    ax.set_ylabel("mean horizontal acceleration ERROR, m/s²")
    ax.set_title("C · Why it is fatal here and nowhere else.\n"
                 "Labels are the ATTITUDE TILT that would leak this much "
                 "gravity.\nC6 measured 0.05–0.14° independently.",
                 fontsize=11, loc="left")
    ax.grid(alpha=0.25, axis="y")

    fig.suptitle("H25 · Where the horizontal acceleration error comes from — "
                 "about half the impact, about half gravity leaking through "
                 "attitude", fontsize=13.5, y=1.005)
    fig.tight_layout()
    out = Path(__file__).with_suffix(".png")
    fig.savefig(out, dpi=125, bbox_inches="tight")
    print(f"wrote {out}")

    print(f"\n{'class':26}{'n':>4}{'|dv_h| med':>12}{'|a_h| err':>11}{'tilt deg':>10}")
    for (n, _, _), g in zip(CLASSES, groups):
        v = np.abs([r["dv_h"] for r in g])
        e = np.median([abs(r["dv_h"]) / r["dur"] for r in g])
        print(f"{n.replace(chr(10), ' '):26}{len(g):4}{np.median(v):12.3f}"
              f"{e:11.4f}{np.degrees(np.arcsin(e / G)):10.2f}")


if __name__ == "__main__":
    np.random.seed(0)
    render(collect())
