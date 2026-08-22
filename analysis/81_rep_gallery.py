"""H33 — a browsable gallery of every set and every rep, video against pipeline.

The owner: *"keep live graphs of each set and rep for both video and data ran
through the most recent pipeline and video tracking so I can sanity check."*

Writes `analysis/rep_gallery.html`, a self-contained page: one card per capture,
each showing the whole set overlaid and then every rep as a small multiple, with
the video path and the reconstruction drawn together on a common axis and a
common sign. **Re-run it after any pipeline or tracker change** — it reads the
live `pipeline.run` and the committed tracked CSVs, so it is only ever as
current as the last run.

Why a page and not more PNGs: `analysis/78_set_paths_*.png` already draws every
set, and the thing it cannot do is let you go from "this set looks wrong" to
"this rep, against this video frame range" without opening a second file. The
per-rep panels are the point; the set overlay is the index into them.

    python3 analysis/81_rep_gallery.py
"""
from __future__ import annotations

import html
import re
import sys
import warnings
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src import capture, metrics, pipeline, tracked   # noqa: E402

RAW = ROOT / "data_v2" / "raw"
TRACKED = ROOT / "data_v2" / "tracked"
OUT = ROOT / "analysis" / "rep_gallery.html"

# Excluded from every aggregate, never from the page. The watch moved; the
# capture is a record of that and hiding it would misrepresent the corpus.
STRAPPED = "deadlift_160x6_1_20260818"

N_POINTS = 64          # per curve, resampled — keeps the page under a few hundred kB


def resample(a, n=N_POINTS):
    """`a` is (m, 2) in metres. Returns (n, 2), arc-length agnostic."""
    a = np.asarray(a, float)
    if len(a) < 2:
        return np.repeat(a, n, axis=0)[:n]
    s = np.linspace(0, 1, len(a))
    q = np.linspace(0, 1, n)
    return np.column_stack([np.interp(q, s, a[:, 0]), np.interp(q, s, a[:, 1])])


def path_d(xy, box, pad=6):
    """(n,2) metres -> an SVG path string inside `box` = (w, h), y up."""
    w, h = box
    x, y = xy[:, 0] * 100, xy[:, 1] * 100          # cm
    x0, x1 = x.min(), x.max()
    y0, y1 = y.min(), y.max()
    return x0, x1, y0, y1, _d(x, y, x0, x1, y0, y1, w, h, pad)


def _d(x, y, x0, x1, y0, y1, w, h, pad):
    sx = (w - 2 * pad) / max(x1 - x0, 1e-6)
    sy = (h - 2 * pad) / max(y1 - y0, 1e-6)
    px = pad + (x - x0) * sx
    py = h - pad - (y - y0) * sy
    return "M" + " L".join(f"{a:.1f},{b:.1f}" for a, b in zip(px, py))


def pair_d(vid, pipe, box, pad=6):
    """Both curves on ONE shared scale, so the comparison is honest."""
    w, h = box
    xs = np.concatenate([vid[:, 0], pipe[:, 0]]) * 100
    ys = np.concatenate([vid[:, 1], pipe[:, 1]]) * 100
    x0, x1, y0, y1 = xs.min(), xs.max(), ys.min(), ys.max()
    return (_d(vid[:, 0] * 100, vid[:, 1] * 100, x0, x1, y0, y1, w, h, pad),
            _d(pipe[:, 0] * 100, pipe[:, 1] * 100, x0, x1, y0, y1, w, h, pad),
            x1 - x0, y1 - y0)


def load_kg(stem):
    m = re.search(r"_(\d+(?:\.\d+)?)x\d+", stem)
    return float(m.group(1)) if m else None


