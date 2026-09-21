import { NextResponse } from "next/server";
import { OpenAICompatibleProvider } from "@/lib/agent/openai-provider";
import { getLLMConfig } from "@/lib/settings";
import { isLocalBaseUrl } from "@/lib/agent/presets";

export const dynamic = "force-dynamic";

// GET /api/agent/status — tells the client whether a usable LLM provider is
// configured. This is a runtime fact (settings vault + env + local servers), so
// the client cannot derive it from a build-time NEXT_PUBLIC flag.
export async function GET() {
  try {
    const provider = new OpenAICompatibleProvider();
    const configured = await provider.isConfiguredAsync();
    const cfg = await getLLMConfig();
    return NextResponse.json({
      configured,
      provider: cfg.provider,
      model: cfg.model,
      local: isLocalBaseUrl(cfg.baseUrl),
    });
  } catch (err) {
    console.error("[api/agent/status] GET error:", err);
    return NextResponse.json({ configured: false });
  }
}
