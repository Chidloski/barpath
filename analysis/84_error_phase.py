"""H34 — where the rep error actually lives, and why two corrections missed it.

H33 measured that reps do not close, and that an oracle told the true closure
gains nothing. This asks the obvious next question — if not at the endpoint,
where? — and the answer joins P2, P3, P6 and H27 into one chain.

1. THE ERROR IS A BULGE IN THE MIDDLE OF THE REP
Horizontal error against phase, rms cm, start-aligned as `vs_truth` scores it:

    phase       0.00  0.12  0.25  0.38  0.50  0.62  0.75  0.88  1.00
    bench       0.00  1.26  2.47  3.37  3.59  3.36  2.79  2.06  2.03
    deadlift    0.00  4.85  4.32  4.02  4.19  3.88  4.29  4.18  2.26
    squat       0.00  3.98  3.55  5.09  6.85  7.09  5.09  3.59  2.52
    ALL         0.00  3.68  3.53  4.17  4.96  4.92  4.11  3.38  2.27

Peak at phase 0.56; the endpoint carries **45% of the peak**. That is the whole
explanation of H33's null result — step 7 acts on the smallest part of the
error, so getting its target right cannot pay.

2. AND A QUADRATIC WOULD REACH SPEC — IF SOMETHING COULD SUPPLY IT
Best per-rep polynomial fitted AGAINST THE VIDEO. An oracle: it uses the answer,
so it is a ceiling on any estimator, never a proposal.

    lift        ships   ord 0   ord 1   ord 2   ord 3   ord 4
    bench        2.10    1.05    0.98    0.34    0.22    0.17
    deadlift     3.09    1.68    1.47    1.10    0.93    0.55
    squat        2.58    1.87    1.78    0.77    0.67    0.58
    ALL          2.39    1.65    1.37    0.71    0.56    0.39

**The jump is 1 -> 2**, 1.37 to 0.71 cm, and 0.71 is inside the ~1 cm spec. A
bulge is quadratic, so this is finding 1 restated in a basis. Order 1 is what
step 7 fits; the shape it cannot represent is exactly the shape the error has.

**This does not contradict C19**, which built a quadratic detrend and lost.
C19's quadratic was constrained to CLOSE the rep, so it had no way to learn the
bulge; this one is told it. The missing ingredient was never the basis.

3. THE BULGE IS A CONSTANT ACCELERATION ERROR — ON DEADLIFT
A constant horizontal acceleration error `a` over a rep of duration T, with a
line removed, leaves a parabola of amplitude a*T^2/8. That is a prediction with
no free parameters, and it is testable against rep duration (2.2-5.8 s here):

    lift        Spearman(T, amplitude)    log-log slope k     [T^2 predicts k = 2]
    deadlift      +0.392  (p = 0.014)         +2.08
    bench         +0.288  (p = 0.076)         +1.26
    squat         -0.167  (p = 0.353)         -0.57

**Deadlift lands on the prediction.** And the implied magnitude is the size P6
already measured from the other direction — the tilt leak surviving step 5b,
0.011-0.070 m/s^2:

    lift        implied a (m/s^2)     as tilt
    bench          0.033               0.19 deg
    deadlift       0.014               0.08
    squat          0.036               0.21

**Squat does not fit the model at all** (k = -0.57), and squat is also where
H33's endpoint oracle made things WORSE and where the non-closure walks. Three
independent analyses now say squat's horizontal error is a different animal.
Nothing here explains it.

4. WHY H27's PER-SET TILT CORRECTION LOST
H27 estimated this acceleration from the pull anchors and applied it per set;
it went `beats_null` 0.68 -> 0.33. The estimate is compared here against what
the position error implies:

    capture              H27 pull_mag   implied |a|   ratio
    deadlift_150x4_1        0.0828        0.0180      4.6
    deadlift_155x5_1        0.0466        0.0222      2.1
    deadlift_160x4_2        0.0529        0.0110      4.8
    deadlift_160x5_2        0.0478        0.0028     17.2
    deadlift_160x6_1        0.0579        0.0312      1.9
    deadlift_160x6_2        0.0119        0.0005     23.8
    deadlift_185x3          0.0496        0.0071      7.0
    deadlift_190x3          0.0330        0.0187      1.8
    deadlift_170x4_3        0.0425        0.0164      2.6

**Over-estimated on 9 of 9, median 4.6x.** Applying a real effect at four times
its size is how a correct mechanism produces 2.78 -> 5.01 cm. The direction is
right — same sign on every capture, Spearman +0.32 — but n = 9 and p = 0.41, so
there are not enough deadlift sets to fit the gain without fitting noise.

5. WHAT A PER-SET CONSTANT COULD CARRY
The implied acceleration is stable within a set — sd/|mean| of 0.34 (bench),
0.60 (deadlift), 0.47 (squat), under 1.0 on 22 of 24 sets — and **negative on
22 of 24 set means**, which is P6's sign result reproduced from position rather
than acceleration. So a per-SET constant is the right granularity. What is
missing is an estimator for its size, and the pull anchors are not it.

    python3 analysis/84_error_phase.py
"""
from __future__ import annotations