def collect():
    warnings.simplefilter("ignore")
    out = []
    for csv in sorted(RAW.glob("*.csv")):
        stem_nodate = csv.stem.rsplit("_", 1)[0]
        rec = {"stem": csv.stem, "short": stem_nodate,
               "lift": capture.lift_of(csv), "kg": load_kg(csv.stem),
               "strapped": STRAPPED in csv.stem, "reps": [], "note": ""}
        try:
            res = pipeline.run(csv)
        except Exception as e:
            rec["note"] = f"pipeline refused: {type(e).__name__}"
            out.append(rec)
            continue
        rec["windows"] = len(res["bounds"])
        rec["expected"] = pipeline.expected_reps(csv)

        tp = TRACKED / f"{stem_nodate}.csv"
        if not tp.is_file():
            rec["note"] = "no tracked video"
            out.append(rec)
            continue
        try:
            vs = metrics.vs_truth(res, tracked.read(None, src=tp))
        except Exception as e:
            rec["note"] = f"not scored — {str(e)[:90]}"
            out.append(rec)
            continue

        rec.update(h_rms=vs["pipeline_h_rms"], v_rms=vs["pipeline_v_rms"],
                   beats=vs["beats_null"], null=vs["null_h_rms"],
                   sync=vs.get("sync_method", ""))
        for pr in vs["per_rep"]:
            if not pr.get("covered"):
                rec["reps"].append(None)
                continue
            v = resample(pr["curve_video"])
            p = resample(pr["curve_pipeline"])
            v = v - v[0]
            p = p - p[0]
            rec["reps"].append({
                "k": pr["rep"], "vid": v, "pipe": p,
                "h": pr["pipeline_h_rms"], "vv": pr["pipeline_v_rms"],
                "null": pr["null_h_rms"],
                "close_h": pr["video_closure_h"], "close_v": pr["video_closure_v"],
                "rom": pr["video_rom_cm"], "ex": pr["video_fore_aft_cm"],
            })
        out.append(rec)
    return out


# ------------------------------------------------------------------ render --

