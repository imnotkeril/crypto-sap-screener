import React, { useState, useEffect } from 'react';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { api } from '../services/api';
import PairsTable from './PairsTable';
import StatisticsPanel from './StatisticsPanel';
import CorrelationHeatmap from './CorrelationHeatmap';
import ScreenerSettings from './ScreenerSettings';
import AlertManager from './AlertManager';
import TrendsDashboard from './TrendsDashboard';
import LiveMonitor from './LiveMonitor';

type Tab = 'screener' | 'live' | 'trends';

const TABS: { id: Tab; label: string }[] = [
  { id: 'screener', label: 'Screener' },
  { id: 'live', label: 'Live monitor' },
  { id: 'trends', label: 'Trends' },
];

const Spinner: React.FC<{ className?: string }> = ({ className = 'h-4 w-4' }) => (
  <div className={`${className} animate-spin rounded-full border-2 border-accent border-t-transparent`} />
);

const ScreenerDashboard: React.FC = () => {
  const [lastUpdate, setLastUpdate] = useState<Date>(new Date());
  const [tf, setTf] = useState<'1d' | '1h'>('1d');
  const [activeTab, setActiveTab] = useState<Tab>('screener');
  const queryClient = useQueryClient();

  const { data: status, error: statusError } = useQuery({
    queryKey: ['screening-status'],
    queryFn: () => api.getStatus(),
    refetchInterval: 10000,
    refetchOnWindowFocus: false,
    staleTime: 5000,
    retry: 1,
  });

  const { data: results, isLoading: resultsLoading, dataUpdatedAt } = useQuery({
    queryKey: ['screening-results', tf],
    queryFn: () => api.getResults(100, undefined, 'correlation', tf),
      refetchInterval: () => {
        try {
          const statusData = queryClient.getQueryData(['screening-status']) as any;
          const isRunning = statusData?.is_running || false;
          const resultsData = queryClient.getQueryData(['screening-results', tf]) as any;
          const hasData = resultsData?.results?.length > 0 || false;

          if (isRunning) return 10000;
          if (hasData) return 30000;
          return 15000;
        } catch (error) {
          console.warn('Error in refetchInterval:', error);
          return 15000;
        }
      },
      enabled: true,
      retry: 1,
      retryDelay: 2000,
      staleTime: 8000,
  });

  const { data: dailyResults } = useQuery({
    queryKey: ['screening-results', '1d'],
    queryFn: () => api.getResults(100, undefined, 'correlation', '1d'),
    staleTime: 30000,
    enabled: activeTab === 'live' || tf === '1d',
  });

  useEffect(() => {
    if (dataUpdatedAt) setLastUpdate(new Date(dataUpdatedAt));
  }, [dataUpdatedAt]);

  const { data: stats } = useQuery({
    queryKey: ['statistics'],
    queryFn: () => api.getStatistics(),
    refetchInterval: 15000,
    staleTime: 10000,
  });

  useEffect(() => {
    const interval = setInterval(() => {
      setLastUpdate(new Date());
    }, 1000);
    return () => clearInterval(interval);
  }, []);

  const formatTime = (date: Date) =>
    date.toLocaleTimeString('en-US', { hour12: false, hour: '2-digit', minute: '2-digit', second: '2-digit' });

  const isRunning = !!status?.is_running;
  const demo = !!status?.demo_mode;

  return (
    <div className="min-h-screen bg-dark-bg text-gray-200">
      <div className="mx-auto max-w-[1600px] px-6 py-8">
        {/* Header */}
        <header className="mb-6 flex flex-wrap items-start justify-between gap-4">
          <div>
            <h1 className="text-2xl font-semibold tracking-tight text-white">SAP Screener</h1>
            <p className="mt-1 text-sm text-muted">Statistical arbitrage pairs · cointegration &amp; mean reversion</p>
          </div>

          <div className="flex flex-wrap items-center gap-2">
            {isRunning && (
              <span className="flex items-center gap-2 rounded border border-dark-border bg-dark-surface px-3 py-2 text-sm text-gray-100">
                <span className="h-2 w-2 rounded-full bg-accent animate-pulse-dot" />
                Running…
              </span>
            )}
            <AlertManager />
            {!demo && (
            <ScreenerSettings
              onSettingsApplied={() => {
                queryClient.invalidateQueries({ queryKey: ['screening-results'] });
                queryClient.invalidateQueries({ queryKey: ['screening-status'] });
                queryClient.invalidateQueries({ queryKey: ['statistics'] });
              }}
            />
            )}

            <div className="ml-1 hidden flex-col items-end text-2xs text-muted-dim sm:flex">
              <span className="text-muted">Updated {formatTime(lastUpdate)}</span>
            </div>
          </div>
        </header>

        {!!statusError && (
          <div className="mb-5 rounded border border-warn/30 bg-warn/5 px-4 py-3 text-sm text-warn">
            Cannot connect to backend API. Please ensure the backend server is running on http://localhost:8000
          </div>
        )}

        {/* Tabs */}
        <nav aria-label="Sections" className="mb-5 flex gap-1 border-b border-dark-border">
          {TABS.map((tab) => (
            <button
              key={tab.id}
              onClick={() => setActiveTab(tab.id)}
              aria-current={activeTab === tab.id ? 'page' : undefined}
              className={`px-3 py-2 text-sm font-medium transition-colors border-b-2 -mb-px ${
                activeTab === tab.id
                  ? 'border-accent text-white'
                  : 'border-transparent text-muted hover:text-gray-200'
              }`}
            >
              {tab.label}
            </button>
          ))}
        </nav>

        {activeTab === 'screener' && (
          <div className="space-y-5">
            {demo && (
              <div className="rounded border border-dark-border bg-dark-surface px-4 py-3 text-2xs text-muted">
                Public demo: results are refreshed by scheduled scans (daily: 60 assets, 365-day window; hourly: 30 assets,
                30-day window). Manual runs are disabled here; run your own copy to change settings.
              </div>
            )}
            <div className="flex items-center gap-2" role="group" aria-label="Scan timeframe">
              {([['1d', 'Daily'], ['1h', 'Hourly']] as const).map(([value, label]) => (
                <button
                  key={value}
                  onClick={() => setTf(value)}
                  aria-pressed={tf === value}
                  className={`rounded border px-3 py-1.5 text-xs font-medium transition-colors ${
                    tf === value
                      ? 'border-accent/50 bg-accent/10 text-accent'
                      : 'border-dark-border text-muted hover:text-gray-200'
                  }`}
                >
                  {label}
                </button>
              ))}
              {tf === '1h' && (
                <span className="text-2xs text-muted-dim">
                  Hourly scan · mean reversion over hours to days · details are available for daily pairs
                </span>
              )}
            </div>
            {tf === '1d' && stats && <StatisticsPanel stats={stats} />}

            {resultsLoading ? (
              <div className="rounded border border-dark-border bg-dark-surface p-12 text-center">
                <Spinner className="mx-auto h-6 w-6" />
                <p className="mt-3 text-sm text-muted">Scanning pairs…</p>
              </div>
            ) : results && results.results.length > 0 ? (
              <PairsTable pairs={results.results} detailsEnabled={tf === '1d'} />
            ) : (
              <div className="rounded border border-dark-border bg-dark-surface p-12 text-center">
                {demo || tf === '1h' ? (
                  <>
                    <p className="text-sm text-muted">No pairs in the latest {tf === '1h' ? 'hourly' : 'daily'} scan</p>
                    <p className="mt-1 text-2xs text-muted-dim">
                      {demo ? 'The next scheduled scan will refresh this.' : 'Run a screening from the Run screening button.'}
                    </p>
                  </>
                ) : (
                  <>
                    <p className="text-sm text-muted">No results yet</p>
                    <p className="mt-1 text-2xs text-muted-dim">
                      Click <span className="text-gray-300">Run screening</span> to scan the market (a first daily scan takes a few minutes).
                    </p>
                  </>
                )}
              </div>
            )}

            {results && results.results.length > 0 ? (
              <CorrelationHeatmap pairs={results.results} />
            ) : (
              <div className="rounded border border-dark-border bg-dark-surface p-6 text-center">
                <p className="text-2xs text-muted-dim">Waiting for data…</p>
              </div>
            )}
          </div>
        )}

        {activeTab === 'live' && <LiveMonitor dailyPairs={dailyResults?.results} />}

        {activeTab === 'trends' && <TrendsDashboard />}

        {/* Footer */}
        <div className="mt-8 text-center text-2xs text-muted-dim">
          {demo ? 'Demo · scheduled scans' : 'Screening runs on request'} · last scan{' '}
          {status?.last_session?.completed_at
            ? new Date(status.last_session.completed_at.endsWith('Z') ? status.last_session.completed_at : status.last_session.completed_at + 'Z').toLocaleString()
            : 'never'}
        </div>
      </div>
    </div>
  );
};

export default ScreenerDashboard;
