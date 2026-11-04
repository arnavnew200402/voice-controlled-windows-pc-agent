"use client";
import { useCallback, useEffect, useReducer, useRef, useState } from "react";
import type { CoreState, Envelope, Mode, VoxEvent } from "@/lib/vox/events";
import type { Lang, NotchState } from "./theme";
import { THEME } from "./theme";

export type Approval = { id: string; tier: 1 | 2; title: string; details: string[]; untrusted: boolean; expiresAt: number; hint?: string };
export type VS = {
  core: CoreState;
  listening: boolean;
  wake: boolean;
  speaking: boolean;
  partial: string;
  transcript: string;
  intent: string;
  step: number;
  of: number;
  steps: ("wait" | "run" | "ok" | "fail")[];
  actionTitle: string;
  actions: { title: string; ok: boolean; evidence: string }[];
  approval: Approval | null;
  reply: string;
  replyId: number;
  replySpoken: boolean;
  mode: { requested: Mode; effective: "online" | "offline" };
  badge: { effective: "online" | "offline"; reason: string; until: number } | null;
  privacy: { mic: boolean; screen: boolean; cloud: boolean };
  echo: { kind: string; value: number; label: string; until: number } | null;
  error: { code: string; message: string; until: number } | null;
  events: Envelope[];
  lastCommand: string;
  busy: boolean;
  turns: number;
};

const init: VS = {
  core: "IDLE", listening: false, wake: false, speaking: false, partial: "", transcript: "", intent: "", step: 0, of: 0, steps: [],
  actionTitle: "", actions: [], approval: null, reply: "", replyId: 0, replySpoken: false,
  mode: { requested: "auto", effective: "online" }, badge: null, privacy: { mic: false, screen: false, cloud: false },
  echo: null, error: null, events: [], lastCommand: "", busy: false, turns: 0,
};

type A =
  | { t: "env"; env: Envelope }
  | { t: "patch"; p: Partial<VS> }
  | { t: "newTurn"; text: string }
  | { t: "turnEnd" };

function reduce(s: VS, a: A): VS {
  if (a.t === "patch") return { ...s, ...a.p };
  if (a.t === "newTurn") return { ...s, lastCommand: a.text, busy: true, step: 0, of: 0, steps: [], intent: "", reply: "", error: null, partial: "", transcript: a.text, actionTitle: "" };
  if (a.t === "turnEnd") return { ...s, busy: false, core: s.core === "ERROR" ? "IDLE" : s.approval ? s.core : "IDLE", approval: null, turns: s.turns + 1 };
  const e: VoxEvent = a.env.event;
  const base: VS = { ...s, events: [a.env, ...s.events].slice(0, 120) };
  switch (e.type) {
    case "StateChanged": return { ...base, core: e.state === "SPEAKING" ? base.core : e.state };
    case "Transcript": return { ...base, transcript: e.text, partial: e.partial ? e.text : "" };
    case "Intent": return { ...base, intent: e.summary };
    case "ToolStarted": {
      const steps: VS["steps"] = Array.from({ length: Math.max(e.of, base.steps.length) }, (_, i) =>
        i < e.step - 1 ? (base.steps[i] === "fail" ? "fail" : "ok") : i === e.step - 1 ? "run" : "wait",
      );
      return { ...base, actionTitle: e.title, step: e.step, of: e.of, steps };
    }
    case "ToolFinished": {
      const steps = [...base.steps];
      if (base.step > 0) steps[base.step - 1] = e.ok ? "ok" : "fail";
      return { ...base, steps, actions: [{ title: base.actionTitle, ok: e.ok, evidence: e.evidence }, ...base.actions].slice(0, 8) };
    }
    case "ApprovalRequested":
      return { ...base, core: "APPROVAL", approval: { id: e.id, tier: e.tier, title: e.title, details: e.details, untrusted: e.untrustedDerived, expiresAt: e.expiresAt } };
    case "ApprovalResolved": return { ...base, approval: null };
    case "Reply": return { ...base, reply: e.text, replyId: base.replyId + 1, replySpoken: e.spoken };
    case "ModeChanged": {
      const changed = e.effective !== base.mode.effective || /Cloud failed|selected/i.test(e.reason);
      return { ...base, mode: { requested: e.requested, effective: e.effective }, badge: changed ? { effective: e.effective, reason: e.reason, until: Date.now() + THEME.timing.badgeMs } : base.badge };
    }
    case "PrivacyIndicator": return { ...base, privacy: { ...base.privacy, screen: e.screenCapturing, cloud: e.cloudActive } };
    case "Error": return { ...base, error: { code: e.code, message: e.message, until: Date.now() + THEME.timing.errorMs } };
    case "EchoHud": return { ...base, echo: { kind: e.kind, value: e.value, label: e.label, until: Date.now() + THEME.timing.echoMs } };
    default: return base;
  }
}

