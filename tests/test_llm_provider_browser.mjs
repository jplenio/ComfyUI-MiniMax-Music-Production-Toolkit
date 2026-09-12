// Real browser integration of the extension with a small ComfyUI host stub.
// No provider traffic or model generation. Optional Playwright, like EQ tests.
import assert from "node:assert/strict";
import {createRequire} from "node:module";
import {readFile} from "node:fs/promises";
import http from "node:http";
let chromium;
try { ({chromium} = createRequire(import.meta.url)("playwright")); }
catch { console.log("LLM browser test skipped: Playwright not installed."); process.exit(0); }
const requests = [];
const contract = JSON.parse(await readFile(new URL("./fixtures/node_contracts.json", import.meta.url), "utf8")).MiniMaxLLMChat;
const server = http.createServer(async (req, res) => {
    try {
        if (req.url === "/scripts/app.js") { res.setHeader("Content-Type", "text/javascript"); res.end("export const app={registerExtension(extension){globalThis.extension=extension;}};"); return; }
        if (req.url === "/scripts/api.js") { res.setHeader("Content-Type", "text/javascript"); res.end("export const api={fetchApi:(...args)=>fetch(...args)};"); return; }
        if (["/web/llm_provider.js", "/web/llm_provider_ui.js"].includes(req.url)) { res.setHeader("Content-Type", "text/javascript"); res.end(await readFile(new URL(`..${req.url}`, import.meta.url))); return; }
        if (req.url.endsWith("/configure")) {
            let raw = ""; for await (const chunk of req) raw += chunk;
            const body = JSON.parse(raw); requests.push(body);
            res.setHeader("Content-Type", "application/json");
            res.end(JSON.stringify(body.action === "models" ? {models: ["loaded-small", "loaded-large"]} : body.action === "set_key" ? {credential_id: "opaque-test-reference"} : {ok: true})); return;
        }
        res.setHeader("Content-Type", "text/html; charset=utf-8");
        res.end('<!doctype html><html><body style="background:#161b22;color:#eee;font:16px sans-serif"><main style="margin:32px;width:520px;background:#283e37;padding:24px;border-radius:12px"><h2>LLM · ComfyUI / Local / Cloud</h2><section></section></main></body></html>');
    } catch { res.statusCode = 500; res.end(); }
});
await new Promise(resolve => server.listen(0, "127.0.0.1", resolve));
let browser;
try {
    try { browser = await chromium.launch({headless: true}); }
    catch { browser = await chromium.launch({headless: true, channel: "msedge"}); }
    const page = await browser.newPage({viewport: {width: 1050, height: 1100}});
    const errors = []; page.on("pageerror", error => errors.push(error.message));
    await page.goto(`http://127.0.0.1:${server.address().port}`);
    await page.evaluate(async contract => {
        await import("/web/llm_provider.js");
        const widgets = [];
        for (const [name, spec] of Object.entries({...contract.required, ...contract.optional})) {
            if (spec[1]?.forceInput) continue;
            widgets.push({name, value: spec[1]?.default ?? (Array.isArray(spec[0]) ? spec[0][0] : ""), type: Array.isArray(spec[0]) ? "combo" : "text", options: {values: Array.isArray(spec[0]) ? spec[0] : null}, draw() {}});
        }
        globalThis.testNode = {comfyClass: "MiniMaxLLMChat", widgets,
            addWidget(type, name, value, callback, options) { const w = {type, name, value, callback, options}; this.widgets.push(w); return w; },
            setDirtyCanvas() { render(); },
        };
        function render() {
            const section = document.querySelector("section"); section.replaceChildren();
            for (const w of widgets) {
                if (w.type === "minimax_hidden") continue;
                const row = document.createElement(w.type === "button" ? "div" : "label"); row.style.cssText = "display:block;margin:12px 0";
                if (w.type === "button") {
                    const button = document.createElement("button"); button.textContent = w.label || w.name; button.onclick = () => w.callback();
                    button.style.cssText = "padding:8px;width:100%"; row.append(button);
                } else {
                    row.append(document.createTextNode(w.label || w.name));
                    const input = document.createElement(w.options.values ? "select" : "input");
                    input.setAttribute("aria-label", w.label || w.name); input.style.cssText = "width:100%;padding:6px;box-sizing:border-box";
                    if (w.options.values) for (const value of w.options.values) { const option = document.createElement("option"); option.textContent = option.value = value; input.append(option); }
                    input.value = w.value; input.onchange = () => { w.value = input.value; w.callback?.(input.value); };
                    row.append(input);
                }
                section.append(row);
            }
        }
        extension.nodeCreated(testNode); render();
    }, contract);
    await page.getByLabel("Run language model", {exact: true}).selectOption("Local app / server");
    assert.equal(await page.getByLabel("model", {exact: true}).count(), 0);
    assert.equal(await page.getByLabel("Local app", {exact: true}).count(), 1);
    assert.equal(await page.getByLabel("Cloud provider", {exact: true}).count(), 0);
    await page.getByRole("button", {name: "Set API key…", exact: true}).click();
    await page.locator('input[type="password"]').fill("browser-test-secret");
    await page.getByRole("button", {name: "Apply", exact: true}).click();
    await page.waitForFunction(() => !document.querySelector("dialog"));
    assert.equal(await page.evaluate(() => JSON.stringify(testNode.widgets.map(w => w.value)).includes("browser-test-secret")), false);
    assert.equal(await page.evaluate(() => localStorage.length), 0);
    await page.getByRole("button", {name: "Find models / test connection…", exact: true}).click();
    await page.locator("dialog select").selectOption("loaded-large");
    await page.getByRole("button", {name: "Apply", exact: true}).click();
    assert.equal(await page.getByLabel("Model ID", {exact: true}).inputValue(), "loaded-large");
    await page.getByLabel("Run language model", {exact: true}).selectOption("Cloud service");
    assert.equal(await page.getByLabel("Local app", {exact: true}).count(), 0);
    assert.equal(await page.getByLabel("Cloud provider", {exact: true}).count(), 1);
    assert.equal(await page.getByLabel("Model ID", {exact: true}).inputValue(), "");
    assert.equal(await page.evaluate(() => testNode.widgets.find(w => w.name === "credential_id").value), "");
    if (process.env.LLM_SCREENSHOT) await page.screenshot({path: process.env.LLM_SCREENSHOT});
    assert.deepEqual(errors, []);
    assert.deepEqual(requests.map(r => r.action), ["set_key", "models"]);
    assert.equal(requests[1].key, undefined);
    console.log("LLM browser: mode switching, key dialog, no secret serialization/storage, model discovery and provider reset passed.");
} finally { await browser?.close(); await new Promise(resolve => server.close(resolve)); }
