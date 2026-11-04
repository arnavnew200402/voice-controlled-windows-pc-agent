import { randomUUID } from "node:crypto";
import { db } from "@/db";
import { tasks } from "@/db/schema";
import { audit } from "./audit";
import { denyAllPending, consumeApproval, requestApproval, resolveApproval } from "./approvals";
import {
  effectiveFor, getSystemPrompt, probeCloud, routedChat,
  type ChatMessage, type ToolCall, type ToolRes,
} from "./brain";
import { LIMITS } from "./constants";
import type { VoxEvent } from "./events";
import { setNetworkUp } from "./netguard";
import { classify, hashCall, normalizePath, PathError, TIER_NAME, type Tier } from "./policy";
import { redactSecrets, redactTree, wrapUntrusted } from "./redact";
import { getTool, toolSpecs, type Ctx, type Preview } from "./tools";
import { resolveLinks } from "./vpc";

export type ApproverFn = (req: { id: string; tier: 1 | 2; tool: string; title: string }) => Promise<{ decision: "approved" | "denied" | "expired"; via: string }>;

export type TurnInput = {
  text: string;
  turnId?: string;
  lang?: string;
  emit: (e: VoxEvent) => void;
  /** test hook: resolves approvals programmatically instead of waiting for the user */
  approver?: ApproverFn;
  /** test hook: model obeys instructions found in tool output (red-team) */
  gullible?: boolean;
  /** scenario hook: cut simulated network after N executed tool calls */
  cutNetworkAfter?: number;
};

export type CallLog = { name: string; tier: Tier; decision: string; ok: boolean; approvalRequested: boolean; untrustedDerived: boolean; evidence: string };
export type TurnSummary = { turnId: string; reply: string; calls: CallLog[]; aborted?: string; tainted: boolean };

type StepState = { title: string; status: "pending" | "running" | "verified" | "failed" | "denied"; evidence: string };
type Task = { id: string; goal: string; status: "running" | "paused" | "done" | "failed" | "stopped"; steps: StepState[] };
type Active = { turnId: string; abort: AbortController; paused: boolean; task: Task | null };

const g = globalThis as typeof globalThis & { __voxActive?: { cur: Active | null; last: Task | null } };
const reg = (g.__voxActive ??= { cur: null, last: null });

const sleep = (ms: number) => new Promise((r) => setTimeout(r, ms));

async function persistTask(t: Task) {
  await db
    .insert(tasks)
    .values({ id: t.id, goal: t.goal, status: t.status, steps: t.steps })
    .onConflictDoUpdate({ target: tasks.id, set: { status: t.status, steps: t.steps, updatedAt: new Date() } });
}

const STOP = /^(stop|cancel|never ?mind|abort|रुको|रुकिए|बंद करो|स्टॉप)$/i;
const norm = (s: string) => s.trim().replace(/[.!?,]+$/g, "").toLowerCase();

export function stopActive(via = "stop") {
  denyAllPending(via);
  reg.cur?.abort.abort();
}

function taskStatusText(t: Task | null): string {
  if (!t) return "There's no task running.";
  const done = t.steps.filter((s) => s.status === "verified").length;
  const cur = t.steps.find((s) => s.status === "running" || s.status === "pending");
  return `${t.status === "paused" ? "Paused. " : ""}Step ${Math.min(done + 1, t.steps.length)} of ${t.steps.length}${cur ? `: ${cur.title}` : ""}. ${done} verified.`;
}

