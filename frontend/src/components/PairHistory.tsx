import React from 'react';
import { useQuery } from 'react-query';
import { LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer } from 'recharts';
import { api } from '../services/api';

interface PairHistoryProps {
  pairId: number;
}

interface HistoryPoint {
  timestamp: string;
  correlation: number;
  beta: number;
  adf_pvalue: number;
  current_zscore: number;
  composite_score: number;
}

const PairHistory: React.FC<PairHistoryProps> = ({ pairId }) => {
  const { data, isLoading } = useQuery(
    ['pair-history', pairId],
    () => api.getPairHistory(pairId),
    { refetchInterval: 30000 }
  );

  if (isLoading) {
    return (
      <div className="bg-[#111118] border border-[#1a1a24] rounded-xl p-6 text-center">
        <div className="inline-block animate-spin rounded-full h-8 w-8 border-b-2 border-emerald-500"></div>
        <p className="text-gray-400 mt-4">Loading history...</p>
      </div>
    );
  }

  const history: HistoryPoint[] = data?.history || [];

  if (history.length === 0) {
    return (
      <div className="bg-[#111118] border border-[#1a1a24] rounded-xl p-6 text-center">
        <p className="text-gray-400">No history available for this pair</p>
      </div>
    );
  }

  // Format data for charts
  const chartData = history.map((point) => ({
    date: new Date(point.timestamp).toLocaleDateString('en-US', { month: 'short', day: 'numeric' }),
    fullDate: point.timestamp,
    correlation: point.correlation,
    beta: point.beta,
    adf_pvalue: point.adf_pvalue,
    zscore: point.current_zscore,
    composite_score: point.composite_score,
  }));

  const CustomTooltip = ({ active, payload }: any) => {
    if (active && payload && payload.length) {
      return (
        <div className="bg-[#1a1a24] border border-[#2a2a34] rounded-lg p-3 shadow-lg">
          <p className="text-white font-medium mb-2">
            {payload[0].payload.fullDate ? new Date(payload[0].payload.fullDate).toLocaleString() : ''}
          </p>
          {payload.map((entry: any, index: number) => (
            <p key={index} className="text-sm" style={{ color: entry.color }}>
              {entry.name}: {typeof entry.value === 'number' ? entry.value.toFixed(4) : entry.value}
            </p>
          ))}
        </div>
      );
    }
    return null;
  };

  return (
    <div className="bg-[#111118] border border-[#1a1a24] rounded-xl p-6 space-y-6">
      <div>
        <h3 className="text-lg font-medium text-white mb-1">Pair History</h3>
        <p className="text-xs text-gray-400">Metrics over time ({history.length} sessions)</p>
      </div>

      {/* Correlation Chart */}
      <div>
        <h4 className="text-sm font-medium text-gray-300 mb-3">Correlation Over Time</h4>
        <ResponsiveContainer width="100%" height={200}>
          <LineChart data={chartData} margin={{ top: 5, right: 30, left: 20, bottom: 5 }}>
            <CartesianGrid strokeDasharray="3 3" stroke="#2a2a34" />
            <XAxis dataKey="date" stroke="#6b7280" style={{ fontSize: '12px' }} />
            <YAxis stroke="#6b7280" style={{ fontSize: '12px' }} domain={[0, 1]} />
            <Tooltip content={<CustomTooltip />} />
            <Line
              type="monotone"
              dataKey="correlation"
              stroke="#3b82f6"
              strokeWidth={2}
              dot={false}
              name="Correlation"
            />
          </LineChart>
        </ResponsiveContainer>
      </div>

      {/* Beta Chart */}
      <div>
        <h4 className="text-sm font-medium text-gray-300 mb-3">Beta (Hedge Ratio) Over Time</h4>
        <ResponsiveContainer width="100%" height={200}>
          <LineChart data={chartData} margin={{ top: 5, right: 30, left: 20, bottom: 5 }}>
            <CartesianGrid strokeDasharray="3 3" stroke="#2a2a34" />
            <XAxis dataKey="date" stroke="#6b7280" style={{ fontSize: '12px' }} />
            <YAxis stroke="#6b7280" style={{ fontSize: '12px' }} />
            <Tooltip content={<CustomTooltip />} />
            <Line
              type="monotone"
              dataKey="beta"
              stroke="#10b981"
              strokeWidth={2}
              dot={false}
              name="Beta"
            />
          </LineChart>
        </ResponsiveContainer>
      </div>

      {/* Z-Score Chart */}
      <div>
        <h4 className="text-sm font-medium text-gray-300 mb-3">Z-Score Over Time</h4>
        <ResponsiveContainer width="100%" height={200}>
          <LineChart data={chartData} margin={{ top: 5, right: 30, left: 20, bottom: 5 }}>
            <CartesianGrid strokeDasharray="3 3" stroke="#2a2a34" />
            <XAxis dataKey="date" stroke="#6b7280" style={{ fontSize: '12px' }} />
            <YAxis stroke="#6b7280" style={{ fontSize: '12px' }} />
            <Tooltip content={<CustomTooltip />} />
            <Line
              type="monotone"
              dataKey="zscore"
              stroke="#f59e0b"
              strokeWidth={2}
              dot={false}
              name="Z-Score"
            />
          </LineChart>
        </ResponsiveContainer>
      </div>
    </div>
  );
};

export default PairHistory;

