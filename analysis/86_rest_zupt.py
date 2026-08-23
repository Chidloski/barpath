"""H36 — the spare constraint was there all along: two rest ZUPTs give the bump.

The owner ruled out H35's recommendation: **the capture must never affect the
set**, so a mid-rep pause is not available. Pausing before and after is fine,
and the protocol already does it. That constraint is what sent this back to the
algebra, and the algebra had been read wrong.

P6 SAYS THE INFORMATION IS SPENT. IT IS NOT.
---------------------------------------------
P6: *"Two still instants give two numbers — the velocity error at each end —
and step 7's closure is the second. A line has two parameters, so the per-rep
detrend already consumes exactly that information."*

**Closure consumes only their MEAN.** A linear detrend of POSITION shifts
VELOCITY by a constant, so it can match one velocity condition, not two. With a
constant acceleration error `a` and an initial velocity error `v0`:

    velocity error at rep start   v0
    velocity error at rep end     v0 + a*T
    their mean                    v0 + a*T/2   <- what closure removes
    their difference / T          a            <- UNTOUCHED, and it is the bump

Verified symbolically at the top of `main`: after forcing closure the residual
is exactly `a*T^2/2 * (s^2 - s)` to 1e-16. So the second still instant is not
spent, and a quadratic needs no new measurement — only a subtraction nobody was
doing.

AND A DEADLIFT ALREADY HAS BOTH INSTANTS
-----------------------------------------
The bar rests on the floor between reps. `segment.rest_instants` finds those
moments from raw acceleration and gyro only — no attitude, no integration — and
`oracle.rest_observables` already returns `dv_h`, the velocity error accumulated
between two consecutive rests. C28b used it to ZERO that error, which is the
mean again. Nobody had divided it by the span.

    a_est = dv_h / span,      c2_est = a_est * T^2 / 2

WHAT IT SCORES, ON 27 DEADLIFT REPS
------------------------------------
    a_est vs the oracle a    Pearson +0.594 (p = 0.0011)
                             Spearman +0.430 (p = 0.025)

**The first estimator in this search with a significant correlation.** But it is
3.9x too large, so applied raw it is a disaster — 3.10 -> 8.23 cm. Applied with
a fitted gain:

    in sample                3.10 -> 2.42 cm
    LEAVE-ONE-CAPTURE-OUT    3.10 -> 2.66 cm, better on 48% of reps
    oracle ceiling           3.10 -> 1.88 cm

**It survives leave-one-out, which is the standard C28's ladder failed.** The
held-out gains are 0.194, 0.177, 0.180, 0.157, 0.166, 0.218, 0.065, 0.183,
0.173 — eight of nine inside 0.157-0.218. A gain that stable across captures it
has not seen is a transferable constant, not a fit to noise. Note the honest
qualifier: the MEDIAN improves while the per-rep hit rate is a coin flip, so it
helps bad reps more than it hurts good ones.

**The gain of ~0.17 is unexplained and is the open question.** It is not span
bookkeeping — rest-to-rest span and rep duration have a ratio of 1.00. Two
candidates, both testable: the interval contains the floor impact, whose impulse
error is not a constant acceleration and inflates `dv_h` (P6 has the impact
roughly doubling the horizontal error); or the watch's posture at rest differs
from its posture under load, which is C28's objection and which the opening-hold
test confirmed from the other side. Until that is settled the gain is an
empirical constant, and a correction resting on one should say so.

**Bench and squat cannot do this and provably never will.** They have no
raw-signal rest anchor: a bar descending at constant velocity reads |a| = g with
a quiet gyro exactly as a bar at rest does. See `metrics.momentum_closure`.

Nothing is proposed for `src/`.

    python3 analysis/86_rest_zupt.py
"""
from __future__ import annotations

import sys
import warnings
from pathlib import Path

import numpy as np
from scipy import stats

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src import metrics, oracle, pipeline, tracked   # noqa: E402

