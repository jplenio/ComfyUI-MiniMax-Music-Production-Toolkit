import { app } from "../../scripts/app.js";

// These values intentionally mirror the Python presets.  The backend remains
// authoritative; this extension only keeps the visible widgets honest.

const DECLIP_PRESETS = {
    "Auto / conservative": {
        detection_threshold_percent: 98.0,
        plateau_tolerance_percent: 0.001,
        min_flat_samples: 3,
        slope_context_samples: 3,
        max_repair_ms: 8.0,
        max_peak_extension_db: 4.0,
        output_ceiling_dbfs: -1.0,
        mix: 1.0,
    },
    "Standard": {
        detection_threshold_percent: 96.0,
        plateau_tolerance_percent: 0.010,
        min_flat_samples: 2,
        slope_context_samples: 4,
        max_repair_ms: 12.0,
        max_peak_extension_db: 6.0,
        output_ceiling_dbfs: -1.0,
        mix: 1.0,
    },
    "Strong": {
        detection_threshold_percent: 93.0,
        plateau_tolerance_percent: 0.100,
        min_flat_samples: 1,
        slope_context_samples: 6,
        max_repair_ms: 20.0,
        max_peak_extension_db: 8.0,
        output_ceiling_dbfs: -1.0,
        mix: 1.0,
    },
};

const HF_PRESETS = {
    "Gentle": {
        start_frequency_hz: 8000.0,
        sustain_reduction_db: 1.25,
        fast_envelope_ms: 8.0,
        slow_envelope_ms: 180.0,
        transient_sensitivity: 0.35,
        side_hf_reduction_db: 0.75,
        static_hf_trim_db: -0.4,
        min_hf_level_dbfs: -58.0,
        mix: 1.0,
    },
    "Cymbal clarity": {
        start_frequency_hz: 7000.0,
        sustain_reduction_db: 2.25,
        fast_envelope_ms: 5.0,
        slow_envelope_ms: 180.0,
        transient_sensitivity: 0.30,
        side_hf_reduction_db: 1.0,
        static_hf_trim_db: -0.5,
        min_hf_level_dbfs: -58.0,
        mix: 1.0,
    },
    "Reverb / shimmer control": {
        start_frequency_hz: 7000.0,
        sustain_reduction_db: 3.25,
        fast_envelope_ms: 8.0,
        slow_envelope_ms: 260.0,
        transient_sensitivity: 0.38,
        side_hf_reduction_db: 1.75,
        static_hf_trim_db: -0.9,
        min_hf_level_dbfs: -60.0,
        mix: 1.0,
    },
};

const RELEASE_PRESETS = {
    "Streaming Safe -14 LUFS / -1 dBTP": {
        custom_target_lufs: -14.0,
        custom_true_peak_dbtp: -1.0,
    },
    "Modern Music -12 LUFS / -2 dBTP": {
        custom_target_lufs: -12.0,
        custom_true_peak_dbtp: -2.0,
    },
    "Loud Electronic -10 LUFS / -2 dBTP": {
        custom_target_lufs: -10.0,
        custom_true_peak_dbtp: -2.0,
    },
};

const LOWPASS_PRESETS = {
    "PRE 14 kHz - light": { cutoff: 14000.0, order: 2, phase: "zero_phase" },
    "PRE 12 kHz - recommended": { cutoff: 12000.0, order: 2, phase: "zero_phase" },
    "PRE 10 kHz - strong": { cutoff: 10000.0, order: 2, phase: "zero_phase" },
    "PRE 8 kHz - aggressive": { cutoff: 8000.0, order: 2, phase: "zero_phase" },
    "POST 20 kHz - recommended gentle": { cutoff: 20000.0, order: 2, phase: "causal" },
    "POST 19 kHz - slightly stronger": { cutoff: 19000.0, order: 2, phase: "causal" },
};

function widget(node, name) {
    return node.widgets?.find((w) => w.name === name);
}

function setWidget(node, name, value) {
    const w = widget(node, name);
    if (w) w.value = value;
}

function dirty(node) {
    node.setDirtyCanvas?.(true, true);
    node.graph?.setDirtyCanvas?.(true, true);
}

function syncDeclip(node) {
    const mode = widget(node, "mode")?.value;
    const preset = DECLIP_PRESETS[mode];
    if (!preset) return; // Custom / Analyze only / Bypass preserve the current controls.
    node.__minimaxPresetSyncing = true;
    try {
        for (const [name, value] of Object.entries(preset)) setWidget(node, name, value);
    } finally {
        node.__minimaxPresetSyncing = false;
    }
    dirty(node);
}

function syncHF(node) {
    const mode = widget(node, "mode")?.value;
    const preset = HF_PRESETS[mode];
    if (!preset) return; // Custom and Bypass deliberately preserve current controls.
    node.__minimaxPresetSyncing = true;
    try {
        for (const [name, value] of Object.entries(preset)) setWidget(node, name, value);
    } finally {
        node.__minimaxPresetSyncing = false;
    }
    dirty(node);
}

function syncRelease(node) {
    const mode = widget(node, "processing")?.value;
    const preset = RELEASE_PRESETS[mode];
    if (!preset) return; // Custom/Resample only/Bypass keep the existing custom fields.
    node.__minimaxPresetSyncing = true;
    try {
        for (const [name, value] of Object.entries(preset)) setWidget(node, name, value);
    } finally {
        node.__minimaxPresetSyncing = false;
    }
    dirty(node);
}

