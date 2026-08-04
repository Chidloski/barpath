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
            bias_frame: str = "world") -> dict:
    """A `pipeline.run`-shaped dict with the error model applied.

    Steps 4, 6 and 7 are re-run. Step 5 is NOT: `bounds` is carried over from
    the unperturbed run so the optimiser cannot improve its score by re-cutting
    the reps. See the module docstring.

    `world_bias` is the shipping `calibrate.accel_bias` subtraction, and it is
    a switch rather than a constant because C28 found it is a NEGATIVE term.
    It is not one of the fitted parameters — it has none — so it belongs here
    as an ablation and not in the ladder's parameter vector.
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

    if "lever" in p:
        position = correct.apply_offset(position, base["quat"], p["lever"])

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
              world_bias: bool = True, bias_frame: str = "world") -> float:
    """Median per-rep horizontal rms in cm. Inf where the model is unusable.

    Horizontal ALONE, deliberately. It is the axis with the spec that matters,
    the axis the display magnifies 4x, and the one the reconstruction fails on;
    including vertical would let a model trade the axis under test against one
    already close and report a better total for a worse answer.
    """
    try:
        res = rebuild(base, unpack(theta, terms), world_bias, bias_frame)
        if not res["reps"]:
            return np.inf
        m = metrics.vs_truth(res, video)
        v = float(m["pipeline_h_rms"])
        return v if np.isfinite(v) else np.inf
    except Exception:
        return np.inf


def fit(base: dict, video: dict, terms: tuple, restarts: int = 3,
        seed: int = 0, world_bias: bool = True,
        bias_frame: str = "world") -> dict:
    """Fit one model to one capture. Nelder-Mead from several starts.

    Derivative-free on purpose: the objective runs a double integration, a
    per-rep detrend and a PCA, and the detrend's rep-closure makes it only
    piecewise smooth in the parameters. A gradient method reports convergence
    on that surface without having found anything.
    """
    if not terms:
        m = metrics.vs_truth(rebuild(base, {}, world_bias, bias_frame), video)
        return {"terms": terms, "theta": np.zeros(0),
                "h_rms": float(m["pipeline_h_rms"]),
                "null": float(m["null_h_rms"]),
                "beats_null": float(m["beats_null"])}

    n = n_params(terms)
    rng = np.random.default_rng(seed)
    scales = np.concatenate([np.full(TERMS[t], PLAUSIBLE[t][0]) for t in terms])

    best = None
    for k in range(restarts):
        x0 = np.zeros(n) if k == 0 else rng.normal(0.0, 0.5, n) * scales
        r = minimize(objective, x0,
                     args=(terms, base, video, world_bias, bias_frame),
                     method="Nelder-Mead",
                     options={"maxiter": 400 * n, "xatol": 1e-6,
                              "fatol": 1e-4, "adaptive": True})
        if best is None or r.fun < best.fun:
            best = r

    res = rebuild(base, unpack(best.x, terms), world_bias, bias_frame)
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