RAW = ROOT / "data_v2" / "raw"
TRACKED = ROOT / "data_v2" / "tracked"
OUT = ROOT / "analysis" / "86_rest_zupt.png"
STRAPPED = "deadlift_160x6_1_20260818"
N = 128
S = np.linspace(0.0, 1.0, N)
BUMP = S ** 2 - S
BB = float(BUMP @ BUMP)


def _resamp(a, n=N):
    s = np.linspace(0, 1, len(a))
    q = np.linspace(0, 1, n)
    return np.column_stack([np.interp(q, s, a[:, 0]), np.interp(q, s, a[:, 1])])


def check_algebra():
    """Closure removes the MEAN of the two velocity errors, not both."""
    T, a, v0 = 3.0, 0.03, 0.11
    s = np.linspace(0, 1, 2001)
    e = v0 * s * T + a * (s * T) ** 2 / 2
    q = e - np.linspace(e[0], e[-1], len(e))
    resid = float(np.abs(q - a * T ** 2 / 2 * (s ** 2 - s)).max())
    v = np.gradient(e, s * T)
    return resid, v[0], v[-1], (v[-1] - v[0]) / T, a


def collect():
    warnings.simplefilter("ignore")
    rows = []
    for csv in sorted(RAW.glob("deadlift*.csv")):
        if STRAPPED in csv.stem:
            continue
        tp = TRACKED / f"{csv.stem.rsplit('_', 1)[0]}.csv"
        if not tp.is_file():
            continue
        try:
            res = pipeline.run(csv)
            m = metrics.vs_truth(res, tracked.read(None, src=tp))
            obs = oracle.rest_observables(res, m)
        except Exception:
            continue
        t = res["log"]["t"]
        for o in obs:
            pr = m["per_rep"][o["rep"]]
            a_, z = res["bounds"][o["rep"]]
            T = float(t[z - 1] - t[a_])
            v = _resamp(np.asarray(pr["curve_video"], float))
            p = _resamp(np.asarray(pr["curve_pipeline"], float))
            e = ((p - p[0] + v[0]) - v)[:, 0]
            c2_o = float((e @ BUMP) / BB)
            rows.append(dict(cap=csv.stem, T=T, span=o["span"], e=e,
                             a_oracle=2 * c2_o / T ** 2,
                             a_est=o["dv_h"] / o["span"], c2_o=c2_o,
                             before=float(np.sqrt((e ** 2).mean()) * 100)))
    return rows


def score(rows, gain, icept=0.0):
    out = []
    for r in rows:
        c2 = (gain * r["a_est"] + icept) * r["T"] ** 2 / 2
        out.append(100 * np.sqrt(((r["e"] - c2 * BUMP) ** 2).mean()))
    return np.array(out)


