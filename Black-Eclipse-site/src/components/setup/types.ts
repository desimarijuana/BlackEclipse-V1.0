import type {
  AiChoice,
  BundleId,
  CapabilityId,
  CapabilityStatus,
  CommercialStatus,
  KeyStatusLite,
  SetupMode,
  SourceTier,
} from "@/lib/setup/types";

export interface SetupSourceRow {
  id: string;
  label: string;
  short: string;
  category: string;
  tier: SourceTier;
  powers: string[];
  commercial: CommercialStatus;
  note?: string;
  termsUrl?: string;
  attribution?: string;
  envVar?: string;
  enabled: boolean;
  keyConfigured?: boolean;
  editable: boolean;
}

export interface SetupCapabilityRow {
  id: CapabilityId;
  label: string;
  description: string;
  status: CapabilityStatus;
  includedSources: string[];
  connectedSources: string[];
  advancedSources: string[];
}

export interface SetupBundleRow {
  id: BundleId;
  label: string;
  description: string;
  needsAcknowledgement?: boolean;
}

export interface SetupAiStatus {
  provider: string;
  model: string;
  baseUrl: string;
  hasKey: boolean;
  configured: boolean;
}

export interface SetupRiskAck {
  requiredVersion: string;
  acceptedVersion?: string;
  accepted: boolean;
}

export interface SetupState {
  completed: boolean;
  isNewInstall: boolean;
  mode: SetupMode;
  /** Recorded acceptance of the current risk notice (see lib/legal). */
  riskAck: SetupRiskAck;
  ai: SetupAiStatus;
  bundles: SetupBundleRow[];
  capabilities: SetupCapabilityRow[];
  sources: SetupSourceRow[];
  acceptedRestrictedSources: string[];
  lastCheck?: { at: string; items: CheckItemView[] } | null;
  warnings: string[];
}

export interface CheckItemView {
  id: string;
  label: string;
  status: "ok" | "failed" | "rate-limited" | "unavailable" | "skipped";
  message: string;
}

export interface SetupDraft {
  step: number;
  mode: SetupMode;
  bundleId: BundleId;
  sources: Record<string, boolean>;
  accepted: string[];
  /** The live-prices decision, kept explicit so the provider step is not a maze. */
  priceMode: "licensed" | "community" | "skip";
  aiKind: "keep" | "local" | "key" | "custom" | "skip";
  aiPreset: string;
  aiBaseUrl: string;
  aiModel: string;
  aiApiKey: string;
  extraKeys: Record<string, string>;
  /** Required before setup can finish; recorded server-side with a version. */
  riskAck: boolean;
}

export type SetupKeyStatuses = Record<string, KeyStatusLite>;

export function draftAiChoice(draft: SetupDraft): AiChoice | undefined {
  if (draft.aiKind === "keep") return undefined;
  if (draft.aiKind === "skip") return { kind: "skip" };
  if (draft.aiKind === "local") {
    return {
      kind: "local",
      presetId: draft.aiPreset === "lmstudio" ? "lmstudio" : "ollama",
      baseUrl: draft.aiBaseUrl || undefined,
      model: draft.aiModel || undefined,
    };
  }
  if (draft.aiKind === "key") {
    return {
      kind: "key",
      presetId: draft.aiPreset,
      apiKey: draft.aiApiKey,
      model: draft.aiModel || undefined,
    };
  }
  return {
    kind: "custom",
    baseUrl: draft.aiBaseUrl,
    apiKey: draft.aiApiKey || undefined,
    model: draft.aiModel,
  };
}
