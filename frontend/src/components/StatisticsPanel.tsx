import React from 'react';
import { Statistics } from '../services/api';

interface StatisticsPanelProps {
  stats: Statistics;
}

const StatCard: React.FC<{ label: string; value: string; sub: string; subClass?: string; valueClass?: string }> = ({
  label,
  value,
  sub,
  subClass = 'text-muted',
  valueClass = 'text-white',
}) => (
  <div className="rounded border border-dark-border bg-dark-surface p-4">
    <div className="text-2xs font-medium uppercase tracking-wider text-muted">{label}</div>
    <div className={`mt-2 text-2xl font-light ${valueClass}`}>{value}</div>
    <div className={`mt-1 text-2xs ${subClass}`}>{sub}</div>
  </div>
);

const StatisticsPanel: React.FC<StatisticsPanelProps> = ({ stats }) => {
  return (
    <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
      <StatCard label="Total pairs" value={String(stats.total_pairs)} sub="Active" />
      <StatCard
        label="Avg correlation"
        value={stats.avg_correlation.toFixed(3)}
        sub="Mean"
        valueClass="text-accent"
      />
      <StatCard
        label="Avg ADF p-value"
        value={stats.avg_adf_pvalue.toFixed(4)}
        sub="Cointegrated"
        valueClass="text-sky-400"
      />
      {stats.avg_hurst !== null && stats.avg_hurst !== undefined && (
        <StatCard
          label="Avg Hurst"
          value={stats.avg_hurst.toFixed(3)}
          sub={stats.avg_hurst < 0.5 ? 'Mean reverting' : 'Trending'}
          valueClass={stats.avg_hurst < 0.5 ? 'text-accent' : 'text-warn'}
          subClass={stats.avg_hurst < 0.5 ? 'text-accent/70' : 'text-warn/70'}
        />
      )}
    </div>
  );
};

export default StatisticsPanel;
