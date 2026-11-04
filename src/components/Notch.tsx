"use client";
import { useEffect, useMemo, useRef, useState, type MutableRefObject, type ReactNode } from "react";
import type { Mode } from "@/lib/vox/events";
import { displayState, type VS } from "@/lib/client/useVox";
import { THEME, tr, type Lang, type NotchState } from "@/lib/client/theme";

declare global {
  interface Window { __voxFrames?: number[]; __voxTransitions?: number }
}

type Props = {
  vs: VS;
  lang: Lang;
  levelRef: MutableRefObject<number>;
  muted: boolean;
  ptt: boolean;
  reduceMotion: boolean;
  onResolve: (d: "approved" | "denied", via: "click" | "voice" | "hotkey") => void;
  onMode: (m: Mode) => void;
  onSend: (t: string) => void;
  onMute: () => void;
  onPtt: () => void;
  onTab: (t: string) => void;
};

const EAR = THEME.ear;

function pathFor(w: number, h: number, r: number) {
  const e = EAR;
  const rr = Math.max(0, Math.min(r, h - e - 1, w / 2));
  const W = w + 2 * e;
  return `M0,0 Q${e},0 ${e},${e} L${e},${h - rr} Q${e},${h} ${e + rr},${h} L${e + w - rr},${h} Q${e + w},${h} ${e + w},${h - rr} L${e + w},${e} Q${e + w},0 ${W},0 Z`;
}

/* ------------------------------ waveform (canvas, driven by levelRef) ------------------------------ */
function Waveform({ levelRef, color, bars = 40, height = 34 }: { levelRef: MutableRefObject<number>; color: string; bars?: number; height?: number }) {
  const ref = useRef<HTMLCanvasElement>(null);
  useEffect(() => {
    const cv = ref.current!;
    const ctx = cv.getContext("2d")!;
    const dpr = window.devicePixelRatio || 1;
    const W = 340, H = height;
    cv.width = W * dpr; cv.height = H * dpr;
    ctx.scale(dpr, dpr);
    let sm = 0, raf = 0, last = performance.now();
    const phase = Array.from({ length: bars }, (_, i) => i * 0.9 + (i % 3));
    const draw = (now: number) => {
      const dt = Math.min(0.05, (now - last) / 1000);
      last = now;
      const tgt = levelRef.current;
      // attack ~20 ms, release ~120 ms
      sm += (tgt - sm) * (1 - Math.exp(-dt / (tgt > sm ? 0.02 : 0.12)));
      document.documentElement.style.setProperty("--lvl", sm.toFixed(3));
      ctx.clearRect(0, 0, W, H);
      ctx.fillStyle = color;
      const bw = W / bars;
      for (let i = 0; i < bars; i++) {
        const env = Math.sin((i / (bars - 1)) * Math.PI);
        const n = 0.45 + 0.55 * Math.abs(Math.sin(now / 160 + phase[i]));
        const h = Math.max(2, sm * env * n * H);
        ctx.globalAlpha = 0.5 + 0.5 * env;
        ctx.beginPath();
        ctx.roundRect(i * bw + 1, (H - h) / 2, bw - 3, h, 2);
        ctx.fill();
      }
      raf = requestAnimationFrame(draw);
    };
    raf = requestAnimationFrame(draw);
    return () => { cancelAnimationFrame(raf); document.documentElement.style.setProperty("--lvl", "0"); };
  }, [levelRef, color, bars, height]);
  return <canvas ref={ref} style={{ width: 340, height }} aria-hidden />;
}

const MicGlyph = ({ c }: { c: string }) => (
  <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke={c} strokeWidth="2" strokeLinecap="round"><rect x="9" y="3" width="6" height="12" rx="3" /><path d="M5 11a7 7 0 0 0 14 0M12 18v3" /></svg>
);
const Cloud = () => <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d="M7 18a4 4 0 0 1-.5-8A6 6 0 0 1 18 9a4.5 4.5 0 0 1-.5 9z" /></svg>;
const Chip = () => <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><rect x="6" y="6" width="12" height="12" rx="2" /><path d="M9 2v4M15 2v4M9 18v4M15 18v4M2 9h4M2 15h4M18 9h4M18 15h4" /></svg>;

