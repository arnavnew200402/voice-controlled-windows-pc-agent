// UI harness: drives the running app with headless Chromium, captures every notch state
// into artifacts/ui/ and records rAF frame times during spring animations.
// Usage: PW=/path/to/node_modules/playwright/index.mjs VOX_URL=http://localhost:3000 node scripts/ui-capture.mjs
import fs from "node:fs";

const { chromium } = await import(process.env.PW ?? "playwright");
const OUT = new URL("../artifacts/ui/", import.meta.url).pathname;
fs.mkdirSync(OUT, { recursive: true });
const URL_ = process.env.VOX_URL ?? "http://localhost:3000";
const browser = await chromium.launch();
const page = await browser.newPage({ viewport: { width: 1440, height: 900 }, deviceScaleFactor: 2 });
const errors = [];
page.on("pageerror", (e) => errors.push(String(e)));
page.on("console", (m) => m.type() === "error" && errors.push(m.text()));
await page.goto(URL_, { waitUntil: "networkidle" });
const clip = { x: 420, y: 0, width: 600, height: 320 };
const state = () => page.evaluate(() => document.querySelector("[data-notch-state]")?.getAttribute("data-notch-state"));
const shot = async (name, full = false) => page.screenshot({ path: `${OUT}${name}.png`, ...(full ? {} : { clip }) });
const seen = new Set();

async function capture(ms, settle = 520) {
  const t0 = Date.now();
  while (Date.now() - t0 < ms) {
    const s = await state();
    if (s && !seen.has(s)) {
      seen.add(s);
      await page.waitForTimeout(settle);
      await shot(`state-${s}`);
    }
    await page.waitForTimeout(80);
  }
}
async function waitState(s, tries = 80) {
  for (let i = 0; i < tries && (await state()) !== s; i++) await page.waitForTimeout(80);
}

await page.waitForTimeout(600);
await shot("state-idle");
seen.add("idle");
await page.mouse.move(720, 14);
await page.waitForTimeout(900);
await shot("state-hover");
seen.add("hover");
await page.mouse.move(100, 600);
await page.waitForTimeout(900);

// 1) synthetic demo through every state
await page.getByRole("button", { name: /Run UI demo/ }).click();
await capture(26000);

// 2) real flows against the backend
await page.getByRole("button", { name: /Delete everything in Downloads/ }).click();
await waitState("approval");
await page.waitForTimeout(600);
await shot("flow-approval-T1-delete-downloads");
await page.getByRole("button", { name: "No", exact: true }).click().catch(() => {});
await page.waitForTimeout(2500);

await page.getByRole("button", { name: /Shut down the computer/ }).click();
await waitState("approval");
await page.waitForTimeout(600);
await shot("flow-approval-T2-shutdown");
await page.getByRole("button", { name: "Deny", exact: true }).click().catch(() => {});
await page.waitForTimeout(2500);

await page.getByRole("button", { name: /Set volume to 30/ }).click();
await waitState("echo");
await page.waitForTimeout(450);
await shot("flow-echo-volume");
await page.waitForTimeout(2500);

await page.getByRole("button", { name: /Format the C drive/ }).click();
await waitState("error");
await page.waitForTimeout(450);
await shot("flow-error-blocked-T3");
await page.waitForTimeout(4500);

await page.getByRole("button", { name: /Failover: cut network/ }).click();
await page.waitForTimeout(4500);
await shot("flow-failover-badge");
await page.getByRole("button", { name: "Reset sandbox" }).click();

// 3) dashboard tabs
await page.waitForTimeout(800);
await shot("tab-pc", true);
await page.getByRole("button", { name: "Safety lab" }).click();
await page.getByRole("button", { name: "Run suite" }).click();
await page.waitForSelector("text=/\\d+\\/\\d+ passed/", { timeout: 90000 });
await page.waitForTimeout(300);
await shot("tab-safety-redteam", true);
await page.getByRole("button", { name: "Router", exact: true }).click();
await page.waitForTimeout(500);
await shot("tab-router", true);

const stats = await page.evaluate(() => {
  const f = [...(window.__voxFrames ?? [])].sort((a, b) => a - b);
  const q = (x) => f[Math.min(f.length - 1, Math.floor(f.length * x))];
  return { frames: f.length, p50: q(0.5), p95: q(0.95), p99: q(0.99), max: f[f.length - 1], over50: f.filter((x) => x > 50).length, transitions: window.__voxTransitions };
});
const report = { ...stats, note: "headless Chromium, software rendering; rAF deltas recorded during spring animations only", states: [...seen], errors };
fs.writeFileSync(`${OUT}frametimes.json`, JSON.stringify(report, null, 2));
console.log(JSON.stringify(report, null, 1));
await browser.close();
