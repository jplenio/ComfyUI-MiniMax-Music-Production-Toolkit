// Pure helpers shared with frontend tests. Custom files have no model family.
export function prepareCoverAudioWidgets(nodeData) {
    if (nodeData?.name !== "MusicCoverSource") return;
    const required = nodeData.input?.required;
    if (required?.audio?.[1]?.audio_upload !== true) return;

    // Comfy.UploadAudio enables AUDIOUPLOAD for any audio_upload input, but
    // Comfy.AudioWidget adds its required audioUI only to native node names.
    // AUDIOUPLOAD reads audioUI.element immediately during node construction.
    // Put our preview before upload, including when the core hook ran first.
    const { audioUI, upload, ...fields } = required;
    nodeData.input.required = {
        ...fields,
        audioUI: audioUI ?? ["AUDIO_UI", {}],
        ...(upload ? { upload } : {}),
    };
    // Some frontends use explicit input_order rather than object iteration.
    if (nodeData.input_order?.required) {
        const order = nodeData.input_order.required.filter(name => name !== "audioUI" && name !== "upload");
        nodeData.input_order.required = [...order, "audioUI", ...(upload ? ["upload"] : [])];
    }
}

export function modelTemplate(file, model) {
    if (["YuE2", "YuE2 Cover"].includes(model) && file?.startsWith("minimax-music3-")) {
        return "yue2/" + file.slice("minimax-music3-".length);
    }
    if (model === "MiniMax Music 3" && file?.startsWith("yue2/")) {
        return "minimax-music3-" + file.slice("yue2/".length);
    }
    return file;
}

export function connectedModel(node) {
    const input = node.inputs?.find(i => i.name === "model_profile_json");
    const link = node.graph?.links?.[input?.link];
    const origin = link && node.graph?.getNodeById(link.origin_id);
    return origin?.widgets?.find(w => w.name === "model")?.value;
}
