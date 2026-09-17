// Prompt-library HTTP helpers shared by the prompt extensions.
//
// The pure option/label helpers live in ``prompt_ui_utils.js`` so they stay
// Node-testable; this module is the thin ``api`` wrapper around the toolkit's
// prompt routes, shared by the structured-prompt node and the style-hint node so
// both resolve the same library the same way.
import { api } from "../../scripts/api.js";

export async function fetchPromptFiles(kind, source, directory) {
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

export async function fetchPromptText(kind, source, directory, file) {
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

export async function fetchPromptMetadata(source, directory, file) {
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
