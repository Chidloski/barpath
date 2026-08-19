"""H26 — three priors on the remaining horizontal error, MEASURED not built.

H25 established that the deadlift horizontal error is about half the floor
impact and about half something already present in the impact-free PULL. The
owner picked three of seven candidate priors and asked for measurement first,
with no correction built. This is that measurement. **Nothing in `src/` changed
and no arm is proposed for the pipeline.**

The interval set is H25's exactly — moments the VIDEO says the bar was still,
so the closure identity (integral of acceleration between two still instants
must be zero) supplies the error with nothing tunable in it. The video is used
only to say WHEN; a scale error cannot move a zero crossing.

Excluded by hand: `deadlift_160x6_1_20260818` (straps, H20).

--------------------------------------------------------------------- PRIOR 1
**The lockout is a second, impact-free anchor, and the error it exposes is
SYSTEMATIC — one sign, one anatomical direction, every capture.**

`segment.dwell_instants` already splits a deadlift rep at the lockout, so a rep
can offer TWO velocity-error readings rather than the one every correction to
date has fitted: a pull (floor -> lockout, no impact in it) and a
descent-plus-landing. The falsifier was that the pull-only error might scatter
in sign and size, which would make it noise.

It does not scatter:

    capture              n      RAW    SHIPS    coherence   null
    deadlift_150x4_1     1   -0.106   -0.049        -         -
    deadlift_155x5_1     2   -0.050   -0.043       0.99      0.63
    deadlift_160x4_2     1   -0.073   -0.040        -         -
    deadlift_160x5_2     1   -0.077   -0.068        -         -
    deadlift_160x6_1     3   -0.156   -0.011       0.99      0.51
    deadlift_160x6_2     1   -0.108   -0.013        -         -
    deadlift_170x4_3     2   -0.032   -0.018       0.83      0.63
    deadlift_185x3       2   -0.022   -0.011       0.86      0.63
    deadlift_190x3       2   -0.015   -0.070       0.94      0.63

m/s^2. **RAW** is Core Motion's attitude as logged, which is what H25 measured.
**SHIPS** is the attitude the pipeline actually uses — step 2's bias correction
and step 5b's fitted drift tilt both applied.

**NEGATIVE on 9 of 9 captures** — a sign test at p = 0.002 — spanning three
sessions spanning 2026-08-04 to 2026-08-18, loads from 150 to
190 kg and both camera sides. As a tilt that is 0.09 to
0.91 degrees, median 0.43, which is the size H25 predicted from the other
direction and the size C6 measured at still holds. The fore-aft sign convention
is fixed per lift by `project.FORE_AFT_SENSE`, so "all negative" means one fixed
anatomical direction relative to the lifter, not an accident of projection.

**AND STEP 5b DOES NOT REMOVE IT, WHICH IS THE CHECK THAT DECIDES WHETHER THE
PRIOR IS LIVE.** 5b already fits a world-horizontal attitude drift rate, so a
standing tilt it had already absorbed would make this measurement a description
of a fixed error. It has not: under the SHIPPED attitude the pull error is
**still negative on 9 of 9** captures, at **55%** of its raw magnitude — a
residual of 0.011-0.070 m/s^2, median 0.040, i.e. **0.06-0.41 degrees, median
0.23**. So 5b removes a little under half of it and leaves a systematic,
same-signed remainder on every capture. That is consistent with 5b fitting a
RATE where this is an OFFSET.

**And the two readings are LARGELY INDEPENDENT: Spearman r = +0.06, p = 0.83,
n = 15 (panel B).** That is the part that bears on a correction. The pull error
does not predict the landing error, so they are two causes rather than one seen
twice — and a single number per rest-to-rest interval, which is what C28b, C29,
H22 and H24 all fit, is being asked to absorb both.

**THE CAVEAT, AND IT IS THE ONE THAT DECIDES WHETHER THIS IS BUILDABLE.** Only
**15** intervals carry a lockout dwell against **24** landings: on a
touch-and-go deadlift the bar is not still enough at lockout on most reps for
`metrics._video_zero_dwells` to name the moment. So the second anchor exists on
fewer than half the reps, and H23's third requirement — a correction must cover
EVERY rep — is not satisfied by using it directly. What the measurement licenses
is estimating a per-SET standing tilt from the reps that do have one and
applying it to all of them; it does not license a per-rep correction.

--------------------------------------------------------------------- PRIOR 2
**Excising the ring is licensed on the HORIZONTAL and forbidden on the
VERTICAL, and the asymmetry is the whole result.**

The ring window is `oracle.ring_duration`, from raw |a| alone, median 0.60 s and
20% of the landing interval. The direct test is not what fraction of the error
lives inside it — the interval's net partly cancels, so that ratio exceeds 100%
and means nothing — but what the interval's closure error BECOMES if those
samples are removed:

    axis          as is      ring excised    better on
    horizontal   0.256 m/s     0.153          15 of 24     <- LICENSED
    vertical     0.128         0.653           1 of 24     <- FORBIDDEN

Inside the ring the bar is on the floor, so its true horizontal acceleration is
~zero and everything integrated there is error — removable. The vertical is the
opposite: that impulse is REAL, B5 measured the IMU capturing it to a ratio of
1.04, and excising it inflates the closure error 5x. Removing it would destroy
vertical ROM, which is exactly the failure H24b caught the hard way.

Read the horizontal row honestly: **a 1.7x median improvement on 15 of 24, not
a universal one.** It is a licence for an axis-selective excision to be TRIED,
not a demonstration that one works — and per H23 it would still have to cover
every rep and keep its detrend boundaries off the impacts.

--------------------------------------------------------------------- PRIOR 4
**DEAD where it was proposed, and alive only where it explains nothing new.**

The hypothesis was that the pull-phase tilt is Core Motion losing its gravity
reference under load. Tested WITHIN H25's four interval classes, so neither the
lift nor the impact can be the confound — a within-LIFT correlation on deadlift
would rediscover H25's own result, because the high-|a| intervals are exactly
the ones containing an impact:

    class                 peak |a|      mean ||a||-g     peak gyro
    deadlift PULL       -0.12 (0.68)   -0.15 (0.59)   +0.12 (0.67)
    deadlift LANDING    +0.45 (0.03)   +0.56 (0.00)   +0.54 (0.01)
    bench               +0.13 (0.34)   -0.08 (0.56)   +0.22 (0.09)
    squat               -0.33 (0.05)   +0.38 (0.02)   -0.15 (0.39)

In the PULL class — the one the hypothesis exists to explain — nothing reaches
|r| = 0.15 and every p is above 0.5. The only class where it correlates is the
LANDING, and there the mechanism is already named: P6's strap ringing, harder
landings ringing more. Squat's two significant cells disagree in SIGN with each
other, which is what a spurious correlation at n = 35 looks like.

So the pull-phase tilt is not driven by the vigour of the rep. It behaves like a
standing attitude offset, which is what prior 1 independently says.
"""
import json
import sys
import warnings
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
warnings.filterwarnings("ignore")

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from scipy.signal import savgol_filter
from scipy.stats import spearmanr

