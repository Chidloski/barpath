"""H33 — why five captures miscount, and what the segmenter already knows.

The owner asked for a deep dive on the segmentation errors. Two distinct
mechanisms, and neither is the one `TASKS.md` recorded.

MECHANISM 1 — THE CLUSTER DISCARDS REPS IT HAS ALREADY IDENTIFIED
------------------------------------------------------------------
`squat_140x4_1`, `squat_140x4_2` and `squat_pause_140x4_1` count 3, 2 and 3
against a labelled 4. **All four reps are present as concentric lobes in every
one of them**, and the fourth discriminator separates them from everything else
by a factor of ten:

    squat_140x4_1   upright ratios  16.8 16.2 13.9 13.5 | 1.3 0.8 ...
    squat_140x4_2                   16.5 16.4 14.3 14.1 | 0.8 0.7 ...
    squat_pause_140x4_1             12.4 10.9  9.6  9.5 | 1.2 0.9 ...

The four on the left are the reps. `_similar_cluster` keeps three, two and
three of them. It is not `_upright` doing the damage — that stage drops nothing
on any of the three — and it is not `peak_ratio`: peak speed declines
monotonically across a set as the lifter fatigues (0.669 -> 0.586 -> 0.546 ->
0.493 on `squat_140x4_1`), a spread of 1.36x against a 2.5x limit.

**`TASKS.md` recorded these as "dropped across a long cadence gap" and that is
FALSIFIED here.** The failing sets do have a lengthening cadence — but so do the
passing ones, and more so. Last gap over first gap:

    PASSES  squat_155x4_3 1.68   squat_pause_140x4_3 1.59   squat_pause_140x4_2 1.53
    FAILS   squat_140x4_1 1.54   squat_140x4_2 1.42   squat_pause_140x4_1 1.27

The most irregular set in the corpus counts correctly and the most regular
failure is the least irregular of the six. Cadence does not separate them.

MECHANISM 2 — A SPURIOUS PAIR OUTVOTES A REAL SINGLE
-----------------------------------------------------
`squat_170x1_20260820` and `deadlift_210x1_20260815` both find 2 windows for a
labelled 1. In both, the winning cluster is a mutually-similar pair drawn from
the setup, and the real rep is a cluster of ONE:

    squat_170x1_20260820   chosen 4.40 s + 8.71 s (walkout, unrack)
                           real rep at 33.69 s — largest area in the capture
    deadlift_210x1         chosen 13.22 s + 20.38 s
                           real pull at 24.80 s — area 0.737 and peak 2.07 m/s,
                           both the largest in the capture by a wide margin

`_similar_cluster`'s docstring already anticipates this failure and fixes it for
`squat_160x1` by ranking SINGLETONS on concentric displacement. **That rule
never engages here, because it guards a winning cluster of size 1 and the
winner here has size 2.** A spurious pair beats a real single on size before
lateness or displacement is consulted.

`squat_170x1_20260820` fails twice over: its real rep scores an upright ratio of
**0.63**, against 8.3-23.4 for every other squat rep in the corpus, so the
fourth discriminator could not have rescued it either. That capture needs its
own explanation and does not have one.

WHAT THE MEASUREMENT LICENSES, AND WHAT IT DOES NOT
----------------------------------------------------
Cutting the sorted upright ratios at their largest multiplicative gap — an
argmax, not a fitted threshold, the same shape as the singleton rule — gives, on
the velocity path:

    lift       shipping   cliff rule
    bench         9 / 9      9 / 9
    squat         9 / 13    12 / 13
    deadlift      1 / 2      0 / 2

**It is a lead, not a fix.** It recovers all three mechanism-1 squats and costs
`deadlift_200x1`, which currently counts correctly; deadlifts reaching the
velocity path are singles, where there is no cliff to find. Nothing is proposed
for `src/` here.

    python3 analysis/82_segmentation_deepdive.py
"""
from __future__ import annotations

import sys
import warnings
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src import pipeline, segment as S   # noqa: E402

RAW = ROOT / "data_v2" / "raw"
OUT = ROOT / "analysis" / "82_segmentation_deepdive.png"


