"""
Main backtester for pairs trading strategies
"""
from typing import Dict, Optional, Tuple
from datetime import datetime
import pandas as pd
import numpy as np
import logging

from .strategy import ZScoreStrategy, TradeSignal
from .metrics import BacktestMetrics
from app.modules.screener.data_loader import DataLoader
from app.modules.screener.cointegration import CointegrationTester

logger = logging.getLogger(__name__)


class Backtester:
    """Backtest pairs trading strategies"""
    
    def __init__(self, initial_capital: float = 10000.0, transaction_cost_pct: float = 0.001):
        """
        Initialize backtester
        
        Args:
            initial_capital: Starting capital in USD
            transaction_cost_pct: Transaction cost as % of notional (default: 0.001 = 0.1%)
        """
        self.initial_capital = initial_capital
        self.transaction_cost_pct = transaction_cost_pct
        self.data_loader = DataLoader()
    
    def run_backtest(
        self,
        asset_a: str,
        asset_b: str,
        strategy: ZScoreStrategy,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
        lookback_days: int = 365,
        beta: Optional[float] = None,
        position_size_pct: float = 100.0
    ) -> Dict:
        """
        Run backtest for a pair
        
        Args:
            asset_a: First asset symbol
            asset_b: Second asset symbol
            strategy: Trading strategy
            start_date: Start date for backtest (optional)
            end_date: End date for backtest (optional)
            lookback_days: Number of days to look back for data
            beta: Pre-calculated beta (optional, will calculate if not provided)
            
        Returns:
            Dictionary with backtest results
        """
        # Load price data
        price_a = self.data_loader.get_price_series(asset_a, days=lookback_days, db=None)
        price_b = self.data_loader.get_price_series(asset_b, days=lookback_days, db=None)
        
        if len(price_a) < 50 or len(price_b) < 50:
            raise ValueError("Insufficient data for backtesting")
        
        # Align prices
        aligned = pd.DataFrame({'a': price_a, 'b': price_b}).dropna()
        if len(aligned) < 50:
            raise ValueError("Insufficient aligned data for backtesting")
        
        # Calculate beta if not provided
        if beta is None:
            X = aligned['b'].values.reshape(-1, 1)
            y = aligned['a'].values
            X_with_const = np.column_stack([np.ones(len(X)), X])
            from statsmodels.regression.linear_model import OLS
            model = OLS(y, X_with_const).fit()
            beta = float(model.params[1])
            alpha = float(model.params[0])
        else:
            # Calculate alpha
            X = aligned['b'].values.reshape(-1, 1)
            y = aligned['a'].values
            X_with_const = np.column_stack([np.ones(len(X)), X])
            from statsmodels.regression.linear_model import OLS
            model = OLS(y, X_with_const).fit()
            alpha = float(model.params[0])
        
        # Calculate ATR for spread (if needed for stop loss/take profit)
        def calculate_atr(series: pd.Series, period: int = 14) -> pd.Series:
            """Calculate Average True Range for spread"""
            high = series.rolling(window=period).max()
            low = series.rolling(window=period).min()
            tr = high - low
            atr = tr.rolling(window=period).mean()
            return atr

        def calc_zscore_take_profit_target(entry_z: float, take_profit: float) -> float:
            """
            Convert user-facing take_profit (z-score) into an absolute target z-score level.

            Semantics:
            - take_profit >= 0: target is on the opposite side AFTER crossing 0
              Example: entry_z=+2 (SHORT), take_profit=+1 -> target=-1
                       entry_z=-2 (LONG),  take_profit=+1 -> target=+1
            - take_profit < 0: target is on the same side BEFORE reaching 0
              Example: entry_z=+2 (SHORT), take_profit=-1 -> target=+1
                       entry_z=-2 (LONG),  take_profit=-1 -> target=-1
            """
            if take_profit == 0:
                return 0.0

            if entry_z > 0:
                entry_sign = 1.0
            elif entry_z < 0:
                entry_sign = -1.0
            else:
                # Should not happen (we enter only beyond a threshold), but keep legacy behavior if it does.
                return float(take_profit)

            magnitude = abs(float(take_profit))
            if take_profit >= 0:
                return -entry_sign * magnitude
            return entry_sign * magnitude
        
        # Pre-calculate global spread for ATR calculation
        global_spread = CointegrationTester.calculate_spread(
            aligned['a'],
            aligned['b'],
            beta,
            alpha
        )
        spread_atr = calculate_atr(global_spread, period=14) if strategy.stop_loss_type == 'atr' or strategy.take_profit_type == 'atr' else None
        
        # Helper function to calculate rolling beta/alpha
        def calculate_rolling_beta_alpha(current_index: int, rolling_window: int = 90) -> Tuple[float, float]:
            """
            Calculate rolling beta and alpha using historical data up to current index
            
            Args:
                current_index: Current index in aligned dataframe
                rolling_window: Number of days to look back (default: 90)
                
            Returns:
                Tuple of (beta, alpha)
            """
            # Use rolling window or available data, but need at least 30 days
            start_idx = max(0, current_index - rolling_window)
            end_idx = current_index  # Exclude current date
            
            if end_idx - start_idx < 30:
                # Not enough data, use global beta/alpha
                return beta, alpha
            
            # Get historical data up to (but not including) current date
            historical_data = aligned.iloc[start_idx:end_idx]
            
            if len(historical_data) < 30:
                return beta, alpha
            
            try:
                X = historical_data['b'].values.reshape(-1, 1)
                y = historical_data['a'].values
                X_with_const = np.column_stack([np.ones(len(X)), X])
                from statsmodels.regression.linear_model import OLS
                model = OLS(y, X_with_const).fit()
                rolling_beta = float(model.params[1])
                rolling_alpha = float(model.params[0])
                
                # Validate beta (should be positive and reasonable)
                if rolling_beta <= 0 or rolling_beta > 10:
                    return beta, alpha
                
                return rolling_beta, rolling_alpha
            except Exception:
                # If calculation fails, use global beta/alpha
                return beta, alpha
        
        # Execute trades - generate signals dynamically on each step
        trades = []
        equity_curve = []
        rolling_zscore_list = []  # Store rolling z-scores for chart
        rolling_dates_list = []   # Store corresponding dates
        current_position = None
        entry_price_a = None
        entry_price_b = None
        entry_zscore = None
        entry_spread = None
        entry_beta = None
        entry_alpha = None
        max_adverse_excursion = 0.0  # Track maximum drawdown during position holding
        capital = self.initial_capital
        total_rebalancing_costs = 0.0  # Track total costs from rebalancing
        last_rebalance_date = None  # Track last rebalancing date
        
        # Iterate through dates and generate signals dynamically
        for i, date in enumerate(aligned.index):
            price_a_val = aligned.loc[date, 'a']
            price_b_val = aligned.loc[date, 'b']
            current_atr = spread_atr.loc[date] if spread_atr is not None and not pd.isna(spread_atr.loc[date]) else None
            
            # ALWAYS calculate rolling z-score (for both entry and exit signals)
            # This ensures consistency between what we see on chart and what we trade
            zscore_val = None
            spread_val = None
            current_beta_for_signal = beta
            current_alpha_for_signal = alpha
            
            # Calculate rolling beta/alpha
            current_beta_for_signal, current_alpha_for_signal = calculate_rolling_beta_alpha(i, rolling_window=90)
            
            # Calculate rolling z-score with window of 60 days
            spread_window = min(60, i + 1)  # Include current date
            if spread_window >= 30:
                spread_data = aligned.iloc[max(0, i+1-spread_window):i+1]  # Include current date
                if len(spread_data) >= 30:
                    try:
                        current_spread = CointegrationTester.calculate_spread(
                            spread_data['a'],
                            spread_data['b'],
                            current_beta_for_signal,
                            current_alpha_for_signal
                        )
                        current_zscore_series = CointegrationTester.calculate_zscore(current_spread)
                        if len(current_zscore_series) > 0:
                            zscore_val = current_zscore_series.iloc[-1]
                            spread_val = current_spread.iloc[-1]
                    except Exception:
                        # If recalculation fails, skip this bar
                        equity_curve.append(capital)
                        continue
            
            # If we couldn't calculate rolling z-score, skip this bar
            if zscore_val is None or pd.isna(zscore_val):
                equity_curve.append(capital)
                continue
            
            # Store rolling z-score for chart
            rolling_zscore_list.append(zscore_val)
            rolling_dates_list.append(date)
            
            # Generate signal dynamically based on current position
            signal = None
            
            if current_position == 'long':
                # Calculate current unrealized P&L
                last_trade = trades[-1]
                current_pnl_a = (price_a_val - entry_price_a) * last_trade['quantity_a']
                current_pnl_b = (entry_price_b - price_b_val) * last_trade['quantity_b']
                current_total_pnl = current_pnl_a + current_pnl_b
                
                # Update maximum adverse excursion (track worst drawdown)
                if current_total_pnl < max_adverse_excursion:
                    max_adverse_excursion = current_total_pnl
                
                # REBALANCING LOGIC: Check if we should rebalance the hedge
                if strategy.enable_rebalancing:
                    days_since_entry = (date - last_trade['entry_date']).days if isinstance(date, pd.Timestamp) else 0
                    days_since_last_rebalance = (date - last_rebalance_date).days if last_rebalance_date else days_since_entry
                    
                    # Check conditions for rebalancing:
                    # 1. Sufficient time has passed since last rebalance
                    # 2. Beta has drifted beyond threshold
                    if days_since_last_rebalance >= strategy.rebalancing_frequency_days:
                        current_beta_check, current_alpha_check = calculate_rolling_beta_alpha(i, rolling_window=90)
                        beta_drift_pct = abs(current_beta_check - entry_beta) / entry_beta if entry_beta > 0 else 0
                        
                        if beta_drift_pct >= strategy.rebalancing_threshold:
                            # Calculate new quantities based on current beta
                            trade_capital = last_trade['trade_capital']
                            new_quantity_a = trade_capital / (price_a_val + current_beta_check * price_b_val)
                            new_quantity_b = current_beta_check * new_quantity_a
                            
                            # Calculate change in positions
                            delta_quantity_a = new_quantity_a - last_trade['quantity_a']
                            delta_quantity_b = new_quantity_b - last_trade['quantity_b']
                            
                            # Calculate transaction costs
                            rebalance_notional = abs(delta_quantity_a * price_a_val) + abs(delta_quantity_b * price_b_val)
                            rebalance_cost = rebalance_notional * self.transaction_cost_pct
                            
                            # Apply rebalancing
                            last_trade['quantity_a'] = new_quantity_a
                            last_trade['quantity_b'] = new_quantity_b
                            last_trade['dollar_a'] = new_quantity_a * price_a_val
                            last_trade['dollar_b'] = new_quantity_b * price_b_val
                            
                            # Update entry beta/alpha for future drift calculations
                            entry_beta = current_beta_check
                            entry_alpha = current_alpha_check
                            
                            # Deduct costs from capital
                            capital -= rebalance_cost
                            total_rebalancing_costs += rebalance_cost
                            last_rebalance_date = date
                            
                            # Log rebalancing
                            if 'rebalances' not in last_trade:
                                last_trade['rebalances'] = []
                            last_trade['rebalances'].append({
                                'date': date,
                                'old_beta': entry_beta,
                                'new_beta': current_beta_check,
                                'beta_drift_pct': beta_drift_pct * 100,
                                'delta_quantity_a': delta_quantity_a,
                                'delta_quantity_b': delta_quantity_b,
                                'cost': rebalance_cost,
                                'new_quantity_a': new_quantity_a,
                                'new_quantity_b': new_quantity_b
                            })
                            
                            logger.debug(f"REBALANCING (LONG) on {date}: Beta drift: {entry_beta:.4f} → {current_beta_check:.4f} ({beta_drift_pct*100:.2f}%), Cost: ${rebalance_cost:.2f}")
                
                # Check exit conditions for long position
                # For LONG: we enter when z-score <= -entry_threshold (spread is low)
                # Exit ONLY via Stop Loss or Take Profit (no exit threshold)
                
                # Calculate current P&L percentage relative to initial capital
                current_pnl_pct = (current_total_pnl / self.initial_capital) * 100
                
                # Check Stop Loss conditions
                if strategy.stop_loss is not None:
                    if strategy.stop_loss_type == 'percent' and current_pnl_pct <= -strategy.stop_loss:
                        signal = TradeSignal.CLOSE_LONG
                    elif strategy.stop_loss_type == 'zscore' and zscore_val >= strategy.stop_loss:
                        signal = TradeSignal.CLOSE_LONG
                    elif strategy.stop_loss_type == 'atr' and current_atr is not None:
                        spread_change = abs(spread_val - entry_spread)
                        if spread_change >= strategy.stop_loss * current_atr:
                            signal = TradeSignal.CLOSE_LONG
                
                # Check Take Profit conditions (only if stop loss didn't trigger)
                if signal != TradeSignal.CLOSE_LONG and strategy.take_profit is not None:
                    if strategy.take_profit_type == 'percent' and current_pnl_pct >= strategy.take_profit:
                        signal = TradeSignal.CLOSE_LONG
                    elif strategy.take_profit_type == 'zscore':
                        # For LONG: entered at negative z-score, exit as z-score moves upward toward target.
                        # take_profit semantics:
                        # - >=0: opposite side after 0 (e.g., +1 => target +1 for LONG, -1 for SHORT)
                        # - <0: same side before 0 (e.g., -1 => target -1 for LONG, +1 for SHORT)
                        target_z = calc_zscore_take_profit_target(entry_zscore, float(strategy.take_profit))
                        if zscore_val >= target_z:
                            signal = TradeSignal.CLOSE_LONG
                    elif strategy.take_profit_type == 'atr' and current_atr is not None:
                        spread_change = spread_val - entry_spread
                        if spread_change >= strategy.take_profit * current_atr:
                            signal = TradeSignal.CLOSE_LONG
                
                if signal != TradeSignal.CLOSE_LONG:
                    signal = TradeSignal.HOLD
                    
            elif current_position == 'short':
                # Calculate current unrealized P&L
                last_trade = trades[-1]
                current_pnl_a = (entry_price_a - price_a_val) * last_trade['quantity_a']
                current_pnl_b = (price_b_val - entry_price_b) * last_trade['quantity_b']
                current_total_pnl = current_pnl_a + current_pnl_b
                
                # Update maximum adverse excursion (track worst drawdown)
                if current_total_pnl < max_adverse_excursion:
                    max_adverse_excursion = current_total_pnl
                
                # REBALANCING LOGIC: Check if we should rebalance the hedge
                if strategy.enable_rebalancing:
                    days_since_entry = (date - last_trade['entry_date']).days if isinstance(date, pd.Timestamp) else 0
                    days_since_last_rebalance = (date - last_rebalance_date).days if last_rebalance_date else days_since_entry
                    
                    # Check conditions for rebalancing:
                    # 1. Sufficient time has passed since last rebalance
                    # 2. Beta has drifted beyond threshold
                    if days_since_last_rebalance >= strategy.rebalancing_frequency_days:
                        current_beta_check, current_alpha_check = calculate_rolling_beta_alpha(i, rolling_window=90)
                        beta_drift_pct = abs(current_beta_check - entry_beta) / entry_beta if entry_beta > 0 else 0
                        
                        if beta_drift_pct >= strategy.rebalancing_threshold:
                            # Calculate new quantities based on current beta
                            trade_capital = last_trade['trade_capital']
                            new_quantity_a = trade_capital / (price_a_val + current_beta_check * price_b_val)
                            new_quantity_b = current_beta_check * new_quantity_a
                            
                            # Calculate change in positions
                            delta_quantity_a = new_quantity_a - last_trade['quantity_a']
                            delta_quantity_b = new_quantity_b - last_trade['quantity_b']
                            
                            # Calculate transaction costs
                            rebalance_notional = abs(delta_quantity_a * price_a_val) + abs(delta_quantity_b * price_b_val)
                            rebalance_cost = rebalance_notional * self.transaction_cost_pct
                            
                            # Apply rebalancing
                            last_trade['quantity_a'] = new_quantity_a
                            last_trade['quantity_b'] = new_quantity_b
                            last_trade['dollar_a'] = new_quantity_a * price_a_val
                            last_trade['dollar_b'] = new_quantity_b * price_b_val
                            
                            # Update entry beta/alpha for future drift calculations
                            entry_beta = current_beta_check
                            entry_alpha = current_alpha_check
                            
                            # Deduct costs from capital
                            capital -= rebalance_cost
                            total_rebalancing_costs += rebalance_cost
                            last_rebalance_date = date
                            
                            # Log rebalancing
                            if 'rebalances' not in last_trade:
                                last_trade['rebalances'] = []
                            last_trade['rebalances'].append({
                                'date': date,
                                'old_beta': entry_beta,
                                'new_beta': current_beta_check,
                                'beta_drift_pct': beta_drift_pct * 100,
                                'delta_quantity_a': delta_quantity_a,
                                'delta_quantity_b': delta_quantity_b,
                                'cost': rebalance_cost,
                                'new_quantity_a': new_quantity_a,
                                'new_quantity_b': new_quantity_b
                            })
                            
                            logger.debug(f"REBALANCING (SHORT) on {date}: Beta drift: {entry_beta:.4f} → {current_beta_check:.4f} ({beta_drift_pct*100:.2f}%), Cost: ${rebalance_cost:.2f}")
                
                # Check exit conditions for short position
                # For SHORT: we enter when z-score >= entry_threshold (spread is high)
                # Exit ONLY via Stop Loss or Take Profit (no exit threshold)
                
                # Calculate current P&L percentage relative to initial capital
                current_pnl_pct = (current_total_pnl / self.initial_capital) * 100
                
                # Check Stop Loss conditions
                if strategy.stop_loss is not None:
                    if strategy.stop_loss_type == 'percent' and current_pnl_pct <= -strategy.stop_loss:
                        signal = TradeSignal.CLOSE_SHORT
                    elif strategy.stop_loss_type == 'zscore' and zscore_val <= -strategy.stop_loss:
                        signal = TradeSignal.CLOSE_SHORT
                    elif strategy.stop_loss_type == 'atr' and current_atr is not None:
                        spread_change = abs(spread_val - entry_spread)
                        if spread_change >= strategy.stop_loss * current_atr:
                            signal = TradeSignal.CLOSE_SHORT
                
                # Check Take Profit conditions (only if stop loss didn't trigger)
                if signal != TradeSignal.CLOSE_SHORT and strategy.take_profit is not None:
                    if strategy.take_profit_type == 'percent' and current_pnl_pct >= strategy.take_profit:
                        signal = TradeSignal.CLOSE_SHORT
                    elif strategy.take_profit_type == 'zscore':
                        # For SHORT: entered at positive z-score, exit as z-score moves downward toward target.
                        target_z = calc_zscore_take_profit_target(entry_zscore, float(strategy.take_profit))
                        if zscore_val <= target_z:
                            signal = TradeSignal.CLOSE_SHORT
                    elif strategy.take_profit_type == 'atr' and current_atr is not None:
                        spread_change = entry_spread - spread_val
                        if spread_change >= strategy.take_profit * current_atr:
                            signal = TradeSignal.CLOSE_SHORT
                
                if signal != TradeSignal.CLOSE_SHORT:
                    signal = TradeSignal.HOLD
            else:
                # No position - check entry conditions
                if zscore_val <= -strategy.entry_threshold:
                    signal = TradeSignal.LONG_SPREAD
                elif zscore_val >= strategy.entry_threshold:
                    signal = TradeSignal.SHORT_SPREAD
                else:
                    signal = TradeSignal.HOLD
            
            # Execute trade based on signal
            if signal == TradeSignal.HOLD or signal is None:
                equity_curve.append(capital)
                continue
            
            # Execute trade
            if signal == TradeSignal.LONG_SPREAD:
                # Long spread: Long A, Short B
                if current_position is None:
                    # Calculate rolling beta/alpha for position sizing
                    # Use historical data up to current date (not including current date)
                    current_beta, current_alpha = calculate_rolling_beta_alpha(i, rolling_window=90)
                    
                    # Calculate position sizes (dollar neutral with beta hedge)
                    # Use fixed position size based on INITIAL capital to avoid compounding issues
                    # position_size_pct is percentage of initial capital to use (e.g., 100% = use all capital)
                    trade_capital = self.initial_capital * (position_size_pct / 100.0)
                    
                    # CORRECT beta hedge calculation:
                    # Beta hedge means: quantity_b = beta * quantity_a (for proper spread hedge)
                    # Dollar-neutral means: dollar_a + dollar_b = trade_capital
                    #
                    # Combining both:
                    #   quantity_a * price_a + quantity_b * price_b = trade_capital
                    #   quantity_a * price_a + beta * quantity_a * price_b = trade_capital
                    #   quantity_a * (price_a + beta * price_b) = trade_capital
                    #   quantity_a = trade_capital / (price_a + beta * price_b)
                    #   quantity_b = beta * quantity_a
                    #
                    # Example with trade_capital = $10,000, price_a = $100, price_b = $50, beta = 0.8:
                    #   quantity_a = 10,000 / (100 + 0.8 * 50) = 10,000 / 140 = 71.43 units
                    #   quantity_b = 0.8 * 71.43 = 57.14 units
                    #   dollar_a = 71.43 * $100 = $7,143
                    #   dollar_b = 57.14 * $50 = $2,857
                    #   Total: $7,143 + $2,857 = $10,000 ✓
                    #   Hedge ratio: quantity_b / quantity_a = 57.14 / 71.43 = 0.8 = beta ✓
                    quantity_a = trade_capital / (price_a_val + current_beta * price_b_val)
                    quantity_b = current_beta * quantity_a
                    
                    dollar_a = quantity_a * price_a_val
                    dollar_b = quantity_b * price_b_val
                    
                    # Apply transaction costs for entry
                    entry_notional = dollar_a + dollar_b
                    entry_cost = entry_notional * self.transaction_cost_pct
                    capital -= entry_cost
                    
                    current_position = 'long'
                    entry_price_a = price_a_val
                    entry_price_b = price_b_val
                    entry_zscore = zscore_val
                    entry_spread = spread_val
                    entry_beta = current_beta
                    entry_alpha = current_alpha
                    max_adverse_excursion = 0.0  # Reset MAE for new position
                    last_rebalance_date = None  # Reset rebalancing tracker for new position
                    
                    trades.append({
                        'entry_date': date,
                        'entry_signal': 'long_spread',
                        'entry_price_a': entry_price_a,
                        'entry_price_b': entry_price_b,
                        'entry_zscore': entry_zscore,
                        'entry_spread': entry_spread,
                        'quantity_a': quantity_a,
                        'quantity_b': quantity_b,
                        'dollar_a': dollar_a,  # Dollar amount allocated to asset A
                        'dollar_b': dollar_b,  # Dollar amount allocated to asset B
                        'trade_capital': trade_capital,  # Total capital used for this trade
                        'beta_used': current_beta,  # Beta used for this trade (rolling)
                        'alpha_used': current_alpha,  # Alpha used for this trade (rolling)
                    })
            
            elif signal == TradeSignal.SHORT_SPREAD:
                # Short spread: Short A, Long B
                if current_position is None:
                    # Calculate rolling beta/alpha for position sizing
                    # Use historical data up to current date (not including current date)
                    current_beta, current_alpha = calculate_rolling_beta_alpha(i, rolling_window=90)
                    
                    # Calculate position sizes (dollar neutral with beta hedge)
                    # For SHORT_SPREAD: Short $X in Asset A, Long $X*beta in Asset B
                    # Same calculation as long spread (just opposite direction)
                    trade_capital = self.initial_capital * (position_size_pct / 100.0)
                    
                    # CORRECT beta hedge calculation (same as LONG_SPREAD):
                    # Beta hedge means: quantity_b = beta * quantity_a
                    # Dollar-neutral means: dollar_a + dollar_b = trade_capital
                    # quantity_a = trade_capital / (price_a + beta * price_b)
                    # quantity_b = beta * quantity_a
                    quantity_a = trade_capital / (price_a_val + current_beta * price_b_val)
                    quantity_b = current_beta * quantity_a
                    
                    dollar_a = quantity_a * price_a_val
                    dollar_b = quantity_b * price_b_val
                    
                    # Apply transaction costs for entry
                    entry_notional = dollar_a + dollar_b
                    entry_cost = entry_notional * self.transaction_cost_pct
                    capital -= entry_cost
                    
                    current_position = 'short'
                    entry_price_a = price_a_val
                    entry_price_b = price_b_val
                    entry_zscore = zscore_val
                    entry_spread = spread_val
                    entry_beta = current_beta
                    entry_alpha = current_alpha
                    max_adverse_excursion = 0.0  # Reset MAE for new position
                    last_rebalance_date = None  # Reset rebalancing tracker for new position
                    
                    trades.append({
                        'entry_date': date,
                        'entry_signal': 'short_spread',
                        'entry_price_a': entry_price_a,
                        'entry_price_b': entry_price_b,
                        'entry_zscore': entry_zscore,
                        'entry_spread': entry_spread,
                        'quantity_a': quantity_a,
                        'quantity_b': quantity_b,
                        'dollar_a': dollar_a,  # Dollar amount allocated to asset A
                        'dollar_b': dollar_b,  # Dollar amount allocated to asset B
                        'trade_capital': trade_capital,  # Total capital used for this trade
                        'beta_used': current_beta,  # Beta used for this trade (rolling)
                        'alpha_used': current_alpha,  # Alpha used for this trade (rolling)
                    })
            
            elif signal in [TradeSignal.CLOSE_LONG, TradeSignal.CLOSE_SHORT]:
                # Close position
                if current_position and trades:
                    last_trade = trades[-1]
                    if 'exit_date' not in last_trade:
                        # Get beta/alpha that were used at entry (critical for correct P&L)
                        entry_beta = last_trade.get('beta_used', beta)
                        entry_alpha = last_trade.get('alpha_used', alpha)
                        
                        # Calculate spread at entry and exit using the SAME beta/alpha from entry
                        # This ensures we're measuring the actual spread change, not a different relationship
                        entry_spread_calc = entry_price_a - (entry_alpha + entry_beta * entry_price_b)
                        exit_spread_calc = price_a_val - (entry_alpha + entry_beta * price_b_val)
                        # IMPORTANT: spread_change = exit - entry (positive means spread increased)
                        spread_change = exit_spread_calc - entry_spread_calc
                        
                        # Calculate P&L using position sizes from entry
                        if current_position == 'long':
                            # Long spread: long A, short B
                            # Profit when spread INCREASES (returns to mean from negative values)
                            # Example: spread goes from -0.1 to 0 → spread increased → profit
                            pnl_a = (price_a_val - entry_price_a) * last_trade['quantity_a']
                            pnl_b = (entry_price_b - price_b_val) * last_trade['quantity_b']
                        else:  # short
                            # Short spread: short A, long B
                            # Profit when spread DECREASES (returns to mean from positive values)
                            # Example: spread goes from 0.1 to 0 → spread decreased → profit
                            pnl_a = (entry_price_a - price_a_val) * last_trade['quantity_a']
                            pnl_b = (price_b_val - entry_price_b) * last_trade['quantity_b']
                        
                        total_pnl = pnl_a + pnl_b
                        
                        # Apply transaction costs for exit
                        exit_notional = last_trade['dollar_a'] + last_trade['dollar_b']
                        exit_cost = exit_notional * self.transaction_cost_pct
                        total_pnl -= exit_cost
                        
                        # Calculate theoretical P&L based on spread change
                        # For a properly hedged position, P&L should be proportional to spread change
                        # LONG: profit when spread_change > 0 (spread increased)
                        # SHORT: profit when spread_change < 0 (spread decreased)
                        if current_position == 'long':
                            theoretical_pnl_from_spread = spread_change * last_trade['quantity_a']
                        else:  # short
                            theoretical_pnl_from_spread = -spread_change * last_trade['quantity_a']
                        
                        # Check if beta has drifted (calculate current beta at exit)
                        current_beta_at_exit, current_alpha_at_exit = calculate_rolling_beta_alpha(i, rolling_window=90)
                        beta_drift = abs(current_beta_at_exit - entry_beta) / entry_beta if entry_beta > 0 else 0
                        
                        # Diagnostic: Check if P&L direction matches spread change
                        # For LONG: spread should INCREASE (spread_change > 0) → P&L should be positive
                        # For SHORT: spread should DECREASE (spread_change < 0) → P&L should be positive
                        if current_position == 'long':
                            # Long position: spread increased → should be profitable
                            if spread_change > 0.01 and total_pnl < -10:  # Significant spread increase but loss
                                logger.warning(f"LONG trade - Spread increased by {spread_change:.4f} but P&L is {total_pnl:.2f}. "
                                             f"Entry: spread={entry_spread_calc:.4f}, z-score={entry_zscore:.2f}. "
                                             f"Exit: spread={exit_spread_calc:.4f}, z-score={zscore_val:.2f}. "
                                             f"Beta drift: {beta_drift*100:.2f}%. "
                                             f"Possible cause: Beta drift or non-linear relationship between assets")
                        else:  # short
                            # Short position: spread decreased → should be profitable
                            if spread_change < -0.01 and total_pnl < -10:  # Significant spread decrease but loss
                                logger.warning(f"SHORT trade - Spread decreased by {abs(spread_change):.4f} but P&L is {total_pnl:.2f}. "
                                             f"Entry: spread={entry_spread_calc:.4f}, z-score={entry_zscore:.2f}. "
                                             f"Exit: spread={exit_spread_calc:.4f}, z-score={zscore_val:.2f}. "
                                             f"Beta drift: {beta_drift*100:.2f}%. "
                                             f"Possible cause: Beta drift or non-linear relationship between assets")
                        # Update capital: add P&L to the capital
                        # The position used position_size_pct of capital, so we add the full P&L
                        capital += total_pnl
                        
                        # Determine exit reason based on signal generation logic
                        exit_reason = 'unknown'
                        exit_reason_detail = ''
                        
                        # Calculate P&L percentage
                        pnl_pct = (total_pnl / self.initial_capital) * 100
                        
                        # Check what triggered the exit
                        if strategy.stop_loss is not None:
                            if strategy.stop_loss_type == 'percent' and pnl_pct <= -strategy.stop_loss:
                                exit_reason = 'stop_loss'
                                exit_reason_detail = f'Stop loss (percent): {pnl_pct:.2f}% <= -{strategy.stop_loss}%'
                            elif strategy.stop_loss_type == 'zscore':
                                if (current_position == 'long' and zscore_val >= strategy.stop_loss) or \
                                   (current_position == 'short' and zscore_val <= -strategy.stop_loss):
                                    exit_reason = 'stop_loss'
                                    exit_reason_detail = f'Stop loss (z-score): {zscore_val:.2f}'
                            elif strategy.stop_loss_type == 'atr' and current_atr:
                                spread_change_atr = abs(spread_val - entry_spread)
                                if spread_change_atr >= strategy.stop_loss * current_atr:
                                    exit_reason = 'stop_loss'
                                    exit_reason_detail = f'Stop loss (ATR): spread change {spread_change_atr:.4f} >= {strategy.stop_loss} * ATR'
                        
                        if exit_reason == 'unknown' and strategy.take_profit is not None:
                            if strategy.take_profit_type == 'percent' and pnl_pct >= strategy.take_profit:
                                exit_reason = 'take_profit'
                                exit_reason_detail = f'Take profit (percent): {pnl_pct:.2f}% >= +{strategy.take_profit}%'
                            elif strategy.take_profit_type == 'zscore':
                                entry_z_for_tp = float(last_trade.get('entry_zscore', 0.0))
                                target_z = calc_zscore_take_profit_target(entry_z_for_tp, float(strategy.take_profit))
                                if (current_position == 'long' and zscore_val >= target_z) or \
                                   (current_position == 'short' and zscore_val <= target_z):
                                    exit_reason = 'take_profit'
                                    exit_reason_detail = f'Take profit (z-score): {zscore_val:.2f} reached target {target_z:.2f}'
                            elif strategy.take_profit_type == 'atr' and current_atr:
                                if current_position == 'long':
                                    spread_change_tp = spread_val - entry_spread
                                else:
                                    spread_change_tp = entry_spread - spread_val
                                if spread_change_tp >= strategy.take_profit * current_atr:
                                    exit_reason = 'take_profit'
                                    exit_reason_detail = f'Take profit (ATR): spread change {spread_change_tp:.4f} >= {strategy.take_profit} * ATR'
                        
                        # Detailed logging for every closed trade
                        entry_zscore = last_trade.get('entry_zscore', 0)
                        days_held = (date - last_trade['entry_date']).days if isinstance(date, pd.Timestamp) else 0
                        
                        # LONG profits when spread increases (spread_change > 0)
                        # SHORT profits when spread decreases (spread_change < 0)
                        expected_profit = (current_position == 'long' and spread_change > 0) or (current_position == 'short' and spread_change < 0)
                        logger.debug(f"TRADE CLOSED ({current_position.upper()}): Entry={last_trade['entry_date']}, Exit={date}, "
                                    f"Days Held={days_held}, Exit Reason={exit_reason} - {exit_reason_detail}, "
                                    f"Z-Score: {entry_zscore:.4f} → {zscore_val:.4f}, "
                                    f"Total P&L: ${total_pnl:.2f} ({(total_pnl / self.initial_capital) * 100:.2f}%), "
                                    f"Beta drift: {beta_drift*100:.2f}%")
                        if abs(total_pnl - theoretical_pnl_from_spread) > 50:  # Significant difference
                            logger.warning(f"P&L mismatch: Actual ${total_pnl:.2f} vs Theoretical ${theoretical_pnl_from_spread:.2f} "
                                         f"(diff: ${total_pnl - theoretical_pnl_from_spread:.2f})")
                        
                        last_trade.update({
                            'exit_date': date,
                            'exit_price_a': price_a_val,
                            'exit_price_b': price_b_val,
                            'exit_zscore': zscore_val,
                            'exit_reason': exit_reason,
                            'exit_reason_detail': exit_reason_detail,
                            'pnl': total_pnl,
                            'pnl_pct': (total_pnl / self.initial_capital) * 100,
                            'max_adverse_excursion': max_adverse_excursion,  # Maximum drawdown during hold
                            'mae_pct': (max_adverse_excursion / last_trade['trade_capital']) * 100,  # MAE as percentage of trade capital
                            'entry_spread_calc': entry_spread_calc,  # Spread at entry (using entry beta/alpha)
                            'exit_spread_calc': exit_spread_calc,  # Spread at exit (using entry beta/alpha)
                            'spread_change': spread_change,  # Change in spread
                            'pnl_a': pnl_a,  # P&L from asset A
                            'pnl_b': pnl_b,  # P&L from asset B
                            'theoretical_pnl_from_spread': theoretical_pnl_from_spread,  # Theoretical P&L based on spread change
                            'beta_at_exit': current_beta_at_exit,  # Beta at exit (for drift analysis)
                            'alpha_at_exit': current_alpha_at_exit,  # Alpha at exit
                            'beta_drift': beta_drift,  # Percentage change in beta from entry to exit
                        })
                        
                        current_position = None
                        entry_price_a = None
                        entry_price_b = None
                        entry_zscore = None
                        entry_spread = None
                        max_adverse_excursion = 0.0  # Reset MAE after closing position
            
            equity_curve.append(capital)
        
        # Close any open position at the end (only if it would be profitable)
        # This prevents forced closing at a loss when stop loss is not set
        if current_position and trades:
            last_trade = trades[-1]
            if 'exit_date' not in last_trade:
                final_date = aligned.index[-1]
                final_price_a = aligned.iloc[-1]['a']
                final_price_b = aligned.iloc[-1]['b']
                # Use the last calculated rolling z-score
                final_zscore = rolling_zscore_list[-1] if rolling_zscore_list else 0.0
                
                # Get beta/alpha that were used at entry
                entry_beta = last_trade.get('beta_used', beta)
                entry_alpha = last_trade.get('alpha_used', alpha)
                
                # Calculate spread at entry and exit using the SAME beta/alpha
                entry_spread_calc = entry_price_a - (entry_alpha + entry_beta * entry_price_b)
                exit_spread_calc = final_price_a - (entry_alpha + entry_beta * final_price_b)
                # IMPORTANT: spread_change = exit - entry (positive means spread increased)
                spread_change = exit_spread_calc - entry_spread_calc
                
                if current_position == 'long':
                    pnl_a = (final_price_a - entry_price_a) * last_trade['quantity_a']
                    pnl_b = (entry_price_b - final_price_b) * last_trade['quantity_b']
                else:
                    pnl_a = (entry_price_a - final_price_a) * last_trade['quantity_a']
                    pnl_b = (final_price_b - entry_price_b) * last_trade['quantity_b']
                
                total_pnl = pnl_a + pnl_b
                
                # Apply transaction costs for exit
                exit_notional = last_trade['dollar_a'] + last_trade['dollar_b']
                exit_cost = exit_notional * self.transaction_cost_pct
                total_pnl -= exit_cost
                
                # Calculate theoretical P&L and beta drift (same as in regular exit)
                # LONG: profit when spread_change > 0 (spread increased)
                # SHORT: profit when spread_change < 0 (spread decreased)
                if current_position == 'long':
                    theoretical_pnl_from_spread = spread_change * last_trade['quantity_a']
                else:  # short
                    theoretical_pnl_from_spread = -spread_change * last_trade['quantity_a']
                # Calculate current beta at final date (use last index)
                current_beta_at_exit, current_alpha_at_exit = calculate_rolling_beta_alpha(len(aligned) - 1, rolling_window=90)
                beta_drift = abs(current_beta_at_exit - entry_beta) / entry_beta if entry_beta > 0 else 0
                
                # Decide whether to close position at end of period
                should_close = False
                
                # Check if take profit conditions are met
                if strategy.take_profit is not None:
                    if strategy.take_profit_type == 'zscore':
                        # For z-score take profit, only close if target z-score is reached
                        entry_z_for_tp = float(last_trade.get('entry_zscore', 0.0))
                        target_z = calc_zscore_take_profit_target(entry_z_for_tp, float(strategy.take_profit))
                        if current_position == 'long' and final_zscore >= target_z:
                            should_close = True
                        elif current_position == 'short' and final_zscore <= target_z:
                            should_close = True
                    else:
                        # For percent/ATR take profit, close if profitable
                        if total_pnl > 0:
                            should_close = True
                else:
                    # No take profit set, close if profitable
                    if total_pnl > 0:
                        should_close = True
                
                # Always close if stop loss is set (to limit losses)
                if strategy.stop_loss is not None and total_pnl < 0:
                    should_close = True
                
                if should_close:
                    capital += total_pnl
                    last_trade.update({
                        'exit_date': final_date,
                        'exit_price_a': final_price_a,
                        'exit_price_b': final_price_b,
                        'exit_zscore': final_zscore,
                        'exit_reason': 'end_of_period',
                        'pnl': total_pnl,
                        'pnl_pct': (total_pnl / self.initial_capital) * 100,
                        'max_adverse_excursion': max_adverse_excursion,  # Maximum drawdown during hold
                        'mae_pct': (max_adverse_excursion / last_trade['trade_capital']) * 100,  # MAE as percentage of trade capital
                        'entry_spread_calc': entry_spread_calc,
                        'exit_spread_calc': exit_spread_calc,
                        'spread_change': spread_change,
                        'pnl_a': pnl_a,
                        'pnl_b': pnl_b,
                        'theoretical_pnl_from_spread': theoretical_pnl_from_spread,
                        'beta_at_exit': current_beta_at_exit,
                        'alpha_at_exit': current_alpha_at_exit,
                        'beta_drift': beta_drift,
                    })
                    equity_curve[-1] = capital
                else:
                    # Keep position open - take profit target not reached
                    unrealized_pnl_pct = (total_pnl / last_trade['trade_capital']) * 100
                    
                    # Explain why position is still open
                    open_reason = 'open_at_end'
                    if strategy.take_profit_type == 'zscore':
                        entry_z_for_tp = float(last_trade.get('entry_zscore', 0.0))
                        target_z = calc_zscore_take_profit_target(entry_z_for_tp, float(strategy.take_profit)) if strategy.take_profit is not None else 0.0
                        if current_position == 'long':
                            open_reason = f'open_at_end - z-score target not reached (current: {final_zscore:.2f}, target: >= {target_z:.2f})'
                        else:
                            open_reason = f'open_at_end - z-score target not reached (current: {final_zscore:.2f}, target: <= {target_z:.2f})'
                    
                    last_trade.update({
                        'exit_date': None,
                        'exit_reason': open_reason,
                        'pnl': None,
                        'pnl_pct': None,
                        'unrealized_pnl': total_pnl,  # Unrealized P&L
                        'unrealized_pnl_pct': unrealized_pnl_pct,
                        'max_adverse_excursion': max_adverse_excursion,  # MAE even for open positions
                        'mae_pct': (max_adverse_excursion / last_trade['trade_capital']) * 100,
                        'current_zscore': final_zscore
                    })
                    # Don't update capital - position still open
                    logger.warning(f"Position still OPEN at end of backtest period: Type={current_position.upper()}, "
                                 f"Entry={last_trade['entry_date']}, z-score: {last_trade['entry_zscore']:.2f} → {final_zscore:.2f}, "
                                 f"Unrealized P&L: ${total_pnl:.2f} ({unrealized_pnl_pct:.2f}%)")
        
        # Calculate metrics
        equity_series = pd.Series(equity_curve, index=aligned.index[:len(equity_curve)])
        returns = equity_series.pct_change().dropna()
        
        # Basic metrics
        sharpe_ratio = BacktestMetrics.calculate_sharpe_ratio(returns)
        max_drawdown = BacktestMetrics.calculate_max_drawdown(equity_series)
        win_rate = BacktestMetrics.calculate_win_rate(trades)
        
        # Calculate MAE metrics
        mae_metrics = BacktestMetrics.calculate_mae_metrics(trades)
        total_return = BacktestMetrics.calculate_total_return(equity_series)
        
        # Calculate Return/MAE Ratio (alternative to Sharpe using MAE as risk measure)
        return_to_mae_ratio = BacktestMetrics.calculate_return_to_mae_ratio(
            total_return=total_return,
            avg_mae_pct=mae_metrics['avg_mae_pct']
        )
        
        # Calculate rebalancing metrics
        total_rebalances = sum(len(t.get('rebalances', [])) for t in trades)
        avg_rebalances_per_trade = total_rebalances / max(1, len([t for t in trades if 'exit_date' in t]))
        
        metrics = {
            'total_trades': len([t for t in trades if 'exit_date' in t]),
            'win_rate': win_rate,
            'total_return': total_return,
            'sharpe_ratio': sharpe_ratio,
            'max_drawdown': max_drawdown,
            'profit_factor': BacktestMetrics.calculate_profit_factor(trades),
            'avg_mae': mae_metrics['avg_mae'],
            'max_mae': mae_metrics['max_mae'],
            'avg_mae_pct': mae_metrics['avg_mae_pct'],
            'max_mae_pct': mae_metrics['max_mae_pct'],
            'return_to_mae_ratio': return_to_mae_ratio,
            'rebalancing_enabled': strategy.enable_rebalancing,
            'total_rebalances': total_rebalances,
            'avg_rebalances_per_trade': avg_rebalances_per_trade,
            'total_rebalancing_costs': total_rebalancing_costs,
            'rebalancing_cost_pct': (total_rebalancing_costs / self.initial_capital) * 100 if self.initial_capital > 0 else 0,
            'final_capital': capital,
            'initial_capital': self.initial_capital
        }
        
        # Calculate leverage recommendations
        leverage_info = BacktestMetrics.calculate_optimal_leverage(
            sharpe_ratio=sharpe_ratio,
            max_drawdown=max_drawdown
        )
        metrics['leverage'] = leverage_info
        
        # Calculate Kelly Criterion
        closed_trades = [t for t in trades if t.get('pnl') is not None]
        if closed_trades:
            winning_trades = [t['pnl'] for t in closed_trades if t.get('pnl', 0) > 0]
            losing_trades = [t['pnl'] for t in closed_trades if t.get('pnl', 0) < 0]
            
            if winning_trades and losing_trades:
                avg_win = np.mean(winning_trades)
                avg_loss = abs(np.mean(losing_trades))
                kelly_pct = BacktestMetrics.calculate_kelly_criterion(
                    win_rate=win_rate,
                    avg_win=avg_win,
                    avg_loss=avg_loss
                )
                metrics['kelly_percentage'] = kelly_pct
                metrics['kelly_details'] = {
                    'avg_win': round(avg_win, 2),
                    'avg_loss': round(avg_loss, 2),
                    'win_loss_ratio': round(avg_win / avg_loss, 2) if avg_loss > 0 else 0.0
                }
            else:
                metrics['kelly_percentage'] = None
        else:
            metrics['kelly_percentage'] = None
        
        # Clean results to remove inf/nan values and convert Timestamp to strings for JSON serialization
        def clean_for_json(obj):
            """Recursively clean inf/nan values and convert Timestamp to ISO strings for JSON serialization"""
            if isinstance(obj, dict):
                return {k: clean_for_json(v) for k, v in obj.items()}
            elif isinstance(obj, (list, tuple)):
                return [clean_for_json(item) for item in obj]
            elif isinstance(obj, pd.Timestamp):
                # Convert pandas Timestamp to ISO format string
                return obj.isoformat()
            elif isinstance(obj, (float, np.floating)):
                if np.isinf(obj) or np.isnan(obj):
                    return None if np.isnan(obj) else (999999.0 if obj > 0 else -999999.0)
                return float(obj)
            elif isinstance(obj, (int, np.integer)):
                return int(obj)
            else:
                return obj
        
        # Convert rolling z-score to pandas Series for chart
        rolling_zscore_series = pd.Series(rolling_zscore_list, index=rolling_dates_list)
        
        results = {
            'asset_a': asset_a,
            'asset_b': asset_b,
            'beta': beta,
            'trades': trades,
            'equity_curve': equity_curve,
            'equity_dates': [d.isoformat() if hasattr(d, 'isoformat') else str(d) for d in aligned.index[:len(equity_curve)]],
            'zscore': rolling_zscore_list,  # Rolling z-score for chart (matches trading logic)
            'zscore_dates': [d.isoformat() if hasattr(d, 'isoformat') else str(d) for d in rolling_dates_list],
            'metrics': metrics
        }
        
        return clean_for_json(results)

