import { app } from "../../scripts/app.js";
import { api } from "../../scripts/api.js";

// Structured Song Prompt (MiniMaxStructuredPromptV20): refreshes the prompt
// file dropdown, prefills the structured fields (Genre, Tempo, Key, Lyrics,
// Language, Voice, Theme, Length) from the selected prompt file's optional
// metadata block, and copies the file's body text (the "further description")
// into the description_override field, which is authoritative from then on.
//
// The user can always override any prefilled value afterwards; "custom" means
// the field is left out of the LLM prompt.  In the prompt-file dropdown,
// "custom" is the first real choice and selects the free mode: no file is
// loaded and the structured fields are left exactly as the user set them.
// Loading a workflow never wipes widget values: on graph load only an empty
// description_override is filled, so serialized user edits survive.

const NODE_TYPES = new Set(["MiniMaxStructuredPromptV20"]);
const PLACEHOLDER = "<select a prompt>";
const CUSTOM = "custom";
const STRUCTURED_FIELDS = ["genre", "tempo", "key", "lyrics", "language", "voice", "theme", "length"];

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

function markDirty(node) {
    node.setDirtyCanvas?.(true, true);
    node.graph?.setDirtyCanvas?.(true, true);
}

async function fetchPromptFiles(source, directory) {
    if (source === "manual") return [];
    const params = new URLSearchParams({ kind: "user", source, directory: directory || "" });
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

async function refreshFiles(node) {
    const source = widget(node, "user_prompt_source")?.value ?? "bundled_library";
    const directory = widget(node, "user_prompt_directory")?.value ?? "";
    const fileWidget = widget(node, "user_prompt_file");
    if (!fileWidget) return;

    if (source === "manual") {
        setComboValues(fileWidget, [], PLACEHOLDER);
        fileWidget.value = PLACEHOLDER;
        markDirty(node);
        return;
    }

    try {
        const files = await fetchPromptFiles(source, directory);
        const oldValue = fileWidget.value;
        // "custom" is always the first real choice and selects the free mode:
        // no prompt file is loaded and the structured fields stay untouched.
        setComboValues(fileWidget, [CUSTOM, ...files], PLACEHOLDER);
        if (files.includes(oldValue)) fileWidget.value = oldValue;
        else if (oldValue === CUSTOM) fileWidget.value = CUSTOM;
        else if (files.length === 1) fileWidget.value = files[0];
        node.__minimaxStructuredPromptError = null;
    } catch (error) {
        console.warn(`[MiniMax Music Production Toolkit] Could not refresh structured prompt library:`, error);
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
    // "custom" is the free mode: it behaves like no file selected, except it
    // deliberately does NOT clear anything - the user composes the fields freely.
    if (!file || file === PLACEHOLDER || file === CUSTOM || source === "manual") {
        if (file === CUSTOM) {
            // Free mode: no file is loaded, nothing is cleared.  Keep the
            // structured option lists fresh so the user can still pick from
            // the curated vocabulary while filling the fields by hand.
            node.__minimaxStructuredPromptError = null;
            await refreshOptionLists(node);
            return;
        }
        // The user unselected the prompt file: clear the file-derived state.
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
            // On a user-driven selection the body text is copied in; on a graph
            // load it only fills an empty field so user edits survive.
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

async function refreshOptionLists(node) {
    // Refresh the option lists of the structured combos (curated vocabulary
    // plus values found in the library).  The current selection is preserved
    // when still available.
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

async function saveCustomPrompt(node) {
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
        "Name of the custom prompt file (saved into _custom/):",
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
        await refreshFiles(node);
        if (fileWidget && payload.file) {
            fileWidget.value = payload.file;
        }
        markDirty(node);
    } catch (error) {
        console.warn("[MiniMax Music Production Toolkit] Could not save custom prompt:", error);
        alert("Could not save custom prompt: " + (error?.message || error));
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

    const fileWidget = widget(node, "user_prompt_file");
    if (fileWidget) {
        chainCallback(fileWidget, () => prefillStructuredFields(node, fileWidget.value));
    }
    chainCallback(widget(node, "user_prompt_source"), async () => {
        await refreshFiles(node);
        const selected = widget(node, "user_prompt_file")?.value;
        if (selected && selected !== PLACEHOLDER) await prefillStructuredFields(node, selected);
        else await refreshOptionLists(node);
    });
    chainCallback(widget(node, "user_prompt_directory"), () => refreshFiles(node));

    // A manual refresh button is useful after adding/deleting prompt files while
    // ComfyUI is already running.  It does not become part of the execution input.
    node.addWidget?.("button", "Refresh prompt lists", null, async () => {
        await refreshFiles(node);
        await refreshOptionLists(node);
        const selected = widget(node, "user_prompt_file")?.value;
        if (selected && selected !== PLACEHOLDER) await prefillStructuredFields(node, selected);
    });
    // Save the current field values + description as a custom prompt file in
    // the prompt library's _custom/ folder (asks for a file name).
    node.addWidget?.("button", "Save as custom prompt", null, () => {
        saveCustomPrompt(node).catch((error) => console.warn(error));
    });
    queueMicrotask(async () => {
        await refreshFiles(node);
        await refreshOptionLists(node);
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
            await refreshFiles(node);
            await refreshOptionLists(node);
            // Fill the description field from the selected file only when it is
            // still empty; never overwrite serialized user edits on load.
            const selected = widget(node, "user_prompt_file")?.value;
            if (selected && selected !== PLACEHOLDER) {
                await prefillStructuredFields(node, selected, { onlyDescription: true });
            }
        });
    },
});