from src import metrics, oracle, orient, pipeline, segment

EXCLUDE = ("deadlift_160x6_1_20260818",)
G = 9.81
LIFT_COL = {"deadlift": "#c0392b", "bench": "#3498db", "squat": "#27ae60"}


def collect():
    """One row per still-to-still interval, on H25's interval set."""
    rows = []
    for csv in sorted((ROOT / "data_v2" / "raw").glob("*.csv")):
        if any(e in csv.stem for e in EXCLUDE):
            continue
        video = pipeline.find_video(csv)
        if video is None:
            continue
        try:
            res = pipeline.run(csv, video=video)
            if res.get("vs_truth") is None or res.get("axis") is None:
                continue
            log = res["log"]
            t = log["t"]
            # TWO world frames, and the pair is the point. `log["quat"]` is
            # the attitude as Core Motion reported it, which is what H25
            # measured; `res["quat"]` carries step 2's bias correction AND step
            # 5b's fitted drift tilt, i.e. the attitude the pipeline SHIPS. If
            # 5b already removes the standing tilt, prior 1 is dead on arrival
            # and the raw-frame number would be measuring a fixed error.
            world = orient.to_world(log["accel"], log["quat"], log["quat"])
            world_c = orient.to_world(log["accel"], log["quat"], res["quat"])
            axis = np.asarray(res["axis"], float)[:2]
            a_h = world[:, :2] @ axis          # signed, along fore-aft
            a_h_c = world_c[:, :2] @ axis
            a_v = world[:, 2]
            amag = np.linalg.norm(log["accel"], axis=1)
            gmag = np.linalg.norm(log["gyro"], axis=1)

            t_imu, _, height, _ = metrics._video_on_imu_clock(res, video, None)
            v_video = np.gradient(savgol_filter(height, 9, 3), t_imu)
            bounds = res["bounds"]
            lo, hi = float(t[bounds[0][0]]), float(t[bounds[-1][1] - 1])
            mids = metrics._video_zero_dwells(t_imu, v_video, 0.10, 0.20)
            mids = mids[(mids >= lo - 0.5) & (mids <= hi + 0.5)]
            if len(mids) < 2:
                continue
            idx = [int(np.searchsorted(t, m)) for m in mids]
            impacts = list(segment.impact_anchors(log))
            lift = csv.stem.split("_")[0]

            for a, b in zip(idx[:-1], idx[1:]):
                if b - a < 10:
                    continue
                inside = [k for k in impacts if a <= k <= b]
                row = {
                    "capture": csv.stem, "lift": lift, "spans": bool(inside),
                    "dur": float(t[b] - t[a]),
                    "dv_h": float(np.trapezoid(a_h[a:b], t[a:b])),
                    "dv_h_ship": float(np.trapezoid(a_h_c[a:b], t[a:b])),
                    "dv_v": float(np.trapezoid(a_v[a:b], t[a:b])),
                    # the 2D horizontal error VECTOR, for direction coherence
                    "dv_x": float(np.trapezoid(world[a:b, 0], t[a:b])),
                    "dv_y": float(np.trapezoid(world[a:b, 1], t[a:b])),
                    # PRIOR 4 predictors
                    "peak_a": float(amag[a:b].max()),
                    "sfd": float(np.mean(np.abs(amag[a:b] - G))),
                    "peak_gyro": float(gmag[a:b].max()),
                }
                # PRIOR 2 — split the interval at the ring window
                if inside:
                    k = inside[-1]
                    ring_s, j = oracle.ring_duration(log, k)
                    j = min(j, b - 1)
                    if j > k:
                        row["ring_s"] = ring_s
                        row["ring_dv_h"] = float(np.trapezoid(a_h[k:j], t[k:j]))
                        row["ring_dv_v"] = float(np.trapezoid(a_v[k:j], t[k:j]))
                        row["ring_frac_t"] = float(t[j] - t[k]) / row["dur"]
                rows.append(row)
        except Exception:
            continue
    return rows


