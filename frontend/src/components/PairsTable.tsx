import React, { useState, useMemo, useEffect } from 'react';
import { createPortal } from 'react-dom';
import { PairResult, api } from '../services/api';
import SpreadChart from './SpreadChart';
import PairDetails from './PairDetails';
import PriceChart from './PriceChart';

interface PairsTableProps {
  pairs: PairResult[];
}

type SortField = 'correlation' | 'adf_pvalue' | 'beta' | 'spread_std' | 'hurst_exponent' | 'pair' | 'composite_score';
type SortDirection = 'asc' | 'desc';

const PairsTable: React.FC<PairsTableProps> = ({ pairs }) => {
  const [selectedPair, setSelectedPair] = useState<PairResult | null>(null);
  const [spreadData, setSpreadData] = useState<any>(null);
  const [loadingChart, setLoadingChart] = useState(false);
  const [showModal, setShowModal] = useState(false);
  
  // Filter states
  const [minCorrelation, setMinCorrelation] = useState<number>(0.8);
  const [maxADFPValue, setMaxADFPValue] = useState<number>(0.1);
  const [minHurst, setMinHurst] = useState<number | null>(null);
  const [maxHurst, setMaxHurst] = useState<number | null>(null);
  const [minZScore, setMinZScore] = useState<number | null>(null);
  const [maxZScore, setMaxZScore] = useState<number | null>(null);
  const [minBeta, setMinBeta] = useState<number | null>(null);
  const [maxBeta, setMaxBeta] = useState<number | null>(null);
  const [minSpreadStd, setMinSpreadStd] = useState<number | null>(null);
  const [maxSpreadStd, setMaxSpreadStd] = useState<number | null>(null);
  const [showFilters, setShowFilters] = useState(false);
  
  // Sort state
  const [sortField, setSortField] = useState<SortField>('composite_score');
  const [sortDirection, setSortDirection] = useState<SortDirection>('desc');
  
  // Pagination state
  const [currentPage, setCurrentPage] = useState<number>(1);
  const itemsPerPage = 20;

  const handlePairClick = async (pair: PairResult) => {
    // Save current scroll position
    const scrollY = window.scrollY;
    
    setSelectedPair(pair);
    setShowModal(true);
    setLoadingChart(true);
    
    try {
      const data = await api.getPairSpreadData(pair.id);
      setSpreadData(data);
    } catch (error) {
      console.error('Error loading spread data:', error);
      setSpreadData(null);
    } finally {
      setLoadingChart(false);
    }
    
    // Restore scroll position after modal opens
    setTimeout(() => {
      window.scrollTo(0, scrollY);
    }, 0);
  };

  const closeModal = () => {
    setShowModal(false);
    setSelectedPair(null);
    setSpreadData(null);
  };

  const handleExportCSV = async () => {
    try {
      const response = await api.exportResultsCSV(filteredAndSortedPairs.length);
      const blob = new Blob([response], { type: 'text/csv' });
      const url = window.URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = `pairs_screener_${new Date().toISOString().split('T')[0]}.csv`;
      document.body.appendChild(a);
      a.click();
      window.URL.revokeObjectURL(url);
      document.body.removeChild(a);
    } catch (error) {
      console.error('Error exporting CSV:', error);
    }
  };

  const handleExportExcel = async () => {
    try {
      const response = await api.exportResultsExcel(filteredAndSortedPairs.length);
      const blob = new Blob([response], { type: 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet' });
      const url = window.URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = `pairs_screener_${new Date().toISOString().split('T')[0]}.xlsx`;
      document.body.appendChild(a);
      a.click();
      window.URL.revokeObjectURL(url);
      document.body.removeChild(a);
    } catch (error) {
      console.error('Error exporting Excel:', error);
    }
  };

  const handleSort = (field: SortField) => {
    if (sortField === field) {
      setSortDirection(sortDirection === 'asc' ? 'desc' : 'asc');
    } else {
      setSortField(field);
      setSortDirection('desc');
    }
  };

  // Filter and sort pairs
  const filteredAndSortedPairs = useMemo(() => {
    let filtered = pairs.filter(pair => {
      if (pair.correlation < minCorrelation) return false;
      if (pair.adf_pvalue > maxADFPValue) return false;
      if (minHurst !== null && (pair.hurst_exponent === null || pair.hurst_exponent < minHurst)) return false;
      if (maxHurst !== null && (pair.hurst_exponent === null || pair.hurst_exponent > maxHurst)) return false;
      if (minZScore !== null && (pair.current_zscore === null || pair.current_zscore === undefined || pair.current_zscore < minZScore)) return false;
      if (maxZScore !== null && (pair.current_zscore === null || pair.current_zscore === undefined || pair.current_zscore > maxZScore)) return false;
      if (minBeta !== null && pair.beta < minBeta) return false;
      if (maxBeta !== null && pair.beta > maxBeta) return false;
      if (minSpreadStd !== null && pair.spread_std < minSpreadStd) return false;
      if (maxSpreadStd !== null && pair.spread_std > maxSpreadStd) return false;
      return true;
    });

    // Sort
    filtered.sort((a, b) => {
      let aVal: number | string;
      let bVal: number | string;

      switch (sortField) {
        case 'composite_score':
          aVal = a.composite_score ?? 0;
          bVal = b.composite_score ?? 0;
          break;
        case 'correlation':
          aVal = a.correlation;
          bVal = b.correlation;
          break;
        case 'adf_pvalue':
          aVal = a.adf_pvalue;
          bVal = b.adf_pvalue;
          break;
        case 'beta':
          aVal = a.beta;
          bVal = b.beta;
          break;
        case 'spread_std':
          aVal = a.spread_std;
          bVal = b.spread_std;
          break;
        case 'hurst_exponent':
          aVal = a.hurst_exponent ?? 0;
          bVal = b.hurst_exponent ?? 0;
          break;
        case 'pair':
          aVal = `${a.asset_a}/${a.asset_b}`;
          bVal = `${b.asset_a}/${b.asset_b}`;
          break;
        default:
          return 0;
      }

      if (typeof aVal === 'string' && typeof bVal === 'string') {
        return sortDirection === 'asc' 
          ? aVal.localeCompare(bVal)
          : bVal.localeCompare(aVal);
      }

      return sortDirection === 'asc'
        ? (aVal as number) - (bVal as number)
        : (bVal as number) - (aVal as number);
    });

    return filtered;
  }, [pairs, minCorrelation, maxADFPValue, minHurst, maxHurst, minZScore, maxZScore, minBeta, maxBeta, minSpreadStd, maxSpreadStd, sortField, sortDirection]);

  // Pagination
  const totalPages = Math.ceil(filteredAndSortedPairs.length / itemsPerPage);
  const startIndex = (currentPage - 1) * itemsPerPage;
  const endIndex = startIndex + itemsPerPage;
  const paginatedPairs = filteredAndSortedPairs.slice(startIndex, endIndex);

  // Reset to first page when filters change
  useEffect(() => {
    setCurrentPage(1);
  }, [minCorrelation, maxADFPValue, minHurst, maxHurst, minZScore, maxZScore, minBeta, maxBeta, minSpreadStd, maxSpreadStd, sortField, sortDirection]);

  const formatNumber = (num: number, decimals: number = 4) => {
    return num.toFixed(decimals);
  };

  const getCorrelationColor = (corr: number) => {
    if (corr >= 0.90) return 'text-emerald-400';
    if (corr >= 0.85) return 'text-teal-400';
    if (corr >= 0.80) return 'text-blue-400';
    return 'text-gray-400';
  };

  const getADFColor = (pval: number) => {
    if (pval < 0.05) return 'text-emerald-400';
    if (pval < 0.10) return 'text-teal-400';
    return 'text-gray-400';
  };

  const SortIcon = ({ field }: { field: SortField }) => {
    if (sortField !== field) {
      return (
        <svg className="w-3 h-3 text-gray-500" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M7 16V4m0 0L3 8m4-4l4 4m6 0v12m0 0l4-4m-4 4l-4-4" />
        </svg>
      );
    }
    return sortDirection === 'asc' ? (
      <svg className="w-3 h-3 text-emerald-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 15l7-7 7 7" />
      </svg>
    ) : (
      <svg className="w-3 h-3 text-emerald-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 9l-7 7-7-7" />
      </svg>
    );
  };

  return (
    <div className="bg-[#111118] border border-[#1a1a24] rounded-xl overflow-hidden backdrop-blur-sm">
      <div className="px-6 py-4 border-b border-[#1a1a24] bg-[#0a0a0f]/50">
        <div className="flex items-center justify-between mb-3">
          <div>
            <h2 className="text-lg font-medium text-white">Live Pairs</h2>
            <p className="text-xs text-gray-400 mt-1">
              {filteredAndSortedPairs.length} of {pairs.length} pairs
              {totalPages > 1 && ` • Page ${currentPage} of ${totalPages}`}
            </p>
          </div>
          <div className="flex items-center gap-3">
            <button
              onClick={() => setShowFilters(!showFilters)}
              className="px-3 py-1.5 text-xs font-medium text-gray-300 bg-[#1a1a24] hover:bg-[#2a2a34] rounded-lg transition-colors flex items-center gap-2"
            >
              <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M3 4a1 1 0 011-1h16a1 1 0 011 1v2.586a1 1 0 01-.293.707l-6.414 6.414a1 1 0 00-.293.707V17l-4 4v-6.586a1 1 0 00-.293-.707L3.293 7.293A1 1 0 013 6.586V4z" />
              </svg>
              Filters
            </button>
            <div className="flex items-center gap-2">
              <div className="w-2 h-2 bg-emerald-400 rounded-full animate-pulse"></div>
              <span className="text-xs text-emerald-400 font-medium">Active</span>
            </div>
          </div>
        </div>

        {/* Filters Panel */}
        {showFilters && (
          <div className="mt-4 p-4 bg-[#0a0a0f] border border-[#1a1a24] rounded-lg">
            <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-5 gap-4">
              <div>
                <label className="block text-xs text-gray-400 mb-1">Min Correlation</label>
                <input
                  type="number"
                  min="0"
                  max="1"
                  step="0.01"
                  value={minCorrelation}
                  onChange={(e) => setMinCorrelation(parseFloat(e.target.value) || 0)}
                  className="w-full px-3 py-1.5 text-sm bg-[#111118] border border-[#1a1a24] rounded text-white focus:outline-none focus:border-emerald-500"
                />
              </div>
              <div>
                <label className="block text-xs text-gray-400 mb-1">Max ADF p-value</label>
                <input
                  type="number"
                  min="0"
                  max="1"
                  step="0.01"
                  value={maxADFPValue}
                  onChange={(e) => setMaxADFPValue(parseFloat(e.target.value) || 0.1)}
                  className="w-full px-3 py-1.5 text-sm bg-[#111118] border border-[#1a1a24] rounded text-white focus:outline-none focus:border-emerald-500"
                />
              </div>
              <div>
                <label className="block text-xs text-gray-400 mb-1">Min Hurst</label>
                <input
                  type="number"
                  min="0"
                  max="1"
                  step="0.01"
                  value={minHurst ?? ''}
                  onChange={(e) => setMinHurst(e.target.value ? parseFloat(e.target.value) : null)}
                  placeholder="Any"
                  className="w-full px-3 py-1.5 text-sm bg-[#111118] border border-[#1a1a24] rounded text-white focus:outline-none focus:border-emerald-500"
                />
              </div>
              <div>
                <label className="block text-xs text-gray-400 mb-1">Max Hurst</label>
                <input
                  type="number"
                  min="0"
                  max="1"
                  step="0.01"
                  value={maxHurst ?? ''}
                  onChange={(e) => setMaxHurst(e.target.value ? parseFloat(e.target.value) : null)}
                  placeholder="Any"
                  className="w-full px-3 py-1.5 text-sm bg-[#111118] border border-[#1a1a24] rounded text-white focus:outline-none focus:border-emerald-500"
                />
              </div>
              <div>
                <label className="block text-xs text-gray-400 mb-1">Min Z-Score</label>
                <input
                  type="number"
                  min="-5"
                  max="5"
                  step="0.1"
                  value={minZScore ?? ''}
                  onChange={(e) => setMinZScore(e.target.value ? parseFloat(e.target.value) : null)}
                  placeholder="Any"
                  className="w-full px-3 py-1.5 text-sm bg-[#111118] border border-[#1a1a24] rounded text-white focus:outline-none focus:border-emerald-500"
                />
              </div>
              <div>
                <label className="block text-xs text-gray-400 mb-1">Max Z-Score</label>
                <input
                  type="number"
                  min="-5"
                  max="5"
                  step="0.1"
                  value={maxZScore ?? ''}
                  onChange={(e) => setMaxZScore(e.target.value ? parseFloat(e.target.value) : null)}
                  placeholder="Any"
                  className="w-full px-3 py-1.5 text-sm bg-[#111118] border border-[#1a1a24] rounded text-white focus:outline-none focus:border-emerald-500"
                />
              </div>
              <div>
                <label className="block text-xs text-gray-400 mb-1">Min Beta</label>
                <input
                  type="number"
                  min="0"
                  step="0.01"
                  value={minBeta ?? ''}
                  onChange={(e) => setMinBeta(e.target.value ? parseFloat(e.target.value) : null)}
                  placeholder="Any"
                  className="w-full px-3 py-1.5 text-sm bg-[#111118] border border-[#1a1a24] rounded text-white focus:outline-none focus:border-emerald-500"
                />
              </div>
              <div>
                <label className="block text-xs text-gray-400 mb-1">Max Beta</label>
                <input
                  type="number"
                  min="0"
                  step="0.01"
                  value={maxBeta ?? ''}
                  onChange={(e) => setMaxBeta(e.target.value ? parseFloat(e.target.value) : null)}
                  placeholder="Any"
                  className="w-full px-3 py-1.5 text-sm bg-[#111118] border border-[#1a1a24] rounded text-white focus:outline-none focus:border-emerald-500"
                />
              </div>
              <div>
                <label className="block text-xs text-gray-400 mb-1">Min Spread Std</label>
                <input
                  type="number"
                  min="0"
                  step="0.01"
                  value={minSpreadStd ?? ''}
                  onChange={(e) => setMinSpreadStd(e.target.value ? parseFloat(e.target.value) : null)}
                  placeholder="Any"
                  className="w-full px-3 py-1.5 text-sm bg-[#111118] border border-[#1a1a24] rounded text-white focus:outline-none focus:border-emerald-500"
                />
              </div>
              <div>
                <label className="block text-xs text-gray-400 mb-1">Max Spread Std</label>
                <input
                  type="number"
                  min="0"
                  step="0.01"
                  value={maxSpreadStd ?? ''}
                  onChange={(e) => setMaxSpreadStd(e.target.value ? parseFloat(e.target.value) : null)}
                  placeholder="Any"
                  className="w-full px-3 py-1.5 text-sm bg-[#111118] border border-[#1a1a24] rounded text-white focus:outline-none focus:border-emerald-500"
                />
              </div>
            </div>
            <button
              onClick={() => {
                setMinCorrelation(0.8);
                setMaxADFPValue(0.1);
                setMinHurst(null);
                setMaxHurst(null);
                setMinZScore(null);
                setMaxZScore(null);
                setMinBeta(null);
                setMaxBeta(null);
                setMinSpreadStd(null);
                setMaxSpreadStd(null);
              }}
              className="mt-3 text-xs text-gray-400 hover:text-white transition-colors"
            >
              Reset filters
            </button>
          </div>
        )}
      </div>
      
      <div className="overflow-x-auto">
        <table className="min-w-full divide-y divide-[#1a1a24]">
          <thead className="bg-[#0a0a0f]/50">
            <tr>
              <th 
                className="px-6 py-3 text-left text-xs font-medium text-gray-400 uppercase tracking-wider cursor-pointer hover:text-white transition-colors"
                onClick={() => handleSort('composite_score')}
              >
                <div className="flex items-center gap-2">
                  Score
                  <SortIcon field="composite_score" />
                </div>
              </th>
              <th 
                className="px-6 py-3 text-left text-xs font-medium text-gray-400 uppercase tracking-wider cursor-pointer hover:text-white transition-colors"
                onClick={() => handleSort('pair')}
              >
                <div className="flex items-center gap-2">
                  Pair
                  <SortIcon field="pair" />
                </div>
              </th>
              <th 
                className="px-6 py-3 text-left text-xs font-medium text-gray-400 uppercase tracking-wider cursor-pointer hover:text-white transition-colors"
                onClick={() => handleSort('correlation')}
              >
                <div className="flex items-center gap-2">
                  Correlation
                  <SortIcon field="correlation" />
                </div>
              </th>
              <th 
                className="px-6 py-3 text-left text-xs font-medium text-gray-400 uppercase tracking-wider cursor-pointer hover:text-white transition-colors"
                onClick={() => handleSort('adf_pvalue')}
              >
                <div className="flex items-center gap-2">
                  ADF p-value
                  <SortIcon field="adf_pvalue" />
                </div>
              </th>
              <th 
                className="px-6 py-3 text-left text-xs font-medium text-gray-400 uppercase tracking-wider cursor-pointer hover:text-white transition-colors"
                onClick={() => handleSort('beta')}
              >
                <div className="flex items-center gap-2">
                  Beta
                  <SortIcon field="beta" />
                </div>
              </th>
              <th 
                className="px-6 py-3 text-left text-xs font-medium text-gray-400 uppercase tracking-wider cursor-pointer hover:text-white transition-colors"
                onClick={() => handleSort('spread_std')}
              >
                <div className="flex items-center gap-2">
                  Spread Std
                  <SortIcon field="spread_std" />
                </div>
              </th>
              <th 
                className="px-6 py-3 text-left text-xs font-medium text-gray-400 uppercase tracking-wider cursor-pointer hover:text-white transition-colors"
                onClick={() => handleSort('hurst_exponent')}
              >
                <div className="flex items-center gap-2">
                  Hurst
                  <SortIcon field="hurst_exponent" />
                </div>
              </th>
              <th className="px-6 py-3 text-left text-xs font-medium text-gray-400 uppercase tracking-wider">
                Z-Score
              </th>
              <th className="px-6 py-3 text-left text-xs font-medium text-gray-400 uppercase tracking-wider">
                TF
              </th>
            </tr>
          </thead>
          <tbody className="divide-y divide-[#1a1a24]">
            {paginatedPairs.map((pair) => {
              const compositeScore = pair.composite_score ?? 0;
              const getScoreColor = (score: number) => {
                if (score >= 80) return 'text-emerald-400';
                if (score >= 60) return 'text-teal-400';
                if (score >= 40) return 'text-yellow-400';
                return 'text-orange-400';
              };
              const getScoreBg = (score: number) => {
                if (score >= 80) return 'bg-emerald-500/20 border-emerald-500/50';
                if (score >= 60) return 'bg-teal-500/20 border-teal-500/50';
                if (score >= 40) return 'bg-yellow-500/20 border-yellow-500/50';
                return 'bg-orange-500/20 border-orange-500/50';
              };
              
              return (
                <tr 
                  key={pair.id} 
                  className="hover:bg-[#0a0a0f]/30 transition-colors duration-150 cursor-pointer"
                  onClick={() => handlePairClick(pair)}
                >
                  <td className="px-6 py-4 whitespace-nowrap">
                    <div className={`inline-flex items-center justify-center w-12 h-12 rounded-lg border ${getScoreBg(compositeScore)}`}>
                      <span className={`text-sm font-bold ${getScoreColor(compositeScore)}`}>
                        {compositeScore.toFixed(0)}
                      </span>
                    </div>
                  </td>
                  <td className="px-6 py-4 whitespace-nowrap">
                    <div className="flex items-center gap-2">
                      <div className="w-2 h-2 rounded-full bg-emerald-500/50"></div>
                      <span className="text-sm font-medium text-white">
                        {pair.asset_a} <span className="text-gray-500">/</span> {pair.asset_b}
                      </span>
                    </div>
                  </td>
                <td className="px-6 py-4 whitespace-nowrap">
                  <span className={`text-sm font-medium ${getCorrelationColor(pair.correlation)}`}>
                    {formatNumber(pair.correlation)}
                  </span>
                </td>
                <td className="px-6 py-4 whitespace-nowrap">
                  <span className={`text-sm font-medium ${getADFColor(pair.adf_pvalue)}`}>
                    {formatNumber(pair.adf_pvalue)}
                  </span>
                </td>
                <td className="px-6 py-4 whitespace-nowrap text-sm text-gray-300">
                  {formatNumber(pair.beta)}
                </td>
                <td className="px-6 py-4 whitespace-nowrap text-sm text-gray-300">
                  {formatNumber(pair.spread_std, 2)}
                </td>
                <td className="px-6 py-4 whitespace-nowrap text-sm text-gray-300">
                  {pair.hurst_exponent !== null && pair.hurst_exponent !== undefined ? (
                    <span className={pair.hurst_exponent < 0.5 ? 'text-emerald-400' : 'text-gray-400'}>
                      {formatNumber(pair.hurst_exponent)}
                    </span>
                  ) : (
                    <span className="text-gray-600">—</span>
                  )}
                </td>
                <td className="px-6 py-4 whitespace-nowrap text-sm">
                  {pair.current_zscore !== null && pair.current_zscore !== undefined ? (
                    <span className={
                      Math.abs(pair.current_zscore) >= 2 ? 'text-red-400' :
                      Math.abs(pair.current_zscore) >= 1 ? 'text-yellow-400' :
                      'text-emerald-400'
                    }>
                      {formatNumber(pair.current_zscore, 2)}
                    </span>
                  ) : (
                    <span className="text-gray-600">—</span>
                  )}
                </td>
                <td className="px-6 py-4 whitespace-nowrap text-sm text-gray-400">
                  {pair.timeframe || '1d'}
                </td>
              </tr>
              );
            })}
          </tbody>
        </table>
      </div>

      {/* Pagination */}
      {totalPages > 1 && (
        <div className="px-6 py-4 border-t border-[#1a1a24] bg-[#0a0a0f]/50 flex items-center justify-between">
          <div className="text-sm text-gray-400">
            Showing {startIndex + 1}-{Math.min(endIndex, filteredAndSortedPairs.length)} of {filteredAndSortedPairs.length} pairs
          </div>
          <div className="flex items-center gap-2">
            <button
              onClick={() => setCurrentPage(prev => Math.max(1, prev - 1))}
              disabled={currentPage === 1}
              className="px-3 py-1.5 text-sm font-medium text-gray-300 bg-[#1a1a24] hover:bg-[#2a2a34] rounded-lg transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
            >
              Previous
            </button>
            <div className="flex items-center gap-1">
              {Array.from({ length: Math.min(5, totalPages) }, (_, i) => {
                let pageNum: number;
                if (totalPages <= 5) {
                  pageNum = i + 1;
                } else if (currentPage <= 3) {
                  pageNum = i + 1;
                } else if (currentPage >= totalPages - 2) {
                  pageNum = totalPages - 4 + i;
                } else {
                  pageNum = currentPage - 2 + i;
                }
                
                return (
                  <button
                    key={pageNum}
                    onClick={() => setCurrentPage(pageNum)}
                    className={`px-3 py-1.5 text-sm font-medium rounded-lg transition-colors ${
                      currentPage === pageNum
                        ? 'bg-emerald-500 text-white'
                        : 'text-gray-300 bg-[#1a1a24] hover:bg-[#2a2a34]'
                    }`}
                  >
                    {pageNum}
                  </button>
                );
              })}
            </div>
            <button
              onClick={() => setCurrentPage(prev => Math.min(totalPages, prev + 1))}
              disabled={currentPage === totalPages}
              className="px-3 py-1.5 text-sm font-medium text-gray-300 bg-[#1a1a24] hover:bg-[#2a2a34] rounded-lg transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
            >
              Next
            </button>
          </div>
        </div>
      )}

      {/* Modal for spread chart - rendered via Portal to body */}
      {showModal && selectedPair && createPortal(
        <div 
          className="fixed inset-0 bg-black/80 backdrop-blur-sm z-[9999] flex items-center justify-center p-4 overflow-y-auto"
          onClick={closeModal}
          style={{ 
            position: 'fixed', 
            top: 0, 
            left: 0, 
            right: 0, 
            bottom: 0,
            zIndex: 9999
          }}
        >
          <div 
            className="bg-[#111118] border border-[#1a1a24] rounded-xl max-w-7xl w-full max-h-[95vh] overflow-y-auto shadow-2xl"
            onClick={(e) => e.stopPropagation()}
            style={{ margin: 'auto' }}
          >
            <div className="sticky top-0 bg-[#111118] border-b border-[#1a1a24] px-6 py-4 flex items-center justify-between z-10">
              <h2 className="text-xl font-medium text-white">
                {selectedPair.asset_a} / {selectedPair.asset_b} - Spread Analysis
              </h2>
              <button
                onClick={closeModal}
                className="text-gray-400 hover:text-white transition-colors"
              >
                <svg className="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
                </svg>
              </button>
            </div>
            
            <div className="p-6 space-y-6">
              {loadingChart ? (
                <div className="text-center py-12">
                  <div className="inline-block animate-spin rounded-full h-8 w-8 border-b-2 border-emerald-500 mb-4"></div>
                  <p className="text-gray-400">Loading chart data...</p>
                </div>
              ) : spreadData ? (
                <>
                  {/* Pair Details Panel */}
                  <PairDetails pair={selectedPair} spreadData={spreadData} />
                  
                  {/* Spread Chart */}
                  <SpreadChart
                    pair={selectedPair}
                    spreadData={spreadData.data}
                    meanSpread={spreadData.mean_spread}
                    stdSpread={spreadData.std_spread}
                    crossingPoints={spreadData.crossing_points}
                  />
                  
                  {/* Normalized Prices Chart */}
                  <PriceChart
                    pair={selectedPair}
                    spreadData={spreadData.data}
                  />
                </>
              ) : (
                <div className="text-center py-12 text-gray-400">
                  <p>Failed to load chart data</p>
                </div>
              )}
            </div>
          </div>
        </div>,
        document.body
      )}
    </div>
  );
};

export default PairsTable;
