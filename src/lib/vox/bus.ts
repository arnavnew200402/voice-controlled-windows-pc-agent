import { persistEvent } from "./audit";
import { EVENT_VERSION, type Envelope, type VoxEvent } from "./events";

/** Wraps events in versioned envelopes, persists them to the event ledger and hands them to `push`. */
export function envelopeEmitter(turnId: string, push: (env: Envelope) => void) {
  let seq = 0;
  return (event: VoxEvent) => {
    const env: Envelope = { v: EVENT_VERSION, seq: ++seq, ts: Date.now(), turnId, event };
    push(env);
    persistEvent(env).catch(() => {});
  };
}
