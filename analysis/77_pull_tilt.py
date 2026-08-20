"""H27 — the per-set tilt correction from the pull anchors. IT LOSES.

The owner asked for H26's prior 1 to be BUILT. It is built
(`oracle.pull_tilt`, `oracle.pull_intervals`, `oracle.pull_tilt_correction`),
it is measured against the video on both axes, and **it makes the horizontal
worse on 7 of 8 deadlifts in every variant tried.** Kept rather than deleted,
with the mechanism, because the arithmetic that explains the failure is worth
more than the correction would have been.

    arm                                  median h   beats_null   better than ship
    shipping                               2.78 cm      0.68             -
    per-SET constant, IMU pull anchors     5.01         0.33          1 of 8
    per-SET constant, VIDEO pull anchors   5.18         0.38          1 of 8
    per-REP constant                       5.00         0.34          1 of 8
    in-span only (correct where measured)  3.54         0.48          2 of 8

**The loss is clean and unconfounded, which is the one thing this arm got
right.** Reps scored is 36 of 36 in every arm — shipping's windows, so the
flat-line null does not move and there is nothing to discount, unlike C29, H22
and H24. Vertical rms is 2.88 cm in every arm and reps outside the 40-61 cm ROM
band are 0 of 36 in every arm, because only columns 0 and 1 are touched. So this
is not H24b's failure shape: nothing was traded, the horizontal simply got
worse.

WHAT WAS BUILT, AND ALL THREE OF H26'S CONDITIONS WERE MET.

1. *Estimable without the video.* `oracle.pull_intervals` uses only the raw
   accel+gyro quiet score, `segment.impact_anchors` and H22's pre-pull anchor,
   and finds **36 pull intervals on the clean eight against the video's 13**,
   at least one on every capture including both singles.
2. *Covers every rep.* `bounds` is SHIPPING's, so `n_compared` and the
   flat-line null are shipping's exactly. No coverage change to discount, which
   is what H23 closed C29 for.
3. *Scored on both axes and the ROM band.* H24b's lesson, applied.

Meeting the conditions was not enough. That is the result.

WHY IT FAILS, AND THE ARITHMETIC PREDICTS THE DAMAGE BEFORE YOU RUN IT.

Step 7 removes a LINE per rep. A constant acceleration error is QUADRATIC in
position, so what survives each rep is a parabola of sagitta a*T^2/8. For the
measured tilt (median 0.058 m/s^2) over a deadlift rep (median T = 3.2 s) that
is **1.2 to 12.9 cm, median 8.0 cm**.

**Shipping's entire horizontal error is 2.78 cm.** So a uniform constant of the
measured size CANNOT be present through the rep — if it were, the reconstruction
would already be missing by ~8 cm and it is not. Subtracting it therefore injects
a parabola that was never there, and the observed 2.78 -> 5.01 is that parabola
arriving. The in-span arm damaging least (3.54) fits: it touches the fewest
samples.

WHAT THE MEASUREMENT ACTUALLY IS, then. `dv/span` is a MEAN acceleration over an
interval. A mean is not a shape. The same closure identity over the WHOLE rep
gives 0.199 m/s^2 — **4.1x larger than the pull's** — and a uniform constant of
THAT size would leave ~30 cm. Both numbers are real and neither is a constant:
the error is concentrated in time (H25's impact, C29's landing), and
concentrated error has a large mean and a small double integral.

**So this is C28's "P3's error is not a constant in ANY frame" reproduced from a
new direction, with a mechanism attached.** H26 was right that the tilt is real,
systematic and survives step 5b. H26's inference that it could therefore be
removed as a constant is what fails here. The gap between those two is the
finding: *a systematically-signed mean over an interval is not evidence of a
uniform error, and this project has now paid for that inference twice.*

ONE DISSENT, RECORDED AND NOT EXPLAINED. `deadlift_190x3_20260818` improves
under every arm — 7.22 -> 1.84 cm and `beats_null` 0.43 -> 1.69 under the per-rep
variant, the highest any deadlift has ever scored here. It is also the capture
H20 measured as elevated and explicitly left open, whose video shows the bar
really moving 8.7/10.2/4.9 cm of fore-aft against a corpus norm of 4.4-6.0.
n = 1, on the one capture that was already anomalous. A lead, not a result.

THE SELF-LIMITING PROPERTY IS WEAKER THAN IT LOOKS, and the control says so.
Bench and squat come back bit-identical, as they must. But squat gets there by
having no impacts at all, while **`bench_92.5x6_1` has ONE spurious impact
anchor** — a re-rack — which yields one pull interval. What makes the correction
the identity there is `min_pulls = 2`, not the absence of impacts. A bench
capture with two spurious anchors would be corrected, on a lift with no floor
landing anywhere in it. Recorded, not fixed: nothing here ships.

Excluded by hand and named every time: `deadlift_160x6_1_20260818` (straps,
H20); `deadlift_170x4_3` (22.8% clock drift, G3) and `deadlift_210x1`
(miscounts a labelled single, H15) are in the EXTRA column only.
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
from scipy.signal import savgol_filter
from scipy.stats import wilcoxon

from src import correct, integrate, metrics, oracle, pipeline

CACHE = Path(__file__).with_suffix(".json")
CLEAN = ["deadlift_150x4_1_20260808_121648", "deadlift_155x5_1_20260815_133343",
         "deadlift_160x4_2_20260808_122319", "deadlift_160x5_2_20260815_134017",
         "deadlift_160x6_1_20260804_104711", "deadlift_160x6_2_20260804_105455",
         "deadlift_185x3_20260804_103456", "deadlift_190x3_20260818_122535"]
EXTRA = ["deadlift_170x4_3_20260808_122936", "deadlift_210x1_20260815_132206"]
# No impacts means no pull intervals means no correction. Verified, not assumed.
SMOOTH = ["bench_92.5x6_1_20260808_114027",
          "squat_pause_140x4_2_20260806_113440"]
BAND = (40.0, 61.0)
G = 9.81


def rec(m):
    roms = [float(np.ptp(np.asarray(r["curve_pipeline"], float)[:, 1] * 100.0))
            for r in m["per_rep"] if r.get("curve_pipeline") is not None]
    return {"h": m["pipeline_h_rms"], "bn": m["beats_null"],
            "v": m["pipeline_v_rms"], "n": m["n_compared"],
            "bad_rom": sum(1 for x in roms if not BAND[0] <= x <= BAND[1]),
            "n_rom": len(roms)}


def _score(res, video, world):
    """Re-integrate a modified world acceleration on SHIPPING's windows."""
    log = res["log"]
    _, pos = integrate.integrate(world, log["dt"])
    d = res.get("wrist_offset")
    if d is not None:
        pos = correct.apply_offset(pos, res["quat"], d)
    out = dict(res)
    out["bar_position"] = pos
    out["reps"] = correct.detrend_set(pos, res["bounds"], log["t"])
    return rec(metrics.vs_truth(out, video))


