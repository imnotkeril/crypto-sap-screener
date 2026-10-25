"""
History analyzer for pairs trading metrics
Analyzes changes in pair metrics over time
"""
from typing import List, Dict


class HistoryAnalyzer:
    """Analyzes historical changes in pair metrics"""
    
    @staticmethod
    def calculate_metric_changes(
        current_results: List[Dict],
        previous_results: List[Dict]
    ) -> List[Dict]:
        """
        Calculate changes in metrics between two screening sessions
        
        Args:
            current_results: Current screening results
            previous_results: Previous screening results
            
        Returns:
            List of pairs with metric changes
        """
        # Create lookup dictionaries
        current_dict = {
            (r.get('asset_a'), r.get('asset_b')): r
            for r in current_results
        }
        previous_dict = {
            (r.get('asset_a'), r.get('asset_b')): r
            for r in previous_results
        }
        
        changes = []
        all_pairs = set(current_dict.keys()) | set(previous_dict.keys())
        
        for pair_key in all_pairs:
            current = current_dict.get(pair_key)
            previous = previous_dict.get(pair_key)
            
            change_data = {
                'asset_a': pair_key[0],
                'asset_b': pair_key[1],
                'status': 'new' if previous is None else ('removed' if current is None else 'updated')
            }
            
            if current and previous:
                # Calculate changes
                change_data.update({
                    'correlation_change': current.get('correlation', 0) - previous.get('correlation', 0),
                    'beta_change': current.get('beta', 0) - previous.get('beta', 0),
                    'adf_pvalue_change': current.get('adf_pvalue', 0) - previous.get('adf_pvalue', 0),
                    'current_correlation': current.get('correlation', 0),
                    'previous_correlation': previous.get('correlation', 0),
                    'current_beta': current.get('beta', 0),
                    'previous_beta': previous.get('beta', 0),
                })
            elif current:
                change_data.update({
                    'current_correlation': current.get('correlation', 0),
                    'current_beta': current.get('beta', 0),
                })
            elif previous:
                change_data.update({
                    'previous_correlation': previous.get('correlation', 0),
                    'previous_beta': previous.get('beta', 0),
                })
            
            changes.append(change_data)
        
        return changes
    
    @staticmethod
    def analyze_trends(
        results_history: List[Dict]
    ) -> Dict:
        """
        Analyze trends across multiple screening sessions
        
        Args:
            results_history: List of screening results over time
            Each item should have 'timestamp' and 'results' keys
            
        Returns:
            Dictionary with trend analysis
        """
        if len(results_history) < 2:
            return {
                'total_pairs_trend': [],
                'avg_correlation_trend': [],
                'pairs_count_by_time': []
            }
        
        # Sort by timestamp
        sorted_history = sorted(results_history, key=lambda x: x.get('timestamp', ''))
        
        trends = {
            'total_pairs_trend': [],
            'avg_correlation_trend': [],
            'pairs_count_by_time': []
        }
        
        for entry in sorted_history:
            results = entry.get('results', [])
            timestamp = entry.get('timestamp')
            
            if not results:
                continue
            
            # Calculate average correlation
            correlations = [r.get('correlation', 0) for r in results if r.get('correlation')]
            avg_correlation = sum(correlations) / len(correlations) if correlations else 0
            
            trends['total_pairs_trend'].append({
                'timestamp': timestamp,
                'count': len(results)
            })
            
            trends['avg_correlation_trend'].append({
                'timestamp': timestamp,
                'avg_correlation': avg_correlation
            })
            
            trends['pairs_count_by_time'].append({
                'timestamp': timestamp,
                'count': len(results)
            })
        
        return trends
    
    @staticmethod
    def detect_degradation(
        current_results: List[Dict],
        historical_average: Dict
    ) -> List[Dict]:
        """
        Detect pairs that have degraded (worse metrics than historical average)
        
        Args:
            current_results: Current screening results
            historical_average: Historical average metrics per pair
            
        Returns:
            List of degraded pairs
        """
        degraded = []
        
        for result in current_results:
            pair_key = (result.get('asset_a'), result.get('asset_b'))
            hist_avg = historical_average.get(pair_key, {})
            
            if not hist_avg:
                continue
            
            current_corr = result.get('correlation', 0)
            hist_corr = hist_avg.get('avg_correlation', 0)
            
            # Consider degraded if correlation dropped significantly
            if current_corr < hist_corr - 0.1:  # 10% drop
                degraded.append({
                    'asset_a': result.get('asset_a'),
                    'asset_b': result.get('asset_b'),
                    'current_correlation': current_corr,
                    'historical_avg_correlation': hist_corr,
                    'degradation': hist_corr - current_corr
                })
        
        return degraded

