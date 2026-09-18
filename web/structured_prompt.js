import { app } from "../../scripts/app.js";
import { api } from "../../scripts/api.js";
import { fetchPromptFiles, fetchPromptMetadata, fetchPromptText } from "./prompt_api.js";
import {
    CUSTOM,
    DIRECTORY_MARKER_SUFFIX,
    PLACEHOLDER,
    STRUCTURED_FIELDS,
    applyDescription,
    applyStructuredFields,
    applySystemPromptText,
    applyTooltip,
    beginRequest,
    buildGroupedFileOptions,
    fileOptionLabel,
    isCurrentRequest,
    markDirty,
    readSelection,
    runGuardedMetadataPrefill,
    runGuardedSystemPrefill,
    sameSelection,
    scheduleInit,
    setComboValues,
    widgetByName,
} from "./prompt_ui_utils.js";

// Structured Song Prompt (MiniMaxStructuredPromptV20): refreshes the user and
// system prompt-file dropdowns, prefills the structured fields (Genre, Tempo,
// Time signature, Key, Lyrics, Language, Voice, Theme, Length) from the
// selected user prompt file's optional metadata block, and copies the file's
// body text (the "further description") into the description_override field,
// which is authoritative from then on.
//
// The system prompt works the same way: selecting a system prompt file copies
// its text into the editable system_prompt field, which is authoritative from
// then on (so the selection can still be tweaked by hand).
//
// The node body is split into a "User Prompt" and a "System Prompt" section by
// two heading buttons; the save/refresh buttons are placed accordingly.

const NODE_TYPES = new Set(["MiniMaxStructuredPromptV20"]);
// PLACEHOLDER / CUSTOM / STRUCTURED_FIELDS / markDirty come from
// prompt_ui_utils.js so the extension and its Node tests share one definition.
// The prompt-file option building and its indent labels come from the same shared
// module, so this dropdown and the style-hint node's cannot drift apart.

// Canonical visual/serialization order of every widget (inputs + buttons +
// section headings).  It must match the Python INPUT_TYPES order so positional
// widgets_values stay aligned.
const WIDGET_ORDER = [
    "USER PROMPT",
    "user_prompt_source", "user_prompt_directory", "user_prompt_file",
    ...STRUCTURED_FIELDS,
    "description_override",
    "Save as custom user prompt",
    "SYSTEM PROMPT",
    "system_prompt_source", "system_prompt_directory", "system_prompt_file",
    "source_name_override",
    "system_prompt",
    "Save as custom system prompt",
    "Refresh prompt lists",
];

const widget = widgetByName;

function nodeClass(node) {
    return node.comfyClass ?? node.type ?? node.constructor?.type;
}

function injectHeadingStyle() {
    if (document.getElementById("minimax-structured-prompt-heading-style")) return;
    const style = document.createElement("style");
    style.id = "minimax-structured-prompt-heading-style";
    // The headings are button widgets only so they stay in the widget order;
    // visually they should look like section headers, not dark input boxes.
    style.textContent = `
        button[aria-label="USER PROMPT"],
        button[aria-label="SYSTEM PROMPT"] {
            background: transparent !important;
            box-shadow: none !important;
            border: none !important;
            color: var(--text-color, var(--fg-color, #d8d4c8)) !important;
            font-weight: 700 !important;
            letter-spacing: 0.03em;
            cursor: default;
        }
    `;
    document.head.appendChild(style);
}

function orderWidgets(node, desiredNames) {
    const widgets = node.widgets;
    if (!widgets || !Array.isArray(widgets)) return;
    const byName = new Map(widgets.map((w) => [w.name, w]));
    const ordered = [];
    for (const name of desiredNames) {
        const w = byName.get(name);
        if (w) ordered.push(w);
    }
    // Keep any unexpected widgets at the end rather than dropping them.
    for (const w of widgets) {
        if (!desiredNames.includes(w.name)) ordered.push(w);
    }
    widgets.length = 0;
    widgets.push(...ordered);
}

async function refreshFiles(node, kind) {
    const selection = readSelection(node, kind);
    const fileWidget = widget(node, `${kind}_prompt_file`);
    if (!fileWidget) return;
    const token = beginRequest(node, `files:${kind}`);

    if (selection.source === "manual") {
        setComboValues(fileWidget, [], PLACEHOLDER);
        fileWidget.value = PLACEHOLDER;
        markDirty(node);
        return;
    }

    try {
        const files = await fetchPromptFiles(kind, selection.source, selection.directory);
        if (!isCurrentRequest(token)) return;
        const oldValue = fileWidget.value;
        const grouped = buildGroupedFileOptions(files, kind === "user");
        fileWidget.options = fileWidget.options || {};
        fileWidget.options.values = grouped;
        fileWidget.options.getOptionLabel = fileOptionLabel;
        if (files.includes(oldValue)) fileWidget.value = oldValue;
        else if (oldValue === CUSTOM && kind === "user") fileWidget.value = CUSTOM;
        else if (files.length === 1) fileWidget.value = files[0];
        else fileWidget.value = PLACEHOLDER;
        node.__minimaxStructuredPromptError = null;
    } catch (error) {
        if (!isCurrentRequest(token)) return;
        console.warn(`[Music Production Toolkit] Could not refresh ${kind} prompt library:`, error);
        setComboValues(fileWidget, [], PLACEHOLDER);
        node.__minimaxStructuredPromptError = String(error?.message || error);
    }
    markDirty(node);
}

