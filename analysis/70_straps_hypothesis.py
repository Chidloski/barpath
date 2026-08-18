"""H20 — the owner's straps hypothesis for `deadlift_160x6_1_20260818`.

H19 recorded that this capture reconstructs at 14.91 cm horizontal, the worst in
the corpus, where the SAME lift, load and rep count on 2026-08-04 gives 1.97 —
a 7.6x difference on a clean track, and it called that unexplained. The owner
then supplied a fact no measurement in this repo could have produced: **he wore
lifting straps for it, which put the watch further up the forearm and may have
let it move around more.**

**STRAPS ARE A PER-CAPTURE FACT, NOT A SESSION ONE (owner, correcting an earlier
version of this file).** `deadlift_160x6_1_20260818` is the ONLY strapped
deadlift in the corpus. `deadlift_190x3_20260818` was filmed the same day, on
the same rig, WITHOUT straps — which makes it a within-day control rather than a
second strapped capture, and makes this comparison much stronger than the
session-level one first drawn here. Its own elevated 7.22 cm is NOT explained by
straps and is left open below.

That is two mechanisms, not one, and they make different predictions.

  GEOMETRY   a watch further up the arm has a LONGER lever `d`, and sits ROLLED
             about the arm because a forearm is tapered. Both are fixed
             transforms of a path that is otherwise fine.
  LOOSENESS  a watch that slides is no longer rigidly indexed to the wrist, so
             it experiences accelerations the bar never did. That MANUFACTURES
             fore-aft travel.

Five panels, and the last one is the discriminator. Run with --cache to
re-render from `70_straps_hypothesis.json` without recomputing.

VERDICT: the session-level claim replicates and LOOSENESS is what carries it.
Geometry is falsified twice over.
"""
import json
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
from scipy.spatial.transform import Rotation

from src import capture, correct, io as bio, metrics, pipeline, project, segment

CACHE = Path(__file__).with_suffix(".json")
STRAPPED = "deadlift_160x6_1_20260818_123507"     # the ONLY strapped capture
SAME_DAY_CONTROL = "deadlift_190x3_20260818_122535"   # same day, same rig, NO straps
DELTAS = [-0.03, 0.0, 0.03, 0.06, 0.10, 0.15]
ANGLES = list(range(-70, 111, 5))
TWIN_A = "deadlift_160x6_1_20260804_104711"
TWIN_B = "deadlift_160x6_1_20260818_123507"
# vtrack's per-rep video fore-aft, replicating C27 on all six deadlifts
VIDEO_FORE_AFT_CM = (4.4, 6.0)
# Independently known bad BEFORE this analysis, so they cannot referee it:
# `170x4_3` is scored through a clock fitting 22.8% drift (G3), and `210x1`
# miscounts a labelled single into two windows, neither in band (H15).
KNOWN_BAD = ("deadlift_170x4_3_20260808_122936", "deadlift_210x1_20260815_132206")


def horizontal_spread(xy):
    """Largest range over ANY in-plane direction — invariant to the display axis.

    This is the panel-E measurement and the reason it can separate the two
    mechanisms: rotating the axis redistributes signal between the two
    horizontal components and leaves this untouched.
    """
    best = 0.0
    for a in np.arange(0, np.pi, np.pi / 90):
        p = xy @ np.array([np.cos(a), np.sin(a)])
        best = max(best, float(p.max() - p.min()))
    return best


def principal(v):
    M = v.T @ v / max(len(v), 1)
    w, V = np.linalg.eigh(M)
    return V[:, -1], float(w[-1] / max(w.sum(), 1e-12))


