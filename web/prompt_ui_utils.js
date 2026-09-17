// Shared frontend helpers for the structured-prompt + prompt-library
// extensions.
//
// Two responsibilities:
//
//  * Request generation guards.  A library/file response that arrives after
//    the user changed the selection, the directory, the source or the field
//    text must never overwrite the newer state.  Each async operation takes a
//    token from beginRequest(); before applying its payload it checks
//    isCurrentRequest() and that the selection it was started for is still the
//    current one.
//
//  * Pure widget access/application helpers.  They import nothing from
//    ComfyUI, so the exact mutations can be unit tested with plain Node
//    (tests/test_structured_prompt_frontend.mjs).

export const PLACEHOLDER = "<select a prompt>";
export const CUSTOM = "custom";
export const STRUCTURED_FIELDS = [
    "genre", "tempo", "meter", "key", "lyrics", "language", "voice", "theme", "length",
];

/**
 * Attach help text to a widget or a DOM element as well as the UI supports it.
 *
 * LiteGraph widgets read ``tooltip`` (and ``options.tooltip``); DOM-backed
 * widgets and our own buttons also get the native ``title`` attribute, which is
 * what the browser renders during a hover.
 */
export function applyTooltip(target, text) {
    if (!target || !text) return target;
    if (typeof target.title === "string") target.title = text;
    if (target.inputEl) target.inputEl.title = text;
    if (target.element) target.element.title = text;
    target.tooltip = text;
    target.options = { ...(target.options || {}), tooltip: text };
    return target;
}

const REQUESTS = new WeakMap();

function registryFor(node) {
    let registry = REQUESTS.get(node);
    if (!registry) {
        registry = new Map();
        REQUESTS.set(node, registry);
    }
    return registry;
}

export function widgetByName(node, name) {
    return node?.widgets?.find((w) => w?.name === name);
}

export function widgetValue(node, name, fallback = undefined) {
    const value = widgetByName(node, name)?.value;
    return value === undefined || value === null ? fallback : value;
}

/**
 * Start a request on *key* and invalidate every older request on the same key.
 * @returns {{node: object, key: string, id: number}} token for isCurrentRequest
 */
export function beginRequest(node, key) {
    const registry = registryFor(node);
    const id = (registry.get(key) || 0) + 1;
    registry.set(key, id);
    return { node, key, id };
}

/** Invalidate every in-flight request on *key* without starting a new one. */
export function invalidateRequest(node, key) {
    const registry = registryFor(node);
    registry.set(key, (registry.get(key) || 0) + 1);
}

export function isCurrentRequest(token) {
    if (!token || !token.node) return false;
    return (registryFor(token.node).get(token.key) || 0) === token.id;
}

/**
 * Snapshot of the prompt selection a request was started for.
 *
 * @param {object} node
 * @param {"user"|"system"} kind
 */
export function readSelection(node, kind) {
    return {
        source: widgetValue(node, `${kind}_prompt_source`, "bundled_library"),
        directory: widgetValue(node, `${kind}_prompt_directory`, ""),
        file: widgetValue(node, `${kind}_prompt_file`),
    };
}

export function sameSelection(a, b) {
    return Boolean(a) && Boolean(b)
        && a.source === b.source
        && a.directory === b.directory
        && a.file === b.file;
}

/**
 * Apply prompt-file metadata to the structured field widgets.
 *
 * Unknown/missing field values reset the widget to the CUSTOM sentinel, which
 * is the documented "leave this field out" value.  Pass ``fields = null`` to
 * skip field handling entirely (restore path).
 */
export function applyStructuredFields(node, fields) {
    if (!fields) return 0;
    let applied = 0;
    for (const field of STRUCTURED_FIELDS) {
        const w = widgetByName(node, field);
        if (!w) continue;
        const value = fields[field];
        const next = value && value !== CUSTOM ? value : CUSTOM;
        if (w.value !== next) {
            w.value = next;
            applied += 1;
        }
    }
    return applied;
}

/**
 * Apply the prompt file's free description to ``description_override``.
 *
 * ``onlyIfEmpty`` is the graph-restore policy: a serialized (possibly edited)
 * description is authoritative and is never overwritten automatically.
 */
export function applyDescription(node, description, { onlyIfEmpty = false } = {}) {
    const w = widgetByName(node, "description_override");
    if (!w) return false;
    const text = typeof description === "string" ? description : "";
    if (onlyIfEmpty && (w.value || "").trim()) return false;
    if (w.value === text) return false;
    w.value = text;
    return true;
}

/** Apply a system prompt text; ``onlyIfEmpty`` protects saved edits. */
export function applySystemPromptText(node, text, options) {
    return applyTextWidget(node, "system_prompt", text, options);
}

export function markDirty(node) {
    node?.setDirtyCanvas?.(true, true);
    node?.graph?.setDirtyCanvas?.(true, true);
}

// Directory group labels in a prompt-file dropdown end with this suffix and carry
// no file value; selecting one keeps the previous real selection.
export const DIRECTORY_MARKER_SUFFIX = "/";

