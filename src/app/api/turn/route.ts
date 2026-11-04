import { randomUUID } from "node:crypto";
import { envelopeEmitter } from "@/lib/vox/bus";
import { runTurn } from "@/lib/vox/engine";

export const dynamic = "force-dynamic";

/** Streams the event bus for one turn as NDJSON. */
export async function POST(req: Request) {
  const body = (await req.json().catch(() => ({}))) as { text?: string; lang?: string; scenario?: { cutNetworkAfter?: number } };
  const text = String(body.text ?? "").trim().slice(0, 500);
  if (!text) return Response.json({ error: "text required" }, { status: 400 });
  const turnId = randomUUID();
  const enc = new TextEncoder();
  const stream = new ReadableStream({
    async start(controller) {
      const emit = envelopeEmitter(turnId, (env) => {
        try {
          controller.enqueue(enc.encode(JSON.stringify(env) + "\n"));
        } catch { /* client went away; the turn still finishes and is audited */ }
      });
      try {
        await runTurn({ text, turnId, lang: body.lang, emit, cutNetworkAfter: body.scenario?.cutNetworkAfter });
      } catch (e) {
        emit({ type: "Error", code: "INTERNAL", message: (e as Error).message, recoverable: true });
      }
      try { controller.close(); } catch { /* already closed */ }
    },
  });
  return new Response(stream, { headers: { "content-type": "application/x-ndjson", "cache-control": "no-store" } });
}
