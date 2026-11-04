/** The product name lives in exactly one place. Rename here. */
export const APP_NAME = "Vox";
export const APP_CODENAME = "vox";
export const WAKE_PHRASE = "Hey Vox";

export const USER_ROOT = "C:\\Users\\vox";
export const DESKTOP = `${USER_ROOT}\\Desktop`;
export const DOWNLOADS = `${USER_ROOT}\\Downloads`;
export const DOCUMENTS = `${USER_ROOT}\\Documents`;

export const LIMITS = {
  maxToolCallsPerTask: 12,
  maxWallMs: 90_000,
  toolTimeoutMs: 8_000,
  approvalT1Ms: 15_000,
  approvalT2Ms: 30_000,
  bulkT2Threshold: 100,
  /** consecutive failures before cloud is considered down */
  failuresToOffline: 2,
  /** healthy probes required before returning online */
  healthyToOnline: 3,
  /** ...spread over at least this long */
  recoveryWindowMs: Number(process.env.VOX_RECOVERY_MS ?? 30_000),
} as const;
