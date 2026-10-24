"""
Hurst exponent calculation for mean reversion detection
"""
import numpy as np
import pandas as pd
from typing import Optional


class HurstCalculator:
    """Calculates Hurst exponent for spread series"""
    
    @staticmethod
    def generalized_hurst_exponent(
        series: pd.Series,
        max_lags: int = 50,
        q: int = 1
    ) -> Optional[float]:
        """
        Calculate generalized Hurst exponent (GHE)
        
        Args:
            series: Time series (typically spread)
            max_lags: Maximum lag for calculation
            q: Moment order (q=1 for standard Hurst)
            
        Returns:
            Hurst exponent (H < 0.5 = mean reverting, H > 0.5 = trending)
        """
        if len(series) < max_lags * 2:
            return None
        
        # Remove NaN
        series_clean = series.dropna().values
        
        if len(series_clean) < max_lags * 2:
            return None
        
        # Generalized Hurst exponent (Di Matteo): K_q(tau) = <|X(t+tau) - X(t)|^q>
        # scales as tau^(q*H). Computed on the series *levels* (the spread),
        # not on its increments - using increments of increments biases H to ~0.
        n = len(series_clean)
        tau_values = np.arange(1, min(max_lags, n // 2))
        k_values = []

        for tau in tau_values:
            diff_tau = series_clean[tau:] - series_clean[:-tau]
            k = np.mean(np.abs(diff_tau) ** q)
            if k <= 0:
                break
            k_values.append(k)

        if len(k_values) < 5:  # Need minimum points for regression
            return None
        
        # Log-log regression: log(K) = q*H*log(tau) + C
        log_tau = np.log(tau_values[:len(k_values)])
        log_k = np.log(np.array(k_values) + 1e-10)  # Add small value to avoid log(0)
        
        # Linear regression
        try:
            slope, _ = np.polyfit(log_tau, log_k, 1)
            h_exponent = slope / q
            return h_exponent
        except (np.linalg.LinAlgError, ValueError):
            return None