function Row({ i, children, className = "" }: { i: number; children: ReactNode; className?: string }) {
  return <div className={`enter ${className}`} style={{ ["--i" as string]: i }}>{children}</div>;
}

/* ------------------------------ content per state ------------------------------ */
function Content(p: Props & { shown: NotchState }) {
  const { vs, lang, shown, levelRef } = p;
  const col = THEME.color[shown];
  const words = vs.partial.split(/\s+/).filter(Boolean);
  const [now, setNow] = useState(() => Date.now());
  const ap = vs.approval;
  const ringMs = useMemo(() => (ap ? Math.max(1000, ap.expiresAt - Date.now()) : 0), [ap]);
  const [text, setText] = useState("");
  useEffect(() => {
    if (shown !== "approval") return;
    const id = setInterval(() => setNow(Date.now()), 500);
    return () => clearInterval(id);
  }, [shown]);

  if (shown === "idle")
    return (
      <div className="flex h-full items-center justify-end gap-1.5 pr-5">
        {vs.privacy.mic && <span title="Mic open" className="h-1.5 w-1.5 rounded-full bg-sky-400" />}
        {vs.privacy.screen && <span title="Screen being captured" className="h-1.5 w-1.5 rounded-full bg-violet-400" />}
        {vs.privacy.cloud && <span title="Cloud in use" className="h-1.5 w-1.5 rounded-full bg-amber-400" />}
        {vs.busy && <span className="pulse-dot h-1.5 w-1.5 rounded-full bg-emerald-400" title="Task running" />}
      </div>
    );
  if (shown === "wake")
    return (
      <div className="flex h-full items-center justify-center gap-3 px-6 text-sm text-white/90">
        <Row i={0}><MicGlyph c={col} /></Row>
        <Row i={1}>{tr(lang, "wake")}</Row>
      </div>
    );
  if (shown === "listening")
    return (
      <div className="flex h-full flex-col items-center justify-center gap-2 px-6 pb-2">
        <Row i={0}><Waveform levelRef={levelRef} color={col} /></Row>
        <Row i={1} className="min-h-5 w-full truncate text-center text-sm text-white/90">
          {words.length === 0 ? <span className="text-white/45">{tr(lang, "listening")}</span> : words.map((w, i) => <span key={i} className={i === words.length - 1 ? "word-in" : ""}>{w} </span>)}
        </Row>
      </div>
    );
  if (shown === "thinking")
    return (
      <div className="flex h-full flex-col items-center justify-center gap-2 px-8">
        <Row i={0} className="flex items-center gap-2 text-xs uppercase tracking-widest text-violet-300/90">
          <span className="orbit" /> {tr(lang, "thinking")}
        </Row>
        <Row i={1} className="w-full truncate text-center text-sm text-white/90">{vs.intent || vs.transcript}</Row>
      </div>
    );
  if (shown === "acting")
    return (
      <div className="flex h-full flex-col justify-center gap-2.5 px-8">
        <Row i={0} className="flex items-center justify-between">
          <span className="truncate text-sm font-medium text-white">{vs.actionTitle || "…"}</span>
          <span className="shrink-0 pl-3 text-xs text-emerald-300/90">{tr(lang, "step", { n: Math.max(1, vs.step), m: Math.max(1, vs.of) })}</span>
        </Row>
        <Row i={1} className="flex gap-1.5">
          {(vs.steps.length ? vs.steps : ["run"]).map((s, i) => (
            <span key={i} className={`flex h-5 flex-1 items-center justify-center rounded-full text-[10px] ${s === "ok" ? "bg-emerald-400/20 text-emerald-300" : s === "fail" ? "bg-red-400/20 text-red-300" : s === "run" ? "bg-emerald-400/10 shimmer-bar" : "bg-white/5"}`}>
              {s === "ok" && <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="3"><path className="check" d="M5 13l4 4L19 7" /></svg>}
              {s === "fail" && "✕"}
            </span>
          ))}
        </Row>
      </div>
    );
  if (shown === "approval" && ap) {
    const left = Math.max(0, Math.ceil((ap.expiresAt - now) / 1000));
    return (
      <div className="flex h-full flex-col gap-2 px-7 pt-3.5 pb-3">
        <Row i={0} className="flex items-start justify-between gap-3">
          <div className="min-w-0">
            <div className="text-[10px] font-semibold uppercase tracking-widest text-amber-300">{ap.tier === 2 ? "Confirm — hard" : "Confirm"}</div>
            <div className="truncate text-[15px] font-semibold text-white">{ap.title}</div>
          </div>
          <svg width="26" height="26" viewBox="0 0 26 26" className="shrink-0">
            <circle cx="13" cy="13" r="10" fill="none" stroke="rgba(255,255,255,.12)" strokeWidth="2.5" />
            <circle key={ap.id} cx="13" cy="13" r="10" fill="none" stroke="#FF9F0A" strokeWidth="2.5" strokeLinecap="round" pathLength={100} strokeDasharray="100" className="ring" style={{ animationDuration: `${ringMs}ms`, transformOrigin: "center", transform: "rotate(-90deg)" }} />
            <text x="13" y="16.5" textAnchor="middle" fontSize="9" fill="#fff">{left}</text>
          </svg>
        </Row>
        <Row i={1} className="max-h-[58px] overflow-hidden text-xs leading-4 text-white/65">
          {ap.details.slice(0, 4).map((d, i) => <div key={i} className={`truncate ${d.startsWith("This came") ? "font-medium text-amber-300" : ""}`}>• {d}</div>)}
        </Row>
        <Row i={2} className="mt-auto flex items-center gap-2">
          {ap.tier === 1 ? (
            <>
              <button onClick={(e) => p.onResolve("approved", e.isTrusted ? "click" : "voice")} className="rounded-full bg-amber-400 px-4 py-1 text-xs font-semibold text-black hover:bg-amber-300">{tr(lang, "yes")}</button>
              <button onClick={() => p.onResolve("denied", "click")} className="rounded-full bg-white/10 px-4 py-1 text-xs font-semibold text-white hover:bg-white/20">{tr(lang, "no")}</button>
              <span className="ml-auto text-[11px] text-white/40">{ap.hint === "loopback" ? "Heard your own speaker — click instead" : tr(lang, "sayYes")}</span>
            </>
          ) : (
            <>
              <button onClick={(e) => p.onResolve("approved", e.isTrusted ? "click" : "voice")} className="rounded-full bg-amber-400 px-4 py-1 text-xs font-semibold text-black hover:bg-amber-300">{tr(lang, "confirm")}</button>
              <button onClick={() => p.onResolve("denied", "click")} className="rounded-full bg-white/10 px-4 py-1 text-xs font-semibold text-white hover:bg-white/20">{tr(lang, "deny")}</button>
              <span className={`ml-auto text-[11px] ${ap.hint === "voice" ? "text-amber-300" : "text-white/40"}`}>{ap.hint === "voice" ? tr(lang, "voiceNo") : "Ctrl+Shift+Y"}</span>
            </>
          )}
        </Row>
      </div>
    );
  }
  if (shown === "speaking")
    return (
      <div className="flex h-full flex-col items-center justify-center gap-2 px-6">
        <Row i={0}><Waveform levelRef={levelRef} color={col} bars={36} /></Row>
        <Row i={1} className="text-[11px] uppercase tracking-widest text-teal-200/70">Vox</Row>
      </div>
    );
  if (shown === "error")
    return (
      <div className="flex h-full flex-col justify-center px-7">
        <Row i={0} className="truncate text-sm font-medium text-red-300">{vs.error?.message}</Row>
        <Row i={1} className="text-[11px] text-white/45">{vs.error?.code}</Row>
      </div>
    );
  if (shown === "echo" && vs.echo) {
    const pct = Math.max(0, Math.min(100, vs.echo.value));
    return (
      <div className="flex h-full flex-col justify-center gap-2 px-6">
        <Row i={0} className="flex items-center justify-between text-xs text-white/80"><span>{vs.echo.label}</span><span className="tabular-nums">{vs.echo.kind === "volume" || vs.echo.kind === "brightness" ? Math.round(pct) : ""}</span></Row>
        <Row i={1} className="h-1.5 overflow-hidden rounded-full bg-white/10"><div className="echo-bar h-full rounded-full bg-teal-200" style={{ width: `${pct}%` }} /></Row>
      </div>
    );
  }
  /* hover panel */
  return (
    <div className="flex h-full flex-col gap-2.5 px-6 pt-4 pb-3 text-white">
      <Row i={0} className="flex items-center gap-2">
        <span className="text-[10px] uppercase tracking-widest text-white/40">{tr(lang, "mode")}</span>
        {(["offline", "auto", "online"] as Mode[]).map((m) => (
          <button key={m} onClick={() => p.onMode(m)} className={`rounded-full px-3 py-0.5 text-xs ${vs.mode.requested === m ? "bg-white text-black" : "bg-white/10 text-white/80 hover:bg-white/20"}`}>{tr(lang, m)}</button>
        ))}
        <span className="ml-auto flex items-center gap-1 text-[11px] text-white/50">{vs.mode.effective === "online" ? <Cloud /> : <Chip />}{tr(lang, vs.mode.effective)}</span>
      </Row>
      <Row i={1} className="flex items-center gap-2 text-xs">
        <button onClick={p.onMute} className={`rounded-full px-3 py-0.5 ${p.muted ? "bg-red-400/80 text-black" : "bg-white/10 hover:bg-white/20"}`}>{tr(lang, "mute")}</button>
        <button onClick={p.onPtt} className={`rounded-full px-3 py-0.5 ${p.ptt ? "bg-sky-400 text-black" : "bg-white/10 hover:bg-white/20"}`}>{tr(lang, "ptt")}</button>
        <button onClick={() => p.onTab("router")} className="ml-auto rounded-full bg-white/10 px-3 py-0.5 hover:bg-white/20">{tr(lang, "settings")}</button>
      </Row>
      <Row i={2} className="min-h-0 flex-1 overflow-hidden text-xs">
        <div className="truncate text-white/40">{tr(lang, "last")}: <span className="text-white/80">{vs.lastCommand || tr(lang, "none")}</span></div>
        <div className="truncate text-white/65">{vs.reply}</div>
        <div className="mt-1 text-white/40">{tr(lang, "actions")}</div>
        {vs.actions.slice(0, 3).map((a, i) => <div key={i} className="truncate text-white/70">{a.ok ? "✓" : "✕"} {a.title}</div>)}
      </Row>
      <Row i={3}>
        <form onSubmit={(e) => { e.preventDefault(); if (text.trim()) { p.onSend(text); setText(""); } }}>
          <input value={text} onChange={(e) => setText(e.target.value)} placeholder={tr(lang, "placeholder")} className="w-full rounded-full bg-white/10 px-4 py-1.5 text-xs text-white placeholder-white/35 outline-none focus:bg-white/15" />
        </form>
      </Row>
    </div>
  );
}

