import { desc } from "drizzle-orm";
import { db } from "@/db";
import { auditLog, eventLog } from "@/db/schema";
import { redactDeep } from "./redact";
import type { Envelope } from "./events";

export type AuditInput = {
  turnId: string | null;
  tool: string;
  tier: number;
  argsHash: string;
  args: unknown;
  decision: "auto" | "approved" | "denied" | "blocked" | "expired" | "invalid";
  via?: string;
  ok?: boolean;
  summary?: string;
  untrustedDerived?: boolean;
};

export async function audit(a: AuditInput) {
  await db.insert(auditLog).values({
    turnId: a.turnId,
    tool: a.tool,
    tier: a.tier,
    argsHash: a.argsHash,
    argsRedacted: redactDeep(a.args) as object,
    decision: a.decision,
    via: a.via ?? "policy",
    ok: a.ok ?? false,
    summary: (a.summary ?? "").slice(0, 300),
    untrustedDerived: a.untrustedDerived ?? false,
  });
}

export async function recentAudit(limit = 100) {
  return db.select().from(auditLog).orderBy(desc(auditLog.id)).limit(limit);
}

export async function persistEvent(env: Envelope) {
  if (env.event.type === "AudioLevel" || env.event.type === "TtsLevel") return;
  await db.insert(eventLog).values({ turnId: env.turnId, type: env.event.type, payload: env.event as object });
}
