"""Streaming sticker detection for data_v2 footage.

Decodes a clip once, in colour, and keeps only per-frame blob detections. The
whole clip's pixels never live in memory at once, so several of these can run
side by side on the 8 GB machine.

Why colour: the stickers are white (low saturation, high value) and the rims
they sit on are saturated blue/yellow. `markers.py` decodes greyscale and
throws that separation away. We keep both a top-hat response on value and the
local saturation so downstream stages can use either.
"""
from __future__ import annotations

import subprocess
from pathlib import Path

import numpy as np
from scipy import ndimage


def probe(path):
    out = subprocess.run(
        ["ffprobe", "-v", "error", "-select_streams", "v:0",
         "-show_entries", "stream=width,height,r_frame_rate",
         "-of", "csv=p=0", str(path)],
        capture_output=True, text=True, check=True).stdout.strip().split(",")
    w, h = int(out[0]), int(out[1])
    num, den = out[2].split("/")
    return w, h, float(num) / float(den)


def frames_rgb(path, chunk=64):
    """Yield (n, H, W, 3) uint8 chunks. Streaming — never holds the clip."""
    w, h, _ = probe(path)
    proc = subprocess.Popen(
        ["ffmpeg", "-loglevel", "error", "-i", str(path),
         "-pix_fmt", "rgb24", "-f", "rawvideo", "-"],
        stdout=subprocess.PIPE, bufsize=10 ** 8)
    fsz = w * h * 3
    try:
        while True:
            buf = proc.stdout.read(fsz * chunk)
            if not buf:
                break
            n = len(buf) // fsz
            if n == 0:
                break
            yield np.frombuffer(buf[:n * fsz], np.uint8).reshape(n, h, w, 3)
    finally:
        proc.stdout.close()
        proc.wait()


def _subpixel(resp, ys, xs, r=2):
    """Intensity-weighted centroid in a (2r+1)^2 window, on resp - local min."""
    H, W = resp.shape
    out = np.empty((len(ys), 2), np.float32)
    for i, (y, x) in enumerate(zip(ys, xs)):
        y0, y1 = max(0, y - r), min(H, y + r + 1)
        x0, x1 = max(0, x - r), min(W, x + r + 1)
        w = resp[y0:y1, x0:x1].astype(np.float64)
        w = w - w.min()
        s = w.sum()
        if s <= 0:
            out[i] = (y, x)
            continue
        gy, gx = np.mgrid[y0:y1, x0:x1]
        out[i] = ((w * gy).sum() / s, (w * gx).sum() / s)
    return out


def _sector_contrast(v, ys, xs, r_in=2.0, r_out=5.5, n_sect=8):
    """Blob-ness: how much brighter the core is than its DARKEST-lit surround.

    A sticker is an isolated bright disc, so every direction around it is dark
    and the score is high. A point on a bright ridge — a ceiling strip light, a
    rack edge, a bar sleeve — has two directions that are just as bright, so
    taking the *worst* sector drives its score to nearly zero.

    This is the discriminator the greyscale top-hat in `markers.response` does
    not have: a top-hat only asks whether a pixel beats its neighbourhood on
    average, which a point on a long bright line comfortably does. Line-like
    clutter is most of what an indoor gym frame contains.
    """
    H, W = v.shape
    k = int(np.ceil(r_out))
    dy, dx = np.mgrid[-k:k + 1, -k:k + 1]
    rad = np.hypot(dy, dx)
    core = rad <= r_in
    ring = (rad > r_in) & (rad <= r_out)
    ang = (np.degrees(np.arctan2(dy, dx)) + 360) % 360
    sect = [(ring & (ang >= s * 360 / n_sect) & (ang < (s + 1) * 360 / n_sect))
            for s in range(n_sect)]
    out = np.zeros(len(ys), np.float32)
    smear = np.zeros(len(ys), np.float32)
    for i, (y, x) in enumerate(zip(ys, xs)):
        if y - k < 0 or y + k + 1 > H or x - k < 0 or x + k + 1 > W:
            out[i] = 0.0
            continue
        patch = v[y - k:y + k + 1, x - k:x + k + 1]
        c = patch[core].mean()
        means = sorted((patch[s].mean() if s.any() else 0.0) for s in sect)
        out[i] = c - means[-1]
        # Same score ignoring the two brightest sectors. A motion-blurred
        # sticker is a short streak, so it has two bright OPPOSITE sectors and
        # the strict score drives it to zero — the filter that removes ridges
        # removes it for exactly the same reason. See `detect_frame`.
        smear[i] = c - means[-3]
    return out, smear


