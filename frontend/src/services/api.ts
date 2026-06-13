/**
 * API client for backend communication
 */
import axios from 'axios';

// Use proxy in development, direct URL in production
// In dev mode, use empty baseURL so proxy handles /api prefix
// In production, use full URL from environment variable or default to Railway backend
const API_BASE_URL = import.meta.env.VITE_API_URL || (import.meta.env.DEV ? '' : '');

const apiClient = axios.create({
  baseURL: API_BASE_URL,
  headers: {
    'Content-Type': 'application/json',
  },
  timeout: 10000, // 10 second timeout
});

// Add error interceptor
apiClient.interceptors.response.use(
  (response) => response,
  (error) => {
    console.error('API Error:', error.message);
    return Promise.reject(error);
  }
);

export interface ScreeningConfig {
  assets?: string[];
  lookback_days?: number;
  min_correlation?: number;
  max_adf_pvalue?: number;
  include_hurst?: boolean;
  min_volume_usd?: number;
}

export interface PairResult {
  id: number;
  asset_a: string;
  asset_b: string;
  correlation: number;
  adf_pvalue: number;
  adf_statistic: number;
  beta: number;
  spread_std: number;
  hurst_exponent?: number;
  screening_date: string;
  lookback_days: number;
  mean_spread?: number;
  min_correlation_window?: number;
  max_correlation_window?: number;
  composite_score?: number;
  current_zscore?: number;
}

export interface ScreeningSession {
  id: number;
  started_at: string;
  completed_at?: string;
  total_pairs_tested: number;
  pairs_found: number;
  status: string;
}

export interface ScreeningStatus {
  is_running: boolean;
  last_session?: ScreeningSession;
  total_pairs_in_db: number;
}

export interface ScreeningResults {
  results: PairResult[];
  total: number;
  session_id?: number;
}

export interface Statistics {
  total_pairs: number;
  avg_correlation: number;
  avg_adf_pvalue: number;
  pairs_with_hurst: number;
  avg_hurst?: number;
}

export interface SpreadDataPoint {
  date: string;
  spread: number;
  zscore: number;
  price_a_norm?: number | null;
  price_b_norm?: number | null;
  price_b_hedged_norm?: number | null;
}

export interface CrossingPoint {
  date: string;
  type: 'entry_high' | 'entry_low' | 'exit_high' | 'exit_low';
  zscore: number;
}

export interface SpreadStatistics {
  mean: number;
  std: number;
  min: number;
  max: number;
  std_pct: number | null;
  min_pct: number | null;
  max_pct: number | null;
}

export interface MeanReversionStats {
  half_life_days: number | null;
  mean_crossings: number;
  time_outside_1sigma_pct: number;
  time_outside_2sigma_pct: number;
  time_outside_3sigma_pct: number;
  avg_reversion_time_days: number | null;
}

export interface CurrentDeviation {
  zscore_percentile: number;
  rarity: string;
  probability_extreme: number;
}

export interface ExpectedReturn {
  expected_return_5d: number;
  expected_return_std: number;
  win_rate: number;
  sample_size: number;
}

export interface RiskMetrics {
  var_95: number;  // Daily z-score change at 5th percentile (in z-score units)
  max_drawdown: number;  // Maximum absolute z-score (in z-score units)
  volatility_annual: number;  // Annualized z-score volatility (in z-score units)
}

export interface ReturnProbabilities {
  extreme_high: number | null;
  high: number | null;
  neutral: number | null;
  low: number | null;
  extreme_low: number | null;
}

export interface ReturnProbabilitiesSamples {
  extreme_high: number;
  high: number;
  neutral: number;
  low: number;
  extreme_low: number;
}

export interface PairSpreadData {
  pair_id: number;
  asset_a: string;
  asset_b: string;
  beta: number;
  mean_spread: number;
  std_spread: number;
  current_zscore: number;
  min_zscore: number;
  max_zscore: number;
  min_spread: number;
  max_spread: number;
  composite_score: number;
  data: SpreadDataPoint[];
  crossing_points?: CrossingPoint[];
  spread_statistics?: SpreadStatistics;
  mean_reversion?: MeanReversionStats;
  current_deviation?: CurrentDeviation;
  expected_return?: ExpectedReturn | null;
  risk_metrics?: RiskMetrics;
  return_probabilities?: ReturnProbabilities;
  return_probabilities_samples?: ReturnProbabilitiesSamples;
}

