#!/usr/bin/env node
// Retake the README screenshots from a running kivi-ui with headless Chrome over the DevTools Protocol.
//
//   node scripts/screenshots.mjs                    # every shot, English and Chinese
//   node scripts/screenshots.mjs overview,alerts    # only these
//
// Needs Node 22 or later and Google Chrome or Chromium. Start the API and the web app with the demo
// data loaded (uv run kivi-ui seed-demo); the script signs in as the demo admin with
// KIVI_DEMO_PASSWORD, taken from the environment or from backend/.env.
//
// Settings, all optional:
//   KIVI_WEB       web app               http://localhost:3000
//   KIVI_API       API base              http://127.0.0.1:8000/api/v1
//   CHROME         Chrome binary         google-chrome
//   SHOTS_OUT      output folder         docs/assets/screenshots
//   SHOTS_PROFILE  Chrome profile folder a fresh temporary one, removed afterwards
//   SHOTS_PORT     DevTools port         9333
import { spawn } from "node:child_process";
import { existsSync, mkdirSync, mkdtempSync, readFileSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { dirname, join, relative } from "node:path";
import { fileURLToPath } from "node:url";

const ROOT = join(dirname(fileURLToPath(import.meta.url)), "..");
const WEB = process.env.KIVI_WEB ?? "http://localhost:3000";
const API = process.env.KIVI_API ?? "http://127.0.0.1:8000/api/v1";
const OUT = process.env.SHOTS_OUT ?? join(ROOT, "docs/assets/screenshots");
const PORT = Number(process.env.SHOTS_PORT ?? 9333);
const WIDTH = 1440;
const ONLY = process.argv[2]?.split(",").filter(Boolean);

// Demo objects, found by the codes seed-demo gives them.
const STRATEGY_CODE = "RETAIL_APPLY";
const MODEL_CODE = "RETAIL_APP";
const INDICATOR_CODE = "inquiries_6m";
const MONITOR_KIND = "indicator_psi";

const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

function demoPassword() {
  if (process.env.KIVI_DEMO_PASSWORD) return process.env.KIVI_DEMO_PASSWORD;
  const file = join(ROOT, "backend/.env");
  const value = existsSync(file) && readFileSync(file, "utf8").match(/^KIVI_DEMO_PASSWORD=(.*)$/m)?.[1]?.trim();
  if (!value) throw new Error("Set KIVI_DEMO_PASSWORD, in the environment or in backend/.env");
  return value;
}

async function signIn() {
  const res = await fetch(`${API}/auth/login`, {
    method: "POST",
    headers: { "Content-Type": "application/json", "X-Requested-With": "XMLHttpRequest" },
    body: JSON.stringify({ username: "admin", password: demoPassword() }),
  }).catch(() => null);
  if (!res) throw new Error(`The API is not reachable at ${API}`);
  if (!res.ok) throw new Error(`Signing in as the demo admin failed (${res.status})`);
  const cookie = res.headers.getSetCookie().find((c) => c.startsWith("kivi_session="));
  return cookie.split(";")[0].slice("kivi_session=".length);
}

async function demoPaths(session) {
  const get = async (path) => {
    const res = await fetch(API + path, { headers: { Cookie: `kivi_session=${session}` } });
    if (!res.ok) throw new Error(`GET ${path} failed (${res.status})`);
    return res.json();
  };
  const need = (item, what) => {
    if (!item) throw new Error(`Demo ${what} not found; load the demo with: uv run kivi-ui seed-demo`);
    return item;
  };
  const newest = (versions) => versions.toSorted((a, b) => b.version - a.version)[0];

  const strategy = need((await get("/strategies")).find((s) => s.code === STRATEGY_CODE), `strategy ${STRATEGY_CODE}`);
  // The newest version is the demo's draft, which carries a backtest against the online one.
  const strategyVersion = need(newest((await get(`/strategies/${strategy.id}`)).versions), "strategy version");
  const model = need((await get("/models")).find((m) => m.code === MODEL_CODE), `model ${MODEL_CODE}`);
  const { versions: modelVersions } = await get(`/models/${model.id}`);
  const modelVersion = need(modelVersions.find((v) => v.status === "online") ?? newest(modelVersions), "model version");
  const { items } = await get(`/indicators?q=${INDICATOR_CODE}`);
  const indicator = need(items.find((i) => i.code === INDICATOR_CODE), `indicator ${INDICATOR_CODE}`);
  const monitor = need((await get("/monitors")).find((m) => m.kind === MONITOR_KIND), `${MONITOR_KIND} monitor`);
  return {
    strategy: `/strategies/${strategy.id}/v/${strategyVersion.id}`,
    model: `/models/${model.id}/v/${modelVersion.id}`,
    indicator: `/indicators/${indicator.id}`,
    monitor: `/monitors/${monitor.id}`,
  };
}

// Page snippets. React Aria handles virtual clicks through usePress, so element.click() works.
const clickText = (selector, text) =>
  `[...document.querySelectorAll(${JSON.stringify(selector)})].find((e) => e.textContent.trim().startsWith(${JSON.stringify(text)}))?.click();`;
const expandFirstAlert = "document.querySelector('main li button[aria-expanded]')?.click();";
// A declined request with at least two rule hits shows the trace at its best.
const openDeclinedDecision =
  "[...document.querySelectorAll('tbody tr')].find((r) => /Decline|拒绝/.test(r.textContent) && r.querySelectorAll('td button').length >= 2)?.click();";
const scrollTo = (y) =>
  `window.scrollTo(0, ${y}); document.querySelectorAll('*').forEach((el) => { if (el.scrollHeight > el.clientHeight + 200 && /auto|scroll/.test(getComputedStyle(el).overflowY)) el.scrollTop = ${y}; });`;

function shotList(paths) {
  return [
    { name: "overview", path: "/", themes: ["light", "dark"] },
    { name: "backtest", path: paths.strategy, prepare: (lang) => clickText("[role=tab]", lang === "zh" ? "回测" : "Backtest"), scroll: 560 },
    { name: "rules", path: paths.strategy },
    { name: "alerts", path: "/alerts", height: 780, prepare: () => expandFirstAlert },
    { name: "stability", path: "/stability", scroll: 640 },
    { name: "model", path: paths.model },
    { name: "binning", path: paths.indicator },
    { name: "decision", path: "/decisions", prepare: () => openDeclinedDecision },
    { name: "monitor", path: paths.monitor },
  ];
}

function startChrome() {
  const profile = process.env.SHOTS_PROFILE ?? mkdtempSync(join(tmpdir(), "kivi-shots-"));
  const chrome = spawn(
    process.env.CHROME ?? "google-chrome",
    [
      "--headless=new",
      `--remote-debugging-port=${PORT}`,
      `--user-data-dir=${profile}`,
      "--no-first-run",
      "--hide-scrollbars",
      "--force-color-profile=srgb",
      "--font-render-hinting=none",
    ],
    { stdio: "ignore" },
  );
  chrome.on("error", (e) => console.error(`Chrome did not start: ${e.message}; set CHROME to its binary`));
  const exited = new Promise((resolve) => chrome.once("close", resolve));
  process.on("exit", () => chrome.kill());
  // Wait for Chrome to exit before removing the profile it writes to.
  return async () => {
    if (chrome.exitCode === null && chrome.signalCode === null) chrome.kill();
    await Promise.race([exited, sleep(5000)]);
    if (!process.env.SHOTS_PROFILE) rmSync(profile, { recursive: true, force: true, maxRetries: 3 });
  };
}

class Page {
  constructor(ws) {
    this.ws = ws;
    this.id = 0;
    this.pending = new Map();
    this.waiters = [];
    ws.onmessage = (event) => {
      const msg = JSON.parse(event.data);
      if (msg.id && this.pending.has(msg.id)) {
        const { resolve, reject } = this.pending.get(msg.id);
        this.pending.delete(msg.id);
        msg.error ? reject(new Error(msg.error.message)) : resolve(msg.result);
      } else if (msg.method) {
        this.waiters = this.waiters.filter((w) => (w.method === msg.method ? (w.resolve(msg.params), false) : true));
      }
    };
  }

  static async open() {
    let ready = false;
    for (let i = 0; i < 150 && !ready; i++) {
      ready = await fetch(`http://127.0.0.1:${PORT}/json/version`).then((r) => r.ok, () => false);
      if (!ready) await sleep(200);
    }
    if (!ready) throw new Error(`Chrome's DevTools did not answer on port ${PORT}`);
    const target = await (await fetch(`http://127.0.0.1:${PORT}/json/new?about:blank`, { method: "PUT" })).json();
    const ws = new WebSocket(target.webSocketDebuggerUrl);
    await new Promise((resolve, reject) => {
      ws.onopen = resolve;
      ws.onerror = reject;
    });
    const page = new Page(ws);
    await page.send("Page.enable");
    await page.send("Network.enable");
    await page.send("Runtime.enable");
    return page;
  }

  send(method, params = {}) {
    const id = ++this.id;
    this.ws.send(JSON.stringify({ id, method, params }));
    return new Promise((resolve, reject) => this.pending.set(id, { resolve, reject }));
  }

  once(method) {
    return new Promise((resolve) => this.waiters.push({ method, resolve }));
  }

  eval(expression) {
    return this.send("Runtime.evaluate", { expression, awaitPromise: true, returnByValue: true });
  }
}

async function shot(page, session, { lang, theme, name, path, prepare, scroll, height = 900 }) {
  await page.send("Network.setCookie", { name: "kivi_session", value: session, url: WEB, httpOnly: true });
  await page.send("Network.setCookie", { name: "kivi_locale", value: lang === "zh" ? "zh-CN" : "en-US", url: WEB });
  await page.send("Emulation.setDeviceMetricsOverride", { width: WIDTH, height, deviceScaleFactor: 1.5, mobile: false });
  // Reduced motion turns chart animations off, so every chart is drawn in full when the shot is taken.
  await page.send("Emulation.setEmulatedMedia", {
    features: [
      { name: "prefers-color-scheme", value: theme },
      { name: "prefers-reduced-motion", value: "reduce" },
    ],
  });
  const { identifier } = await page.send("Page.addScriptToEvaluateOnNewDocument", {
    source: `try { localStorage.setItem("boardui:theme", ${JSON.stringify(theme)}); } catch {}
      document.addEventListener("DOMContentLoaded", () => {
        const style = document.createElement("style");
        style.textContent = "nextjs-portal { display: none !important; }";
        document.head.appendChild(style);
      });`,
  });
  const loaded = page.once("Page.loadEventFired");
  await page.send("Page.navigate", { url: WEB + path });
  await loaded;
  await sleep(2500);
  const steps = [prepare?.(lang), scroll && `await new Promise((r) => setTimeout(r, 1200)); ${scrollTo(scroll)}`].filter(Boolean);
  if (steps.length) {
    await page.eval(`(async () => { ${steps.join("\n")} })()`);
    await sleep(1500);
  }
  const { data } = await page.send("Page.captureScreenshot", { format: "webp", quality: 82 });
  await page.send("Page.removeScriptToEvaluateOnNewDocument", { identifier });
  const dir = join(OUT, lang);
  mkdirSync(dir, { recursive: true });
  const file = join(dir, `${name}${theme === "dark" ? "-dark" : ""}.webp`);
  const bytes = Buffer.from(data, "base64");
  writeFileSync(file, bytes);
  const shown = relative(ROOT, file).startsWith("..") ? file : relative(ROOT, file);
  console.log(`${shown}  ${Math.round(bytes.length / 1024)} KB`);
}

let stopChrome;
try {
  const session = await signIn();
  const shots = shotList(await demoPaths(session));
  const unknown = ONLY?.filter((n) => !shots.some((s) => s.name === n)) ?? [];
  if (unknown.length) throw new Error(`Unknown shot ${unknown.join(", ")}; choose from ${shots.map((s) => s.name).join(", ")}`);
  stopChrome = startChrome();
  const page = await Page.open();
  for (const lang of ["en", "zh"]) {
    for (const s of shots) {
      if (ONLY && !ONLY.includes(s.name)) continue;
      for (const theme of s.themes ?? ["light"]) await shot(page, session, { ...s, lang, theme });
    }
  }
} catch (e) {
  console.error(e.message);
  process.exitCode = 1;
} finally {
  await stopChrome?.();
  process.exit();
}
