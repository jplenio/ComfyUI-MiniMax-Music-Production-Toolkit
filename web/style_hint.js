// Style hint node: the same prompt-file dropdown as the structured prompt node.
//
// The two nodes must not drift apart, so the option building, the indent labels
// and the text applier come from prompt_ui_utils.js - the shared module the
// structured-prompt extension uses too. Only the node's own reaction differs: a
// selected file is copied into `style_text` (the structured-prompt node copies it
// into description_override and its fields).
import { app } from "../../scripts/app.js";
import { fetchPromptFiles, fetchPromptText } from "./prompt_api.js";
import {
    CUSTOM,
    DIRECTORY_MARKER_SUFFIX,
    PLACEHOLDER,
    applyTextWidget,
    beginRequest,
    buildGroupedFileOptions,
    chainCallback,
    fileOptionLabel,
    isCurrentRequest,
    markDirty,
    readSelection,
    sameSelection,
    scheduleInit,
    setComboValues,
    widgetByName as widget,
} from "./prompt_ui_utils.js";

const NODE_TYPES = new Set(["MiniMaxStyleHint"]);
const TEXT_WIDGET = "style_text";

function nodeClass(node) {
    return node.comfyClass ?? node.type ?? node.constructor?.type;
}

/** Fill the prompt-file dropdown from the library, grouped and indented. */
async function refreshFiles(node) {
    const selection = readSelection(node, "user");
    const fileWidget = widget(node, "user_prompt_file");
    if (!fileWidget) return;
    const token = beginRequest(node, "files:user");

    if (selection.source === "manual") {
        setComboValues(fileWidget, [], PLACEHOLDER);
        fileWidget.value = PLACEHOLDER;
        markDirty(node);
        return;
    }

    try {
        const files = await fetchPromptFiles("user", selection.source, selection.directory);
        if (!isCurrentRequest(token)) return;
        const oldValue = fileWidget.value;
        fileWidget.options = fileWidget.options || {};
        fileWidget.options.values = buildGroupedFileOptions(files, true);
        fileWidget.options.getOptionLabel = fileOptionLabel;
        if (files.includes(oldValue)) fileWidget.value = oldValue;
        else if (oldValue === CUSTOM) fileWidget.value = CUSTOM;
        else if (files.length === 1) fileWidget.value = files[0];
        else fileWidget.value = PLACEHOLDER;
        markDirty(node);
    } catch (error) {
        if (!isCurrentRequest(token)) return;
        console.warn(`[Music Production Toolkit] Could not refresh the style-hint library:`, error);
        setComboValues(fileWidget, [], PLACEHOLDER);
        markDirty(node);
    }
}

/**
 * Copy the selected file's text into `style_text`.
 *
 * ``overwrite`` follows an explicit selection; ``restore`` only fills an empty
 * field so a saved edit survives reopening the workflow - the same contract the
 * structured-prompt node uses for its description.
 */
async function applyHintText(node, file, { mode = "overwrite" } = {}) {
    if (!file || file === PLACEHOLDER || file === CUSTOM) return;
    const selection = readSelection(node, "user");
    if (selection.source === "manual") return;
    const token = beginRequest(node, "hintText");

    let text;
    try {
        text = await fetchPromptText("user", selection.source, selection.directory, file);
    } catch (error) {
        if (isCurrentRequest(token)) {
            console.warn(`[Music Production Toolkit] Could not load the style hint text:`, error);
        }
        return;
    }
    if (!isCurrentRequest(token)) return;
    if (!sameSelection(selection, readSelection(node, "user"))) return;
    if (applyTextWidget(node, TEXT_WIDGET, text, { onlyIfEmpty: mode === "restore" })) markDirty(node);
}

function attach(node) {
    if (!NODE_TYPES.has(nodeClass(node)) || node.__minimaxStyleHintInstalled) return;
    node.__minimaxStyleHintInstalled = true;

    const fileWidget = widget(node, "user_prompt_file");
    if (fileWidget) {
        node.__minimaxLastStyleHintFile = fileWidget.value;
        chainCallback(fileWidget, () => {
            const value = fileWidget.value;
            if (typeof value === "string" && value.endsWith(DIRECTORY_MARKER_SUFFIX)) {
                // A directory label is a display marker: keep the real selection.
                fileWidget.value = node.__minimaxLastStyleHintFile ?? PLACEHOLDER;
                markDirty(node);
                return;
            }
            node.__minimaxLastStyleHintFile = value;
            applyHintText(node, value);
        });
    }
    chainCallback(widget(node, "user_prompt_source"), async () => {
        await refreshFiles(node);
        const selected = widget(node, "user_prompt_file")?.value;
        if (selected && selected !== PLACEHOLDER) await applyHintText(node, selected);
    });
    chainCallback(widget(node, "user_prompt_directory"), () => refreshFiles(node));
}

function initialize(node, mode) {
    scheduleInit(node, mode, async () => {
        await refreshFiles(node);
        const selected = widget(node, "user_prompt_file")?.value;
        if (selected && selected !== PLACEHOLDER && selected !== CUSTOM) {
            await applyHintText(node, selected, { mode: mode === "create" ? "overwrite" : "restore" });
        }
    });
}

app.registerExtension({
    name: "minimax_music_production_toolkit.style_hint_v1",
    nodeCreated(node) {
        attach(node);
        initialize(node, "create");
    },
    loadedGraphNode(node) {
        attach(node);
        initialize(node, "restore");
    },
});
