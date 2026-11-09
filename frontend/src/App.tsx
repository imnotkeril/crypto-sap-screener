import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import ScreenerDashboard from './components/ScreenerDashboard';
import ErrorBoundary from './components/ErrorBoundary';

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      refetchOnWindowFocus: false,
      refetchOnMount: true,
      refetchOnReconnect: true,
      retry: 1,
      staleTime: 5000, // Default: consider data fresh for 5 seconds
      gcTime: 300000, // Keep unused data in cache for 5 minutes
    },
  },
});

function App() {
  return (
    <ErrorBoundary>
      <QueryClientProvider client={queryClient}>
        <main>
          <ScreenerDashboard />
        </main>
        <footer className="px-4 py-4 text-center text-xs text-gray-400">
          Research and educational tool, not investment advice. Results are statistical and may be
          affected by survivorship bias (the universe is today&apos;s top-volume listed perpetuals;
          delisted assets are absent). The app never places orders.
        </footer>
      </QueryClientProvider>
    </ErrorBoundary>
  );
}

export default App;

