"""H33 — reps do NOT start and end in the same place. What that costs, and what
fixing it would buy.

The owner: *"the assumption that reps start and end in the same place is
disproven by the video tracking."* He is right, and this measures the whole
chain: how far off closure the real bar is, how much of what step 7 removes was
ever real, and — the number that decides B3 — what a PERFECT non-closure
estimate would gain.

1. THE BAR DOES NOT CLOSE
    lift       n    median |dh|   p90    max
    bench      39      1.39 cm    2.61   5.94
    deadlift   39      1.77       3.29   6.03
    squat      33      1.49       4.53   5.88

Over 111 refereed reps the median horizontal non-closure is **1.61 cm against a
~1 cm spec**, only 33% of reps close to within that spec, and the miss is 19-28%
of the rep's own fore-aft excursion. The assumption is false and it is not
marginally false.

2. BUT STEP 7 IS NOT MAINLY DESTROYING IT
Per-rep net displacement, median absolute, cm:

    lift       reconstruction (removed)   video (real)   real fraction
    bench             50.30                   1.39            3 %
    deadlift         454.39                   1.77            0 %
    squat            445.68                   1.49            0 %

**97-100% of what the detrend removes is integration drift.** The detrend has to
stay. And the reconstruction carries NO information about the true non-closure
— correlation between the two columns is -0.26 to +0.09 across lifts and axes —
so B3's estimator cannot come from the reconstruction's own drift.

3. THE COST OF FORCING CLOSURE
A linear ramp removing Delta contributes Delta/sqrt(3) rms over the rep, so the
injected error is 0.80 cm on bench, 1.02 on deadlift, 0.86 on squat. **About the
whole horizontal spec, and roughly half the typical 2.4 cm error.**

4. AND FIXING IT DOES NOT HELP — THIS IS THE RESULT THAT DECIDES B3
Re-detrend every rep to close on the video's TRUE net displacement instead of on
zero, then re-score. This is an oracle: it uses the answer, so it is the ceiling
on any estimator that could ever be built.

    lift       shipped   closed   ORACLE    gain
    bench        2.08     2.08     1.93    +0.15
    deadlift     3.11     3.11     2.78    +0.33
    squat        2.58     2.58     3.19    -0.61
    ALL          2.40     2.40     2.58    -0.18

Better on **50% of 111 reps**, median -0.02 cm. (`closed` re-derives the shipped
number here as a control and matches it exactly, so the re-implementation of
step 7 is faithful.)

**Knowing the true non-closure perfectly does not improve the reconstruction.**
The endpoint is not where the error lives — P3 says the error is at rep
frequency, distributed through the rep, and correcting one endpoint pivots the
whole curve about its start without touching the middle. On squat that pivot is
actively harmful.

5. WHAT IS STILL WORTH KNOWING
The non-closure is not the same animal on every lift. Sign-consistency within a
set, |sum| / sum|.|, against the ~1/sqrt(n) a coin flip would give:

    deadlift   0.20  (chance 0.49)   set total +0.44 cm, p = 0.65
    bench      0.54  (chance 0.42)   set total -3.28 cm, p = 0.051
    squat      0.73  (chance 0.52)   set total -4.68 cm, p = 0.095, 2 of 8 sets unanimous

**Deadlift is BELOW chance — the misses actively cancel.** The bar is set down
in the same place each rep, so the SET closes even though the reps do not.
Squat and bench WALK, both in the same direction, a few cm per set. n = 7-9 sets
per lift and p = 0.05-0.10, so this is suggestive, not established.

    python3 analysis/83_nonclosure.py
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
OUT = ROOT / "analysis" / "83_nonclosure.png"
STRAPPED = "deadlift_160x6_1_20260818"


def detrend_to(curve, target):
    """Per-rep linear detrend landing on `target` net displacement."""
    s = np.linspace(0.0, 1.0, len(curve))[:, None]
    return curve - s * ((curve[-1] - curve[0]) - target)


def collect():
    warnings.simplefilter("ignore")
    out = []
    for csv in sorted(RAW.glob("*.csv")):
        if STRAPPED in csv.stem:
            continue
        short = csv.stem.rsplit("_", 1)[0]
        tp = TRACKED / f"{short}.csv"
        if not tp.is_file():
            continue
        try:
            res = pipeline.run(csv)
            vs = metrics.vs_truth(res, tracked.read(None, src=tp))
        except Exception:
            continue
        reps = []
        for pr in vs["per_rep"]:
            if not pr.get("covered") or "curve_raw" not in pr:
                continue
            raw = np.asarray(pr["curve_raw"], float)
            vid = np.asarray(pr["curve_video"], float)
            closed = detrend_to(raw, np.zeros(2))
            oracle = detrend_to(raw, vid[-1] - vid[0])

            def rms(a):
                a = a - a[0] + vid[0]
                return float(np.sqrt(((a[:, 0] - vid[:, 0]) ** 2).mean()) * 100)

            reps.append(dict(
                k=pr["rep"], lift=capture.lift_of(csv),
                dh=float((vid[-1, 0] - vid[0, 0]) * 100),
                dv=float((vid[-1, 1] - vid[0, 1]) * 100),
                rec_dh=float((raw[-1, 0] - raw[0, 0]) * 100),
                rec_dv=float((raw[-1, 1] - raw[0, 1]) * 100),
                ex=pr["video_fore_aft_cm"], rom=pr["video_rom_cm"],
                shipped=pr["pipeline_h_rms"], closed=rms(closed),
                oracle=rms(oracle), null=pr["null_h_rms"]))
        if reps:
            out.append((csv.stem, capture.lift_of(csv), reps))
    return out


def main():
    sets = collect()
    reps = [r for _, _, rr in sets for r in rr]
    lifts = sorted({r["lift"] for r in reps})

    print("1. HOW FAR THE REAL BAR MISSES CLOSING")
    print(f"   {'lift':10s} {'n':>4s} {'med |dh|':>9s} {'p90':>6s} {'max':>6s} "
          f"{'as % of excursion':>19s}")
    for lf in lifts:
        a = np.array([[abs(r["dh"]), r["ex"]] for r in reps if r["lift"] == lf])
        print(f"   {lf:10s} {len(a):4d} {np.median(a[:,0]):9.2f} "
              f"{np.percentile(a[:,0],90):6.2f} {a[:,0].max():6.2f} "
              f"{100*np.median(a[:,0]/a[:,1]):18.0f}%")
    h = np.array([abs(r["dh"]) for r in reps])
    print(f"   ALL {len(h):d} reps: median {np.median(h):.2f} cm; "
          f"{100*(h<1).mean():.0f}% close inside the 1 cm spec")

    print("\n2. WHAT STEP 7 REMOVES, AND HOW MUCH OF IT WAS REAL")
    print(f"   {'lift':10s} {'removed':>10s} {'real':>8s} {'fraction':>9s} "
          f"{'corr(removed, real)':>20s}")
    for lf in lifts:
        a = np.array([[abs(r["rec_dh"]), abs(r["dh"])] for r in reps
                      if r["lift"] == lf])
        s = np.array([[r["rec_dh"], r["dh"]] for r in reps if r["lift"] == lf])
        print(f"   {lf:10s} {np.median(a[:,0]):10.2f} {np.median(a[:,1]):8.2f} "
              f"{100*np.median(a[:,1])/np.median(a[:,0]):8.0f}% "
              f"{np.corrcoef(s[:,0], s[:,1])[0,1]:+20.3f}")

    print("\n3. THE ORACLE — knowing the true closure exactly")
    print(f"   {'lift':10s} {'shipped':>8s} {'closed':>8s} {'ORACLE':>8s} "
          f"{'gain':>7s}")
    for lf in lifts + ["ALL"]:
        rr = reps if lf == "ALL" else [r for r in reps if r["lift"] == lf]
        a = np.array([[r["shipped"], r["closed"], r["oracle"]] for r in rr])
        print(f"   {lf:10s} {np.median(a[:,0]):8.2f} {np.median(a[:,1]):8.2f} "
              f"{np.median(a[:,2]):8.2f} "
              f"{np.median(a[:,1])-np.median(a[:,2]):+7.2f}")
    a = np.array([[r["closed"], r["oracle"]] for r in reps])
    print(f"   better on {100*(a[:,1]<a[:,0]).mean():.0f}% of {len(a)} reps")

    print("\n4. WALK OR WOBBLE, per lift")
    for lf in lifts:
        rs, tot = [], []
        for _, lift, rr in sets:
            if lift != lf or len(rr) < 3:
                continue
            d = np.array([r["dh"] for r in rr])
            rs.append(abs(d.sum()) / np.abs(d).sum())
            tot.append(d.sum())
        if not rs:
            continue
        chance = np.mean([1 / np.sqrt(len([r for r in rr])) for _, l, rr in sets
                          if l == lf and len(rr) >= 3])
        t, p = stats.ttest_1samp(tot, 0)
        print(f"   {lf:10s} n={len(rs)} sets  ratio {np.median(rs):.2f} "
              f"(chance {chance:.2f})  set total {np.mean(tot):+6.2f} cm, p={p:.3f}")

    figure(sets, reps, lifts)


def figure(sets, reps, lifts):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    fig, axs = plt.subplots(1, 3, figsize=(15, 4.6))
    C = {"bench": "#2f7fbf", "deadlift": "#c1352c", "squat": "#a96a13"}

    ax = axs[0]
    for lf in lifts:
        d = np.abs([r["dh"] for r in reps if r["lift"] == lf])
        ax.hist(d, bins=np.arange(0, 7, .5), alpha=.55, label=lf, color=C[lf])
    ax.axvline(1.0, color="#2f855a", ls="--", lw=1.4, label="the 1 cm spec")
    ax.set_xlabel("|horizontal non-closure|, cm")
    ax.set_ylabel("reps")
    ax.set_title("1. the bar does not close", fontsize=10)
    ax.legend(fontsize=8)

    ax = axs[1]
    for lf in lifts:
        x = [abs(r["rec_dh"]) for r in reps if r["lift"] == lf]
        y = [abs(r["dh"]) for r in reps if r["lift"] == lf]
        ax.scatter(x, y, s=16, alpha=.7, color=C[lf], label=lf)
    ax.set_xscale("log")
    ax.set_xlabel("what step 7 removes, cm (log)")
    ax.set_ylabel("what was real, cm")
    ax.set_title("2. 97-100% of it is drift, and the two do not correlate",
                 fontsize=10)
    ax.legend(fontsize=8)

    ax = axs[2]
    w = .35
    xs = np.arange(len(lifts))
    cl = [np.median([r["closed"] for r in reps if r["lift"] == lf]) for lf in lifts]
    orc = [np.median([r["oracle"] for r in reps if r["lift"] == lf]) for lf in lifts]
    ax.bar(xs - w/2, cl, w, label="forced closed (ships)", color="#7b8694")
    ax.bar(xs + w/2, orc, w, label="oracle: true closure", color="#2f855a")
    ax.set_xticks(xs)
    ax.set_xticklabels(lifts)
    ax.set_ylabel("horizontal rms vs video, cm")
    ax.set_title("3. and knowing the answer does not help", fontsize=10)
    ax.legend(fontsize=8)

    fig.suptitle("H33 — reps do not close, step 7 forces them to, and correcting "
                 "that is worth nothing", fontsize=12)
    fig.tight_layout()
    fig.savefig(OUT, dpi=115)
    print(f"\nwrote {OUT}")


if __name__ == "__main__":
    main()
