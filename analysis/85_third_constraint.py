"""H35 — a quadratic detrend needs a third constraint. Four sources, none works.

The owner: *"investigate subtracting a polynomial from the endpoints rather than
a straight line - this will need extra information from somewhere, see what you
can do."* He is right that it needs extra information, and this is the search
for it.

THE SHAPE OF THE PROBLEM: ONE UNKNOWN, NOT THREE
-------------------------------------------------
Step 7 removes a line through the rep's endpoints. Keep that and add curvature
and the extra term must VANISH at both endpoints, so the whole added freedom is
a single number:

    q(s) = p(s) - c2 * (s^2 - s),     s in [0, 1]

`c2` is exactly a constant acceleration error: c2 = a*T^2/2, peak bulge a*T^2/8.
So "a polynomial instead of a line" is precisely "estimate the constant
horizontal acceleration error over the rep".

WHAT IT IS WORTH
-----------------
Oracle c2, projected from the shipped error onto (s^2 - s):

    lift        ships   with oracle c2   gain
    bench        2.09        0.65       +1.43
    deadlift     3.10        1.83       +1.27
    squat        2.58        1.41       +1.17
    ALL          2.39        1.25       +1.14

And how coarse it may be — these are ceilings, not estimators:

    lift        ships   global   per-lift   per-set   per-rep
    bench        2.09    1.41      1.35      1.03      0.65
    deadlift     3.10    3.49      3.15      2.44      1.83
    squat        2.58    2.39      2.24      1.75      1.41
    ALL          2.39    2.37      1.93      1.71      1.25

**A per-SET c2 captures 60% of the gain** and is the right granularity. A global
constant is worthless and makes deadlift worse, because the per-set sign is not
fixed within a lift — deadlift runs -35 to +36 cm and squat -30 to +27.

FOUR SOURCES FOR c2, AND WHY EACH FAILS
----------------------------------------
1. **The pull anchors** (H27's estimator). Too large on 9 of 9 deadlifts, median
   4.6x, range 1.8-23.8x; Spearman +0.32 at p = 0.41. Right sign, wrong size,
   and n = 9 is too few to fit the gain.

2. **Rep-to-rep dispersion**, the 5b pattern. **Blocked by construction**: a bump
   applied identically to every rep in a set is common-mode in rep phase, and
   dispersion sees only differences between reps. The only leverage is that a
   constant `a` gives rep k a bump of a*T_k^2/2, which differs as durations
   differ — and the within-set spread of T^2 is 42% of its mean, so most of the
   signal is invisible. Within a set the oracle c2 tracks T^2 at a median
   r = +0.45 over 19 sets, where a constant `a` predicts +1.

3. **The turnaround.** The obvious mid-rep landmark, free on every rep of every
   lift, trivially found as the vertical velocity zero crossing. **It fails
   structurally.** The bump's slope is c2*(2s-1)/T, so a still instant at phase
   s* gives c2 = v(s*)*T/(2s*-1) and is SINGULAR at s* = 0.5 — and the
   turnaround is the middle of the motion by definition:

       lift       turn phase   |v_h| there, vs the rep's typical
       bench         0.57               0.20
       squat         0.47               0.29
       deadlift      0.74               1.40

   Where the bar is still the lever vanishes; where the lever is usable
   (deadlift, 0.74) the bar is moving FASTER than typical. Run anyway, the
   estimator scores Spearman +0.06 to +0.24, none significant, at 2.6-4.5x the
   oracle magnitude. **Every pause the corpus has — paused squats at the bottom,
   spoto benches at the chest — is at the same useless phase.**

4. **The opening hold**, the one still interval that is not mid-rep. When the
   watch is still the accelerometer sees only gravity, so world-frame horizontal
   acceleration there is pure attitude error. It is **the right size** (0.006 to
   0.024 m/s^2 against an implied 0.02) and **uncorrelated per capture**:
   Spearman -0.04, p = 0.83, n = 26. That is C28's objection confirmed — the
   watch's posture at the hold is not its posture during the rep, and a tilt
   error is posture-dependent.

WHAT WOULD WORK, AND IT IS A CAPTURE CHANGE
--------------------------------------------
The information has to come from a still instant AWAY from mid-rep, and no lift
naturally provides one. Cue a pause at roughly a quarter of the way through a
rep — partway down a squat, partway up a bench — and the lever becomes usable.
The IMU's horizontal velocity error at a still instant is measured here at
**2.04 cm/s**, which sets the achievable precision:

    pause phase   per-rep sigma(c2)    averaged over 4 reps   over 6
        0.30       15.8 cm (1.48x)       7.9 cm (0.74x)     6.5 (0.60x)
        0.25       12.7 cm (1.18x)       6.3 cm (0.59x)     5.2 (0.48x)
        0.20       10.6 cm (0.99x)       5.3 cm (0.49x)     4.3 (0.40x)

against a signal of 10.7 cm. **A single rep is not enough and a set is.** Since
a per-set c2 is the right granularity anyway, and captures 60% of the gain,
a paused-at-25% set of 4-6 reps is the experiment that would settle this.

Nothing is proposed for `src/`.

    python3 analysis/85_third_constraint.py
"""
from __future__ import annotations

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
OUT = ROOT / "analysis" / "85_third_constraint.png"
STRAPPED = "deadlift_160x6_1_20260818"
N = 128
S = np.linspace(0.0, 1.0, N)
BUMP = S ** 2 - S
BB = float(BUMP @ BUMP)


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
        t, lift = res["log"]["t"], capture.lift_of(csv)
        for pr in vs["per_rep"]:
            if not pr.get("covered"):
                continue
            a, z = res["bounds"][pr["rep"]]
            T = float(t[z - 1] - t[a])
            v = _resamp(np.asarray(pr["curve_video"], float))
            p = _resamp(np.asarray(pr["curve_pipeline"], float))
            e = ((p - p[0] + v[0]) - v)[:, 0]
            k = int(np.argmin(v[:, 1])) if lift != "deadlift" \
                else int(np.argmax(v[:, 1]))
            dt = T / (N - 1)
            out.append(dict(capture=csv.stem, lift=lift, T=T,
                            c2=float((e @ BUMP) / BB), e=e,
                            before=float(np.sqrt((e ** 2).mean()) * 100),
                            turn_phase=S[k],
                            vh_turn=abs(float(np.gradient(v[:, 0], dt)[k])),
                            vh_typ=float(np.percentile(
                                np.abs(np.gradient(v[:, 0], dt)), 75)),
                            dv_turn=abs(float(np.gradient(p[:, 0], dt)[k]
                                              - np.gradient(v[:, 0], dt)[k]))))
    return out