def compute():
    out = {}
    base_d = correct.WRIST_OFFSET_M["deadlift"]
    for csv in sorted((ROOT / "data_v2" / "raw").glob("deadlift_*.csv")):
        stem = csv.stem
        video = pipeline.find_video(csv)
        row = {"date": stem.split("_")[-2]}
        res = pipeline.run(csv, video=video)

        vs = res.get("vs_truth")
        row["ship_h"] = None if vs is None else vs["pipeline_h_rms"]
        row["ship_bn"] = None if vs is None else vs["beats_null"]

        # E — axis-free per-rep horizontal spread
        row["spread"] = [horizontal_spread(np.asarray(rp, float)[:, :2]
                                           - np.asarray(rp, float)[:, :2].mean(0))
                         * 100 for rp in (res.get("reps") or [])
                         if len(np.asarray(rp)) > 4]

        # F — the same phenomenon with NO video in it: how fast the raw,
        # pre-detrend double integration runs away, rep by rep.
        pos = res.get("position")
        row["raw_spread"] = []
        if pos is not None:
            for a, b in (res.get("bounds") or []):
                xy = np.asarray(pos, float)[a:b, :2]
                if len(xy) > 4:
                    row["raw_spread"].append(
                        horizontal_spread(xy - xy.mean(axis=0)) * 100)

        # D — bar angle straight off the gyro, no video anywhere in it
        log = bio.load_log(csv)
        t, quat, gyro = log["t"], log["quat"], log["gyro"]
        bounds = res.get("bounds") or []
        inside = np.zeros(len(t), bool)
        for a, b in bounds:
            inside[a:b] = True
        if inside.any():
            mag = np.linalg.norm(gyro, axis=1)
            use = inside & (mag > np.percentile(mag[inside], 60))
            u, _ = principal(gyro[use])
            gs = []
            for a in np.atleast_1d(segment.impact_anchors(log)):
                ta = t[a] if np.issubdtype(type(a), np.integer) else float(a)
                w = (t > ta + 0.35) & (t < ta + 0.75)
                if w.sum() >= 5:
                    q = quat[w]
                    R = Rotation.from_quat(np.c_[q[:, 1], q[:, 2], q[:, 3], q[:, 0]])
                    gs.append(R.inv().apply(
                        np.tile([0, 0, -1.0], (len(q), 1))).mean(axis=0))
            if gs:
                g = np.mean(gs, axis=0)
                g /= np.linalg.norm(g)
                fa = np.cross(u, g)
                if np.linalg.norm(fa) > 1e-6:
                    fa /= np.linalg.norm(fa)
                    ang = np.degrees(np.arctan2(fa[1], fa[2]))
                    row["gyro_angle"] = float((ang + 90) % 180 - 90)
                    # |u.g| -> 1 is the DEGENERATE case: the bar axis has
                    # collapsed onto the forearm axis and the cross product
                    # that defines fore-aft is ill-conditioned.
                    row["u_dot_g"] = float(abs(np.dot(u, g)))

        if vs is not None:
            # B — lever-arm length: push the watch toward the elbow
            row["lever"] = {}
            for delta in DELTAS:
                d = base_d + np.array([-delta, 0.0, 0.0])
                try:
                    m = pipeline.run(csv, video=video, wrist_offset=d)["vs_truth"]
                    row["lever"][f"{delta:+.2f}"] = m["pipeline_h_rms"]
                except Exception:
                    pass
            # C — roll about the forearm, i.e. BAR_ANGLE_DEG itself
            row["angle"] = {}
            lift = capture.lift_of(csv)
            for ang in ANGLES:
                try:
                    ax = project.anatomical_axis(quat, bounds,
                                                 angle_deg=float(ang), lift=lift)
                    r2 = dict(res)
                    r2["axis"] = ax
                    r2["planar"] = project.project_to_plane(res["reps"], ax)
                    m = metrics.vs_truth(r2, video)
                    row["angle"][str(ang)] = {"h": m["pipeline_h_rms"],
                                              "bn": m["beats_null"]}
                except Exception:
                    pass
        out[stem] = row
        print(f"  {stem[:40]:42} h={row['ship_h']}", flush=True)
    CACHE.write_text(json.dumps(out, indent=1))
    return out


def short(k):
    """Two captures share the stem `deadlift_160x6_1`, so keep the date."""
    name = k.replace("deadlift_", "").split("_2026")[0]
    return f"{name} {k.split('_2026')[1][:4]}"


