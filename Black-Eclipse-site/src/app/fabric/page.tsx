// Execution Fabric Console — a standalone observability surface over the
// Execution Fabric. Server shell; interactivity lives in fabric-console.tsx
// (the Next `/api/fabric` proxy is operator-gated and reaches the Python admin
// API). Mirrors the Event Console.
import { FabricConsole } from "./fabric-console";
import { ChatDock } from "@/components/chat/chat-dock";

export const metadata = {
  title: "Execution Fabric — BlackEclipse",
  description: "Durable queues, workers, retries and dead letters.",
};

export default function FabricPage() {
  return (
    <div className="app-page-bg min-h-screen bg-background text-foreground">
      <FabricConsole />
      {/* This standalone route is outside the app shell, so it mounts its own dock. */}
      <ChatDock />
    </div>
  );
}
