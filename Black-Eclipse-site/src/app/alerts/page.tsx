// Price & Condition Alerts — create/edit watches, live status, history.
// Server shell; interactivity lives in alerts-client.tsx.
import { AlertsClient } from "./alerts-client";

export const metadata = {
  title: "Price & Condition Alerts — BlackEclipse",
};

export default function AlertsPage() {
  return (
    <div className="min-h-screen bg-background text-foreground">
      <AlertsClient />
    </div>
  );
}