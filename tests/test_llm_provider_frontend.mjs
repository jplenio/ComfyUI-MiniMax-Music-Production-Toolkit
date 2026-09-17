import assert from "node:assert/strict";
import { visible, refresh, settings, signature, INTEGRATED, LOCAL, CLOUD, BUTTONS } from "../web/llm_provider_ui.js";
import { removeLegacyLLMSessionInput } from "../web/migration_utils.js";
import { applyTooltip } from "../web/prompt_ui_utils.js";

// Every action button must carry help text; a canvas button has no label
// attribute of its own, so the tooltip is the only explanation available.
const EXPECTED_BUTTONS = ["llm_ui_advanced", "llm_ui_key", "llm_ui_clear", "llm_ui_models", "llm_ui_help"];
assert.deepEqual(Object.keys(BUTTONS).sort(), [...EXPECTED_BUTTONS].sort());
for (const [name, entry] of Object.entries(BUTTONS)) {
    assert.ok(entry.label && entry.label.length > 3, `${name} needs a label`);
    assert.ok(entry.tooltip && entry.tooltip.length > 30, `${name} needs a real tooltip`);
}

const fakeWidget = {name: "x"};
applyTooltip(fakeWidget, "help text");
assert.equal(fakeWidget.tooltip, "help text");
assert.equal(fakeWidget.options.tooltip, "help text");
const fakeDom = {title: "", inputEl: {title: ""}};
applyTooltip(fakeDom, "dom help");
assert.equal(fakeDom.title, "dom help", "DOM elements need the native title attribute");
assert.equal(fakeDom.inputEl.title, "dom help");
assert.equal(applyTooltip(undefined, "ignored"), undefined, "a missing widget must not throw");

for (const mode of [INTEGRATED, LOCAL, CLOUD]) {
    assert.equal(visible("backend", mode), true);
    assert.equal(visible("credential_id", mode, true), false);
    assert.equal(visible("model", mode), mode === INTEGRATED);
    assert.equal(visible("remote_model", mode), mode !== INTEGRATED);
    assert.equal(visible("local_provider", mode), mode === LOCAL);
    assert.equal(visible("cloud_provider", mode), mode === CLOUD);
    assert.equal(visible("n_gpu_layers", mode), false);
    assert.equal(visible("n_gpu_layers", mode, true), mode === INTEGRATED);
}
const make = (name, value, type = "text") => ({name, value, type, computeSize: () => [300, 20], draw() {}});
const node = {widgets: [make("model", "legacy.gguf"), make("seed", 123), make("backend", INTEGRATED, "combo"), make("remote_model", "remote-id"), make("credential_id", "opaque-handle")], setDirtyCanvas() {}};
const order = node.widgets.map(w => w.name);
const values = node.widgets.map(w => w.value);
const draw = node.widgets[0].draw;
refresh(node);
node.widgets[2].value = LOCAL;
refresh(node);
assert.equal(node.widgets[0].type, "minimax_hidden");
assert.equal(node.widgets[3].type, "text");
node.widgets[2].value = INTEGRATED;
refresh(node);
assert.equal(node.widgets[0].draw, draw);
assert.equal(node.widgets[0].type, "text");
assert.deepEqual(node.widgets.map(w => w.name), order);
assert.deepEqual(node.widgets.map(w => w.value), values);
const before = signature(node);
node.widgets.push(make("server_url", "http://localhost:8888/v1"));
assert.notEqual(signature(node), before);
assert.equal(settings(node).server_url, "http://localhost:8888/v1");
console.log("LLM provider visibility, restore, serialization and request signatures: OK");

const oldNode = {inputs: [{name: "user_text"}, {name: "session_id"}, {name: "system_prompt"}], removeInput(index) { this.inputs.splice(index, 1); this.removed = index; }};
assert.equal(removeLegacyLLMSessionInput(oldNode), true);
assert.equal(oldNode.removed, 1);
assert.deepEqual(oldNode.inputs.map(i => i.name), ["user_text", "system_prompt"]);
assert.equal(removeLegacyLLMSessionInput(oldNode), false);
