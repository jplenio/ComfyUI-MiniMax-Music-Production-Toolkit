// Visibility never removes/reorders widgets: old positional workflows stay valid.
const SAVED = new WeakMap();
export const INTEGRATED = "In ComfyUI (GGUF)";
export const LOCAL = "Local app / server";
export const CLOUD = "Cloud service";
export const CONNECTION_FIELDS = ["backend", "local_provider", "cloud_provider", "server_url", "api_key_env", "credential_id"];
export const REMOTE_FIELDS = ["server_url", "remote_model", "api_key_env", "credential_id", "remote_max_tokens", "request_timeout"];
const BASIC = new Set(["enabled", "model", "max_tokens", "temperature", "n_ctx", "auto_download"]);

export function widget(node, name) { return node.widgets?.find(w => w.name === name); }
export function settings(node) {
    return Object.fromEntries(CONNECTION_FIELDS.map(name => [name, widget(node, name)?.value ?? ""]));
}
export function signature(node) { return JSON.stringify(settings(node)); }

export function visible(name, backend, advanced = false) {
    if (name === "credential_id") return false;
    if (name === "backend" || name === "enabled") return true;
    if (name === "local_provider") return backend === LOCAL;
    if (name === "cloud_provider") return backend === CLOUD;
    if (name.startsWith("llm_ui_")) return name === "llm_ui_advanced" ? backend === INTEGRATED : backend !== INTEGRATED;
    if (REMOTE_FIELDS.includes(name)) return backend !== INTEGRATED;
    return backend === INTEGRATED && (advanced || BASIC.has(name));
}

export function setVisible(w, show) {
    if (!SAVED.has(w)) SAVED.set(w, {type: w.type, computeSize: w.computeSize, draw: w.draw});
    const original = SAVED.get(w);
    if (show) Object.assign(w, original);
    else {
        w.type = "minimax_hidden";
        w.computeSize = () => [0, -4];
        w.draw = () => {};
    }
    if (w.inputEl) w.inputEl.hidden = !show;
}

export function refresh(node) {
    const backend = widget(node, "backend")?.value || INTEGRATED;
    for (const w of node.widgets || []) setVisible(w, visible(w.name, backend, !!node._llmAdvanced));
    const size = node.computeSize?.();
    if (size) node.setSize?.([Math.max(node.size?.[0] || 360, size[0]), size[1]]);
    node.setDirtyCanvas?.(true, true);
}
