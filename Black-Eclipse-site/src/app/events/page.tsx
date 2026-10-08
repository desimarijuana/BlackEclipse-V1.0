// Event Console — a standalone observability surface over the Event System.
// Server shell; interactivity lives in events-console.tsx (the Next `/api/events`
// proxy is operator-gated and reaches the Python runtime).
import { EventsConsole } from "./events-console";
import { ChatDock } from "@/components/chat/chat-dock";

export const metadata = {
  title: "Event Console — BlackEclipse",
  description: "Durable events, consumers, retries, dead letters and replay.",
};

export default function EventsPage() {
  return (
    <div className="app-page-bg min-h-screen bg-background text-foreground">
      <EventsConsole />
      {/* This standalone route is outside the app shell, so it mounts its own dock. */}
      <ChatDock />
    </div>
  );
}
