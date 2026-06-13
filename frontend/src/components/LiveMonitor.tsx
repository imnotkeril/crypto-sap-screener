import React, { useState } from 'react';
import { useQuery } from 'react-query';
import { LineChart, Line, ResponsiveContainer, YAxis } from 'recharts';
import { api, LivePairSnapshot } from '../services/api';

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
  const { data } = useQuery(
    ['live-history', assetA, assetB],
    () => api.getLivePairHistory(assetA, assetB),
    { enabled: active, refetchInterval: active ? 5000 : false, staleTime: 4000 }
  );

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

const LiveMonitor: React.FC = () => {
  const [expanded, setExpanded] = useState<string | null>(null);

  const { data: snapshot, isLoading } = useQuery(
    'live-snapshot',
    api.getLiveSnapshot,
    { refetchInterval: 5000, staleTime: 3000 }
  );

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
                <th className="px-4 py-2.5 text-right font-medium">Δ intraday</th>
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
                      <td className={`px-4 py-2.5 text-right font-mono ${Math.abs(p.zscore_delta) >= 0.5 ? 'text-accent' : 'text-muted'}`}>
                        {fmtZ(p.zscore_delta)}
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
                        <td colSpan={8}>
                          <Sparkline assetA={p.asset_a} assetB={p.asset_b} active={isExpanded} />
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