export function displayState(s: VS): NotchState {
  if (s.approval) return "approval";
  if (s.error) return "error";
  if (s.speaking) return "speaking";
  if (s.echo) return "echo";
  if (s.core === "ACTING") return "acting";
  if (s.core === "THINKING") return "thinking";
  if (s.listening) return "listening";
  if (s.wake) return "wake";
  return "idle";
}

type SR = {
  lang: string; interimResults: boolean; continuous: boolean; onresult: ((e: { results: ArrayLike<ArrayLike<{ transcript: string }> & { isFinal: boolean }> }) => void) | null;
  onerror: (() => void) | null; onend: (() => void) | null; start(): void; stop(): void;
};

const YES = /^(yes|yeah|yep|do it|go ahead|confirm|haan|हाँ|हां)$/i;
const NO = /^(no|nope|cancel|stop|don'?t|nahi|नहीं|रुको)$/i;
const norm = (s: string) => s.trim().replace(/[.!?,]+$/g, "");

export function useVox() {
  const [vs, dispatch] = useReducer(reduce, init);
  const [lang, setLang] = useState<Lang>("en");
  const [muted, setMuted] = useState(false);
  const [tick, setTick] = useState(0);
  const levelRef = useRef(0);
  const vsRef = useRef(vs);
  vsRef.current = vs;
  const listenRef = useRef<{ stop: () => void } | null>(null);
  const speakingRef = useRef(false);
  const demoRef = useRef<{ cancel: boolean }>({ cancel: false });

  const emitLocal = useCallback((event: VoxEvent) => dispatch({ t: "env", env: { v: 1, seq: -1, ts: Date.now(), turnId: null, event } }), []);

  /* ---------- timers: echo / error / badge fold away on their own ---------- */
  useEffect(() => {
    const times = [vs.echo?.until, vs.error?.until, vs.badge?.until].filter(Boolean) as number[];
    if (!times.length) return;
    const id = setTimeout(() => {
      const now = Date.now();
      const p: Partial<VS> = {};
      if (vsRef.current.echo && vsRef.current.echo.until <= now) p.echo = null;
      if (vsRef.current.error && vsRef.current.error.until <= now) p.error = null;
      if (vsRef.current.badge && vsRef.current.badge.until <= now) p.badge = null;
      dispatch({ t: "patch", p });
    }, Math.max(30, Math.min(...times) - Date.now() + 20));
    return () => clearTimeout(id);
  }, [vs.echo, vs.error, vs.badge]);

  /* ---------- TTS: spoken reply drives the speaking state + synthetic TtsLevel ---------- */
  useEffect(() => {
    if (!vs.replyId || !vs.replySpoken || !vs.reply) return;
    let done = false;
    let raf = 0;
    const end = () => {
      if (done) return;
      done = true;
      speakingRef.current = false;
      cancelAnimationFrame(raf);
      levelRef.current = 0;
      dispatch({ t: "patch", p: { speaking: false } });
    };
    speakingRef.current = true;
    dispatch({ t: "patch", p: { speaking: true } });
    const t0 = performance.now();
    const loop = () => {
      const t = (performance.now() - t0) / 1000;
      levelRef.current = 0.3 + 0.35 * Math.abs(Math.sin(t * 7.3)) + 0.2 * Math.abs(Math.sin(t * 13.1 + 1));
      raf = requestAnimationFrame(loop);
    };
    raf = requestAnimationFrame(loop);
    const fallbackMs = Math.min(9000, 900 + vs.reply.length * 62);
    const fb = setTimeout(end, fallbackMs);
    const synth = typeof window !== "undefined" ? window.speechSynthesis : undefined;
    if (synth && typeof SpeechSynthesisUtterance !== "undefined") {
      try {
        synth.cancel();
        const u = new SpeechSynthesisUtterance(vs.reply);
        u.lang = lang === "hi" ? "hi-IN" : "en-US";
        u.onend = () => { clearTimeout(fb); setTimeout(end, 250); };
        u.onerror = () => {};
        synth.speak(u);
      } catch { /* fallback timer handles it */ }
    }
    return () => { clearTimeout(fb); end(); };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [vs.replyId]);

  /* ---------- sending a turn: consume the NDJSON event stream ---------- */
  const send = useCallback(async (text: string, scenario?: { cutNetworkAfter?: number }) => {
    const t = text.trim();
    if (!t) return;
    dispatch({ t: "newTurn", text: t });
    try {
      const res = await fetch("/api/turn", { method: "POST", headers: { "content-type": "application/json" }, body: JSON.stringify({ text: t, lang, scenario }) });
      if (!res.body) throw new Error("no stream");
      const reader = res.body.getReader();
      const dec = new TextDecoder();
      let buf = "";
      for (;;) {
        const { done, value } = await reader.read();
        if (done) break;
        buf += dec.decode(value, { stream: true });
        let i;
        while ((i = buf.indexOf("\n")) >= 0) {
          const line = buf.slice(0, i).trim();
          buf = buf.slice(i + 1);
          if (line) dispatch({ t: "env", env: JSON.parse(line) as Envelope });
        }
      }
    } catch (e) {
      emitLocal({ type: "Error", code: "NETWORK", message: (e as Error).message, recoverable: true });
    }
    dispatch({ t: "turnEnd" });
    setTick((x) => x + 1);
  }, [lang, emitLocal]);

  /* ---------- approvals ---------- */
  const resolve = useCallback(async (decision: "approved" | "denied", via: "click" | "voice" | "hotkey") => {
    const a = vsRef.current.approval;
    if (!a) return;
    const r = await fetch(`/api/approvals/${a.id}`, {
      method: "POST", headers: { "content-type": "application/json" },
      body: JSON.stringify({ decision, via, loopbackOverlap: via === "voice" && speakingRef.current }),
    });
    if (!r.ok) {
      const j = (await r.json()) as { error?: string };
      if (j.error === "T2_REQUIRES_PHYSICAL_CONFIRMATION") dispatch({ t: "patch", p: { approval: { ...a, hint: "voice" } } });
      else if (j.error === "VOICE_MATCHES_LOOPBACK") dispatch({ t: "patch", p: { approval: { ...a, hint: "loopback" } } });
    }
  }, []);

  const stop = useCallback(async () => {
    window.speechSynthesis?.cancel();
    listenRef.current?.stop();
    demoRef.current.cancel = true;
    await fetch("/api/stop", { method: "POST" });
    dispatch({ t: "patch", p: { speaking: false, listening: false, wake: false, echo: null, error: null } });
  }, []);

  /* ---------- microphone: real level via WebAudio, transcript via SpeechRecognition ---------- */
  const stopListening = useCallback(() => listenRef.current?.stop(), []);
  const startListening = useCallback(async () => {
    if (listenRef.current || muted) return;
    window.speechSynthesis?.cancel(); // barge-in by hotkey
    dispatch({ t: "patch", p: { speaking: false, wake: true } });
    let stream: MediaStream;
    try {
      stream = await navigator.mediaDevices.getUserMedia({ audio: { echoCancellation: true, noiseSuppression: true } });
    } catch {
      dispatch({ t: "patch", p: { wake: false } });
      emitLocal({ type: "Error", code: "MIC_DENIED", message: "Microphone unavailable. Type a command instead.", recoverable: true });
      return;
    }
    const AC = window.AudioContext ?? (window as unknown as { webkitAudioContext: typeof AudioContext }).webkitAudioContext;
    const ctx = new AC();
    const an = ctx.createAnalyser();
    an.fftSize = 512;
    ctx.createMediaStreamSource(stream).connect(an);
    const buf = new Float32Array(an.fftSize);
    let raf = 0;
    let finished = false;
    const loop = () => {
      an.getFloatTimeDomainData(buf);
      let sum = 0;
      for (const x of buf) sum += x * x;
      levelRef.current = Math.min(1, Math.sqrt(sum / buf.length) * 7);
      raf = requestAnimationFrame(loop);
    };
    raf = requestAnimationFrame(loop);
    const W = window as unknown as { SpeechRecognition?: new () => SR; webkitSpeechRecognition?: new () => SR };
    const Rec = W.SpeechRecognition ?? W.webkitSpeechRecognition;
    let rec: SR | null = null;
    let noStt: ReturnType<typeof setTimeout> | undefined;
    const finish = () => {
      if (finished) return;
      finished = true;
      clearTimeout(noStt);
      cancelAnimationFrame(raf);
      stream.getTracks().forEach((t) => t.stop());
      ctx.close().catch(() => {});
      try { rec?.stop(); } catch { /* ignore */ }
      levelRef.current = 0;
      listenRef.current = null;
      dispatch({ t: "patch", p: { listening: false, wake: false, partial: "", privacy: { ...vsRef.current.privacy, mic: false } } });
    };
    listenRef.current = { stop: finish };
    setTimeout(() => {
      if (finished) return;
      dispatch({ t: "patch", p: { wake: false, listening: true, privacy: { ...vsRef.current.privacy, mic: true } } });
    }, THEME.timing.wakeMs);
    if (!Rec) {
      noStt = setTimeout(() => {
        finish();
        emitLocal({ type: "Error", code: "NO_STT", message: "This browser has no speech recognition. Type your command.", recoverable: true });
      }, 5000);
      return;
    }
    rec = new Rec();
    rec.lang = lang === "hi" ? "hi-IN" : "en-US";
    rec.interimResults = true;
    rec.continuous = false;
    rec.onresult = (ev) => {
      let text = "";
      let final = false;
      for (let i = 0; i < ev.results.length; i++) {
        text += ev.results[i][0].transcript;
        if (ev.results[i].isFinal) final = true;
      }
      if (!final) { dispatch({ t: "patch", p: { partial: text } }); return; }
      finish();
      const n = norm(text);
      const ap = vsRef.current.approval;
      if (ap && YES.test(n)) void resolve("approved", "voice");
      else if (ap && NO.test(n)) void resolve("denied", "voice");
      else void send(text);
    };
    rec.onerror = () => finish();
    rec.onend = () => finish();
    try { rec.start(); } catch { finish(); }
  }, [muted, lang, resolve, send, emitLocal]);

  /* ---------- hotkeys ---------- */
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.ctrlKey && e.shiftKey && e.key.toLowerCase() === "q") { e.preventDefault(); void stop(); }
      else if (e.ctrlKey && e.shiftKey && e.key.toLowerCase() === "y" && e.isTrusted) { e.preventDefault(); void resolve("approved", "hotkey"); }
      else if (e.ctrlKey && e.shiftKey && e.key.toLowerCase() === "n" && e.isTrusted) { e.preventDefault(); void resolve("denied", "hotkey"); }
      else if (e.altKey && e.key.toLowerCase() === "v") { e.preventDefault(); if (listenRef.current) stopListening(); else void startListening(); }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [stop, resolve, startListening, stopListening]);

  /* ---------- mode ---------- */
  const setMode = useCallback(async (mode: Mode) => {
    const r = await fetch("/api/mode", { method: "POST", headers: { "content-type": "application/json" }, body: JSON.stringify({ mode }) });
    const j = (await r.json()) as { router: { effective: "online" | "offline" } };
    emitLocal({ type: "ModeChanged", requested: mode, effective: j.router.effective, reason: `User selected ${mode}` });
    setTick((x) => x + 1);
  }, [emitLocal]);

  const setNetwork = useCallback(async (up: boolean) => {
    const r = await fetch("/api/mode", { method: "POST", headers: { "content-type": "application/json" }, body: JSON.stringify({ networkUp: up }) });
    const j = (await r.json()) as { router: { effective: "online" | "offline"; requested: Mode } };
    emitLocal({ type: "ModeChanged", requested: j.router.requested, effective: j.router.effective, reason: up ? "Selected: network restored" : "Cloud failed: network cut" });
    setTick((x) => x + 1);
  }, [emitLocal]);

  /* ---------- synthetic UI demo cycling through every state (--ui-demo) ---------- */
  const runDemo = useCallback(async () => {
    demoRef.current = { cancel: false };
    const d = demoRef.current;
    const wait = (ms: number) => new Promise((r) => setTimeout(r, ms));
    const ev = (event: VoxEvent) => { if (!d.cancel) emitLocal(event); };
    const p = (patch: Partial<VS>) => { if (!d.cancel) dispatch({ t: "patch", p: patch }); };
    let raf = 0;
    const t0 = performance.now();
    const lv = () => { levelRef.current = 0.25 + 0.5 * Math.abs(Math.sin((performance.now() - t0) / 140)); raf = requestAnimationFrame(lv); };
    raf = requestAnimationFrame(lv);
    p({ wake: true }); await wait(700);
    p({ wake: false, listening: true, privacy: { ...vsRef.current.privacy, mic: true } });
    for (const w of ["open", "Notepad", "and", "type", "hello"]) { p({ partial: (vsRef.current.partial + " " + w).trim() }); await wait(380); }
    p({ listening: false, partial: "", privacy: { ...vsRef.current.privacy, mic: false } });
    ev({ type: "Transcript", text: "open Notepad and type hello", partial: false, lang: "en" });
    ev({ type: "StateChanged", state: "THINKING", reason: "demo" });
    ev({ type: "Intent", summary: "Open Notepad and type hello" });
    ev({ type: "PrivacyIndicator", micOpen: false, screenCapturing: false, cloudActive: true });
    await wait(1500);
    ev({ type: "PrivacyIndicator", micOpen: false, screenCapturing: false, cloudActive: false });
    ev({ type: "StateChanged", state: "ACTING", reason: "demo" });
    ev({ type: "ToolStarted", id: "d1", name: "open_app", title: "Open Notepad", step: 1, of: 2 });
    await wait(900);
    ev({ type: "ToolFinished", id: "d1", ok: true, evidence: "Opened Notepad" });
    ev({ type: "ToolStarted", id: "d2", name: "type_text", title: 'Type "hello"', step: 2, of: 2 });
    await wait(900);
    ev({ type: "ToolFinished", id: "d2", ok: true, evidence: "Typed 5 characters" });
    await wait(500);
    ev({ type: "ApprovalRequested", id: "demo", tier: 1, title: "Delete 14 items from Downloads?", details: ["invoice_march.pdf", "photo_001.jpg", "Goes to the Recycle Bin"], untrustedDerived: false, expiresAt: Date.now() + 15000 });
    await wait(2600);
    ev({ type: "ApprovalResolved", id: "demo", decision: "approved", via: "click" });
    ev({ type: "Reply", text: "Opened Notepad and typed hello.", spoken: true });
    await wait(3000);
    p({ speaking: false });
    ev({ type: "StateChanged", state: "IDLE", reason: "demo" });
    ev({ type: "EchoHud", kind: "volume", value: 30, label: "Volume" });
    await wait(1600);
    ev({ type: "Error", code: "BLOCKED_BY_POLICY", message: "Blocked: Protected path: Windows directory", recoverable: true });
    await wait(2200);
    ev({ type: "ModeChanged", requested: "auto", effective: "offline", reason: "Cloud failed: demo" });
    await wait(2000);
    ev({ type: "ModeChanged", requested: "auto", effective: "online", reason: "Selected: demo" });
    await wait(1700);
    cancelAnimationFrame(raf);
    levelRef.current = 0;
    p({ speaking: false, listening: false, wake: false });
    dispatch({ t: "turnEnd" });
  }, [emitLocal]);

  return { vs, lang, setLang, muted, setMuted, send, resolve, stop, startListening, stopListening, setMode, setNetwork, runDemo, levelRef, tick };
}
