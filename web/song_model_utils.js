// Pure helpers shared with frontend tests. Custom files have no model family.
export function modelTemplate(file, model) {
    if (model === "YuE2" && file?.startsWith("minimax-music3-")) {
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
