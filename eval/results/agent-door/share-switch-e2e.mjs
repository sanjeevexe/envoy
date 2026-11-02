// The share switch end to end on the :8761 copy of main (my own session there; agent keys made here are never shown).
import { chromium } from "playwright-core";
import { readFileSync, writeFileSync } from "fs";
const [dir, mcpTokenFile, out] = process.argv.slice(2);
const token = readFileSync(`${dir}/session_token`, "utf8").trim();
const mcpKey = readFileSync(mcpTokenFile, "utf8").trim();
const base = "http://127.0.0.1:8761";
const H = { Authorization: `Bearer ${token}`, "Content-Type": "application/json" };
const apiGet = (p) => fetch(base + p, { headers: H }).then((r) => r.json());
const share = (name, on) => fetch(`${base}/api/routines/${name}/share`, { method: "POST", headers: H, body: JSON.stringify({ on }) });
const toolsList = async () => {
  const r = await fetch(base + "/mcp", { method: "POST", headers: { Authorization: `Bearer ${mcpKey}`, "Content-Type": "application/json",
    Accept: "application/json, text/event-stream", "MCP-Protocol-Version": "2025-11-25" }, body: JSON.stringify({ jsonrpc: "2.0", id: 1, method: "tools/list", params: {} }) });
  return (await r.json()).result.tools.map((t) => t.name);
};
const sees = async () => { const a = await apiGet("/api/agents"); return Object.fromEntries([[a.muse.name, a.muse.sees?.length], ...a.agents.map((x) => [x.name, x.sees?.length])]); };
const R = "skylark_check_flight_status", INTENT = "Check the status of a SkyLark flight";
const log = { at: new Date().toISOString() };

const have = (await apiGet("/api/agents")).agents.map((a) => a.name);
for (const [name, tools] of [["Spark agent", ["read", "run"]], ["Reader", ["read"]]])
  if (!have.includes(name)) await fetch(base + "/api/agents", { method: "POST", headers: H, body: JSON.stringify({ name, tools }) });  // the key in the answer is dropped
await share(R, false);
log.before = { mcp_has_tool: (await toolsList()).includes(R), sees: await sees() };

const browser = await chromium.launch({ executablePath: "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome", headless: true });
const page = await browser.newPage({ viewport: { width: 1920, height: 1080 }, deviceScaleFactor: 1 });
await page.goto(`http://localhost:8761/login?k=${token}`);
await page.waitForTimeout(800);
await page.goto("http://localhost:8761/?settings=agents#agent-tools");
await page.waitForTimeout(2500);
await page.evaluate(() => { window.__events = 0; window.addEventListener("envoy:sharing", () => { window.__events++; }); });
await page.getByRole("button", { name: /Not shared/ }).click();
await page.waitForTimeout(500);
const t0 = Date.now();
await page.getByRole("switch", { name: `Share ${INTENT} with agents` }).click();
await page.locator(`#agent-tool-${R}`).waitFor({ timeout: 5000 });
log.shared_in_settings = { ms_to_row: Date.now() - t0, first_row: await page.locator('[id^="agent-tool-"]').first().getAttribute("id"),
  new_mark: await page.locator(`#agent-tool-${R}`).getByText(/New · added/).isVisible(), events: await page.evaluate(() => window.__events),
  mcp_has_tool: (await toolsList()).includes(R), sees: await sees() };
await page.waitForTimeout(800);
await page.screenshot({ path: `${out}/e2e-1080p-shared.png` });

// The routine's own page: the switch is on and names the tool; turn it off there.
await page.getByRole("button", { name: "Routines" }).first().click();
await page.waitForTimeout(800);
await page.getByText(INTENT).first().click();
await page.waitForTimeout(1200);
const sw = page.getByRole("switch", { name: "Share with agents" });
log.routine_page = { switch_on: await sw.getAttribute("aria-checked"), names_tool: await page.getByText(R, { exact: true }).first().isVisible() };
await page.screenshot({ path: `${out}/e2e-1080p-routine-page.png` });
await sw.click();
await page.waitForTimeout(1200);
log.unshared_on_routine_page = { switch_on: await sw.getAttribute("aria-checked"), mcp_has_tool: (await toolsList()).includes(R), sees: await sees() };
await browser.close();
writeFileSync(`${out}/e2e.json`, JSON.stringify(log, null, 1));
console.log(JSON.stringify(log, null, 1));
