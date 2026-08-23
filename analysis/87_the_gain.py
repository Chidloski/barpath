"""H37 — the 0.17 explained: it is arithmetic, and it is the right number.

H36 found that the rest-to-rest velocity change predicts the mid-rep bump
(Pearson +0.594, p = 0.001) but is 3.9x too large, and needed a gain of 0.173 to
be usable. The owner asked what that gain is. It is not a fudge and it is not a
physical scaling — it is the ordinary least-squares attenuation factor, and the
identity reproduces it to three decimals.

1. THE GAIN IS ARITHMETIC
    sd(a_oracle)                 0.0261 m/s^2
    sd(a_est)                    0.0895
    Pearson r                    +0.594
    predicted slope r*sd_o/sd_e  +0.173
    MEASURED OLS slope           +0.173

If `a_est` carries noise, the regression of the truth on it is attenuated by
exactly this factor. So the gain is not describing a physical process that
shrinks the signal by 6x; it is the statistically correct shrinkage of a noisy
predictor, and `r^2 = 0.35` says 65% of `a_est`'s variance does not map to the
bump. The question "why 0.17" becomes "what is that 65%".

2. IT IS NOT THE REST ANCHORS
`segment.rest_instants` is validated at |v| < 0.10 m/s, which sounded like it
might swamp a signal of a*span ~ 0.08 m/s. Measured against the video at the 35
rest instants the corpus holds, the bar's real speed there is a median of
**0.0168 m/s horizontally** — 0.2x the signal, and 0.3x for a difference of two.
The anchors are better than their own tolerance and are not the problem.

3. IT CANNOT BE FIXED BY EXCISING THE IMPACT, AND THAT IS THE INTERESTING PART
The obvious suspect was the landing: its impulse is not a constant acceleration,
so it should inflate `dv_h` without contributing to the bump. Split the interval
at the impact and the suspicion inverts:

    estimator                 sd      r vs oracle    p
    rest-to-rest (H36)      0.0895      +0.594     0.0011
    pull only, pre-impact   0.0881      +0.200     0.32
    post-ring only          0.4304      -0.164     0.41
    ring EXCISED            0.1010      +0.050     0.80

**Excising the ring destroys the signal entirely.** The reason is that only the
full interval brackets two instants where the TRUE velocity is zero. A
sub-interval ending at the impact does not: the bar is genuinely moving there, so
its `dv` mixes real motion with error and measures neither. The zero-velocity
bracketing is the whole validity of the measurement, and the impact sits inside
it and cannot be taken out.

4. THE LANDING AND THE TILT ARE NOT INDEPENDENT
    ring dv/T vs a_est                  r +0.684 (p = 0.0001)   47% of variance
    ring dv/T vs a_oracle (the bump)    r +0.421 (p = 0.029)
    ring dv/T vs the UNEXPLAINED part   r -0.018 (p = 0.93)

The ring explains more of `a_est` than the bump does — but it is itself
correlated with the bump, and it explains none of the residual. A larger tilt
error inflates both the bump and the apparent impulse, because the impulse is
measured in the same tilted frame. So "constant acceleration plus impulse" is
not a decomposition this data supports; the two covary and no split separates
them.

WHAT THIS MEANS FOR THE CORRECTION
-----------------------------------
The gain is doing what a gain should: shrinking a noisy but genuine predictor by
the optimal amount. Its stability across held-out captures (0.157-0.218 on eight
of nine) says it is a population parameter and not a fit to this corpus. **So it
should be treated as a calibrated constant with a known meaning, not as a fudge
factor to be explained away.**

To do better, reduce `sd(a_est)` — the leverage is entirely there, since the
gain rises toward 1 as the noise falls. Averaging over a set was tried and LOSES
(3.10 -> 3.11 against per-rep's 2.66), because the oracle `a` genuinely varies
rep to rep and averaging discards that. What would help is a less noisy velocity
error at the anchors, which is a sensing question, not an algorithmic one.

    python3 analysis/87_the_gain.py
"""
from __future__ import annotations

import sys
import warnings
from pathlib import Path

