import { randomUUID } from "node:crypto";
import { LIMITS } from "./constants";
import { hashCall } from "./policy";

/**
 * Approvals are bound to the exact tool name + validated arguments (SHA-256),
 * expire (T1 ~15 s / T2 ~30 s), are single-use, and are never reusable by a different action.
 * T2 cannot be approved by voice: only a physical click / hotkey.
 */
export type Decision = "approved" | "denied" | "expired";
type Entry = {
  id: string;
  tool: string;
  argsHash: string;
  tier: 1 | 2;
  expiresAt: number;
  status: "pending" | "approved" | "denied" | "expired" | "consumed";
  via?: string;
  settle: (d: { decision: Decision; via: string }) => void;
};
const g = globalThis as typeof globalThis & { __voxApprovals?: Map<string, Entry> };
const entries = (g.__voxApprovals ??= new Map<string, Entry>());

export function requestApproval(p: { tool: string; args: unknown; tier: 1 | 2; ttlMs?: number }) {
  const id = randomUUID();
  const ttl = p.ttlMs ?? (p.tier === 2 ? LIMITS.approvalT2Ms : LIMITS.approvalT1Ms);
  const expiresAt = Date.now() + ttl;
  let settle!: Entry["settle"];
  const wait = new Promise<{ decision: Decision; via: string }>((res) => (settle = res));
  const e: Entry = { id, tool: p.tool, argsHash: hashCall(p.tool, p.args), tier: p.tier, expiresAt, status: "pending", settle };
  entries.set(id, e);
  const timer = setTimeout(() => {
    if (e.status === "pending") {
      e.status = "expired";
      e.via = "timeout";
      settle({ decision: "expired", via: "timeout" }); // silence = deny
    }
  }, ttl);
  timer.unref?.();
  return { id, expiresAt, wait };
}

export function resolveApproval(
  id: string,
  decision: "approved" | "denied",
  via: string,
  opts: { loopbackOverlap?: boolean } = {},
): { ok: boolean; error?: string } {
  const e = entries.get(id);
  if (!e) return { ok: false, error: "UNKNOWN_APPROVAL" };
  if (e.status !== "pending") return { ok: false, error: `ALREADY_${e.status.toUpperCase()}` };
  if (Date.now() > e.expiresAt) {
    e.status = "expired";
    e.settle({ decision: "expired", via: "timeout" });
    return { ok: false, error: "EXPIRED" };
  }
  if (decision === "approved") {
    if (e.tier === 2 && via !== "click" && via !== "hotkey") {
      return { ok: false, error: "T2_REQUIRES_PHYSICAL_CONFIRMATION" };
    }
    if (via === "voice" && opts.loopbackOverlap) {
      return { ok: false, error: "VOICE_MATCHES_LOOPBACK" };
    }
  }
  e.status = decision;
  e.via = via;
  e.settle({ decision, via });
  return { ok: true };
}

/** Single-use consumption right before execution. */
export function consumeApproval(id: string, tool: string, args: unknown): { ok: boolean; reason?: string } {
  const e = entries.get(id);
  if (!e) return { ok: false, reason: "UNKNOWN_APPROVAL" };
  if (e.status === "consumed") return { ok: false, reason: "ALREADY_USED" };
  if (e.status !== "approved") return { ok: false, reason: "NOT_APPROVED" };
  if (Date.now() > e.expiresAt) {
    e.status = "expired";
    return { ok: false, reason: "EXPIRED" };
  }
  if (e.tool !== tool || e.argsHash !== hashCall(tool, args)) return { ok: false, reason: "ARGS_MISMATCH" };
  e.status = "consumed";
  return { ok: true };
}

export function denyAllPending(via = "stop") {
  for (const e of entries.values()) {
    if (e.status === "pending") {
      e.status = "denied";
      e.via = via;
      e.settle({ decision: "denied", via });
    }
  }
}

export function pendingApprovals() {
  return [...entries.values()].filter((e) => e.status === "pending").map((e) => ({ id: e.id, tool: e.tool, tier: e.tier, expiresAt: e.expiresAt }));
}