export async function runTurn(input: TurnInput): Promise<TurnSummary> {
  const turnId = input.turnId ?? randomUUID();
  const { emit } = input;
  const summary: TurnSummary = { turnId, reply: "", calls: [], tainted: false };
  const say = (text: string, spoken = true) => {
    summary.reply = text;
    emit({ type: "Reply", text, spoken });
    emit({ type: "StateChanged", state: spoken ? "SPEAKING" : "IDLE", reason: "reply ready" });
  };

  emit({ type: "Transcript", text: input.text, partial: false, lang: input.lang ?? "en" });
  const word = norm(input.text);

  /* deterministic controls: stop / pause / resume / status (never go through the model) */
  if (STOP.test(word)) {
    const had = !!reg.cur;
    stopActive("stop");
    if (reg.last && reg.last.status === "running") reg.last.status = "stopped";
    say(had ? "Stopped." : "Nothing is running.", true);
    return summary;
  }
  if (word === "task status" || word === "status") {
    say(taskStatusText(reg.cur?.task ?? reg.last), true);
    return summary;
  }
  if (word === "pause" && reg.cur) {
    reg.cur.paused = true;
    if (reg.cur.task) reg.cur.task.status = "paused";
    say("Paused.", true);
    return summary;
  }
  if (word === "resume" && reg.cur) {
    reg.cur.paused = false;
    if (reg.cur.task) reg.cur.task.status = "running";
    say("Resuming.", true);
    return summary;
  }
  if (reg.cur) {
    emit({ type: "Error", code: "BUSY", message: "I'm still working on something. Say stop to cancel it.", recoverable: true });
    summary.aborted = "BUSY";
    return summary;
  }

  const active: Active = { turnId, abort: new AbortController(), paused: false, task: null };
  reg.cur = active;
  const started = Date.now();
  const S = { tainted: false, stepIdx: 0, toolCount: 0, failures: new Map<string, number>(), echoOnly: true, anyEcho: false };
  const messages: ChatMessage[] = [{ role: "system", content: getSystemPrompt() }, { role: "user", content: input.text }];
  const aborted = new Promise<never>((_, rej) => active.abort.signal.addEventListener("abort", () => rej(new Error("ABORTED"))));
  aborted.catch(() => {});

  const setPriv = (cloud: boolean, screen = false) => emit({ type: "PrivacyIndicator", micOpen: false, screenCapturing: screen, cloudActive: cloud });

  try {
    await probeCloud();
    emit({ type: "StateChanged", state: "THINKING", reason: "transcript received" });
    emit({ type: "Intent", summary: input.text.length > 70 ? input.text.slice(0, 67) + "…" : input.text });

    const logCall = (c: CallLog) => summary.calls.push(c);

    const execute = async (c: ToolCall): Promise<ToolRes> => {
      const tool = getTool(c.name);
      if (!tool) {
        await audit({ turnId, tool: c.name, tier: 0, argsHash: hashCall(c.name, c.args), args: c.args, decision: "invalid", summary: "UNKNOWN_TOOL" });
        logCall({ name: c.name, tier: 0, decision: "invalid", ok: false, approvalRequested: false, untrustedDerived: S.tainted, evidence: "UNKNOWN_TOOL" });
        return { ok: false, error: "UNKNOWN_TOOL", evidence: `There is no tool called ${c.name}.` };
      }
      const parsed = tool.args.safeParse(c.args);
      if (!parsed.success) {
        await audit({ turnId, tool: c.name, tier: tool.tier, argsHash: hashCall(c.name, c.args), args: c.args, decision: "invalid", summary: "INVALID_TOOL_ARGUMENTS" });
        logCall({ name: c.name, tier: tool.tier, decision: "invalid", ok: false, approvalRequested: false, untrustedDerived: S.tainted, evidence: "INVALID_TOOL_ARGUMENTS" });
        return { ok: false, error: "INVALID_TOOL_ARGUMENTS", evidence: "Those arguments weren't valid." };
      }
      const args = parsed.data; // zod strips unknown keys: a model-supplied "tier" is ignored
      const hash = hashCall(tool.name, args);

      // loop detection
      const fails = S.failures.get(hash) ?? 0;
      if (fails >= 2) throw new Error("LOOP");

      // policy: path args (plus junction-resolved targets), preview count, tool-level escalation
      const pathArgs = [...(tool.pathArgs?.(args) ?? [])];
      for (const pa of [...pathArgs]) {
        try {
          const real = await resolveLinks(normalizePath(pa.value));
          if (real.toLowerCase() !== normalizePath(pa.value).toLowerCase()) pathArgs.push({ ...pa, value: real });
        } catch { /* classify will reject it */ }
      }
      let pv: Preview | undefined;
      try { pv = await tool.preview?.(args); } catch (e) { if (!(e instanceof PathError)) throw e; }
      const extra = await tool.extraTier?.(args);
      const cls = classify({ tool: tool.name, baseTier: tool.tier, pathArgs, count: pv?.count, extraTier: extra });
      const tier = cls.tier;
      const title = tool.title(args, pv);

      if (tier === 3) {
        const why = cls.reasons.join("; ") || "Blocked by policy";
        await audit({ turnId, tool: tool.name, tier, argsHash: hash, args, decision: "blocked", via: "policy", summary: why, untrustedDerived: S.tainted });
        logCall({ name: tool.name, tier, decision: "blocked", ok: false, approvalRequested: false, untrustedDerived: S.tainted, evidence: why });
        emit({ type: "Error", code: "BLOCKED_BY_POLICY", message: `Blocked: ${why}`, recoverable: true });
        return { ok: false, error: "BLOCKED_BY_POLICY", evidence: `That's blocked by my safety policy (${why}).` };
      }

      let decision: "auto" | "approved" = "auto";
      let via = "policy";
      let approvalRequested = false;
      if (tier >= 1) {
        approvalRequested = true;
        const req = requestApproval({ tool: tool.name, args, tier: tier as 1 | 2 });
        const details = [
          ...(S.tainted ? ["This came from page/file content."] : []),
          ...cls.reasons,
          ...(pv?.lines ?? []),
        ].slice(0, 6);
        emit({ type: "StateChanged", state: "APPROVAL", reason: `${TIER_NAME[tier]} action` });
        emit({ type: "ApprovalRequested", id: req.id, tier: tier as 1 | 2, title, details, untrustedDerived: S.tainted, expiresAt: req.expiresAt });
        let res: { decision: "approved" | "denied" | "expired"; via: string };
        if (input.approver) {
          // the programmatic approver goes through the SAME resolution rules as the UI
          const a = await Promise.race([input.approver({ id: req.id, tier: tier as 1 | 2, tool: tool.name, title }), aborted]);
          const r = resolveApproval(req.id, a.decision === "approved" ? "approved" : "denied", a.via);
          res = a.decision === "approved" && !r.ok ? { decision: "denied", via: r.error ?? "rejected" } : a;
          if (!r.ok) resolveApproval(req.id, "denied", "policy");
        } else {
          res = await Promise.race([req.wait, aborted]);
        }
        emit({ type: "ApprovalResolved", id: req.id, decision: res.decision, via: res.via });
        if (res.decision !== "approved") {
          const d = res.decision === "expired" ? "expired" : "denied";
          await audit({ turnId, tool: tool.name, tier, argsHash: hash, args, decision: d, via: res.via, summary: title, untrustedDerived: S.tainted });
          logCall({ name: tool.name, tier, decision: d, ok: false, approvalRequested, untrustedDerived: S.tainted, evidence: title });
          return { ok: false, error: "DENIED_BY_USER", evidence: d === "expired" ? "The approval timed out, so I didn't do it." : "Okay, I won't do that." };
        }
        const used = consumeApproval(req.id, tool.name, args);
        if (!used.ok) {
          await audit({ turnId, tool: tool.name, tier, argsHash: hash, args, decision: "denied", via: "policy", summary: `Approval rejected: ${used.reason}` });
          logCall({ name: tool.name, tier, decision: "denied", ok: false, approvalRequested, untrustedDerived: S.tainted, evidence: `Approval rejected: ${used.reason}` });
          return { ok: false, error: "APPROVAL_INVALID", evidence: "The approval wasn't valid for that action." };
        }
        decision = "approved";
        via = res.via;
      }

      // task step bookkeeping
      const task = active.task;
      const stepNo = Math.min(++S.stepIdx, Math.max(task?.steps.length ?? 1, 1));
      const of = Math.max(task?.steps.length ?? 1, 1);
      if (task?.steps[stepNo - 1]) task.steps[stepNo - 1].status = "running";
      while (active.paused && !active.abort.signal.aborted) await sleep(100);
      emit({ type: "StateChanged", state: "ACTING", reason: tool.name });
      emit({ type: "ToolStarted", id: c.id, name: tool.name, title, step: stepNo, of });
      if (tool.screen) setPriv(false, true);
      if (++S.toolCount > LIMITS.maxToolCallsPerTask) throw new Error("TOOL_BUDGET");

      const ctx: Ctx = { turnId, tainted: S.tainted, effectiveMode: effectiveFor() };
      let res: ToolRes;
      try {
        res = await Promise.race([
          tool.run(args, ctx),
          sleep(LIMITS.toolTimeoutMs).then((): ToolRes => ({ ok: false, error: "TIMEOUT", evidence: `${tool.name} timed out.` })),
          aborted,
        ]);
      } catch (e) {
        if ((e as Error).message === "ABORTED") throw e;
        res = { ok: false, error: e instanceof PathError ? "INVALID_PATH" : "TOOL_ERROR", evidence: e instanceof PathError ? "That path isn't allowed." : `${tool.name} failed.` };
      }
      if (tool.screen) setPriv(false, false);
      emit({ type: "ToolFinished", id: c.id, ok: res.ok, evidence: res.evidence });
      const echo = res.ok ? tool.echo?.(args, res) : undefined;
      if (echo) { emit({ type: "EchoHud", ...echo }); S.anyEcho = true; } else S.echoOnly = false;
      if (task?.steps[stepNo - 1]) {
        task.steps[stepNo - 1].status = res.ok ? "verified" : "failed";
        task.steps[stepNo - 1].evidence = res.evidence;
        await persistTask(task);
      }
      if (!res.ok) S.failures.set(hash, fails + 1);
      await audit({ turnId, tool: tool.name, tier, argsHash: hash, args, decision, via, ok: res.ok, summary: res.evidence, untrustedDerived: S.tainted });
      logCall({ name: tool.name, tier, decision, ok: res.ok, approvalRequested, untrustedDerived: S.tainted, evidence: res.evidence });
      if (tool.untrustedOutput) S.tainted = true;
      summary.tainted = S.tainted;
      if (input.cutNetworkAfter !== undefined && S.toolCount === input.cutNetworkAfter) setNetworkUp(false);
      return res;
    };

    /* the LLM-first loop: chat -> (answer | tool calls -> compact results -> follow-up) */
    let finalText = "";
    for (let round = 0; round < 16; round++) {
      if (Date.now() - started > LIMITS.maxWallMs) throw new Error("WALL_TIME");
      while (active.paused && !active.abort.signal.aborted) await sleep(100);
      emit({ type: "StateChanged", state: "THINKING", reason: round === 0 ? "planning" : "reading tool evidence" });
      let routed;
      try {
        routed = await Promise.race([
          routedChat(messages, toolSpecs(), { gullible: input.gullible }, {
            onUse: (p) => setPriv(p.privacy === "cloud"),
            onEvent: emit,
          }),
          aborted,
        ]);
      } finally {
        setPriv(false);
      }
      const { out, provider, failedOver } = routed;
      if (failedOver) emit({ type: "Reply", text: "Network dropped, continuing offline.", spoken: false });
      emit({ type: "ModeChanged", requested: effectiveRequested(), effective: provider.privacy === "cloud" ? "online" : "offline", reason: `Using ${provider.label}` });

      if (out.toolCalls?.length) {
        if (round === 0 && out.plan && out.plan.length >= 2 && !active.task) {
          active.task = { id: randomUUID(), goal: input.text, status: "running", steps: out.plan.map((title) => ({ title, status: "pending", evidence: "" })) };
          reg.last = active.task;
          await persistTask(active.task);
        }
        messages.push({ role: "assistant", content: "", toolCalls: out.toolCalls });
        for (const c of out.toolCalls) {
          const res = await execute(c);
          const safe = redactTree<ToolRes>({ ok: res.ok, evidence: res.evidence, data: res.data, error: res.error });
          const raw = JSON.stringify(safe);
          const untrusted = getTool(c.name)?.untrustedOutput;
          messages.push({ role: "tool", toolName: c.name, toolCallId: c.id, content: untrusted ? wrapUntrusted(c.name, raw) : raw, result: safe });
        }
        continue;
      }
      finalText = out.text ?? "Done.";
      break;
    }

    // completion guard: never claim success while a planned step is unverified
    const t = active.task;
    if (t) {
      const bad = t.steps.find((s) => s.status === "failed" || s.status === "pending" || s.status === "running");
      t.status = bad ? "failed" : "done";
      if (bad) finalText = bad.evidence || finalText;
      await persistTask(t);
    }
    const echoOnly = S.anyEcho && S.echoOnly;
    say(redactSecrets(finalText), !echoOnly);
  } catch (e) {
    const msg = (e as Error).message;
    summary.aborted = msg;
    if (active.task) { active.task.status = msg === "ABORTED" ? "stopped" : "failed"; await persistTask(active.task); }
    if (msg === "ABORTED") {
      emit({ type: "StateChanged", state: "IDLE", reason: "stopped by user" });
    } else if (msg === "LOOP") {
      emit({ type: "Error", code: "LOOP_DETECTED", message: "The same step kept failing, so I stopped.", recoverable: true });
      say("The same step kept failing, so I stopped.");
    } else {
      const code = (e as { code?: string }).code ?? msg;
      emit({ type: "Error", code, message: msg === "WALL_TIME" ? "That took too long, so I stopped." : msg, recoverable: true });
    }
  } finally {
    reg.cur = null;
    setPriv(false);
  }
  return summary;
}

function effectiveRequested() {
  return (globalThis as typeof globalThis & { __voxRouter?: { mode: "offline" | "auto" | "online" } }).__voxRouter?.mode ?? "auto";
}
