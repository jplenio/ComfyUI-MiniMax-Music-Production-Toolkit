// Presets materialize existing controls; no extra serialized state or DSP path.
let catalogPromise;
export function loadEQPresets() {
    return catalogPromise ??= fetch(new URL("./eq_presets.json", import.meta.url))
        .then(r => { if (!r.ok) throw new Error(`HTTP ${r.status}`); return r.json(); })
        .catch(error => { catalogPromise = null; throw error; });
}
function close(a, b) { return Math.abs(a - b) < 1e-6; }
export function sameSettings(a, b) {
    if (!a || !b || a.schema !== b.schema || !close(a.preamp_db ?? 0, b.preamp_db ?? 0)
        || a.bands.length !== b.bands.length) return false;
    return a.bands.every((x, i) => {
        const y = b.bands[i];
        return x.type === y.type && (x.enabled !== false) === (y.enabled !== false)
            && close(x.frequency_hz, y.frequency_hz) && close(x.gain_db ?? 0, y.gain_db ?? 0)
            && close(x.q ?? Math.SQRT1_2, y.q ?? Math.SQRT1_2) && close(x.slope ?? 1, y.slope ?? 1);
    });
}
export function sameValues(a, b) {
    return Object.entries(b).every(([key, value]) => typeof value === "number"
        ? close(a[key], value) : a[key] === value);
}
export function presetControl(label, group, current, locked, apply, load = loadEQPresets, notice = () => "") {
    const root = document.createElement("div"), select = document.createElement("select"), description = document.createElement("div");
    root.style.cssText = "font:12px sans-serif;padding:6px;box-sizing:border-box;width:100%;color:#eee;background:#20232a";
    select.style.cssText = "width:100%;margin-bottom:5px";
    select.setAttribute("aria-label", label);
    description.style.cssText = "white-space:normal;line-height:1.3";
    description.setAttribute("role", "status");
    root.append(select, description);
    let presets = [], error = "", loaded = false;
    const option = name => { const o = document.createElement("option"); o.value = name; o.textContent = name; select.append(o); };
    option("Custom");
    function sync() {
        const preset = presets.find(p => group === "manual" ? sameSettings(current(), p.settings) : sameValues(current(), p.values));
        select.value = preset?.name ?? "Custom";
        select.disabled = !loaded || locked();
        description.textContent = error || (!loaded ? "Loading EQ presets…" : locked()
            ? "Connected settings: presets are read-only."
            : notice(preset) || preset?.description || "Custom: edit the EQ controls. Your settings are preserved.");
    }
    select.onchange = () => {
        if (locked()) { sync(); return; }
        const preset = presets.find(p => p.name === select.value);
        if (preset) apply(structuredClone(group === "manual" ? preset.settings : preset.values));
        sync();
    };
    const ready = load().then(catalog => {
        presets = catalog[group]; presets.forEach(p => option(p.name)); loaded = true; sync();
    }).catch(e => { error = `Presets unavailable: ${e.message}. Existing EQ controls still work; reload to retry.`; sync(); });
    sync();
    return { root, sync, ready, select };
}
export function attachAutoEQPresets(node) {
    if (!node.addDOMWidget || node.__miniMaxAutoEQPresets) return;
    node.__miniMaxAutoEQPresets = true;
    const keys = ["target_mode", "strength_percent", "max_gain_db", "max_bands", "min_frequency_hz", "max_frequency_hz"];
    const widgets = () => keys.map(key => node.widgets?.find(w => w.name === key));
    // Keep the legacy value at its exact serialization index for saved graphs
    // and API prompts. Only the unified preset selector edits its target mode.
    function hideTargetMode() {
        const target = widgets()[0];
        if (!target) return;
        target.type = "minimax_hidden";
        target.hidden = true;
        target.options ??= {};
        target.options.hidden = true;
        target.computeSize = () => [0, -4];
        target.draw = () => {};
        if (target.inputEl) target.inputEl.hidden = true;
    }
    hideTargetMode();
    const control = presetControl("Auto-EQ preset", "auto",
        () => Object.fromEntries(keys.map((key, i) => [key, widgets()[i]?.value])),
        () => widgets().some(w => !w) || node.inputs?.some(i => keys.includes(i.name) && i.link != null),
        values => { widgets().forEach(w => { w.value = values[w.name]; w.callback?.(w.value); }); node.setDirtyCanvas?.(true, true); },
        loadEQPresets, preset => widgets()[0]?.value === "Reference track" &&
            !node.inputs?.some(i => i.name === "reference_audio" && i.link != null)
            ? "Reference audio missing: Auto-EQ will skip correction. Connect reference_audio or choose a Warm / Bright preset."
            : !preset ? `Custom: ${widgets()[0]?.value ?? "saved target"}. Edit the numerical controls or select a preset to change the tonal target.` : "");
    const dom = node.addDOMWidget("auto_eq_presets", "minimax_eq_presets", control.root, {serialize:false});
    dom.computeSize = width => [width, 100];
    const draw = node.onDrawForeground, removed = node.onRemoved, configured = node.onConfigure;
    node.onDrawForeground = function(...args) { draw?.apply(this, args); hideTargetMode(); control.sync(); };
    node.onConfigure = function(...args) { configured?.apply(this, args); hideTargetMode(); control.sync(); };
    node.onRemoved = function(...args) { control.root.remove(); removed?.apply(this, args); };
    return control;
}
