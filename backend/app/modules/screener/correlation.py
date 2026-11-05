"""
Correlation analysis for pairs
"""
import pandas as pd
from typing import Tuple, Optional
import warnings


class CorrelationAnalyzer:
    """Analyzes correlation between price series"""
    
    @staticmethod
    def calculate_correlation(
        price_a: pd.Series,
        price_b: pd.Series,
        window: Optional[int] = None
    ) -> Tuple[float, float, float]:
        """
        Calculate Pearson correlation between two price series
        
        Args:
            price_a: Price series for asset A
            price_b: Price series for asset B
            window: Rolling window size (None = full period)
            
        Returns:
            Tuple of (correlation, min_correlation, max_correlation)
        """
        # Align series
        aligned = pd.DataFrame({'a': price_a, 'b': price_b}).dropna()
        
        if len(aligned) < 30:
            return 0.0, 0.0, 0.0
        
        # Calculate returns
        returns_a = aligned['a'].pct_change().dropna()
        returns_b = aligned['b'].pct_change().dropna()
        
        # Align returns
        returns_aligned = pd.DataFrame({'a': returns_a, 'b': returns_b}).dropna()
        
        if len(returns_aligned) < 30:
            return 0.0, 0.0, 0.0
        
        # Check for zero standard deviation (constant returns)
        std_a = returns_aligned['a'].std()
        std_b = returns_aligned['b'].std()
        
        if std_a == 0 or std_b == 0:
            # If either series has zero variance, correlation is undefined
            # Return 0.0 as default (no correlation)
            return 0.0, 0.0, 0.0
        
        if window:
            # Rolling correlation with warning suppression
            with warnings.catch_warnings():
                warnings.simplefilter("ignore", RuntimeWarning)
                rolling_corr = returns_aligned['a'].rolling(window=window).corr(returns_aligned['b'])
                rolling_corr = rolling_corr.dropna()
            
            if len(rolling_corr) == 0:
                # Fallback to full period
                with warnings.catch_warnings():
                    warnings.simplefilter("ignore", RuntimeWarning)
                    corr = returns_aligned['a'].corr(returns_aligned['b'])
                # Handle NaN from correlation calculation
                if pd.isna(corr):
                    return 0.0, 0.0, 0.0
                return corr, corr, corr
            
            # Filter out NaN values
            rolling_corr = rolling_corr[~pd.isna(rolling_corr)]
            if len(rolling_corr) == 0:
                return 0.0, 0.0, 0.0
            
            min_corr = rolling_corr.min()
            max_corr = rolling_corr.max()
            mean_corr = rolling_corr.mean()
            
            return mean_corr, min_corr, max_corr
        else:
            # Full period correlation with warning suppression
            with warnings.catch_warnings():
                warnings.simplefilter("ignore", RuntimeWarning)
                corr = returns_aligned['a'].corr(returns_aligned['b'])
            # Handle NaN from correlation calculation
            if pd.isna(corr):
                return 0.0, 0.0, 0.0
            return corr, corr, corr
    
    @staticmethod
    def calculate_volatility_ratio(price_a: pd.Series, price_b: pd.Series) -> float:
        """
        Calculate volatility ratio for hedge ratio calculation
        
        Args:
            price_a: Price series for asset A
            price_b: Price series for asset B
            
        Returns:
            Volatility ratio: σ_A / σ_B
        """
        returns_a = price_a.pct_change().dropna()
        returns_b = price_b.pct_change().dropna()
        
        vol_a = returns_a.std()
        vol_b = returns_b.std()
        
        if vol_b == 0:
            return 1.0
        
        return vol_a / vol_b

