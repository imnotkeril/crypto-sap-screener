"""
Position calculator for pairs trading
Calculates position sizes based on beta (hedge ratio) and capital
"""
from typing import Dict, Literal
from enum import Enum


class PositionStrategy(str, Enum):
    """Position sizing strategies"""
    DOLLAR_NEUTRAL = "dollar_neutral"  # Long $X, Short $X*beta
    EQUAL_DOLLAR = "equal_dollar"  # Long $X/2, Short ($X/2)*beta
    LONG_ASSET_A = "long_asset_a"  # Long Asset A, Short Asset B
    LONG_ASSET_B = "long_asset_b"  # Long Asset B, Short Asset A


class PositionCalculator:
    """Calculate position sizes for pairs trading"""
    
    @staticmethod
    def calculate_position(
        capital: float,
        beta: float,
        asset_a_price: float,
        asset_b_price: float,
        strategy: PositionStrategy = PositionStrategy.DOLLAR_NEUTRAL,
        zscore: float = 0.0
    ) -> Dict:
        """
        Calculate position sizes for a pair
        
        Args:
            capital: Total capital to invest in USD
            beta: Hedge ratio (beta) from cointegration
            asset_a_price: Current price of asset A
            asset_b_price: Current price of asset B
            strategy: Position sizing strategy
            zscore: Current Z-Score (determines direction)
            
        Returns:
            Dictionary with position details:
            {
                'asset_a': {
                    'side': 'long' or 'short',
                    'quantity': float,
                    'dollar_amount': float,
                    'price': float
                },
                'asset_b': {
                    'side': 'long' or 'short',
                    'quantity': float,
                    'dollar_amount': float,
                    'price': float
                },
                'total_capital': float,
                'strategy': str,
                'beta': float
            }
        """
        if capital <= 0:
            raise ValueError("Capital must be positive")
        if beta <= 0:
            raise ValueError("Beta must be positive")
        if asset_a_price <= 0 or asset_b_price <= 0:
            raise ValueError("Asset prices must be positive")
        
        # Determine direction based on Z-Score
        # Z-Score > 0: spread is high, short spread (short A, long B)
        # Z-Score < 0: spread is low, long spread (long A, short B)
        if zscore > 0:
            # Spread is high - short the spread
            direction_a = "short"
            direction_b = "long"
        else:
            # Spread is low - long the spread
            direction_a = "long"
            direction_b = "short"
        
        if strategy == PositionStrategy.DOLLAR_NEUTRAL:
            # Asset A always gets $X, asset B gets $X*beta - the actual
            # long/short side for each is set above based on the z-score.
            dollar_a = capital
            dollar_b = capital * beta

        elif strategy == PositionStrategy.EQUAL_DOLLAR:
            # Split capital equally, then apply beta
            dollar_a = capital / 2
            dollar_b = (capital / 2) * beta
            
        elif strategy == PositionStrategy.LONG_ASSET_A:
            # Always long A, short B
            dollar_a = capital
            dollar_b = capital * beta
            direction_a = "long"
            direction_b = "short"
            
        elif strategy == PositionStrategy.LONG_ASSET_B:
            # Always long B, short A
            dollar_a = capital * beta
            dollar_b = capital
            direction_a = "short"
            direction_b = "long"
        else:
            raise ValueError(f"Unknown strategy: {strategy}")
        
        # Calculate quantities
        quantity_a = dollar_a / asset_a_price
        quantity_b = dollar_b / asset_b_price
        
        return {
            'asset_a': {
                'side': direction_a,
                'quantity': quantity_a,
                'dollar_amount': dollar_a,
                'price': asset_a_price
            },
            'asset_b': {
                'side': direction_b,
                'quantity': quantity_b,
                'dollar_amount': dollar_b,
                'price': asset_b_price
            },
            'total_capital': capital,
            'strategy': strategy.value,
            'beta': beta,
            'zscore': zscore,
            'net_exposure': abs(dollar_a - dollar_b)  # Net dollar exposure
        }
    
    @staticmethod
    def calculate_estimated_pnl(
        position: Dict,
        price_a_change_pct: float,
        price_b_change_pct: float
    ) -> Dict:
        """
        Calculate estimated P&L for different price change scenarios
        
        Args:
            position: Position dictionary from calculate_position
            price_a_change_pct: Expected price change for asset A (as decimal, e.g., 0.01 = 1%)
            price_b_change_pct: Expected price change for asset B (as decimal)
            
        Returns:
            Dictionary with P&L calculations:
            {
                'pnl_a': float,
                'pnl_b': float,
                'total_pnl': float,
                'return_pct': float
            }
        """
        asset_a = position['asset_a']
        asset_b = position['asset_b']
        
        # Calculate P&L for each asset
        if asset_a['side'] == 'long':
            pnl_a = asset_a['dollar_amount'] * price_a_change_pct
        else:
            pnl_a = -asset_a['dollar_amount'] * price_a_change_pct
        
        if asset_b['side'] == 'long':
            pnl_b = asset_b['dollar_amount'] * price_b_change_pct
        else:
            pnl_b = -asset_b['dollar_amount'] * price_b_change_pct
        
        total_pnl = pnl_a + pnl_b
        return_pct = (total_pnl / position['total_capital']) * 100
        
        return {
            'pnl_a': pnl_a,
            'pnl_b': pnl_b,
            'total_pnl': total_pnl,
            'return_pct': return_pct
        }

