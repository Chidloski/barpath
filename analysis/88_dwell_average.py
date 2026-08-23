"""H38 — the ceiling on a one-number-per-rep correction, per lift.

H37 put all the leverage in reducing `sd(a_est)`. This tried the obvious way and
found it does not work, then asked why — and the answer sets a hard ceiling on
the whole approach and inverts which lift it should be aimed at.

1. AVERAGING DOES NOTHING, SO THE RESIDUAL IS NOT NOISE
`oracle.rest_observables` samples velocity at a SINGLE index at each rest.
Averaging over a window either side should cut white noise by sqrt(n):

    window (s)   sd(a_est)   Pearson r   OLS gain   LOO cm
      0.00        0.0895      +0.594      0.173      2.66
      0.05        0.0893      +0.595      0.174      2.74
      0.10        0.0882      +0.598      0.177      2.88
      0.20        0.0878      +0.601      0.178      2.91
      0.50        0.0884      +0.614      0.181      2.89

**Flat.** Half a second of averaging moves `sd` by 1% and `r` by 0.02, and the
leave-one-out score gets slightly worse. So the 65% of `a_est` that does not map
to the bump is STRUCTURED, not measurement noise, and no amount of smoothing
will recover it.

2. WHY: THE ACCELERATION ERROR IS NOT CONSTANT ACROSS A REP
After closure the error vanishes at both endpoints, so its natural basis is
sin(k*pi*s). A constant acceleration error is a parabola, which is 99.9% the
k = 1 mode. Anything at k >= 2 is `a` varying within the rep. Median energy
fraction over 113 refereed reps:

    lift        k=1     k=2     k=3     k=4    k>=5 + rest
    bench      0.940   0.015   0.004   0.006      0.035
    squat      0.829   0.044   0.020   0.004      0.103
    deadlift   0.445   0.078   0.201   0.005      0.271
    ALL        0.827   0.048   0.036   0.005      0.084

**On bench the error IS a parabola — 94% of it.** On squat, 83%. On deadlift,
**44%**, with a strong third mode.

k = 1 is the ceiling on ANY correction carrying one number per rep, whatever
estimates it. So a per-rep constant-acceleration term can in principle remove
94% of bench's error energy and 44% of deadlift's, and the rest-ZUPT estimator's
r = 0.594 on deadlift is not a weak estimator — it is close to what the model
allows.

3. AND THE LIFTS ARE THE WRONG WAY ROUND
    lift        the model fits          an anchor exists
    bench          94%                   NO — and provably never will
    squat          83%                   no
    deadlift       44%                   yes, the floor between reps

**The lift where a constant acceleration explains the error is the lift with no
way to measure it, and the lift with the measurement is the one the model
suits worst.** That is not bad luck; it is the same physics twice. A bar that
sets down gives you a zero-velocity anchor AND a landing impulse, and the
impulse is exactly the localised, non-constant term that fills deadlift's k >= 3
modes. You cannot have the anchor without the thing that spoils the model.

WHAT THIS MEANS
----------------
The rest-ZUPT correction is near its ceiling on deadlift and should not be
pushed further by better estimation. Deadlift's remaining 56% is the
localised-in-time term that `TASKS.md`'s B6 has been chasing — this measures how
much of the error that is, which nothing had.

For bench and squat the prize is much larger and the blocker is different: the
model fits, and there is no anchor. `metrics.momentum_closure` records why a raw
anchor is impossible there — a bar descending at constant velocity reads |a| = g
with a quiet gyro exactly as a bar at rest does.

    python3 analysis/88_dwell_average.py
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
OUT = ROOT / "analysis" / "88_dwell_average.png"
STRAPPED = "deadlift_160x6_1_20260818"
NS = 256
S = np.linspace(0.0, 1.0, NS)
K = 6
BASIS = np.array([np.sin(k * np.pi * S) for k in range(1, K + 1)])
BASIS /= np.linalg.norm(BASIS, axis=1, keepdims=True)
BUMP = S ** 2 - S
BB = float(BUMP @ BUMP)
WINDOWS = (0.0, 0.05, 0.10, 0.20, 0.30, 0.50)


def _resamp(a, n=NS):
    s = np.linspace(0, 1, len(a))
    q = np.linspace(0, 1, n)
    return np.column_stack([np.interp(q, s, a[:, 0]), np.interp(q, s, a[:, 1])])


def collect():
    warnings.simplefilter("ignore")
    spec, dl = {}, {"oracle": [], "meta": [], **{w: [] for w in WINDOWS}}
    for csv in sorted(RAW.glob("*.csv")):
        if STRAPPED in csv.stem:
            continue
        tp = TRACKED / f"{csv.stem.rsplit('_', 1)[0]}.csv"
        if not tp.is_file():
            continue
        try:
            res = pipeline.run(csv)
            m = metrics.vs_truth(res, tracked.read(None, src=tp))
        except Exception:
            continue
        lift = capture.lift_of(csv)
        t = res["log"]["t"]

        for pr in m["per_rep"]:
            if not pr.get("covered"):
                continue
            v = _resamp(np.asarray(pr["curve_video"], float))
            p = _resamp(np.asarray(pr["curve_pipeline"], float))
            e = ((p - p[0] + v[0]) - v)[:, 0]
            e = e - np.linspace(e[0], e[-1], NS)
            n = np.linalg.norm(e)
            if n > 1e-9:
                spec.setdefault(lift, []).append(((BASIS @ e) / n) ** 2)

        if lift != "deadlift":
            continue
        try:
            rest = segment.rest_instants(res["log"], res["impacts"])
        except Exception:
            continue
        if len(rest) < 2:
            continue
        vel, fs = res["velocity"], res["log"]["fs"]
        axis = np.real(np.asarray(m["axis"], float))[:2]
        axis = axis / np.linalg.norm(axis)
        sign = -1.0 if m["axis_flipped"] else 1.0
        vh = sign * (vel[:, :2] @ axis)
        for j in range(len(rest) - 1):
            i0, i1 = rest[j], rest[j + 1]
            best = None
            for k, (a_, z) in enumerate(res["bounds"]):
                ov = min(i1, z - 1) - max(i0, a_)
                if ov > 0 and (best is None or ov > best[0]):
                    best = (ov, k)
            if best is None:
                continue
            pr = m["per_rep"][best[1]]
            if not pr.get("covered"):
                continue
            a_, z = res["bounds"][best[1]]
            T = float(t[z - 1] - t[a_])
            v = _resamp(np.asarray(pr["curve_video"], float))
            p = _resamp(np.asarray(pr["curve_pipeline"], float))
            e = ((p - p[0] + v[0]) - v)[:, 0]
            dl["oracle"].append(2 * float((e @ BUMP) / BB) / T ** 2)
            dl["meta"].append(dict(T=T, e=e, cap=csv.stem,
                                   before=float(np.sqrt((e ** 2).mean()) * 100)))
            span = t[i1] - t[i0]
            for w in WINDOWS:
                h = max(int(w * fs / 2), 0)
                a0 = vh[max(0, i0 - h): i0 + h + 1].mean() if h else vh[i0]
                a1 = vh[max(0, i1 - h): i1 + h + 1].mean() if h else vh[i1]
                dl[w].append((a1 - a0) / span)
    return spec, dl


def main():
    spec, dl = collect()
    ao = np.array(dl["oracle"])
    meta = dl["meta"]
    caps = sorted({m_["cap"] for m_ in meta})

    print("1. AVERAGING THE REST VELOCITY OVER A WINDOW")
    print(f"   {'window':>8s} {'sd':>9s} {'r':>8s} {'gain':>7s} {'LOO cm':>8s}")
    for w in WINDOWS:
        x = np.array(dl[w])
        r_, _ = stats.pearsonr(ao, x)
        la, lb = [], []
        for c in caps:
            tr = [i for i, m_ in enumerate(meta) if m_["cap"] != c]
            te = [i for i, m_ in enumerate(meta) if m_["cap"] == c]
            g = np.polyfit(x[tr], ao[tr], 1)
            for i in te:
                c2 = (g[0] * x[i] + g[1]) * meta[i]["T"] ** 2 / 2
                la.append(100 * np.sqrt(((meta[i]["e"] - c2 * BUMP) ** 2).mean()))
                lb.append(meta[i]["before"])
        print(f"   {w:8.2f} {x.std():9.4f} {r_:+8.3f} "
              f"{np.polyfit(x, ao, 1)[0]:7.3f} {np.median(la):8.2f}")
    print("   -> flat. The residual is structured, not noise.")

    par = BUMP / np.linalg.norm(BUMP)
    print(f"\n2. MODE ENERGY  (a parabola is {(par @ BASIS[0])**2:.3f} at k=1)")
    print(f"   {'lift':10s} {'n':>4s} " +
          " ".join(f"{'k=' + str(k):>7s}" for k in range(1, K + 1)) + "    rest")
    for lf in ("bench", "squat", "deadlift"):
        a = np.array(spec[lf])
        med = np.median(a, axis=0)
        print(f"   {lf:10s} {len(a):4d} " + " ".join(f"{x:7.3f}" for x in med)
              + f" {1 - med.sum():7.3f}")
    print("   k=1 is the ceiling on any one-number-per-rep correction.")

    print("\n3. THE LIFTS ARE THE WRONG WAY ROUND")
    print(f"   {'lift':10s} {'model fits':>11s}   raw anchor?")
    for lf, anc in (("bench", "no, never"), ("squat", "no"),
                    ("deadlift", "yes")):
        print(f"   {lf:10s} {np.median(np.array(spec[lf]), axis=0)[0]:11.0%}"
              f"   {anc}")

    figure(spec, dl, ao, meta, caps)


def figure(spec, dl, ao, meta, caps):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    C = {"bench": "#2f7fbf", "deadlift": "#c1352c", "squat": "#a96a13"}
    fig, axs = plt.subplots(1, 3, figsize=(15, 4.6))

    ax = axs[0]
    sds = [np.array(dl[w]).std() for w in WINDOWS]
    rs = [stats.pearsonr(ao, np.array(dl[w]))[0] for w in WINDOWS]
    ax.plot(WINDOWS, np.array(sds) / sds[0], "o-", color="#c1352c",
            label="sd(a_est), relative")
    ax.plot(WINDOWS, np.array(rs) / rs[0], "s-", color="#2f855a",
            label="Pearson r, relative")
    ax.plot(WINDOWS, [1 / np.sqrt(max(w * 100, 1)) for w in WINDOWS], "--",
            color="#7b8694", label="what white noise would do")
    ax.set_xlabel("averaging window at each rest, s")
    ax.set_ylabel("relative to no averaging")
    ax.set_title("averaging does nothing — not noise", fontsize=10)
    ax.legend(fontsize=8)

    ax = axs[1]
    ks = np.arange(1, K + 1)
    w = 0.26
    for i, lf in enumerate(("bench", "squat", "deadlift")):
        med = np.median(np.array(spec[lf]), axis=0)
        ax.bar(ks + (i - 1) * w, med, w, color=C[lf], label=lf)
    ax.set_xticks(ks)
    ax.set_xlabel("mode k of sin(kπs)")
    ax.set_ylabel("share of the post-closure error energy")
    ax.set_title("k=1 is a constant acceleration error", fontsize=10)
    ax.legend(fontsize=8)

    ax = axs[2]
    fits = [np.median(np.array(spec[lf]), axis=0)[0]
            for lf in ("bench", "squat", "deadlift")]
    anchors = [0, 0, 1]
    ax.bar(["bench", "squat", "deadlift"], fits,
           color=[C[l] for l in ("bench", "squat", "deadlift")])
    for i, (f, a) in enumerate(zip(fits, anchors)):
        ax.text(i, f + .02, f"{f:.0%}", ha="center", fontsize=10)
        ax.text(i, 0.05, "anchor" if a else "no anchor", ha="center",
                fontsize=9, color="white" if a else "#10151c",
                fontweight="bold" if a else "normal")
    ax.set_ylim(0, 1.05)
    ax.set_ylabel("ceiling on a one-number correction")
    ax.set_title("the model fits where it cannot be measured", fontsize=10)

    fig.suptitle("H38 — a one-number-per-rep correction is capped at 94% on "
                 "bench and 44% on deadlift", fontsize=12)
    fig.tight_layout()
    fig.savefig(OUT, dpi=115)
    print(f"\nwrote {OUT}")


if __name__ == "__main__":
    main()
