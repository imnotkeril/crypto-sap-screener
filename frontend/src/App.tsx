import { QueryClient, QueryClientProvider } from 'react-query';
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
      cacheTime: 300000, // Keep unused data in cache for 5 minutes
    },
  },
});

function App() {
  return (
    <ErrorBoundary>
      <QueryClientProvider client={queryClient}>
        <ScreenerDashboard />
      </QueryClientProvider>
    </ErrorBoundary>
  );
}

export default App;

