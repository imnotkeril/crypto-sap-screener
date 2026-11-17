import React, { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { LineChart, Line, ResponsiveContainer, YAxis } from 'recharts';
import { api, LivePairSnapshot, PairResult } from '../services/api';

const fmtPrice = (v: number) => {
  if (v >= 1000) return v.toFixed(2);
  if (v >= 1) return v.toFixed(4);
  return v.toPrecision(4);
};

const fmtZ = (v: number) => (v >= 0 ? `+${v.toFixed(2)}` : v.toFixed(2));

const zColor = (z: number, threshold: number) => {
  const abs = Math.abs(z);
  if (abs >= threshold) return 'text-negative';
  if (abs >= threshold * 0.7) return 'text-warn';
  return 'text-gray-200';
};

const Sparkline: React.FC<{ assetA: string; assetB: string; active: boolean }> = ({ assetA, assetB, active }) => {
  const { data } = useQuery({
    queryKey: ['live-history', assetA, assetB],
    queryFn: () => api.getLivePairHistory(assetA, assetB),
    enabled: active,
    refetchInterval: active ? 5000 : false,
    staleTime: 4000,
  });

  if (!data || data.length < 2) {
    return <div className="text-2xs text-muted-dim px-4 pb-4">Collecting live data…</div>;
  }

  return (
    <div className="h-28 px-2 pb-3">
      <ResponsiveContainer width="100%" height="100%">
        <LineChart data={data}>
          <YAxis hide domain={['dataMin', 'dataMax']} />
          <Line
            type="monotone"
            dataKey="z"
            stroke="#5eead4"
            strokeWidth={1.5}
            dot={false}
            isAnimationActive={false}
          />
        </LineChart>
      </ResponsiveContainer>
    </div>
  );
};

const Tile: React.FC<{ label: string; value: string; hint?: string; tone?: string }> = ({ label, value, hint, tone = 'text-gray-100' }) => (
  <div className="rounded border border-dark-border bg-dark-surface px-3 py-2" title={hint}>
    <div className="text-2xs uppercase tracking-wider text-muted-dim">{label}</div>
    <div className={`mt-0.5 font-mono text-sm ${tone}`}>{value}</div>
  </div>
);

/** Expanded row: live numbers joined with the daily screen stats of the same pair. */
const PairDetailCard: React.FC<{ p: LivePairSnapshot; daily?: PairResult; threshold: number; showHistory: boolean }> = ({ p, daily, threshold, showHistory }) => {
  const deviation = p.zscore - p.daily_zscore;
  const stretched = Math.abs(p.zscore) >= threshold;
  const richA = p.zscore > 0; // spread = A - (alpha + beta * B)
  const halfLife = daily?.half_life;
  const dash = '—';

  return (
    <div className="space-y-3 px-4 pb-4 pt-1">
      <div className="grid grid-cols-2 gap-2 sm:grid-cols-4 lg:grid-cols-5">
        <Tile label="Live z" value={fmtZ(p.zscore)} tone={zColor(p.zscore, threshold)} hint="Spread z-score on live prices" />
        <Tile label="Daily z" value={fmtZ(p.daily_zscore)} hint="z-score at the last daily close" />
        <Tile label="Intraday move" value={fmtZ(deviation)} hint="Live z minus daily z: how far the spread moved since the daily fit" />
        <Tile label="Hedge ratio β" value={p.beta.toFixed(3)} hint="Units of B per unit of A in the spread A − (α + β·B)" />
        <Tile label="Correlation" value={daily ? daily.correlation.toFixed(2) : dash} />
        <Tile label="ADF p-value" value={daily ? daily.adf_pvalue.toFixed(4) : dash} hint="Engle-Granger cointegration test on the daily window" />
        <Tile label="Half-life" value={halfLife != null ? `${halfLife.toFixed(1)} d` : dash} hint="Typical time for the spread to close half of a deviation" />
        <Tile label="Hurst" value={daily?.hurst_exponent != null ? daily.hurst_exponent.toFixed(2) : dash} hint="Below 0.5 suggests mean reversion" />
        <Tile
          label="Net edge"
          value={daily?.expected_net_edge_pct != null ? `${daily.expected_net_edge_pct.toFixed(2)}%` : dash}
          hint="Expected profit of a round trip at entry z after fees, slippage and funding"
          tone={daily?.expected_net_edge_pct != null && daily.expected_net_edge_pct > 0 ? 'text-positive' : 'text-gray-100'}
        />
        <Tile label="Score" value={daily?.composite_score != null ? daily.composite_score.toFixed(0) : dash} hint="Composite quality score of the daily screen (0-100)" />
      </div>

      <div className={`rounded border px-3 py-2 text-xs ${stretched ? 'border-negative/30 bg-negative/5 text-gray-200' : 'border-dark-border bg-dark-surface text-muted'}`}>
        {stretched ? (
          <>
            Spread is stretched (|z| = {Math.abs(p.zscore).toFixed(2)} ≥ {threshold.toFixed(1)}). If the pair keeps mean-reverting:{' '}
            <span className="font-medium text-gray-100">
              {richA ? `short ${p.asset_a}, long ${p.beta.toFixed(3)}× ${p.asset_b}` : `long ${p.asset_a}, short ${p.beta.toFixed(3)}× ${p.asset_b}`}
            </span>
            {halfLife != null && <> · closing half the gap typically takes about {halfLife.toFixed(1)} days</>}. A fast, large move can also mean the
            relationship broke: check the pair before acting. Research tool, not advice.
          </>
        ) : (
          <>
            Inside the normal range (|z| {Math.abs(p.zscore).toFixed(2)} &lt; {threshold.toFixed(1)}): no signal. The monitor flags the pair at |z| ≥ {threshold.toFixed(1)}.
          </>
        )}
      </div>

      {showHistory && <Sparkline assetA={p.asset_a} assetB={p.asset_b} active />}
    </div>
  );
};

interface LiveMonitorProps {
  dailyPairs?: PairResult[];
  /** the z-score history is kept in backend memory: hide it on stateless (serverless) hosts */
  showHistory?: boolean;
}

const LiveMonitor: React.FC<LiveMonitorProps> = ({ dailyPairs, showHistory = true }) => {
  const [expanded, setExpanded] = useState<string | null>(null);

  const { data: snapshot, isLoading } = useQuery({
    queryKey: ['live-snapshot'],
    queryFn: () => api.getLiveSnapshot(),
    refetchInterval: 5000,
    staleTime: 3000,
  });

  const pairs = snapshot?.pairs || [];
  const threshold = snapshot?.alert_threshold ?? 2.5;
  const unusualCount = pairs.filter((p) => p.is_unusual).length;

  const lastUpdate = snapshot?.last_update
    ? new Date(snapshot.last_update).toLocaleTimeString('en-US', { hour12: false })
    : '—';

  const toggleExpand = (key: string) => {
    setExpanded((prev) => (prev === key ? null : key));
  };

  return (
    <div className="space-y-4">
      {/* Header bar */}
      <div className="flex flex-wrap items-center justify-between gap-3 rounded border border-dark-border bg-dark-surface px-4 py-3">
        <div className="flex items-center gap-3">
          <span className={`h-2 w-2 rounded-full ${snapshot?.is_running ? 'bg-accent animate-pulse-dot' : 'bg-muted-dim'}`} />
          <div>
            <div className="text-sm font-medium text-gray-100">Intraday divergence monitor</div>
            <div className="text-2xs text-muted">
              Live spread z-score vs. daily fit · refresh {snapshot?.interval_seconds ?? 15}s · updated {lastUpdate}
            </div>
          </div>
        </div>
        <div className="flex items-center gap-4 text-2xs text-muted">
          <div>
            Alert threshold <span className="font-mono text-gray-200">|z| ≥ {threshold.toFixed(1)}</span>
          </div>
          <div className={`rounded px-2 py-1 font-mono ${unusualCount > 0 ? 'bg-negative/10 text-negative' : 'bg-dark-raised text-muted'}`}>
            {unusualCount} unusual
          </div>
        </div>
      </div>

      {/* Table */}
      <div className="overflow-hidden rounded border border-dark-border bg-dark-surface">
        {isLoading ? (
          <div className="p-10 text-center text-sm text-muted">Loading live data…</div>
        ) : pairs.length === 0 ? (
          <div className="p-10 text-center">
            <p className="text-sm text-muted">No live data yet</p>
            <p className="mt-1 text-2xs text-muted-dim">
              The monitor tracks the top pairs from the latest daily screen — run a screening pass first.
            </p>
          </div>
        ) : (
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-dark-border text-2xs uppercase tracking-wider text-muted">
                <th className="px-4 py-2.5 text-left font-medium">Pair</th>
                <th className="px-4 py-2.5 text-right font-medium">Live z</th>
                <th className="px-4 py-2.5 text-right font-medium">Daily z</th>
                <th className="px-4 py-2.5 text-right font-medium">Price A</th>
                <th className="px-4 py-2.5 text-right font-medium">Price B</th>
                <th className="px-4 py-2.5 text-right font-medium">Beta</th>
                <th className="px-4 py-2.5 text-right font-medium">Status</th>
              </tr>
            </thead>
            <tbody>
              {pairs.map((p: LivePairSnapshot) => {
                const key = `${p.asset_a}_${p.asset_b}`;
                const isExpanded = expanded === key;
                return (
                  <React.Fragment key={key}>
                    <tr
                      onClick={() => toggleExpand(key)}
                      className="cursor-pointer border-b border-dark-divider last:border-b-0 hover:bg-dark-raised"
                    >
                      <td className="px-4 py-2.5 font-medium text-gray-100">
                        {p.asset_a}/{p.asset_b}
                      </td>
                      <td className={`px-4 py-2.5 text-right font-mono ${zColor(p.zscore, threshold)}`}>
                        {fmtZ(p.zscore)}
                      </td>
                      <td className="px-4 py-2.5 text-right font-mono text-muted">
                        {fmtZ(p.daily_zscore)}
                      </td>
                      <td className="px-4 py-2.5 text-right font-mono text-gray-300">{fmtPrice(p.price_a)}</td>
                      <td className="px-4 py-2.5 text-right font-mono text-gray-300">{fmtPrice(p.price_b)}</td>
                      <td className="px-4 py-2.5 text-right font-mono text-muted">{p.beta.toFixed(3)}</td>
                      <td className="px-4 py-2.5 text-right">
                        {p.is_unusual ? (
                          <span className="rounded bg-negative/10 px-2 py-0.5 text-2xs font-medium text-negative">
                            extreme
                          </span>
                        ) : Math.abs(p.zscore) >= threshold * 0.7 ? (
                          <span className="rounded bg-warn/10 px-2 py-0.5 text-2xs font-medium text-warn">
                            elevated
                          </span>
                        ) : (
                          <span className="rounded bg-dark-raised px-2 py-0.5 text-2xs font-medium text-muted">
                            normal
                          </span>
                        )}
                      </td>
                    </tr>
                    {isExpanded && (
                      <tr className="border-b border-dark-divider last:border-b-0 bg-dark-bg/40">
                        <td colSpan={7}>
                          <PairDetailCard
                            p={p}
                            daily={dailyPairs?.find((d) => d.asset_a === p.asset_a && d.asset_b === p.asset_b)}
                            threshold={threshold}
                            showHistory={showHistory}
                          />
                        </td>
                      </tr>
                    )}
                  </React.Fragment>
                );
              })}
            </tbody>
          </table>
        )}
      </div>
    </div>
  );
};

export default LiveMonitor;
