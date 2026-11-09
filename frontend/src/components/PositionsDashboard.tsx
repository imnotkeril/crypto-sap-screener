import React from 'react';
import { useQuery } from '@tanstack/react-query';
import { api } from '../services/api';
import PositionCard from './PositionCard';

const PositionsDashboard: React.FC = () => {
  const { data, refetch } = useQuery({
    queryKey: ['positions'],
    queryFn: () => api.getPositions(),
    refetchInterval: 5000,
  });

  const positions = data?.positions || [];

  return (
    <div className="bg-[#111118] border border-[#1a1a24] rounded-xl p-6">
      <div className="flex items-center justify-between mb-4">
        <h2 className="text-xl font-medium text-white">Open Positions</h2>
        <div className="text-sm text-gray-400">
          {positions.length} position{positions.length !== 1 ? 's' : ''}
        </div>
      </div>

      {positions.length === 0 ? (
        <div className="text-center text-gray-400 py-12">
          No open positions
        </div>
      ) : (
        <div className="space-y-4">
          {positions.map((position: any) => (
            <PositionCard key={position.position_id} position={position} onUpdate={refetch} />
          ))}
        </div>
      )}
    </div>
  );
};

export default PositionsDashboard;

