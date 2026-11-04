import { createHash } from "node:crypto";
import { DESKTOP, DOCUMENTS, DOWNLOADS, LIMITS, USER_ROOT } from "./constants";

export type Tier = 0 | 1 | 2 | 3;
export const TIER_NAME = ["Safe", "Confirm", "Confirm-Hard", "Blocked"] as const;

/* ------------------------------------------------------------------ */
/* Path normalisation: no `..` tricks, no UNC / ADS / device paths.     */
/* ------------------------------------------------------------------ */

export class PathError extends Error {
  constructor(public code: string, message: string) {
    super(message);
  }
}

const DEVICE_NAMES = new Set([
  "CON", "PRN", "AUX", "NUL", "CONIN$", "CONOUT$",
  ...Array.from({ length: 9 }, (_, i) => `COM${i + 1}`),
  ...Array.from({ length: 9 }, (_, i) => `LPT${i + 1}`),
]);

const ALIASES: Record<string, string> = {
  desktop: DESKTOP,
  downloads: DOWNLOADS,
  documents: DOCUMENTS,
  home: USER_ROOT,
};

/** Expand a friendly alias ("Downloads", "desktop\\x") and normalise. Throws PathError on smuggling. */
export function normalizePath(input: string): string {
  let p = String(input ?? "").trim().replace(/^"+|"+$/g, "");
  if (!p) throw new PathError("EMPTY_PATH", "Empty path");
  if (p.includes("\0")) throw new PathError("NUL_BYTE", "Null byte in path");
  // percent / unicode tricks: decode once and reject if decoding changes separators
  if (/%2e|%2f|%5c/i.test(p)) throw new PathError("ENCODED_PATH", "Encoded path segments are not allowed");
  p = p.replace(/\//g, "\\");
  if (p.startsWith("\\\\")) throw new PathError("UNC_OR_DEVICE", "UNC / device paths are not allowed");
  const first = p.split("\\")[0].toLowerCase();
  if (ALIASES[first] && !/^[a-z]:/i.test(p)) p = ALIASES[first] + p.slice(first.length);
  if (!/^[a-z]:\\/i.test(p) && !/^[a-z]:$/i.test(p)) {
    // relative path: anchor to user root (never to cwd)
    p = `${USER_ROOT}\\${p}`;
  }
  // alternate data streams: any colon after the drive letter
  if (p.slice(2).includes(":")) throw new PathError("ADS", "Alternate data streams are not allowed");
  const drive = p.slice(0, 2).toUpperCase();
  const out: string[] = [];
  for (const raw of p.slice(3).split("\\")) {
    if (raw === "" || raw === ".") continue;
    if (raw === "..") {
      out.pop();
      continue;
    }
    // trailing dots/spaces are stripped by Win32: normalise like Win32 does
    const seg = raw.replace(/[. ]+$/, "");
    if (!seg) throw new PathError("BAD_SEGMENT", "Invalid path segment");
    if (/[<>"|?*%]/.test(seg)) throw new PathError("BAD_CHAR", "Invalid character in path");
    const base = seg.split(".")[0].toUpperCase();
    if (DEVICE_NAMES.has(base)) throw new PathError("DEVICE_NAME", "Device names are not allowed");
    // 8.3 short names (PROGRA~1) can alias protected dirs
    if (/~\d/.test(seg)) throw new PathError("SHORT_NAME", "8.3 short names are not allowed");
    out.push(seg);
  }
  return out.length ? `${drive}\\${out.join("\\")}` : `${drive}\\`;
}

/* ------------------------------------------------------------------ */
/* Protected policy (built-in T3 set is not removable; user may add)    */
/* ------------------------------------------------------------------ */

export const BUILTIN_PROTECTED: { path: string; reason: string }[] = [
  { path: "C:\\Windows", reason: "Windows directory" },
  { path: "C:\\Program Files", reason: "Program Files" },
  { path: "C:\\Program Files (x86)", reason: "Program Files (x86)" },
  { path: "C:\\ProgramData\\Microsoft", reason: "System data" },
  { path: `${USER_ROOT}\\.ssh`, reason: "SSH keys" },
  { path: `${USER_ROOT}\\AppData\\Local\\Google\\Chrome\\User Data`, reason: "Browser profile / saved passwords" },
  { path: `${USER_ROOT}\\AppData\\Local\\Microsoft\\Edge\\User Data`, reason: "Browser profile / saved passwords" },
  { path: `${USER_ROOT}\\AppData\\Roaming\\Mozilla`, reason: "Browser profile" },
  { path: `${USER_ROOT}\\AppData\\Roaming\\KeePass`, reason: "Password manager" },
  { path: `${USER_ROOT}\\AppData\\Local\\Bitwarden`, reason: "Password manager" },
  { path: `${USER_ROOT}\\AppData\\Local\\vox`, reason: "Vox config / audit directory" },
];

/** The user profile root itself is protected, but not its children (Desktop, Downloads...). */
const PROTECTED_EXACT = [USER_ROOT];

let userProtected: string[] = [];
export function setUserProtected(paths: string[]) {
  userProtected = paths.map((p) => normalizePath(p));
}
export function getUserProtected() {
  return userProtected;
}

const lc = (s: string) => s.toLowerCase();

export function isUnder(path: string, root: string): boolean {
  const a = lc(path);
  const b = lc(root).replace(/\\$/, "");
  return a === b || a.startsWith(b + "\\");
}

export function protectedReason(normalized: string): string | null {
  for (const e of BUILTIN_PROTECTED) if (isUnder(normalized, e.path)) return e.reason;
  for (const e of PROTECTED_EXACT) if (lc(normalized) === lc(e)) return "User profile root";
  for (const e of userProtected) if (isUnder(normalized, e)) return "User-protected path";
  return null;
}

/* ------------------------------------------------------------------ */
/* Argument hashing (approvals are bound to tool + validated args)      */
/* ------------------------------------------------------------------ */

function canonical(v: unknown): string {
  if (Array.isArray(v)) return `[${v.map(canonical).join(",")}]`;
  if (v && typeof v === "object") {
    const o = v as Record<string, unknown>;
    return `{${Object.keys(o).sort().map((k) => `${JSON.stringify(k)}:${canonical(o[k])}`).join(",")}}`;
  }
  return JSON.stringify(v);
}
export function hashCall(tool: string, args: unknown): string {
  return createHash("sha256").update(`${tool}\n${canonical(args)}`).digest("hex");
}

/* ------------------------------------------------------------------ */
/* Tier escalation (never lowers)                                       */
/* ------------------------------------------------------------------ */

export type Classification = {
  tier: Tier;
  reasons: string[];
  blockedBy?: string;
  count?: number;
};

export type PolicyInput = {
  tool: string;
  baseTier: Tier;
  /** names of args that hold filesystem paths (already validated by schema) */
  pathArgs: { arg: string; value: string; mode: "read" | "write" | "delete" }[];
  /** number of objects affected (from tool preview) */
  count?: number;
  /** tool-specific escalation computed by the tool itself */
  extraTier?: { tier: Tier; reason: string };
};

const SENSITIVE_READ_NAMES = /(\\|^)(login data|cookies|web data|key[34]?\.db|logins\.json|id_rsa|id_ed25519|\.kdbx|credentials?|ntuser\.dat|sam|security)$/i;

export function classify(input: PolicyInput): Classification {
  let tier: Tier = input.baseTier;
  const reasons: string[] = [];
  const esc = (t: Tier, why: string) => {
    if (t > tier) tier = t;
    reasons.push(why);
  };
  if (input.extraTier) esc(input.extraTier.tier, input.extraTier.reason);
  let blockedBy: string | undefined;
  for (const pa of input.pathArgs) {
    let n: string;
    try {
      n = normalizePath(pa.value);
    } catch (e) {
      esc(3, `Rejected path (${(e as PathError).code})`);
      blockedBy = (e as PathError).code;
      continue;
    }
    const pr = protectedReason(n);
    if (pr) {
      esc(3, `Protected path: ${pr}`);
      blockedBy = pr;
    }
    if (pa.mode !== "read") {
      // deleting/moving/writing an ANCESTOR of a protected path is as bad as touching it
      const anc = [...BUILTIN_PROTECTED.map((e) => e.path), ...PROTECTED_EXACT, ...userProtected].find((e) => isUnder(e, n));
      if (anc) {
        esc(3, "Contains a protected path");
        blockedBy = "Contains a protected path";
      }
    }
    if (SENSITIVE_READ_NAMES.test(n)) {
      esc(3, "Credential store");
      blockedBy = "Credential store";
    }
  }
  if (input.count !== undefined && input.count >= LIMITS.bulkT2Threshold) {
    esc(2, `Bulk operation (${input.count} items)`);
  }
  return { tier, reasons, blockedBy, count: input.count };
}