CSS = """
:root{
  --ground:#f6f7f9; --panel:#ffffff; --ink:#10151c; --ink-2:#4a5563;
  --ink-3:#7b8694; --line:#dfe4ea; --line-2:#eef1f5;
  --video:#2f7fbf; --pipe:#e07a3f;
  --good:#2f855a; --bad:#c1352c; --warn:#a96a13; --good-bg:#e7f2ec;
  --bad-bg:#fbeae9; --warn-bg:#fbf1e0;
}
@media (prefers-color-scheme:dark){:root:not([data-theme="light"]){
  --ground:#0d1117; --panel:#151b23; --ink:#e6ebf2; --ink-2:#a9b4c2;
  --ink-3:#6f7c8c; --line:#242d38; --line-2:#1c242e;
  --video:#5aa9e6; --pipe:#f0955c;
  --good:#5cc08a; --bad:#e8736a; --warn:#dda13f; --good-bg:#152a20;
  --bad-bg:#2c1917; --warn-bg:#2a2113;
}}
:root[data-theme="dark"]{
  --ground:#0d1117; --panel:#151b23; --ink:#e6ebf2; --ink-2:#a9b4c2;
  --ink-3:#6f7c8c; --line:#242d38; --line-2:#1c242e;
  --video:#5aa9e6; --pipe:#f0955c;
  --good:#5cc08a; --bad:#e8736a; --warn:#dda13f; --good-bg:#152a20;
  --bad-bg:#2c1917; --warn-bg:#2a2113;
}
*{box-sizing:border-box}
body{margin:0;background:var(--ground);color:var(--ink);
  font-family:"IBM Plex Sans","Helvetica Neue",Arial,sans-serif;
  font-size:15px;line-height:1.55;-webkit-font-smoothing:antialiased}
.wrap{max-width:1220px;margin:0 auto;padding:34px 22px 90px}
h1{font-family:"IBM Plex Sans Condensed","IBM Plex Sans",sans-serif;
  font-weight:600;font-size:31px;letter-spacing:-.015em;margin:0 0 6px;
  text-wrap:balance}
.sub{color:var(--ink-2);max-width:64ch;margin:0 0 8px}
.stamp{font-family:"IBM Plex Mono",ui-monospace,monospace;font-size:11.5px;
  color:var(--ink-3);letter-spacing:.03em}
.legend{display:flex;gap:18px;flex-wrap:wrap;align-items:center;margin:20px 0 26px;
  padding:12px 14px;background:var(--panel);border:1px solid var(--line);
  border-radius:3px}
.key{display:flex;gap:7px;align-items:center;font-size:13px;color:var(--ink-2)}
.swatch{width:20px;height:3px;border-radius:2px;display:inline-block}
h2{font-family:"IBM Plex Sans Condensed","IBM Plex Sans",sans-serif;
  font-weight:600;font-size:13px;letter-spacing:.11em;text-transform:uppercase;
  color:var(--ink-3);margin:38px 0 12px;padding-bottom:7px;
  border-bottom:1px solid var(--line)}
table{width:100%;border-collapse:collapse;font-size:13.5px;
  font-variant-numeric:tabular-nums}
th{text-align:right;font-weight:600;font-size:11px;letter-spacing:.07em;
  text-transform:uppercase;color:var(--ink-3);padding:6px 9px;
  border-bottom:1px solid var(--line);white-space:nowrap}
th:first-child,td:first-child{text-align:left}
td{padding:6px 9px;border-bottom:1px solid var(--line-2);text-align:right;
  white-space:nowrap}
td.name{font-family:"IBM Plex Mono",ui-monospace,monospace;font-size:12px}
.scroller{overflow-x:auto;background:var(--panel);border:1px solid var(--line);
  border-radius:3px;padding:4px 10px 2px}
.pill{display:inline-block;font-family:"IBM Plex Mono",ui-monospace,monospace;
  font-size:10.5px;font-weight:600;padding:1.5px 6px;border-radius:2px;
  letter-spacing:.02em}
.p-good{background:var(--good-bg);color:var(--good)}
.p-bad{background:var(--bad-bg);color:var(--bad)}
.p-warn{background:var(--warn-bg);color:var(--warn)}
.card{background:var(--panel);border:1px solid var(--line);border-radius:3px;
  padding:16px 18px 18px;margin:14px 0}
.card.miscount{border-left:3px solid var(--bad)}
.card.excluded{border-left:3px solid var(--warn)}
.chead{display:flex;justify-content:space-between;align-items:baseline;gap:16px;
  flex-wrap:wrap;margin-bottom:4px}
.cname{font-family:"IBM Plex Mono",ui-monospace,monospace;font-size:14px;
  font-weight:600}
.cstats{display:flex;gap:15px;flex-wrap:wrap;font-size:12.5px;color:var(--ink-2);
  font-variant-numeric:tabular-nums}
.cstats b{color:var(--ink);font-weight:600}
.panels{display:flex;gap:14px;align-items:flex-start;overflow-x:auto;
  padding:12px 0 4px}
figure{margin:0;flex:0 0 auto}
figcaption{font-family:"IBM Plex Mono",ui-monospace,monospace;font-size:10.5px;
  color:var(--ink-3);text-align:center;margin-top:3px;
  font-variant-numeric:tabular-nums}
.plot{background:transparent;display:block;border:1px solid var(--line-2);
  border-radius:2px}
.setplot{border-color:var(--line)}
.note{font-size:12.5px;color:var(--ink-3);font-style:italic;padding:2px 0}
.caveat{background:var(--panel);border:1px solid var(--line);
  border-left:3px solid var(--warn);border-radius:3px;padding:13px 16px;
  margin:14px 0;font-size:13.5px;color:var(--ink-2)}
.caveat b{color:var(--ink)}
a{color:var(--video)}
"""


def svg_pair(vid, pipe, w, h, cls=""):
    dv, dp, spanx, spany = pair_d(vid, pipe, (w, h))
    return (f'<svg class="plot {cls}" width="{w}" height="{h}" '
            f'viewBox="0 0 {w} {h}" role="img">'
            f'<path d="{dv}" fill="none" stroke="var(--video)" stroke-width="1.6" '
            f'stroke-linejoin="round"/>'
            f'<path d="{dp}" fill="none" stroke="var(--pipe)" stroke-width="1.6" '
            f'stroke-linejoin="round" stroke-dasharray="3 2"/>'
            f'<circle cx="0" cy="0" r="0" fill="none"/></svg>'), spanx, spany


