// ── Recorded risk acknowledgement (server-only) ─────────────────────────────
// The first-run wizard must record WHICH notice version the user accepted and
// WHEN. The record lives in SystemConfig beside the onboarding flag, so it
// follows the same single-user, local-install model the wizard already uses.
//
// This is evidence, not immunity: the enforceable limitation of liability lives
// in the Terms. The UI notice and this record make the Terms credible.

import { getConfig, setConfig } from "@/lib/settings";
import type { SetupMode } from "@/lib/setup/types";
import { RISK_DISCLOSURE_VERSION } from "./disclosure";

export const RISK_ACK_CONFIG_KEY = "risk_ack_v1";

export interface RiskAcknowledgement {
  version: string;
  acceptedAt: string;
  mode?: SetupMode;
}

export interface RiskAckStatus {
  requiredVersion: string;
  acceptedVersion?: string;
  accepted: boolean;
}

function parseAcknowledgement(raw: string | null): RiskAcknowledgement | null {
  if (!raw) return null;
  try {
    const parsed = JSON.parse(raw) as Partial<RiskAcknowledgement>;
    if (typeof parsed.version !== "string" || typeof parsed.acceptedAt !== "string") {
      return null;
    }
    return {
      version: parsed.version,
      acceptedAt: parsed.acceptedAt,
      mode:
        parsed.mode === "commercial"
          ? "commercial"
          : parsed.mode === "personal"
            ? "personal"
            : undefined,
    };
  } catch {
    return null;
  }
}

export async function readRiskAcknowledgement(): Promise<RiskAcknowledgement | null> {
  return parseAcknowledgement(await getConfig(RISK_ACK_CONFIG_KEY));
}

/**
 * Accepted only for the CURRENT version. A stale acceptance (from an older
 * notice) is reported as not accepted so the wizard asks again.
 */
export async function riskAcknowledgementStatus(): Promise<RiskAckStatus> {
  const ack = await readRiskAcknowledgement();
  return {
    requiredVersion: RISK_DISCLOSURE_VERSION,
    acceptedVersion: ack?.version,
    accepted: ack?.version === RISK_DISCLOSURE_VERSION,
  };
}

export async function recordRiskAcknowledgement(
  mode?: SetupMode,
): Promise<RiskAcknowledgement> {
  const ack: RiskAcknowledgement = {
    version: RISK_DISCLOSURE_VERSION,
    acceptedAt: new Date().toISOString(),
    mode,
  };
  await setConfig(RISK_ACK_CONFIG_KEY, JSON.stringify(ack));
  return ack;
}
