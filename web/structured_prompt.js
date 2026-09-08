import { app } from "../../scripts/app.js";
import { api } from "../../scripts/api.js";

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
const PLACEHOLDER = "<select a prompt>";
const CUSTOM = "custom";
const STRUCTURED_FIELDS = ["genre", "tempo", "meter", "key", "lyrics", "language", "voice", "theme", "length"];
// Directory group labels in the prompt-file dropdown end with this suffix and
// carry no file value; selecting one keeps the previous real selection.
const DIRECTORY_MARKER_SUFFIX = "/";

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

function widget(node, name) {
    return node.widgets?.find((w) => w.name === name);
}

function nodeClass(node) {
    return node.comfyClass ?? node.type ?? node.constructor?.type;
}

function setComboValues(w, values, firstValue = CUSTOM) {
    if (!w) return;
    const normalized = [firstValue, ...values.filter((v) => v && v !== firstValue)];
    w.options = w.options || {};
    w.options.values = normalized;
    if (!normalized.includes(w.value)) w.value = firstValue;
}

function buildGroupedFileOptions(files, includeCustom = true) {
    // files arrive sorted by relative path, which groups them per directory.
    // The dropdown shows each directory once (first), then its files indented
    // beneath it.  Directory labels are display-only markers.  "custom" is only
    // meaningful for user prompts (free mode); system prompts never offer it.
    const entries = includeCustom ? [PLACEHOLDER, CUSTOM] : [PLACEHOLDER];
    let currentDir = null;
    for (const file of files) {
        const slash = file.indexOf("/");
        const dir = slash >= 0 ? file.slice(0, slash) : "";
        if (slash >= 0 && dir !== currentDir) {
            entries.push(dir + DIRECTORY_MARKER_SUFFIX);
            currentDir = dir;
        }
        entries.push(file);
    }
    return entries;
}

function fileOptionLabel(value) {
    if (typeof value !== "string") return value;
    if (value === PLACEHOLDER || value === CUSTOM) return value;
    if (value.endsWith(DIRECTORY_MARKER_SUFFIX)) return value;
    const slash = value.indexOf("/");
    // Indent files under their directory label (non-breaking spaces survive
    // HTML rendering; the value itself stays the resolvable relative path).
    return slash >= 0 ? "\u00A0\u00A0\u00A0\u00A0" + value.slice(slash + 1) : value;
}

