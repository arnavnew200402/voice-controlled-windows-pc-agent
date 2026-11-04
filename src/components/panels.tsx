"use client";
import { useCallback, useEffect, useState } from "react";
import type { Envelope, Mode } from "@/lib/vox/events";

/* eslint-disable @typescript-eslint/no-explicit-any */
export type ServerState = {
  vpc: any;
  files: { path: string; kind: string; link: string | null }[];
  archiveCount: number;
  trash: string[];
  router: any;
  net: any;
  approvals: any[];
  memories: string[];
  tasks: any[];
};

const TIER_CLS = ["bg-emerald-500/15 text-emerald-300", "bg-amber-500/15 text-amber-300", "bg-orange-500/20 text-orange-300", "bg-red-500/20 text-red-300"];
const TIER_LBL = ["T0 Safe", "T1 Confirm", "T2 Confirm-Hard", "T3 Blocked"];
export const TierBadge = ({ tier }: { tier: number }) => <span className={`rounded px-1.5 py-0.5 text-[10px] font-semibold ${TIER_CLS[tier]}`}>{TIER_LBL[tier]}</span>;
const Card = ({ title, children, right }: { title: string; children: React.ReactNode; right?: React.ReactNode }) => (
  <section className="rounded-2xl border border-white/10 bg-white/[0.03] p-4">
    <div className="mb-3 flex items-center justify-between"><h3 className="text-xs font-semibold uppercase tracking-widest text-white/50">{title}</h3>{right}</div>
    {children}
  </section>
);
const Btn = ({ children, onClick, tone = "default", disabled }: { children: React.ReactNode; onClick?: () => void; tone?: "default" | "warn" | "primary"; disabled?: boolean }) => (
  <button disabled={disabled} onClick={onClick} className={`rounded-full px-3 py-1 text-xs font-medium transition disabled:opacity-40 ${tone === "primary" ? "bg-white text-black hover:bg-white/90" : tone === "warn" ? "bg-amber-400/90 text-black hover:bg-amber-300" : "bg-white/10 text-white hover:bg-white/20"}`}>{children}</button>
);
export { Card, Btn };