export function setComboValues(w, values, firstValue = CUSTOM) {
    if (!w) return;
    const normalized = [firstValue, ...values.filter((v) => v && v !== firstValue)];
    w.options = w.options || {};
    w.options.values = normalized;
    if (!normalized.includes(w.value)) w.value = firstValue;
}

/**
 * Build the dropdown options for a prompt-file list.
 *
 * Files arrive sorted by relative path, which groups them per directory. The
 * dropdown shows each directory once (first), then its files indented beneath it.
 * Directory labels are display-only markers. "custom" is only meaningful for user
 * prompts (free mode); system prompts never offer it.
 */
export function buildGroupedFileOptions(files, includeCustom = true) {
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

/** The display label for one file option; the value stays the resolvable path. */
export function fileOptionLabel(value) {
    if (typeof value !== "string") return value;
    if (value === PLACEHOLDER || value === CUSTOM) return value;
    if (value.endsWith(DIRECTORY_MARKER_SUFFIX)) return value;
    const slash = value.indexOf("/");
    // Indent files under their directory label (non-breaking spaces survive
    // HTML rendering; the value itself stays the resolvable relative path).
    return slash >= 0 ? "\u00A0\u00A0\u00A0\u00A0" + value.slice(slash + 1) : value;
}

/** Chain a callback onto a widget without replacing the original one. */
export function chainCallback(w, callback) {
    if (!w || w.__minimaxChainedCallback) return;
    const original = w.callback;
    w.callback = function (...args) {
        const result = original?.apply(this, args);
        Promise.resolve(callback()).catch((error) => console.warn(error));
        return result;
    };
    w.__minimaxChainedCallback = true;
}

/** Write *text* into a named STRING widget; ``onlyIfEmpty`` protects saved edits. */
export function applyTextWidget(node, name, text, { onlyIfEmpty = false } = {}) {
    const w = widgetByName(node, name);
    if (!w) return false;
    const value = typeof text === "string" ? text : "";
    if (onlyIfEmpty && (w.value || "").trim()) return false;
    if (w.value === value) return false;
    w.value = value;
    return true;
}

/**
 * Run a guarded user-prompt metadata prefill.
 *
 * The *loader* receives the selection snapshot that was current when the
 * request started.  Its payload is applied only when (a) no newer request on
 * the same key was started and (b) the selection is still the one the request
 * was made for.  Either way the outcome is reported instead of being guessed.
 *
 * @returns {Promise<{status: "applied"|"stale"|"skipped"|"error", error?: unknown}>}
 */
export async function runGuardedMetadataPrefill(node, file, loader, { mode = "overwrite" } = {}) {
    const selection = readSelection(node, "user");
    const token = beginRequest(node, "userFields");
    if (!file || file === PLACEHOLDER || file === CUSTOM || selection.source === "manual") {
        return { status: "skipped" };
    }
    let payload;
    try {
        payload = await loader(selection);
    } catch (error) {
        return isCurrentRequest(token) ? { status: "error", error } : { status: "stale", error };
    }
    if (!isCurrentRequest(token)) return { status: "stale" };
    if (!sameSelection(selection, readSelection(node, "user"))) return { status: "stale" };

    const onlyDescription = mode === "restore";
    applyStructuredFields(node, onlyDescription ? null : payload?.fields || {});
    applyDescription(node, typeof payload?.description === "string" ? payload.description : "", {
        onlyIfEmpty: onlyDescription,
    });
    return { status: "applied" };
}

/**
 * Guarded system-prompt text prefill.  Same contract as
 * :func:`runGuardedMetadataPrefill`; ``onlyIfEmpty`` protects saved edits.
 */
export async function runGuardedSystemPrefill(node, file, loader, { mode = "overwrite" } = {}) {
    const selection = readSelection(node, "system");
    const token = beginRequest(node, "systemText");
    if (!file || file === PLACEHOLDER || file === CUSTOM || selection.source === "manual") {
        return { status: "skipped" };
    }
    let text;
    try {
        text = await loader(selection);
    } catch (error) {
        return isCurrentRequest(token) ? { status: "error", error } : { status: "stale", error };
    }
    if (!isCurrentRequest(token)) return { status: "stale" };
    if (!sameSelection(selection, readSelection(node, "system"))) return { status: "stale" };
    applySystemPromptText(node, text, { onlyIfEmpty: mode === "restore" });
    return { status: "applied" };
}

/**
 * Schedule an initialization step exactly once, superseding an earlier one.
 *
 * ``nodeCreated`` and ``loadedGraphNode`` both run during workflow loading, but
 * their relative order is not guaranteed.  Whichever runs last wins, so
 * creating a fresh node runs the create defaults while reopening a saved graph
 * runs the restore path only.
 *
 * @returns {object} the token that is now current
 */
export function scheduleInit(node, mode, runner) {
    const token = { mode };
    node.__minimaxInitToken = token;
    queueMicrotask(() => {
        if (node.__minimaxInitToken !== token) return undefined;
        return runner(mode);
    });
    return token;
}

export function isCurrentInit(node, token) {
    return Boolean(node) && node.__minimaxInitToken === token;
}
