import { app } from "../../scripts/app.js";
import { api } from "../../scripts/api.js";

const NODE_TYPES = new Set(["MiniMaxLLMTemplateV16"]);
const PLACEHOLDER = "<select a prompt>";

function widget(node, name) {
    return node.widgets?.find((w) => w.name === name);
}

function nodeClass(node) {
    return node.comfyClass ?? node.type ?? node.constructor?.type;
}

function setComboValues(w, values) {
    if (!w) return;
    const normalized = [PLACEHOLDER, ...values.filter((v) => v && v !== PLACEHOLDER)];
    w.options = w.options || {};
    w.options.values = normalized;
    if (!normalized.includes(w.value)) w.value = PLACEHOLDER;
}

function markDirty(node) {
    node.setDirtyCanvas?.(true, true);
    node.graph?.setDirtyCanvas?.(true, true);
}

async function fetchPromptFiles(kind, source, directory) {
    if (source === "manual") return [];
    const params = new URLSearchParams({ kind, source, directory: directory || "" });
    const response = await api.fetchApi(`/minimax_music_toolkit/prompt_files?${params.toString()}`);
    let payload = {};
    try {
        payload = await response.json();
    } catch (_) {
        throw new Error(`Prompt library returned HTTP ${response.status}`);
    }
    if (!response.ok || !payload.ok) {
        throw new Error(payload.error || `Prompt library returned HTTP ${response.status}`);
    }
    return Array.isArray(payload.files) ? payload.files : [];
}

async function refreshKind(node, kind) {
    const source = widget(node, `${kind}_prompt_source`)?.value ?? "manual";
    const directory = widget(node, `${kind}_prompt_directory`)?.value ?? "";
    const fileWidget = widget(node, `${kind}_prompt_file`);
    if (!fileWidget) return;

    if (source === "manual") {
        setComboValues(fileWidget, []);
        fileWidget.value = PLACEHOLDER;
        markDirty(node);
        return;
    }

    try {
        const files = await fetchPromptFiles(kind, source, directory);
        const oldValue = fileWidget.value;
        setComboValues(fileWidget, files);
        if (files.includes(oldValue)) fileWidget.value = oldValue;
        else if (files.length === 1) fileWidget.value = files[0];
        node.__minimaxPromptLibraryError = null;
    } catch (error) {
        console.warn(`[MiniMax Music Production Toolkit] Could not refresh ${kind} prompt library:`, error);
        setComboValues(fileWidget, []);
        node.__minimaxPromptLibraryError = String(error?.message || error);
    }
    markDirty(node);
}

async function refreshBoth(node) {
    await Promise.all([refreshKind(node, "user"), refreshKind(node, "system")]);
}

function chainCallback(w, callback) {
    if (!w || w.__minimaxPromptLibraryCallbackInstalled) return;
    const original = w.callback;
    w.callback = function (...args) {
        const result = original?.apply(this, args);
        Promise.resolve(callback()).catch((error) => console.warn(error));
        return result;
    };
    w.__minimaxPromptLibraryCallbackInstalled = true;
}

function attach(node) {
    if (!NODE_TYPES.has(nodeClass(node)) || node.__minimaxPromptLibraryInstalled) return;
    node.__minimaxPromptLibraryInstalled = true;

    for (const kind of ["user", "system"]) {
        chainCallback(widget(node, `${kind}_prompt_source`), () => refreshKind(node, kind));
        chainCallback(widget(node, `${kind}_prompt_directory`), () => refreshKind(node, kind));
    }

    // A manual refresh button is useful after adding/deleting prompt files while
    // ComfyUI is already running.  It does not become part of the execution input.
    node.addWidget?.("button", "Refresh prompt lists", null, () => refreshBoth(node));
    queueMicrotask(() => refreshBoth(node));
}

app.registerExtension({
    name: "minimax_music_production_toolkit.prompt_library_v1",
    nodeCreated(node) {
        attach(node);
    },
    loadedGraphNode(node) {
        attach(node);
        queueMicrotask(() => refreshBoth(node));
    },
});
