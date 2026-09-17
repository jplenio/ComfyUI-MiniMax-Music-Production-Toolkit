import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import { attachAutoEQPresets, sameSettings } from "../web/eq_presets.js";
const catalog = JSON.parse(await readFile(new URL("../web/eq_presets.json", import.meta.url)));
globalThis.fetch = async () => ({ok:true, json:async () => catalog});
class Element {
    constructor(tag) { this.tag = tag; this.style = {}; this.children = []; }
    append(...items) { this.children.push(...items); }
    prepend(...items) { this.children.unshift(...items); }
    replaceChildren(...items) { this.children = items; }
    setAttribute(key, value) { this[key] = value; }
    getContext() { return null; }
    remove() { this.removed = true; }
}
globalThis.document = {createElement:tag => new Element(tag)};
globalThis.ResizeObserver = class { observe() {} disconnect() {} };
const descendants = root => [root, ...root.children.flatMap(descendants)];
const makeNode = widgets => ({widgets, inputs:[], addDOMWidget(name, type, root, options) {
    assert.equal(options.serialize, false); this.root = root; return {};
}, setDirtyCanvas() {}});
const defaults = catalog.auto[0].values;
const auto = makeNode(Object.entries(defaults).map(([name,value]) => ({name,value})));
auto.widgets[0].type="combo";
auto.widgets[0].options={values:["Reference track","Warm tilt","Bright tilt"]};
auto.widgets[0].inputEl={hidden:false};
auto.widgets.push({name:"enabled",value:false});
const originalWidgets=[...auto.widgets];
const ui = attachAutoEQPresets(auto);
await ui.ready;
assert.deepEqual(auto.widgets,originalWidgets); // Values retain legacy positions.
assert.equal(auto.widgets[0].hidden,true);
assert.equal(auto.widgets[0].options.hidden,true);
assert.equal(auto.widgets[0].inputEl.hidden,true);
assert.notEqual(auto.widgets[0].options.serialize,false);
assert.equal(auto.widgets[0].computeSize()[1],-4);
assert.equal(descendants(ui.root).filter(e=>e.tag==="select").length,1);
assert.equal(ui.select.children.length,11); // Ten presets and Custom, one control.
assert.equal(ui.select.value, "Warm - gentle (workflow default)");
for (const preset of catalog.auto) {
    ui.select.value = preset.name; ui.select.onchange();
    for (const [key,value] of Object.entries(preset.values)) assert.equal(auto.widgets.find(w=>w.name===key).value,value);
    assert.equal(auto.widgets.at(-1).value, false);
}
const description=ui.root.children[1];
assert.match(description.textContent,/Reference audio missing/);
auto.inputs=[{name:"reference_audio",link:99}]; auto.onDrawForeground();
assert.doesNotMatch(description.textContent,/Reference audio missing/);
auto.inputs=[]; auto.onDrawForeground(); assert.match(description.textContent,/Reference audio missing/);
ui.select.value=catalog.auto[0].name; ui.select.onchange();
assert.doesNotMatch(description.textContent,/Reference audio missing/);
auto.widgets[1].value = 42; auto.onDrawForeground(); assert.equal(ui.select.value,"Custom");
assert.match(description.textContent,/Custom: Warm tilt/);
// Old positional workflow restore still supplies the backend's canonical target.
auto.widgets[0].value="Bright tilt";
auto.widgets[0].hidden=false; auto.widgets[0].type="combo"; auto.onConfigure();
assert.equal(auto.widgets[0].value,"Bright tilt");
assert.equal(auto.widgets[0].hidden,true);
assert.equal(auto.widgets[1].value,42);
assert.match(description.textContent,/Custom: Bright tilt/);
auto.inputs = [{name:"strength_percent",link:1}]; auto.onDrawForeground();
assert.equal(ui.select.disabled,true);
ui.select.value=catalog.auto[0].name; ui.select.onchange(); assert.equal(auto.widgets[1].value,42);
auto.onRemoved(); assert.equal(ui.root.removed,true);

// Exercise the actual editor, including its existing JSON, Undo and linked state.
const source = (await readFile(new URL("../web/audio_eq.js",import.meta.url),"utf8"))
    .replace('import { app } from "../../scripts/app.js";', 'const app={registerExtension(){}};')
    .replaceAll('"./eq_dsp.js"', JSON.stringify(new URL("../web/eq_dsp.js",import.meta.url).href))
    .replaceAll('"./eq_presets.js"', JSON.stringify(new URL("../web/eq_presets.js",import.meta.url).href))
    .replaceAll('"./prompt_ui_utils.js"', JSON.stringify(new URL("../web/prompt_ui_utils.js",import.meta.url).href));
const {attachEQEditor} = await import(`data:text/javascript;base64,${Buffer.from(source).toString("base64")}`);
const flat=JSON.stringify(catalog.manual[0].settings);
const manual=makeNode([{name:"eq_settings_json",value:flat}]);
const editor=attachEQEditor(manual);
await new Promise(resolve=>setImmediate(resolve));
const select=descendants(editor.root).find(e=>e["aria-label"]==="Manual EQ preset");
assert.equal(select.value,"Flat"); assert.equal(manual.widgets[0].value,flat);
for(const p of catalog.manual) {
    select.value=p.name; select.onchange();
    assert.ok(sameSettings(JSON.parse(manual.widgets[0].value),p.settings));
}
select.value="YuE2 - Smooth highs"; select.onchange();
const saved=manual.widgets[0].value;
const preamp=descendants(editor.root).find(e=>e["aria-label"]==="Preamp dB");
preamp.value=-4; preamp.onchange(); assert.equal(select.value,"Custom");
descendants(editor.root).find(e=>e.textContent==="Undo").onclick();
assert.equal(manual.widgets[0].value,saved); assert.equal(select.value,"YuE2 - Smooth highs");
manual.inputs=[{name:"eq_settings_json",link:5}]; editor.sync(); assert.equal(select.disabled,true);
select.value="Flat"; select.onchange(); assert.equal(manual.widgets[0].value,saved);
manual.inputs=[]; manual.widgets[0].value=flat; editor.sync(); assert.equal(select.value,"Flat");
manual.onRemoved(); assert.equal(editor.root.removed,true);
assert.equal(catalog.auto.length,10); assert.equal(catalog.manual.length,24);
console.log("EQ presets: all recipes, defaults, Custom, Undo, restore, linked protection and cleanup passed.");
