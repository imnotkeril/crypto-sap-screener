import React, { useState } from 'react';
import { useMutation } from 'react-query';
import { PairResult, PairSpreadData, api } from '../services/api';
import BacktestResults from './BacktestResults';

interface BacktestSectionProps {
  pair: PairResult;
  spreadData: PairSpreadData;
}

type StopLossType = 'none' | 'zscore' | 'percent' | 'atr';

const BacktestSection: React.FC<BacktestSectionProps> = ({ pair }) => {
  const [showForm, setShowForm] = useState(false);
  const [showResults, setShowResults] = useState(false);
  const [sessionId, setSessionId] = useState<number | null>(null);
  
  const [formData, setFormData] = useState({
    entry_threshold: 2.0,
    stop_loss_type: 'none' as StopLossType,
    stop_loss_value: 5.0,
    take_profit_type: 'zscore' as StopLossType,
    take_profit_value: 0.0,
    initial_capital: 10000,
    position_size_pct: 100, // Use 100% of capital per trade
    lookback_days: 365,
    transaction_cost_pct: 0.001,
    enable_rebalancing: false,
    rebalancing_frequency_days: 5,
    rebalancing_threshold: 0.05,
  });

  const runBacktestMutation = useMutation(
    (data: any) => api.runBacktest(data),
    {
      onSuccess: (data) => {
        setSessionId(data.session_id);
        setShowResults(true);
        setShowForm(false);
      },
    }
  );

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    
    // Prepare request data
    const requestData: any = {
      asset_a: pair.asset_a,
      asset_b: pair.asset_b,
      entry_threshold: formData.entry_threshold,
      stop_loss: formData.stop_loss_type === 'none' ? null : formData.stop_loss_value,
      stop_loss_type: formData.stop_loss_type === 'none' ? 'percent' : formData.stop_loss_type,
      take_profit: formData.take_profit_value,
      take_profit_type: formData.take_profit_type,
      initial_capital: formData.initial_capital,
      position_size_pct: formData.position_size_pct,
      lookback_days: formData.lookback_days,
      beta: pair.beta, // Use beta from pair
      transaction_cost_pct: formData.transaction_cost_pct,
      enable_rebalancing: formData.enable_rebalancing,
      rebalancing_frequency_days: formData.rebalancing_frequency_days,
      rebalancing_threshold: formData.rebalancing_threshold,
    };

    runBacktestMutation.mutate(requestData);
  };

  return (
    <div className="bg-[#0a0a0f] border border-[#1a1a24] rounded-xl p-4">
      <div className="flex items-center justify-between mb-4">
        <div>
          <h3 className="text-lg font-medium text-white">Backtest Strategy</h3>
          <p className="text-xs text-gray-400 mt-1">
            Test trading strategy on historical data
          </p>
        </div>
        {!showForm && !showResults && (
          <button
            onClick={() => setShowForm(true)}
            className="px-4 py-2 bg-emerald-500 hover:bg-emerald-600 text-white font-medium rounded-lg transition-colors"
          >
            Run Backtest
          </button>
        )}
        {showForm && (
          <button
            onClick={() => {
              setShowForm(false);
              setShowResults(false);
            }}
            className="px-4 py-2 text-gray-400 hover:text-white transition-colors"
          >
            Cancel
          </button>
        )}
        {showResults && (
          <button
            onClick={() => {
              setShowResults(false);
              setSessionId(null);
            }}
            className="px-4 py-2 text-gray-400 hover:text-white transition-colors"
          >
            Close Results
          </button>
        )}
      </div>

      {showForm && (
        <form onSubmit={handleSubmit} className="space-y-4">
          <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
            {/* Entry Threshold */}
            <div>
              <label className="block text-sm font-medium text-gray-300 mb-2">
                Entry Threshold (Z-Score)
              </label>
              <div className="flex gap-2 mb-2">
                {[1.5, 2.0, 2.5, 3.0].map((val) => (
                  <button
                    key={val}
                    type="button"
                    onClick={() => setFormData({ ...formData, entry_threshold: val })}
                    className={`flex-1 px-3 py-2 rounded-lg transition-colors text-sm ${
                      formData.entry_threshold === val
                        ? 'bg-blue-500 text-white'
                        : 'bg-[#1a1a24] text-gray-300 hover:bg-[#2a2a34]'
                    }`}
                  >
                    {val}σ
                  </button>
                ))}
              </div>
              <input
                type="number"
                step="0.1"
                min="0.5"
                max="5.0"
                value={formData.entry_threshold}
                onChange={(e) => setFormData({ ...formData, entry_threshold: parseFloat(e.target.value) || 2.0 })}
                className="w-full px-4 py-2 bg-[#1a1a24] border border-[#2a2a34] rounded-lg text-white"
              />
              <p className="mt-1 text-xs text-gray-400">
                Enter when |z-score| ≥ threshold
              </p>
            </div>

            {/* Stop Loss */}
            <div>
              <label className="block text-sm font-medium text-gray-300 mb-2">
                Stop Loss
              </label>
              <div className="grid grid-cols-4 gap-1 mb-2">
                <button
                  type="button"
                  onClick={() => setFormData({ ...formData, stop_loss_type: 'none' })}
                  className={`px-2 py-2 rounded-lg transition-colors text-xs ${
                    formData.stop_loss_type === 'none'
                      ? 'bg-red-500 text-white'
                      : 'bg-[#1a1a24] text-gray-300 hover:bg-[#2a2a34]'
                  }`}
                >
                  None
                </button>
                <button
                  type="button"
                  onClick={() => setFormData({ ...formData, stop_loss_type: 'zscore' })}
                  className={`px-2 py-2 rounded-lg transition-colors text-xs ${
                    formData.stop_loss_type === 'zscore'
                      ? 'bg-red-500 text-white'
                      : 'bg-[#1a1a24] text-gray-300 hover:bg-[#2a2a34]'
                  }`}
                >
                  Z-Score
                </button>
                <button
                  type="button"
                  onClick={() => setFormData({ ...formData, stop_loss_type: 'percent' })}
                  className={`px-2 py-2 rounded-lg transition-colors text-xs ${
                    formData.stop_loss_type === 'percent'
                      ? 'bg-red-500 text-white'
                      : 'bg-[#1a1a24] text-gray-300 hover:bg-[#2a2a34]'
                  }`}
                >
                  %
                </button>
                <button
                  type="button"
                  onClick={() => setFormData({ ...formData, stop_loss_type: 'atr' })}
                  className={`px-2 py-2 rounded-lg transition-colors text-xs ${
                    formData.stop_loss_type === 'atr'
                      ? 'bg-red-500 text-white'
                      : 'bg-[#1a1a24] text-gray-300 hover:bg-[#2a2a34]'
                  }`}
                >
                  ATR
                </button>
              </div>
              <input
                type="number"
                step="0.1"
                min="0"
                value={formData.stop_loss_value}
                onChange={(e) => setFormData({ ...formData, stop_loss_value: parseFloat(e.target.value) || 0 })}
                disabled={formData.stop_loss_type === 'none'}
                className="w-full px-4 py-2 bg-[#1a1a24] border border-[#2a2a34] rounded-lg text-white disabled:opacity-50"
              />
              <p className="mt-1 text-xs text-gray-400">
                {formData.stop_loss_type === 'none' && 'No stop loss'}
                {formData.stop_loss_type === 'percent' && `Exit at -${formData.stop_loss_value}% loss`}
                {formData.stop_loss_type === 'zscore' && `Exit at ${formData.stop_loss_value}σ against`}
                {formData.stop_loss_type === 'atr' && `Exit at ${formData.stop_loss_value}× ATR`}
              </p>
            </div>

            {/* Take Profit */}
            <div>
              <label className="block text-sm font-medium text-gray-300 mb-2">
                Take Profit
              </label>
              <div className="grid grid-cols-3 gap-1 mb-2">
                <button
                  type="button"
                  onClick={() => setFormData({ ...formData, take_profit_type: 'zscore' })}
                  className={`px-2 py-2 rounded-lg transition-colors text-xs ${
                    formData.take_profit_type === 'zscore'
                      ? 'bg-emerald-500 text-white'
                      : 'bg-[#1a1a24] text-gray-300 hover:bg-[#2a2a34]'
                  }`}
                >
                  Z-Score
                </button>
                <button
                  type="button"
                  onClick={() => setFormData({ ...formData, take_profit_type: 'percent' })}
                  className={`px-2 py-2 rounded-lg transition-colors text-xs ${
                    formData.take_profit_type === 'percent'
                      ? 'bg-emerald-500 text-white'
                      : 'bg-[#1a1a24] text-gray-300 hover:bg-[#2a2a34]'
                  }`}
                >
                  %
                </button>
                <button
                  type="button"
                  onClick={() => setFormData({ ...formData, take_profit_type: 'atr' })}
                  className={`px-2 py-2 rounded-lg transition-colors text-xs ${
                    formData.take_profit_type === 'atr'
                      ? 'bg-emerald-500 text-white'
                      : 'bg-[#1a1a24] text-gray-300 hover:bg-[#2a2a34]'
                  }`}
                >
                  ATR
                </button>
              </div>
              <input
                type="number"
                step={formData.take_profit_type === 'zscore' ? '0.1' : '0.5'}
                min={formData.take_profit_type === 'zscore' ? '-3' : '0'}
                max={formData.take_profit_type === 'zscore' ? '3' : '100'}
                value={formData.take_profit_value}
                onChange={(e) => setFormData({ ...formData, take_profit_value: parseFloat(e.target.value) || 0 })}
                className="w-full px-4 py-2 bg-[#1a1a24] border border-[#2a2a34] rounded-lg text-white"
              />
              <p className="mt-1 text-xs text-gray-400">
                {formData.take_profit_type === 'percent' && `Exit at +${formData.take_profit_value}% profit`}
                {formData.take_profit_type === 'zscore' && (
                  formData.take_profit_value === 0
                    ? `Exit at mean (0σ): LONG z≥0, SHORT z≤0`
                    : formData.take_profit_value > 0
                      ? `Exit on opposite side after crossing 0: LONG z≥+${Math.abs(formData.take_profit_value)}, SHORT z≤-${Math.abs(formData.take_profit_value)}`
                      : `Exit on same side before reaching 0: LONG z≥${formData.take_profit_value}, SHORT z≤+${Math.abs(formData.take_profit_value)}`
                )}
                {formData.take_profit_type === 'atr' && `Exit at ${formData.take_profit_value}× ATR`}
              </p>
            </div>
          </div>

          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
            {/* Initial Capital */}
            <div>
              <label className="block text-sm font-medium text-gray-300 mb-2">
                Initial Capital (USD)
              </label>
              <input
                type="number"
                min="100"
                step="100"
                value={formData.initial_capital}
                onChange={(e) => setFormData({ ...formData, initial_capital: parseFloat(e.target.value) || 10000 })}
                className="w-full px-4 py-2 bg-[#1a1a24] border border-[#2a2a34] rounded-lg text-white"
              />
            </div>

            {/* Position Size Percentage */}
            <div>
              <label className="block text-sm font-medium text-gray-300 mb-2">
                Position Size (% of Capital)
              </label>
              <div className="flex gap-1 mb-2">
                {[25, 50, 75, 100].map((pct) => (
                  <button
                    key={pct}
                    type="button"
                    onClick={() => setFormData({ ...formData, position_size_pct: pct })}
                    className={`flex-1 px-2 py-1 rounded-lg transition-colors text-xs ${
                      formData.position_size_pct === pct
                        ? 'bg-blue-500 text-white'
                        : 'bg-[#1a1a24] text-gray-300 hover:bg-[#2a2a34]'
                    }`}
                  >
                    {pct}%
                  </button>
                ))}
              </div>
              <input
                type="number"
                min="1"
                max="100"
                step="1"
                value={formData.position_size_pct}
                onChange={(e) => {
                  const value = parseFloat(e.target.value);
                  if (!isNaN(value) && value >= 1 && value <= 100) {
                    setFormData({ ...formData, position_size_pct: value });
                  }
                }}
                className="w-full px-4 py-2 bg-[#1a1a24] border border-[#2a2a34] rounded-lg text-white"
              />
            </div>

            {/* Lookback Days */}
            <div>
              <label className="block text-sm font-medium text-gray-300 mb-2">
                Lookback Period (Days)
              </label>
              <div className="flex gap-1 mb-2">
                {[90, 180, 365, 730].map((days) => (
                  <button
                    key={days}
                    type="button"
                    onClick={() => setFormData({ ...formData, lookback_days: days })}
                    className={`flex-1 px-2 py-1 rounded-lg transition-colors text-xs ${
                      formData.lookback_days === days
                        ? 'bg-blue-500 text-white'
                        : 'bg-[#1a1a24] text-gray-300 hover:bg-[#2a2a34]'
                    }`}
                  >
                    {days}d
                  </button>
                ))}
              </div>
              <input
                type="number"
                min="50"
                max="1000"
                step="1"
                value={formData.lookback_days}
                onChange={(e) => {
                  const value = parseInt(e.target.value);
                  if (!isNaN(value) && value >= 50 && value <= 1000) {
                    setFormData({ ...formData, lookback_days: value });
                  }
                }}
                className="w-full px-4 py-2 bg-[#1a1a24] border border-[#2a2a34] rounded-lg text-white"
              />
            </div>

            {/* Transaction Cost */}
            <div>
              <label className="block text-sm font-medium text-gray-300 mb-2">
                Transaction Cost (%)
              </label>
              <div className="flex gap-1 mb-2">
                {[0.05, 0.10, 0.20, 0.50].map((cost) => (
                  <button
                    key={cost}
                    type="button"
                    onClick={() => setFormData({ ...formData, transaction_cost_pct: cost / 100 })}
                    className={`flex-1 px-2 py-1 rounded-lg transition-colors text-xs ${
                      formData.transaction_cost_pct === cost / 100
                        ? 'bg-blue-500 text-white'
                        : 'bg-[#1a1a24] text-gray-300 hover:bg-[#2a2a34]'
                    }`}
                  >
                    {cost.toFixed(2)}%
                  </button>
                ))}
              </div>
              <input
                type="number"
                min="0.0001"
                max="0.01"
                step="0.0001"
                value={formData.transaction_cost_pct}
                onChange={(e) => setFormData({ ...formData, transaction_cost_pct: parseFloat(e.target.value) || 0.001 })}
                className="w-full px-4 py-2 bg-[#1a1a24] border border-[#2a2a34] rounded-lg text-white"
              />
            </div>
          </div>

          {/* Dynamic Hedge Rebalancing Section */}
          <div className="border border-[#2a2a34] rounded-lg p-4 bg-[#0d0d12]">
            <div className="flex items-center justify-between mb-3">
              <div>
                <label className="text-sm font-medium text-white flex items-center gap-2">
                  🔄 Dynamic Hedge Rebalancing
                  <span className="px-2 py-0.5 bg-blue-500/20 text-blue-400 text-xs rounded-full">EXPERIMENTAL</span>
                </label>
                <p className="text-xs text-gray-400 mt-1">
                  Automatically adjust hedge ratios during position holding to combat beta drift
                </p>
              </div>
              <label className="relative inline-flex items-center cursor-pointer">
                <input
                  type="checkbox"
                  checked={formData.enable_rebalancing}
                  onChange={(e) => setFormData({ ...formData, enable_rebalancing: e.target.checked })}
                  className="sr-only peer"
                />
                <div className="w-11 h-6 bg-gray-700 peer-focus:outline-none peer-focus:ring-2 peer-focus:ring-emerald-500 rounded-full peer peer-checked:after:translate-x-full peer-checked:after:border-white after:content-[''] after:absolute after:top-[2px] after:left-[2px] after:bg-white after:rounded-full after:h-5 after:w-5 after:transition-all peer-checked:bg-emerald-500"></div>
              </label>
            </div>

            {formData.enable_rebalancing && (
              <div className="grid grid-cols-1 md:grid-cols-2 gap-4 mt-3 pt-3 border-t border-[#2a2a34]">
                {/* Rebalancing Frequency */}
                <div>
                  <label className="block text-xs font-medium text-gray-300 mb-2">
                    Frequency (Days)
                  </label>
                  <div className="flex gap-1 mb-2">
                    {[3, 5, 7, 10].map((days) => (
                      <button
                        key={days}
                        type="button"
                        onClick={() => setFormData({ ...formData, rebalancing_frequency_days: days })}
                        className={`flex-1 px-2 py-1 rounded text-xs transition-colors ${
                          formData.rebalancing_frequency_days === days
                            ? 'bg-blue-500 text-white'
                            : 'bg-[#1a1a24] text-gray-300 hover:bg-[#2a2a34]'
                        }`}
                      >
                        {days}d
                      </button>
                    ))}
                  </div>
                  <input
                    type="number"
                    min="1"
                    max="30"
                    step="1"
                    value={formData.rebalancing_frequency_days}
                    onChange={(e) => setFormData({ ...formData, rebalancing_frequency_days: parseInt(e.target.value) || 5 })}
                    className="w-full px-3 py-1.5 bg-[#1a1a24] border border-[#2a2a34] rounded text-white text-sm"
                  />
                </div>

                {/* Beta Drift Threshold */}
                <div>
                  <label className="block text-xs font-medium text-gray-300 mb-2">
                    Beta Drift Threshold
                  </label>
                  <div className="flex gap-1 mb-2">
                    {[0.03, 0.05, 0.10, 0.15].map((threshold) => (
                      <button
                        key={threshold}
                        type="button"
                        onClick={() => setFormData({ ...formData, rebalancing_threshold: threshold })}
                        className={`flex-1 px-2 py-1 rounded text-xs transition-colors ${
                          formData.rebalancing_threshold === threshold
                            ? 'bg-blue-500 text-white'
                            : 'bg-[#1a1a24] text-gray-300 hover:bg-[#2a2a34]'
                        }`}
                      >
                        {(threshold * 100).toFixed(0)}%
                      </button>
                    ))}
                  </div>
                  <input
                    type="number"
                    min="0.01"
                    max="0.5"
                    step="0.01"
                    value={formData.rebalancing_threshold}
                    onChange={(e) => setFormData({ ...formData, rebalancing_threshold: parseFloat(e.target.value) || 0.05 })}
                    className="w-full px-3 py-1.5 bg-[#1a1a24] border border-[#2a2a34] rounded text-white text-sm"
                  />
                </div>
              </div>
            )}
          </div>

          <button
            type="submit"
            disabled={runBacktestMutation.isLoading}
            className="w-full px-4 py-3 bg-emerald-500 hover:bg-emerald-600 text-white font-medium rounded-lg transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
          >
            {runBacktestMutation.isLoading ? 'Running Backtest...' : 'Run Backtest'}
          </button>

          {runBacktestMutation.isError && (
            <div className="p-3 bg-red-500/20 border border-red-500/50 rounded-lg text-red-400 text-sm">
              Error: {runBacktestMutation.error instanceof Error ? runBacktestMutation.error.message : 'Failed to run backtest'}
            </div>
          )}
        </form>
      )}

      {showResults && sessionId && (
        <div className="mt-4">
          <BacktestResults sessionId={sessionId} />
        </div>
      )}
    </div>
  );
};

export default BacktestSection;