def render(data):
    fig = plt.figure(figsize=(15.0, 16.0))
    gs = fig.add_gridspec(3, 2, height_ratios=[1.0, 1.0, 1.08],
                          hspace=0.46, wspace=0.24)

    def colour(k):
        if k == STRAPPED:
            return "#c0392b"
        return "#e67e22" if k == SAME_DAY_CONTROL else "#34495e"

    # ---- A: straps are a per-CAPTURE fact --------------------------------
    ax = fig.add_subplot(gs[0, 0])
    keys = [k for k in data if data[k]["ship_h"] is not None]
    keys.sort(key=lambda k: data[k]["ship_h"])
    for i, k in enumerate(keys):
        ax.barh(i, data[k]["ship_h"], color=colour(k),
                height=0.66, zorder=3)
    ax.set_yticks(range(len(keys)))
    ax.set_yticklabels([short(k) for k in keys], fontsize=8)
    ax.axvspan(1.7, 3.95, color="#27ae60", alpha=0.10, zorder=0)
    ax.set_xlabel("horizontal rms vs video, cm")
    ax.set_title("A · One capture was strapped, not one session.\n"
                 "red = STRAPPED · orange = same day, same rig, NO straps "
                 "(the control)", fontsize=11, loc="left")
    ax.grid(alpha=0.25, axis="x")

    # ---- F: the same story with NO video in it ---------------------------
    ax = fig.add_subplot(gs[0, 1])
    for k, r in data.items():
        rs = r.get("raw_spread")
        if not rs:
            continue
        lead = k in (STRAPPED, SAME_DAY_CONTROL)
        ax.plot(range(1, len(rs) + 1), rs, marker="o", ms=4,
                color=colour(k), lw=2.6 if lead else 1.2,
                zorder=3 if lead else 1,
                label=short(k) if lead or k.startswith("deadlift_160x6_1_2026080")
                else None)
    ax.set_yscale("log")
    ax.set_xlabel("rep number")
    ax.set_ylabel("RAW pre-detrend horizontal spread, cm")
    ax.legend(fontsize=8)
    ax.set_title("F · Video-free corroboration: the raw integration runs away.\n"
                 "The strapped set reaches 2744 cm; its own unstrapped twin, "
                 "same reps, reaches 579.", fontsize=11, loc="left")
    ax.grid(alpha=0.25, which="both")

    # ---- B: geometry 1 — a LONGER lever ------------------------------------
    ax = fig.add_subplot(gs[1, 0])
    for k, r in data.items():
        lev = r.get("lever")
        if not lev:
            continue
        xs2 = [d for d in DELTAS if f"{d:+.2f}" in lev]
        ys = [lev[f"{d:+.2f}"] for d in xs2]
        lead = k in (STRAPPED, SAME_DAY_CONTROL)
        ax.plot([x * 100 for x in xs2], ys, marker="o", ms=4, color=colour(k),
                lw=2.6 if lead else 1.2, zorder=3 if lead else 1,
                label=short(k) if lead else None)
    ax.set_xlabel("watch pushed toward the elbow, cm")
    ax.set_ylabel("horizontal rms, cm")
    ax.set_yscale("log")
    ax.legend(fontsize=8)
    ax.set_title("B · FALSIFIED — a longer lever does not rescue it.\n"
                 "15 cm of displacement buys the strapped capture six percent.",
                 fontsize=11, loc="left")
    ax.grid(alpha=0.25, which="both")

    # ---- C: geometry 2 — a ROLLED watch ------------------------------------
    ax = fig.add_subplot(gs[1, 1])
    for k, r in data.items():
        a = r.get("angle")
        if not a:
            continue
        xs2 = [x for x in ANGLES if str(x) in a]
        ys = [a[str(x)]["h"] for x in xs2]
        lead = k in (STRAPPED, SAME_DAY_CONTROL)
        ax.plot(xs2, ys, color=colour(k), lw=2.6 if lead else 1.2,
                zorder=3 if lead else 1, label=short(k) if lead else None)
    ax.axvline(project.BAR_ANGLE_DEG, color="#2c3e50", ls="--", lw=1.4)
    ax.text(project.BAR_ANGLE_DEG + 2, ax.get_ylim()[1] * 0.72,
            f"ships at {project.BAR_ANGLE_DEG:.0f}°", fontsize=8, color="#2c3e50")
    ax.set_xlabel("BAR_ANGLE_DEG — the watch's roll about the forearm")
    ax.set_ylabel("horizontal rms, cm")
    ax.set_yscale("log")
    ax.legend(fontsize=8)
    ax.set_title("C · DISCOUNTED — the UNSTRAPPED control wants the same −50°.\n"
                 "So this optimum is not a strap effect; it is one parameter "
                 "fitted against the answer.", fontsize=11, loc="left")
    ax.grid(alpha=0.25, which="both")

    # ---- D: the same roll, measured WITHOUT the video ----------------------
    ax = fig.add_subplot(gs[2, 0])
    for k, r in data.items():
        if "gyro_angle" not in r:
            continue
        deg = r["u_dot_g"] > 0.75
        ax.scatter(r["u_dot_g"], r["gyro_angle"], s=165, color=colour(k),
                   marker="X" if deg else "o", zorder=3,
                   edgecolor="white", linewidth=1.4)
        ax.annotate(short(k), (r["u_dot_g"], r["gyro_angle"]), fontsize=7.5,
                    xytext=(7, 4), textcoords="offset points")
    ax.axvspan(0.75, 1.0, color="#e74c3c", alpha=0.08)
    ax.text(0.77, ax.get_ylim()[0] + 3, "ill-conditioned:\nbar axis ∥ forearm",
            fontsize=8, color="#c0392b")
    ax.set_xlabel("|u·g| — conditioning (→1 is degenerate)")
    ax.set_ylabel("roll estimated from the GYRO, deg")
    ax.set_title("D · The independent read: ~20°, not ~73°.\n"
                 "Of the well-conditioned captures only the strapped one leaves "
                 "the −3…+8° cluster.", fontsize=11, loc="left")
    ax.grid(alpha=0.25)

    # ---- E: the discriminator ----------------------------------------------
    ax = fig.add_subplot(gs[2, 1])
    keys = [k for k in data if data[k].get("spread")]
    keys.sort(key=lambda k: (data[k]["date"], k))
    for i, k in enumerate(keys):
        sp = data[k]["spread"]
        bad = k in KNOWN_BAD
        ax.scatter([i] * len(sp), sp, s=62, zorder=3,
                   marker="X" if bad else "o",
                   color="#95a5a6" if (bad and k != SAME_DAY_CONTROL) else colour(k),
                   alpha=0.85)
        if bad:
            ax.axvspan(i - 0.42, i + 0.42, color="#95a5a6", alpha=0.13, zorder=0)
    ax.axhspan(*VIDEO_FORE_AFT_CM, color="#27ae60", alpha=0.16, zorder=0)
    ax.text(0.02, 0.055, "what the bar actually did (video, all six deadlifts)",
            transform=ax.transAxes, fontsize=8.5, color="#1e8449")
    ax.set_xticks(range(len(keys)))
    ax.set_xticklabels([short(k) for k in keys], rotation=55, ha="right",
                       fontsize=7.5)
    ax.set_ylabel("per-rep horizontal spread, cm  (AXIS-FREE)")
    ax.set_title("E · THE DISCRIMINATOR — invented travel, which no rotation "
                 "can create.\nStrapped 19.9–27.9 cm · its own twin 5.4–7.7 · "
                 "the same-day unstrapped control 6.9–12.0.\n"
                 "grey X = already known bad for unrelated reasons.",
                 fontsize=11, loc="left")
    ax.grid(alpha=0.25, axis="y")

    fig.suptitle("H20 · The owner's straps hypothesis, tested — the watch was "
                 "MOVING, not merely repositioned", fontsize=14, y=0.997)
    out = Path(__file__).with_suffix(".png")
    fig.savefig(out, dpi=125, bbox_inches="tight")
    print(f"wrote {out}")


if __name__ == "__main__":
    if "--cache" in sys.argv and CACHE.exists():
        render(json.loads(CACHE.read_text()))
    else:
        render(compute())
