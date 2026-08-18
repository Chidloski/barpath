"""H22 — the deadlift impulse: a pre-pull rest anchor and the rest PERIOD.

Renders `analysis/72_deadlift_rest_anchor.png` from
`analysis/72_deadlift_rest_anchor.json`, which is committed beside it so the
figure can be redrawn without re-running the corpus (as `analysis/68` and `70`
already do). Measurement only; no reconstruction module was written.

Owner's task: *"explore new ways to fix deadlifts ... see whether you can use
the impulse to your advantage or whether by overlapping reps slightly you can
more easily find a rest period. You know that the bounces at the drop will
decrease and the watch will move very little during the ringing."*

Three readings were tested and they came out very differently.

**The rest PERIOD is real and it is worth having.** The bar is genuinely still
for a median 0.96 s after each landing (37 landings, raw gyro and raw user
acceleration only), and there is a still interval before the FIRST pull on 9 of
9 deadlifts whose quiet score is *lower than every post-impact rest instant in
the same capture*. That anchor is what C29's frame was missing: it takes the
rest-to-rest frame from n-1 windows to n and recovers rep 1, which H19 recorded
as the one thing standing between C29 and shipping.

**Averaging over the period is what makes it pay.** Recovering rep 1 costs
accuracy on its own (2.00 -> 2.77 cm), because the recovered window is the
hardest in the set. Reading `dv` as the MEAN reconstructed velocity over the
still interval, instead of at the single quietest sample, buys it back
(2.98 -> 2.14). Neither change helps alone; only together — the same shape C29
itself had.

**Overlapping the windows LOSES**, which was the owner's literal suggestion and
is the cleanest negative here: of three boundary placements, overlapping is the
worst at every width tried (2.93 against 2.14 and 2.59 at 0.30 s).

**And "the watch barely moves during the ringing" cannot be spent, for a
structural reason.** Step 7's per-window linear detrend already absorbs any
CONSTANT velocity error, so an absolute zero-displacement statement is
invisible to the metric; imposing it inside one window only manufactures a
kink. Measured: a two-parameter correction zeroing both dv and the window's
displacement gives 11.53 cm against C29's 2.00, and a hard velocity clamp
gives 4.22.
"""
import json
import sys
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
GREEN, GREY, RED, BLUE, ORANGE = "#2e7d32", "#8b949e", "#c1362f", "#1b6ca8", "#e08214"
EXCLUDE = {"deadlift_160x6_1_20260818_123507",      # straps, H20
           "deadlift_170x4_3_20260808_122936",      # 22.8% clock drift, G3
           "deadlift_210x1_20260815_132206"}        # miscounts a single, H15
W = [0.05, 0.10, 0.15, 0.20, 0.25, 0.30, 0.40, 0.60]


def short(stem):
    name = stem.split("_2026")[0].replace("deadlift_", "")
    return f"{name}\n{stem.split('_2026')[1][:4]}"