def detect_frame(rgb, size=7, max_dets=80, min_resp=0.04, merge_px=3.0,
                 max_relaxed=60):
    """Bright compact blobs in one RGB frame.

    Returns (m, 6): y, x, blob-ness, whiteness, top-hat response, and a
    flag that is 0 for the strict block and 1 for the relaxed one.

    `whiteness` is 1 - saturation at the blob, so a white sticker on a blue rim
    scores high and a blue rim highlight scores low. It is reported, never
    thresholded here — thresholding it would lose the stickers on the black
    plates, where the rim is unsaturated too.
    """
    f = rgb.astype(np.float32) / 255.0
    v = f.max(2)
    mn = f.min(2)
    sat = np.where(v > 1e-6, (v - mn) / np.maximum(v, 1e-6), 0.0)

    # Detect on WHITENESS — bright AND unsaturated — not on brightness.
    #
    # The stickers are white; every plate they sit on is strongly coloured
    # (blue rim, yellow face) or black. On brightness alone a white sticker on
    # the blue rim of a yellow-faced plate is barely a local maximum at all,
    # because the yellow face beside it is just as bright: measured on
    # `bench_92.5x4_1`, only 4 to 6 of the 8 stickers survived brightness
    # ranking, and that shortfall is what let 5-slot rack clutter outscore the
    # real plate in the clip-level search.
    #
    #   sticker   v~0.90 sat~0.10 -> 0.81
    #   yellow    v~0.85 sat~0.80 -> 0.17
    #   blue rim  v~0.50 sat~0.70 -> 0.15
    #   black     v~0.20 sat~0.10 -> 0.18
    #
    # `markers.py` decodes greyscale and cannot make this distinction at all.
    v = v * (1.0 - sat)

    # White top-hat: brighter than the surrounding neighbourhood.
    opened = ndimage.grey_opening(v, size=size)
    resp = v - opened

    # Local maxima of the response.
    mx = ndimage.maximum_filter(resp, size=3)
    peak = (resp == mx) & (resp > min_resp)
    ys, xs = np.nonzero(peak)
    if len(ys) == 0:
        return np.zeros((0, 6), np.float32)

    r = resp[ys, xs]
    # Keep a generous top-hat shortlist, then rank it by blob-ness. Ranking on
    # the top-hat alone is what lets ridge clutter fill the list.
    pre = min(len(ys), max(max_dets * 4, 400))
    keep = np.argpartition(-r, pre - 1)[:pre]
    ys, xs, r = ys[keep], xs[keep], r[keep]

    blob, smear = _sector_contrast(v, ys, xs)
    yx = _subpixel(resp, ys, xs)

    # One sticker, one detection. `maximum_filter` returns every cell of a flat
    # plateau, so a 5 px marker routinely yields two or three peaks a fraction
    # of a pixel apart. C27 hit this on the eight-sticker deadlifts — 9 and 10
    # model slots for 8 stickers — and it double-weights a sticker in an
    # unweighted fit. Downstream it also inflates every inlier count, which is
    # worse: it makes clutter look like a constellation.
    def _dedup(order, cap, already=()):
        """Top `cap` in `order`, no two within `merge_px`."""
        keep, pts = [], list(already)
        for i in order:
            if all(np.hypot(*(yx[i] - q)) > merge_px for q in pts):
                keep.append(i)
                pts.append(yx[i])
            if len(keep) >= cap:
                break
        return np.array(keep, int), pts

    strict_i, pts = _dedup(np.argsort(-blob)[blob[np.argsort(-blob)] > 0],
                           max_dets)
    # A SECOND, relaxed block, kept separate rather than merged.
    #
    # These are candidates the strict blob-ness score rejects but the
    # smear-tolerant one accepts: predominantly motion-blurred stickers, and
    # inevitably some ridge clutter too, since ignoring the two brightest
    # sectors is exactly what makes a long bright line admissible again.
    #
    # They are flagged instead of merged so the clip-level search never sees
    # them. Seeding decides WHICH circle is the plate, and a noisier candidate
    # list can only make that decision worse; tracking already knows where the
    # plate is to within a few pixels and has the 8-fold lattice to check
    # against, so there the extra clutter is harmless. The relaxed block can
    # therefore only ever recover frames, never change which plate is chosen.
    rel_order = [i for i in np.argsort(-smear)
                 if smear[i] > 0 and blob[i] <= 0]
    relax_i, _ = _dedup(rel_order, max_relaxed, already=pts)

    idx = np.concatenate([strict_i, relax_i]) if len(relax_i) else strict_i
    flag = np.concatenate([np.zeros(len(strict_i)), np.ones(len(relax_i))])
    yx, blob, r, ys, xs = yx[idx], blob[idx], r[idx], ys[idx], xs[idx]
    white = 1.0 - sat[ys, xs]
    return np.column_stack([yx[:, 0], yx[:, 1], blob, white, r,
                            flag[:len(idx)]]).astype(np.float32)