function resetStructuredFields(node, { clearDescription = false } = {}) {
    for (const field of STRUCTURED_FIELDS) {
        const w = widget(node, field);
        if (w) w.value = CUSTOM;
    }
    if (clearDescription) {
        const w = widget(node, "description_override");
        if (w) w.value = "";
    }
}

// mode:
//   "overwrite"  - user changed the prompt file: fields and description
//                  are (re)filled from the selected file.
//   "restore"    - graph load: structured fields keep their serialized
//                  values, only an empty description_override is filled.
//
// The request carries a selection snapshot; a response that arrives after the
// selection changed is discarded instead of overwriting the newer state.
async function prefillStructuredFields(node, file, { mode = "overwrite" } = {}) {
    if (file === CUSTOM) {
        node.__minimaxStructuredPromptError = null;
        await refreshOptionLists(node);
        return;
    }
    if (!file || file === PLACEHOLDER || readSelection(node, "user").source === "manual") {
        resetStructuredFields(node, { clearDescription: true });
        markDirty(node);
        return;
    }
    const result = await runGuardedMetadataPrefill(
        node,
        file,
        (selection) => fetchPromptMetadata(selection.source, selection.directory, file),
        { mode },
    );
    if (result.status === "error") {
        console.warn(`[Music Production Toolkit] Could not prefill structured prompt fields:`, result.error);
        node.__minimaxStructuredPromptError = String(result.error?.message || result.error);
    } else if (result.status === "applied") {
        node.__minimaxStructuredPromptError = null;
        markDirty(node);
    }
}

async function prefillSystemPrompt(node, file, { mode = "overwrite" } = {}) {
    if (!file || file === PLACEHOLDER || file === CUSTOM) return;
    const result = await runGuardedSystemPrefill(
        node,
        file,
        (selection) => fetchPromptText("system", selection.source, selection.directory, file),
        { mode },
    );
    if (result.status === "error") {
        console.warn(`[Music Production Toolkit] Could not load system prompt text:`, result.error);
        node.__minimaxStructuredPromptError = String(result.error?.message || result.error);
    } else if (result.status === "applied") {
        node.__minimaxStructuredPromptError = null;
        markDirty(node);
    }
}

async function refreshOptionLists(node) {
    const selection = readSelection(node, "user");
    if (selection.source === "manual") return;
    const token = beginRequest(node, "userOptions");
    try {
        const params = new URLSearchParams({ source: selection.source, directory: selection.directory || "" });
        const response = await api.fetchApi(`/minimax_music_toolkit/prompt_metadata?${params.toString()}&file=`);
        const payload = await response.json();
        if (!isCurrentRequest(token)) return;
        if (!response.ok || !payload.ok) return;
        const unique = payload.unique_values || {};
        for (const field of STRUCTURED_FIELDS) {
            const w = widget(node, field);
            const values = unique[field];
            if (w && Array.isArray(values)) setComboValues(w, values);
        }
        markDirty(node);
    } catch (error) {
        if (!isCurrentRequest(token)) return;
        console.warn(`[Music Production Toolkit] Could not refresh structured options:`, error);
    }
}

/**
 * Refresh the two prompt-file dropdowns and the structured option lists.
 *
 * Never touches field or description values - a list refresh must not
 * overwrite edits.  Used by the "Refresh prompt lists" button.
 */
async function refreshLibraryLists(node) {
    await Promise.all([refreshFiles(node, "user"), refreshFiles(node, "system")]);
    await refreshOptionLists(node);
}

/**
 * Node creation defaults: a brand-new node has no serialized state, so the
 * selected prompt files may seed every field.
 */
async function applyCreateDefaults(node) {
    await refreshLibraryLists(node);
    const selectedUser = widget(node, "user_prompt_file")?.value;
    if (selectedUser && selectedUser !== PLACEHOLDER && selectedUser !== CUSTOM) {
        await prefillStructuredFields(node, selectedUser, { mode: "overwrite" });
    }
    const selectedSystem = widget(node, "system_prompt_file")?.value;
    if (selectedSystem && selectedSystem !== PLACEHOLDER && selectedSystem !== CUSTOM) {
        await prefillSystemPrompt(node, selectedSystem, { mode: "overwrite" });
    }
}

