import { app } from "../../scripts/app.js";
import { api } from "../../scripts/api.js";
import { modelTemplate, connectedModel } from "./song_model_utils.js";

const widget = (node, name) => node.widgets?.find(w => w.name === name);

async function syncPrompt(node) {
    if (widget(node, "system_prompt_source")?.value !== "bundled_library") return;
    const model = connectedModel(node);
    const file = widget(node, "system_prompt_file");
    const text = widget(node, "system_prompt");
    const next = modelTemplate(file?.value, model);
    if (!file || !text || next === file.value) return;
    const oldFile = file.value;
    const oldText = text.value;
    const request = node.__songModelRequest = (node.__songModelRequest || 0) + 1;
    try {
        const params = new URLSearchParams({kind: "system", source: "bundled_library", directory: "", file: next});
        const response = await api.fetchApi(`/minimax_music_toolkit/prompt_text?${params}`);
        const payload = await response.json();
        if (!response.ok || !payload.ok) throw new Error(payload.error || "Could not load model template");
        // A later model change, file selection or edit invalidates this request.
        if (request !== node.__songModelRequest || connectedModel(node) !== model ||
            file.value !== oldFile || text.value !== oldText ||
            widget(node, "system_prompt_source")?.value !== "bundled_library") return;
        node.__songModelDrafts ??= {};
        node.__songModelDrafts[oldFile] = oldText;
        file.value = next;
        text.value = node.__songModelDrafts[next] ?? payload.text;
        node.graph?.setDirtyCanvas?.(true, true);
    } catch (error) {
        console.warn("Song model template:", error);
    }
}

app.registerExtension({
    name: "music_toolkit.song_model",
    nodeCreated(node) {
        if (!["MiniMaxMusicModelProfile", "MusicProductionControl"].includes(node.comfyClass ?? node.type)) return;
        const w = widget(node, "model");
        if (!w) return;
        const previous = w.callback;
        w.callback = function (...args) {
            const result = previous?.apply(this, args);
            for (const target of node.graph?._nodes || []) {
                if (connectedModel(target)) syncPrompt(target);
            }
            return result;
        };
    },
    async afterConfigureGraph() {
        for (const node of app.graph?._nodes || []) {
            if (connectedModel(node)) await syncPrompt(node);
        }
    },
});
