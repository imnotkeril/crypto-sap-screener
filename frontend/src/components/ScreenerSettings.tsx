import React, { useState } from 'react';
import { api, ScreeningConfig } from '../services/api';

interface ScreenerSettingsProps {
  onSettingsApplied?: () => void;
}

// For each candle timeframe, the lookback window (in days) needs to be long enough
// to cover many independent cycles - otherwise cointegration/ADF results are just
// overfitting to a single short-term move (e.g. "today's data").
// Fine candle timeframes require many paginated requests per asset (Binance
// caps OHLCV responses at 1000 candles/request), so the asset universe is
// capped lower to keep a screening run from taking too long / hitting rate
// limits. maxAssetsDefault/maxAssetsLimit scale up as candles get coarser.
const TIMEFRAMES: {
  value: string;
  label: string;
  min: number;
  max: number;
  default: number;
  maxAssetsDefault: number;
  maxAssetsLimit: number;
}[] = [
  { value: '1m', label: '1 minute', min: 2, max: 7, default: 3, maxAssetsDefault: 15, maxAssetsLimit: 30 },
  { value: '5m', label: '5 minutes', min: 5, max: 21, default: 10, maxAssetsDefault: 30, maxAssetsLimit: 50 },
  { value: '15m', label: '15 minutes', min: 10, max: 45, default: 21, maxAssetsDefault: 50, maxAssetsLimit: 100 },
  { value: '1h', label: '1 hour', min: 14, max: 180, default: 30, maxAssetsDefault: 100, maxAssetsLimit: 200 },
  { value: '4h', label: '4 hours', min: 30, max: 365, default: 90, maxAssetsDefault: 100, maxAssetsLimit: 200 },
  { value: '1d', label: '1 day', min: 50, max: 1000, default: 365, maxAssetsDefault: 100, maxAssetsLimit: 200 },
];

