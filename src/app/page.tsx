"use client";
import { useCallback, useEffect, useState } from "react";
import Notch from "@/components/Notch";
import { AboutPanel, AuditPanel, Btn, Card, EventsPanel, PcPanel, PerfPanel, RouterPanel, SafetyLab, ToolsPanel, type ServerState } from "@/components/panels";
import { useVox } from "@/lib/client/useVox";
import { APP_NAME, WAKE_PHRASE } from "@/lib/vox/constants";

const COMMANDS: { label: string; text: string; scenario?: { cutNetworkAfter: number } }[] = [
  { label: "Open Notepad and type hello", text: "Open Notepad and type hello" },
  { label: "Move this window to the right monitor", text: "Move this window to the right monitor" },
  { label: "Set volume to 30", text: "Set volume to 30" },
  { label: "What's on my screen?", text: "What's on my screen?" },
  { label: "Search the web… and open the first result", text: "Search the web for local LLM tool calling and open the first result" },
  { label: "Create a folder on the desktop + a file", text: "Create a folder called Test on my desktop and put a text file in it" },
  { label: "Delete everything in Downloads (T1 approval)", text: "Delete everything in Downloads" },
  { label: "Shut down the computer (T2: click only)", text: "Shut down the computer" },
  { label: "Format the C drive (T3 blocked)", text: "Format the C drive" },
  { label: "Read the hostile web page (injection)", text: "Read page https://evil.example.test/free-stuff" },
  { label: "नोटपैड खोलो (Hindi)", text: "नोटपैड खोलो" },
  { label: "Failover: cut network mid-task", text: "Open Notepad and type hello", scenario: { cutNetworkAfter: 1 } },
  { label: "Task status", text: "task status" },
  { label: "Stop", text: "stop" },
];

const TABS = [["pc", "Virtual PC"], ["events", "Events"], ["audit", "Audit"], ["safety", "Safety lab"], ["tools", "Tools"], ["router", "Router"], ["perf", "Perf"], ["about", "Status"]] as const;

