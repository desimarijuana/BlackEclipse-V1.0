import { StockChat } from '@/components/screens/stock-chat';
import { ErrorBoundary } from '@/components/ui/error-boundary';
import { UiCatalogSync } from '@/components/layout/ui-catalog-sync';

export default function Page() {
  return (
    <ErrorBoundary>
      <UiCatalogSync />
      <StockChat />
    </ErrorBoundary>
  );
}
