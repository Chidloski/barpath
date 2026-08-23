"""H39 — bench gets an anchor at lockout, and it halves the horizontal error.

H38 made this the biggest prize on the board: a one-number-per-rep correction
can reach 94% of bench's post-closure error energy and 83% of squat's, against
44% on deadlift, and the only thing missing was an anchor.

THE STANDING REASON WAS ABOUT DETECTION, NOT AVAILABILITY
----------------------------------------------------------
`metrics.momentum_closure` records why bench and squat have no raw-signal rest
anchor: a bar descending at constant velocity reads |a| = g with a quiet gyro
exactly as a bar at rest does. True, and it argues about DETECTING an anchor
from the raw signal. **It does not apply here, because nothing has to be
detected.** `_full_cycles` already runs a smooth lift's window turnaround to
turnaround, so the rep boundary is at lockout, and the segmenter has placed it.

AND THE BAR IS STILL ENOUGH THERE — IN THE CHANNEL THAT MATTERS
----------------------------------------------------------------
Measured against video. `deadlift REST` is the control: it is the anchor H36's
working estimator is built on.

    where                    n   |v_h| median   vs typical   |v_v| median
    bench window edge       55      0.0323         0.66         0.0581
    squat window edge       72      0.0196         0.45         0.1704
    deadlift window edge    79      0.0352         0.89         0.6375
    deadlift REST (works)   35      0.0168         0.44         0.0123

The bar is moving VERTICALLY at a smooth lift's boundary — it is reversing —
but its HORIZONTAL velocity is near zero, and horizontal is the channel the
whole problem lives in. Squat's boundary is stiller horizontally than deadlift's
floor rest.

THE RESULT
-----------
    a_est = [v_h(edge_end) - v_h(edge_start)] / T

no new sensing, no change to the capture, no new anchor detection.

    lift        n      r        p     gain   ships   LOO    better   ceiling
    bench      39   +0.656   0.0000   0.576   2.09   0.98    79%      0.65
    squat      35   +0.217   0.21     0.396   2.81   2.55    54%      1.41
    deadlift   39   +0.558   0.0002   0.088   3.10   2.76    49%      1.83

**Bench halves, under leave-one-CAPTURE-out, and lands inside the 1 cm spec.**

    capture                       h rms          beats_null
                                now -> LOO      now -> LOO
    bench_92.5x6_1              1.21   1.39     3.25   2.84
    bench_92.5x6_2              1.68   1.01     2.55   4.27
    bench_95x6_1                1.90   0.71     2.27   6.06
    bench_95x6_2                1.81   0.73     2.46   6.10
    bench_spoto_80x5_1          1.12   0.98     3.77   4.33
    bench_spoto_95x5_1          2.71   1.28     1.26   2.67
    bench_spoto_95x5_2          5.10   2.50     0.75   1.53
    ---------------------------------------------------------
    median                      2.09   0.98     2.46   4.27

**Six of seven captures improve and all seven now beat the null**, where six did
before. `bench_spoto_95x5_2` — the one capture that LOST to drawing no fore-aft
motion at all — crosses at 1.53. And `bench_spoto_95x5_1`, which `TASKS.md`
names as "the capture to explain", goes 2.71 -> 1.28.

The held-out gains are 0.622, 0.550, 0.584, 0.584, 0.583, 0.591, 0.458 — six of
seven inside 0.55-0.62. A gain that stable on captures it has not seen is a
population parameter. It is also much closer to 1 than deadlift's 0.088, which
is H37's attenuation identity working in bench's favour: the estimator is far
less noisy here.

WHY SQUAT DOES NOT WORK, THOUGH ITS ANCHOR IS BETTER
------------------------------------------------------
Squat's boundary is stiller horizontally (0.45 of typical against bench's 0.66)
and still fails at r = +0.217, p = 0.21. Two differences, and the second is the
likely one: its k = 1 model fit is 83% against bench's 94%, and **the bar is
moving vertically at 0.170 m/s at its boundary against bench's 0.058** — three
times faster. Any error in the display axis leaks that vertical motion into the
horizontal channel, and the axis is exactly the thing `FINDINGS.md` P2 says has
evidence against one step of its derivation. Not established here.

WHAT IS NOT DONE
-----------------
Nothing is proposed for `src/`. This changes every bench number in the project
and adds a calibrated constant to `correct.py`, which is a decision. The
measurement is leave-one-capture-out on 7 captures and 39 reps, which is the
right standard and a small corpus.

    python3 analysis/89_lockout_anchor.py
"""
from __future__ import annotations

import sys
import warnings
from pathlib import Path

import numpy as np
from scipy import stats

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src import capture, metrics, pipeline, segment, tracked   # noqa: E402

RAW = ROOT / "data_v2" / "raw"
TRACKED = ROOT / "data_v2" / "tracked"
OUT = ROOT / "analysis" / "89_lockout_anchor.png"
STRAPPED = "deadlift_160x6_1_20260818"
N = 128
S = np.linspace(0.0, 1.0, N)
BUMP = S ** 2 - S
BB = float(BUMP @ BUMP)