def detect_clip(path, cache_dir=None, force=False, **kw):
    """All detections for a clip, cached.

    Stored concatenated with an offsets array rather than as a ragged object
    array: when every frame happens to yield the same number of detections
    numpy silently builds a 3-D object array instead of a list of 2-D float
    ones, and the dtype error surfaces a long way downstream.
    """
    path = Path(path)
    if cache_dir is not None:
        cache = Path(cache_dir) / (path.stem + ".npz")
        if cache.exists() and not force:
            z = np.load(cache)
            flat, off = z["flat"], z["off"]
            dets = [flat[off[i]:off[i + 1]] for i in range(len(off) - 1)]
            return dets, float(z["fps"]), tuple(z["shape"])
    w, h, fps = probe(path)
    dets = []
    for chunk in frames_rgb(path):
        for fr in chunk:
            dets.append(detect_frame(fr, **kw))
    if cache_dir is not None:
        Path(cache_dir).mkdir(parents=True, exist_ok=True)
        off = np.concatenate([[0], np.cumsum([len(d) for d in dets])])
        np.savez_compressed(cache, flat=np.concatenate(dets).astype(np.float32),
                            off=off.astype(np.int64), fps=fps, shape=(h, w))
    return dets, fps, (h, w)


if __name__ == "__main__":
    import sys, time
    for p in sys.argv[1:]:
        t = time.time()
        dets, fps, shape = detect_clip(p, cache_dir="/Users/sam/.claude/jobs/b4b2d95a/tmp/dets")
        n = np.array([len(d) for d in dets])
        print(f"{Path(p).stem:38s} {len(dets):5d} frames  dets/frame "
              f"min {n.min():3d} med {int(np.median(n)):3d} max {n.max():3d}"
              f"  {time.time()-t:5.1f}s")


def strict_pts(d, max_dets=80):
    """The strict block only — what the clip-level search is allowed to see."""
    d = np.asarray(d, float)
    if d.shape[1] < 6:
        return d[:max_dets, :2]
    return d[d[:, 5] == 0][:max_dets, :2]


def all_pts(d, max_dets=80, max_relaxed=60):
    """Strict block plus the smear-tolerant one, for tracking only."""
    d = np.asarray(d, float)
    if d.shape[1] < 6:
        return d[:max_dets, :2]
    strict = d[d[:, 5] == 0][:max_dets]
    relax = d[d[:, 5] == 1][:max_relaxed]
    return np.concatenate([strict[:, :2], relax[:, :2]]) if len(relax) \
        else strict[:, :2]