export default function Home() {
  const v = useVox();
  const { vs } = v;
  const [tab, setTab] = useState<string>("pc");
  const [st, setSt] = useState<ServerState | null>(null);
  const [text, setText] = useState("");
  const [reduce, setReduce] = useState(false);
  const [ptt, setPtt] = useState(false);

  const refresh = useCallback(() => fetch("/api/state", { cache: "no-store" }).then((r) => r.json()).then(setSt).catch(() => {}), []);
  useEffect(() => { void refresh(); const id = setInterval(refresh, 3000); return () => clearInterval(id); }, [refresh, v.tick]);
  useEffect(() => { setReduce(window.matchMedia("(prefers-reduced-motion: reduce)").matches); }, []);

  const mode = st?.router.requested ?? vs.mode.requested;
  const micBtn = ptt
    ? { onMouseDown: () => void v.startListening(), onMouseUp: () => v.stopListening() }
    : { onClick: () => (vs.listening ? v.stopListening() : void v.startListening()) };

  return (
    <main className="min-h-screen bg-[radial-gradient(ellipse_at_top,#14182200,#07080b_60%)] pt-24 pb-16 text-white">
      <Notch
        vs={vs} lang={v.lang} levelRef={v.levelRef} muted={v.muted} ptt={ptt} reduceMotion={reduce}
        onResolve={v.resolve} onMode={v.setMode} onSend={(t) => void v.send(t)} onMute={() => v.setMuted((m) => !m)}
        onPtt={() => setPtt((p) => !p)} onTab={setTab}
      />
      <div className="mx-auto max-w-7xl px-5">
        <header className="mb-6 flex flex-wrap items-end justify-between gap-3">
          <div>
            <h1 className="text-2xl font-semibold tracking-tight">{APP_NAME} <span className="text-white/35">control center</span></h1>
            <p className="mt-1 max-w-2xl text-sm text-white/50">A voice-first PC agent with a virtual notch. This build runs against a sandboxed virtual PC; the tier-based safety model, bound approvals, provider failover and offline guard are real code under test.</p>
          </div>
          <div className="flex flex-wrap items-center gap-2 text-xs text-white/50">
            <label className="flex items-center gap-1.5"><input type="checkbox" checked={reduce} onChange={(e) => setReduce(e.target.checked)} /> Reduce motion</label>
            <select value={v.lang} onChange={(e) => v.setLang(e.target.value as "en" | "hi")} className="rounded-full bg-white/10 px-2 py-1 text-white"><option value="en">English</option><option value="hi">हिन्दी</option></select>
          </div>
        </header>

        <div className="grid gap-5 lg:grid-cols-[360px_1fr]">
          <div className="space-y-4">
            <Card title="Talk to Vox">
              <form className="flex gap-2" onSubmit={(e) => { e.preventDefault(); if (text.trim()) { void v.send(text); setText(""); } }}>
                <input value={text} onChange={(e) => setText(e.target.value)} placeholder={`Say “${WAKE_PHRASE}…” or type`} className="min-w-0 flex-1 rounded-full bg-white/10 px-4 py-2 text-sm outline-none placeholder:text-white/30 focus:bg-white/15" />
                <button type="submit" disabled={vs.busy} className="rounded-full bg-white px-4 text-sm font-medium text-black disabled:opacity-40">Send</button>
              </form>
              <div className="mt-2 flex flex-wrap items-center gap-2">
                <button {...micBtn} disabled={v.muted} className={`rounded-full px-3 py-1 text-xs font-medium ${vs.listening ? "bg-sky-400 text-black" : "bg-white/10 hover:bg-white/20"} disabled:opacity-40`}>🎙 {ptt ? "Hold to talk" : vs.listening ? "Stop listening" : "Listen (Alt+V)"}</button>
                <Btn onClick={() => v.setMuted((m) => !m)}>{v.muted ? "Unmute mic" : "Mute mic"}</Btn>
                <Btn tone="warn" onClick={() => void v.stop()}>Stop (Ctrl+Shift+Q)</Btn>
              </div>
              <p className="mt-2 text-[11px] leading-4 text-white/35">Mic uses the browser’s SpeechRecognition (Chrome/Edge). While an approval is open you can say “yes/no” for T1; T2 needs a click or Ctrl+Shift+Y.</p>
            </Card>

            <Card title="Demo script (spec 15.7)">
              <div className="flex flex-col gap-1.5">
                {COMMANDS.map((c) => (
                  <button key={c.label} onClick={() => void v.send(c.text, c.scenario)} className="rounded-xl bg-white/5 px-3 py-1.5 text-left text-xs text-white/80 transition hover:bg-white/10">{c.label}</button>
                ))}
              </div>
              <div className="mt-3 flex flex-wrap gap-2">
                <Btn tone="primary" onClick={() => void v.runDemo()}>Run UI demo (all states)</Btn>
                <Btn onClick={async () => { await fetch("/api/reset", { method: "POST" }); void refresh(); }}>Reset sandbox</Btn>
              </div>
            </Card>

            {vs.reply && (
              <Card title="Last reply">
                <p className="text-sm text-white/85">{vs.reply}</p>
                <p className="mt-1 text-[11px] text-white/35">“{vs.lastCommand}”</p>
              </Card>
            )}
          </div>

          <div>
            <nav className="mb-4 flex flex-wrap gap-1.5">
              {TABS.map(([k, label]) => (
                <button key={k} onClick={() => setTab(k)} className={`rounded-full px-3.5 py-1.5 text-xs font-medium transition ${tab === k ? "bg-white text-black" : "bg-white/5 text-white/70 hover:bg-white/10"}`}>{label}</button>
              ))}
            </nav>
            {tab === "pc" && <PcPanel st={st} />}
            {tab === "events" && <EventsPanel events={vs.events} />}
            {tab === "audit" && <AuditPanel tick={v.tick} />}
            {tab === "safety" && <SafetyLab />}
            {tab === "tools" && <ToolsPanel />}
            {tab === "router" && <RouterPanel st={st} mode={mode} onMode={v.setMode} onNet={v.setNetwork} onProbe={() => { fetch("/api/mode", { method: "POST", headers: { "content-type": "application/json" }, body: "{}" }).then(refresh); }} />}
            {tab === "perf" && <PerfPanel />}
            {tab === "about" && <AboutPanel />}
          </div>
        </div>
      </div>
    </main>
  );
}
