/**
 * Scripted product demo: drives the running local Smart Docs stack with
 * Playwright, records a video (Playwright's built-in recorder, webm) and
 * captures captioned still frames. `make-gif.py` turns the frames into a GIF.
 *
 *   cd e2e && bun install
 *   E2E_BASE_URL=http://localhost:8010 bun run scripts/record-demo.ts [outDir]
 *   uv run --with pillow e2e/scripts/make-gif.py e2e/demo-frames docs/pr/mvp.gif 960
 *
 * It needs the API, the worker and a local model running, so the saved page
 * gets a summary, tags and an embedding during the recording.
 */
import { chromium, type Page } from "playwright";
import { mkdirSync, renameSync, writeFileSync } from "node:fs";
import { join } from "node:path";

const BASE = process.env.E2E_BASE_URL ?? "http://localhost:8010";
const OUT = process.argv[2] ?? join(import.meta.dir, "..", "demo-frames");
mkdirSync(OUT, { recursive: true });

const frames: { file: string; hold: number }[] = [];
let n = 0;

async function caption(page: Page, text: string) {
  await page.evaluate((t) => {
    let el = document.getElementById("__demo_caption");
    if (!el) {
      el = document.createElement("div");
      el.id = "__demo_caption";
      Object.assign(el.style, {
        position: "fixed", left: "0", right: "0", bottom: "0", zIndex: "99999",
        padding: "14px 24px", background: "rgba(15,23,42,.92)", color: "#fff",
        font: "600 20px/1.3 system-ui, sans-serif", textAlign: "center",
        letterSpacing: ".01em",
      });
      document.body.appendChild(el);
    }
    el.textContent = t;
  }, text);
}

/** Capture one frame; `hold` is how long the GIF shows it (ms). The video keeps rolling. */
async function shot(page: Page, text: string, hold = 1600) {
  await caption(page, text);
  await page.waitForTimeout(250);
  const file = join(OUT, `frame-${String(n++).padStart(3, "0")}.png`);
  await page.screenshot({ path: file });
  frames.push({ file, hold });
  await page.waitForTimeout(hold);
}

/** Public URLs are built with PUBLIC_BASE_URL (port 8000 locally); the app listens on BASE. */
function local(url: string) {
  return BASE + url.replace(/^https?:\/\/[^/]+/, "");
}

const browser = await chromium.launch();
const ctx = await browser.newContext({
  viewport: { width: 1280, height: 800 },
  deviceScaleFactor: 1,
  colorScheme: "light",
  recordVideo: { dir: OUT, size: { width: 1280, height: 800 } },
});
const page = await ctx.newPage();

// The editor uses window.prompt / window.confirm. Answer them from a queue.
const answers: string[] = [];
page.on("dialog", (d) => {
  const a = answers.length ? answers.shift() : undefined;
  console.log(`dialog ${d.type()} "${d.message()}" -> ${a === undefined ? "(accept)" : JSON.stringify(a)}`);
  return d.accept(a);
});
page.on("response", (r) => { if (r.url().includes("/api/v1") && r.status() >= 400) console.log(`HTTP ${r.status()} ${r.request().method()} ${r.url()}`); });
page.on("pageerror", (e) => console.log("pageerror", e.message));

const ts = Date.now().toString(36);
const handle = `demo${ts.slice(-5)}`;
const email = `demo-${ts}@example.com`;
const password = "Demo-Passw0rd!";
// Identity lives at the accounts service (SD-014): sign up there through its API, confirm the
// address through Mailpit, refresh so the session carries email_verified, then open the editor.
const ACCOUNTS = process.env.ACCOUNTS_URL ?? "http://localhost:8085";
const MAILPIT = process.env.MAILPIT_URL ?? "http://localhost:8025";
async function mailedLink(kind: "verify" | "magic"): Promise<string> {
  for (let i = 0; i < 40; i++) {
    const list = await (await fetch(`${MAILPIT}/api/v1/search?query=${encodeURIComponent("to:" + email)}`)).json();
    for (const m of list.messages ?? []) {
      const full = await (await fetch(`${MAILPIT}/api/v1/message/${m.ID}`)).json();
      const match = String(full.Text ?? "").match(new RegExp(`${ACCOUNTS.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")}/${kind}\?token=[A-Za-z0-9_-]+`));
      if (match) return match[0];
    }
    await new Promise((r) => setTimeout(r, 500));
  }
  throw new Error(`no ${kind} mail for ${email}`);
}

// 1. Landing
await page.goto(`${BASE}/`);
await page.waitForSelector("text=Pages for people");
await shot(page, "Smart Docs: an open-source knowledge base for people and agents", 2400);

// 2. Sign up at the accounts service (shared across the 3m4 apps), then come back to the editor
await page.goto(`${BASE}/signup`);
await page.waitForURL(/\/signup/);
await shot(page, "Sign up once at accounts.3m4.net: it works in every 3m4 app", 1600);
const signup = await ctx.request.post(`${ACCOUNTS}/api/auth/signup`, { data: { email, password, handle } });
if (!signup.ok()) throw new Error(`signup ${signup.status()}: ${await signup.text()}`);
const verifyToken = new URL(await mailedLink("verify")).searchParams.get("token");
await ctx.request.post(`${ACCOUNTS}/api/auth/verify/consume`, { data: { token: verifyToken } });
await ctx.request.post(`${ACCOUNTS}/api/session/refresh`, { data: {} });
await page.goto(`${BASE}/app`);
await page.waitForSelector("text=No projects yet");
await shot(page, "The editor. Projects, API keys, usage and settings on the left", 1800);

