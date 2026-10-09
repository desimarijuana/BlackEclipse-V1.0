// Problem-Solving & Recovery console — a standalone observability surface over
// the recovery engine. Server shell; interactivity lives in recovery-console.tsx
// (the Next `/api/recovery` proxy is operator-gated and reaches the Python
// runtime).
import { RecoveryConsole } from "./recovery-console";
import { ChatDock } from "@/components/chat/chat-dock";

export const metadata = {
  title: "Recovery Console — BlackEclipse",
  description: "Failure incidents, root-cause diagnosis, recovery decisions, capability discovery and skill-candidate promotion.",
};

export default function RecoveryPage() {
  return (
    <div className="app-page-bg min-h-screen bg-background text-foreground">
      <RecoveryConsole />
      {/* This standalone route is outside the app shell, so it mounts its own dock. */}
      <ChatDock />
    </div>
  );
}