// GET /api/harness/commands — the canonical command manifest.
//
// One read-only document for every surface that is not the composer: CLI, remote
// channels, integrations and tests. It is generated from the SAME registry the
// router executes, plus any validated project command pack. `agentPrompt` is
// omitted (the client does not need the template); everything else is the
// declarative contract.

import { NextResponse } from "next/server";
import { createHash } from "node:crypto";
import { allCommands, isCommandAvailable, type CommandSpec } from "@/lib/harness/commands/command-registry";
import { loadProjectCommands } from "@/lib/harness/commands/command-plugins";

export const dynamic = "force-dynamic";

function manifestCommand(spec: CommandSpec): Record<string, unknown> {
  const copy: Record<string, unknown> = {
    ...spec,
    source: spec.source ?? "builtin",
    available: isCommandAvailable(spec),
  };
  delete copy.agentPrompt;
  return copy;
}

export async function GET(request: Request) {
  const project = await loadProjectCommands();
  const commands = [...allCommands(), ...project.commands].map(manifestCommand);
  const errors = project.errors;
  // The ETag is stable across `generatedAt`; a client revalidating the same
  // catalog gets a 304 while the body still carries the current timestamp.
  const stable = JSON.stringify({ version: 1, commands, errors });
  const etag = `"${createHash("sha256").update(stable).digest("hex").slice(0, 32)}"`;
  const body = JSON.stringify({
    version: 1,
    generatedAt: new Date().toISOString(),
    commands,
    errors,
  });

  if (request.headers.get("if-none-match") === etag) {
    return new NextResponse(null, { status: 304, headers: { ETag: etag } });
  }
  return new NextResponse(body, {
    status: 200,
    headers: {
      "Content-Type": "application/json",
      ETag: etag,
      "Cache-Control": "no-store",
    },
  });
}
