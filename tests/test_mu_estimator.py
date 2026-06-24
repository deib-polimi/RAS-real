"""Regression test for the windowed Operational Utilization Law estimator.

Smoke A (23 giu 2026) showed c_phys oscillating 1↔8 because μ̂ = λ/U computed
tick-by-tick (instantaneous, noisy U from docker stats) jumped 1.1↔24.3.
The windowed estimator μ̂ = ΣX/ΣU must be stable under U-noise and track the
true per-core service rate.
"""
import statistics

from controllers.mmc_pi_controller import MuEstimator

TRUE_MU = 13.0          # req/s/core (measured local calibration)
U_TRUE = 3.0            # ~3 busy cores
X_TRUE = TRUE_MU * U_TRUE   # consistent throughput (req/s)
# Heavy multiplicative jitter on the *instantaneous* U reading (docker glitches).
JITTER = [0.5, 1.0, 1.5, 1.0, 2.0, 0.3]


def test_windowed_mu_stable_and_accurate_under_U_noise():
    est = MuEstimator(window_s=120.0, min_samples=10)
    windowed, instantaneous = [], []
    for i in range(300):
        u_noisy = U_TRUE * JITTER[i % len(JITTER)]
        est.update(float(i), X_TRUE, u_noisy)
        m = est.estimate()
        if m is not None:
            windowed.append(m)
        instantaneous.append(X_TRUE / u_noisy)

    final = windowed[-1]
    # (a) converges near the true μ (windowing removes the multiplicative bias)
    assert abs(final - TRUE_MU) / TRUE_MU < 0.20, f"μ̂={final:.2f} off from {TRUE_MU}"
    # (b) is *stable*: tail std well under 1 core-rate unit (~8% of μ)
    assert statistics.pstdev(windowed[-60:]) < 1.0, "windowed μ̂ still noisy"
    # (c) and far more stable than the naive instantaneous λ/U it replaces
    assert (statistics.pstdev(windowed[-60:])
            < statistics.pstdev(instantaneous[-60:]) / 3.0)


def test_returns_none_until_window_is_warm():
    est = MuEstimator(window_s=120.0, min_samples=10)
    for i in range(5):
        est.update(float(i), X_TRUE, U_TRUE)
    assert est.estimate() is None          # < min_samples
    for i in range(5, 15):
        est.update(float(i), X_TRUE, U_TRUE)
    assert est.estimate() is not None      # now warm


def test_ignores_invalid_samples():
    est = MuEstimator(window_s=120.0, min_samples=1)
    est.update(0.0, X_TRUE, 0.0)    # U=0 → ignored
    est.update(1.0, X_TRUE, None)   # U None → ignored
    assert est.estimate() is None