/* ------------------------------ virtual PC ------------------------------ */
export function PcPanel({ st }: { st: ServerState | null }) {
  if (!st) return <div className="text-sm text-white/40">Loading sandbox…</div>;
  const v = st.vpc;
  const root = "C:\\Users\\vox";
  return (
    <div className="grid gap-4 lg:grid-cols-2">
      <Card title="Monitors & windows (sandbox)">
        {v.poweredOff && <div className="mb-2 rounded-lg bg-red-500/20 px-3 py-2 text-xs text-red-200">Simulated PC is powered off (shutdown was confirmed). Use “Reset sandbox”.</div>}
        <div className="grid gap-3 sm:grid-cols-2">
          {v.monitors.map((m: any) => (
            <div key={m.id}>
              <div className="relative aspect-video overflow-hidden rounded-lg border border-white/15 bg-gradient-to-br from-slate-800 to-slate-900">
                {v.windows.filter((w: any) => w.monitor === m.id && !w.minimized).map((w: any) => {
                  const r = v.rects[w.id];
                  return (
                    <div key={w.id} className={`absolute overflow-hidden rounded-md border bg-neutral-950/90 p-1 text-[9px] ${v.foreground === w.id ? "border-sky-400/70" : "border-white/15"}`}
                      style={{ left: `${((r.x - m.x) / m.w) * 100}%`, top: `${(r.y / m.h) * 100}%`, width: `${(r.w / m.w) * 100}%`, height: `${(r.h / m.h) * 100}%`, transition: "all .35s cubic-bezier(.2,.8,.2,1)" }}>
                      <div className="font-semibold text-white/80">{w.app}</div>
                      <div className="truncate text-white/40">{w.text || w.title}</div>
                    </div>
                  );
                })}
              </div>
              <div className="mt-1 text-[11px] text-white/40">{m.name}</div>
            </div>
          ))}
        </div>
        <dl className="mt-4 grid grid-cols-2 gap-x-4 gap-y-1 text-xs text-white/70">
          <dt className="text-white/40">Volume</dt><dd>{v.muted ? "muted" : v.volume}</dd>
          <dt className="text-white/40">Brightness</dt><dd>{v.brightness}</dd>
          <dt className="text-white/40">Audio out</dt><dd className="truncate">{v.defaultAudio}</dd>
          <dt className="text-white/40">Clipboard</dt><dd className="truncate">{v.clipboard || "—"}</dd>
          <dt className="text-white/40">Browser</dt><dd className="truncate">{v.browser.url ?? "—"}</dd>
          <dt className="text-white/40">Locked</dt><dd>{String(v.locked)}</dd>
        </dl>
      </Card>
      <Card title="Files (sandbox, Postgres-backed)" right={<span className="text-[11px] text-white/40">🗑 {st.trash.length} in Recycle Bin</span>}>
        <div className="max-h-[360px] overflow-auto font-mono text-[11px] leading-5 text-white/70">
          {st.files.map((f) => {
            const depth = f.path.slice(root.length + 1).split("\\").length - 1;
            return (
              <div key={f.path} style={{ paddingLeft: depth * 14 }} className="truncate">
                {f.link ? "🔗" : f.kind === "dir" ? "📁" : "📄"} {f.path.split("\\").pop()}
                {f.link && <span className="text-amber-300/70"> → {f.link}</span>}
              </div>
            );
          })}
          <div className="pl-[14px] text-white/35">📁 Archive — {st.archiveCount} files (hidden)</div>
        </div>
        {st.memories.length > 0 && <div className="mt-3 border-t border-white/10 pt-2 text-xs text-white/60">Memory: {st.memories.join(" · ")}</div>}
      </Card>
      {st.tasks.length > 0 && (
        <Card title="Recent tasks (persisted plan + evidence)">
          <div className="space-y-2 text-xs">
            {st.tasks.map((t: any) => (
              <div key={t.id} className="rounded-lg bg-white/5 p-2">
                <div className="flex justify-between"><span className="text-white/80">{t.goal}</span><span className="text-white/40">{t.status}</span></div>
                {(t.steps as any[]).map((s, i) => <div key={i} className="text-white/50">{s.status === "verified" ? "✓" : s.status === "failed" ? "✕" : "·"} {s.title}{s.evidence ? ` — ${s.evidence}` : ""}</div>)}
              </div>
            ))}
          </div>
        </Card>
      )}
    </div>
  );
}

/* ------------------------------ events ------------------------------ */
export function EventsPanel({ events }: { events: Envelope[] }) {
  return (
    <Card title="Live event bus (versioned, also persisted to event_log)">
      <div className="max-h-[480px] overflow-auto font-mono text-[11px] leading-5">
        {events.length === 0 && <div className="text-white/40">Run a command to see events.</div>}
        {events.map((e, i) => (
          <div key={i} className="flex gap-3 border-b border-white/5 py-0.5">
            <span className="w-8 shrink-0 text-white/30">{e.seq < 0 ? "ui" : e.seq}</span>
            <span className="w-36 shrink-0 text-sky-300">{e.event.type}</span>
            <span className="truncate text-white/60">{JSON.stringify({ ...e.event, type: undefined })}</span>
          </div>
        ))}
      </div>
    </Card>
  );
}

/* ------------------------------ audit ------------------------------ */
export function AuditPanel({ tick }: { tick: number }) {
  const [rows, setRows] = useState<any[]>([]);
  const load = useCallback(() => fetch("/api/audit").then((r) => r.json()).then((j) => setRows(j.rows)), []);
  useEffect(() => { void load(); }, [load, tick]);
  return (
    <Card title="Append-only audit log (args redacted, secrets never stored)" right={<Btn onClick={load}>Refresh</Btn>}>
      <div className="max-h-[480px] overflow-auto text-xs">
        <table className="w-full text-left">
          <thead className="sticky top-0 bg-[#0d0f14] text-white/40"><tr><th className="py-1">Time</th><th>Tool</th><th>Tier</th><th>Decision</th><th>Via</th><th>Result</th></tr></thead>
          <tbody>
            {rows.map((r) => (
              <tr key={r.id} className="border-t border-white/5 align-top">
                <td className="py-1 pr-2 text-white/40">{new Date(r.ts).toLocaleTimeString()}</td>
                <td className="pr-2 font-mono text-white/80">{r.tool}{r.untrustedDerived && <span title="derived from untrusted content" className="ml-1 text-amber-300">⚠</span>}</td>
                <td className="pr-2"><TierBadge tier={r.tier} /></td>
                <td className={`pr-2 ${r.decision === "blocked" || r.decision === "denied" || r.decision === "expired" ? "text-red-300" : "text-emerald-300"}`}>{r.decision}</td>
                <td className="pr-2 text-white/50">{r.via}</td>
                <td className="text-white/60">{r.summary}</td>
              </tr>
            ))}
          </tbody>
        </table>
        {rows.length === 0 && <div className="py-6 text-center text-white/40">No entries yet.</div>}
      </div>
    </Card>
  );
}