def render(rows):
    esc = html.escape
    scored = [r for r in rows if r["reps"] and not r["strapped"]]
    allh = [x["h"] for r in scored for x in r["reps"] if x]
    parts = []
    parts.append(f"<style>{CSS}</style>")
    parts.append('<link rel="preconnect" href="https://fonts.googleapis.com">'
                 '<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>'
                 '<link rel="stylesheet" href="https://fonts.googleapis.com/css2?'
                 'family=IBM+Plex+Mono:wght@400;600&'
                 'family=IBM+Plex+Sans+Condensed:wght@600&'
                 'family=IBM+Plex+Sans:wght@400;600&display=swap">')
    parts.append('<div class="wrap">')
    parts.append("<h1>Bar Path Review</h1>")
    parts.append('<p class="sub">Every set and every rep in the corpus, the '
                 'video referee against the reconstruction, on a shared axis '
                 'and a shared sign. Both curves are start-aligned, which is '
                 'how <code>vs_truth</code> scores them.</p>')
    parts.append(f'<p class="stamp">{len(rows)} captures · '
                 f'{sum(1 for r in rows for x in r["reps"] if x)} refereed reps · '
                 f'regenerate with <code>python3 analysis/81_rep_gallery.py</code></p>')

    parts.append('<div class="legend">'
                 '<span class="key"><span class="swatch" style="background:var(--video)">'
                 '</span>video — the bar</span>'
                 '<span class="key"><span class="swatch" style="background:var(--pipe);'
                 'opacity:.9"></span>pipeline — the reconstruction</span>'
                 '<span class="key">horizontal axis is fore-aft, vertical is height; '
                 'each panel scales to its own data</span></div>')

    parts.append('<div class="caveat"><b>Read the panels, not the shapes.</b> '
                 'Every panel is scaled to fit, so two panels are not comparable '
                 'by eye — the numbers under each one are. A rep whose curves '
                 'diverge visibly but reads 1.5&nbsp;cm is fine; a rep whose '
                 'curves look similar at 40&nbsp;cm of span is not.</div>')

    # ---- summary -----------------------------------------------------------
    parts.append("<h2>Every capture</h2>")
    parts.append('<div class="scroller"><table><thead><tr>'
                 "<th>capture</th><th>lift</th><th>reps</th><th>h rms</th>"
                 "<th>null</th><th>beats</th><th>v rms</th><th>status</th>"
                 "</tr></thead><tbody>")
    for r in rows:
        cnt = f'{r.get("windows","-")}/{r.get("expected","-")}'
        mis = r.get("windows") != r.get("expected")
        bits = []
        if mis:
            bits.append('<span class="pill p-bad">MISCOUNT</span>')
        if r["strapped"]:
            bits.append('<span class="pill p-warn">STRAPPED</span>')
        if r["note"]:
            bits.append(f'<span class="pill p-warn">{esc(r["note"][:26])}</span>')
        if not bits:
            bits.append('<span class="pill p-good">OK</span>')
        b = r.get("beats")
        bcls = "" if b is None else (' style="color:var(--good)"' if b >= 1
                                     else ' style="color:var(--bad)"')
        if "h_rms" in r:
            nums = (f'<td>{r["h_rms"]:.2f}</td><td>{r["null"]:.2f}</td>'
                    f'<td{bcls}>{b:.2f}</td><td>{r["v_rms"]:.2f}</td>')
        else:
            nums = "<td>—</td>" * 4
        parts.append(
            f'<tr><td class="name">{esc(r["short"])}</td>'
            f'<td>{r["lift"]}</td><td>{cnt}</td>{nums}'
            f'<td>{"".join(bits)}</td></tr>')
    parts.append("</tbody></table></div>")

    # ---- per capture -------------------------------------------------------
    for lift in ("bench", "squat", "deadlift"):
        group = [r for r in rows if r["lift"] == lift]
        parts.append(f"<h2>{lift} — {len(group)} captures</h2>")
        for r in group:
            cls = "card"
            if r.get("windows") != r.get("expected"):
                cls += " miscount"
            if r["strapped"]:
                cls += " excluded"
            parts.append(f'<div class="{cls}">')
            parts.append('<div class="chead">'
                         f'<span class="cname">{esc(r["short"])}</span>'
                         '<span class="cstats">')
            parts.append(f'<span>windows <b>{r.get("windows","–")}</b> / '
                         f'labelled <b>{r.get("expected","–")}</b></span>')
            if "h_rms" in r:
                parts.append(
                    f'<span>h rms <b>{r["h_rms"]:.2f}</b> cm</span>'
                    f'<span>null <b>{r["null"]:.2f}</b></span>'
                    f'<span>beats null <b>{r["beats"]:.2f}</b></span>'
                    f'<span>v rms <b>{r["v_rms"]:.2f}</b> cm</span>')
            parts.append("</span></div>")
            if r["strapped"]:
                parts.append('<p class="note">Lifting straps — the watch moved. '
                             'Excluded from every aggregate; drawn because '
                             'hiding it would misrepresent the corpus.</p>')
            if r["note"]:
                parts.append(f'<p class="note">{esc(r["note"])}</p>')
            reps = [x for x in r["reps"] if x]
            if not reps:
                parts.append("</div>")
                continue

            parts.append('<div class="panels">')
            # the set: every rep overlaid, one shared scale
            allv = np.concatenate([x["vid"] for x in reps])
            allp = np.concatenate([x["pipe"] for x in reps])
            xs = np.concatenate([allv[:, 0], allp[:, 0]]) * 100
            ys = np.concatenate([allv[:, 1], allp[:, 1]]) * 100
            x0, x1, y0, y1 = xs.min(), xs.max(), ys.min(), ys.max()
            W, H = 210, 250
            seg = []
            for x in reps:
                for arr, col, dash in ((x["vid"], "var(--video)", ""),
                                       (x["pipe"], "var(--pipe)", ' stroke-dasharray="3 2"')):
                    d = _d(arr[:, 0] * 100, arr[:, 1] * 100, x0, x1, y0, y1, W, H, 8)
                    seg.append(f'<path d="{d}" fill="none" stroke="{col}" '
                               f'stroke-width="1.3" opacity=".8"{dash}/>')
            parts.append(
                f'<figure><svg class="plot setplot" width="{W}" height="{H}" '
                f'viewBox="0 0 {W} {H}" role="img">{"".join(seg)}</svg>'
                f'<figcaption>whole set · {x1-x0:.0f}×{y1-y0:.0f} cm</figcaption></figure>')

            for x in reps:
                svg, sx, sy = svg_pair(x["vid"], x["pipe"], 150, 250)
                beat = x["null"] / x["h"] if x["h"] else float("inf")
                col = "var(--good)" if beat >= 1 else "var(--bad)"
                parts.append(
                    f"<figure>{svg}<figcaption>rep {x['k']+1} · "
                    f'<span style="color:{col}">{x["h"]:.2f}</span>/'
                    f'{x["null"]:.2f} cm<br>miss {x["close_h"]:.1f} cm · '
                    f'ROM {x["rom"]:.0f}</figcaption></figure>')
            parts.append("</div>")
            parts.append('<p class="note">Per rep: horizontal rms / null, then '
                         'how far the real bar missed returning to its start.</p>')
            parts.append("</div>")

    parts.append("</div>")
    return "\n".join(parts)


if __name__ == "__main__":
    rows = collect()
    OUT.write_text("<title>Bar Path Review</title>\n" + render(rows))
    n = sum(1 for r in rows for x in r["reps"] if x)
    print(f"wrote {OUT}  —  {len(rows)} captures, {n} refereed reps, "
          f"{OUT.stat().st_size/1024:.0f} kB")