def main():
    resid, v0, v1, diff, a = check_algebra()
    print("THE ALGEBRA — closure spends the mean, not both instants")
    print(f"  residual after closure equals a*T^2/2*(s^2-s) to {resid:.1e}")
    print(f"  v at start {v0:+.4f}, at end {v1:+.4f}")
    print(f"  difference/T = {diff:+.4f}  vs the true a = {a:+.4f}   <- unspent")

    rows = collect()
    ao = np.array([r["a_oracle"] for r in rows])
    ae = np.array([r["a_est"] for r in rows])
    before = np.array([r["before"] for r in rows])
    print(f"\nTHE ESTIMATOR, on {len(rows)} deadlift reps")
    rs, ps = stats.spearmanr(ao, ae)
    rp, pp = stats.pearsonr(ao, ae)
    print(f"  Pearson {rp:+.3f} (p={pp:.4f})   Spearman {rs:+.3f} (p={ps:.3f})")
    print(f"  a_est is {np.median(np.abs(ae / ao)):.1f}x the oracle magnitude")
    print(f"  span/T = {np.median([r['span']/r['T'] for r in rows]):.2f}, "
          f"so the factor is not span bookkeeping")

    sl = np.polyfit(ae, ao, 1)
    print(f"\nAPPLIED")
    print(f"  raw estimate            {np.median(before):.2f} -> "
          f"{np.median(score(rows, 1.0)):.2f} cm")
    print(f"  fitted gain {sl[0]:.3f}       {np.median(before):.2f} -> "
          f"{np.median(score(rows, sl[0], sl[1])):.2f} cm")

    caps = sorted({r["cap"] for r in rows})
    la, lb, gains = [], [], []
    for c in caps:
        tr = [r for r in rows if r["cap"] != c]
        te = [r for r in rows if r["cap"] == c]
        g = np.polyfit([r["a_est"] for r in tr], [r["a_oracle"] for r in tr], 1)
        gains.append(g[0])
        la += list(score(te, g[0], g[1]))
        lb += [r["before"] for r in te]
    la, lb = np.array(la), np.array(lb)
    print(f"  LEAVE-ONE-CAPTURE-OUT   {np.median(lb):.2f} -> {np.median(la):.2f} cm"
          f"   better on {100*(la<lb).mean():.0f}% of reps")
    print(f"  oracle ceiling          {np.median(before):.2f} -> "
          f"{np.median(score(rows, 0, 0) * 0 + [100*np.sqrt(((r['e']-r['c2_o']*BUMP)**2).mean()) for r in rows]):.2f} cm")
    print(f"  held-out gains: {[round(float(g), 3) for g in gains]}")

    figure(rows, ao, ae, before, la, lb, sl)


def figure(rows, ao, ae, before, la, lb, sl):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    fig, axs = plt.subplots(1, 3, figsize=(15, 4.6))

    ax = axs[0]
    ax.scatter(ae, ao, s=26, color="#c1352c", alpha=.8)
    xs = np.linspace(ae.min(), ae.max(), 20)
    ax.plot(xs, sl[0] * xs + sl[1], color="#10151c", lw=1.4,
            label=f"fit, gain {sl[0]:.2f}")
    ax.plot(xs, xs, ls="--", lw=1.2, color="#7b8694", label="gain 1 (raw)")
    ax.set_xlabel("a from the rest-to-rest velocity change, m/s²")
    ax.set_ylabel("a the bump implies, m/s²")
    ax.set_title("real signal, 3.9x too large", fontsize=10)
    ax.legend(fontsize=8)

    ax = axs[1]
    oracle_after = np.array([100 * np.sqrt(((r["e"] - r["c2_o"] * BUMP) ** 2).mean())
                             for r in rows])
    names = ["ships", "raw est", "fitted", "LOO", "oracle"]
    vals = [np.median(before), np.median(score(rows, 1.0)),
            np.median(score(rows, sl[0], sl[1])), np.median(la),
            np.median(oracle_after)]
    cols = ["#7b8694", "#c1352c", "#a96a13", "#2f855a", "#2f7fbf"]
    ax.bar(names, vals, color=cols)
    for i, v in enumerate(vals):
        ax.text(i, v, f"{v:.2f}", ha="center", va="bottom", fontsize=9)
    ax.set_ylabel("deadlift horizontal rms, cm")
    ax.set_title("applied — LOO is the one that counts", fontsize=10)

    ax = axs[2]
    ax.scatter(lb, la, s=26, color="#2f855a", alpha=.8)
    lim = [0, max(lb.max(), la.max()) * 1.05]
    ax.plot(lim, lim, ls="--", color="#7b8694", lw=1.2)
    ax.set_xlim(lim); ax.set_ylim(lim)
    ax.set_xlabel("before, cm")
    ax.set_ylabel("after, leave-one-out, cm")
    ax.set_title("below the line is an improvement", fontsize=10)

    fig.suptitle("H36 — the second rest instant was never spent, and a deadlift "
                 "already has it", fontsize=12)
    fig.tight_layout()
    fig.savefig(OUT, dpi=115)
    print(f"\nwrote {OUT}")


if __name__ == "__main__":
    main()