def lobes_of(csv):
    res = pipeline.run(csv)
    log, t = res["log"], res["log"]["t"]
    v = S.bandpass(res["velocity"][:, 2], log["fs"])
    lob = S._concentric_lobes(v, t, 0.08)
    allb = S._all_lobes(v, t, 0.08)
    anchors = S.impact_anchors(log)
    up = S._upright_ratios(allb, lob, res["position"], t, len(v))
    chosen = {l[1] for l in S._similar_cluster(v, t, lob, 0.7, 2.5, up)}
    return dict(res=res, t=t, v=v, lobes=lob, up=up, chosen=chosen,
                path="impact" if len(anchors) >= 3 else "velocity",
                exp=pipeline.expected_reps(csv), got=len(res["bounds"]))


def cliff(ups):
    u = np.array(sorted([x for x in ups if x > 0], reverse=True))
    if len(u) < 2:
        return len(u)
    return int(np.argmax(u[:-1] / np.maximum(u[1:], 1e-9))) + 1


def main():
    warnings.simplefilter("ignore")
    rows = []
    for csv in sorted(RAW.glob("*.csv")):
        d = lobes_of(csv)
        ups = [d["up"].get(a, 0.0) for _, a, _, _ in d["lobes"]]
        rows.append((csv.stem, csv.stem.split("_")[0], d, ups, cliff(ups)))

    print(f"{'capture':34s} {'path':9s} {'lab':>3s} {'now':>3s} {'cliff':>5s}  "
          f"upright ratios, sorted")
    for stem, lift, d, ups, c in rows:
        tag = "" if d["got"] == d["exp"] else "  MISCOUNT"
        fx = "  <- cliff fixes" if d["got"] != d["exp"] and c == d["exp"] else ""
        br = "  <- cliff breaks" if d["got"] == d["exp"] and c != d["exp"] else ""
        top = " ".join(f"{u:.1f}" for u in sorted(ups, reverse=True)[:6])
        print(f"{stem[:34]:34s} {d['path']:9s} {d['exp']:3d} {d['got']:3d} "
              f"{c:5d}  {top}{tag}{fx}{br}")

    for lift in ("bench", "squat", "deadlift"):
        g = [(d, c) for _, lf, d, _, c in rows if lf == lift]
        gv = [(d, c) for d, c in g if d["path"] == "velocity"]
        print(f"\n{lift:9s} shipping {sum(1 for d,_ in g if d['got']==d['exp'])}/{len(g)}"
              f"   cliff {sum(1 for d,c in g if c==d['exp'])}/{len(g)}"
              f"   (velocity path: shipping "
              f"{sum(1 for d,_ in gv if d['got']==d['exp'])}/{len(gv)}, "
              f"cliff {sum(1 for d,c in gv if c==d['exp'])}/{len(gv)})")

    figure(rows)


def figure(rows):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    cases = ["squat_140x4_1_20260813", "squat_140x4_2_20260813",
             "squat_pause_140x4_1_20260820", "squat_135x4_1_20260817",
             "squat_170x1_20260820", "deadlift_210x1_20260815"]
    pick = [r for c in cases for r in rows if r[0].startswith(c)]
    fig, axs = plt.subplots(2, 3, figsize=(15, 8))
    for ax, (stem, lift, d, ups, c) in zip(axs.ravel(), pick):
        t, v = d["t"], d["v"]
        ax.plot(t, v, lw=.6, color="#8a94a3")
        for (peak, a, b, area) in d["lobes"]:
            u = d["up"].get(a, 0.0)
            inc = a in d["chosen"]
            ax.axvspan(t[a], t[b - 1], alpha=.5 if inc else .16,
                       color="#2f855a" if inc else "#c1352c", lw=0)
            ax.text(t[a], ax.get_ylim()[1] * .88, f"{u:.1f}", fontsize=7,
                    color="#10151c", ha="left")
        ok = d["got"] == d["exp"]
        ax.set_title(f"{stem[:30]}\nlabelled {d['exp']}, found {d['got']}"
                     f"{'' if ok else '  MISCOUNT'}", fontsize=9,
                     color="#2f855a" if ok else "#c1352c")
        ax.set_xlabel("t, s", fontsize=8)
        ax.set_ylabel("band-passed vertical velocity", fontsize=8)
        ax.tick_params(labelsize=7)
    fig.suptitle("H33 — green = kept by _similar_cluster, red = discarded. "
                 "Numbers are the upright ratio: the reps are unmistakable and "
                 "some are thrown away anyway.", fontsize=11)
    fig.tight_layout()
    fig.savefig(OUT, dpi=115)
    print(f"\nwrote {OUT}")


if __name__ == "__main__":
    main()