/**
 * Graph restore: serialized widget values are authoritative.  Only refresh
 * the lists and fill values that are still empty (description text, system
 * prompt text) - never overwrite a saved edit.
 */
async function restoreSavedValues(node) {
    await refreshLibraryLists(node);
    const selectedUser = widget(node, "user_prompt_file")?.value;
    if (selectedUser && selectedUser !== PLACEHOLDER && selectedUser !== CUSTOM) {
        await prefillStructuredFields(node, selectedUser, { mode: "restore" });
    }
    const promptWidget = widget(node, "system_prompt");
    if (promptWidget && !(promptWidget.value || "").trim()) {
        const selectedSystem = widget(node, "system_prompt_file")?.value;
        if (selectedSystem && selectedSystem !== PLACEHOLDER && selectedSystem !== CUSTOM) {
            await prefillSystemPrompt(node, selectedSystem, { mode: "restore" });
        }
    }
}

async function saveCustomUserPrompt(node) {
    // Save the current widget values as a prompt file in the prompt library's
    // _custom/ folder.  Manual mode saves into the bundled library and then
    // switches the node to it so the new file is immediately usable.
    const sourceWidget = widget(node, "user_prompt_source");
    let source = sourceWidget?.value ?? "bundled_library";
    const wasManual = source === "manual";
    if (wasManual) source = "bundled_library";
    const directory = widget(node, "user_prompt_directory")?.value ?? "";
    const fileWidget = widget(node, "user_prompt_file");
    const currentFile = fileWidget?.value;
    const suggested = currentFile && currentFile !== PLACEHOLDER
        ? currentFile.replace(/\.(txt|md|prompt)$/i, "") + "-custom"
        : "custom";

    const name = window.prompt?.(
        "Name of the custom user prompt file (saved into _custom/):",
        suggested
    );
    if (name === null || name === undefined) return;

    const fields = {};
    for (const field of STRUCTURED_FIELDS) {
        fields[field] = widget(node, field)?.value ?? CUSTOM;
    }
    const description = widget(node, "description_override")?.value ?? "";

    try {
        const response = await api.fetchApi("/minimax_music_toolkit/save_prompt", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
                source, directory, file: name, fields, description, overwrite: false,
            }),
        });
        const payload = await response.json();
        if (!response.ok || !payload.ok) {
            throw new Error(payload.error || `save_prompt returned HTTP ${response.status}`);
        }
        if (wasManual && sourceWidget) {
            sourceWidget.value = "bundled_library";
            sourceWidget.callback?.(sourceWidget.value);
        }
        await refreshFiles(node, "user");
        if (fileWidget && payload.file) {
            fileWidget.value = payload.file;
        }
        markDirty(node);
    } catch (error) {
        console.warn("[Music Production Toolkit] Could not save custom user prompt:", error);
        alert("Could not save custom user prompt: " + (error?.message || error));
    }
}

async function saveCustomSystemPrompt(node) {
    // Save the current system_prompt text as a plain system prompt file in the
    // system library's _custom/ folder.
    const sourceWidget = widget(node, "system_prompt_source");
    let source = sourceWidget?.value ?? "bundled_library";
    const wasManual = source === "manual";
    if (wasManual) source = "bundled_library";
    const directory = widget(node, "system_prompt_directory")?.value ?? "";
    const fileWidget = widget(node, "system_prompt_file");
    const currentFile = fileWidget?.value;
    const suggested = currentFile && currentFile !== PLACEHOLDER
        ? currentFile.replace(/\.(txt|md|prompt)$/i, "") + "-custom"
        : "custom-system";

    const name = window.prompt?.(
        "Name of the custom system prompt file (saved into _custom/):",
        suggested
    );
    if (name === null || name === undefined) return;

    const text = widget(node, "system_prompt")?.value ?? "";

    try {
        const response = await api.fetchApi("/minimax_music_toolkit/save_system_prompt", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
                source, directory, file: name, text, overwrite: false,
            }),
        });
        const payload = await response.json();
        if (!response.ok || !payload.ok) {
            throw new Error(payload.error || `save_system_prompt returned HTTP ${response.status}`);
        }
        if (wasManual && sourceWidget) {
            sourceWidget.value = "bundled_library";
            sourceWidget.callback?.(sourceWidget.value);
        }
        await refreshFiles(node, "system");
        if (fileWidget && payload.file) {
            fileWidget.value = payload.file;
        }
        markDirty(node);
    } catch (error) {
        console.warn("[Music Production Toolkit] Could not save custom system prompt:", error);
        alert("Could not save custom system prompt: " + (error?.message || error));
    }
}

