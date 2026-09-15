export function applyMasteringPreset(node, name, catalog) {
    if (name === "Custom") return;
    const values = catalog[name];
    if (!values) throw new Error(`Unknown mastering preset: ${name}`);
    for (const [key, value] of Object.entries(values)) {
        const w = node.widgets?.find(w => w.name === key);
        if (w) w.value = value;
    }
    node.graph?.setDirtyCanvas?.(true, true);
}

// Appended widgets must not alter the effective settings of old workflows.
export function restoreAppendedControls(node, info) {
    const type = node.comfyClass ?? node.type;
    const values = info.widgets_values;
    if (!Array.isArray(values)) return;
    const widget = name => node.widgets?.find(w => w.name === name);
    if (type === "MiniMaxModelAutodownload" && values.length <= 5) {
        const w = widget("yue2_models");
        if (w) w.value = false;
    }
    if (type === "MiniMaxMusicModelSettings" && values.length <= 18) {
        const w = widget("yue2_max_duration");
        if (w) w.value = widget("max_duration")?.value ?? 300;
    }
}