def _resamp(a, n=N):
    s = np.linspace(0, 1, len(a))
    q = np.linspace(0, 1, n)
    return np.column_stack([np.interp(q, s, a[:, 0]), np.interp(q, s, a[:, 1])])


def _sync(m):
    """Offset and slope, defending against NaN — `x or 1.0` does NOT, since NaN
    is truthy, and bench and squat fit an offset only."""
    off = m.get("sync_offset")
    slope = m.get("sync_slope")
    if off is None or not np.isfinite(off):
        return None, None
    if slope is None or not np.isfinite(slope):
        slope = 1.0
    return off, slope


def collect():
    warnings.simplefilter("ignore")
    reps, still = [], {}
    for csv in sorted(RAW.glob("*.csv")):
        if STRAPPED in csv.stem:
            continue
        tp = TRACKED / f"{csv.stem.rsplit('_', 1)[0]}.csv"
        if not tp.is_file():
            continue
        try:
            res = pipeline.run(csv)
            path = tracked.read(None, src=tp)
            m = metrics.vs_truth(res, path)
        except Exception:
            continue
        lift = capture.lift_of(csv)
        t, vel = res["log"]["t"], res["velocity"]
        axis = np.real(np.asarray(m["axis"], float))[:2]
        axis = axis / np.linalg.norm(axis)
        sign = -1.0 if m["axis_flipped"] else 1.0
        vh = sign * (vel[:, :2] @ axis)

        for pr in m["per_rep"]:
            if not pr.get("covered"):
                continue
            a_, z = res["bounds"][pr["rep"]]
            T = float(t[z - 1] - t[a_])
            if T <= 0:
                continue
            v = _resamp(np.asarray(pr["curve_video"], float))
            p = _resamp(np.asarray(pr["curve_pipeline"], float))
            e = ((p - p[0] + v[0]) - v)[:, 0]
            reps.append(dict(
                lift=lift, cap=csv.stem, T=T, e=e, null=pr["null_h_rms"],
                a_o=2 * float((e @ BUMP) / BB) / T ** 2,
                a_e=(vh[z - 1] - vh[a_]) / T,
                before=float(np.sqrt((e ** 2).mean()) * 100)))

        # how still the bar really is at the anchors, from video
        off, slope = _sync(m)
        if off is None:
            continue
        vt = (np.asarray(path["t"]) - off) / slope
        vx, vz = np.asarray(path["x"]), np.asarray(path["height"])
        ok = np.isfinite(vt) & np.isfinite(vx) & np.isfinite(vz)
        if ok.sum() < 20:
            continue
        vt, vx, vz = vt[ok], vx[ok], vz[ok]
        dvx, dvz = np.gradient(vx, vt), np.gradient(vz, vt)
        typ = float(np.percentile(np.abs(dvx), 75))
        idx = sorted({a for a, _ in res["bounds"]} | {z - 1 for _, z in res["bounds"]})
        for lbl, ii in ((f"{lift} window edge", idx),
                        ("deadlift REST",
                         segment.rest_instants(res["log"], res["impacts"])
                         if lift == "deadlift" else [])):
            for i in ii:
                if vt[0] <= t[i] <= vt[-1]:
                    still.setdefault(lbl, []).append(
                        (abs(float(np.interp(t[i], vt, dvx))),
                         abs(float(np.interp(t[i], vt, dvz))), typ))
    return reps, still


def loo(rr):
    """Leave-one-CAPTURE-out scores, and the held-out gains."""
    ao = np.array([r["a_o"] for r in rr])
    ae = np.array([r["a_e"] for r in rr])
    caps = sorted({r["cap"] for r in rr})
    la, lb, gains, per_cap = [], [], [], {}
    for c in caps:
        tr = [i for i, r in enumerate(rr) if r["cap"] != c]
        te = [i for i, r in enumerate(rr) if r["cap"] == c]
        if len(tr) < 4:
            continue
        g = np.polyfit(ae[tr], ao[tr], 1)
        gains.append(float(g[0]))
        a = [100 * np.sqrt(((rr[i]["e"]
                             - (g[0] * ae[i] + g[1]) * rr[i]["T"] ** 2 / 2 * BUMP)
                            ** 2).mean()) for i in te]
        b = [rr[i]["before"] for i in te]
        per_cap[c] = (float(np.median(b)), float(np.median(a)),
                      float(np.median([rr[i]["null"] for i in te])))
        la += a
        lb += b
    return np.array(la), np.array(lb), gains, per_cap