const ScreenerSettings: React.FC<ScreenerSettingsProps> = ({ onSettingsApplied }) => {
  const [isOpen, setIsOpen] = useState(false);
  const [isRunning, setIsRunning] = useState(false);

  const [settings, setSettings] = useState<ScreeningConfig>({
    lookback_days: 365,
    timeframe: '1d',
    max_assets: 100,
    min_correlation: 0.80,
    max_adf_pvalue: 0.10,
    include_hurst: true,
    min_volume_usd: 1_000_000,
  });

  const currentTimeframe = TIMEFRAMES.find((t) => t.value === settings.timeframe) || TIMEFRAMES[5];

  const handleTimeframeChange = (value: string) => {
    const tf = TIMEFRAMES.find((t) => t.value === value) || TIMEFRAMES[5];
    setSettings((prev) => {
      const lookback = prev.lookback_days ?? tf.default;
      const inRange = lookback >= tf.min && lookback <= tf.max;
      const maxAssets = prev.max_assets ?? tf.maxAssetsDefault;
      const maxAssetsInRange = maxAssets <= tf.maxAssetsLimit;
      return {
        ...prev,
        timeframe: tf.value,
        lookback_days: inRange ? lookback : tf.default,
        max_assets: maxAssetsInRange ? maxAssets : tf.maxAssetsDefault,
      };
    });
  };

  const handleRunScreening = async () => {
    setIsRunning(true);
    try {
      await api.runScreening(settings);
      setIsOpen(false);
      if (onSettingsApplied) {
        onSettingsApplied();
      }

      // The run executes as a background task, so poll status until it
      // finishes (or a 5 minute cap, for slow intraday scans) so we can
      // surface failures and refresh results once new data is in.
      const start = Date.now();
      const poll = async () => {
        try {
          const status = await api.getStatus();
          if (status.is_running && Date.now() - start < 5 * 60 * 1000) {
            setTimeout(poll, 3000);
            return;
          }
          if (status.last_error) {
            alert(`Screening failed: ${status.last_error}`);
          }
        } catch (e) {
          // ignore polling errors
        } finally {
          setIsRunning(false);
          if (onSettingsApplied) {
            onSettingsApplied();
          }
        }
      };
      setTimeout(poll, 3000);
    } catch (error) {
      console.error('Error running screening:', error);
      setIsRunning(false);
    }
  };

  // Check if lookback_days changed from default
  const defaultLookbackDays = 365;
  const lookbackChanged = settings.lookback_days !== defaultLookbackDays;

  return (
    <>
      <button
        onClick={() => setIsOpen(true)}
        className="px-4 py-2 text-sm font-medium text-white bg-emerald-500/20 hover:bg-emerald-500/30 border border-emerald-500/50 rounded-lg transition-colors flex items-center gap-2"
      >
        <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M10.325 4.317c.426-1.756 2.924-1.756 3.35 0a1.724 1.724 0 002.573 1.066c1.543-.94 3.31.826 2.37 2.37a1.724 1.724 0 001.065 2.572c1.756.426 1.756 2.924 0 3.35a1.724 1.724 0 00-1.066 2.573c.94 1.543-.826 3.31-2.37 2.37a1.724 1.724 0 00-2.572 1.065c-.426 1.756-2.924 1.756-3.35 0a1.724 1.724 0 00-2.573-1.066c-1.543.94-3.31-.826-2.37-2.37a1.724 1.724 0 00-1.065-2.572c-1.756-.426-1.756-2.924 0-3.35a1.724 1.724 0 001.066-2.573c-.94-1.543.826-3.31 2.37-2.37.996.608 2.296.07 2.572-1.065z" />
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15 12a3 3 0 11-6 0 3 3 0 016 0z" />
        </svg>
        Settings
      </button>

      {isOpen && (
        <div 
          className="fixed inset-0 bg-black/80 backdrop-blur-sm z-50 flex items-center justify-center p-4"
          onClick={() => setIsOpen(false)}
        >
          <div 
            className="bg-[#111118] border border-[#1a1a24] rounded-xl max-w-2xl w-full"
            onClick={(e) => e.stopPropagation()}
          >
            <div className="px-6 py-4 border-b border-[#1a1a24] flex items-center justify-between">
              <h2 className="text-xl font-medium text-white">Screener Settings</h2>
              <button
                onClick={() => setIsOpen(false)}
                className="text-gray-400 hover:text-white transition-colors"
              >
                <svg className="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
                </svg>
              </button>
            </div>
            
            <div className="p-6 space-y-6">
              {lookbackChanged && (
                <div className="bg-amber-500/10 border border-amber-500/30 rounded-lg p-3 mb-4">
                  <p className="text-xs text-amber-400">
                    ⚠️ Analysis period changed. After running the screening, all found pairs will use {settings.lookback_days} days of data. 
                    Old pairs (found with different settings) will show data for the period with which they were found.
                  </p>
                </div>
              )}
              <div>
                <label className="block text-sm font-medium text-gray-300 mb-2">
                  Timeframe
                </label>
                <div className="grid grid-cols-3 gap-2 sm:grid-cols-6">
                  {TIMEFRAMES.map((tf) => (
                    <button
                      key={tf.value}
                      type="button"
                      onClick={() => handleTimeframeChange(tf.value)}
                      className={`rounded-lg border px-2 py-2 text-xs font-medium transition-colors ${
                        settings.timeframe === tf.value
                          ? 'border-emerald-500 bg-emerald-500/20 text-emerald-300'
                          : 'border-[#1a1a24] bg-[#1a1a24] text-gray-400 hover:border-emerald-500/40 hover:text-gray-200'
                      }`}
                    >
                      {tf.value}
                    </button>
                  ))}
                </div>
                <p className="mt-2 text-2xs text-gray-500">
                  Intraday timeframes (1m–4h) re-run cointegration on shorter candles. The lookback range below
                  is constrained per timeframe so results still span enough independent cycles to be statistically
                  meaningful — a 1m screen over a single day, for example, would just overfit to today's move.
                </p>
              </div>

              <div>
                <label className="block text-sm font-medium text-gray-300 mb-2">
                  Lookback Days: {settings.lookback_days} <span className="text-gray-500">({currentTimeframe.label} candles)</span>
                </label>
                <input
                  type="range"
                  min={currentTimeframe.min}
                  max={currentTimeframe.max}
                  step="1"
                  value={settings.lookback_days}
                  onChange={(e) => setSettings({ ...settings, lookback_days: parseInt(e.target.value) })}
                  className="w-full h-2 bg-[#1a1a24] rounded-lg appearance-none cursor-pointer accent-emerald-500"
                />
                <div className="flex justify-between text-xs text-gray-500 mt-1">
                  <span>{currentTimeframe.min}</span>
                  <span>{currentTimeframe.max}</span>
                </div>
              </div>

              <div>
                <label className="block text-sm font-medium text-gray-300 mb-2">
                  Max Assets: {settings.max_assets ?? currentTimeframe.maxAssetsDefault}
                </label>
                <input
                  type="range"
                  min="10"
                  max={currentTimeframe.maxAssetsLimit}
                  step="5"
                  value={settings.max_assets ?? currentTimeframe.maxAssetsDefault}
                  onChange={(e) => setSettings({ ...settings, max_assets: parseInt(e.target.value) })}
                  className="w-full h-2 bg-[#1a1a24] rounded-lg appearance-none cursor-pointer accent-emerald-500"
                />
                <div className="flex justify-between text-xs text-gray-500 mt-1">
                  <span>10</span>
                  <span>{currentTimeframe.maxAssetsLimit}</span>
                </div>
                <p className="mt-2 text-2xs text-gray-500">
                  Number of top-volume assets to scan (pairs tested ≈ N²/2). Fine timeframes are capped lower
                  since each asset needs many paginated requests to fetch enough candles.
                </p>
              </div>

              <div>
                <label className="block text-sm font-medium text-gray-300 mb-2">
                  Min Correlation: {settings.min_correlation.toFixed(2)}
                </label>
                <input
                  type="range"
                  min="0"
                  max="1"
                  step="0.01"
                  value={settings.min_correlation}
                  onChange={(e) => setSettings({ ...settings, min_correlation: parseFloat(e.target.value) })}
                  className="w-full h-2 bg-[#1a1a24] rounded-lg appearance-none cursor-pointer accent-emerald-500"
                />
                <div className="flex justify-between text-xs text-gray-500 mt-1">
                  <span>0.0</span>
                  <span>1.0</span>
                </div>
              </div>

              <div>
                <label className="block text-sm font-medium text-gray-300 mb-2">
                  Max ADF p-value: {settings.max_adf_pvalue.toFixed(2)}
                </label>
                <input
                  type="range"
                  min="0"
                  max="0.5"
                  step="0.01"
                  value={settings.max_adf_pvalue}
                  onChange={(e) => setSettings({ ...settings, max_adf_pvalue: parseFloat(e.target.value) })}
                  className="w-full h-2 bg-[#1a1a24] rounded-lg appearance-none cursor-pointer accent-emerald-500"
                />
                <div className="flex justify-between text-xs text-gray-500 mt-1">
                  <span>0.0</span>
                  <span>0.5</span>
                </div>
              </div>

              <div>
                <label className="block text-sm font-medium text-gray-300 mb-2">
                  Min Volume USD: {(settings.min_volume_usd / 1_000_000).toFixed(1)}M
                </label>
                <input
                  type="range"
                  min="0"
                  max="100"
                  step="1"
                  value={settings.min_volume_usd / 1_000_000}
                  onChange={(e) => setSettings({ ...settings, min_volume_usd: parseFloat(e.target.value) * 1_000_000 })}
                  className="w-full h-2 bg-[#1a1a24] rounded-lg appearance-none cursor-pointer accent-emerald-500"
                />
                <div className="flex justify-between text-xs text-gray-500 mt-1">
                  <span>0M</span>
                  <span>100M</span>
                </div>
              </div>

              <div className="flex items-center gap-3">
                <input
                  type="checkbox"
                  id="include_hurst"
                  checked={settings.include_hurst}
                  onChange={(e) => setSettings({ ...settings, include_hurst: e.target.checked })}
                  className="w-4 h-4 text-emerald-500 bg-[#1a1a24] border-[#2a2a34] rounded focus:ring-emerald-500"
                />
                <label htmlFor="include_hurst" className="text-sm text-gray-300">
                  Include Hurst Exponent calculation
                </label>
              </div>

              <div className="flex gap-3 pt-4 border-t border-[#1a1a24]">
                <button
                  onClick={handleRunScreening}
                  disabled={isRunning}
                  className="flex-1 px-4 py-2 bg-emerald-500 hover:bg-emerald-600 text-white font-medium rounded-lg transition-colors disabled:opacity-50 disabled:cursor-not-allowed flex items-center justify-center gap-2"
                >
                  {isRunning ? (
                    <>
                      <div className="w-4 h-4 border-2 border-white border-t-transparent rounded-full animate-spin"></div>
                      Running...
                    </>
                  ) : (
                    <>
                      <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M14.752 11.168l-3.197-2.132A1 1 0 0010 9.87v4.263a1 1 0 001.555.832l3.197-2.132a1 1 0 000-1.664z" />
                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
                      </svg>
                      Run Screening
                    </>
                  )}
                </button>
                <button
                  onClick={() => setIsOpen(false)}
                  className="px-4 py-2 bg-[#1a1a24] hover:bg-[#2a2a34] text-gray-300 font-medium rounded-lg transition-colors"
                >
                  Cancel
                </button>
              </div>
            </div>
          </div>
        </div>
      )}
    </>
  );
};

export default ScreenerSettings;

