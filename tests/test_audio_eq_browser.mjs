// Optional real-browser acceptance test. Requires Playwright + a Chromium browser.
// Run from the repository root: node tests/test_audio_eq_browser.mjs
// Without Playwright it reports the skip and exits 0, so an optional tool never
// turns the release gate red; with Playwright installed a real failure fails.
import assert from "node:assert/strict";
import { createRequire } from "node:module";
import { readFile } from "node:fs/promises";
import http from "node:http";

let chromium = null;
try {
    ({ chromium } = createRequire(import.meta.url)("playwright"));
} catch {
    console.log(
        "test_audio_eq_browser.mjs: skipped - Playwright is not installed " +
        "(npm i -D playwright && npx playwright install chromium)."
    );
    process.exit(0);
}
const server = http.createServer(async(req,res)=>{
    try {
        if(req.url==="/scripts/app.js") {res.setHeader("Content-Type","text/javascript");res.end("export const app={registerExtension(){}};");return;}
        if(req.url==="/web/audio_eq.js" || req.url==="/web/eq_dsp.js") {res.setHeader("Content-Type","text/javascript");res.end(await readFile(new URL(`..${req.url}`,import.meta.url)));return;}
        res.setHeader("Content-Type","text/html");res.end('<!doctype html><html><body style="background:#111"><main style="width:620px"></main></body></html>');
    } catch {res.statusCode=404;res.end();}
});
await new Promise(resolve=>server.listen(0,"127.0.0.1",resolve));
let browser;
try {
    try {browser=await chromium.launch({headless:true});}
    catch {browser=await chromium.launch({headless:true,channel:"msedge"});}
    const page=await browser.newPage({viewport:{width:900,height:850},deviceScaleFactor:2});
    const errors=[];page.on('pageerror',error=>errors.push(error.message));
    await page.goto(`http://127.0.0.1:${server.address().port}`);
    await page.evaluate(async()=>{
        const {attachEQEditor}=await import('/web/audio_eq.js');
        globalThis.testNode={widgets:[{name:'eq_settings_json',value:'{"schema":"minimax_eq_v1","preamp_db":0,"bands":[]}'}],inputs:[{name:'eq_settings_json',link:null}],
            setDirtyCanvas(){},addDOMWidget(name,type,element){document.querySelector('main').append(element);return {};}};
        globalThis.editor=attachEQEditor(testNode);
    });
    await page.getByRole('button',{name:'Add band',exact:true}).click();
    await page.getByRole('spinbutton',{name:'dB',exact:true}).fill('6');
    await page.getByRole('spinbutton',{name:'dB',exact:true}).press('Tab');
    assert.equal(await page.evaluate(()=>JSON.parse(testNode.widgets[0].value).bands[0].gain_db),6);
    await page.getByRole('spinbutton',{name:'Hz',exact:true}).fill('2400');
    await page.getByRole('spinbutton',{name:'Hz',exact:true}).press('Tab');
    await page.getByRole('button',{name:'Undo',exact:true}).click();
    assert.equal(await page.evaluate(()=>JSON.parse(testNode.widgets[0].value).bands[0].frequency_hz),1000);
    await page.evaluate(()=>{testNode.inputs[0].link=42;editor.sync();});
    assert.ok(await page.getByRole('spinbutton',{name:'dB',exact:true}).isDisabled());
    await page.evaluate(()=>{testNode.inputs[0].link=null;editor.sync();});
    await page.getByRole('combobox',{name:'Band 1 type'}).selectOption('low_shelf');
    assert.equal(await page.getByRole('spinbutton',{name:'Slope',exact:true}).count(),1);
    await page.evaluate(()=>{testNode.widgets[0].value=JSON.stringify({schema:'minimax_eq_v1',preamp_db:-3,bands:[{id:'restored',enabled:true,type:'peak',frequency_hz:500,gain_db:-4,q:1}]});editor.sync();});
    assert.equal(await page.getByRole('spinbutton',{name:'Hz',exact:true}).inputValue(),'500');
    if(process.env.EQ_SCREENSHOT)await page.screenshot({path:process.env.EQ_SCREENSHOT});
    await page.evaluate(()=>testNode.onRemoved());
    assert.equal(await page.locator('canvas').count(),0);
    assert.deepEqual(errors,[]);
    console.log('EQ browser: numeric editing, undo, linked read-only state, shelf controls, restore, cleanup passed.');
} finally {
    await browser?.close();
    await new Promise(resolve=>server.close(resolve));
}