def rms_for(r, c):
    """|e - c*BUMP| in cm, from the identity, without re-storing e."""
    return float(np.sqrt(((r["e"] - c * BUMP) ** 2).mean()) * 100)


def main():
    reps = collect()
    lifts = ("bench", "deadlift", "squat")
    import collections
    by_set = collections.defaultdict(list)
    by_lift = collections.defaultdict(list)
    for r in reps:
        by_set[r["capture"]].append(r)
        by_lift[r["lift"]].append(r)

    print(f"{len(reps)} reps\n\nWHAT c2 IS WORTH, and how coarse it may be")
    print(f"{'lift':10s} {'ships':>7s} {'global':>7s} {'per-lift':>9s} "
          f"{'per-set':>8s} {'per-rep':>8s}")
    g_all = np.median([r["c2"] for r in reps])
    lift_c = {l: np.median([r["c2"] for r in v]) for l, v in by_lift.items()}
    set_c = {k: np.median([r["c2"] for r in v]) for k, v in by_set.items()}
    for lf in lifts + ("ALL",):
        rr = reps if lf == "ALL" else by_lift[lf]
        print(f"{lf:10s} {np.median([r['before'] for r in rr]):7.2f} "
              f"{np.median([rms_for(r, g_all) for r in rr]):7.2f} "
              f"{np.median([rms_for(r, lift_c[r['lift']]) for r in rr]):9.2f} "
              f"{np.median([rms_for(r, set_c[r['capture']]) for r in rr]):8.2f} "
              f"{np.median([rms_for(r, r['c2']) for r in rr]):8.2f}")

    print("\nSOURCE 3 — the turnaround")
    print(f"{'lift':10s} {'turn phase':>11s} {'|v_h| vs typical':>17s}")
    for lf in lifts:
        rr = by_lift[lf]
        print(f"{lf:10s} {np.median([r['turn_phase'] for r in rr]):11.2f} "
              f"{np.median([r['vh_turn'] / r['vh_typ'] for r in rr]):17.2f}")
    print("   singular at phase 0.50 — the turnaround is mid-motion by definition")

    print("\nSOURCE 2 — dispersion's leverage")
    rs, spread = [], []
    for k, v in by_set.items():
        if len(v) < 4:
            continue
        T2 = np.array([r["T"] ** 2 for r in v])
        c2 = np.array([r["c2"] for r in v])
        spread.append((T2.max() - T2.min()) / T2.mean())
        if T2.std() > 1e-9:
            rs.append(np.corrcoef(T2, c2)[0, 1])
    print(f"   within-set T^2 spread {100 * np.median(spread):.0f}% of the mean; "
          f"the rest is common-mode and invisible")
    print(f"   within-set r(T^2, c2) = {np.median(rs):+.2f} over {len(rs)} sets, "
          f"where a constant `a` predicts +1")

    print("\nWHAT AN OFF-CENTRE PAUSE WOULD BUY")
    sv = np.median([r["dv_turn"] for r in reps if r["lift"] != "deadlift"])
    T = np.median([r["T"] for r in reps])
    sig = np.median([abs(r["c2"]) for r in reps])
    print(f"   IMU horizontal velocity error at a still instant: {sv*100:.2f} cm/s")
    print(f"   {'phase':>7s} {'per rep':>18s} {'over 4 reps':>16s} {'over 6':>14s}")
    for s_ in (0.30, 0.25, 0.20):
        s1 = sv * T / abs(2 * s_ - 1)
        print(f"   {s_:7.2f} {100*s1:9.1f} cm ({s1/sig:.2f}x) "
              f"{100*s1/2:8.1f} ({s1/2/sig:.2f}x) {100*s1/np.sqrt(6):8.1f} "
              f"({s1/np.sqrt(6)/sig:.2f}x)")
    print(f"   against a signal of {sig*100:.1f} cm")

    figure(reps, by_lift, by_set, lifts, sv, T, sig)


