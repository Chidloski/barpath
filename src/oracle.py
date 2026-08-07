"""How close can a PHYSICAL error model bring the IMU to the video? — C28.

This is a measurement, not a stage. Nothing here is in the pipeline and nothing
here should be: it fits parameters against the video it is scored on, which is
the definition of cheating if the number is quoted as accuracy. What it is for
is finding the CEILING of a family of corrections, so that work is not spent
building an estimator for a term that could not have paid off.

The same job B3's oracle does for the per-rep detrend, one layer upstream.

The rule that makes it evidence rather than curve-fitting
---------------------------------------------------------
**Every parameter must name a real defect of the sensor or the geometry, and
its fitted value is checked against what that defect is known to be.** A model
that reaches the spec on an implausible parameter has not found the error; it
has found a flexible enough basis, and it convicts itself.

That check is not hypothetical. B2 fitted the wrist offset `d` against this
same video objective and got |d| = 21, 64 and 60 cm on the three deadlifts,
against a real wrist-to-bar distance of 10-15 cm. The fit was absorbing P3,
which is also a body-frame constant swept by a rotating forearm and therefore
nearly degenerate with `d`. The lesson generalises to everything here: **a
lower residual is not a better model.**

The second discipline is GENERALISATION. Every model is also fitted
leave-one-out — parameters from two captures, scored on the third. A real
error model transfers, because the defect is a property of the watch and the
lifter rather than of the clip. An absorber does not, and B2's LOO returned
|d| = 129 cm and made the held-out capture worse.

The ladder
----------
Each model adds terms to the one above it, and each term is a named defect:

* `bias` — a constant body-frame accelerometer offset, added to `accel_body`
  before rotation. Measured on a table at **0.0025 g** (P4), so that is the
  scale a fitted value has to be near.
* `tilt` — a constant small rotation between Core Motion's world frame and the
  true one. Leaks gravity: a tilt of theta puts g*sin(theta) into horizontal,
  which is 1.7 cm/s^2 per 0.1 degree. C6 bounds the attitude at a still hold to
  0.05-0.14 degrees, worst case 0.27, so a fit far outside that is not tilt.
* `scale` — a diagonal accelerometer sensitivity error. Consumer MEMS parts
  are specified around 1%; 10% would be a broken part.
* `lever` — the wrist-to-bar offset `d` of step 6. Real magnitude 10-15 cm.
  Included because B2's failure is a RESULT to reproduce and place in the
  ladder, not a reason to omit the term.
* `gravref` — the one term here that is not constant, and the reason this
  module exists. Core Motion estimates gravity by trusting the accelerometer
  as a plumb line; while the bar is accelerating hard that reference is wrong,
  so the attitude error should grow with |a| rather than sit still. Modelled
  as a tilt proportional to |userAcceleration|, which is one parameter per
  axis and is the only candidate in the ladder that can produce error AT REP
  FREQUENCY without being given a rep-frequency basis to do it with.

What is deliberately NOT here
-----------------------------
No per-rep parameters, and no basis functions of time. Those reach any
residual you like and say nothing — B3's oracle already showed a per-rep
quadratic gets bench inside spec while meaning nothing about the physics. Every
parameter in this module is **constant over the whole capture**, which is what
makes a fitted value comparable to a datasheet.

Segmentation is frozen from the unperturbed run. The optimiser is not allowed
to move rep boundaries: that would let it improve the score by re-cutting the
comparison rather than by fixing the acceleration, and the two are not the same
finding.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
from scipy.optimize import minimize
from scipy.spatial.transform import Rotation

from . import calibrate, correct, integrate, metrics, orient

# Parameter counts per named term, in ladder order.
TERMS = {
    "bias": 3,       # body-frame accel offset, m/s^2
    "tilt": 3,       # constant world-frame attitude offset, rad
    "scale": 3,      # diagonal accel sensitivity, dimensionless (1 + s)
    "lever": 3,      # wrist-to-bar offset d, body frame, m
    "gravref": 3,    # tilt per unit |userAccel|, rad / (m/s^2)
}

# What each term is known to be, physically. A fit outside this is the model
# absorbing something else — see the module docstring. Units match TERMS.
PLAUSIBLE = {
    "bias": (0.025, "m/s^2   (P4 measured 0.0025 g = 0.025 m/s^2 on a table)"),
    "tilt": (np.deg2rad(0.3), "rad   (C6: 0.05-0.14 deg at a still hold, 0.27 worst)"),
    "scale": (0.02, "        (consumer MEMS sensitivity error ~1%)"),
    "lever": (0.15, "m       (real wrist-to-bar distance 10-15 cm)"),
    "gravref": (np.deg2rad(0.3) / 9.81, "rad per m/s^2   (0.3 deg at 1 g)"),
}

LADDER = [
    (),
    ("bias",),
    ("bias", "tilt"),
    ("bias", "tilt", "scale"),
    ("bias", "tilt", "scale", "lever"),
    ("bias", "tilt", "gravref"),
    ("bias", "tilt", "scale", "lever", "gravref"),
]


def unpack(theta: np.ndarray, terms: tuple) -> dict:
    """Split a flat parameter vector into named terms."""
    out, i = {}, 0
    for name in terms:
        n = TERMS[name]
        out[name] = np.asarray(theta[i:i + n], dtype=float)
        i += n
    return out


def n_params(terms: tuple) -> int:
    return sum(TERMS[t] for t in terms)


def apply_model(log: dict, quat_corrected: np.ndarray, p: dict) -> np.ndarray:
    """World-frame acceleration under the error model. The whole physics of C28.

    Order matters and follows the signal path through the hardware:

    1. `scale` and `bias` are properties of the ACCELEROMETER, so they act on
       the body-frame reading before anything rotates it.
    2. `tilt` and `gravref` are properties of the ATTITUDE, so they perturb the
       rotation that carries the reading into the world.

    Writing it the other way round — biasing after rotation, say — would be a
    world-frame bias, which is not a thing any part of this hardware has, and
    is exactly the kind of term that fits well and means nothing.
    """
    a_body = np.asarray(log["accel"], dtype=float)
    if "scale" in p:
        a_body = a_body * (1.0 + p["scale"])
    if "bias" in p:
        a_body = a_body + p["bias"]

    q = quat_corrected
    rot = None
    if "tilt" in p:
        rot = Rotation.from_rotvec(p["tilt"])
    if "gravref" in p:
        # A tilt that grows with how hard the bar is accelerating. |a| is taken
        # from the RAW body reading, not the corrected one, because it stands
        # in for how badly Core Motion's own accelerometer-as-plumb-line was
        # being misled at that instant — that is the reported attitude's input,
        # not ours.
        mag = np.linalg.norm(np.asarray(log["accel"], dtype=float), axis=1)
        vec = mag[:, None] * p["gravref"][None, :]
        per = Rotation.from_rotvec(vec)
        rot = per if rot is None else per * rot

    if rot is not None:
        # Perturb in the WORLD frame: this is an error in where Core Motion
        # thinks down is, not an error in how the watch sits on the wrist.
        q_r = Rotation.from_quat(q, scalar_first=True)
        q = (rot * q_r).as_quat(scalar_first=True)

    return orient.to_world(a_body, log["quat"], q)


def body_frame_bias(log: dict, quat: np.ndarray,
                    world: np.ndarray) -> np.ndarray:
    """The pause bias as a BODY-frame vector. Zero fitted parameters.

    `calibrate.accel_bias` measures the mean world acceleration over the
    stillest pre-set second and subtracts it as a world-frame constant. Its own
    docstring says the bias is fixed in the BODY frame — and then subtracts it
    in the world one, which is only the same thing while the watch does not
    move. It moves: the whole of P3 is that the forearm rotates through the rep.

    So the shipping correction applies a body-frame quantity rotated by the
    attitude at the PAUSE to samples taken at every other attitude in the
    capture. This rotates it back once, at the pause, and then forward again per
    sample — which is what "fixed in the body frame" actually means.

    This is the same posture argument C6 used to refuse reading the change
    between the opening and closing attitude anchors (P5): a world-frame
    residual is the body-frame bias rotated by whatever the watch was doing at
    the time, so two of them are not comparable unless the watch was doing the
    same thing.
    """
    i, j = calibrate.stillest_window(log, 3.0, 1.0)
    r_pause = Rotation.from_quat(quat[i:j], scalar_first=True)
    return r_pause.inv().apply(world[i:j]).mean(axis=0)


def split_bias(log: dict, quat: np.ndarray, world: np.ndarray,
               span_s: float = 1.5) -> dict | None:
    """Separate the world-frame TILT LEAK from the body-frame ACCEL BIAS.

    Zero parameters fitted against the video. This is the decomposition C6's
    `calibrate.anchor_tilt` docstring says the pause residual is made of, and
    which C6 then declined to read because "the watch's posture differs at the
    two anchors". **That posture difference is exactly what makes it solvable.**

    At a still hold the world-frame acceleration must be zero, so whatever is
    left is the error. It has two parts that transform differently:

        r = tau + R . b

    `tau` is a world-frame constant — an error in where Core Motion thinks down
    is, which leaks g*sin(theta) and does not care how the wrist is turned.
    `b` is a body-frame constant — an accelerometer offset, which rotates with
    the watch. One hold gives three equations and six unknowns. The C3 phase
    column gives TWO holds, at different wrist postures, hence:

        r_open - r_close = (R_open - R_close) . b

    which determines `b`, and then `tau` follows. C28 built this after finding
    that neither pure correction generalises — the body-frame one helps 5 of 6
    deadlifts and hurts 10 of 11 benches, which is what a MIXTURE looks like
    when you force it to be one thing or the other.

    Returns None where it cannot be done honestly: no phase column (pre
    2026-07-30), a missing hold, or — the one that matters — two holds at too
    similar a posture. `(R_open - R_close)` is then near-singular and `b` is
    the reciprocal of a small number, so `cond` is returned and the caller must
    refuse on it rather than trusting a large `b` that came out of noise.
    """
    w = calibrate.hold_windows(log, span_s)
    if w.get("open") is None or w.get("close") is None:
        return None
    rot = Rotation.from_quat(quat, scalar_first=True)
    out = {}
    for k in ("open", "close"):
        idx = w[k]
        out["r_" + k] = world[idx].mean(axis=0)
        out["R_" + k] = rot[idx].mean().as_matrix()
    d = out["R_open"] - out["R_close"]

    # THE DIFFERENCE OF TWO ROTATION MATRICES IS ALWAYS RANK <= 2, exactly, and
    # this is a structural limit rather than a conditioning problem to be tuned
    # away. Write it as R_open - R_close = R_open (I - R_open^T R_close). The
    # relative rotation fixes its own axis n, so (I - Delta) n = 0 identically,
    # and therefore (R_open - R_close) n = 0 for EVERY pair of postures however
    # far apart they are. Verified numerically at 91-137 degrees of separation:
    # the third singular value is 0 to machine precision every time.
    #
    # So two holds determine the body bias only in the PLANE perpendicular to
    # the axis the wrist rotates about between them. The component along that
    # axis is unobservable, and a plain `lstsq` with rcond=None does not decline
    # it — it divides by a 1e-16 singular value and returns 1e12 m/s^2, which is
    # what C28 first saw. Truncating instead gives the minimum-norm solution:
    # recover what is observable, and set the rest to zero rather than to noise.
    #
    # THREE holds at genuinely different postures would determine it in full,
    # because three pairwise differences have three different null axes and only
    # b = 0 lies in all of them. That is a capture-protocol change, not code.
    u, sv, vt = np.linalg.svd(d)
    keep = sv > 1e-8 * sv[0]
    rank = int(keep.sum())
    if rank < 2:
        return None
    dr = out["r_open"] - out["r_close"]
    b = vt[:rank].T @ ((u[:, :rank].T @ dr) / sv[:rank])
    axis = vt[rank:].T if rank < 3 else np.zeros((3, 0))
    tau = out["r_open"] - out["R_open"] @ b
    return {"body": b, "tilt": tau, "rank": rank,
            "unobservable_axis": axis, "sv": sv,
            "r_open": out["r_open"], "r_close": out["r_close"]}


def rebuild(base: dict, p: dict, world_bias: bool = True,
            bias_frame: str = "world", lever0: np.ndarray | None = None) -> dict:
    """A `pipeline.run`-shaped dict with the error model applied.

    Steps 4, 6 and 7 are re-run. Step 5 is NOT: `bounds` is carried over from
    the unperturbed run so the optimiser cannot improve its score by re-cutting
    the reps. See the module docstring.

    `world_bias` is the shipping `calibrate.accel_bias` subtraction, and it is
    a switch rather than a constant because C28 found it is a NEGATIVE term.
    It is not one of the fitted parameters — it has none — so it belongs here
    as an ablation and not in the ladder's parameter vector.

    `lever0` is a wrist offset `d` that is KNOWN rather than fitted — C31b,
    2026-08-06, after the owner tape-measured it into `correct.WRIST_OFFSET_M`.
    It is deliberately separate from the `lever` TERM rather than replacing it,
    because the two ask different questions and both are worth asking:

    * `lever0` alone, with `lever` out of the term tuple, is the ladder run on a
      signal that no longer contains a contaminant we now know is real. Every
      C28 number was measured with step 6 OFF, so every one of them was fitted
      against `d`'s residue as well as against the defect it names.
    * `lever0` AND a fitted `lever` makes the fitted term a RESIDUAL on the
      tape — "how far from the measurement does the optimiser still want to
      go?" — which is a sharper plausibility check than C28's, because it is
      scored against a measured vector rather than against a range of plausible
      wrist lengths. They add, so the fit can still reach anywhere.
    """
    log = base["log"]
    world = apply_model(log, base["quat"], p)
    if world_bias and bias_frame == "world":
        world = world - calibrate.accel_bias(world, log)
    elif world_bias and bias_frame == "body":
        b = body_frame_bias(log, base["quat"], world)
        world = world - Rotation.from_quat(base["quat"],
                                           scalar_first=True).apply(b)
    elif world_bias and bias_frame == "split":
        sp = split_bias(log, base["quat"], world)
        if sp is None:
            world = world - calibrate.accel_bias(world, log)
        else:
            r = Rotation.from_quat(base["quat"], scalar_first=True)
            world = world - (sp["tilt"] + r.apply(sp["body"]))
    velocity, position = integrate.integrate(world, log["dt"])

    d = np.zeros(3)
    if lever0 is not None:
        d = d + np.asarray(lever0, dtype=float)
    if "lever" in p:
        d = d + np.asarray(p["lever"], dtype=float)
    if np.any(d):
        position = correct.apply_offset(position, base["quat"], d)

    bounds = base["bounds"]
    reps = correct.detrend_set(position, bounds, log["t"]) if bounds else []
    # `velocity` and `world_accel` ride along because `metrics.bench_sync`
    # reads them; without them every bench capture raises KeyError and the
    # ablation silently becomes deadlift-only, which is the half of the corpus
    # that would NOT have caught a regression.
    return {"path": base["path"], "log": log, "bounds": bounds,
            "reps": reps, "bar_position": position,
            "velocity": velocity, "world_accel": world,
            "quat": base["quat"], "impacts": base.get("impacts")}


def objective(theta: np.ndarray, terms: tuple, base: dict, video: dict,
              world_bias: bool = True, bias_frame: str = "world",
              lever0: np.ndarray | None = None) -> float:
    """Median per-rep horizontal rms in cm. Inf where the model is unusable.

    Horizontal ALONE, deliberately. It is the axis with the spec that matters,
    the axis the display magnifies 4x, and the one the reconstruction fails on;
    including vertical would let a model trade the axis under test against one
    already close and report a better total for a worse answer.
    """
    try:
        res = rebuild(base, unpack(theta, terms), world_bias, bias_frame, lever0)
        if not res["reps"]:
            return np.inf
        m = metrics.vs_truth(res, video)
        v = float(m["pipeline_h_rms"])
        return v if np.isfinite(v) else np.inf
    except Exception:
        return np.inf


def fit(base: dict, video: dict, terms: tuple, restarts: int = 3,
        seed: int = 0, world_bias: bool = True,
        bias_frame: str = "world", lever0: np.ndarray | None = None) -> dict:
    """Fit one model to one capture. Nelder-Mead from several starts.

    Derivative-free on purpose: the objective runs a double integration, a
    per-rep detrend and a PCA, and the detrend's rep-closure makes it only
    piecewise smooth in the parameters. A gradient method reports convergence
    on that surface without having found anything.

    `lever0` is a known, un-fitted wrist offset — see `rebuild`.
    """
    if not terms:
        m = metrics.vs_truth(rebuild(base, {}, world_bias, bias_frame, lever0),
                             video)
        return {"terms": terms, "theta": np.zeros(0),
                "h_rms": float(m["pipeline_h_rms"]),
                "null": float(m["null_h_rms"]),
                "beats_null": float(m["beats_null"]),
                "v_rms": float(m["pipeline_v_rms"])}

    n = n_params(terms)
    rng = np.random.default_rng(seed)
    scales = np.concatenate([np.full(TERMS[t], PLAUSIBLE[t][0]) for t in terms])

    best = None
    for k in range(restarts):
        x0 = np.zeros(n) if k == 0 else rng.normal(0.0, 0.5, n) * scales
        r = minimize(objective, x0,
                     args=(terms, base, video, world_bias, bias_frame, lever0),
                     method="Nelder-Mead",
                     options={"maxiter": 400 * n, "xatol": 1e-6,
                              "fatol": 1e-4, "adaptive": True})
        if best is None or r.fun < best.fun:
            best = r

    res = rebuild(base, unpack(best.x, terms), world_bias, bias_frame, lever0)
    m = metrics.vs_truth(res, video)
    return {"terms": terms, "theta": best.x, "h_rms": float(best.fun),
            "null": float(m["null_h_rms"]),
            "beats_null": float(m["beats_null"]),
            "v_rms": float(m["pipeline_v_rms"])}


def plausibility(theta: np.ndarray, terms: tuple) -> list[str]:
    """One line per term: fitted magnitude against what the defect really is."""
    p = unpack(theta, terms)
    out = []
    for name in terms:
        mag = float(np.linalg.norm(p[name]))
        lim, unit = PLAUSIBLE[name]
        verdict = "ok" if mag <= lim else f"{mag / lim:.0f}x TOO BIG"
        out.append(f"{name:8s} |v| = {mag:9.4g}  vs {lim:9.4g} {unit}  -> {verdict}")
    return out


def figure(ladder: dict, loo: dict, ablation: list, holds: list):
    """The four panels C28 turns on. Drawn here rather than in `plot.py`
    because this is a measurement module and the figure is part of the
    measurement, not part of the product.

    `ladder` and `loo` map term-tuple -> list of per-capture h_rms.
    `ablation` is (name, world, body, null, lift) per capture.
    `holds` is (name, rel_rot_deg, amplification, |b|) per capture with phase.
    """
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    fig, ax = plt.subplots(2, 2, figsize=(15, 11))

    # --- 1: the ceiling and whether it transfers -------------------------
    a = ax[0][0]
    labels = ["none" if not t else "+".join(t) for t in ladder]
    x = np.arange(len(labels))
    ceil = [float(np.median(ladder[t])) for t in ladder]
    gen = [float(np.median(loo[t])) for t in loo]
    a.bar(x - 0.2, ceil, 0.4, label="fitted ON the capture (ceiling)", color="tab:blue")
    a.bar(x + 0.2, gen, 0.4, label="leave-one-out (does it transfer?)", color="tab:red")
    a.axhline(1.6, color="0.3", ls="--", lw=1.4, label="flat-line null (~1.6 cm)")
    a.axhline(1.0, color="tab:green", ls=":", lw=1.4, label="1 cm spec")
    a.set_xticks(x)
    a.set_xticklabels(labels, rotation=25, ha="right", fontsize=7)
    a.set_ylabel("median horizontal rms, cm")
    a.set_title("Every physically-named model, fitted against the video\n"
                "Blue is the CEILING no estimator can beat; red is what survives",
                fontsize=9)
    a.legend(fontsize=7)

    # --- 2: which frame the pause bias belongs in ------------------------
    a = ax[0][1]
    names = [r[0] for r in ablation]
    w = np.array([r[1] for r in ablation])
    b = np.array([r[2] for r in ablation])
    lift = [r[4] for r in ablation]
    x = np.arange(len(names))
    col = ["tab:orange" if l == "deadlift" else "tab:purple" for l in lift]
    a.bar(x - 0.2, w, 0.4, label="world frame (shipping)", color="0.6")
    a.bar(x + 0.2, b, 0.4, label="body frame", color=col)
    a.set_xticks(x)
    a.set_xticklabels(names, rotation=90, fontsize=6)
    a.set_ylabel("horizontal rms, cm")
    a.set_title("calibrate.accel_bias: which frame?\n"
                "orange = deadlift (body wins 5/6), purple = bench (world wins 10/11)",
                fontsize=9)
    a.legend(fontsize=7)

    # --- 3: the two-hold decomposition, and what it needs ---------------
    a = ax[1][0]
    ang = np.array([h[1] for h in holds])
    bb = np.array([h[3] for h in holds])
    a.scatter(ang, bb, s=48, c=np.where(ang >= 30, "tab:green", "tab:red"), zorder=3)
    for h in holds:
        a.annotate(h[0].replace("deadlift_", "dl_").replace("bench_", "b_"),
                   (h[1], h[3]), fontsize=6, xytext=(4, 3),
                   textcoords="offset points")
    a.axhline(0.0245, color="tab:blue", ls="--", lw=1.4,
              label="P4's table measurement, 0.0245 m/s$^2$")
    a.axvline(30, color="0.4", ls=":", lw=1.4, label="~30 deg of wrist rotation")
    a.set_yscale("log")
    a.set_xlabel("relative wrist rotation between the two C3 holds, degrees")
    a.set_ylabel("recovered body-frame |b|, m/s$^2$")
    a.set_title("Separating tilt from accel bias needs the two holds to DIFFER\n"
                "Above ~30 deg it recovers the table value; below, it recovers noise",
                fontsize=9)
    a.legend(fontsize=7)

    # --- 4: the structural limit ----------------------------------------
    a = ax[1][1]
    from scipy.spatial.transform import Rotation as _R
    angs = np.linspace(2, 178, 60)
    s2, s3 = [], []
    for t in angs:
        R1 = np.eye(3)
        R2 = _R.from_rotvec(np.deg2rad(t) * np.array([0.3, 0.5, 0.81])).as_matrix()
        sv = np.linalg.svd(R1 - R2, compute_uv=False)
        s2.append(sv[1]); s3.append(sv[2])
    a.plot(angs, s2, lw=2, color="tab:blue", label="2nd singular value (observable)")
    a.plot(angs, s3, lw=2, color="tab:red", label="3rd singular value (ALWAYS zero)")
    a.set_xlabel("relative rotation between the two postures, degrees")
    a.set_ylabel("singular value of $R_{open} - R_{close}$")
    a.set_title("Why two holds can never be enough\n"
                r"$R_1-R_2=R_1(I-R_1^{T}R_2)$ and $(I-\Delta)n=0$: rank $\leq$ 2, exactly",
                fontsize=9)
    a.legend(fontsize=7)

    for row in ax:
        for a_ in row:
            a_.grid(alpha=.25)
            a_.tick_params(labelsize=7)
    fig.suptitle(
        "C28 — how close can a PHYSICAL error model bring the IMU to the video?\n"
        "Answer: to about the flat-line null, and nothing that gets there transfers",
        fontsize=12)
    fig.tight_layout(rect=(0, 0, 1, 0.94))
    return fig


def rest_observables(result: dict, m: dict) -> list[dict]:
    """The velocity error at each rest instant, WITHOUT the video. C28b.

    The whole argument in one line: at a rest instant the true velocity is
    ~zero, so the reconstruction's velocity there IS the velocity error, and it
    is readable from the reconstruction alone. That is the entire information
    content the floor impacts add — one sample of the velocity error per rep.

    `segment.rest_instants` places those instants from raw acceleration and gyro
    only, so this inherits none of the drift it is measuring, and they are
    validated against video at |v| < 0.10 m/s. Deadlift only: bench and squat
    have no raw-signal rest anchor and provably cannot be given one — a bar
    descending at constant velocity reads |a| = g with a quiet gyro exactly as a
    bar at rest does. See `metrics.momentum_closure`.

    Returned per rest-to-rest interval, matched to the rep it most overlaps:
    `dv_h` (the observable, along the display axis), `dv_z` (C11's quantity,
    carried as a negative control), `h_rms` and `span`.
    """
    from . import segment
    rest = segment.rest_instants(result["log"], result["impacts"])
    if len(rest) < 2:
        return []
    t = result["log"]["t"]
    vel = result["velocity"]
    axis = np.real(np.asarray(m["axis"], dtype=float))[:2]
    axis = axis / np.linalg.norm(axis)
    sign = -1.0 if m["axis_flipped"] else 1.0

    out = []
    for j in range(len(rest) - 1):
        i0, i1 = rest[j], rest[j + 1]
        best = None
        for k, (a, b) in enumerate(result["bounds"]):
            ov = min(i1, b - 1) - max(i0, a)
            if ov > 0 and (best is None or ov > best[0]):
                best = (ov, k)
        if best is None:
            continue
        pr = m["per_rep"][best[1]]
        if not pr.get("covered"):
            continue
        out.append({"rep": best[1],
                    "dv_h": sign * float((vel[i1, :2] - vel[i0, :2]) @ axis),
                    "dv_z": float(vel[i1, 2] - vel[i0, 2]),
                    "h_rms": float(pr["pipeline_h_rms"]),
                    "span": float(t[i1] - t[i0])})
    return out


def impact_correction(result: dict) -> dict:
    """Zero the observed velocity error over each rest-to-rest interval. C28b.

    **No free parameters at all.** The correction is a constant horizontal
    acceleration over each interval, sized entirely by the observable `dv`, so
    this is not a fit against the video — it is the minimal thing the
    measurement licenses, and therefore the fairest test of whether using the
    measurement helps.

    It LOSES: worse on 4 of the 6 deadlifts, median 8.21 -> 8.96 cm. Recorded
    because the pairing with `rest_observables` is the finding. The information
    is there (r = 0.77) and this model wastes it, because a constant over a 3 s
    interval is smooth where B6 measured the error to be localised at the
    landing. That is the fourth correction to fail this way — B7's anchor, B6's
    splice, C19's quadratic, and this — and together they say the obstacle is
    the correction's SHAPE IN TIME, not the measurement.

    The consequence for a Kalman filter: a random-walk bias state distributes
    the correction smoothly by construction and would reproduce this exactly.
    What the evidence points at is a jump state AT the impact.
    """
    from . import correct, segment
    log = result["log"]
    rest = segment.rest_instants(log, result["impacts"])
    world = np.asarray(result["world_accel"], dtype=float).copy()
    vel = result["velocity"]
    t = log["t"]
    for j in range(len(rest) - 1):
        i0, i1 = rest[j], rest[j + 1]
        span = t[i1] - t[i0]
        if span <= 0:
            continue
        # i1 INCLUSIVE: the trapezoid between i0 and i1 half-weights both
        # endpoints, so a correction applied over [i0:i1] integrates to
        # c*(span - dt/2) rather than c*span and the interval does not quite
        # close. Half a sample, 0.17% here, and it changes no conclusion — but
        # a correction that does not do exactly what it claims makes a negative
        # result a statement about a fencepost instead of about the physics.
        world[i0:i1 + 1, :2] -= (vel[i1, :2] - vel[i0, :2]) / span
    _, position = integrate.integrate(world, log["dt"])
    reps = correct.detrend_set(position, result["bounds"], t) if result["bounds"] else []
    out = dict(result)
    out["reps"] = reps
    out["bar_position"] = position
    return out


def jump_correction(result: dict, width_s: float | None = None,
                    axes: tuple = (0, 1)) -> dict:
    """Remove the observable velocity error in a WINDOW at the impact. C29.

    The same observable as `impact_correction` — the velocity error read at the
    rest instants, no video — removed over a window of `width_s` starting at the
    floor impact instead of spread across the whole rest-to-rest interval.
    `width_s=None` uses the whole interval and reproduces `impact_correction`
    exactly, which is what makes this ONE experiment rather than two: sweeping
    the width interpolates between C28b's failure and a pure jump.

    Why a window at the impact is the physically motivated shape. B6 measured
    cumulative velocity as smooth and physical through the pull and the descent,
    then ringing violently for several hundred milliseconds AT the floor impact
    and settling short — the watch still moving on a compliant strap after the
    bar has stopped. So the error is not distributed over the rep; it is created
    in the few hundred ms after contact. Four corrections have now failed by
    being smooth across the rep (B7, B6, C19, C28b) and this is the first that
    is not.

    **A pure instantaneous jump is expected to do NOTHING, and that is a
    prediction rather than a caveat.** `segment.rep_bounds` ends each rep at an
    impact, so a velocity step exactly at the impact is a step exactly at a rep
    boundary: within a rep the velocity correction is then constant, the
    position correction is linear in t, and step 7's per-rep linear detrend
    removes a line. The correction would be annihilated by construction.

    What rescues it, if anything does, is that the rest instant sits ~0.85 s
    AFTER the impact — inside the NEXT rep. A correction ramping over that
    window is quadratic where it overlaps the following rep, and a linear
    detrend cannot remove a quadratic. So the sweep is really asking whether
    there is a width small enough to be localised and large enough to survive
    step 7, and the answer may be that no such width exists.

    `axes` is (0, 1) — horizontal only. B6's splice was vertical and could not
    move a horizontal metric at all ("a column-2 correction cannot move a metric
    that reads columns 0 and 1"), so the horizontal jump has never been tried.
    """
    from . import correct, segment
    log = result["log"]
    t = log["t"]
    impacts = list(result.get("impacts") or [])
    rest = segment.rest_instants(log, impacts)
    world = np.asarray(result["world_accel"], dtype=float).copy()
    vel = result["velocity"]
    ax = list(axes)

    applied = []
    for j in range(len(rest) - 1):
        i0, i1 = rest[j], rest[j + 1]
        dv = vel[i1] - vel[i0]                    # observable; true dv is zero
        if width_s is None:
            a, b = i0, i1
        else:
            inside = [k for k in impacts if i0 < k <= i1]
            if not inside:
                continue
            a = inside[-1]
            n = max(1, int(round(width_s / float(np.median(log["dt"])))))
            b = min(i1, a + n)
        span = t[b] - t[a]
        if span <= 0:
            continue
        world[a:b + 1, ax] -= (dv[ax] / span)
        applied.append((int(a), int(b), float(span)))

    _, position = integrate.integrate(world, log["dt"])
    reps = correct.detrend_set(position, result["bounds"], t) if result["bounds"] else []
    out = dict(result)
    out["reps"] = reps
    out["bar_position"] = position
    out["jump_windows"] = applied
    return out


def rest_knots(result: dict) -> list[int]:
    """Detrend boundaries that are NOT the impacts. C29.

    The C29 structural failure is that `segment.rep_bounds` ends each rep at a
    floor impact, so a correction localised at the impact is constant within
    every rep, linear in position, and removed exactly by the per-rep line. The
    correction and the detrend's null space coincide.

    These knots move the boundaries off the impacts and onto the moments the bar
    is actually at rest. That is a better place for them on its own terms, and
    the point is worth stating separately from the jump: **today's boundaries
    sit where the bar is still moving.** `segment.rest_instants` says so —
    against video the bar is travelling at 0.4-1.0 m/s at the impact and reaches
    a near-zero crossing ~150 ms later. A closure asserted at the impact is
    asserted at a moment the closure premise is false.

    The C3 holds bookend it. `phase == 0` and `phase == 2` are genuine still
    periods, so they are legitimate knots and they matter: without one at the
    front, the first pull of a set lies entirely before the first rest instant
    and would go undetrended. Captures with no `phase` column fall back to the
    first and last samples, which is weaker and is why this is deadlift-and-
    2026-07-30-onward in practice.
    """
    from . import calibrate, segment
    log = result["log"]
    n = len(log["t"])
    knots = list(segment.rest_instants(log, result.get("impacts")))
    hw = calibrate.hold_windows(log, 1.5)
    if hw.get("open") is not None:
        knots.append(int(np.median(hw["open"])))
    else:
        knots.append(0)
    if hw.get("close") is not None:
        knots.append(int(np.median(hw["close"])))
    else:
        knots.append(n - 1)
    return sorted(set(int(k) for k in knots if 0 <= k < n))


def detrend_knots(position: np.ndarray, knots, t: np.ndarray,
                  axes: tuple = (0, 1, 2)) -> np.ndarray:
    """Piecewise-linear detrend with boundaries at `knots`, globally continuous.

    Same premise as step 7 — the bar comes back to where it was — asserted at
    the knots instead of at the rep boundaries, and as ONE continuous
    piecewise-linear drift rather than as independent per-rep lines. A jump
    inside a knot interval then shows up as a kink, and a line cannot remove a
    kink, which is the whole point of C29's fix.

    Outside the first and last knot the drift is held flat rather than
    extrapolated: a slope fitted to the last interval and run past the end of
    the data is exactly how B7's anchor walked off, and there is nothing out
    there to constrain it.
    """
    p = np.asarray(position, dtype=float).copy()
    k = np.asarray(sorted({int(x) for x in knots}), dtype=int)
    if len(k) < 2:
        return p
    ref = p[k[0]]
    out = p.copy()
    for ax in axes:
        drift = np.interp(t, t[k], p[k, ax] - ref[ax])   # flat outside
        out[:, ax] = p[:, ax] - drift
    return out


def jump_then_knots(result: dict, width_s: float | None = 0.0,
                    axes: tuple = (0, 1)) -> dict:
    """C29's fix: correct at the impact, then detrend on boundaries that avoid it.

    `width_s=0.0` is the pure jump the structural result says is annihilated by
    the SHIPPING detrend. Under `detrend_knots` it should survive, because the
    impact is now interior to a knot interval. `width_s=None` spreads it over
    the whole rest-to-rest interval, i.e. C28b's shape, so the two can be
    compared under the same detrend.

    Pass `width_s=-1` to apply no correction at all and measure the knot
    detrend on its own — the control that says whether any gain is the jump or
    just the moved boundaries.
    """
    from . import segment
    log = result["log"]
    t = log["t"]
    world = np.asarray(result["world_accel"], dtype=float).copy()
    vel = result["velocity"]
    ax = list(axes)

    if width_s is not None and width_s >= 0.0:
        rest = segment.rest_instants(log, result.get("impacts"))
        impacts = list(result.get("impacts") or [])
        dtm = float(np.median(log["dt"]))
        for j in range(len(rest) - 1):
            i0, i1 = rest[j], rest[j + 1]
            dv = vel[i1] - vel[i0]
            inside = [k for k in impacts if i0 < k <= i1]
            if not inside:
                continue
            a = inside[-1]
            b = min(i1, a + max(1, int(round(width_s / dtm)))) if width_s > 0 else a + 1
            span = t[b] - t[a]
            if span <= 0:
                continue
            world[a:b + 1, ax] -= (dv[ax] / span)
    elif width_s is None:
        rest = segment.rest_instants(log, result.get("impacts"))
        for j in range(len(rest) - 1):
            i0, i1 = rest[j], rest[j + 1]
            span = t[i1] - t[i0]
            if span <= 0:
                continue
            world[i0:i1 + 1, ax] -= ((vel[i1] - vel[i0])[ax] / span)

    _, position = integrate.integrate(world, log["dt"])
    corrected = detrend_knots(position, rest_knots(result), t)
    reps = []
    for a, b in result["bounds"]:
        seg = corrected[a:b].copy()
        reps.append(seg - seg[0])
    out = dict(result)
    out["reps"] = reps
    out["bar_position"] = corrected
    return out


def rest_windows(result: dict) -> list[tuple]:
    """Rep windows running rest-to-rest instead of impact-to-impact. C29.

    The honest version of "move the detrend boundaries", after the continuous
    `detrend_knots` failed. **That failure was the informative one:** the
    shipping detrend fits INDEPENDENT lines, two free parameters per rep with no
    continuity between them, and a continuous piecewise-linear drift has about
    one per knot. Replacing the first with the second removed most of the
    detrend's absorbing power and cost 8.21 -> 17.00 cm with vertical ROM at
    70-138 against a 61 cm ceiling — the same shape of failure as B7's ablation.
    So the detrend is load-bearing for a reason nobody had named: it is not the
    closure that carries it, it is the per-rep INDEPENDENCE.

    These windows keep that independence exactly and move only where the
    boundaries fall. A rest-to-rest window is still a whole rep — descent,
    landing, pull instead of pull, descent, landing — and it puts the impact in
    the MIDDLE, where a correction localised there is a kink a line cannot
    remove, rather than at the edge where it is a slope a line removes exactly.
    """
    from . import segment
    rest = segment.rest_instants(result["log"], result.get("impacts"))
    return [(int(a), int(b) + 1) for a, b in zip(rest[:-1], rest[1:])]


def jump_rest_windows(result: dict, width_s: float | None = 0.0,
                      axes: tuple = (0, 1),
                      wrist_offset: np.ndarray | None = None) -> dict:
    """Correct at the impact, detrend per rest-to-rest window. C29's real fix.

    Identical machinery to the shipping step 7 — `correct.detrend_set`,
    independent endpoint lines, start-aligned — with the windows moved off the
    impacts. `width_s=0.0` is the pure jump, `-1` applies no correction and is
    the control, `None` reproduces C28b's whole-interval spread.

    **`bounds` is replaced, so `metrics.vs_truth` scores these windows on both
    sides.** The video is compared over the same windows as the reconstruction,
    which is what keeps it a fair comparison — but it is NOT the same quantity
    as the shipping number, because the reps being scored are different spans of
    the same lifting. Read the control row before the treatment rows.

    `wrist_offset` is step 6, and it has to be an argument rather than something
    the caller can do beforehand. This function re-integrates `world_accel` from
    scratch, so a `d` applied by `pipeline.run` upstream is in `bar_position`
    and is silently discarded here. C31b measured the arms with and without it;
    passing `None` reproduces C29 exactly.
    """
    from . import correct, segment
    log = result["log"]
    t = log["t"]
    world = np.asarray(result["world_accel"], dtype=float).copy()
    vel = result["velocity"]
    ax = list(axes)
    rest = segment.rest_instants(log, result.get("impacts"))
    impacts = list(result.get("impacts") or [])
    dtm = float(np.median(log["dt"]))

    for j in range(len(rest) - 1):
        i0, i1 = rest[j], rest[j + 1]
        dv = vel[i1] - vel[i0]
        if width_s is None:
            a, b = i0, i1
        elif width_s < 0:
            continue
        else:
            inside = [k for k in impacts if i0 < k <= i1]
            if not inside:
                continue
            a = inside[-1]
            b = min(i1, a + max(1, int(round(width_s / dtm)))) if width_s > 0 else a + 1
        span = t[b] - t[a]
        if span <= 0:
            continue
        world[a:b + 1, ax] -= (dv[ax] / span)

    _, position = integrate.integrate(world, log["dt"])
    if wrist_offset is not None:
        position = correct.apply_offset(position, result["quat"], wrist_offset)
    bounds = rest_windows(result)
    out = dict(result)
    out["bounds"] = bounds
    out["reps"] = correct.detrend_set(position, bounds, t) if bounds else []
    out["bar_position"] = position
    return out


# ------------------------------------------------------------------- D1 -----
#
# D1 (2026-08-07) asked where the deadlift's invented fore-aft is GENERATED,
# and the four functions below are the measurement. The answer changed the
# question: it is not generated anywhere in particular WITHIN a rep, and it is
# not generated at the floor impact. It is one number per rep — a constant
# horizontal acceleration — and that number grows through the set.


def rep_attribution(result: dict, masks: dict, axis, flipped: bool = False):
    """Attribute each detrended rep path to disjoint sets of samples. EXACT.

    Step 7's output is a LINEAR functional of the world acceleration: two
    cumulative trapezoids, an endpoint line removed, a start alignment. Step 6's
    lever `-R(t).d` is an additive term that does not involve `a` at all. So for
    any partition of the samples into disjoint masks,

        rep_k  =  sum_bins detrend_k(integrate2(a * mask_bin))  +  detrend_k(-R.d)

    holds identically, and `attribution_error` below checks it to ~1e-13 m. That
    is what makes this an attribution rather than an ablation: nothing is
    re-integrated with a hole in it, no bin interacts with any other, and the
    parts provably sum to the whole.

    **A fact that fell out of it and is worth keeping.** Samples BEFORE a rep
    contribute `p(t0) + v(t0)*(t - t0)` inside it — exactly a line — so the
    endpoint detrend removes them completely, and samples after it cannot reach
    it at all. Measured: a bin holding every sample outside the rep windows
    contributes 4e-13 cm. **A detrended rep depends only on the acceleration
    inside its own window, plus the lever.** All the drift this project worries
    about is therefore already gone by the time step 7 has run, and what is left
    is generated inside 3 seconds.

    Returns {bin_name: [per-rep (M,3) partial paths]} with "lever" (when step 6
    ran) and "FULL" added. `axis`/`flipped` are `vs_truth`'s, so the caller can
    project a partial path onto the same display axis the score uses.
    """
    log = result["log"]
    t, dt = log["t"], log["dt"]
    world = np.asarray(result["world_accel"], dtype=float)
    bounds = result["bounds"]

    out = {}
    for name, m in masks.items():
        masked = np.where(np.asarray(m, bool)[:, None], world, 0.0)
        _, p = integrate.integrate(masked, dt)
        out[name] = correct.detrend_set(p, bounds, t)

    d = result.get("wrist_offset")
    if d is not None:
        lever = -Rotation.from_quat(result["quat"], scalar_first=True).apply(
            np.asarray(d, dtype=float))
        out["lever"] = correct.detrend_set(lever, bounds, t)

    out["FULL"] = correct.detrend_set(result["bar_position"], bounds, t)
    return out


def attribution_error(parts: dict) -> float:
    """Max |sum of the bins - the whole| over every rep, in metres.

    The self-check for `rep_attribution`. If this is not ~1e-13 the partition
    was not disjoint or not covering, and no number derived from it is quotable.
    """
    keys = [k for k in parts if k != "FULL"]
    worst = 0.0
    for k in range(len(parts["FULL"])):
        total = sum(parts[name][k] for name in keys)
        worst = max(worst, float(np.abs(total - parts["FULL"][k]).max()))
    return worst


def impact_mask(result: dict, half_s: float = 0.10) -> np.ndarray:
    """Samples within `half_s` of a floor impact. C6's window is 0.10."""
    t = result["log"]["t"]
    m = np.zeros(len(t), dtype=bool)
    for i in result.get("impacts") or []:
        m |= np.abs(t - t[i]) <= half_s
    return m


def parabola_fit(curve: np.ndarray, duration: float) -> dict:
    """Fit `c * tau(tau - T)/2` to one rep's along-axis path. D1.

    That basis is the position response to a CONSTANT acceleration `c` after
    step 7's endpoint line has been removed, and it is zero at both endpoints —
    so `c` is exactly "what constant horizontal acceleration would draw this
    path", and removing it preserves the rep's closure.

    Returns `c` in m/s^2, `r2` (the fraction of the path's variance it
    explains), `excursion_m`, and `tilt_deg` = asin(|c|/g): the attitude error
    that would leak this much gravity into the horizontal.

    **What it measures, on the six deadlifts (D1, 2026-08-07).** The
    reconstruction's per-rep fore-aft path IS this parabola: median r2 of
    0.76, 0.95, 0.95, 0.97, 0.98 and 1.00. So the entire fore-aft output of the
    deadlift pipeline is one number per rep, and that number is 0.005-0.16
    m/s^2 — an effective tilt of 0.03-0.94 degrees. A third of a metre of
    invented travel is a fraction of a degree of attitude, amplified by T^2.

    The same fit against the VIDEO's own path is what convicts it. Pooled over
    30 deadlift reps the reconstruction's `c` is **5.0x** the bar's in rms and
    **uncorrelated** with it, r = +0.18. Over 24 bench reps it is **0.7x** and
    correlated, r = 0.49-0.97 within each capture. That is C30b's bench/deadlift
    split measured in the position domain instead of the acceleration one.
    """
    y = np.asarray(curve, dtype=float)
    tau = np.linspace(0.0, float(duration), len(y))
    T = tau[-1]
    basis = tau * (tau - T) / 2.0
    den = float(basis @ basis)
    c = float(basis @ y) / den if den > 0 else 0.0
    resid = y - c * basis
    var = float(y @ y)
    return {"c": c,
            "r2": 1.0 - float(resid @ resid) / var if var > 0 else 0.0,
            "excursion_m": float(np.ptp(y)),
            "tilt_deg": float(np.degrees(np.arcsin(min(1.0, abs(c) / 9.80665))))}


def parabola_detrend(reps: list, bounds: list, t: np.ndarray,
                     axes: tuple = (0, 1)) -> list:
    """Remove each rep's own best-fit parabola. MEASURED AND REJECTED. D1.

    An ADDITION to step 7, not a replacement: the basis `tau(tau - T)/2` is zero
    at both endpoints, so the closure step 7 asserts is untouched and the only
    thing removed is the constant-acceleration component. One coefficient per
    rep per axis, fitted to the rep's OWN path — no video, no anchor, nothing
    external. Horizontal only, so the vertical cannot regress.

    It is the correction D1's diagnosis implies, and on deadlift it works:

        capture            h_rms          beats_null     excursion   video
        deadlift_160x6_1   6.65 -> 1.99   0.25 -> 0.84   13.7 -> 5.1   6.0
        deadlift_160x6_2   4.39 -> 1.49   0.35 -> 1.03    8.1 -> 4.6   4.1
        deadlift_185x3    10.61 -> 2.08   0.15 -> 0.76   16.3 -> 5.0   5.4
        deadlift_155x6_1   4.57 -> 3.16   0.78 -> 1.13    7.9 -> 8.2  12.8
        deadlift_155x6_2   8.99 -> 2.84   0.36 -> 1.14   10.5 -> 7.4   9.4
        deadlift_180x3    15.65 -> 1.69   0.13 -> 1.16   21.5 -> 8.3   8.4

    Six of six improve on horizontal rms and six of six move toward the video's
    excursion. **It is still REJECTED, on the bench regression, and the reason
    is the finding rather than a tuning failure.**

        bench_95x2         0.80 -> 4.27   5.39 -> 1.01
        bench_92.5x4_2     1.18 -> 2.85   2.32 -> 0.96
        bench_92.5x4_1     1.23 -> 2.17   1.78 -> 1.02
        bench_92.5x4_3     1.92 -> 2.30   1.19 -> 0.99
        bench_spoto_95x5_1 3.54 -> 2.95   0.88 -> 1.05
        bench_spoto_95x5_2 4.45 -> 3.07   0.72 -> 1.05

    Four of six benches get worse and two fall from beating the null to losing
    to it. Look at what `beats_null` does across all twelve captures: it enters
    spanning 0.13 to 5.39 and leaves spanning 0.76 to 1.16. **This correction
    converts every capture into approximately the flat-line null.** It does not
    add information; it removes the channel. On deadlift that is a gain because
    the channel was 3-7x worse than nothing. On bench it is a loss because the
    channel was up to 5x better than nothing.

    So the honest reading is not "a fix that needs gating by lift". It is that
    **the deadlift's horizontal position output contains one parabola and
    essentially nothing else** — remove it and you are at the null, and no
    estimator can do better than the null with what is left. That is the
    position-domain counterpart of C30/C31's acceleration-domain dispute, and
    it is why five localised corrections (B7, B6, C19, C28b, C29) all failed:
    they were rearranging a signal that carries one bit.

    It also explains C28's negative result rather than contradicting it. C28
    fitted ONE constant per capture and found the family capped at the null with
    nothing transferring. The constant is real — it is right here — but it is
    per REP and it grows 2.2-4.2x across a set, so no per-capture constant could
    ever have fitted it.
    """
    out = []
    for rep, (a, b) in zip(reps, bounds):
        tau = np.asarray(t[a:b], dtype=float) - t[a]
        basis = tau * (tau - tau[-1]) / 2.0
        den = float(basis @ basis)
        p = np.asarray(rep, dtype=float).copy()
        if den > 0:
            for ax in axes:
                p[:, ax] -= (float(basis @ p[:, ax]) / den) * basis
        out.append(p - p[0])
    return out
