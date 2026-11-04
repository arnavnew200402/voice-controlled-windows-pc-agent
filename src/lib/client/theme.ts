/** Single source of design tokens for the notch (spec 11.4). Tune here only. */
export type NotchState =
  | "idle" | "wake" | "listening" | "thinking" | "acting" | "approval" | "speaking" | "error" | "echo" | "hover";

export const THEME = {
  ear: 9, // concave "ear" radius where the notch fuses with the top edge
  geo: {
    idle: { w: 200, h: 32, r: 14 },
    wake: { w: 360, h: 64, r: 24 },
    listening: { w: 420, h: 112, r: 30 },
    thinking: { w: 420, h: 88, r: 28 },
    acting: { w: 460, h: 120, r: 30 },
    approval: { w: 480, h: 176, r: 32 },
    speaking: { w: 460, h: 140, r: 30 },
    error: { w: 400, h: 72, r: 26 },
    echo: { w: 300, h: 64, r: 24 },
    hover: { w: 520, h: 232, r: 34 },
  } satisfies Record<NotchState, { w: number; h: number; r: number }>,
  color: {
    idle: "#ffffff",
    wake: "#8AB4FF",
    listening: "#4DA3FF",
    thinking: "#8B7CFF",
    acting: "#34D399",
    approval: "#FF9F0A",
    speaking: "#7DF9E6",
    error: "#FF453A",
    echo: "#7DF9E6",
    hover: "#9aa4b2",
  } satisfies Record<NotchState, string>,
  /** Springs. expand: zeta ~0.69 -> ~5% overshoot, ~300 ms settle. collapse: critically damped, ~220 ms. */
  spring: {
    expand: { k: 380, c: 27 },
    collapse: { k: 330, c: 36.3 },
  },
  timing: { hoverIntentMs: 120, hoverLeaveMs: 400, echoMs: 1200, errorMs: 4000, badgeMs: 1500, wakeMs: 450 },
};

export type Lang = "en" | "hi";
const STR = {
  en: {
    listening: "Listening…", thinking: "Thinking…", step: "Step {n} of {m}", yes: "Yes", no: "No",
    confirm: "Press to confirm", deny: "Deny", voiceNo: "Voice can't approve this. Click to confirm.",
    wake: "Hey Vox", offline: "Offline", online: "Online", auto: "Auto", mute: "Mic mute", ptt: "Push to talk",
    settings: "Settings", audit: "Audit log", pause: "Pause listening", quit: "Quit (disabled in simulator)",
    placeholder: "Type a command…", last: "Last command", actions: "Recent actions", sayYes: "Say “yes” or “no”",
    fromContent: "This came from page/file content.", mode: "Mode", none: "Nothing yet",
  },
  hi: {
    listening: "सुन रहा हूँ…", thinking: "सोच रहा हूँ…", step: "चरण {n} / {m}", yes: "हाँ", no: "नहीं",
    confirm: "पुष्टि के लिए दबाएँ", deny: "मना करें", voiceNo: "यह आवाज़ से स्वीकृत नहीं हो सकता। क्लिक करें।",
    wake: "हे वॉक्स", offline: "ऑफ़लाइन", online: "ऑनलाइन", auto: "ऑटो", mute: "माइक म्यूट", ptt: "बोलने के लिए दबाएँ",
    settings: "सेटिंग्स", audit: "ऑडिट लॉग", pause: "सुनना रोकें", quit: "बंद करें (सिम्युलेटर में बंद)",
    placeholder: "कमांड लिखें…", last: "पिछला कमांड", actions: "हाल की क्रियाएँ", sayYes: "“हाँ” या “नहीं” कहें",
    fromContent: "यह पेज/फ़ाइल की सामग्री से आया है।", mode: "मोड", none: "अभी कुछ नहीं",
  },
} as const;
export type StrKey = keyof (typeof STR)["en"];
export const tr = (lang: Lang, key: StrKey, vars?: Record<string, string | number>) => {
  let s: string = STR[lang][key] ?? STR.en[key];
  for (const [k, v] of Object.entries(vars ?? {})) s = s.replace(`{${k}}`, String(v));
  return s;
};