def video_pull_bias(res, video):
    """H26's own pull intervals — video-defined still instants, no impact."""
    log = res["log"]; t = log["t"]; vel = res["velocity"]
    impacts = list(res.get("impacts") or [])
    t_imu, _, height, _ = metrics._video_on_imu_clock(res, video, None)
    v_vid = np.gradient(savgol_filter(height, 9, 3), t_imu)
    b = res["bounds"]
    lo, hi = float(t[b[0][0]]), float(t[b[-1][1] - 1])
    mids = metrics._video_zero_dwells(t_imu, v_vid, 0.10, 0.20)
    mids = mids[(mids >= lo - 0.5) & (mids <= hi + 0.5)]
    idx = [int(np.searchsorted(t, m)) for m in mids]
    rows = [(vel[bb][:2] - vel[a][:2]) / float(t[bb] - t[a])
            for a, bb in zip(idx[:-1], idx[1:])
            if bb - a >= 10 and not any(a <= k <= bb for k in impacts)]
    return (np.median(np.asarray(rows), axis=0), len(rows)) if rows else (None, 0)


def compute():
    out = {}
    for stem in CLEAN + EXTRA + SMOOTH:
        csv = ROOT / "data_v2" / "raw" / f"{stem}.csv"
        if not csv.exists():
            print(f"  {stem[:40]:42} MISSING, skipped", flush=True)
            continue
        video = pipeline.find_video(csv)
        res = pipeline.run(csv, video=video)
        if res.get("vs_truth") is None:
            print(f"  {stem[:40]:42} no vs_truth, skipped", flush=True)
            continue
        log = res["log"]; t = log["t"]; vel = res["velocity"]
        spans = oracle.pull_intervals(res)
        bias, info = oracle.pull_tilt(res)
        row = {"label": len(res["bounds"]), "n_pulls": info["n_pulls"],
               "bias": bias.tolist(), "tilt_deg": info.get("tilt_deg"),
               "ship": rec(res["vs_truth"])}

        base = np.asarray(res["world_accel"], float)
        w = base.copy(); w[:, :2] -= bias
        row["set"] = _score(res, video, w)

        vb, nv = video_pull_bias(res, video)
        row["n_video_pulls"] = nv
        if vb is not None:
            w = base.copy(); w[:, :2] -= vb
            row["vset"] = _score(res, video, w)

        w = base.copy()                                   # in-span only
        w2 = base.copy()                                  # per-rep
        for a, b in spans:
            sp = float(t[b] - t[a])
            if sp <= 0:
                continue
            bj = (vel[b][:2] - vel[a][:2]) / sp
            w[a:b + 1, :2] -= bj
            owner = [q for q in res["bounds"] if q[0] <= a < q[1]]
            lo, hi = owner[0] if owner else (a, b)
            w2[lo:hi, :2] -= bj
        row["inspan"] = _score(res, video, w)
        row["rep"] = _score(res, video, w2)

        # the mechanism: what a uniform constant of this size would leave
        T = float(np.median([t[b - 1] - t[a] for a, b in res["bounds"]]))
        repmean = [np.linalg.norm((vel[b - 1][:2] - vel[a][:2])
                                  / float(t[b - 1] - t[a]))
                   for a, b in res["bounds"] if t[b - 1] > t[a]]
        row["T"] = T
        row["pull_mag"] = float(np.linalg.norm(bias))
        row["rep_mag"] = float(np.median(repmean)) if repmean else None
        row["sagitta_cm"] = float(np.linalg.norm(bias) * T * T / 8 * 100)
        out[stem] = row
        print(f"  {stem[:40]:42} ship {row['ship']['h']:5.2f} -> set "
              f"{row['set']['h']:5.2f}  inspan {row['inspan']['h']:5.2f}  "
              f"rep {row['rep']['h']:5.2f}  (predicted +{row['sagitta_cm']:.1f} cm)",
              flush=True)
    CACHE.write_text(json.dumps(out, indent=1))
    return out


