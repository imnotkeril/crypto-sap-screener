"""
Trading strategies for pairs trading
"""
from typing import Optional
from enum import Enum
import pandas as pd


class TradeSignal(Enum):
    """Trading signals"""
    LONG_SPREAD = "long_spread"  # Buy spread (long A, short B)
    SHORT_SPREAD = "short_spread"  # Sell spread (short A, long B)
    CLOSE_LONG = "close_long"
    CLOSE_SHORT = "close_short"
    HOLD = "hold"


class ZScoreStrategy:
    """Z-Score based trading strategy"""
    
    def __init__(
        self,
        entry_threshold: float = 2.0,
        stop_loss: Optional[float] = None,
        stop_loss_type: str = 'percent',  # 'zscore', 'percent', 'atr'
        take_profit: Optional[float] = None,
        take_profit_type: str = 'percent',  # 'zscore', 'percent', 'atr'
        enable_rebalancing: bool = False,
        rebalancing_frequency_days: int = 5,
        rebalancing_threshold: float = 0.05,
    ):
        """
        Initialize Z-Score strategy
        
        Args:
            entry_threshold: Z-Score threshold for entry (default: 2.0)
            stop_loss: Stop loss value (depends on type)
            stop_loss_type: Type of stop loss ('zscore', 'percent', 'atr')
            take_profit: Take profit value (depends on type)
            take_profit_type: Type of take profit ('zscore', 'percent', 'atr')
            enable_rebalancing: Enable dynamic hedge rebalancing (default: False)
            rebalancing_frequency_days: Minimum days between rebalances (default: 5)
            rebalancing_threshold: Minimum beta drift % to trigger rebalance (default: 0.05 = 5%)
        """
        self.entry_threshold = entry_threshold
        self.stop_loss = stop_loss
        self.stop_loss_type = stop_loss_type
        self.take_profit = take_profit
        self.take_profit_type = take_profit_type
        self.enable_rebalancing = enable_rebalancing
        self.rebalancing_frequency_days = rebalancing_frequency_days
        self.rebalancing_threshold = rebalancing_threshold
    
    def generate_signals(
        self,
        zscores: pd.Series,
        current_position: Optional[str] = None
    ) -> pd.Series:
        """
        Generate trading signals based on Z-Score
        
        Args:
            zscores: Series of Z-Score values
            current_position: Current position ('long' or 'short' or None)
            
        Returns:
            Series of TradeSignal values
        """
        signals = pd.Series(index=zscores.index, dtype=object)
        
        def calc_zscore_take_profit_target_for_position(take_profit: float, position: str) -> float:
            """
            Convert user-facing take_profit (z-score) into an absolute target z-score level.

            Semantics:
            - take_profit >= 0: target is on the opposite side AFTER crossing 0
              LONG  -> target = +abs(take_profit)
              SHORT -> target = -abs(take_profit)
            - take_profit < 0: target is on the same side BEFORE reaching 0
              LONG  -> target = -abs(take_profit)
              SHORT -> target = +abs(take_profit)
            """
            if take_profit == 0:
                return 0.0

            magnitude = abs(float(take_profit))
            if position == 'long':
                entry_sign = -1.0
            elif position == 'short':
                entry_sign = 1.0
            else:
                return float(take_profit)

            if take_profit >= 0:
                return -entry_sign * magnitude
            return entry_sign * magnitude

        for i, zscore in enumerate(zscores):
            if pd.isna(zscore):
                signals.iloc[i] = TradeSignal.HOLD
                continue
            
            # Exit logic
            if current_position == 'long':
                if self.stop_loss and zscore >= self.stop_loss:
                    signals.iloc[i] = TradeSignal.CLOSE_LONG
                elif self.take_profit is not None and self.take_profit_type == 'zscore':
                    target_z = calc_zscore_take_profit_target_for_position(self.take_profit, 'long')
                    if zscore >= target_z:
                        signals.iloc[i] = TradeSignal.CLOSE_LONG
                else:
                    signals.iloc[i] = TradeSignal.HOLD
            elif current_position == 'short':
                if self.stop_loss and zscore <= -self.stop_loss:
                    signals.iloc[i] = TradeSignal.CLOSE_SHORT
                elif self.take_profit is not None and self.take_profit_type == 'zscore':
                    target_z = calc_zscore_take_profit_target_for_position(self.take_profit, 'short')
                    if zscore <= target_z:
                        signals.iloc[i] = TradeSignal.CLOSE_SHORT
                else:
                    signals.iloc[i] = TradeSignal.HOLD
            else:
                # Entry logic
                if zscore <= -self.entry_threshold:
                    signals.iloc[i] = TradeSignal.LONG_SPREAD
                elif zscore >= self.entry_threshold:
                    signals.iloc[i] = TradeSignal.SHORT_SPREAD
                else:
                    signals.iloc[i] = TradeSignal.HOLD
        
        return signals

