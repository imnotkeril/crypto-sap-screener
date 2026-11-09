"""
Metrics calculation for backtesting
"""
from typing import List, Dict
import pandas as pd
import numpy as np


class BacktestMetrics:
    """Calculate backtest performance metrics"""
    
    @staticmethod
    def calculate_sharpe_ratio(returns: pd.Series, risk_free_rate: float = 0.0, periods_per_year: float = 365.0) -> float:
        """
        Calculate Sharpe ratio
        
        Args:
            returns: Series of returns
            risk_free_rate: Risk-free rate (default: 0.0)
            
        Returns:
            Sharpe ratio
        """
        if len(returns) == 0 or returns.std() == 0:
            return 0.0
        
        excess_returns = returns - risk_free_rate
        return np.sqrt(periods_per_year) * excess_returns.mean() / returns.std()  # 365 daily bars/year for crypto (24/7)
    
    @staticmethod
    def calculate_max_drawdown(equity_curve: pd.Series) -> float:
        """
        Calculate maximum drawdown
        
        Args:
            equity_curve: Series of cumulative equity values
            
        Returns:
            Maximum drawdown as a percentage
        """
        if len(equity_curve) == 0:
            return 0.0
        
        running_max = equity_curve.expanding().max()
        drawdown = (equity_curve - running_max) / running_max
        return abs(drawdown.min()) * 100
    
    @staticmethod
    def calculate_win_rate(trades: List[Dict]) -> float:
        """
        Calculate win rate
        
        Args:
            trades: List of trade dictionaries with 'pnl' key
            
        Returns:
            Win rate as a percentage
        """
        if not trades:
            return 0.0
        
        # Filter out trades with None pnl (open positions)
        closed_trades = [t for t in trades if t.get('pnl') is not None]
        if not closed_trades:
            return 0.0
        
        winning_trades = [t for t in closed_trades if t.get('pnl', 0) > 0]
        return (len(winning_trades) / len(closed_trades)) * 100
    
    @staticmethod
    def calculate_profit_factor(trades: List[Dict]) -> float:
        """
        Calculate profit factor
        
        Args:
            trades: List of trade dictionaries with 'pnl' key
            
        Returns:
            Profit factor (gross profit / gross loss)
        """
        if not trades:
            return 0.0
        
        # Filter out trades with None pnl (open positions)
        closed_trades = [t for t in trades if t.get('pnl') is not None]
        if not closed_trades:
            return 0.0
        
        gross_profit = sum(t.get('pnl', 0) for t in closed_trades if t.get('pnl', 0) > 0)
        gross_loss = abs(sum(t.get('pnl', 0) for t in closed_trades if t.get('pnl', 0) < 0))
        
        if gross_loss == 0:
            # Return a large number instead of inf for JSON compatibility
            # This represents "perfect" profit factor (no losses)
            return 999999.0 if gross_profit > 0 else 0.0
        
        return gross_profit / gross_loss
    
    @staticmethod
    def calculate_mae_metrics(trades: List[Dict]) -> Dict[str, float]:
        """
        Calculate Maximum Adverse Excursion (MAE) metrics
        
        Args:
            trades: List of trade dictionaries with 'max_adverse_excursion' and 'mae_pct' keys
            
        Returns:
            Dictionary with average and maximum MAE metrics
        """
        if not trades:
            return {
                'avg_mae': 0.0,
                'max_mae': 0.0,
                'avg_mae_pct': 0.0,
                'max_mae_pct': 0.0
            }
        
        # Filter out trades without MAE data
        trades_with_mae = [t for t in trades if 'max_adverse_excursion' in t and t.get('max_adverse_excursion') is not None]
        if not trades_with_mae:
            return {
                'avg_mae': 0.0,
                'max_mae': 0.0,
                'avg_mae_pct': 0.0,
                'max_mae_pct': 0.0
            }
        
        mae_values = [t['max_adverse_excursion'] for t in trades_with_mae]
        mae_pct_values = [t.get('mae_pct', 0) for t in trades_with_mae]
        
        return {
            'avg_mae': sum(mae_values) / len(mae_values),
            'max_mae': min(mae_values),  # Min because MAE is negative
            'avg_mae_pct': sum(mae_pct_values) / len(mae_pct_values),
            'max_mae_pct': min(mae_pct_values)  # Min because MAE % is negative
        }
    
    @staticmethod
    def calculate_total_return(equity_curve: pd.Series) -> float:
        """
        Calculate total return
        
        Args:
            equity_curve: Series of cumulative equity values
            
        Returns:
            Total return as a percentage
        """
        if len(equity_curve) == 0:
            return 0.0
        
        initial = equity_curve.iloc[0]
        final = equity_curve.iloc[-1]
        
        if initial == 0:
            return 0.0
        
        return ((final - initial) / initial) * 100
    
    @staticmethod
    def calculate_optimal_leverage(
        sharpe_ratio: float,
        max_drawdown: float,
        target_sharpe: float = 1.0,
        max_leverage: float = 5.0,
        risk_factor: float = 0.5
    ) -> Dict[str, float]:
        """
        Calculate optimal leverage based on Sharpe ratio and max drawdown
        
        Methods:
        1. Sharpe-based: leverage = sharpe / target_sharpe
        2. Drawdown-based: leverage = 1 / (max_drawdown / 100) * risk_factor
        3. Conservative: min of both methods
        
        Args:
            sharpe_ratio: Current Sharpe ratio
            max_drawdown: Max drawdown percentage
            target_sharpe: Target Sharpe ratio (default: 1.0)
            max_leverage: Maximum allowed leverage (default: 5.0)
            risk_factor: Risk adjustment factor (default: 0.5 for conservative)
            
        Returns:
            Dictionary with leverage recommendations
        """
        if sharpe_ratio <= 0 or max_drawdown <= 0:
            return {
                'optimal_leverage': 1.0,
                'sharpe_based': 1.0,
                'drawdown_based': 1.0,
                'recommended': 1.0,
                'max_leverage': max_leverage
            }
        
        # Method 1: Sharpe-based leverage
        # If Sharpe = 1.5 and target = 1.0, leverage = 1.5x
        # Sharpe ratio doesn't change with leverage (return and risk scale proportionally)
        sharpe_based = sharpe_ratio / target_sharpe
        
        # Method 2: Drawdown-based leverage
        # If max DD = 3%, can use 1 / 0.03 * 0.5 = 16.67x (but we cap it)
        # Formula: leverage = 1 / (max_drawdown / 100) * risk_factor
        # This allows higher leverage for lower drawdown strategies
        drawdown_based = min(1.0 / (max_drawdown / 100) * risk_factor, max_leverage)
        
        # Method 3: Use the more conservative of the two, but prioritize drawdown for low-risk strategies
        # If drawdown is very low (< 5%), drawdown-based is more relevant
        # If drawdown is higher, sharpe-based becomes the limiting factor
        if max_drawdown < 5.0:
            # Low drawdown: use drawdown-based as primary, but cap by sharpe if it's lower
            optimal_leverage = min(drawdown_based, max(sharpe_based, 1.0), max_leverage)
            # For recommended, use drawdown-based (scaled down) since it's the relevant constraint
            recommended = min(max(1.0, drawdown_based * 0.75), max_leverage)
        else:
            # Higher drawdown: use conservative minimum
            optimal_leverage = min(sharpe_based, drawdown_based, max_leverage)
            # Recommended: Use fractional leverage (75% of optimal for safety)
            recommended = max(1.0, optimal_leverage * 0.75) if optimal_leverage > 1.5 else optimal_leverage
        
        return {
            'optimal_leverage': round(max(1.0, optimal_leverage), 2),
            'sharpe_based': round(max(1.0, sharpe_based), 2),
            'drawdown_based': round(max(1.0, drawdown_based), 2),
            'recommended': round(max(1.0, recommended), 2),
            'max_leverage': max_leverage
        }
    
    @staticmethod
    def calculate_kelly_criterion(
        win_rate: float,
        avg_win: float,
        avg_loss: float
    ) -> float:
        """
        Calculate Kelly Criterion for optimal position sizing
        
        Formula: f* = (bp - q) / b
        where:
            f* = fraction of capital to risk
            b = avg_win / avg_loss (win/loss ratio)
            p = win_rate (probability of win)
            q = 1 - p (probability of loss)
        
        Args:
            win_rate: Win rate as percentage (0-100)
            avg_win: Average winning trade P&L
            avg_loss: Average losing trade P&L (positive number)
            
        Returns:
            Kelly percentage (0-100)
        """
        if avg_loss <= 0 or win_rate <= 0 or win_rate >= 100:
            return 0.0
        
        p = win_rate / 100.0
        q = 1 - p
        b = avg_win / avg_loss if avg_loss > 0 else 0
        
        if b <= 0:
            return 0.0
        
        kelly = (b * p - q) / b
        
        # Kelly can be negative (don't trade) or > 1 (use leverage)
        # Cap at 100% for safety (fractional Kelly is often used)
        return max(0.0, min(kelly * 100, 100.0))
    
    @staticmethod
    def calculate_return_to_mae_ratio(
        total_return: float,
        avg_mae_pct: float
    ) -> float:
        """
        Calculate Return/MAE Ratio (alternative to Sharpe using MAE as risk measure)
        
        This metric measures return per unit of maximum adverse excursion.
        Higher ratio means better returns relative to worst drawdown during holding.
        
        Unlike Sharpe which uses standard deviation (total volatility),
        this focuses on downside risk only.
        
        Args:
            total_return: Total return percentage
            avg_mae_pct: Average MAE percentage (should be negative or absolute value)
            
        Returns:
            Return/MAE ratio (higher is better)
        """
        # MAE is typically negative, so we use absolute value
        mae_abs = abs(avg_mae_pct)
        
        if mae_abs == 0 or mae_abs < 0.01:
            # If MAE is zero or negligible, return large number
            return 999999.0 if total_return > 0 else 0.0
        
        return total_return / mae_abs