import numpy as np
from scipy import stats

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src import metrics, oracle, pipeline, segment, tracked   # noqa: E402

RAW = ROOT / "data_v2" / "raw"
TRACKED = ROOT / "data_v2" / "tracked"
OUT = ROOT / "analysis" / "87_the_gain.png"
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
    rows, anchor_v = [], []
    for csv in sorted(RAW.glob("deadlift*.csv")):
        if STRAPPED in csv.stem:
            continue
        tp = TRACKED / f"{csv.stem.rsplit('_', 1)[0]}.csv"
        if not tp.is_file():
            continue
        try:
            res = pipeline.run(csv)
            path = tracked.read(None, src=tp)
            m = metrics.vs_truth(res, path)
            rest = segment.rest_instants(res["log"], res["impacts"])
        except Exception:
            continue
        if len(rest) < 2:
            continue
        t, vel = res["log"]["t"], res["velocity"]
        axis = np.real(np.asarray(m["axis"], float))[:2]
        axis = axis / np.linalg.norm(axis)
        sign = -1.0 if m["axis_flipped"] else 1.0
        imp = sorted(res["impacts"])

        # how still the anchors really are, from the video
        off, slope = m.get("sync_offset"), m.get("sync_slope") or 1.0
        if off is not None:
            vt = (np.asarray(path["t"]) - off) / slope
            vx = np.asarray(path["x"])
            ok = np.isfinite(vt) & np.isfinite(vx)
            if ok.sum() > 10:
                d = np.gradient(vx[ok], vt[ok])
                for i in rest:
                    if vt[ok][0] <= t[i] <= vt[ok][-1]:
                        anchor_v.append(abs(float(np.interp(t[i], vt[ok], d))))

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
            inside = [k for k in imp if i0 < k < i1]
            if not inside:
                continue
            k_imp = inside[-1]
            dur, _ = oracle.ring_duration(res["log"], k_imp)
            k_end = min(i1, k_imp + int(dur * res["log"]["fs"]))

            def dv(a_, b_):
                return sign * float((vel[b_, :2] - vel[a_, :2]) @ axis)

            a_, z = res["bounds"][best[1]]
            T = float(t[z - 1] - t[a_])
            v = _resamp(np.asarray(pr["curve_video"], float))
            p = _resamp(np.asarray(pr["curve_pipeline"], float))
            e = ((p - p[0] + v[0]) - v)[:, 0]
            c2 = float((e @ BUMP) / BB)
            span_ex = (t[k_imp] - t[i0]) + (t[i1] - t[k_end])
            rows.append(dict(
                cap=csv.stem, T=T, a_o=2 * c2 / T ** 2,
                full=dv(i0, i1) / (t[i1] - t[i0]),
                pre=dv(i0, k_imp) / max(t[k_imp] - t[i0], 1e-6),
                post=dv(k_end, i1) / max(t[i1] - t[k_end], 1e-6),
                exring=(dv(i0, k_imp) + dv(k_end, i1)) / max(span_ex, 1e-6),
                ring=dv(k_imp, k_end)))
    return rows, np.array(anchor_v)