def main():
    reps, still = collect()
    print("HOW STILL IS THE BAR AT EACH CANDIDATE ANCHOR (video)")
    print(f"  {'where':24s} {'n':>4s} {'|v_h| med':>10s} {'vs typ':>7s} "
          f"{'|v_v| med':>10s}")
    for k in ("bench window edge", "squat window edge", "deadlift window edge",
              "deadlift REST"):
        if k not in still:
            continue
        a = np.array(still[k])
        print(f"  {k:24s} {len(a):4d} {np.median(a[:, 0]):10.4f} "
              f"{np.median(a[:, 0] / a[:, 2]):7.2f} {np.median(a[:, 1]):10.4f}")

    print(f"\nTHE ESTIMATOR  a_est = [v_h(end) - v_h(start)] / T")
    print(f"  {'lift':10s} {'n':>4s} {'r':>8s} {'p':>8s} {'gain':>7s} "
          f"{'ships':>7s} {'LOO':>7s} {'better':>7s} {'ceiling':>8s}")
    for lf in ("bench", "squat", "deadlift"):
        rr = [r for r in reps if r["lift"] == lf]
        ao = np.array([r["a_o"] for r in rr])
        ae = np.array([r["a_e"] for r in rr])
        r_, p_ = stats.pearsonr(ao, ae)
        la, lb, gains, _ = loo(rr)
        ceil = np.median([100 * np.sqrt(((r["e"] - r["a_o"] * r["T"] ** 2 / 2
                                          * BUMP) ** 2).mean()) for r in rr])
        print(f"  {lf:10s} {len(rr):4d} {r_:+8.3f} {p_:8.4f} "
              f"{np.polyfit(ae, ao, 1)[0]:7.3f} "
              f"{np.median([r['before'] for r in rr]):7.2f} "
              f"{np.median(la):7.2f} {100 * (la < lb).mean():6.0f}% {ceil:8.2f}")

    rr = [r for r in reps if r["lift"] == "bench"]
    la, lb, gains, per_cap = loo(rr)
    print(f"\nBENCH, PER CAPTURE     h rms now -> LOO     beats_null now -> LOO")
    nb, na = [], []
    for c, (b, a, nl) in sorted(per_cap.items()):
        nb.append(nl / b)
        na.append(nl / a)
        print(f"  {c[:34]:34s} {b:6.2f} {a:6.2f}      {nl/b:6.2f} {nl/a:6.2f}")
    print(f"  {'median':34s} {np.median(lb):6.2f} {np.median(la):6.2f}      "
          f"{np.median(nb):6.2f} {np.median(na):6.2f}")
    print(f"  beating the null: {sum(x > 1 for x in nb)}/{len(nb)} -> "
          f"{sum(x > 1 for x in na)}/{len(na)}")
    print(f"  held-out gains: {[round(g, 3) for g in gains]}")

    figure(reps, still, per_cap)


def figure(reps, still, per_cap):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    C = {"bench": "#2f7fbf", "deadlift": "#c1352c", "squat": "#a96a13"}
    fig, axs = plt.subplots(1, 3, figsize=(15, 4.6))

    ax = axs[0]
    keys = ["bench window edge", "squat window edge", "deadlift window edge",
            "deadlift REST"]
    vals = [np.median(np.array(still[k])[:, 0] / np.array(still[k])[:, 2])
            for k in keys if k in still]
    cols = ["#2f7fbf", "#a96a13", "#c1352c", "#2f855a"]
    ax.barh([k.replace(" window edge", "\nwindow edge") for k in keys], vals,
            color=cols)
    ax.set_xlabel("horizontal speed there, vs the rep's typical")
    ax.set_title("the bar is still enough at lockout", fontsize=10)

    ax = axs[1]
    for lf in ("bench", "squat", "deadlift"):
        rr = [r for r in reps if r["lift"] == lf]
        ax.scatter([r["a_e"] for r in rr], [r["a_o"] for r in rr], s=22,
                   alpha=.75, color=C[lf], label=lf)
    ax.set_xlabel("a from the window-edge velocity change, m/s²")
    ax.set_ylabel("a the bump implies, m/s²")
    ax.set_title("bench r = +0.66; squat does not follow", fontsize=10)
    ax.legend(fontsize=8)

    ax = axs[2]
    names = [c.replace("bench_", "").replace("_2026", "\n2026")[:22]
             for c in sorted(per_cap)]
    b = [per_cap[c][0] for c in sorted(per_cap)]
    a = [per_cap[c][1] for c in sorted(per_cap)]
    x = np.arange(len(names))
    ax.bar(x - .2, b, .4, label="ships", color="#7b8694")
    ax.bar(x + .2, a, .4, label="with the anchor (LOO)", color="#2f7fbf")
    ax.axhline(1.0, color="#2f855a", ls="--", lw=1.4, label="the 1 cm spec")
    ax.set_xticks(x)
    ax.set_xticklabels(names, rotation=90, fontsize=6.5)
    ax.set_ylabel("horizontal rms, cm")
    ax.set_title("bench, per capture — 6 of 7 improve", fontsize=10)
    ax.legend(fontsize=8)

    fig.suptitle("H39 — a smooth lift's rep boundary IS an anchor, and on bench "
                 "it halves the error", fontsize=12)
    fig.tight_layout()
    fig.savefig(OUT, dpi=115)
    print(f"\nwrote {OUT}")


if __name__ == "__main__":
    main()
