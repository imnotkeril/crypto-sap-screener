import React from 'react';
import { useQuery } from '@tanstack/react-query';
import { LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, ReferenceLine, Scatter, ComposedChart } from 'recharts';
import { api } from '../services/api';

interface BacktestResultsProps {
  sessionId: number;
}

const BacktestResults: React.FC<BacktestResultsProps> = ({ sessionId }) => {
  const { data, isLoading } = useQuery({
    queryKey: ['backtest-results', sessionId],
    queryFn: () => api.getBacktestResults(sessionId),
  });

  if (isLoading) {
    return <div className="text-center text-gray-400 py-8">Loading results...</div>;
  }

  if (!data) {
    return <div className="text-center text-gray-400 py-8">No results found</div>;
  }

  const metrics = data.metrics || {};
  const trades = data.trades || [];
  
  const equityData = (data.equity_curve || []).map((equity: number, idx: number) => ({
    date: data.equity_dates?.[idx] || idx,
    equity,
  }));
  
  // Helper function to normalize date strings for comparison
  const normalizeDateString = (dateStr: string) => {
    try {
      const date = new Date(dateStr);
      return date.toISOString(); // Full ISO format for exact matching
    } catch {
      return dateStr;
    }
  };

  // Create a map of trade entry/exit points by date for efficient lookup
  const tradePointsByDate = new Map<string, any>();
  
  trades.forEach((trade: any) => {
    // Entry points
    if (trade.entry_date && trade.entry_zscore !== undefined) {
      const normalizedDate = normalizeDateString(trade.entry_date);
      const isLong = trade.entry_signal?.includes('long');
      
      if (!tradePointsByDate.has(normalizedDate)) {
        tradePointsByDate.set(normalizedDate, {});
      }
      
      const point = tradePointsByDate.get(normalizedDate);
      if (isLong) {
        point.longEntry = trade.entry_zscore;
      } else {
        point.shortEntry = trade.entry_zscore;
      }
    }
    
    // Exit points
    if (trade.exit_date && trade.exit_zscore !== undefined) {
      const normalizedDate = normalizeDateString(trade.exit_date);
      
      if (!tradePointsByDate.has(normalizedDate)) {
        tradePointsByDate.set(normalizedDate, {});
      }
      
      const point = tradePointsByDate.get(normalizedDate);
      point.exit = trade.exit_zscore;
    }
  });

  // Rolling Z-Score data from backtest (matches actual trading logic)
  // Merge with entry/exit points for scatter plot
  const rollingZscoreData = (data.zscore || []).map((zscore: number, idx: number) => {
    const date = data.zscore_dates?.[idx] || idx;
    const normalizedDate = normalizeDateString(date);
    const tradePoint = tradePointsByDate.get(normalizedDate);
    
    return {
      date,
      zscore,
      longEntry: tradePoint?.longEntry || null,
      shortEntry: tradePoint?.shortEntry || null,
      exit: tradePoint?.exit || null,
    };
  });

  // Calculate dynamic Y-axis range: min - 10% below, max + 10% above
  const equityValues = equityData.map((d: any) => d.equity).filter((v: number) => !isNaN(v) && v > 0);
  const minEquity = Math.min(...equityValues);
  const maxEquity = Math.max(...equityValues);
  const range = maxEquity - minEquity;
  const yAxisMin = Math.max(0, minEquity - range * 0.1); // 10% below min, but not negative
  const yAxisMax = maxEquity + range * 0.1; // 10% above max

  return (
    <div className="space-y-6">
      <div className="grid grid-cols-2 md:grid-cols-4 lg:grid-cols-5 gap-4">
        <div className="bg-[#0a0a0f] border border-[#1a1a24] rounded-lg p-3">
          <div className="text-xs text-gray-400 mb-1">Total Return</div>
          <div className={`text-lg font-medium ${metrics.total_return >= 0 ? 'text-emerald-400' : 'text-red-400'}`}>
            {metrics.total_return?.toFixed(2)}%
          </div>
        </div>
        <div className="bg-[#0a0a0f] border border-[#1a1a24] rounded-lg p-3">
          <div className="text-xs text-gray-400 mb-1">Sharpe Ratio</div>
          <div className="text-lg font-medium text-white">{metrics.sharpe_ratio?.toFixed(2)}</div>
        </div>
        <div className="bg-[#0a0a0f] border border-[#1a1a24] rounded-lg p-3">
          <div className="text-xs text-gray-400 mb-1">Return/MAE Ratio</div>
          <div className="text-lg font-medium text-cyan-400" title="Return per unit of Maximum Adverse Excursion - higher is better">
            {metrics.return_to_mae_ratio?.toFixed(2) || '0.00'}
          </div>
        </div>
        <div className="bg-[#0a0a0f] border border-[#1a1a24] rounded-lg p-3">
          <div className="text-xs text-gray-400 mb-1">Max Drawdown</div>
          <div className="text-lg font-medium text-red-400">{metrics.max_drawdown?.toFixed(2)}%</div>
        </div>
        <div className="bg-[#0a0a0f] border border-[#1a1a24] rounded-lg p-3">
          <div className="text-xs text-gray-400 mb-1">Win Rate</div>
          <div className="text-lg font-medium text-white">{metrics.win_rate?.toFixed(2)}%</div>
        </div>
      </div>

      {/* MAE (Maximum Adverse Excursion) Metrics */}
      {(metrics.avg_mae !== undefined || metrics.max_mae !== undefined) && (
        <div className="bg-[#0a0a0f] border border-[#1a1a24] rounded-lg p-4">
          <h3 className="text-lg font-semibold text-white mb-3">Maximum Adverse Excursion (MAE)</h3>
          <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
            <div>
              <p className="text-xs text-gray-400 mb-1">Avg MAE</p>
              <p className="text-xl font-bold text-orange-400">
                ${metrics.avg_mae?.toFixed(2) || '0.00'}
              </p>
            </div>
            <div>
              <p className="text-xs text-gray-400 mb-1">Max MAE</p>
              <p className="text-xl font-bold text-red-400">
                ${metrics.max_mae?.toFixed(2) || '0.00'}
              </p>
            </div>
            <div>
              <p className="text-xs text-gray-400 mb-1">Avg MAE %</p>
              <p className="text-xl font-bold text-orange-400">
                {metrics.avg_mae_pct?.toFixed(2) || '0.00'}%
              </p>
            </div>
            <div>
              <p className="text-xs text-gray-400 mb-1">Max MAE %</p>
              <p className="text-xl font-bold text-red-400">
                {metrics.max_mae_pct?.toFixed(2) || '0.00'}%
              </p>
            </div>
          </div>
          <p className="text-xs text-gray-400 mt-3">
            MAE shows the worst unrealized drawdown experienced during each trade, even if the trade closed profitably. Lower MAE indicates less stress during position holding.
          </p>
        </div>
      )}

      {/* Dynamic Hedge Rebalancing Metrics */}
      {metrics.rebalancing_enabled && (
        <div className="bg-[#0a0a0f] border border-[#1a1a24] rounded-lg p-4">
          <h3 className="text-lg font-semibold text-white mb-3 flex items-center gap-2">
            🔄 Dynamic Hedge Rebalancing
            <span className="px-2 py-0.5 bg-blue-500/20 text-blue-400 text-xs rounded-full">ACTIVE</span>
          </h3>
          <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
            <div>
              <p className="text-xs text-gray-400 mb-1">Total Rebalances</p>
              <p className="text-xl font-bold text-blue-400">
                {metrics.total_rebalances || 0}
              </p>
            </div>
            <div>
              <p className="text-xs text-gray-400 mb-1">Avg per Trade</p>
              <p className="text-xl font-bold text-cyan-400">
                {metrics.avg_rebalances_per_trade?.toFixed(2) || '0.00'}
              </p>
            </div>
            <div>
              <p className="text-xs text-gray-400 mb-1">Total Cost</p>
              <p className="text-xl font-bold text-orange-400">
                ${metrics.total_rebalancing_costs?.toFixed(2) || '0.00'}
              </p>
            </div>
            <div>
              <p className="text-xs text-gray-400 mb-1">Cost %</p>
              <p className="text-xl font-bold text-red-400">
                {metrics.rebalancing_cost_pct?.toFixed(2) || '0.00'}%
              </p>
            </div>
          </div>
          <p className="text-xs text-gray-400 mt-3">
            Rebalancing adjusts hedge ratios during position holding to maintain proper beta hedging as market conditions change. This helps combat beta drift but incurs transaction costs.
          </p>
        </div>
      )}

      {/* Leverage and Kelly Recommendations */}
      {(metrics.leverage || metrics.kelly_percentage !== undefined) && (
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          {/* Leverage Recommendations */}
          {metrics.leverage && (
            <div className="bg-[#0a0a0f] border border-[#1a1a24] rounded-lg p-4">
              <h3 className="text-lg font-semibold text-white mb-3">Leverage Recommendations</h3>
              <div className="grid grid-cols-2 gap-4 mb-3">
                <div>
                  <p className="text-xs text-gray-400 mb-1">Optimal Leverage</p>
                  <p className="text-2xl font-bold text-emerald-400">
                    {metrics.leverage.optimal_leverage}x
                  </p>
                </div>
                <div>
                  <p className="text-xs text-gray-400 mb-1">Recommended (75%)</p>
                  <p className="text-2xl font-bold text-blue-400">
                    {metrics.leverage.recommended}x
                  </p>
                </div>
              </div>
              <div className="space-y-1 text-xs text-gray-500">
                <p>Sharpe-based: {metrics.leverage.sharpe_based}x</p>
                <p>Drawdown-based: {metrics.leverage.drawdown_based}x</p>
                <p className="text-gray-400 mt-2">
                  Sharpe ratio remains unchanged with leverage (returns and risk scale proportionally)
                </p>
              </div>
            </div>
          )}

          {/* Kelly Criterion */}
          {metrics.kelly_percentage !== undefined && metrics.kelly_percentage !== null && (
            <div className="bg-[#0a0a0f] border border-[#1a1a24] rounded-lg p-4">
              <h3 className="text-lg font-semibold text-white mb-3">Kelly Criterion</h3>
              <div className="mb-3">
                <p className="text-xs text-gray-400 mb-1">Optimal Position Size</p>
                <p className="text-2xl font-bold text-purple-400">
                  {metrics.kelly_percentage.toFixed(1)}%
                </p>
              </div>
              {metrics.kelly_details && (
                <div className="space-y-1 text-xs text-gray-500">
                  <p>Avg Win: ${metrics.kelly_details.avg_win.toFixed(2)}</p>
                  <p>Avg Loss: ${metrics.kelly_details.avg_loss.toFixed(2)}</p>
                  <p>Win/Loss Ratio: {metrics.kelly_details.win_loss_ratio.toFixed(2)}</p>
                </div>
              )}
              <p className="text-xs text-gray-400 mt-2">
                Optimal position size for maximizing long-term capital growth
              </p>
            </div>
          )}
        </div>
      )}

      <div className="bg-[#0a0a0f] border border-[#1a1a24] rounded-xl p-4">
        <h3 className="text-lg font-medium text-white mb-4">Equity Curve</h3>
        <ResponsiveContainer width="100%" height={300}>
          <LineChart data={equityData}>
            <CartesianGrid strokeDasharray="3 3" stroke="#2a2a34" />
            <XAxis 
              dataKey="date" 
              stroke="#6b7280"
              tickFormatter={(value) => {
                try {
                  const date = new Date(value);
                  return date.toLocaleDateString('en-US', { month: 'short', day: 'numeric' });
                } catch {
                  return value;
                }
              }}
            />
            <YAxis 
              stroke="#6b7280"
              domain={[yAxisMin, yAxisMax]}
              tickFormatter={(value) => value.toFixed(0)}
            />
            <Tooltip 
              contentStyle={{
                backgroundColor: '#1a1a24',
                border: '1px solid #2a2a34',
                borderRadius: '8px',
                color: '#e5e7eb'
              }}
              formatter={(value: any) => [value.toFixed(2), 'Equity']}
              labelFormatter={(label) => {
                try {
                  return new Date(label).toLocaleDateString('en-US');
                } catch {
                  return label;
                }
              }}
              labelStyle={{ color: '#9ca3af' }}
            />
            <Line type="monotone" dataKey="equity" stroke="#10b981" strokeWidth={2} dot={false} isAnimationActive={false} />
          </LineChart>
        </ResponsiveContainer>
      </div>

      {/* Rolling Z-Score Chart (Trading Signal) */}
      {rollingZscoreData.length > 0 && (
        <div className="bg-[#0a0a0f] border border-[#1a1a24] rounded-xl p-4">
          <div className="flex items-center justify-between mb-4">
            <h3 className="text-lg font-medium text-white">Rolling Z-Score (Trading Signal)</h3>
            <span className="text-xs text-gray-400 bg-[#1a1a24] px-3 py-1 rounded-full">
              60-day rolling window
            </span>
          </div>
          <ResponsiveContainer width="100%" height={300}>
            <ComposedChart data={rollingZscoreData}>
              <CartesianGrid strokeDasharray="3 3" stroke="#2a2a34" />
              <XAxis 
                dataKey="date" 
                stroke="#6b7280"
                tickFormatter={(value) => {
                  try {
                  const date = new Date(value);
                  return date.toLocaleDateString('en-US', { month: 'short', day: 'numeric' });
                  } catch {
                    return value;
                  }
                }}
              />
              <YAxis 
                stroke="#6b7280"
                domain={[-4, 4]}
                ticks={[-4, -3, -2, -1, 0, 1, 2, 3, 4]}
              />
              <Tooltip 
                contentStyle={{
                  backgroundColor: '#1a1a24',
                  border: '1px solid #2a2a34',
                  borderRadius: '8px',
                  color: '#e5e7eb'
                }}
                formatter={(value: any, name: string) => {
                  if (value === null || value === undefined) return null;
                  const formatted = typeof value === 'number' ? value.toFixed(2) : value;
                  if (name === 'Rolling Z-Score') return [formatted, 'Z-Score'];
                  if (name === 'LONG Entry') return [formatted, '🟢 LONG Entry'];
                  if (name === 'SHORT Entry') return [formatted, '🔴 SHORT Entry'];
                  if (name === 'Exit') return [formatted, '🟣 Exit'];
                  return [formatted, name];
                }}
                labelFormatter={(label) => {
                  try {
                    return new Date(label).toLocaleDateString('en-US', { month: 'short', day: 'numeric' });
                  } catch {
                    return label;
                  }
                }}
                labelStyle={{ color: '#9ca3af' }}
                animationDuration={0}
              />
              {/* Z-Score line */}
              <Line 
                type="monotone" 
                dataKey="zscore" 
                stroke="#3b82f6" 
                strokeWidth={2} 
                dot={false}
                name="Rolling Z-Score"
                isAnimationActive={false}
              />
              {/* Reference lines for entry/exit thresholds */}
              <ReferenceLine 
                y={2} 
                stroke="#ef4444" 
                strokeWidth={1} 
                strokeDasharray="5 5"
                label={{ value: '+2σ Entry', fill: '#ef4444', fontSize: 10, position: 'right' }}
              />
              <ReferenceLine 
                y={-2} 
                stroke="#ef4444" 
                strokeWidth={1} 
                strokeDasharray="5 5"
                label={{ value: '-2σ Entry', fill: '#ef4444', fontSize: 10, position: 'right' }}
              />
              <ReferenceLine 
                y={0} 
                stroke="#6b7280" 
                strokeWidth={1}
                label={{ value: 'Mean', fill: '#6b7280', fontSize: 10, position: 'right' }}
              />
              {/* Scatter plots for entry/exit points */}
              <Scatter 
                dataKey="longEntry" 
                fill="#10b981" 
                shape="circle"
                r={6}
                name="LONG Entry"
                isAnimationActive={false}
              />
              <Scatter 
                dataKey="shortEntry"
                fill="#ef4444" 
                shape="circle"
                r={6}
                name="SHORT Entry"
                isAnimationActive={false}
              />
              <Scatter 
                dataKey="exit"
                fill="#8b5cf6" 
                shape="diamond"
                r={7}
                name="Exit"
                isAnimationActive={false}
              />
            </ComposedChart>
          </ResponsiveContainer>
          <div className="flex items-center gap-4 mt-3 text-xs">
            <div className="flex items-center gap-1">
              <span className="inline-block w-3 h-3 rounded-full bg-emerald-500"></span>
              <span className="text-gray-400">LONG Entry</span>
            </div>
            <div className="flex items-center gap-1">
              <span className="inline-block w-3 h-3 rounded-full bg-red-500"></span>
              <span className="text-gray-400">SHORT Entry</span>
            </div>
            <div className="flex items-center gap-1">
              <span className="inline-block w-3 h-3 rotate-45 bg-purple-500"></span>
              <span className="text-gray-400">Exit</span>
            </div>
          </div>
          <p className="text-xs text-gray-400 mt-3">
            ⚡ This z-score matches the actual trading logic used by the backtester. 
            Entry signals: z-score ≥ ±2σ. Exit signals based on your settings (z-score return to mean, take profit, or stop loss).
          </p>
        </div>
      )}

      {trades.length > 0 && (
        <div className="bg-[#0a0a0f] border border-[#1a1a24] rounded-xl p-4">
          <h3 className="text-lg font-medium text-white mb-4">Trades ({trades.length})</h3>
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-[#1a1a24]">
                  <th className="text-left py-2 text-gray-400">Type</th>
                  <th className="text-left py-2 text-gray-400">Entry</th>
                  <th className="text-left py-2 text-gray-400">Exit</th>
                  <th className="text-right py-2 text-gray-400">Z-Score (Entry→Exit)</th>
                  <th className="text-right py-2 text-gray-400">Spread Δ</th>
                  <th className="text-right py-2 text-gray-400">Beta Drift</th>
                  <th className="text-right py-2 text-gray-400">P&L</th>
                  <th className="text-right py-2 text-gray-400">Return %</th>
                  <th className="text-right py-2 text-gray-400">MAE %</th>
                </tr>
              </thead>
              <tbody>
                {trades.slice(0, 20).map((trade: any, idx: number) => {
                  const tradeType = trade.entry_signal?.includes('long') ? 'LONG' : 'SHORT';
                  const zscoreChange = trade.exit_zscore ? (trade.exit_zscore - trade.entry_zscore) : null;
                  const betaDrift = trade.beta_drift ? (trade.beta_drift * 100) : 0;
                  
                  // Check if trade should be profitable based on spread change
                  const spreadChange = trade.spread_change || 0;
                  const shouldBeProfit = (tradeType === 'LONG' && spreadChange > 0) || (tradeType === 'SHORT' && spreadChange < 0);
                  const actualProfit = (trade.pnl || 0) > 0;
                  const hasMismatch = shouldBeProfit !== actualProfit && Math.abs(trade.pnl || 0) > 10;
                  
                  return (
                    <tr key={idx} className={`border-b border-[#1a1a24] ${hasMismatch ? 'bg-red-900 bg-opacity-10' : ''}`}>
                      <td className="py-2">
                        <span className={`px-2 py-1 rounded text-xs font-semibold ${
                          tradeType === 'LONG' ? 'bg-green-900 text-green-300' : 'bg-red-900 text-red-300'
                        }`}>
                          {tradeType}
                        </span>
                      </td>
                      <td className="py-2 text-white">
                        {new Date(trade.entry_date).toLocaleDateString()}
                      </td>
                      <td className="py-2 text-white">
                        {trade.exit_date ? new Date(trade.exit_date).toLocaleDateString() : 'Open'}
                      </td>
                      <td className="py-2 text-right text-gray-300">
                        {trade.entry_zscore?.toFixed(2)} → {trade.exit_zscore?.toFixed(2) || '?'}
                        {zscoreChange !== null && (
                          <span className={`ml-1 text-xs ${zscoreChange > 0 ? 'text-green-400' : 'text-red-400'}`}>
                            ({zscoreChange > 0 ? '+' : ''}{zscoreChange.toFixed(2)})
                          </span>
                        )}
                      </td>
                      <td className={`py-2 text-right ${spreadChange > 0 ? 'text-green-400' : 'text-red-400'}`}>
                        {spreadChange > 0 ? '+' : ''}{spreadChange?.toFixed(4) || '0.0000'}
                      </td>
                      <td className="py-2 text-right">
                        <span className={betaDrift > 10 ? 'text-yellow-400 font-semibold' : 'text-gray-400'}>
                          {betaDrift.toFixed(1)}%
                          {betaDrift > 10 && ' ⚠️'}
                        </span>
                      </td>
                      <td className={`py-2 text-right font-medium ${trade.pnl >= 0 ? 'text-emerald-400' : 'text-red-400'}`}>
                        {hasMismatch && '⚠️ '}${trade.pnl?.toFixed(2)}
                      </td>
                      <td className={`py-2 text-right ${trade.pnl_pct >= 0 ? 'text-emerald-400' : 'text-red-400'}`}>
                        {trade.pnl_pct?.toFixed(2)}%
                      </td>
                      <td className="py-2 text-right text-red-400">
                        {trade.mae_pct?.toFixed(2) || '0.00'}%
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
          
          {/* Legend for warnings */}
          <div className="mt-3 text-xs text-gray-400 space-y-1">
            <div>⚠️ = P&L direction doesn't match expected outcome based on spread change</div>
            <div>🟡 Beta Drift &gt; 10% = Hedge may be less effective due to changing relationship</div>
            <div>LONG Spread: Profit when spread increases (z-score moves from negative to zero)</div>
            <div>SHORT Spread: Profit when spread decreases (z-score moves from positive to zero)</div>
          </div>
        </div>
      )}
    </div>
  );
};

export default BacktestResults;