ARMS = [("ship", "shipping", "#7f8c8d"),
        ("set", "per-SET constant\n(IMU anchors)", "#c0392b"),
        ("vset", "per-SET constant\n(VIDEO anchors)", "#e67e22"),
        ("rep", "per-REP constant", "#8e44ad"),
        ("inspan", "in-span only", "#2980b9")]


def render(d):
    clean = [s for s in CLEAN if s in d]
    fig, axes = plt.subplots(2, 2, figsize=(16.8, 12.4))

    # ------------------------------------------------------ A · every arm
    ax = axes[0][0]
    for i, (k, lab, c) in enumerate(ARMS):
        v = [d[s][k]["h"] for s in clean if k in d[s]]
        ax.scatter(np.full(len(v), i) + np.random.uniform(-.12, .12, len(v)),
                   v, s=44, color=c, alpha=0.8, zorder=3)
        ax.hlines(np.median(v), i - .3, i + .3, color="#2c3e50", lw=2.8, zorder=4)
        ax.text(i, np.median(v) + 0.35, f"{np.median(v):.2f}", ha="center",
                fontsize=10.5, fontweight="bold", color=c)
    ship = [d[s]["ship"]["h"] for s in clean]
    ax.axhline(np.median(ship), color="#7f8c8d", lw=1.4, ls="--", zorder=1)
    ax.set_xticks(range(len(ARMS)))
    ax.set_xticklabels([a[1] for a in ARMS], fontsize=8.5)
    ax.set_ylabel("horizontal rms vs video, cm")
    wins = {k: sum(1 for s in clean if k in d[s] and d[s][k]["h"] < d[s]["ship"]["h"])
            for k, _, _ in ARMS[1:]}
    ax.set_title("A · Every variant LOSES to shipping.\n"
                 "Better than shipping: " +
                 ", ".join(f"{v} of {len(clean)}" for v in wins.values()) +
                 " respectively.\nThe idea met all three of H26's conditions "
                 "and still fails.", fontsize=11, loc="left")
    ax.grid(alpha=0.25, axis="y")

    # ------------------------------------------------------ B · beats_null
    ax = axes[0][1]
    bs = [d[s]["ship"]["bn"] for s in clean]
    bt = [d[s]["set"]["bn"] for s in clean]
    for a, b in zip(bs, bt):
        ax.plot([0, 1], [a, b], color="#95a5a6", lw=1.2, zorder=2)
    ax.scatter(np.zeros(len(bs)), bs, s=62, color="#7f8c8d", zorder=3)
    ax.scatter(np.ones(len(bt)), bt, s=62, color="#c0392b", zorder=3)
    ax.axhline(1.0, color="#c0392b", lw=1.6, ls="--", zorder=1)
    ax.text(1.03, 1.0, " the flat-line null", color="#c0392b", fontsize=9,
            va="center")
    ax.set_xticks([0, 1]); ax.set_xlim(-0.3, 1.5)
    ax.set_xticklabels(["shipping", "+ per-set tilt"], fontsize=10)
    ax.set_ylabel("beats_null")
    try:
        p = float(wilcoxon(bs, bt).pvalue)
    except Exception:
        p = float("nan")
    ax.set_title(f"B · beats_null {np.median(bs):.2f} -> {np.median(bt):.2f} "
                 f"(paired Wilcoxon p = {p:.3f}).\n"
                 "The null is UNCHANGED — shipping's windows — so this is "
                 "like-for-like\nand there is nothing to discount, unlike C29 "
                 "and H22.", fontsize=11, loc="left")
    ax.grid(alpha=0.25, axis="y")

    # ------------------------------------------------------ C · the mechanism
    ax = axes[1][0]
    sag = [d[s]["sagitta_cm"] for s in clean]
    obs = [d[s]["set"]["h"] - d[s]["ship"]["h"] for s in clean]
    ax.bar(np.arange(len(clean)) - 0.19, sag, 0.36, color="#c0392b", zorder=3,
           label="parabola a·T²/8 a uniform constant would leave")
    ax.bar(np.arange(len(clean)) + 0.19, ship, 0.36, color="#7f8c8d", zorder=3,
           label="shipping's ENTIRE horizontal error")
    ax.set_xticks(range(len(clean)))
    ax.set_xticklabels([s.split("_2026")[0].replace("deadlift_", "")
                        for s in clean], rotation=30, ha="right", fontsize=8)
    ax.set_ylabel("cm")
    ax.legend(fontsize=8.5)
    ax.set_title("C · WHY it fails, and the arithmetic says so in advance.\n"
                 f"A uniform constant of the measured size would leave "
                 f"{np.median(sag):.0f} cm after step 7's line.\n"
                 f"Shipping's whole horizontal error is "
                 f"{np.median(ship):.2f} cm — so the error is NOT that "
                 "constant,\nand subtracting it injects a parabola that was "
                 "never there.", fontsize=11, loc="left")
    ax.grid(alpha=0.25, axis="y")

    # ------------------------------------------------------ D · mean vs shape
    ax = axes[1][1]
    pm = [d[s]["pull_mag"] for s in clean]
    rm = [d[s]["rep_mag"] for s in clean]
    x = np.arange(len(clean))
    ax.bar(x - 0.19, pm, 0.36, color="#f39c12", zorder=3,
           label="mean |a| error over the PULL (impact-free)")
    ax.bar(x + 0.19, rm, 0.36, color="#c0392b", zorder=3,
           label="mean |a| error over the WHOLE REP")
    ax.set_xticks(x)
    ax.set_xticklabels([s.split("_2026")[0].replace("deadlift_", "")
                        for s in clean], rotation=30, ha="right", fontsize=8)
    ax.set_ylabel("mean horizontal acceleration error, m/s²")
    ax.legend(fontsize=8.5)
    ax.set_title("D · A MEAN is not a SHAPE.\n"
                 f"The whole rep's mean error is {np.median(rm)/np.median(pm):.1f}x "
                 "the pull's — and a uniform constant of\nTHAT size would leave "
                 "~30 cm. Neither is a constant: the error is\nconcentrated in "
                 "time (H25's impact), which has a large mean and a\nsmall "
                 "double integral.", fontsize=11, loc="left")
    ax.grid(alpha=0.25, axis="y")

    fig.suptitle("H27 · The per-set tilt correction, built and measured — it "
                 "loses, and the arithmetic says why", fontsize=14, y=1.003)
    fig.tight_layout()
    png = Path(__file__).with_suffix(".png")
    fig.savefig(png, dpi=118, bbox_inches="tight")
    print(f"wrote {png}")

    print(f"\n{'capture':26}{'pulls':>6}{'ship':>7}{'set':>7}{'vset':>7}"
          f"{'rep':>7}{'inspan':>8}{'bn':>6}{'->bn':>6}{'v':>7}{'->v':>7}")
    for s in CLEAN + EXTRA:
        if s not in d:
            continue
        r = d[s]
        g = lambda k: f"{r[k]['h']:.2f}" if k in r else "-"
        print(f"{s.split('_2026')[0]:26}{r['n_pulls']:6}{r['ship']['h']:7.2f}"
              f"{g('set'):>7}{g('vset'):>7}{g('rep'):>7}{g('inspan'):>8}"
              f"{r['ship']['bn']:6.2f}{r['set']['bn']:6.2f}"
              f"{r['ship']['v']:7.2f}{r['set']['v']:7.2f}"
              + ("" if s in CLEAN else "   (EXTRA)"))
    print("\nSELF-LIMITING control — no impacts, so no pull intervals, so the "
          "correction must be the IDENTITY:")
    for s in SMOOTH:
        if s not in d:
            continue
        r = d[s]
        same = abs(r["ship"]["h"] - r["set"]["h"]) < 1e-9
        print(f"  {s.split('_2026')[0]:34} pulls {r['n_pulls']}  "
              f"h {r['ship']['h']:.4f} -> {r['set']['h']:.4f}  "
              f"{'IDENTICAL' if same else '*** MOVED ***'}")
    print("\nVERTICAL is untouched by construction (columns 0,1 only) — "
          "check the v columns above.")


if __name__ == "__main__":
    np.random.seed(0)
    render(compute() if "--fresh" in sys.argv or not CACHE.exists()
           else json.loads(CACHE.read_text()))
