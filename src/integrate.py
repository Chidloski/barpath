"""
Step 4 — acceleration to velocity to position.

This module was reserved for the owner until 2026-07-28. It is not any more —
every file is collaborative now. What the lockout was protecting survived it:
this is where the physics lives, so a change here explains the mechanism
alongside the diff and names what would falsify it. See CLAUDE.md, "Learning
contract".

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

That is an algebraic identity — integrating a known acceleration — and it is
the kind of claim synth.py can still settle, because it holds regardless of how
lifting behaves. Do not read it as evidence that the pipeline works. The
quantities this module is fed on a real capture are wrong by two orders of
magnitude and a correct integrator propagates them faithfully.
"""

from __future__ import annotations

import numpy as np
from scipy.integrate import cumulative_trapezoid


def integrate(accel_world: np.ndarray, dt: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    times = np.cumsum(dt)
    velocity = cumulative_trapezoid(accel_world, times, axis=0, initial=0)
    displacement = cumulative_trapezoid(velocity, times, axis=0, initial=0)

    return velocity, displacement