function markDirty(node) {
    node.setDirtyCanvas?.(true, true);
    node.graph?.setDirtyCanvas?.(true, true);
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

async function fetchPromptMetadata(source, directory, file) {
    const params = new URLSearchParams({ source, directory: directory || "", file });
    const response = await api.fetchApi(`/minimax_music_toolkit/prompt_metadata?${params.toString()}`);
    let payload = {};
    try {
        payload = await response.json();
    } catch (_) {
        throw new Error(`Prompt metadata returned HTTP ${response.status}`);
    }
    if (!response.ok || !payload.ok) {
        throw new Error(payload.error || `Prompt metadata returned HTTP ${response.status}`);
    }
    return payload;
}

async function fetchPromptText(kind, source, directory, file) {
    const params = new URLSearchParams({ kind, source, directory: directory || "", file });
    const response = await api.fetchApi(`/minimax_music_toolkit/prompt_text?${params.toString()}`);
    let payload = {};
    try {
        payload = await response.json();
    } catch (_) {
        throw new Error(`Prompt text returned HTTP ${response.status}`);
    }
    if (!response.ok || !payload.ok) {
        throw new Error(payload.error || `Prompt text returned HTTP ${response.status}`);
    }
    return typeof payload.text === "string" ? payload.text : "";
}

async function refreshFiles(node, kind) {
    const source = widget(node, `${kind}_prompt_source`)?.value ?? "manual";
    const directory = widget(node, `${kind}_prompt_directory`)?.value ?? "";
    const fileWidget = widget(node, `${kind}_prompt_file`);
    if (!fileWidget) return;

    if (source === "manual") {
        setComboValues(fileWidget, [], PLACEHOLDER);
        fileWidget.value = PLACEHOLDER;
        markDirty(node);
        return;
    }

    try {
        const files = await fetchPromptFiles(kind, source, directory);
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
        console.warn(`[MiniMax Music Production Toolkit] Could not refresh ${kind} prompt library:`, error);
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
//   "overwrite"     - user changed the prompt file: fields and description
//                     are (re)filled from the selected file.
//   onlyDescription - graph load: structured fields keep their serialized
//                     values, only an empty description_override is filled.
async function prefillStructuredFields(node, file, { onlyDescription = false } = {}) {
    const source = widget(node, "user_prompt_source")?.value ?? "bundled_library";
    const directory = widget(node, "user_prompt_directory")?.value ?? "";
    if (!file || file === PLACEHOLDER || file === CUSTOM || source === "manual") {
        if (file === CUSTOM) {
            node.__minimaxStructuredPromptError = null;
            await refreshOptionLists(node);
            return;
        }
        resetStructuredFields(node, { clearDescription: true });
        markDirty(node);
        return;
    }
    try {
        const payload = await fetchPromptMetadata(source, directory, file);
        const fields = payload.fields || {};
        if (!onlyDescription) {
            for (const field of STRUCTURED_FIELDS) {
                const w = widget(node, field);
                if (!w) continue;
                const value = fields[field];
                if (value && value !== CUSTOM) w.value = value;
                else w.value = CUSTOM;
            }
        }
        const descriptionWidget = widget(node, "description_override");
        if (descriptionWidget) {
            const description = typeof payload.description === "string" ? payload.description : "";
            if (!onlyDescription || !(descriptionWidget.value || "").trim()) {
                descriptionWidget.value = description;
            }
        }
        node.__minimaxStructuredPromptError = null;
    } catch (error) {
        console.warn(`[MiniMax Music Production Toolkit] Could not prefill structured prompt fields:`, error);
        node.__minimaxStructuredPromptError = String(error?.message || error);
    }
    markDirty(node);
}

async function prefillSystemPrompt(node, file) {
    const source = widget(node, "system_prompt_source")?.value ?? "bundled_library";
    const directory = widget(node, "system_prompt_directory")?.value ?? "";
    const promptWidget = widget(node, "system_prompt");
    if (!promptWidget || !file || file === PLACEHOLDER || file === CUSTOM || source === "manual") {
        return;
    }
    try {
        const text = await fetchPromptText("system", source, directory, file);
        promptWidget.value = text;
        node.__minimaxStructuredPromptError = null;
    } catch (error) {
        console.warn(`[MiniMax Music Production Toolkit] Could not load system prompt text:`, error);
        node.__minimaxStructuredPromptError = String(error?.message || error);
    }
    markDirty(node);
}

async function refreshOptionLists(node) {
    const source = widget(node, "user_prompt_source")?.value ?? "bundled_library";
    const directory = widget(node, "user_prompt_directory")?.value ?? "";
    if (source === "manual") return;
    try {
        const params = new URLSearchParams({ source, directory: directory || "" });
        const response = await api.fetchApi(`/minimax_music_toolkit/prompt_metadata?${params.toString()}&file=`);
        const payload = await response.json();
        if (!response.ok || !payload.ok) return;
        const unique = payload.unique_values || {};
        for (const field of STRUCTURED_FIELDS) {
            const w = widget(node, field);
            const values = unique[field];
            if (w && Array.isArray(values)) setComboValues(w, values);
        }
        markDirty(node);
    } catch (error) {
        console.warn(`[MiniMax Music Production Toolkit] Could not refresh structured options:`, error);
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
        console.warn("[MiniMax Music Production Toolkit] Could not save custom user prompt:", error);
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
        console.warn("[MiniMax Music Production Toolkit] Could not save custom system prompt:", error);
        alert("Could not save custom system prompt: " + (error?.message || error));
    }
}

async function refreshAll(node) {
    await Promise.all([refreshFiles(node, "user"), refreshFiles(node, "system")]);
    await refreshOptionLists(node);
    const selectedUser = widget(node, "user_prompt_file")?.value;
    if (selectedUser && selectedUser !== PLACEHOLDER) {
        await prefillStructuredFields(node, selectedUser);
    }
    const selectedSystem = widget(node, "system_prompt_file")?.value;
    if (selectedSystem && selectedSystem !== PLACEHOLDER) {
        await prefillSystemPrompt(node, selectedSystem);
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
    node.addWidget?.("button", "Save as custom user prompt", null, () => {
        saveCustomUserPrompt(node).catch((error) => console.warn(error));
    });
    // Save the current system_prompt text as a custom system prompt.
    node.addWidget?.("button", "Save as custom system prompt", null, () => {
        saveCustomSystemPrompt(node).catch((error) => console.warn(error));
    });
    // Refresh both user and system prompt libraries.
    node.addWidget?.("button", "Refresh prompt lists", null, async () => {
        await refreshAll(node);
    });

    orderWidgets(node, WIDGET_ORDER);
    queueMicrotask(async () => {
        await refreshAll(node);
    });
}

app.registerExtension({
    name: "minimax_music_production_toolkit.structured_prompt_v1",
    nodeCreated(node) {
        attach(node);
    },
    loadedGraphNode(node) {
        attach(node);
        queueMicrotask(async () => {
            await refreshAll(node);
            // Fill the description and system prompt fields from the selected
            // files only when they are still empty; never overwrite serialized
            // user edits on load.
            const selectedUser = widget(node, "user_prompt_file")?.value;
            if (selectedUser && selectedUser !== PLACEHOLDER) {
                await prefillStructuredFields(node, selectedUser, { onlyDescription: true });
            }
            const promptWidget = widget(node, "system_prompt");
            if (promptWidget && !(promptWidget.value || "").trim()) {
                const selectedSystem = widget(node, "system_prompt_file")?.value;
                if (selectedSystem && selectedSystem !== PLACEHOLDER) {
                    await prefillSystemPrompt(node, selectedSystem);
                }
            }
        });
    },
});