/* ------------------------------ safety lab ------------------------------ */
const PRESETS: { label: string; tool: string; path: string; mode: "read" | "write" | "delete"; command?: string }[] = [
  { label: "Write to System32", tool: "create_file", path: "C:\\Windows\\System32\\x.txt", mode: "write" },
  { label: "Traversal ..\\..", tool: "create_file", path: "..\\..\\Windows\\System32\\x.txt", mode: "write" },
  { label: "Junction → System32", tool: "create_file", path: "Desktop\\system-shortcut\\config\\SAM", mode: "write" },
  { label: "Device path \\\\?\\", tool: "create_file", path: "\\\\?\\C:\\Windows\\x", mode: "write" },
  { label: "ADS ::$DATA", tool: "create_file", path: "C:\\Users\\vox\\Desktop\\a.txt:evil", mode: "write" },
  { label: "Read SSH key", tool: "read_text_file", path: "C:\\Users\\vox\\.ssh\\id_ed25519", mode: "read" },
  { label: "Delete profile root", tool: "delete_path", path: "C:\\Users\\vox", mode: "delete" },
  { label: "Safe: Desktop file", tool: "create_file", path: "Desktop\\hello.txt", mode: "write" },
  { label: "Shell: ipconfig", tool: "run_command", path: "", mode: "read", command: "ipconfig /all" },
  { label: "Shell: net user add", tool: "run_command", path: "", mode: "read", command: "net user hacker /add" },
  { label: "Shell: del /s", tool: "run_command", path: "", mode: "read", command: "del /s /q C:\\x" },
];
export function SafetyLab() {
  const [p, setP] = useState(PRESETS[0]);
  const [res, setRes] = useState<any>(null);
  const [rt, setRt] = useState<any>(null);
  const [busy, setBusy] = useState(false);
  const check = useCallback(async (x: typeof PRESETS[number]) => {
    setP(x);
    const r = await fetch("/api/policy-check", { method: "POST", headers: { "content-type": "application/json" }, body: JSON.stringify(x) });
    setRes(await r.json());
  }, []);
  const run = async () => {
    setBusy(true);
    try { setRt(await (await fetch("/api/redteam", { method: "POST" })).json()); } finally { setBusy(false); }
  };
  return (
    <div className="grid gap-4 lg:grid-cols-2">
      <Card title="Policy dry-run (nothing executes)">
        <div className="mb-3 flex flex-wrap gap-1.5">{PRESETS.map((x) => <Btn key={x.label} onClick={() => void check(x)}>{x.label}</Btn>)}</div>
        <div className="grid grid-cols-[80px_1fr] items-center gap-2 text-xs">
          <span className="text-white/40">Tool</span><input value={p.tool} onChange={(e) => setP({ ...p, tool: e.target.value })} className="rounded bg-white/10 px-2 py-1 font-mono" />
          <span className="text-white/40">Path</span><input value={p.path} onChange={(e) => setP({ ...p, path: e.target.value })} className="rounded bg-white/10 px-2 py-1 font-mono" />
          <span className="text-white/40">Command</span><input value={p.command ?? ""} onChange={(e) => setP({ ...p, command: e.target.value })} className="rounded bg-white/10 px-2 py-1 font-mono" />
        </div>
        <div className="mt-2"><Btn tone="primary" onClick={() => void check(p)}>Classify</Btn></div>
        {res && (
          <div className="mt-3 space-y-1 rounded-lg bg-black/40 p-3 text-xs">
            <div className="flex items-center gap-2"><TierBadge tier={res.tier} /><span className="text-white/50">base tier {res.baseTier}</span></div>
            {res.normalized && <div className="font-mono text-white/60">normalized: {res.normalized}</div>}
            {res.resolved && res.resolved !== res.normalized && <div className="font-mono text-amber-300">resolved via link → {res.resolved}</div>}
            {res.error && <div className="font-mono text-red-300">{res.error}</div>}
            {res.reasons?.map((r: string) => <div key={r} className="text-white/70">• {r}</div>)}
          </div>
        )}
      </Card>
      <Card title="Red-team suite (runs real policy + engine against the sandbox)" right={<Btn tone="warn" disabled={busy} onClick={() => void run()}>{busy ? "Running…" : "Run suite"}</Btn>}>
        {!rt && <p className="text-xs text-white/50">25 cases: hidden-instruction web page, clipboard + filename injection, spoofed titles/OCR, voice injection, path-smuggling fuzz (466 variants), confused deputy, approval replay/expiry/arg-swap, tier downgrade, bulk escalation, offline guard, mid-task failover, stop latency. Resets the sandbox.</p>}
        {rt && (
          <>
            <div className={`mb-2 text-sm font-semibold ${rt.passed === rt.total ? "text-emerald-300" : "text-red-300"}`}>{rt.passed}/{rt.total} passed in {(rt.ms / 1000).toFixed(1)} s</div>
            <div className="max-h-[420px] space-y-1 overflow-auto text-xs">
              {rt.results.map((r: any) => (
                <div key={r.id} className="rounded bg-white/5 px-2 py-1">
                  <div className="flex gap-2"><span className={r.pass ? "text-emerald-300" : "text-red-300"}>{r.pass ? "PASS" : "FAIL"}</span><span className="text-white/40">{r.id}</span><span className="text-white/80">{r.name}</span></div>
                  <div className="font-mono text-[10px] text-white/45">{r.detail}</div>
                </div>
              ))}
            </div>
          </>
        )}
      </Card>
    </div>
  );
}

