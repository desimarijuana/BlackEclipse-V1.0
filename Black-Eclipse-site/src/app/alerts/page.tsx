// Price & Condition Alerts — create/edit watches, live status, history.
// Server shell; interactivity lives in alerts-client.tsx.
import { AlertsClient } from "./alerts-client";
import { ChatDock } from "@/components/chat/chat-dock";

export const metadata = {
  title: "Price & Condition Alerts — BlackEclipse",
};

export default function AlertsPage() {
  return (
    <div className="app-page-bg min-h-screen bg-background text-foreground">
      <AlertsClient />
      {/* Floating assistant — this standalone route is outside the app shell,
          so it mounts its own dock (the shell's does not cover it). */}
      <ChatDock />
    </div>
  );
}