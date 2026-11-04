/**
 * Offline guard (app-level reference implementation of spec section 5).
 * Every outbound call the agent itself makes (model / speech traffic) goes through
 * `guardedFetch`. In offline mode non-loopback destinations are blocked and counted.
 * The Windows build installs the same policy at socket level; here it is application level.
 */
type G = {
  offlineEnforced: boolean;
  networkUp: boolean; // simulated physical connectivity
  attempts: { t: number; host: string; blocked: boolean }[];
};
const g = globalThis as typeof globalThis & { __voxNet?: G };
const state: G = (g.__voxNet ??= { offlineEnforced: false, networkUp: true, attempts: [] });

export class NetworkBlocked extends Error {
  code = "OFFLINE_GUARD";
}
export class NetworkDown extends Error {
  code = "ENETUNREACH";
}

export const isLoopback = (host: string) =>
  /^(localhost|127\.\d+\.\d+\.\d+|\[?::1\]?)$/i.test(host);

export function setOfflineEnforced(v: boolean) {
  state.offlineEnforced = v;
}
export function setNetworkUp(v: boolean) {
  state.networkUp = v;
}
export function netStatus() {
  const nonLoop = state.attempts.filter((a) => !isLoopback(a.host));
  return {
    offlineEnforced: state.offlineEnforced,
    networkUp: state.networkUp,
    attempts: state.attempts.length,
    blocked: state.attempts.filter((a) => a.blocked).length,
    outboundNonLoopback: nonLoop.filter((a) => !a.blocked).length,
  };
}
export function resetNetCounters() {
  state.attempts = [];
}

/** Gate for a (real or simulated) outbound connection. Throws if not allowed. */
export function netGate(host: string) {
  const loop = isLoopback(host);
  if (state.offlineEnforced && !loop) {
    state.attempts.push({ t: Date.now(), host, blocked: true });
    throw new NetworkBlocked(`Offline guard blocked connection to ${host}`);
  }
  state.attempts.push({ t: Date.now(), host, blocked: false });
  if (!loop && !state.networkUp) throw new NetworkDown(`Network unreachable (${host})`);
}

export async function guardedFetch(url: string, init?: RequestInit): Promise<Response> {
  const host = new URL(url).hostname;
  netGate(host);
  return fetch(url, init);
}
