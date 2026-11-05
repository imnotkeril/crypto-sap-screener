import React from 'react';
import { useQuery } from 'react-query';
import { LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer } from 'recharts';
import { api } from '../services/api';

const TrendsDashboard: React.FC = () => {
  const { data: trendsData, isLoading: trendsLoading } = useQuery(
    'trends',
    () => api.getTrends(),
    { refetchInterval: 30000 }
  );

  const { isLoading: comparisonLoading } = useQuery(
    'comparison',
    () => api.getComparison(),
    { refetchInterval: 30000 }
  );

  if (trendsLoading || comparisonLoading) {
    return (
      <div className="bg-[#111118] border border-[#1a1a24] rounded-xl p-6 text-center">
        <div className="inline-block animate-spin rounded-full h-8 w-8 border-b-2 border-emerald-500"></div>
        <p className="text-gray-400 mt-4">Loading trends...</p>
      </div>
    );
  }

  const trends = trendsData || {};

  // Format trends data for charts
  const pairsCountData = (trends.total_pairs_trend || []).map((point: any) => ({
    date: new Date(point.timestamp).toLocaleDateString('en-US', { month: 'short', day: 'numeric' }),
    count: point.count,
  }));

  const correlationData = (trends.avg_correlation_trend || []).map((point: any) => ({
    date: new Date(point.timestamp).toLocaleDateString('en-US', { month: 'short', day: 'numeric' }),
    avgCorrelation: point.avg_correlation,
  }));

  const CustomTooltip = ({ active, payload }: any) => {
    if (active && payload && payload.length) {
      return (
        <div className="bg-[#1a1a24] border border-[#2a2a34] rounded-lg p-3 shadow-lg">
          {payload.map((entry: any, index: number) => (
            <p key={index} className="text-sm" style={{ color: entry.color }}>
              {entry.name}: {typeof entry.value === 'number' ? entry.value.toFixed(2) : entry.value}
            </p>
          ))}
        </div>
      );
    }
    return null;
  };

  return (
    <div className="space-y-6">
      {/* Trends Charts */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
        {/* Total Pairs Trend */}
        <div className="bg-[#111118] border border-[#1a1a24] rounded-xl p-6">
          <h3 className="text-lg font-medium text-white mb-4">Total Pairs Over Time</h3>
          {pairsCountData.length > 0 ? (
            <ResponsiveContainer width="100%" height={250}>
              <LineChart data={pairsCountData} margin={{ top: 5, right: 30, left: 20, bottom: 5 }}>
                <CartesianGrid strokeDasharray="3 3" stroke="#2a2a34" />
                <XAxis dataKey="date" stroke="#6b7280" style={{ fontSize: '12px' }} />
                <YAxis stroke="#6b7280" style={{ fontSize: '12px' }} />
                <Tooltip content={<CustomTooltip />} />
                <Line
                  type="monotone"
                  dataKey="count"
                  stroke="#3b82f6"
                  strokeWidth={2}
                  dot={false}
                  name="Pairs Count"
                />
              </LineChart>
            </ResponsiveContainer>
          ) : (
            <div className="text-center text-gray-400 py-12">No trend data available</div>
          )}
        </div>

        {/* Average Correlation Trend */}
        <div className="bg-[#111118] border border-[#1a1a24] rounded-xl p-6">
          <h3 className="text-lg font-medium text-white mb-4">Average Correlation Over Time</h3>
          {correlationData.length > 0 ? (
            <ResponsiveContainer width="100%" height={250}>
              <LineChart data={correlationData} margin={{ top: 5, right: 30, left: 20, bottom: 5 }}>
                <CartesianGrid strokeDasharray="3 3" stroke="#2a2a34" />
                <XAxis dataKey="date" stroke="#6b7280" style={{ fontSize: '12px' }} />
                <YAxis stroke="#6b7280" style={{ fontSize: '12px' }} domain={[0, 1]} />
                <Tooltip content={<CustomTooltip />} />
                <Line
                  type="monotone"
                  dataKey="avgCorrelation"
                  stroke="#10b981"
                  strokeWidth={2}
                  dot={false}
                  name="Avg Correlation"
                />
              </LineChart>
            </ResponsiveContainer>
          ) : (
            <div className="text-center text-gray-400 py-12">No trend data available</div>
          )}
        </div>
      </div>

    </div>
  );
};

export default TrendsDashboard;

