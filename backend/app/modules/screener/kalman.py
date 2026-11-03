"""
Kalman-filter dynamic hedge ratio for pairs trading.

The daily screener fits a single static (alpha, beta) over the whole lookback.
Applied to live intraday prices that hedge ratio drifts out of date - the spread
looks "extreme" only because beta is stale, not because of a real divergence.

This filter estimates a *time-varying* hedge ratio online. The state
``x = [beta, alpha]`` follows a random walk and is updated on every new
observation, so beta tracks the current relationship instead of being frozen at
the daily fit. The Kalman innovation (one-step forecast error) is the natural
spread, and ``innovation / sqrt(innovation_variance)`` is a self-normalizing
z-score - no separate rolling mean/std needed.

Model:
    state:        x_t   = x_{t-1} + w_t,        w_t ~ N(0, Q)
    observation:  a_t   = H_t x_t + v_t,        H_t = [b_t, 1],  v_t ~ N(0, R)

where a_t = price of asset A, b_t = price of asset B.
"""
from typing import Optional

import numpy as np
import pandas as pd


class KalmanHedge:
    """Online dynamic hedge ratio estimator.

    Args:
        delta: Controls the state transition covariance
            ``Q = delta / (1 - delta) * I`` (normalised units). Larger delta lets beta move faster
            (more responsive, noisier); smaller delta is smoother/slower.
        r: Observation noise variance R, relative to price level (the filter runs on
            prices normalised by their first value). Larger r trusts the model over
            each new price more (smoother spread). None (default) estimates R from the
            OLS residual variance of the first ``warmup`` normalised observations.
    """

    def __init__(self, delta: float = 1e-4, r: Optional[float] = None):
        self.delta = delta
        self.r = r

    warmup = 100

    def _estimate_r(self, a: np.ndarray, b: np.ndarray) -> float:
        m = min(len(a), self.warmup)
        if m < 3:
            return 1e-6
        slope, intercept = np.polyfit(b[:m], a[:m], 1)
        resid = a[:m] - (slope * b[:m] + intercept)
        return max(float(np.var(resid)), 1e-10)

    def run(self, price_a: pd.Series, price_b: pd.Series) -> pd.DataFrame:
        """Run the filter over aligned price series.

        Returns a DataFrame indexed like the inputs with columns:
            beta, alpha   - filtered hedge ratio / intercept at each step
            spread        - Kalman innovation (one-step forecast error)
            zscore        - innovation / sqrt(innovation variance)
        Returns an empty DataFrame if there is not enough aligned data.
        """
        aligned = pd.DataFrame({'a': price_a, 'b': price_b}).dropna()
        n = len(aligned)
        if n < 2:
            return pd.DataFrame(columns=['beta', 'alpha', 'spread', 'zscore'])

        a = aligned['a'].to_numpy(dtype=float)
        b = aligned['b'].to_numpy(dtype=float)

        # Scale invariance (R-03): R and Q are absolute, so run the filter on prices
        # normalised by their first value (both ~1) and map beta/alpha/spread back to
        # price units afterwards. z-scores are unitless and unaffected by the mapping.
        a0 = a[0] if a[0] != 0 else 1.0
        b0 = b[0] if b[0] != 0 else 1.0
        a = a / a0
        b = b / b0

        # State x = [beta, alpha]; covariance P.
        x = np.zeros(2)
        # Seed beta with a rough ratio so the filter converges faster than from 0.
        if b[0] != 0:
            x[0] = a[0] / b[0]
        P = np.eye(2) * 1.0
        R = self.r if self.r is not None else self._estimate_r(a, b)
        # Q is absolute in normalised units, so it is price-level independent. (Tying Q to R
        # calibrates z dispersion better but stops beta tracking drift - tested, rejected.)
        Q = (self.delta / (1.0 - self.delta)) * np.eye(2)

        betas = np.empty(n)
        alphas = np.empty(n)
        spreads = np.empty(n)
        zscores = np.empty(n)

        for t in range(n):
            H = np.array([b[t], 1.0])

            # Predict (state unchanged for a random walk; only covariance grows).
            if t > 0:
                P = P + Q

            y_hat = H @ x
            e = a[t] - y_hat                 # innovation == spread
            S = float(H @ P @ H + R)         # innovation variance
            if S <= 0 or not np.isfinite(S):
                S = R

            K = (P @ H) / S                  # Kalman gain
            x = x + K * e
            P = P - np.outer(K, H) @ P

            betas[t] = x[0]
            alphas[t] = x[1]
            spreads[t] = e
            zscores[t] = e / np.sqrt(S)

        # Back to price units: a = (a0*beta_n/b0) * b + a0*alpha_n, spread scales with a0.
        return pd.DataFrame(
            {'beta': betas * a0 / b0, 'alpha': alphas * a0, 'spread': spreads * a0,
             'zscore': zscores},
            index=aligned.index,
        )