def main():
    D = json.loads((ROOT / "analysis" / "72_deadlift_rest_anchor.json").read_text())
    fin = D["final"]
    caps = [k for k in fin if k not in EXCLUDE
            and "h" in fin[k].get("ship", {}) and "h" in fin[k].get("H22", {})]

    fig = plt.figure(figsize=(15.5, 12.4))
    gs = fig.add_gridspec(3, 3, hspace=0.52, wspace=0.34,
                          left=0.055, right=0.965, top=0.925, bottom=0.055)

    # A — one landing, drawn: the bounces decay, then the bar is STILL
    tr = D["trace"]
    t = np.array(tr["t"])
    ax = fig.add_subplot(gs[0, :2])
    ax.plot(t, tr["a"], lw=.8, color=RED, label="|a| (g), raw")
    pk = np.array(tr["peaks"])
    if len(pk):
        ax.plot(pk[:, 0], pk[:, 1] / 9.80665, "o", ms=3, color="#7a1d16",
                label=f"bounce peaks ({len(pk)}), decaying")
    still = np.array(tr["still"]).astype(bool)
    ax.fill_between(t, 0, 1, where=still, transform=ax.get_xaxis_transform(),
                    color=GREEN, alpha=.13, lw=0, label="still: |omega| < 0.6 rad/s and |a| < 4 m/s²")
    for r in tr["rest"]:
        ax.axvline(r, color="k", ls="--", lw=.9)
    ax.axvline(0, color=RED, ls=":", lw=.9)
    ax.axvspan(0, tr["ring"], color=RED, alpha=.07, lw=0)
    ax.text(tr["ring"] / 2, 0.86, f"ringing\n{tr['ring']:.2f} s", ha="center",
            transform=ax.get_xaxis_transform(), fontsize=7.5, color=RED)
    ax.set_ylabel("|a| (g)")
    ax.set_xlabel("s after impact onset")
    ax.legend(fontsize=7, loc="upper right")
    ax.set_title(f"A  one landing ({tr['cap']}): the bounces decay (median peak ratio 0.83) and a ~1 s rest PERIOD follows\n"
                 f"   dashed = the single sample `segment.rest_instants` returns; the green band is the interval it sits in",
                 fontsize=9.5, loc="left")

    # A2 — the same landing's reconstructed velocity
    ax = fig.add_subplot(gs[0, 2])
    for key, c, lbl in (("vx", BLUE, "v fore-aft"), ("vy", ORANGE, "v lateral"), ("vz", GREEN, "v up")):
        ax.plot(t, tr[key], lw=.9, color=c, label=lbl)
    ax.fill_between(t, 0, 1, where=still, transform=ax.get_xaxis_transform(),
                    color=GREEN, alpha=.13, lw=0)
    ax.axhline(0, color="#333", lw=.6)
    ax.axvline(0, color=RED, ls=":", lw=.9)
    ax.set_xlabel("s after impact onset"); ax.set_ylabel("reconstructed velocity (m/s)")
    ax.legend(fontsize=6.5)
    ax.set_title("A2  the bar is provably still in the green band\n"
                 "    and the reconstruction claims ~1 m/s there", fontsize=9.5, loc="left")

    # B — the pre-pull anchor is the QUIETEST instant in the capture
    ax = fig.add_subplot(gs[1, 0])
    names = list(D["quiet"])
    for i, n in enumerate(names):
        r = D["quiet"][n]["rest"]
        ax.scatter([i] * len(r), r, s=18, color=GREY, zorder=2,
                   label="post-impact rest instants" if i == 0 else None)
        if D["quiet"][n]["pre"] is not None:
            ax.scatter([i], [D["quiet"][n]["pre"]], s=44, marker="v", color=GREEN,
                       zorder=3, label="the PRE-PULL instant" if i == 0 else None)
    ax.set_yscale("log")
    ax.set_xticks(range(len(names)))
    ax.set_xticklabels([n.replace(" ", "\n") for n in names], fontsize=5.6)
    ax.set_ylabel("quiet score (accel var + gyro var)")
    ax.legend(fontsize=7)
    ax.set_title("B  the anchor C29's frame was missing exists,\n"
                 "   and it is quieter than every rest it already uses (9 of 9)",
                 fontsize=9.5, loc="left")

    # C — the ladder
    ax = fig.add_subplot(gs[1, 1:])
    arms = [("ship", "shipping\n(step 7 on impact windows)", BLUE),
            ("c29ctl", "C29 frame,\nNO correction", GREY),
            ("c29", "C29\n(rest instants)", "#7cb342"),
            ("c29pre", "C29\n+ pre-pull anchor", ORANGE),
            ("H22", "H22: period frame\n+ period-averaged dv", GREEN)]
    x = np.arange(len(arms))
    hs = [float(np.median([fin[k][a]["h"] for k in caps if "h" in fin[k].get(a, {})])) for a, _, _ in arms]
    ns = [sum(fin[k][a]["n"] for k in caps if "n" in fin[k].get(a, {})) for a, _, _ in arms]
    bn = [float(np.median([fin[k][a]["bn"] for k in caps if "bn" in fin[k].get(a, {})])) for a, _, _ in arms]
    ax.bar(x, hs, 0.6, color=[c for _, _, c in arms])
    for i, (h, n, b) in enumerate(zip(hs, ns, bn)):
        ax.text(i, h + 0.18, f"{h:.2f} cm\nbn {b:.2f}\n{n}/36 reps", ha="center", fontsize=7.4)
    ax.set_xticks(x); ax.set_xticklabels([l for _, l, _ in arms], fontsize=7.2)
    ax.set_ylabel("median horizontal rms (cm)")
    ax.set_ylim(0, max(hs) * 1.28)
    ax.set_title("C  the coverage blocker, closed: 23 of 36 reps -> 31, at 2.00 cm -> 2.14\n"
                 "   n = 8 deadlifts (three excluded: straps, clock drift, miscount)",
                 fontsize=9.5, loc="left")

    # D — the 2x2: neither change works alone
    ax = fig.add_subplot(gs[2, 0])
    e8 = D["exp8"]
    k8 = [k for k in e8 if k not in EXCLUDE]
    grid = np.array([[float(np.median([e8[k][f"{b}_{dv}"]["h"] for k in k8]))
                      for dv in ("instant", "period")] for b in ("anchor", "mid")])
    im = ax.imshow(grid, cmap="RdYlGn_r", vmin=2.0, vmax=3.1)
    for i in range(2):
        for j in range(2):
            ax.text(j, i, f"{grid[i, j]:.2f}", ha="center", va="center", fontsize=13)
    ax.set_xticks([0, 1]); ax.set_xticklabels(["dv at the\nINSTANT", "dv over the\nPERIOD"], fontsize=8)
    ax.set_yticks([0, 1]); ax.set_yticklabels(["boundary =\nrest instant", "boundary =\nperiod midpoint"], fontsize=8)
    ax.set_title("D  neither change helps alone — C29's own shape\n"
                 "   (median h rms, cm; all with the pre-pull anchor)", fontsize=9.5, loc="left")

    # E — the two rejected shapes
    ax = fig.add_subplot(gs[2, 1])
    e3 = D["exp3"]
    ks = [k for k in e3 if k not in EXCLUDE]
    def med3(tag, w):
        v = [e3[k][f"{tag}_r0_{w:.2f}"]["h"] for k in ks
             if "h" in e3[k].get(f"{tag}_r0_{w:.2f}", {})]
        return float(np.median(v)) if v else np.nan
    ws = [0.10, 0.20, 0.30, 0.40]
    for tag, c, lbl in (("const", GREEN, "C29: zero dv (1 free param)"),
                        ("disp", RED, "+ zero net displacement (2 params)"),
                        ("zupt", ORANGE, "clamp velocity to zero")):
        ax.plot(ws, [med3(tag, w) for w in ws], "o-", color=c, label=lbl, ms=4)
    ax.set_yscale("log")
    ax.set_xlabel("correction width (s)"); ax.set_ylabel("median horizontal rms (cm)")
    ax.legend(fontsize=6.6)
    ax.set_title("E  \"the watch barely moves during the ringing\"\n"
                 "   cannot be spent — both shapes lose, badly", fontsize=9.5, loc="left")

    # F — the width sweep, period frame
    ax = fig.add_subplot(gs[2, 2])
    e5 = D["exp5"]
    ks = [k for k in e5 if k not in EXCLUDE]
    def med5(tag, w, f="h"):
        v = [e5[k][f"{tag}_{w:.2f}"][f] for k in ks if f in e5[k].get(f"{tag}_{w:.2f}", {})]
        return float(np.median(v)) if v else np.nan
    ax.plot(W, [med5("c29", w) for w in W], "o-", color="#7cb342", ms=4, label="C29 (23 reps)")
    ax.plot(W, [med5("mid", w) for w in W], "s-", color=GREEN, ms=4, label="H22 (31 reps)")
    ax.axhline(float(np.median([fin[k]["ship"]["h"] for k in caps])), color=BLUE,
               ls="--", lw=1.2, label="shipping (36 reps)")
    rd = [x["ring_s"] for v in D["ring"].values() for x in v if x["ring_s"] < 1.0]
    ax.axvspan(np.percentile(rd, 25) / 2, np.percentile(rd, 75) / 2, color=RED, alpha=.09, lw=0)
    ax.text(np.median(rd) / 2, 0.94, "half the\nmeasured ringing", ha="center", fontsize=6.5,
            color=RED, transform=ax.get_xaxis_transform(), va="top")
    ax.set_xlabel("correction width (s)"); ax.set_ylabel("median horizontal rms (cm)")
    ax.legend(fontsize=7)
    ax.set_title("F  the optimum sits at half the ringing —\n"
                 "   and a per-landing adaptive width buys nothing", fontsize=9.5, loc="left")

    fig.suptitle("H22 — the deadlift impulse: a pre-pull rest anchor closes C29's coverage blocker; "
                 "the zero-displacement constraint cannot be spent", fontsize=12)
    out = ROOT / "analysis" / "72_deadlift_rest_anchor.png"
    fig.savefig(out, dpi=115)
    print("wrote", out)


if __name__ == "__main__":
    main()