import json
import sys
import warnings
from pathlib import Path

import numpy as np
from scipy import stats

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src import capture, metrics, pipeline, tracked   # noqa: E402

RAW = ROOT / "data_v2" / "raw"
TRACKED = ROOT / "data_v2" / "tracked"
OUT = ROOT / "analysis" / "84_error_phase.png"
STRAPPED = "deadlift_160x6_1_20260818"
N = 64
PH = np.linspace(0.0, 1.0, N)


def _resamp(a, n=N):
    s = np.linspace(0, 1, len(a))
    q = np.linspace(0, 1, n)
    return np.column_stack([np.interp(q, s, a[:, 0]), np.interp(q, s, a[:, 1])])


def collect():
    warnings.simplefilter("ignore")
    out = []
    for csv in sorted(RAW.glob("*.csv")):
        if STRAPPED in csv.stem:
            continue
        tp = TRACKED / f"{csv.stem.rsplit('_', 1)[0]}.csv"
        if not tp.is_file():
            continue
        try:
            res = pipeline.run(csv)
            vs = metrics.vs_truth(res, tracked.read(None, src=tp))
        except Exception:
            continue
        t = res["log"]["t"]
        for pr in vs["per_rep"]:
            if not pr.get("covered"):
                continue
            a, z = res["bounds"][pr["rep"]]
            v = _resamp(np.asarray(pr["curve_video"], float))
            p = _resamp(np.asarray(pr["curve_pipeline"], float))
            e = ((p - p[0] + v[0]) - v)[:, 0]
            out.append(dict(capture=csv.stem, lift=capture.lift_of(csv),
                            rep=pr["rep"], T=float(t[z - 1] - t[a]), e=e))
    return out


def sagitta(e):
    """Amplitude of the best parabola through `e`, measured off its own chord."""
    c, *_ = np.linalg.lstsq(np.vander(PH, 3), e, rcond=None)
    fit = np.vander(PH, 3) @ c
    dev = fit - np.linspace(fit[0], fit[-1], N)
    return float(dev[int(np.argmax(np.abs(dev)))])


def main():
    reps = collect()
    lifts = ("bench", "deadlift", "squat")
    err = np.array([r["e"] for r in reps]) * 100
    lf = np.array([r["lift"] for r in reps])
    T = np.array([r["T"] for r in reps])

    print(f"{len(reps)} reps, duration {T.min():.1f}-{T.max():.1f} s\n")
    print("1. ERROR AGAINST PHASE, rms cm")
    idx = [int(round(x * (N - 1))) for x in np.linspace(0, 1, 9)]
    print("   " + " " * 10 + " ".join(f"{x:5.2f}" for x in np.linspace(0, 1, 9)))
    for l in lifts + ("ALL",):
        m = np.ones(len(err), bool) if l == "ALL" else (lf == l)
        prof = np.sqrt((err[m] ** 2).mean(0))
        print(f"   {l:10s}" + " ".join(f"{prof[i]:5.2f}" for i in idx))
    prof = np.sqrt((err ** 2).mean(0))
    print(f"   peak at phase {PH[np.argmax(prof)]:.2f}; "
          f"endpoint is {100*prof[-1]/prof.max():.0f}% of it")

    print("\n2. ORACLE LADDER over polynomial order (fitted against the video)")
    print(f"   {'lift':10s} {'ships':>7s} " +
          " ".join(f"{'ord ' + str(k):>7s}" for k in range(5)))
    for l in lifts + ("ALL",):
        m = np.ones(len(err), bool) if l == "ALL" else (lf == l)
        ships = np.median(np.sqrt((err[m] ** 2).mean(1)))
        row = []
        for k in range(5):
            V = np.vander(PH, k + 1)
            row.append(np.median([
                np.sqrt(((e - V @ np.linalg.lstsq(V, e, rcond=None)[0]) ** 2).mean())
                for e in err[m]]))
        print(f"   {l:10s} {ships:7.2f} " + " ".join(f"{x:7.2f}" for x in row))

    print("\n3. IS THE BULGE a*T^2/8 ?")
    amp = np.array([abs(sagitta(r["e"])) for r in reps])
    for l in lifts:
        m = lf == l
        r_, p_ = stats.spearmanr(T[m], amp[m])
        k = np.polyfit(np.log(T[m]), np.log(np.maximum(amp[m], 1e-6)), 1)[0]
        a_imp = np.median(8 * amp[m] / T[m] ** 2)
        print(f"   {l:10s} Spearman {r_:+.3f} (p={p_:.3f})  k={k:+.2f}  "
              f"implied a = {a_imp:.3f} m/s^2 = "
              f"{np.degrees(np.arcsin(a_imp / 9.81)):.2f} deg")

    print("\n4. H27's ESTIMATE vs WHAT THE POSITION ERROR IMPLIES")
    h27p = ROOT / "analysis" / "77_pull_tilt.json"
    if h27p.is_file():
        h27 = json.loads(h27p.read_text())
        by_cap = {}
        for r in reps:
            by_cap.setdefault(r["capture"], []).append(
                8 * sagitta(r["e"]) / r["T"] ** 2)
        pm, im = [], []
        print(f"   {'capture':34s} {'H27':>9s} {'implied':>9s} {'ratio':>7s}")
        for k, d in h27.items():
            if k not in by_cap or not d.get("pull_mag"):
                continue
            a = abs(float(np.mean(by_cap[k])))
            pm.append(d["pull_mag"])
            im.append(a)
            print(f"   {k[:34]:34s} {d['pull_mag']:9.4f} {a:9.4f} "
                  f"{d['pull_mag'] / max(a, 1e-9):7.1f}")
        pm, im = np.array(pm), np.array(im)
        if len(pm) > 2:
            r_, p_ = stats.spearmanr(pm, im)
            print(f"   over-estimated on {int((pm > im).sum())}/{len(pm)}, "
                  f"median {np.median(pm / im):.1f}x; Spearman {r_:+.3f} (p={p_:.3f})")

    print("\n5. IS IT CONSTANT WITHIN A SET?")
    sets = {}
    for r in reps:
        sets.setdefault((r["capture"], r["lift"]), []).append(
            8 * sagitta(r["e"]) / r["T"] ** 2)
    for l in lifts:
        cv, means = [], []
        for (cap, lift2), v in sets.items():
            if lift2 != l or len(v) < 3:
                continue
            v = np.array(v)
            cv.append(v.std() / max(abs(v.mean()), 1e-9))
            means.append(v.mean())
        print(f"   {l:10s} n={len(cv):2d} sets  median sd/|mean| {np.median(cv):.2f}"
              f"  under 1.0 on {int((np.array(cv) < 1).sum())}/{len(cv)}"
              f"  negative set means {int((np.array(means) < 0).sum())}/{len(means)}")

    figure(err, lf, T, amp, lifts)


