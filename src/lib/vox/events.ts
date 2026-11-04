/** Versioned event bus models (mirrors spec 3.2). The UI is a pure function of these. */
export const EVENT_VERSION = 1;

export type CoreState =
  | "IDLE"
  | "WAKE"
  | "LISTENING"
  | "THINKING"
  | "ACTING"
  | "APPROVAL"
  | "SPEAKING"
  | "ERROR";

export type Mode = "offline" | "auto" | "online";

export type VoxEvent =
  | { type: "StateChanged"; state: CoreState; reason: string }
  | { type: "AudioLevel"; rms: number; peak: number; t: number }
  | { type: "Transcript"; text: string; partial: boolean; lang: string }
  | { type: "Intent"; summary: string }
  | { type: "ToolStarted"; id: string; name: string; title: string; step: number; of: number }
  | { type: "ToolFinished"; id: string; ok: boolean; evidence: string }
  | {
      type: "ApprovalRequested";
      id: string;
      tier: 1 | 2;
      title: string;
      details: string[];
      untrustedDerived: boolean;
      expiresAt: number;
    }
  | { type: "ApprovalResolved"; id: string; decision: "approved" | "denied" | "expired"; via: string }
  | { type: "Reply"; text: string; spoken: boolean }
  | { type: "TtsLevel"; rms: number }
  | { type: "ModeChanged"; requested: Mode; effective: "offline" | "online"; reason: string }
  | { type: "PrivacyIndicator"; micOpen: boolean; screenCapturing: boolean; cloudActive: boolean }
  | { type: "Error"; code: string; message: string; recoverable: boolean }
  | { type: "EchoHud"; kind: string; value: number; label: string };

export type Envelope = { v: number; seq: number; ts: number; turnId: string | null; event: VoxEvent };