def coherence(vecs):
    """Mean resultant length of unit vectors. 1 = one direction, 0 = random."""
    u = np.asarray(vecs, float)
    n = np.linalg.norm(u, axis=1)
    keep = n > 0
    if keep.sum() < 2:
        return np.nan
    u = u[keep] / n[keep, None]
    return float(np.linalg.norm(u.mean(axis=0)))


def render(rows):
    pulls = [r for r in rows if r["lift"] == "deadlift" and not r["spans"]]
    lands = [r for r in rows if r["lift"] == "deadlift" and r["spans"]]
    fig, axes = plt.subplots(2, 2, figsize=(16.5, 12.4))
    out = {}

    # ---------------------------------------------------------- A · PRIOR 1
    ax = axes[0][0]
    caps = sorted({r["capture"] for r in pulls})
    coh = {}
    for i, c in enumerate(caps):
        g = [r for r in pulls if r["capture"] == c]
        e = [r["dv_h"] / r["dur"] for r in g]
        es = [r["dv_h_ship"] / r["dur"] for r in g]
        ax.scatter(np.full(len(e), i) - 0.16 + np.random.uniform(-.05, .05, len(e)),
                   e, s=46, color="#f39c12", alpha=0.85, zorder=3,
                   label="Core Motion attitude (raw)" if i == 0 else None)
        ax.scatter(np.full(len(es), i) + 0.16 + np.random.uniform(-.05, .05, len(es)),
                   es, s=46, color="#8e44ad", alpha=0.85, zorder=3, marker="D",
                   label="attitude the pipeline SHIPS (step 2 + 5b)" if i == 0 else None)
        ax.hlines(np.median(e), i - .30, i - .02, color="#2c3e50", lw=2.4, zorder=4)
        ax.hlines(np.median(es), i + .02, i + .30, color="#2c3e50", lw=2.4, zorder=4)
        coh[c] = coherence([(r["dv_x"], r["dv_y"]) for r in g])
    ax.axhline(0, color="#7f8c8d", lw=1.2, ls="--")
    ax.set_xticks(range(len(caps)))
    ax.set_xticklabels([c.split("_2026")[0].replace("deadlift_", "")
                        for c in caps], rotation=30, ha="right", fontsize=8)
    ax.set_ylabel("mean horizontal acceleration error, m/s²  (signed)")
    # The null is the expected resultant length of n RANDOM unit vectors,
    # ~sqrt(pi)/(2 sqrt(n)) — and it is computed over the SAME captures the
    # coherence is, i.e. only those with two or more pull intervals. Including
    # the n=1 captures would put their null at 0.89 against a coherence of 1.0
    # by definition and flatter nothing but the comparison.
    usable = [c for c in caps if len([r for r in pulls if r["capture"] == c]) > 1]
    med_coh = float(np.nanmedian([coh[c] for c in usable]))
    nulls = [np.sqrt(np.pi) / (2 * np.sqrt(len([r for r in pulls
                                                if r["capture"] == c])))
             for c in usable]
    cap_meds = [float(np.median([r["dv_h"] / r["dur"]
                                 for r in pulls if r["capture"] == c]))
                for c in caps]
    neg = sum(1 for m in cap_meds if m < 0)
    p_sign = 2.0 ** -len(cap_meds)
    ship_meds = [float(np.median([r["dv_h_ship"] / r["dur"]
                                  for r in pulls if r["capture"] == c]))
                 for c in caps]
    neg_s = sum(1 for m in ship_meds if m < 0)
    kept = float(np.median(np.abs(ship_meds)) / np.median(np.abs(cap_meds)))
    out["prior1_ship_medians"] = dict(zip(caps, ship_meds))
    out["prior1_ship_sign"] = [neg_s, len(ship_meds)]
    out["prior1_5b_kept"] = kept
    ax.legend(fontsize=8, loc="lower right")
    ax.set_title("A · PRIOR 1 — the impact-free PULL error is SYSTEMATIC, and "
                 "STEP 5b DOES NOT REMOVE IT.\n"
                 f"Same sign on {neg} of {len(cap_meds)} captures "
                 f"(sign test p = {p_sign:.3f}) and one fixed anatomical\n"
                 f"direction — coherence {med_coh:.2f} against a "
                 f"random null of ~{np.mean(nulls):.2f} (n>=2 only). A standing TILT.\n"
                 f"Under the attitude the pipeline SHIPS it is still "
                 f"negative on {neg_s} of {len(ship_meds)}, at "
                 f"{kept:.0%} of the raw size.\n"
                 f"Only {len(pulls)} of {len(pulls) + len(lands)} intervals "
                 "have a lockout dwell — see the caveat.",
                 fontsize=11, loc="left")
    ax.grid(alpha=0.25, axis="y")
    out["prior1_sign"] = [neg, len(cap_meds), float(p_sign)]
    out["prior1_capture_medians"] = dict(zip(caps, cap_meds))
    out["prior1_coverage"] = [len(pulls), len(lands)]
    out["coherence"] = coh
    out["coherence_usable"] = usable
    out["coherence_null"] = float(np.mean(nulls))

    # ---------------------------------------------------------- B · PRIOR 1b
    ax = axes[0][1]
    px, py = [], []
    for c in caps:
        p = [r for r in pulls if r["capture"] == c]
        l = [r for r in lands if r["capture"] == c]
        for a, b in zip(p, l):                       # pull j with landing j
            px.append(a["dv_h"] / a["dur"])
            py.append(b["dv_h"] / b["dur"])
    r_pl, p_pl = spearmanr(px, py) if len(px) > 3 else (np.nan, np.nan)
    ax.scatter(px, py, s=52, color="#c0392b", alpha=0.8, zorder=3)
    ax.axhline(0, color="#7f8c8d", lw=1.0, ls="--")
    ax.axvline(0, color="#7f8c8d", lw=1.0, ls="--")
    ax.set_xlabel("PULL interval error, m/s²  (no impact in it)")
    ax.set_ylabel("the SAME rep's landing interval error, m/s²")
    ax.set_title("B · PRIOR 1 — are they one cause or two?\n"
                 f"Spearman r = {r_pl:+.2f} (p = {p_pl:.2f}), n = {len(px)}: "
                 "LARGELY INDEPENDENT.\n"
                 "So one number per rest-to-rest interval is absorbing two "
                 "errors.", fontsize=11, loc="left")
    ax.grid(alpha=0.25)
    out["pull_vs_landing_spearman"] = [float(r_pl), float(p_pl), len(px)]

    # ---------------------------------------------------------- C · PRIOR 2
    # The direct test: if the ring samples were EXCISED, what would the
    # interval's closure error become? A ratio of the interval's NET dv is
    # meaningless here — the net partly cancels, so the ring's share exceeds
    # 100% and says nothing. Excising and re-closing is the thing itself.
    ax = axes[1][0]
    ring = [r for r in lands if "ring_dv_h" in r]
    bh = np.array([abs(r["dv_h"]) for r in ring])
    ah_ = np.array([abs(r["dv_h"] - r["ring_dv_h"]) for r in ring])
    bv = np.array([abs(r["dv_v"]) for r in ring])
    av_ = np.array([abs(r["dv_v"] - r["ring_dv_v"]) for r in ring])
    for i, (b0, a0, c, lab) in enumerate(
            [(bh, ah_, "#e67e22", "HORIZONTAL\nerror"),
             (bv, av_, "#2980b9", "VERTICAL\nimpulse")]):
        x0, x1 = i * 2.0, i * 2.0 + 0.85
        for u, v in zip(b0, a0):
            ax.plot([x0, x1], [u, v], color=c, alpha=0.30, lw=1.1, zorder=2)
        ax.scatter(np.full(len(b0), x0), b0, s=30, color=c, alpha=0.8, zorder=3)
        ax.scatter(np.full(len(a0), x1), a0, s=30, color=c, alpha=0.8, zorder=3)
        ax.hlines(np.median(b0), x0 - .22, x0 + .22, color="#2c3e50", lw=2.6, zorder=4)
        ax.hlines(np.median(a0), x1 - .22, x1 + .22, color="#2c3e50", lw=2.6, zorder=4)
        ax.text((x0 + x1) / 2, max(b0.max(), a0.max()) * 1.04,
                f"{np.median(b0):.3f} → {np.median(a0):.3f}", ha="center",
                fontsize=10, fontweight="bold", color=c)
    ax.set_xticks([0, 0.85, 2.0, 2.85])
    ax.set_xticklabels(["as is", "ring\nexcised", "as is", "ring\nexcised"],
                       fontsize=9)
    ax.set_ylabel("|closure error| over the landing interval, m/s")
    hgain = float(np.median(bh) / np.median(ah_))
    vloss = float(np.median(av_) / np.median(bv))
    ax.set_title("C · PRIOR 2 — excision is licensed on ONE axis and forbidden "
                 "on the other.\n"
                 f"Excising the ring cuts the HORIZONTAL closure error "
                 f"{hgain:.1f}x ({(ah_ < bh).sum()}/{len(bh)} intervals) —\n"
                 f"and inflates the VERTICAL {vloss:.0f}x, because that "
                 "impulse is REAL (B5, ratio 1.04).", fontsize=11, loc="left")
    ax.grid(alpha=0.25, axis="y")
    out["ring"] = {
        "n": len(ring),
        "ring_s": float(np.median([r["ring_s"] for r in ring])),
        "frac_time": float(np.median([r["ring_frac_t"] for r in ring])),
        "h_before": float(np.median(bh)), "h_after": float(np.median(ah_)),
        "h_better": int((ah_ < bh).sum()),
        "v_before": float(np.median(bv)), "v_after": float(np.median(av_)),
        "v_better": int((av_ < bv).sum())}

    # ---------------------------------------------------------- D · PRIOR 4
    # WITHIN H25's four interval classes, not within lift. On deadlift a
    # within-LIFT correlation is confounded outright: the high-|a| intervals
    # are exactly the ones containing an impact, so it would rediscover H25's
    # result and call it a gravity-reference effect.
    ax = axes[1][1]
    preds = ["peak_a", "sfd", "peak_gyro"]
    labels = ["peak |a|", "mean |‖a‖−g|", "peak gyro"]
    classes = [
        ("deadlift PULL", lambda r: r["lift"] == "deadlift" and not r["spans"], "#f39c12"),
        ("deadlift LANDING", lambda r: r["lift"] == "deadlift" and r["spans"], "#c0392b"),
        ("bench", lambda r: r["lift"] == "bench", "#3498db"),
        ("squat", lambda r: r["lift"] == "squat", "#27ae60")]
    width = 0.20
    stats = {}
    for pi, pred in enumerate(preds):
        for li, (nm, f, c) in enumerate(classes):
            g = [r for r in rows if f(r)]
            if len(g) < 6:
                continue
            rr, pp = spearmanr([r[pred] for r in g],
                               [abs(r["dv_h"]) / r["dur"] for r in g])
            ax.bar(pi + (li - 1.5) * width, rr, width=width * 0.88,
                   color=c, alpha=0.9, zorder=3, label=nm if pi == 0 else None)
            stats[f"{nm}/{pred}"] = [float(rr), float(pp), len(g)]
    ax.axhline(0, color="#2c3e50", lw=1.2)
    for sline in (0.5, -0.5):
        ax.axhline(sline, color="#7f8c8d", lw=1.0, ls=":")
    ax.set_xticks(range(len(preds)))
    ax.set_xticklabels(labels, fontsize=10)
    ax.set_ylim(-1, 1)
    ax.set_ylabel("Spearman r  vs  horizontal acceleration error")
    ax.legend(fontsize=8.5, loc="lower right", ncol=2)
    ax.set_title("D · PRIOR 4 — DEAD where it was proposed, alive only where "
                 "it explains nothing new.\n"
                 "The hypothesis was that the PULL-phase tilt is Core Motion "
                 "losing its gravity\nreference under load. In the PULL class "
                 "it reaches |r| = 0.15, p > 0.5, on all three\npredictors. "
                 "It correlates only on the LANDING (+0.45..+0.56) — the strap "
                 "ringing\nof P6, already known, and not a tilt.",
                 fontsize=11, loc="left")
    ax.grid(alpha=0.25, axis="y")
    out["prior4"] = stats

    fig.suptitle("H26 · Three priors on the remaining horizontal error — "
                 "measured, nothing built", fontsize=14, y=1.002)
    fig.tight_layout()
    png = Path(__file__).with_suffix(".png")
    fig.savefig(png, dpi=118, bbox_inches="tight")
    print(f"wrote {png}")

    # ------------------------------------------------------------- console
    print(f"\nPRIOR 1 — pull-only error repeatability, {len(pulls)} intervals")
    print(f"{'capture':30}{'n':>3}{'raw':>9}{'SHIPS':>9}{'MAD':>8}"
          f"{'coh':>7}{'null':>7}")
    for c in caps:
        g = [r for r in pulls if r["capture"] == c]
        e = np.array([r["dv_h"] / r["dur"] for r in g])
        es = np.array([r["dv_h_ship"] / r["dur"] for r in g])
        nl = np.sqrt(np.pi) / (2 * np.sqrt(len(g))) if len(g) > 1 else np.nan
        print(f"{c.split('_2026')[0]:30}{len(g):3}{np.median(e):9.4f}"
              f"{np.median(es):9.4f}{np.median(np.abs(e - np.median(e))):8.4f}"
              f"{coh[c]:7.2f}{nl:7.2f}")
    print(f"  sign: raw {neg}/{len(cap_meds)} negative, "
          f"SHIPPED {neg_s}/{len(ship_meds)}; step 5b leaves {kept:.0%} "
          "of the raw magnitude")
    print(f"\nPRIOR 1b — pull vs same-rep landing: r = {r_pl:+.2f}, "
          f"p = {p_pl:.3f}, n = {len(px)}")
    print(f"\nPRIOR 2 — ring EXCISION, {out['ring']['n']} landings, median "
          f"{out['ring']['ring_s']:.2f} s = {out['ring']['frac_time']:.0%} "
          "of the interval")
    print(f"  horizontal closure error {out['ring']['h_before']:.3f} -> "
          f"{out['ring']['h_after']:.3f} m/s   better on "
          f"{out['ring']['h_better']}/{out['ring']['n']}   <- LICENSED")
    print(f"  vertical  closure error {out['ring']['v_before']:.3f} -> "
          f"{out['ring']['v_after']:.3f} m/s   better on "
          f"{out['ring']['v_better']}/{out['ring']['n']}   <- FORBIDDEN, the "
          "impulse is real")
    print("\nPRIOR 4 — within-CLASS Spearman vs horizontal error")
    print(f"{'':20}{'peak |a|':>18}{'mean|a|-g':>18}{'peak gyro':>18}")
    for nm, _, _ in classes:
        cells = []
        for pred in preds:
            k = f"{nm}/{pred}"
            cells.append(f"{stats[k][0]:+.2f} (p={stats[k][1]:.2f})"
                         if k in stats else "-")
        print(f"{nm:20}" + "".join(f"{c:>18}" for c in cells))

    Path(__file__).with_suffix(".json").write_text(json.dumps(out, indent=1))


if __name__ == "__main__":
    np.random.seed(0)
    render(collect())
