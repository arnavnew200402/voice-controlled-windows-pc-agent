# MODEL BENCH — model/routing measurements

Only measured numbers; unmeasured items say so (spec §0.3).

## LE2 — contextualiser A/B (2026-11-05, `scripts/context_bench.py`)

Arms: **code-only** vs **code + oracle LLM fallback** (the "LLM" is
scripted to return perfect JSON — this measures *routing and coverage*,
not any real model's accuracy; no small model or API key exists in this
sandbox). 10 cases (references, redo, correction, Hinglish, ambiguity,
one deliberately unresolvable "close it" with an empty registry).

| Arm | Accuracy | Notes |
|---|---|---|
| Code path only | 9/10 | p50 0.116 ms, p95 0.166 ms per contextualise (budget ≤20 ms) |
| Auto (+ oracle fallback) | 10/10 | oracle invoked exactly once — for the unresolvable case |

**L-01 verdict so far:** keep the rewrite step, code-first with LLM only
on unresolved references/low confidence. The fused variant and a real
small-model arm (Groq fast tier / local) are **not measured** — they land
with the LE4 pipeline, where prompt-cache hit rate and TTFT are also due.

## WER with/without glossary (LE2, synthetic ASR-error corpus)

14 intended/heard pairs built from known small-model failure modes
("no pad", "vs code", "crow"): mean word error rate **0.562 → 0.000**
after glossary repair. This validates the repair table against its own
failure catalogue — it is *not* field WER. Field WER ±hotwords (EN/HI/
Hinglish) needs recorded speech through real STT: not measured (no key/
mic in sandbox), scheduled with the voice harness.

## LE3 — retrieval (2026-11-05, `scripts/memory_bench.py`)

BM25 + phonetic over an inverted index (sandbox timings, adversarial
synthetic corpus where most chunks share query tokens): p95 **0.96 ms**
@254 chunks, **3.1 ms** @1,254, **21.6 ms** @6,254 — inside the ≤100 ms
retrieval budget with headroom. Session checkpoint (500 events + 100
actions) ≈62 ms, restore ≈2.6 ms. Vector retrieval not implemented
(no licence-verified local embedding model in this environment).
