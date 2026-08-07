import { StockChat } from '@/components/screens/stock-chat';
import { ErrorBoundary } from '@/components/ui/error-boundary';

export default function Page() {
  return (
    <ErrorBoundary>
      <StockChat />
    </ErrorBoundary>
  );
}