def figure(reps, by_lift, by_set, lifts, sv, T, sig):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    C = {"bench": "#2f7fbf", "deadlift": "#c1352c", "squat": "#a96a13"}
    fig, axs = plt.subplots(1, 3, figsize=(15, 4.6))

    ax = axs[0]
    g_all = np.median([r["c2"] for r in reps])
    lift_c = {l: np.median([r["c2"] for r in v]) for l, v in by_lift.items()}
    set_c = {k: np.median([r["c2"] for r in v]) for k, v in by_set.items()}
    labels = ["ships", "global", "per-lift", "per-set", "per-rep"]
    for lf in lifts:
        rr = by_lift[lf]
        vals = [np.median([r["before"] for r in rr]),
                np.median([rms_for(r, g_all) for r in rr]),
                np.median([rms_for(r, lift_c[lf]) for r in rr]),
                np.median([rms_for(r, set_c[r["capture"]]) for r in rr]),
                np.median([rms_for(r, r["c2"]) for r in rr])]
        ax.plot(labels, vals, "o-", color=C[lf], label=lf)
    ax.axhline(1.0, color="#2f855a", ls="--", lw=1.3, label="the 1 cm spec")
    ax.set_ylabel("horizontal rms, cm")
    ax.set_title("how coarse c2 may be (all oracles)", fontsize=10)
    ax.legend(fontsize=8)
    ax.tick_params(axis="x", labelrotation=20)

    ax = axs[1]
    for lf in lifts:
        rr = by_lift[lf]
        ax.scatter([r["turn_phase"] for r in rr],
                   [r["vh_turn"] / r["vh_typ"] for r in rr],
                   s=16, alpha=.7, color=C[lf], label=lf)
    ax.axvline(0.5, color="#c1352c", lw=1.4, ls="--")
    ax.annotate("no lever here", (0.5, 1.9), fontsize=8, color="#c1352c",
                ha="center")
    ax.set_xlabel("phase of the turnaround")
    ax.set_ylabel("horizontal speed there, vs typical")
    ax.set_title("the still instant sits where the lever vanishes", fontsize=10)
    ax.legend(fontsize=8)

    ax = axs[2]
    ph = np.linspace(0.15, 0.48, 80)
    for n, style in ((1, "-"), (4, "--"), (6, ":")):
        ax.plot(ph, 100 * sv * T / np.abs(2 * ph - 1) / np.sqrt(n), style,
                color="#10151c", label=f"{n} rep{'s' if n > 1 else ''}")
    ax.axhline(100 * sig, color="#2f855a", lw=1.4,
               label="the signal being estimated")
    ax.set_ylim(0, 40)
    ax.set_xlabel("phase of a cued pause")
    ax.set_ylabel("uncertainty in c2, cm")
    ax.set_title("what an off-centre pause would buy", fontsize=10)
    ax.legend(fontsize=8)

    fig.suptitle("H35 — a quadratic needs one number, and no current sensor "
                 "reading supplies it", fontsize=12)
    fig.tight_layout()
    fig.savefig(OUT, dpi=115)
    print(f"\nwrote {OUT}")


if __name__ == "__main__":
    main()