function syncLowpassLab(node) {
    const p = LOWPASS_PRESETS[widget(node, "preset")?.value];
    if (!p) return; // CUSTOM leaves values untouched.
    node.__minimaxPresetSyncing = true;
    try {
        setWidget(node, "custom_cutoff_hz", p.cutoff);
        setWidget(node, "custom_order", p.order);
        setWidget(node, "custom_phase_mode", p.phase);
    } finally {
        node.__minimaxPresetSyncing = false;
    }
    dirty(node);
}

function syncFlashSettings(node, which) {
    const presetName = widget(node, `${which}_preset`)?.value;
    const p = LOWPASS_PRESETS[presetName];
    if (!p) return;
    node.__minimaxPresetSyncing = true;
    try {
        setWidget(node, `${which}_custom_cutoff_hz`, p.cutoff);
        setWidget(node, `${which}_custom_order`, p.order);
        setWidget(node, `${which}_custom_phase`, p.phase);
    } finally {
        node.__minimaxPresetSyncing = false;
    }
    dirty(node);
}

function chainCallback(w, fn) {
    if (!w || w.__minimaxPresetSyncInstalled) return;
    const original = w.callback;
    w.callback = function (...args) {
        const result = original?.apply(this, args);
        fn();
        return result;
    };
    w.__minimaxPresetSyncInstalled = true;
}

function nodeClass(node) {
    return node.comfyClass ?? node.type ?? node.constructor?.type;
}

function switchWidgetValue(node, name, value) {
    const w = widget(node, name);
    if (!w || w.value === value) return;
    w.value = value;
    // Calling the mode callback keeps any other extensions/state in sync.
    w.callback?.(value);
    dirty(node);
}

function chainEditToCustom(w, node, modeName, customValue, excluded = []) {
    if (!w || w.__minimaxEditToCustomInstalled) return;
    const original = w.callback;
    w.callback = function (...args) {
        const result = original?.apply(this, args);
        if (!node.__minimaxPresetSyncing) {
            const mode = widget(node, modeName)?.value;
            if (mode !== customValue && !excluded.includes(mode)) {
                switchWidgetValue(node, modeName, customValue);
            }
        }
        return result;
    };
    w.__minimaxEditToCustomInstalled = true;
}

function attach(node) {
    switch (nodeClass(node)) {
        case "AudioDeclipRepair":
            chainCallback(widget(node, "mode"), () => syncDeclip(node));
            for (const name of Object.keys(DECLIP_PRESETS["Auto / conservative"])) {
                chainEditToCustom(widget(node, name), node, "mode", "Custom", ["Custom", "Analyze only", "Bypass"]);
            }
            break;
        case "HFCymbalShimmerRepair":
            chainCallback(widget(node, "mode"), () => syncHF(node));
            for (const name of Object.keys(HF_PRESETS["Gentle"])) {
                chainEditToCustom(widget(node, name), node, "mode", "Custom", ["Custom", "Bypass"]);
            }
            break;
        case "AudioReleasePrep":
            chainCallback(widget(node, "processing"), () => syncRelease(node));
            // Editing a target while a LUFS preset is active turns that preset into a real
            // Custom configuration. Resample-only/Bypass remain unchanged until explicitly selected.
            for (const name of ["custom_target_lufs", "custom_true_peak_dbtp"]) {
                chainEditToCustom(widget(node, name), node, "processing", "Custom", ["Custom", "Resample only", "Bypass"]);
            }
            break;
        case "FlashSRLowpassLab":
            chainCallback(widget(node, "preset"), () => syncLowpassLab(node));
            for (const name of ["custom_cutoff_hz", "custom_order", "custom_phase_mode"]) {
                chainEditToCustom(widget(node, name), node, "preset", "CUSTOM", ["CUSTOM"]);
            }
            break;
        case "FlashSRProcessingSettings":
            chainCallback(widget(node, "pre_preset"), () => syncFlashSettings(node, "pre"));
            chainCallback(widget(node, "post_preset"), () => syncFlashSettings(node, "post"));
            for (const name of ["pre_custom_cutoff_hz", "pre_custom_order", "pre_custom_phase"]) {
                chainEditToCustom(widget(node, name), node, "pre_preset", "CUSTOM", ["CUSTOM"]);
            }
            for (const name of ["post_custom_cutoff_hz", "post_custom_order", "post_custom_phase"]) {
                chainEditToCustom(widget(node, name), node, "post_preset", "CUSTOM", ["CUSTOM"]);
            }
            break;
    }
}

function syncAfterLoad(node) {
    // loadedGraphNode runs after stored widget values are restored.  A microtask
    // prevents stored older values from visually disagreeing with the selected preset.
    queueMicrotask(() => {
        switch (nodeClass(node)) {
            case "AudioDeclipRepair": syncDeclip(node); break;
            case "HFCymbalShimmerRepair": syncHF(node); break;
            case "AudioReleasePrep": syncRelease(node); break;
            case "FlashSRLowpassLab": syncLowpassLab(node); break;
            case "FlashSRProcessingSettings":
                syncFlashSettings(node, "pre");
                syncFlashSettings(node, "post");
                break;
        }
    });
}

app.registerExtension({
    name: "minimax_music_production_toolkit.preset_sync_v1",
    nodeCreated(node) {
        attach(node);
    },
    loadedGraphNode(node) {
        attach(node);
        syncAfterLoad(node);
    },
});