function chainCallback(w, callback) {
    if (!w || w.__minimaxStructuredPromptCallbackInstalled) return;
    const original = w.callback;
    w.callback = function (...args) {
        const result = original?.apply(this, args);
        Promise.resolve(callback()).catch((error) => console.warn(error));
        return result;
    };
    w.__minimaxStructuredPromptCallbackInstalled = true;
}

function attach(node) {
    if (!NODE_TYPES.has(nodeClass(node)) || node.__minimaxStructuredPromptInstalled) return;
    node.__minimaxStructuredPromptInstalled = true;

    injectHeadingStyle();

    const fileWidget = widget(node, "user_prompt_file");
    if (fileWidget) {
        node.__minimaxLastFileValue = fileWidget.value;
        chainCallback(fileWidget, () => {
            const value = fileWidget.value;
            if (typeof value === "string" && value.endsWith(DIRECTORY_MARKER_SUFFIX)) {
                fileWidget.value = node.__minimaxLastFileValue ?? PLACEHOLDER;
                markDirty(node);
                return;
            }
            node.__minimaxLastFileValue = value;
            prefillStructuredFields(node, value);
        });
    }
    chainCallback(widget(node, "user_prompt_source"), async () => {
        await refreshFiles(node, "user");
        const selected = widget(node, "user_prompt_file")?.value;
        if (selected && selected !== PLACEHOLDER) await prefillStructuredFields(node, selected);
        else await refreshOptionLists(node);
    });
    chainCallback(widget(node, "user_prompt_directory"), () => refreshFiles(node, "user"));

    const systemFileWidget = widget(node, "system_prompt_file");
    if (systemFileWidget) {
        node.__minimaxLastSystemFileValue = systemFileWidget.value;
        chainCallback(systemFileWidget, () => {
            const value = systemFileWidget.value;
            if (typeof value === "string" && value.endsWith(DIRECTORY_MARKER_SUFFIX)) {
                systemFileWidget.value = node.__minimaxLastSystemFileValue ?? PLACEHOLDER;
                markDirty(node);
                return;
            }
            node.__minimaxLastSystemFileValue = value;
            prefillSystemPrompt(node, value);
        });
    }
    chainCallback(widget(node, "system_prompt_source"), async () => {
        await refreshFiles(node, "system");
        const selected = widget(node, "system_prompt_file")?.value;
        if (selected && selected !== PLACEHOLDER) await prefillSystemPrompt(node, selected);
    });
    chainCallback(widget(node, "system_prompt_directory"), () => refreshFiles(node, "system"));

    // Section headings (display-only separators between User and System Prompt).
    // They are button widgets only so they participate in the widget order; the
    // label is set explicitly so the injected CSS can target them reliably and
    // render them as plain section headers instead of dark input boxes.
    const userHeading = node.addWidget?.("button", "USER PROMPT", null, () => {});
    if (userHeading) userHeading.label = "USER PROMPT";
    const systemHeading = node.addWidget?.("button", "SYSTEM PROMPT", null, () => {});
    if (systemHeading) systemHeading.label = "SYSTEM PROMPT";

    // Save the current field values + description as a custom user prompt.
    applyTooltip(node.addWidget?.("button", "Save as custom user prompt", null, () => {
        saveCustomUserPrompt(node).catch((error) => console.warn(error));
    }), "Writes the current field values and description into your own user-prompt file, so a template you like can be reused. It does not overwrite bundled prompts.");
    // Save the current system_prompt text as a custom system prompt.
    applyTooltip(node.addWidget?.("button", "Save as custom system prompt", null, () => {
        saveCustomSystemPrompt(node).catch((error) => console.warn(error));
    }), "Writes the current system-prompt text into your own system-prompt file. Use it to keep a template that produced good songs.");
    // Refresh both user and system prompt libraries (lists only - never
    // overwrites edited field or description values).
    applyTooltip(node.addWidget?.("button", "Refresh prompt lists", null, async () => {
        await refreshLibraryLists(node);
    }), "Re-reads the prompt directories so files you added outside ComfyUI appear in the lists. Edited field and description values are never overwritten.");

    orderWidgets(node, WIDGET_ORDER);
}

// Both hooks run while a graph is loaded; scheduleInit keeps exactly one of
// them, whichever fires last, so a reopened graph restores saved values and a
// freshly created node gets the create defaults.
function initialize(node, mode) {
    scheduleInit(node, mode, (resolved) => (
        resolved === "create" ? applyCreateDefaults(node) : restoreSavedValues(node)
    ));
}

app.registerExtension({
    name: "minimax_music_production_toolkit.structured_prompt_v1",
    nodeCreated(node) {
        attach(node);
        initialize(node, "create");
    },
    loadedGraphNode(node) {
        attach(node);
        initialize(node, "restore");
    },
});
