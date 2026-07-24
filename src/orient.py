"""
Steps 2-3 — attitude correction and rotation into the world frame.

=========================================================================
RESERVED MODULE. The owner writes this. Claude Code reviews and explains,
but does not implement. See CLAUDE.md.
=========================================================================

Background
----------
The accelerometer's axes are glued to the watch case, so they tumble as the
wrist moves. Attitude is the watch's orientation relative to a fixed frame
with z pointing up. Formally it is a rotation matrix R — orthogonal,
determinant +1 — taking a vector in watch coordinates to world coordinates.
Core Motion stores it as a quaternion; treat it as R.

This is the crux of the whole project. An accelerometer does not measure
acceleration: it is a mass on springs measuring how hard the springs push,
which is specific force, a - g. To recover motion you must subtract gravity,
and you only know which way gravity points via attitude. So attitude error
does not add noise — it injects a fraction of 9.81 m/s^2 straight into the
signal. One degree gives 0.17 m/s^2, which over a 2 s rep integrates to
about 34 cm.

Note the asymmetry, which shapes everything downstream. A tilt error theta
leaks g*sin(theta) into the horizontal axes but only g*(1-cos(theta)) into
vertical — first order against second order. At 2 degrees that is a factor
of about 57. Vertical is structurally forgiving; horizontal is not.


What to implement
-----------------

correct_attitude(log, bias) -> (N, 4) quaternions, w x y z
    Apple's filter integrates the raw gyro, so a constant bias b_g produces
    an attitude error that grows as b_g * t. Undo it: compose each reported
    quaternion with the inverse of the rotation accumulated by the bias
    since the start of the record.

    Watch the frame convention. The bias is in body coordinates, so the
    correction is a right-multiplication, not a left one. Getting this
    backwards produces a result that looks almost right and is wrong in a
    way that only shows up on long sets — check it against synth.quat_true,
    which is exactly what that field is for.

to_world(accel_body, quat) -> (N, 3) world-frame acceleration, m/s^2
    Rotate each sample. io.load_log has already converted from Core Motion's
    units of g to m/s^2; do not convert again.

    The resulting frame has z vertical and x, y horizontal but rotated by an
    unknown angle — the watch has no idea which way the lifter is facing.
    project.py resolves that later.


Suggested check
---------------
Generate a synthetic set with zero noise and zero bias. to_world should
return synth.acc_true to machine precision. It did when this scaffold was
built, so if it does not, the bug is yours and not the generator's.
"""

from __future__ import annotations

import numpy as np
from scipy.spatial.transform import Rotation


def correct_attitude(log: dict, bias: np.ndarray) -> np.ndarray:
    R_log = Rotation.from_quat(log["quat"], scalar_first=True)
    time_log = log["t"] - log["t"][0] # first log needs no bias applied as movement is relative to the first log

    bias_with_time = np.outer(time_log, bias)

    # reverse the effect of the gyro bias to get the true attitude of the watch
    R_true = R_log * Rotation.from_rotvec(bias_with_time).inv()

    return R_true.as_quat(scalar_first=True)


def to_world(accel_body: np.ndarray, reported_quat: np.ndarray, corrected_quat: np.ndarray) -> np.ndarray:
    R = Rotation.from_quat(corrected_quat, scalar_first=True)
    G = np.array([0, 0, -9.80665])

    accel_with_g = accel_body - Rotation.from_quat(reported_quat, scalar_first=True).inv().apply(G)

    return R.apply(accel_with_g) + G