/* ------------------------------ the notch ------------------------------ */
export default function Notch(props: Props) {
  const { vs, reduceMotion, lang } = props;
  const display = displayState(vs);
  const [hover, setHover] = useState(false);
  const [pinned, setPinned] = useState(false);
  const [menu, setMenu] = useState<{ x: number; y: number } | null>(null);
  const hoverT = useRef<ReturnType<typeof setTimeout> | undefined>(undefined);
  const shown: NotchState = display === "idle" && (hover || pinned) ? "hover" : display;

  const boxRef = useRef<HTMLDivElement>(null);
  const bodyRef = useRef<HTMLDivElement>(null);
  const svgRef = useRef<SVGSVGElement>(null);
  const fillRef = useRef<SVGPathElement>(null);
  const edgeRef = useRef<SVGPathElement>(null);
  const cur = useRef({ w: THEME.geo.idle.w, h: THEME.geo.idle.h, r: THEME.geo.idle.r, vw: 0, vh: 0, vr: 0 });
  const tgt = useRef<{ w: number; h: number; r: number }>({ ...THEME.geo.idle });
  const dirExpand = useRef(true);
  const raf = useRef(0);
  const lastTs = useRef(0);

  const apply = () => {
    const c = cur.current;
    const w = Math.max(40, c.w), h = Math.max(12, c.h);
    const d = pathFor(w, h, c.r);
    fillRef.current?.setAttribute("d", d);
    edgeRef.current?.setAttribute("d", d);
    const W = w + 2 * EAR;
    if (svgRef.current) { svgRef.current.setAttribute("width", String(W)); svgRef.current.setAttribute("height", String(h + 2)); }
    if (boxRef.current) { boxRef.current.style.width = `${W}px`; boxRef.current.style.height = `${h}px`; }
    if (bodyRef.current) {
      const r = Math.max(0, Math.min(c.r, h - EAR - 1, w / 2));
      bodyRef.current.style.width = `${w}px`;
      bodyRef.current.style.height = `${h}px`;
      bodyRef.current.style.borderRadius = `0 0 ${r}px ${r}px`;
    }
  };

  const loop = (ts: number) => {
    const c = cur.current, t = tgt.current;
    const dt = Math.min(0.05, lastTs.current ? (ts - lastTs.current) / 1000 : 1 / 60);
    if (lastTs.current) {
      const frames = (window.__voxFrames ??= []);
      frames.push((ts - lastTs.current));
      if (frames.length > 3000) frames.splice(0, frames.length - 3000);
    }
    lastTs.current = ts;
    const p = dirExpand.current ? THEME.spring.expand : THEME.spring.collapse;
    const sub = 4, h = dt / sub;
    let moving = false;
    for (const [k, vk] of [["w", "vw"], ["h", "vh"], ["r", "vr"]] as const) {
      let x = c[k], v = c[vk];
      for (let i = 0; i < sub; i++) {
        const a = -p.k * (x - t[k]) - p.c * v;
        v += a * h;
        x += v * h;
      }
      c[k] = x; c[vk] = v;
      if (Math.abs(x - t[k]) > 0.05 || Math.abs(v) > 0.05) moving = true;
    }
    if (!moving) { c.w = t.w; c.h = t.h; c.r = t.r; c.vw = c.vh = c.vr = 0; apply(); raf.current = 0; lastTs.current = 0; return; }
    apply();
    raf.current = requestAnimationFrame(loop);
  };

  useEffect(() => {
    const g = THEME.geo[shown];
    const t = { ...g };
    if (shown === "approval" && vs.approval && vs.approval.details.length > 3) t.h += 8;
    tgt.current = t;
    window.__voxTransitions = (window.__voxTransitions ?? 0) + 1;
    if (reduceMotion) {
      Object.assign(cur.current, { w: t.w, h: t.h, r: t.r, vw: 0, vh: 0, vr: 0 });
      apply();
      return;
    }
    // direction chosen at target change; interrupting mid-flight keeps position AND velocity (smooth reversal)
    dirExpand.current = t.w * t.h >= cur.current.w * cur.current.h;
    if (!raf.current) raf.current = requestAnimationFrame(loop);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [shown, reduceMotion, vs.approval?.id]);

  useEffect(() => { apply(); return () => cancelAnimationFrame(raf.current); // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  /* hover intent (120 ms) / leave delay (400 ms); click pins; Esc / outside click collapses */
  const enter = () => { clearTimeout(hoverT.current); hoverT.current = setTimeout(() => setHover(true), THEME.timing.hoverIntentMs); };
  const leave = () => { clearTimeout(hoverT.current); hoverT.current = setTimeout(() => setHover(false), THEME.timing.hoverLeaveMs); };
  useEffect(() => {
    const k = (e: KeyboardEvent) => { if (e.key === "Escape") { setPinned(false); setHover(false); setMenu(null); } };
    const c = (e: MouseEvent) => { if (!boxRef.current?.contains(e.target as Node)) { setPinned(false); setMenu(null); } };
    window.addEventListener("keydown", k);
    window.addEventListener("mousedown", c);
    return () => { window.removeEventListener("keydown", k); window.removeEventListener("mousedown", c); };
  }, []);

  const color = THEME.color[shown];
  const showBadge = vs.badge && shown !== "approval";
  return (
    <div className={`pointer-events-none fixed top-0 left-1/2 z-50 flex -translate-x-1/2 flex-col items-center ${reduceMotion ? "rm" : ""}`} data-notch-state={shown}>
      <div
        ref={boxRef}
        className="pointer-events-auto relative"
        onMouseEnter={enter}
        onMouseLeave={leave}
        onClick={() => display === "idle" && setPinned((p) => !p)}
        onContextMenu={(e) => { e.preventDefault(); setMenu({ x: e.clientX, y: e.clientY }); }}
        style={{ width: THEME.geo.idle.w + 2 * EAR, height: THEME.geo.idle.h }}
      >
        <svg ref={svgRef} className="notch-svg absolute top-0 left-0 overflow-visible" style={{ ["--c" as string]: color }} data-state={shown}>
          <path ref={fillRef} fill="#000" />
          <path ref={edgeRef} fill="none" pathLength={100} className={`edge edge-${shown}`} />
        </svg>
        <div ref={bodyRef} className="absolute top-0 overflow-hidden" style={{ left: EAR }}>
          <div key={shown} className={`h-full w-full ${reduceMotion ? "fade-only" : ""}`}>
            <Content {...props} shown={shown} />
          </div>
        </div>
        {showBadge && vs.badge && (
          <div className="enter absolute top-1 right-5 flex items-center gap-1 rounded-full px-2 py-0.5 text-[10px] font-medium"
            style={{ background: vs.badge.effective === "offline" ? "rgba(255,159,10,.18)" : vs.mode.requested === "auto" ? "rgba(140,160,190,.18)" : "rgba(77,163,255,.18)", color: vs.badge.effective === "offline" ? "#FFB84D" : "#9CC9FF" }}>
            <span className="morph">{vs.badge.effective === "offline" ? <Chip /> : <Cloud />}</span>
            {tr(lang, vs.badge.effective)}
          </div>
        )}
      </div>
      {display === "speaking" || (vs.speaking && vs.reply) ? (
        <div className="bubble pointer-events-none mt-3 max-w-md rounded-2xl bg-black/90 px-4 py-2 text-center text-sm text-teal-50 shadow-xl ring-1 ring-teal-200/20">{vs.reply}</div>
      ) : null}
      {menu && (
        <div style={{ position: "fixed", left: menu.x, top: menu.y }} className="pointer-events-auto w-56 rounded-xl bg-neutral-900 p-1 text-sm text-white shadow-2xl ring-1 ring-white/10">
          {[
            [tr(lang, "settings"), () => props.onTab("router")],
            [tr(lang, "audit"), () => props.onTab("audit")],
            [tr(lang, "pause"), props.onMute],
          ].map(([label, fn]) => (
            <button key={label as string} onMouseDown={(e) => e.stopPropagation()} onClick={() => { (fn as () => void)(); setMenu(null); }} className="block w-full rounded-lg px-3 py-1.5 text-left hover:bg-white/10">{label as string}</button>
          ))}
          <div className="px-3 py-1.5 text-white/35">{tr(lang, "quit")}</div>
        </div>
      )}
    </div>
  );
}