// 3. Project + page
answers.push("Field notes");
await page.locator("button[title='New project']").click();
await page.waitForSelector("text=This project is empty");
await shot(page, "Create a project with +", 1400);
answers.push("Getting started");
await page.locator("button.mini:has-text('+ page')").click();
await page.waitForSelector("textarea");
const createdAt = Date.now();
await shot(page, "Add a page with + page", 1200);
const body = [
  "# Getting started",
  "",
  "Smart Docs keeps pages for people and agents in one place.",
  "",
  "## What you get",
  "",
  "- HTML for people",
  "- Raw Markdown for tools",
  "- `llms.txt` for models",
  "",
  "| Form | URL |",
  "|------|-----|",
  "| HTML | `/handle/project/page` |",
  "| Markdown | `/handle/project/page.md` |",
  "| Index | `/handle/project/llms.txt` |",
  "",
  "Private pages are 404 to everyone but you, never 403.",
].join("\n");
await page.fill("textarea", "");
await page.locator("textarea").pressSequentially(body, { delay: 12 });
await shot(page, "Write Markdown: headings, lists, tables", 1400);
// The local tier allows one model call per 10 s per account; creating the page used one.
await page.waitForTimeout(Math.max(0, 12000 - (Date.now() - createdAt)));
await page.locator("button.primary:has-text('Save')").click();
await page.waitForSelector("text=Saved. Version");
await shot(page, "Save. The summary, tags and embedding run in a worker", 1800);

// 4. Preview + publish
await page.locator("button:has-text('Preview')").click();
await page.waitForSelector(".split .preview table");
await shot(page, "Preview renders the page side by side", 2000);
await page.locator("button:has-text('Publish')").click();
await page.waitForSelector("text=Published at");
await shot(page, "Publish. The page now has a public URL", 1800);

// 5. Public forms
const publicUrl = (await page.locator(".status a:has-text('public page')").getAttribute("href"))!;
const projectUrl = publicUrl.split("/").slice(0, -1).join("/");
const [projectSlug, pagePath] = publicUrl.split("/").slice(-2);
await page.goto(local(publicUrl));
await page.waitForSelector("table");
await shot(page, `${publicUrl.replace(/^https?:\/\/[^/]+/, "")}: the HTML page, for people`, 2200);
await page.goto(local(publicUrl + ".md"));
await page.waitForTimeout(300);
await shot(page, "The same page as raw Markdown, for tools", 2000);
await page.goto(local(projectUrl + "/llms.txt"));
await page.waitForTimeout(300);
await shot(page, "And the project's llms.txt, for models", 2000);

// 6. Back in the editor: wait for the worker
await page.goto(`${BASE}/app#/p/${projectSlug}/${pagePath}`);
await page.waitForSelector("textarea");
await caption(page, "Meanwhile the worker asks a local model (Ollama) for a summary and tags…");
let status = "pending";
for (let i = 0; i < 45 && status === "pending"; i++) {
  await page.waitForTimeout(2000);
  await page.reload();
  await page.waitForSelector(".status");
  status = (await page.locator(".status span[title]").innerText()).replace("metadata: ", "").trim();
}
if (status === "done") {
  await page.waitForTimeout(400);
  await shot(page, "A minute later: summary and tags from a local model (Ollama)", 2600);
} else {
  console.warn(`enrichment ended as "${status}"; skipping the metadata frame`);
}

// 7. API keys
await page.goto(`${BASE}/app#/keys`);
await page.waitForSelector("button:has-text('Create key')");
await shot(page, "API keys for agents, with read / write / publish scopes", 1600);
await page.locator("button:has-text('Create key')").click();
await page.waitForSelector("td:has-text('claude-code')");
await shot(page, "Create a key. Agents send it as a Bearer token on /api/v1 and /mcp", 2200);

// 8. Search
await page.goto(`${BASE}/app#/p/${projectSlug}`);
await page.waitForSelector("text=Pick a page in the tree");
await page.locator("button.mini:has-text('search')").click();
await page.waitForSelector("input[placeholder^='Ask']");
await page.locator("input[placeholder^='Ask']").pressSequentially("private pages", { delay: 50 });
await page.locator("button.primary:has-text('Search')").click();
await page.waitForSelector(".results li");
await shot(page, "Semantic search over the project (pgvector)", 2800);

// 9. MCP one-liner
await page.goto(`${BASE}/`);
await page.locator("pre").scrollIntoViewIfNeeded();
await page.waitForTimeout(300);
await shot(page, "One line adds Smart Docs to Claude Code as an MCP server", 3000);

const video = page.video();
await ctx.close();
await browser.close();
if (video) {
  const recorded = await video.path();
  renameSync(recorded, join(OUT, "demo.webm"));
}
writeFileSync(join(OUT, "frames.json"), JSON.stringify(frames, null, 2));
console.log(`captured ${frames.length} frames${video ? " + demo.webm" : ""} in ${OUT}`);
