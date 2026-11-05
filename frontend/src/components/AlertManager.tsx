import React, { useState } from 'react';
import { useQuery } from 'react-query';
import { api } from '../services/api';

interface Alert {
  alert_id: number;
  pair_id: number;
  asset_a: string;
  asset_b: string;
  threshold_high: number | null;
  threshold_low: number | null;
  enabled: boolean;
  last_triggered: string | null;
  trigger_count: number;
}

interface TriggeredAlert extends Alert {
  current_zscore: number;
}

const AlertManager: React.FC = () => {
  const [isOpen, setIsOpen] = useState(false);
  const [showCreateForm, setShowCreateForm] = useState(false);
  const [newAlert, setNewAlert] = useState({
    pair_id: 0,
    asset_a: '',
    asset_b: '',
    threshold_high: 2.0,
    threshold_low: -2.0,
  });

  // Fetch alerts
  const { data: alertsData, refetch: refetchAlerts } = useQuery(
    'alerts',
    async () => {
      const response = await api.getAlerts();
      return response;
    },
    { refetchInterval: 10000 }
  );

  // Fetch triggered alerts
  const { data: triggeredData } = useQuery(
    'triggered-alerts',
    async () => {
      const response = await api.getTriggeredAlerts();
      return response;
    },
    { refetchInterval: 5000 }
  );

  const alerts: Alert[] = alertsData?.alerts || [];
  const triggered: TriggeredAlert[] = triggeredData?.triggered || [];

  const handleCreateAlert = async () => {
    try {
      await api.createAlert(
        newAlert.pair_id,
        newAlert.asset_a,
        newAlert.asset_b,
        newAlert.threshold_high,
        newAlert.threshold_low
      );
      setShowCreateForm(false);
      setNewAlert({ pair_id: 0, asset_a: '', asset_b: '', threshold_high: 2.0, threshold_low: -2.0 });
      refetchAlerts();
    } catch (error) {
      console.error('Error creating alert:', error);
    }
  };

  const handleDeleteAlert = async (alertId: number) => {
    try {
      await api.deleteAlert(alertId);
      refetchAlerts();
    } catch (error) {
      console.error('Error deleting alert:', error);
    }
  };

  const handleToggleAlert = async (alert: Alert) => {
    try {
      await api.updateAlert(alert.alert_id, undefined, undefined, !alert.enabled);
      refetchAlerts();
    } catch (error) {
      console.error('Error updating alert:', error);
    }
  };

  return (
    <>
      <button
        onClick={() => setIsOpen(true)}
        className="px-4 py-2 text-sm font-medium text-white bg-yellow-500/20 hover:bg-yellow-500/30 border border-yellow-500/50 rounded-lg transition-colors flex items-center gap-2 relative"
      >
        <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15 17h5l-1.405-1.405A2.032 2.032 0 0118 14.158V11a6.002 6.002 0 00-4-5.659V5a2 2 0 10-4 0v.341C7.67 6.165 6 8.388 6 11v3.159c0 .538-.214 1.055-.595 1.436L4 17h5m6 0v1a3 3 0 11-6 0v-1m6 0H9" />
        </svg>
        Alerts
        {triggered.length > 0 && (
          <span className="absolute -top-1 -right-1 bg-red-500 text-white text-xs rounded-full w-5 h-5 flex items-center justify-center">
            {triggered.length}
          </span>
        )}
      </button>

      {isOpen && (
        <div
          className="fixed inset-0 bg-black/80 backdrop-blur-sm z-50 flex items-center justify-center p-4"
          onClick={() => setIsOpen(false)}
        >
          <div
            className="bg-[#111118] border border-[#1a1a24] rounded-xl max-w-4xl w-full max-h-[90vh] overflow-y-auto"
            onClick={(e) => e.stopPropagation()}
          >
            <div className="px-6 py-4 border-b border-[#1a1a24] flex items-center justify-between sticky top-0 bg-[#111118]">
              <h2 className="text-xl font-medium text-white">Alert Manager</h2>
              <button
                onClick={() => setIsOpen(false)}
                className="text-gray-400 hover:text-white transition-colors"
              >
                <svg className="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
                </svg>
              </button>
            </div>

            <div className="p-6 space-y-6">
              {/* Triggered Alerts */}
              {triggered.length > 0 && (
                <div className="bg-red-500/10 border border-red-500/50 rounded-xl p-4">
                  <h3 className="text-lg font-medium text-red-400 mb-3">Triggered Alerts ({triggered.length})</h3>
                  <div className="space-y-2">
                    {triggered.map((alert) => (
                      <div
                        key={alert.alert_id}
                        className="bg-[#1a1a24] border border-red-500/50 rounded-lg p-3"
                      >
                        <div className="flex items-center justify-between">
                          <div>
                            <div className="text-white font-medium">
                              {alert.asset_a} / {alert.asset_b}
                            </div>
                            <div className="text-sm text-gray-400">
                              Z-Score: <span className="text-red-400 font-medium">{alert.current_zscore.toFixed(2)}</span>
                              {alert.threshold_high && alert.current_zscore >= alert.threshold_high && (
                                <span className="ml-2">(≥ {alert.threshold_high})</span>
                              )}
                              {alert.threshold_low && alert.current_zscore <= alert.threshold_low && (
                                <span className="ml-2">(≤ {alert.threshold_low})</span>
                              )}
                            </div>
                            <div className="text-xs text-gray-500 mt-1">
                              Triggered {alert.trigger_count} time(s)
                            </div>
                          </div>
                        </div>
                      </div>
                    ))}
                  </div>
                </div>
              )}

              {/* Create Alert Form */}
              {showCreateForm ? (
                <div className="bg-[#0a0a0f] border border-[#1a1a24] rounded-xl p-4">
                  <h3 className="text-lg font-medium text-white mb-4">Create New Alert</h3>
                  <div className="space-y-4">
                    <div>
                      <label className="block text-sm font-medium text-gray-300 mb-2">Pair ID</label>
                      <input
                        type="number"
                        value={newAlert.pair_id}
                        onChange={(e) => setNewAlert({ ...newAlert, pair_id: parseInt(e.target.value) || 0 })}
                        className="w-full px-4 py-2 bg-[#1a1a24] border border-[#2a2a34] rounded-lg text-white"
                      />
                    </div>
                    <div className="grid grid-cols-2 gap-4">
                      <div>
                        <label className="block text-sm font-medium text-gray-300 mb-2">Asset A</label>
                        <input
                          type="text"
                          value={newAlert.asset_a}
                          onChange={(e) => setNewAlert({ ...newAlert, asset_a: e.target.value })}
                          className="w-full px-4 py-2 bg-[#1a1a24] border border-[#2a2a34] rounded-lg text-white"
                        />
                      </div>
                      <div>
                        <label className="block text-sm font-medium text-gray-300 mb-2">Asset B</label>
                        <input
                          type="text"
                          value={newAlert.asset_b}
                          onChange={(e) => setNewAlert({ ...newAlert, asset_b: e.target.value })}
                          className="w-full px-4 py-2 bg-[#1a1a24] border border-[#2a2a34] rounded-lg text-white"
                        />
                      </div>
                    </div>
                    <div className="grid grid-cols-2 gap-4">
                      <div>
                        <label className="block text-sm font-medium text-gray-300 mb-2">Threshold High</label>
                        <input
                          type="number"
                          step="0.1"
                          value={newAlert.threshold_high}
                          onChange={(e) => setNewAlert({ ...newAlert, threshold_high: parseFloat(e.target.value) || 2.0 })}
                          className="w-full px-4 py-2 bg-[#1a1a24] border border-[#2a2a34] rounded-lg text-white"
                        />
                      </div>
                      <div>
                        <label className="block text-sm font-medium text-gray-300 mb-2">Threshold Low</label>
                        <input
                          type="number"
                          step="0.1"
                          value={newAlert.threshold_low}
                          onChange={(e) => setNewAlert({ ...newAlert, threshold_low: parseFloat(e.target.value) || -2.0 })}
                          className="w-full px-4 py-2 bg-[#1a1a24] border border-[#2a2a34] rounded-lg text-white"
                        />
                      </div>
                    </div>
                    <div className="flex gap-3">
                      <button
                        onClick={handleCreateAlert}
                        className="flex-1 px-4 py-2 bg-emerald-500 hover:bg-emerald-600 text-white font-medium rounded-lg transition-colors"
                      >
                        Create Alert
                      </button>
                      <button
                        onClick={() => setShowCreateForm(false)}
                        className="px-4 py-2 bg-[#1a1a24] hover:bg-[#2a2a34] text-gray-300 font-medium rounded-lg transition-colors"
                      >
                        Cancel
                      </button>
                    </div>
                  </div>
                </div>
              ) : (
                <button
                  onClick={() => setShowCreateForm(true)}
                  className="w-full px-4 py-2 bg-emerald-500/20 hover:bg-emerald-500/30 border border-emerald-500/50 rounded-lg text-emerald-400 font-medium transition-colors"
                >
                  + Create New Alert
                </button>
              )}

              {/* Active Alerts List */}
              <div>
                <h3 className="text-lg font-medium text-white mb-3">Active Alerts ({alerts.length})</h3>
                {alerts.length === 0 ? (
                  <div className="text-center text-gray-400 py-8">
                    No alerts configured. Create one to get notified when Z-Score crosses thresholds.
                  </div>
                ) : (
                  <div className="space-y-2">
                    {alerts.map((alert) => (
                      <div
                        key={alert.alert_id}
                        className={`bg-[#0a0a0f] border rounded-lg p-4 ${alert.enabled ? 'border-[#1a1a24]' : 'border-gray-800 opacity-50'}`}
                      >
                        <div className="flex items-center justify-between">
                          <div className="flex-1">
                            <div className="flex items-center gap-2 mb-1">
                              <span className="text-white font-medium">
                                {alert.asset_a} / {alert.asset_b}
                              </span>
                              <span className="text-xs px-2 py-1 rounded bg-[#1a1a24] text-gray-400">
                                Pair #{alert.pair_id}
                              </span>
                              {!alert.enabled && (
                                <span className="text-xs px-2 py-1 rounded bg-gray-800 text-gray-500">
                                  Disabled
                                </span>
                              )}
                            </div>
                            <div className="text-sm text-gray-400">
                              {alert.threshold_high && (
                                <span>High: ≥ {alert.threshold_high.toFixed(2)}</span>
                              )}
                              {alert.threshold_high && alert.threshold_low && <span className="mx-2">|</span>}
                              {alert.threshold_low && (
                                <span>Low: ≤ {alert.threshold_low.toFixed(2)}</span>
                              )}
                            </div>
                            {alert.last_triggered && (
                              <div className="text-xs text-gray-500 mt-1">
                                Last triggered: {new Date(alert.last_triggered).toLocaleString()}
                                {alert.trigger_count > 0 && ` (${alert.trigger_count} times)`}
                              </div>
                            )}
                          </div>
                          <div className="flex items-center gap-2">
                            <button
                              onClick={() => handleToggleAlert(alert)}
                              className={`px-3 py-1 text-xs rounded-lg transition-colors ${
                                alert.enabled
                                  ? 'bg-emerald-500/20 text-emerald-400 hover:bg-emerald-500/30'
                                  : 'bg-gray-800 text-gray-500 hover:bg-gray-700'
                              }`}
                            >
                              {alert.enabled ? 'Disable' : 'Enable'}
                            </button>
                            <button
                              onClick={() => handleDeleteAlert(alert.alert_id)}
                              className="px-3 py-1 text-xs bg-red-500/20 text-red-400 hover:bg-red-500/30 rounded-lg transition-colors"
                            >
                              Delete
                            </button>
                          </div>
                        </div>
                      </div>
                    ))}
                  </div>
                )}
              </div>
            </div>
          </div>
        </div>
      )}
    </>
  );
};

export default AlertManager;