/* ------------------------------ tools ------------------------------ */
export function ToolsPanel() {
  const [d, setD] = useState<any>(null);
  useEffect(() => { fetch("/api/tools").then((r) => r.json()).then(setD); }, []);
  if (!d) return null;
  return (
    <div className="grid gap-4 lg:grid-cols-[2fr_1fr]">
      <Card title={`Tool packs (${d.tools.filter((t: any) => !t.hidden).length} model-visible tools)`}>
        <div className="max-h-[480px] space-y-3 overflow-auto text-xs">
          {d.packs.map((pk: any) => (
            <div key={pk.name}>
              <div className="mb-1 font-semibold text-white/80">{pk.name} <span className="font-normal text-white/30">v{pk.version}</span></div>
              {d.tools.filter((t: any) => t.pack === pk.name).map((t: any) => (
                <div key={t.name} className="flex items-start gap-2 py-0.5"><TierBadge tier={t.tier} /><span className="w-40 shrink-0 font-mono text-sky-300">{t.name}</span><span className="text-white/50">{t.description}{t.untrustedOutput ? " (output = untrusted data)" : ""}</span></div>
              ))}
            </div>
          ))}
          <div className="text-white/40">Hidden T3 tools (never exposed to the model; attempts are blocked + audited): {d.tools.filter((t: any) => t.hidden).map((t: any) => t.name).join(", ")}</div>
        </div>
      </Card>
      <Card title="Built-in protected policy (not removable)">
        <ul className="space-y-1 text-[11px] text-white/60">{d.protected.map((p: any) => <li key={p.path}><span className="font-mono text-white/80">{p.path}</span><br /><span className="text-white/35">{p.reason}</span></li>)}</ul>
      </Card>
    </div>
  );
}

