import { app } from "../../scripts/app.js";
import { attachAutoEQPresets } from "./eq_presets.js";

app.registerExtension({name:"minimax_music_production_toolkit.autoEQPresets",
    nodeCreated(node) { if (node.comfyClass === "MiniMaxAutoEQAnalyze") attachAutoEQPresets(node); },
});