def main():
    rows, anchor_v = collect()
    ao = np.array([r["a_o"] for r in rows])
    ae = np.array([r["full"] for r in rows])
    r_, _ = stats.pearsonr(ao, ae)
    beta = np.polyfit(ae, ao, 1)[0]

    print(f"{len(rows)} intervals\n\n1. THE GAIN IS ARITHMETIC")
    print(f"   sd(a_oracle) {ao.std():.4f}   sd(a_est) {ae.std():.4f}")
    print(f"   Pearson r {r_:+.3f}")
    print(f"   predicted r*sd_o/sd_e = {r_ * ao.std() / ae.std():+.3f}")
    print(f"   measured OLS slope    = {beta:+.3f}")
    print(f"   r^2 = {r_**2:.2f}, so {100*(1-r_**2):.0f}% of a_est is not the bump")

    print(f"\n2. NOT THE ANCHORS — {len(anchor_v)} rest instants, video's own speed")
    print(f"   |v_h| median {np.median(anchor_v):.4f} m/s = "
          f"{np.median(anchor_v)/(ao.std()*3.1):.1f}x the signal")

    print("\n3. AND NOT REMOVABLE — split the interval at the impact")
    print(f"   {'estimator':24s} {'sd':>8s} {'r':>8s} {'p':>8s}")
    for k, lab in (("full", "rest-to-rest (H36)"), ("pre", "pull only"),
                   ("post", "post-ring only"), ("exring", "ring EXCISED")):
        x = np.array([r[k] for r in rows])
        rr, pp = stats.pearsonr(ao, x)
        print(f"   {lab:24s} {x.std():8.4f} {rr:+8.3f} {pp:8.4f}")
    print("   only the full interval brackets two TRUE zeros; a sub-interval")
    print("   ending at the impact mixes real motion with error")

    print("\n4. THE LANDING AND THE TILT COVARY")
    ring = np.array([r["ring"] for r in rows]) / np.array([r["T"] for r in rows])
    fit = np.polyfit(ae, ao, 1)
    unex = ae - (ao - fit[1]) / fit[0]
    for lab, y in (("a_est", ae), ("a_oracle (the bump)", ao),
                   ("the unexplained part", unex)):
        rr, pp = stats.pearsonr(ring, y)
        print(f"   ring dv/T vs {lab:22s} r {rr:+.3f} (p={pp:.4f})")

    figure(rows, ao, ae, ring, anchor_v, beta, r_)


def figure(rows, ao, ae, ring, anchor_v, beta, r_):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    fig, axs = plt.subplots(1, 3, figsize=(15, 4.6))

    ax = axs[0]
    ax.scatter(ae, ao, s=28, color="#c1352c", alpha=.8)
    xs = np.linspace(ae.min(), ae.max(), 20)
    ax.plot(xs, beta * xs + np.polyfit(ae, ao, 1)[1], color="#10151c", lw=1.5,
            label=f"OLS slope {beta:.3f}")
    ax.plot(xs, xs, ls="--", color="#7b8694", lw=1.2, label="slope 1")
    ax.set_xlabel("a from rest-to-rest, m/s²")
    ax.set_ylabel("a the bump implies, m/s²")
    ax.set_title(f"the gain is r·sd$_o$/sd$_e$ = {r_ * ao.std() / ae.std():.3f}",
                 fontsize=10)
    ax.legend(fontsize=8)

    ax = axs[1]
    names, vals = [], []
    for k, lab in (("full", "rest-to-rest"), ("pre", "pull only"),
                   ("post", "post-ring"), ("exring", "ring excised")):
        x = np.array([r[k] for r in rows])
        names.append(lab)
        vals.append(stats.pearsonr(ao, x)[0])
    cols = ["#2f855a" if v > 0.4 else "#c1352c" for v in vals]
    ax.bar(names, vals, color=cols)
    ax.axhline(0, color="k", lw=.6)
    for i, v in enumerate(vals):
        ax.text(i, v, f"{v:+.2f}", ha="center",
                va="bottom" if v > 0 else "top", fontsize=9)
    ax.set_ylabel("r vs the oracle bump")
    ax.set_title("excising the impact destroys it", fontsize=10)
    ax.tick_params(axis="x", labelrotation=15)

    ax = axs[2]
    ax.hist(anchor_v, bins=14, color="#2f7fbf", alpha=.8)
    sig = ao.std() * 3.1
    ax.axvline(sig, color="#2f855a", lw=1.6, label="the signal being measured")
    ax.axvline(0.10, color="#c1352c", lw=1.4, ls="--",
               label="rest_instants' own tolerance")
    ax.set_xlabel("bar's real speed at a rest instant, m/s")
    ax.set_ylabel("instants")
    ax.set_title("the anchors are not the noise", fontsize=10)
    ax.legend(fontsize=8)

    fig.suptitle("H37 — the 0.17 is the optimal shrinkage of a noisy predictor, "
                 "not a fudge", fontsize=12)
    fig.tight_layout()
    fig.savefig(OUT, dpi=115)
    print(f"\nwrote {OUT}")


if __name__ == "__main__":
    main()
