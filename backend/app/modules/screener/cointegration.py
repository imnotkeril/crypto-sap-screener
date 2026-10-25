"""
Cointegration testing using Engle-Granger method
"""
import numpy as np
import pandas as pd
from statsmodels.tsa.stattools import coint
from statsmodels.regression.linear_model import OLS
from typing import Tuple, Optional


class CointegrationTester:
    """Tests for cointegration between two price series"""
    
    @staticmethod
    def engle_granger_test(
        price_a: pd.Series,
        price_b: pd.Series
    ) -> Tuple[bool, float, float, float, float]:
        """
        Perform Engle-Granger cointegration test.

        Uses ``statsmodels.tsa.stattools.coint`` for the cointegration p-value
        rather than running ``adfuller`` on the OLS residuals directly. The
        residuals are *estimated* (not observed), so a plain ADF test uses the
        wrong (too-lenient) Dickey-Fuller critical values and overstates
        cointegration. ``coint`` applies the proper Engle-Granger /
        MacKinnon-Phillips-Ouliaris critical values. The OLS regression is still
        run separately to recover the hedge ratio (beta), intercept (alpha) and
        spread std used downstream.

        Args:
            price_a: Price series for asset A
            price_b: Price series for asset B

        Returns:
            Tuple of (is_cointegrated, beta, eg_statistic, eg_pvalue, spread_std)
            is_cointegrated: True if p-value < 0.10
            beta: Hedge ratio from OLS regression
            eg_statistic: Engle-Granger test statistic (from ``coint``)
            eg_pvalue: Engle-Granger cointegration p-value (proper crit. values)
            spread_std: Normalized standard deviation of spread residuals (% of price A)
        """
        # Align series (remove NaN values)
        aligned = pd.DataFrame({'a': price_a, 'b': price_b}).dropna()

        if len(aligned) < 50:  # Need minimum data points
            return False, 0.0, 0.0, 1.0, 0.0

        price_a_aligned = aligned['a']
        price_b_aligned = aligned['b']

        # Step 1: OLS regression: Price_A = alpha + beta * Price_B + epsilon
        X = price_b_aligned.values.reshape(-1, 1)
        y = price_a_aligned.values

        # Add constant term
        X_with_const = np.column_stack([np.ones(len(X)), X])

        try:
            model = OLS(y, X_with_const).fit()
            alpha = model.params[0]
            beta = model.params[1]

            # Step 2: Calculate residuals (spread)
            residuals = price_a_aligned - (alpha + beta * price_b_aligned)

            # Normalize spread_std to avoid issues with different price scales
            # Use percentage of average price A to make it comparable across pairs
            avg_price_a = price_a_aligned.mean()
            spread_std_absolute = residuals.std()

            # Normalized spread_std as percentage (more comparable across different price levels)
            if avg_price_a > 0:
                spread_std = (spread_std_absolute / avg_price_a) * 100
            else:
                spread_std = spread_std_absolute

            # Step 3: Engle-Granger cointegration test with correct critical values.
            # coint() regresses the first arg on the second and tests the residual
            # for a unit root using Engle-Granger critical values. The test is
            # direction-dependent (regressing a~b vs b~a gives different
            # statistics because the residual is normalized differently), so we
            # run both and take the stronger (lower p-value) as the decision -
            # this avoids rejecting a genuinely cointegrated pair just because
            # the arbitrary a~b orientation happened to be the weaker one. The
            # hedge ratio (beta/alpha) stays in the canonical a~b form used
            # downstream for the spread.
            eg_stat_ab, eg_p_ab, _ = coint(
                price_a_aligned, price_b_aligned, trend='c', autolag='AIC'
            )
            eg_stat_ba, eg_p_ba, _ = coint(
                price_b_aligned, price_a_aligned, trend='c', autolag='AIC'
            )
            if eg_p_ba < eg_p_ab:
                eg_statistic, eg_pvalue = eg_stat_ba, eg_p_ba
            else:
                eg_statistic, eg_pvalue = eg_stat_ab, eg_p_ab
            # Taking the better of two directional tests is two looks at the
            # data: Bonferroni-adjust so the reported p-value stays honest.
            eg_pvalue = min(1.0, 2.0 * eg_pvalue)

            # Cointegrated if p-value < 0.10
            is_cointegrated = eg_pvalue < 0.10

            return is_cointegrated, beta, float(eg_statistic), float(eg_pvalue), spread_std

        except Exception as e:
            print(f"Error in cointegration test: {e}")
            return False, 0.0, 0.0, 1.0, 0.0

    @staticmethod
    def half_life(spread: pd.Series) -> Optional[float]:
        """
        Estimate the half-life of mean reversion of a spread series.

        Fits the discrete Ornstein-Uhlenbeck / AR(1) model
        ``Δspread_t = θ * spread_{t-1} + c + ε`` by OLS. The half-life
        (number of bars for a deviation to decay by half) is ``-ln(2) / θ``.

        Returns the half-life in *bars* (same unit as the input frequency), or
        None if the spread is not mean-reverting (θ >= 0) or there is not
        enough data. Use it to (a) reject pairs that revert too fast (noise /
        unstable) or too slow (no trades), and (b) size the rolling z-score
        window.
        """
        s = spread.dropna()
        if len(s) < 20:
            return None

        lagged = s.shift(1)
        delta = s - lagged
        df = pd.concat([delta, lagged], axis=1).dropna()
        df.columns = ['delta', 'lag']
        if len(df) < 10:
            return None

        try:
            X = np.column_stack([np.ones(len(df)), df['lag'].values])
            model = OLS(df['delta'].values, X).fit()
            theta = model.params[1]
        except Exception:
            return None

        if theta >= 0:
            # Not mean-reverting (random walk or trending)
            return None

        hl = -np.log(2) / theta
        if not np.isfinite(hl) or hl <= 0:
            return None
        return float(hl)

    @staticmethod
    def rolling_zscore(spread: pd.Series, window: int) -> pd.Series:
        """
        Rolling z-score of the spread.

        Unlike the static z-score (which normalizes against the mean/std of the
        *entire* sample and therefore peeks at the whole history), this uses a
        trailing window so the current z-score only reflects information
        available up to that point. The window is typically set to the
        mean-reversion half-life.
        """
        s = spread.dropna()
        if len(s) == 0:
            return pd.Series(dtype=float)

        w = max(2, int(window))
        min_periods = max(2, w // 2)
        mean = s.rolling(w, min_periods=min_periods).mean()
        std = s.rolling(w, min_periods=min_periods).std()
        z = (s - mean) / std.replace(0, np.nan)
        return z.fillna(0.0)
    
    @staticmethod
    def calculate_spread(
        price_a: pd.Series,
        price_b: pd.Series,
        beta: float,
        alpha: float = 0.0
    ) -> pd.Series:
        """
        Calculate spread between two price series
        
        Args:
            price_a: Price series for asset A
            price_b: Price series for asset B
            beta: Hedge ratio
            alpha: Constant term from regression (default 0)
        
        Returns:
            Spread series: Price_A - (alpha + beta * Price_B)
        """
        aligned = pd.DataFrame({'a': price_a, 'b': price_b}).dropna()
        spread = aligned['a'] - (alpha + beta * aligned['b'])
        return spread
    
    @staticmethod
    def calculate_zscore(spread: pd.Series) -> pd.Series:
        """
        Calculate z-score of spread (normalized spread)
        
        Args:
            spread: Spread series
        
        Returns:
            Z-score series: (spread - mean) / std
        """
        spread_clean = spread.dropna()
        if len(spread_clean) == 0:
            return pd.Series(dtype=float)
        
        mean_spread = spread_clean.mean()
        std_spread = spread_clean.std()
        
        if std_spread == 0:
            return pd.Series(0, index=spread_clean.index)
        
        zscore = (spread_clean - mean_spread) / std_spread
        return zscore

