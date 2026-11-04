# Decisions (date · question · choice · reason · how to reverse)

- 2026-05 · Can the Windows/PySide6 agent be built here? · **No.** Build the verifiable parts as a Next.js + Postgres app (notch UI, safety/approval/router/engine reference implementation, red-team suite) and document the port. · Sandbox is Linux; Win32/UIA/Core Audio/Qt cannot run or be tested; claiming otherwise would be dishonest. · Reverse: start the Python package from `ARCHITECTURE.md` mapping.
- · Spine repo? · Wyzer (typed registry, bound approvals, evidence-based task engine). Port from Aemyos only provider adapters/Edge TTS/signing/test cases. · Audit. · Reverse: n/a.
- · Port Aemyos regex destructive guards? · **No**; replaced by tool-assigned tiers + argument-level escalation. · Regexes are bypassable (see AUDIT). · Reverse: add as an extra escalator in `policy.classify`.
- · LLM in tests/demo? · Deterministic scripted fake provider, clearly labelled; Claude and Ollama adapters written but enabled only with `ANTHROPIC_API_KEY` / `OLLAMA_MODEL`. · No keys/Ollama in sandbox; spec says use a fake provider. The fake is *not* product routing logic. · Reverse: set env keys.
- · Offline guard depth? · Application-level (`netGate`), counters tested. · Socket-level patching of the Node runtime is risky and untestable against a real firewall here. · Reverse: patch `net.Socket.connect` + `dns.lookup` in `netguard.ts`.
- · Path chars `%` rejected · conservative: env-var style segments are never expanded by tools, but rejecting removes a class of confusion. · Reverse: remove `%` from the BAD_CHAR regex in `policy.ts`.
- · Reading anything under protected paths is T3 (not only writes) · conservative; read of SSH keys / browser DBs must be blocked, and splitting read/write per path adds bypass surface. · Reverse: relax per-mode in `classify`.
- · Taint tracking is turn-wide: once any untrusted tool output enters context, every later T≥1 approval card carries "This came from page/file content." and `remember` is refused. · Over-warns, never under-warns. · Reverse: track taint per argument.
- · T2 "physical confirm" in a browser = a trusted click or Ctrl+Shift+Y; the server cannot truly verify physicality. Documented as a gap; Windows build should use a low-level input hook / secure attention. 
- · Voice-injection defence in the browser = half-duplex gate + server rejection of `voice` approvals flagged `loopbackOverlap`. Real WASAPI-loopback correlation not built.
- · Wake word in browser · not available; Alt+V toggles listening, "Hey Vox" is label only. 
