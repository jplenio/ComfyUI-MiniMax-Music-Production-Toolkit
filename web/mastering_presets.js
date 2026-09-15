import { app } from "../../scripts/app.js";
import { applyMasteringPreset, restoreAppendedControls } from "./mastering_preset_utils.js";

let pendingCatalog;
function catalog() {
    return pendingCatalog ??= fetch(new URL("./mastering_presets.json", import.meta.url))
        .then(response => {
            if (!response.ok) throw new Error("Could not load mastering presets");
            return response.json();
        }).catch(error => { pendingCatalog = null; throw error; });
}

app.registerExtension({
    name: "music_toolkit.mastering_presets",
    beforeRegisterNodeDef(nodeType, nodeData) {
        if (!["MiniMaxModelAutodownload", "MiniMaxMusicModelSettings"].includes(nodeData.name)) return;
        const previous = nodeType.prototype.onConfigure;
        nodeType.prototype.onConfigure = function(info) {
            const result = previous?.apply(this, arguments);
            restoreAppendedControls(this, info);
            return result;
        };
    },
    nodeCreated(node) {
        if ((node.comfyClass ?? node.type) !== "MiniMaxMasteringCompressor") return;
        const preset = node.widgets?.find(w => w.name === "preset");
        if (!preset) return;
        const previous = preset.callback;
        preset.callback = async function(value) {
            previous?.apply(this, arguments);
            const request = node.__masteringRequest = (node.__masteringRequest || 0) + 1;
            if (value === "Custom") return;
            try {
                const presets = await catalog();
                if (node.__masteringRequest === request && preset.value === value) {
                    applyMasteringPreset(node, value, presets);
                }
            } catch(error) { console.warn("Mastering preset:", error); }
        };
        for (const w of node.widgets || []) {
            if (["preset", "bypass", "target_sample_rate"].includes(w.name)) continue;
            const callback = w.callback;
            w.callback = function(...args) {
                preset.value = "Custom";
                node.__masteringRequest = (node.__masteringRequest || 0) + 1;
                return callback?.apply(this, args);
            };
        }
    },
});
