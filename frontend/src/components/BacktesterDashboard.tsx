import React, { useState } from 'react';
import { useMutation, useQuery } from '@tanstack/react-query';
import { api } from '../services/api';
import BacktestResults from './BacktestResults';

const BacktesterDashboard: React.FC = () => {
  const [formData, setFormData] = useState({
    asset_a: '',
    asset_b: '',
    entry_threshold: 2.0,
    exit_threshold: 0.0,
    stop_loss: null as number | null,
    take_profit: null as number | null,
    initial_capital: 10000,
    lookback_days: 365,
    beta: null as number | null,
  });
  const [selectedSessionId, setSelectedSessionId] = useState<number | null>(null);

  const { data: sessions } = useQuery({
    queryKey: ['backtest-sessions'],
    queryFn: () => api.getBacktestSessions(),
    refetchInterval: 30000,
  });

  const runBacktestMutation = useMutation({
    mutationFn: (data: any) => api.runBacktest(data),
    onSuccess: (data) => {
      setSelectedSessionId(data.session_id);
    },
  });

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    runBacktestMutation.mutate(formData);
  };

  return (
    <div className="bg-[#111118] border border-[#1a1a24] rounded-xl p-6 space-y-6">
      <h2 className="text-xl font-medium text-white">Backtester</h2>

      <form onSubmit={handleSubmit} className="space-y-4">
        <div className="grid grid-cols-2 gap-4">
          <div>
            <label className="block text-sm font-medium text-gray-300 mb-2">Asset A</label>
            <input
              type="text"
              value={formData.asset_a}
              onChange={(e) => setFormData({ ...formData, asset_a: e.target.value })}
              className="w-full px-4 py-2 bg-[#1a1a24] border border-[#2a2a34] rounded-lg text-white"
              required
            />
          </div>
          <div>
            <label className="block text-sm font-medium text-gray-300 mb-2">Asset B</label>
            <input
              type="text"
              value={formData.asset_b}
              onChange={(e) => setFormData({ ...formData, asset_b: e.target.value })}
              className="w-full px-4 py-2 bg-[#1a1a24] border border-[#2a2a34] rounded-lg text-white"
              required
            />
          </div>
        </div>

        <div className="grid grid-cols-2 gap-4">
          <div>
            <label className="block text-sm font-medium text-gray-300 mb-2">Entry Threshold</label>
            <input
              type="number"
              step="0.1"
              value={formData.entry_threshold}
              onChange={(e) => setFormData({ ...formData, entry_threshold: parseFloat(e.target.value) })}
              className="w-full px-4 py-2 bg-[#1a1a24] border border-[#2a2a34] rounded-lg text-white"
            />
          </div>
          <div>
            <label className="block text-sm font-medium text-gray-300 mb-2">Exit Threshold</label>
            <input
              type="number"
              step="0.1"
              value={formData.exit_threshold}
              onChange={(e) => setFormData({ ...formData, exit_threshold: parseFloat(e.target.value) })}
              className="w-full px-4 py-2 bg-[#1a1a24] border border-[#2a2a34] rounded-lg text-white"
            />
          </div>
        </div>

        <div className="grid grid-cols-2 gap-4">
          <div>
            <label className="block text-sm font-medium text-gray-300 mb-2">Initial Capital</label>
            <input
              type="number"
              value={formData.initial_capital}
              onChange={(e) => setFormData({ ...formData, initial_capital: parseFloat(e.target.value) })}
              className="w-full px-4 py-2 bg-[#1a1a24] border border-[#2a2a34] rounded-lg text-white"
            />
          </div>
          <div>
            <label className="block text-sm font-medium text-gray-300 mb-2">Lookback Days</label>
            <input
              type="number"
              value={formData.lookback_days}
              onChange={(e) => setFormData({ ...formData, lookback_days: parseInt(e.target.value) })}
              className="w-full px-4 py-2 bg-[#1a1a24] border border-[#2a2a34] rounded-lg text-white"
            />
          </div>
        </div>

        <button
          type="submit"
          disabled={runBacktestMutation.isPending}
          className="w-full px-4 py-2 bg-emerald-500 hover:bg-emerald-600 text-white font-medium rounded-lg transition-colors disabled:opacity-50"
        >
          {runBacktestMutation.isPending ? 'Running Backtest...' : 'Run Backtest'}
        </button>
      </form>

      {selectedSessionId && (
        <BacktestResults sessionId={selectedSessionId} />
      )}

      {sessions && sessions.sessions && sessions.sessions.length > 0 && (
        <div>
          <h3 className="text-lg font-medium text-white mb-3">Previous Sessions</h3>
          <div className="space-y-2">
            {sessions.sessions.map((session: any) => (
              <div
                key={session.id}
                onClick={() => setSelectedSessionId(session.id)}
                className="bg-[#0a0a0f] border border-[#1a1a24] rounded-lg p-3 cursor-pointer hover:border-emerald-500/50 transition-colors"
              >
                <div className="text-white font-medium">
                  {session.asset_a} / {session.asset_b}
                </div>
                <div className="text-sm text-gray-400">
                  Return: {session.metrics?.total_return?.toFixed(2)}% | 
                  Sharpe: {session.metrics?.sharpe_ratio?.toFixed(2)} | 
                  Trades: {session.metrics?.total_trades}
                </div>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
};

export default BacktesterDashboard;

