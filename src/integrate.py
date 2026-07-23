"""
Step 4 — acceleration to velocity to position.

=========================================================================
RESERVED MODULE. The owner writes this. Claude Code reviews and explains,
but does not implement. See CLAUDE.md.
=========================================================================

Background
----------
Why drift dominates and noise does not. Any constant error b in acceleration
becomes (1/2) b t^2 in position. Sensor noise, by contrast, is almost
irrelevant: double integration acts as a 1/n^2 low-pass filter, so 50 Hz
noise is suppressed roughly 10^4 times relative to 0.5 Hz bar motion. Over a
2 s rep, realistic noise contributes something like 1.6 mm of position
error. This is why every correction in this pipeline targets bias, and why
smoothing the signal would be solving a problem you do not have.

Gyro bias is worse than accelerometer bias over a set, and the reason is
that it sits one integration further out. Accel bias reaches position in two
integrations, giving t^2. Gyro bias must first be integrated to become an
attitude error, which then leaks gravity into acceleration, which is then
integrated twice — three integrations, giving t^3. The crossover is around
7 seconds, so within a rep the quadratic dominates and across a set the
cubic does.


What to implement
-----------------

integrate(accel_world, dt) -> (velocity, position)
    Cumulative trapezoidal, both stages, starting from rest.

    Use the per-sample dt array from io.load_log rather than a constant.
    The watch does not always honour the requested rate, and baking in a
    fixed interval introduces a scale error you cannot see and cannot fix.

    Trapezoidal is not fussiness. On the noise-free synthetic set,
    rectangular integration leaves about 9 mm of vertical error while
    trapezoidal leaves 0.24 mm — a factor of 40, for one extra term.


Suggested check
---------------
Zero-noise, zero-bias synthetic set: position should match synth.pos_true to
well under a millimetre. If it does not, the fault is in the integration
scheme, not the data.

Then inject 1 deg/s of gyro bias with the correction in step 2 switched off
and confirm the horizontal blow-up of roughly 20-25 cm. Seeing that failure
deliberately is worth more than reading about it.
"""

from __future__ import annotations

import numpy as np


def integrate(accel_world: np.ndarray, dt: np.ndarray):
    raise NotImplementedError("Reserved module — see docstring.")
