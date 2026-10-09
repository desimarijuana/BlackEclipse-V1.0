// Investment Thesis Tracker — persistent, versioned theses with evidence.
// Server shell; interactivity lives in theses-client.tsx.
import { ThesesClient } from "./theses-client";
import { ChatDock } from "@/components/chat/chat-dock";

export const metadata = {
  title: "Investment Theses — BlackEclipse",
};

export default function ThesesPage() {
  return (
    <div className="app-page-bg min-h-screen bg-background text-foreground">
      <ThesesClient />
      <ChatDock />
    </div>
  );
}
