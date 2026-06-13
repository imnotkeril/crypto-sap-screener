import React, { useState, useEffect } from 'react';
import { useQuery, useQueryClient } from 'react-query';
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
  const [isStarting, setIsStarting] = useState(false);
  const [activeTab, setActiveTab] = useState<Tab>('screener');
  const queryClient = useQueryClient();

  useEffect(() => {
    const autoStartTimer = setTimeout(async () => {
      try {
        const statusData = queryClient.getQueryData('screening-status') as any;
        const resultsData = queryClient.getQueryData('screening-results') as any;
        const hasData = resultsData?.results?.length > 0 || false;
        const isRunning = statusData?.is_running || false;

        if (!hasData && !isRunning) {
          await api.runLiveScreening();
          queryClient.invalidateQueries('screening-status');
          queryClient.invalidateQueries('screening-results');
        }
      } catch (error) {
        console.error('Error auto-starting screening:', error);
      }
    }, 2000);

    return () => clearTimeout(autoStartTimer);
  }, [queryClient]);

  const { data: status, error: statusError } = useQuery(
    'screening-status',
    api.getStatus,
    {
      refetchInterval: 10000,
      refetchOnWindowFocus: false,
      staleTime: 5000,
      retry: 1,
    }
  );

  const { data: results, isLoading: resultsLoading } = useQuery(
    'screening-results',
    () => api.getResults(100),
    {
      refetchInterval: () => {
        try {
          const statusData = queryClient.getQueryData('screening-status') as any;
          const isRunning = statusData?.is_running || false;
          const resultsData = queryClient.getQueryData('screening-results') as any;
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
      onSuccess: () => {
        setLastUpdate(new Date());
      },
    }
  );

  const { data: stats } = useQuery('statistics', api.getStatistics, {
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

  const handleRunScreening = async () => {
    setIsStarting(true);
    try {
      await api.runLiveScreening();
      queryClient.invalidateQueries('screening-status');
      queryClient.invalidateQueries('screening-results');
      queryClient.invalidateQueries('statistics');
      setTimeout(() => setIsStarting(false), 2000);
    } catch (error) {
      console.error('Error starting screening:', error);
      setIsStarting(false);
      alert('Failed to start screening. Please check console for details.');
    }
  };

  const isRunning = !!status?.is_running;

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
            <button
              onClick={handleRunScreening}
              disabled={isStarting || isRunning}
              className="flex items-center gap-2 rounded border border-dark-border bg-dark-surface px-3 py-2 text-sm font-medium text-gray-100 transition-colors hover:border-accent/40 hover:text-accent disabled:cursor-not-allowed disabled:opacity-50"
            >
              {isStarting ? (
                <>
                  <Spinner className="h-3.5 w-3.5" />
                  Starting…
                </>
              ) : isRunning ? (
                <>
                  <span className="h-2 w-2 rounded-full bg-accent animate-pulse-dot" />
                  Running…
                </>
              ) : (
                <>
                  <svg className="h-4 w-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M14.752 11.168l-3.197-2.132A1 1 0 0010 9.87v4.263a1 1 0 001.555.832l3.197-2.132a1 1 0 000-1.664z" />
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
                  </svg>
                  Run screening
                </>
              )}
            </button>

            <AlertManager />
            <ScreenerSettings
              onSettingsApplied={() => {
                queryClient.invalidateQueries('screening-results');
                queryClient.invalidateQueries('screening-status');
                queryClient.invalidateQueries('statistics');
              }}
            />

            <div className="ml-1 hidden flex-col items-end text-2xs text-muted-dim sm:flex">
              <span className="text-muted">Updated {formatTime(lastUpdate)}</span>
            </div>
          </div>
        </header>

        {statusError && (
          <div className="mb-5 rounded border border-warn/30 bg-warn/5 px-4 py-3 text-sm text-warn">
            Cannot connect to backend API. Please ensure the backend server is running on http://localhost:8000
          </div>
        )}

        {/* Tabs */}
        <nav className="mb-5 flex gap-1 border-b border-dark-border">
          {TABS.map((tab) => (
            <button
              key={tab.id}
              onClick={() => setActiveTab(tab.id)}
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
            {stats && <StatisticsPanel stats={stats} />}

            {resultsLoading ? (
              <div className="rounded border border-dark-border bg-dark-surface p-12 text-center">
                <Spinner className="mx-auto h-6 w-6" />
                <p className="mt-3 text-sm text-muted">Scanning pairs…</p>
              </div>
            ) : results && results.results.length > 0 ? (
              <PairsTable pairs={results.results} />
            ) : (
              <div className="rounded border border-dark-border bg-dark-surface p-12 text-center">
                <Spinner className="mx-auto h-6 w-6" />
                <p className="mt-3 text-sm text-muted">Initializing screener…</p>
                <p className="mt-1 text-2xs text-muted-dim">First scan may take a few minutes</p>
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

        {activeTab === 'live' && <LiveMonitor />}

        {activeTab === 'trends' && <TrendsDashboard />}

        {/* Footer */}
        <div className="mt-8 text-center text-2xs text-muted-dim">
          Auto-screening runs continuously · last scan{' '}
          {status?.last_session?.completed_at
            ? new Date(status.last_session.completed_at).toLocaleTimeString()
            : 'never'}
        </div>
      </div>
    </div>
  );
};

export default ScreenerDashboard;