/* ------------------------------ router ------------------------------ */
export function RouterPanel({ st, mode, onMode, onNet, onProbe }: { st: ServerState | null; mode: Mode; onMode: (m: Mode) => void; onNet: (up: boolean) => void; onProbe: () => void }) {
  if (!st) return null;
  const r = st.router, n = st.net;
  return (
    <div className="grid gap-4 lg:grid-cols-2">
      <Card title="Mode & provider health">
        <div className="mb-3 flex gap-2">{(["offline", "auto", "online"] as Mode[]).map((m) => <Btn key={m} tone={mode === m ? "primary" : "default"} onClick={() => onMode(m)}>{m}</Btn>)}</div>
        <dl className="grid grid-cols-2 gap-y-1 text-xs">
          <dt className="text-white/40">Requested / effective</dt><dd>{r.requested} / <b className={r.effective === "online" ? "text-sky-300" : "text-amber-300"}>{r.effective}</b></dd>
          <dt className="text-white/40">Reason</dt><dd className="text-white/70">{r.reason}</dd>
          <dt className="text-white/40">Consecutive failures</dt><dd>{r.consecFail} (offline at 2)</dd>
          <dt className="text-white/40">Recovery</dt><dd>{r.effective === "offline" && r.requested === "auto" ? `${r.healthyCount}/3 healthy checks, needs ≥ ${Math.round(r.recoveryWindowMs / 1000)} s span` : "—"}</dd>
          <dt className="text-white/40">Avg cloud latency</dt><dd>{r.avgLatency ?? "—"} ms</dd>
        </dl>
        <div className="mt-3 flex gap-2"><Btn tone="warn" onClick={() => onNet(false)} disabled={!n.networkUp}>Cut network</Btn><Btn onClick={() => onNet(true)} disabled={n.networkUp}>Restore network</Btn><Btn onClick={onProbe}>Probe now</Btn></div>
        <p className="mt-2 text-[11px] text-white/40">Network is simulated. Auto mode fails over after 2 consecutive failures and returns online only after 3 healthy probes spanning ≥ 30 s (hysteresis, never mid-sentence).</p>
      </Card>
      <Card title="Offline guard (application level)">
        <dl className="grid grid-cols-2 gap-y-1 text-xs">
          <dt className="text-white/40">Guard enforced</dt><dd>{String(n.offlineEnforced)}</dd>
          <dt className="text-white/40">Simulated link</dt><dd>{n.networkUp ? "up" : "DOWN"}</dd>
          <dt className="text-white/40">Outbound attempts</dt><dd>{n.attempts}</dd>
          <dt className="text-white/40">Blocked by guard</dt><dd>{n.blocked}</dd>
          <dt className="text-white/40">Non-loopback that got through</dt><dd className={n.outboundNonLoopback && n.offlineEnforced ? "text-red-300" : ""}>{n.outboundNonLoopback}</dd>
        </dl>
        <h4 className="mt-3 mb-1 text-[11px] uppercase tracking-widest text-white/40">Providers</h4>
        {r.providers.map((p: any) => <div key={p.id} className="flex justify-between text-xs"><span className={p.enabled ? "text-white/80" : "text-white/30"}>{p.label}</span><span className="text-white/40">{p.privacy}{p.enabled ? "" : " · off (no key)"}</span></div>)}
        {r.transitions.length > 0 && <><h4 className="mt-3 mb-1 text-[11px] uppercase tracking-widest text-white/40">Transitions</h4>{r.transitions.map((t: any, i: number) => <div key={i} className="text-xs text-white/60">{new Date(t.t).toLocaleTimeString()} → {t.to}: {t.reason}</div>)}</>}
      </Card>
    </div>
  );
}