def figure(err, lf, T, amp, lifts):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    C = {"bench": "#2f7fbf", "deadlift": "#c1352c", "squat": "#a96a13"}
    fig, axs = plt.subplots(1, 3, figsize=(15, 4.6))

    ax = axs[0]
    for l in lifts:
        ax.plot(PH, np.sqrt((err[lf == l] ** 2).mean(0)), lw=2, color=C[l], label=l)
    ax.plot(PH, np.sqrt((err ** 2).mean(0)), lw=1.4, color="#10151c", ls="--",
            label="all")
    ax.axvline(0.56, color="#7b8694", lw=1, ls=":")
    ax.set_xlabel("phase of the rep")
    ax.set_ylabel("horizontal error, rms cm")
    ax.set_title("1. the error is a bulge, not an endpoint", fontsize=10)
    ax.legend(fontsize=8)

    ax = axs[1]
    orders = range(5)
    for l in lifts:
        m = lf == l
        row = []
        for k in orders:
            V = np.vander(PH, k + 1)
            row.append(np.median([
                np.sqrt(((e - V @ np.linalg.lstsq(V, e, rcond=None)[0]) ** 2).mean())
                for e in err[m]]))
        ax.plot(list(orders), row, "o-", color=C[l], label=l)
    ax.axhline(1.0, color="#2f855a", ls="--", lw=1.3, label="the 1 cm spec")
    ax.set_xticks(list(orders))
    ax.set_xlabel("polynomial order fitted against the video (oracle)")
    ax.set_ylabel("residual, cm")
    ax.set_title("2. order 2 reaches spec — the basis is not the blocker",
                 fontsize=10)
    ax.legend(fontsize=8)

    ax = axs[2]
    for l in lifts:
        m = lf == l
        ax.scatter(T[m], amp[m] * 100, s=18, alpha=.75, color=C[l], label=l)
    tt = np.linspace(T.min(), T.max(), 50)
    for a_ in (0.01, 0.03):
        ax.plot(tt, 100 * a_ * tt ** 2 / 8, color="#7b8694", lw=1, ls="--")
        ax.annotate(f"a = {a_:.2f} m/s²", (tt[-1], 100 * a_ * tt[-1] ** 2 / 8),
                    fontsize=7, color="#7b8694", ha="right")
    ax.set_xlabel("rep duration, s")
    ax.set_ylabel("bulge amplitude, cm")
    ax.set_title("3. deadlift follows a·T²/8; squat does not", fontsize=10)
    ax.legend(fontsize=8)

    fig.suptitle("H34 — the rep error lives mid-rep, is quadratic, and on "
                 "deadlift is a constant acceleration offset", fontsize=12)
    fig.tight_layout()
    fig.savefig(OUT, dpi=115)
    print(f"\nwrote {OUT}")


if __name__ == "__main__":
    main()
