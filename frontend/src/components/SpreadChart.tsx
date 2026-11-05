import React from 'react';
import { LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, Legend, ResponsiveContainer, ReferenceLine, Scatter } from 'recharts';
import { PairResult, SpreadDataPoint, CrossingPoint } from '../services/api';
import { api } from '../services/api';

interface SpreadChartProps {
  pair: PairResult;
  spreadData: SpreadDataPoint[];
  meanSpread: number;
  stdSpread: number;
  crossingPoints?: CrossingPoint[];
}

const SpreadChart: React.FC<SpreadChartProps> = ({ pair, spreadData, meanSpread, stdSpread, crossingPoints = [] }) => {
  // Format data for chart
  const chartData = spreadData.map(point => ({
    date: new Date(point.date).toLocaleDateString('en-US', { month: 'short', day: 'numeric' }),
    fullDate: point.date,
    spread: point.spread,
    zscore: point.zscore,
  }));
  
  // Format crossing points for scatter plot
  const crossingData = crossingPoints.map(cp => {
    const chartPoint = chartData.find(p => p.fullDate === cp.date);
    if (!chartPoint) return null;
    return {
      date: chartPoint.date,
      fullDate: cp.date,
      x: chartPoint.date,
      y: cp.zscore,
      spread: chartPoint.spread,
      zscore: cp.zscore,
      type: cp.type,
      label: cp.type === 'entry_high' ? '↑ Entry' : 
             cp.type === 'entry_low' ? '↓ Entry' :
             cp.type === 'exit_high' ? '↑ Exit' : '↓ Exit'
    };
  }).filter(Boolean);

  // Calculate Y-axis domain with 10% padding from min/max values
  const zscoreValues = chartData.map(d => d.zscore);
  
  let zscoreAxisMin = -3;
  let zscoreAxisMax = 3;
  let zscoreTicks: number[] = [];
  
  if (zscoreValues.length > 0) {
    const minZscore = Math.min(...zscoreValues);
    const maxZscore = Math.max(...zscoreValues);
    
    // 10% padding from min/max values
    // Example: if max = 3.5, then upper bound = 3.5 + (3.5 × 0.1) = 3.85
    // Example: if min = -2.5, then lower bound = -2.5 - (2.5 × 0.1) = -2.75
    const paddingTop = Math.abs(maxZscore) * 0.1;
    const paddingBottom = Math.abs(minZscore) * 0.1;
    
    // Exact boundaries with padding (no rounding)
    zscoreAxisMin = minZscore - paddingBottom;
    zscoreAxisMax = maxZscore + paddingTop;
    
    // Generate integer ticks only within the domain with padding
    const minTick = Math.ceil(zscoreAxisMin);
    const maxTick = Math.floor(zscoreAxisMax);
    zscoreTicks = [];
    for (let i = minTick; i <= maxTick; i++) {
      zscoreTicks.push(i);
    }
  } else {
    zscoreTicks = [-3, -2, -1, 0, 1, 2, 3];
  }

  // Format Z-Score ticks to show only integers
  const formatZScoreTick = (value: number) => {
    return Math.round(value).toString();
  };

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
    <div className="bg-[#111118] border border-[#1a1a24] rounded-xl p-6 backdrop-blur-sm">
      <div className="mb-4 flex items-center justify-between">
        <div>
          <h3 className="text-lg font-medium text-white mb-1">
            Spread Chart: {pair.asset_a} / {pair.asset_b}
          </h3>
          <p className="text-xs text-gray-400">
            Beta: {pair.beta.toFixed(4)} | Mean: {meanSpread.toFixed(4)} | Std: {stdSpread.toFixed(4)}
          </p>
        </div>
        <button
          onClick={async () => {
            try {
              const response = await api.exportPairData(pair.id, 'csv');
              const blob = new Blob([response], { type: 'text/csv' });
              const url = window.URL.createObjectURL(blob);
              const a = document.createElement('a');
              a.href = url;
              a.download = `pair_${pair.asset_a}_${pair.asset_b}_${new Date().toISOString().split('T')[0]}.csv`;
              document.body.appendChild(a);
              a.click();
              window.URL.revokeObjectURL(url);
              document.body.removeChild(a);
            } catch (error) {
              console.error('Error exporting pair data:', error);
            }
          }}
          className="px-3 py-1.5 text-xs bg-emerald-500/20 hover:bg-emerald-500/30 border border-emerald-500/50 rounded-lg text-emerald-400 transition-colors flex items-center gap-2"
          title="Export pair data to CSV"
        >
          <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 10v6m0 0l-3-3m3 3l3-3m2 8H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
          </svg>
          Export
        </button>
      </div>
      
      {chartData.length > 0 ? (
        <ResponsiveContainer width="100%" height={400}>
          <LineChart 
            data={chartData} 
            margin={{ top: 20, right: 20, left: 10, bottom: 20 }}
          >
            <CartesianGrid strokeDasharray="3 3" stroke="#2a2a34" />
            <XAxis 
              dataKey="date" 
              stroke="#6b7280"
              style={{ fontSize: '12px' }}
              angle={-45}
              textAnchor="end"
              height={60}
              interval="preserveStartEnd"
            />
            <YAxis 
              yAxisId="zscore"
              stroke="#6b7280"
              style={{ fontSize: '12px' }}
              domain={[zscoreAxisMin, zscoreAxisMax]}
              tickFormatter={formatZScoreTick}
              allowDecimals={false}
              ticks={zscoreTicks}
              width={50}
            />
            <Tooltip content={<CustomTooltip />} />
            <Legend wrapperStyle={{ color: '#9ca3af' }} />
            
            {/* Z-score reference lines */}
            <ReferenceLine 
              yAxisId="zscore"
              y={0} 
              stroke="#10b981" 
              strokeDasharray="5 5" 
              strokeOpacity={0.7}
            />
            <ReferenceLine 
              yAxisId="zscore"
              y={2} 
              stroke="#ef4444" 
              strokeDasharray="3 3" 
              strokeOpacity={0.5}
            />
            <ReferenceLine 
              yAxisId="zscore"
              y={-2} 
              stroke="#ef4444" 
              strokeDasharray="3 3" 
              strokeOpacity={0.5}
            />
            <ReferenceLine 
              yAxisId="zscore"
              y={1} 
              stroke="#f59e0b" 
              strokeDasharray="2 2" 
              strokeOpacity={0.5}
            />
            <ReferenceLine 
              yAxisId="zscore"
              y={-1} 
              stroke="#f59e0b" 
              strokeDasharray="2 2" 
              strokeOpacity={0.5}
            />
            <ReferenceLine 
              yAxisId="zscore"
              y={3} 
              stroke="#dc2626" 
              strokeDasharray="2 2" 
              strokeOpacity={0.3}
            />
            <ReferenceLine 
              yAxisId="zscore"
              y={-3} 
              stroke="#dc2626" 
              strokeDasharray="2 2" 
              strokeOpacity={0.3}
            />
            
            {/* Z-score line */}
            <Line
              yAxisId="zscore"
              type="monotone"
              dataKey="zscore"
              stroke="#10b981"
              strokeWidth={2}
              dot={false}
              name="Z-Score"
              activeDot={{ r: 4 }}
            />
            
            {/* Crossing points markers */}
            {crossingData.length > 0 && (
              <Scatter
                yAxisId="zscore"
                data={crossingData}
                dataKey="zscore"
                fill="#10b981"
                shape={(props: any) => {
                  const { cx, cy, payload } = props;
                  if (!payload || !cx || !cy) return <g />;
                  const isEntry = payload.type?.includes('entry');
                  const color = isEntry ? '#10b981' : '#ef4444';
                  return (
                    <g>
                      <circle cx={cx} cy={cy} r={isEntry ? 6 : 5} fill={color} stroke="#fff" strokeWidth={1} />
                      {isEntry && (
                        <text x={cx} y={cy - 10} textAnchor="middle" fill={color} fontSize={9} fontWeight="bold">
                          {payload.label}
                        </text>
                      )}
                    </g>
                  );
                }}
                name="Entry/Exit Points"
              />
            )}
          </LineChart>
        </ResponsiveContainer>
      ) : (
        <div className="text-center text-gray-400 py-12">
          <div className="inline-block animate-spin rounded-full h-8 w-8 border-b-2 border-emerald-500 mb-4"></div>
          <p>Loading spread data...</p>
        </div>
      )}
    </div>
  );
};

export default SpreadChart;
