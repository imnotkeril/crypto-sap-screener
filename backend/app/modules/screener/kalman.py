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
import numpy as np
import pandas as pd
from typing import Optional


class KalmanHedge:
    """Online dynamic hedge ratio estimator.

    Args:
        delta: Controls the state transition covariance
            ``Q = delta / (1 - delta) * I``. Larger delta lets beta move faster
            (more responsive, noisier); smaller delta is smoother/slower.
        r: Observation noise variance R. Larger r trusts the model over each new
            price more (smoother spread).
    """

    def __init__(self, delta: float = 1e-4, r: float = 1e-3):
        self.delta = delta
        self.r = r

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

        # State x = [beta, alpha]; covariance P.
        x = np.zeros(2)
        # Seed beta with a rough ratio so the filter converges faster than from 0.
        if b[0] != 0:
            x[0] = a[0] / b[0]
        P = np.eye(2) * 1.0
        Q = (self.delta / (1.0 - self.delta)) * np.eye(2)
        R = self.r

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

        return pd.DataFrame(
            {'beta': betas, 'alpha': alphas, 'spread': spreads, 'zscore': zscores},
            index=aligned.index,
        )
