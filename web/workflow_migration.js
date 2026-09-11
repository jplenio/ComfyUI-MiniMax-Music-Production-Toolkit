import { app } from "../../scripts/app.js";
import {
    repairJsonNodeLinks,
    repairLLMChatWidgets,
    repairParserNodeLinks,
    repairStructuredPromptWidgets,
} from "./migration_utils.js";

// ComfyUI extension wrapper around the pure graph/widget migration adapters in
// migration_utils.js.  The mutations themselves live there so they can be unit
// tested with plain Node (tests/test_workflow_migration.mjs); this file only
// decides *when* they run.
//
// MiniMaxParseExternalLLMOutputV16 moved "structured_llm_output" from the
// first required slot to the optional section (so the LLM part can be
// bypassed), and MiniMaxSaveProductionJSON moved "metadata_json" the same way.
// Pre-2.0.0 workflows store a link into the old slot; after loading with the
// new node definition that slot belongs to a different input.  The repair is
// deliberately conservative - see shouldRepairParserLink() and
// shouldRepairJsonMetadataLink() in migration_utils.js.  In particular the
// 2.0.0 parser also has STRING links for user_prompt, source_name_override and
// model_check_report; those must never be moved, or the model-check report
// would be parsed as LLM output.
//
// The same migration exists for serialized JSON files as
// workflow_schema.migrate_workflow(...).

const PARSER_NODE_TYPE = "MiniMaxParseExternalLLMOutputV16";
const JSON_NODE_TYPE = "MiniMaxSaveProductionJSON";
const STRUCTURED_PROMPT_TYPE = "MiniMaxStructuredPromptV20";
const LLM_CHAT_TYPE = "MiniMaxLLMChat";

function matches(node, typeName) {
    return node.comfyClass === typeName || node.type === typeName;
}

app.registerExtension({
    name: "minimax_music_production_toolkit.workflow_migration_v1",
    loadedGraphNode(node) {
        if (matches(node, PARSER_NODE_TYPE)) {
            queueMicrotask(() => repairParserNodeLinks(node));
        }
        if (matches(node, JSON_NODE_TYPE)) {
            queueMicrotask(() => repairJsonNodeLinks(node));
        }
        if (matches(node, LLM_CHAT_TYPE)) {
            queueMicrotask(() => repairLLMChatWidgets(node));
        }
        if (matches(node, STRUCTURED_PROMPT_TYPE)) {
            // Synchronous: the structured-prompt extension's description prefill
            // is queued as a microtask and must observe the repaired values.
            repairStructuredPromptWidgets(node);
        }
    },
});
