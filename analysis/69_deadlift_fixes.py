"""H19 — does C29's impact correction survive step 5b? (2026-08-18)

Renders `analysis/69_deadlift_fixes.png`. Measurement only; no module under
`src/` is written.

C31b_STATE has had this open since 2026-08-06 as item B: C29 took the deadlift
horizontal 10.66 -> 3.93 cm with step 6 OFF and before H8's step 5b existed, and
5b also removes a drift-shaped error. Either 5b already took what C29 was
taking, or the two compose and C29 is a deadlift fix nobody shipped.

**They compose.** Inside C29's own frame, with everything the pipeline now ships
(`d`, 5b, H9's axis, B4's sign, H14's scale), the impact correction takes the
median deadlift horizontal from 9.34 cm to 2.00 and `beats_null` from 0.21 to
0.83. It is worth MORE with 5b on (2.00) than with it off (3.16), so 5b did not
subsume it.

**And it still cannot be compared to what ships, for two reasons that both
flatter it.** The rest-to-rest frame scores 25 of 37 reps — it pairs consecutive
rests, so with n impacts it yields n-1 windows and rep 1 is never scored — and
its windows carry a **29% larger null** (1.63 -> 2.10 cm median, larger on 7 of
8), so part of the `beats_null` gain is the denominator moving rather than the
reconstruction improving. That is C12's shape: a referee change that flatters
the pipeline. The frame-internal control-vs-treatment comparison is the only
clean one here, and it is the one C29 itself insisted on.
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
TMP = Path("/Users/sam/.claude/jobs/874a041a/tmp")
WIDTHS = [0.10, 0.15, 0.20, 0.25, 0.30, 0.40]
WIDE = [0.20, 0.40, 0.60, 0.80, 1.20]
GREEN, GREY, RED, BLUE = "#2e7d32", "#8b949e", "#c1362f", "#1b6ca8"


def short(k):
    """Two captures share the stem `deadlift_160x6_1`, so keep the date."""
    name = k.split("_2026")[0].replace("deadlift_", "")
    return f"{name}\n{k.split('_2026')[1][:4]}" if "2026" in k else name


def main():
    a = json.loads((TMP / "h19.json").read_text())      # 5b on/off sweep
    b = json.loads((TMP / "h19b10.json").read_text())   # 3-axis + fine widths
    e = json.loads((TMP / "h19e.json").read_text())     # ship / control / C29
    caps = [k for k in e if "h" in e[k].get("ship", {})
            and "h" in e[k].get("c29", {})]

    fig = plt.figure(figsize=(15, 9.4))
    gs = fig.add_gridspec(2, 3, hspace=0.46, wspace=0.42,
                          left=0.06, right=0.965, top=0.90, bottom=0.10)

    # A — the frame-internal result, per capture
    ax = fig.add_subplot(gs[0, :2])
    x = np.arange(len(caps))
    ctl = [e[k]["ctl"]["h"] for k in caps]
    c29 = [e[k]["c29"]["h"] for k in caps]
    shp = [e[k]["ship"]["h"] for k in caps]
    ax.bar(x - 0.27, ctl, 0.27, color=GREY, label="rest windows, NO correction (control)")
    ax.bar(x, c29, 0.27, color=GREEN, label="rest windows + 0.20 s jump (C29)")
    ax.bar(x + 0.27, shp, 0.27, color=BLUE, alpha=.55, label="shipping (different windows — see D)")
    ax.set_xticks(x)
    ax.set_xticklabels([short(k) for k in caps], rotation=0, ha="center", fontsize=6)
    ax.set_ylabel("horizontal rms (cm)")
    ax.legend(fontsize=7.5)
    ax.set_title("A  frame-internal: C29 beats its control on 10 of 10 (Wilcoxon p = 0.002).\n   Against SHIPPING it is 7 of 10, Wilcoxon p = 0.049 — marginal, hold it loosely",
                 fontsize=9.5, loc="left")

    # B — does 5b subsume it?
    ax = fig.add_subplot(gs[0, 2])
    def med(src, key, f="h"):
        v = [src[k][key][f] for k in src if key in src[k] and f in src[k][key]]
        return float(np.median(v))
    bars = [("control\n5b off", med(a, "ctl_5b_off"), GREY),
            ("C29\n5b off", med(a, "c29_5b_off_0.20"), "#7cb342"),
            ("control\n5b on", med(a, "ctl_5b_on"), GREY),
            ("C29\n5b on", med(a, "c29_5b_on_0.20"), GREEN)]
    ax.bar(range(4), [v for _, v, _ in bars], color=[c for _, _, c in bars])
    for i, (_, v, _) in enumerate(bars):
        ax.text(i, v + 0.25, f"{v:.2f}", ha="center", fontsize=8)
    ax.set_xticks(range(4))
    ax.set_xticklabels([n for n, _, _ in bars], fontsize=7.5)
    ax.set_ylabel("median horizontal rms (cm)")
    ax.set_title("B  they COMPOSE: C29 is worth more with 5b on",
                 fontsize=9.5, loc="left")
    ax.text(.5, .93, "closes C31b item B,\nopen since 2026-08-06",
            transform=ax.transAxes, fontsize=7.2, ha="center", va="top")

    # C — the width plateau
    ax = fig.add_subplot(gs[1, 0])
    w_json = json.loads((TMP / "h19w.json").read_text())
    def medw(w, f):
        v = [r[str(w)][f] for r in w_json.values() if str(w) in r]
        return float(np.median(v))
    hs = [med(b, f"c29_hv_{w:.2f}") for w in WIDTHS] + [medw(w, "h") for w in WIDE[2:]]
    bn = [med(b, f"c29_hv_{w:.2f}", "bn") for w in WIDTHS] + [medw(w, "bn") for w in WIDE[2:]]
    xs = WIDTHS + WIDE[2:]
    ax.plot(xs, hs, "o-", color=GREEN, label="h rms (cm)")
    ax.axhline(med(b, "ship"), color=BLUE, ls="--", lw=1.2, label="shipping h rms")
    ax.set_xlabel("jump-correction width (s)")
    ax.set_ylabel("median horizontal rms (cm)")
    ax2 = ax.twinx()
    ax2.plot(xs, bn, "s--", color="#666", ms=4, label="beats_null")
    ax2.set_ylabel("beats_null", color="#666", fontsize=8)
    ax.legend(fontsize=7, loc="upper center")
    ax.set_title("C  an interior optimum at 0.20-0.40 s: the correction is LOCAL",
                 fontsize=9.5, loc="left")

    # D — the two confounds
    ax = fig.add_subplot(gs[1, 1])
    sn = [e[k]["ship"]["null"] for k in caps]
    cn = [e[k]["c29"]["null"] for k in caps]
    ax.scatter(sn, cn, s=42, color=RED, zorder=3)
    lim = [1.2, 4.2]
    ax.plot(lim, lim, "k-", lw=1)
    ax.set_xlim(*lim); ax.set_ylim(*lim)
    ax.set_xlabel("null in the SHIPPING frame (cm)")
    ax.set_ylabel("null, C29 frame (cm)")
    ax.text(.04, .93, "9 of 10 above the line:\nthe C29 frame's null is 27% larger,\n"
            "so beats_null is flattered by the\nDENOMINATOR moving (C12's shape)",
            transform=ax.transAxes, fontsize=7.2, va="top")
    ax.set_title("D  confound 1 — the window change moves the null",
                 fontsize=9.5, loc="left")

    # E — coverage
    ax = fig.add_subplot(gs[1, 2])
    ns = [e[k]["ship"]["n"] for k in caps]
    nc = [e[k]["c29"]["n"] for k in caps]
    ax.bar(x - 0.19, ns, 0.38, color=BLUE, alpha=.55, label=f"shipping ({sum(ns)} reps)")
    ax.bar(x + 0.19, nc, 0.38, color=GREEN, label=f"C29 frame ({sum(nc)} reps)")
    ax.set_xticks(x)
    ax.set_xticklabels([short(k).replace("\n", " ") for k in caps],
                       rotation=45, ha="right", fontsize=5.4)
    ax.set_ylabel("reps scored")
    ax.legend(fontsize=7.5)
    ax.set_title("E  confound 2 — n impacts give n-1 windows",
                 fontsize=9.5, loc="left")

    fig.suptitle("H19 — C29's impact correction survives step 5b, and still is "
                 "not shippable: the frame costs a rep per set",
                 fontsize=12.5, weight="bold", x=0.008, ha="left", y=0.972)
    out = ROOT / "analysis" / "69_deadlift_fixes.png"
    fig.savefig(out, dpi=105)
    print(f"wrote {out.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