/* ------------------------------ perf ------------------------------ */
export function PerfPanel() {
  const [s, setS] = useState<{ n: number; p50: number; p95: number; max: number; slow: number; tr: number } | null>(null);
  useEffect(() => {
    const id = setInterval(() => {
      const f = [...(window.__voxFrames ?? [])].sort((a, b) => a - b);
      if (!f.length) return setS(null);
      const q = (x: number) => f[Math.min(f.length - 1, Math.floor(f.length * x))];
      setS({ n: f.length, p50: q(0.5), p95: q(0.95), max: f[f.length - 1], slow: f.filter((x) => x > 50).length, tr: window.__voxTransitions ?? 0 });
    }, 1000);
    return () => clearInterval(id);
  }, []);
  return (
    <Card title="Notch frame times (measured in this browser, during spring animations only)" right={<Btn onClick={() => { window.__voxFrames = []; }}>Clear</Btn>}>
      {!s ? <p className="text-xs text-white/50">Trigger some state changes (or “Run UI demo”) to collect frames.</p> : (
        <dl className="grid max-w-sm grid-cols-2 gap-y-1 text-sm">
          <dt className="text-white/40">Frames sampled</dt><dd>{s.n}</dd>
          <dt className="text-white/40">p50</dt><dd>{s.p50.toFixed(1)} ms</dd>
          <dt className="text-white/40">p95</dt><dd className={s.p95 <= 16.7 ? "text-emerald-300" : "text-amber-300"}>{s.p95.toFixed(1)} ms {s.p95 <= 16.7 ? "(≤ 16.6 ✓)" : "(> 16.6)"}</dd>
          <dt className="text-white/40">max</dt><dd>{s.max.toFixed(1)} ms</dd>
          <dt className="text-white/40">frames &gt; 50 ms</dt><dd>{s.slow}</dd>
          <dt className="text-white/40">state transitions</dt><dd>{s.tr}</dd>
        </dl>
      )}
      <p className="mt-3 text-xs text-white/40">Springs: expand k=380 c=27 (ζ≈0.69, ≈5% overshoot, ≈300 ms); collapse k=330 c=36.3 (critically damped, ≈220 ms). The animation loop stops when settled, so collapsed idle costs no JS per frame. Numbers depend on your machine and a headless/background tab will throttle rAF.</p>
    </Card>
  );
}

/* ------------------------------ about / status ------------------------------ */
const ROWS: [string, string, string][] = [
  ["Notch UI (shape, springs, 10 states, echo, hover panel, mode badge, privacy dots, reduce-motion)", "Built (web)", "Implemented in React/SVG. Not Qt Quick/QML; Win32 window flags (no-activate, click-through, fullscreen hide) not applicable in a browser."],
  ["Safety model (tiers, escalation, protected policy, bound approvals, T2 click-only, untrusted tagging, redaction, audit)", "Built + tested", "TypeScript reference implementation; 25-case red-team suite runs in-app."],
  ["Provider router (health, hysteresis, mid-task failover, offline guard)", "Built + tested", "Guard is application-level, not socket-level. Cloud/local models are scripted fakes unless ANTHROPIC_API_KEY / OLLAMA_MODEL are set (adapters written, not exercised here)."],
  ["Tool registry + task engine (plan, evidence, pause/resume/stop, loop + budget limits)", "Built", "~45 tools on a Postgres-backed virtual PC. Not real Windows APIs. click_target/read_ui, drag, zip, brightness/volume Core Audio, CDP browser not implemented."],
  ["Voice: wake word, Silero VAD, Faster-Whisper, Piper, AEC, loopback voice-injection defence", "Not built", "Browser SpeechRecognition + speechSynthesis are used as stand-ins; voice-injection defence is a half-duplex gate."],
  ["Windows app: PySide6/QML, Win32, UIA, Core Audio, installers, signing, soak tests", "Not built", "Cannot be built or verified in this Linux sandbox. See docs/FINAL_REPORT.md and docs/BACKLOG.md."],
];
export function AboutPanel() {
  return (
    <Card title="What exists in this build, honestly">
      <div className="space-y-2 text-xs">
        {ROWS.map(([a, b, c]) => (
          <div key={a} className="rounded-lg bg-white/5 p-2.5">
            <div className="flex items-start justify-between gap-3"><span className="text-white/85">{a}</span><span className={`shrink-0 rounded px-1.5 py-0.5 text-[10px] font-semibold ${b.startsWith("Not") ? "bg-red-500/20 text-red-300" : "bg-emerald-500/15 text-emerald-300"}`}>{b}</span></div>
            <div className="mt-1 text-white/45">{c}</div>
          </div>
        ))}
      </div>
    </Card>
  );
}