export interface LivePairSnapshot {
  pair_id?: number;
  asset_a: string;
  asset_b: string;
  price_a: number;
  price_b: number;
  beta: number;
  spread: number;
  zscore: number;
  daily_zscore: number;
  zscore_delta: number;
  is_unusual: boolean;
  updated_at: string;
}

export interface LiveSnapshot {
  pairs: LivePairSnapshot[];
  last_update: string | null;
  is_running: boolean;
  interval_seconds: number;
  alert_threshold: number;
  last_error: string | null;
}

export interface LiveHistoryPoint {
  t: string;
  z: number;
}

export const api = {
  // Get screening status
  getStatus: async (): Promise<ScreeningStatus> => {
    try {
      const response = await apiClient.get('/api/v1/screener/status');
      return response.data;
    } catch (error) {
      // Return default status if API is unavailable
      return {
        is_running: false,
        total_pairs_in_db: 0,
      };
    }
  },

  // Run screening
  runScreening: async (config: ScreeningConfig): Promise<ScreeningSession> => {
    const response = await apiClient.post('/api/v1/screener/run', config);
    return response.data;
  },

  // Run live screening (fetches fresh data from Binance)
  runLiveScreening: async (): Promise<{ message: string; status: string; note?: string }> => {
    const response = await apiClient.post('/api/v1/screener/run-live');
    return response.data;
  },

  // Get screening results
  getResults: async (
    limit: number = 50,
    min_correlation?: number,
    sort_by: string = 'correlation'
  ): Promise<ScreeningResults> => {
    try {
      const params: any = { limit, sort_by };
      if (min_correlation !== undefined) {
        params.min_correlation = min_correlation;
      }
      const response = await apiClient.get('/api/v1/screener/results', { params });
      return response.data;
    } catch (error) {
      // Return empty results if API is unavailable
      return {
        results: [],
        total: 0,
      };
    }
  },

  // Get pair details
  getPairDetails: async (pairId: number): Promise<PairResult> => {
    const response = await apiClient.get(`/api/v1/screener/pairs/${pairId}`);
    return response.data;
  },

  // Get statistics
  getStatistics: async (): Promise<Statistics> => {
    try {
      const response = await apiClient.get('/api/v1/screener/stats');
      return response.data;
    } catch (error) {
      // Return default statistics if API is unavailable
      return {
        total_pairs: 0,
        avg_correlation: 0,
        avg_adf_pvalue: 0,
        pairs_with_hurst: 0,
      };
    }
  },

  // Get pair spread data for charting
  getPairSpreadData: async (pairId: number): Promise<PairSpreadData> => {
    const response = await apiClient.get(`/api/v1/screener/pairs/${pairId}/spread`);
    return response.data;
  },

  // Calculate position sizes
  calculatePosition: async (
    pairId: number,
    capital: number,
    strategy: string = 'dollar_neutral'
  ): Promise<any> => {
    const response = await apiClient.post('/api/v1/screener/calculate-position', {
      pair_id: pairId,
      capital,
      strategy,
    });
    return response.data;
  },

  // Alerts
  getAlerts: async (pairId?: number): Promise<any> => {
    const params = pairId ? { pair_id: pairId } : {};
    const response = await apiClient.get('/api/v1/alerts', { params });
    return response.data;
  },

  createAlert: async (
    pairId: number,
    assetA: string,
    assetB: string,
    thresholdHigh?: number,
    thresholdLow?: number
  ): Promise<any> => {
    const response = await apiClient.post('/api/v1/alerts', null, {
      params: {
        pair_id: pairId,
        asset_a: assetA,
        asset_b: assetB,
        threshold_high: thresholdHigh,
        threshold_low: thresholdLow,
      },
    });
    return response.data;
  },

  updateAlert: async (
    alertId: number,
    thresholdHigh?: number,
    thresholdLow?: number,
    enabled?: boolean
  ): Promise<any> => {
    const response = await apiClient.put(`/api/v1/alerts/${alertId}`, null, {
      params: {
        threshold_high: thresholdHigh,
        threshold_low: thresholdLow,
        enabled: enabled,
      },
    });
    return response.data;
  },

  deleteAlert: async (alertId: number): Promise<void> => {
    await apiClient.delete(`/api/v1/alerts/${alertId}`);
  },

  getTriggeredAlerts: async (): Promise<any> => {
    const response = await apiClient.get('/api/v1/alerts/triggered/check');
    return response.data;
  },

  // History and Trends
  getPairHistory: async (pairId: number): Promise<any> => {
    const response = await apiClient.get(`/api/v1/screener/pairs/${pairId}/history`);
    return response.data;
  },

  getTrends: async (): Promise<any> => {
    const response = await apiClient.get('/api/v1/screener/trends');
    return response.data;
  },

  getComparison: async (): Promise<any> => {
    const response = await apiClient.get('/api/v1/screener/comparison');
    return response.data;
  },

  // Export
  exportResultsCSV: async (limit: number = 1000): Promise<string> => {
    const response = await apiClient.get('/api/v1/screener/export/csv', {
      params: { limit },
      responseType: 'text',
    });
    return response.data;
  },

  exportResultsExcel: async (limit: number = 1000): Promise<Blob> => {
    const response = await apiClient.get('/api/v1/screener/export/excel', {
      params: { limit },
      responseType: 'blob',
    });
    return response.data;
  },

  exportPairData: async (pairId: number, format: string = 'csv'): Promise<string> => {
    const response = await apiClient.get(`/api/v1/screener/pairs/${pairId}/export`, {
      params: { format },
      responseType: 'text',
    });
    return response.data;
  },

  // Backtester
  runBacktest: async (config: any): Promise<any> => {
    const response = await apiClient.post('/api/v1/backtester/run', config);
    return response.data;
  },

  getBacktestResults: async (sessionId: number): Promise<any> => {
    const response = await apiClient.get(`/api/v1/backtester/results/${sessionId}`);
    return response.data;
  },

  getBacktestSessions: async (): Promise<any> => {
    const response = await apiClient.get('/api/v1/backtester/sessions');
    return response.data;
  },

  // Positions
  getPositions: async (): Promise<any> => {
    const response = await apiClient.get('/api/v1/positions');
    return response.data;
  },

  createPosition: async (position: any): Promise<any> => {
    const response = await apiClient.post('/api/v1/positions', position);
    return response.data;
  },

  getPosition: async (positionId: number): Promise<any> => {
    const response = await apiClient.get(`/api/v1/positions/${positionId}`);
    return response.data;
  },

  deletePosition: async (positionId: number): Promise<void> => {
    await apiClient.delete(`/api/v1/positions/${positionId}`);
  },

  getPositionPnl: async (positionId: number, priceA: number, priceB: number): Promise<any> => {
    const response = await apiClient.get(`/api/v1/positions/${positionId}/pnl`, {
      params: { current_price_a: priceA, current_price_b: priceB },
    });
    return response.data;
  },

  // Live intraday monitor
  getLiveSnapshot: async (): Promise<LiveSnapshot> => {
    try {
      const response = await apiClient.get('/api/v1/live/snapshot');
      return response.data;
    } catch (error) {
      return {
        pairs: [],
        last_update: null,
        is_running: false,
        interval_seconds: 15,
        alert_threshold: 2.5,
        last_error: 'Backend unavailable',
      };
    }
  },

  getLivePairHistory: async (assetA: string, assetB: string): Promise<LiveHistoryPoint[]> => {
    try {
      const response = await apiClient.get(`/api/v1/live/pairs/${assetA}/${assetB}/history`);
      return response.data.history || [];
    } catch (error) {
      return [];
    }
  },
};

