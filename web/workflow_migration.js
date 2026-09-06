import { app } from "../../scripts/app.js";
import {
    JSON_METADATA_INPUT_NAME,
    PARSER_INPUT_NAME,
    llmWidgetRepairs,
    shouldRepairJsonMetadataLink,
    shouldRepairParserLink,
    structuredPromptWidgetRepairs,
} from "./migration_utils.js";

// Workflow schema migration for the 2.0.0 parser node.
//
// MiniMaxParseExternalLLMOutputV16 moved its "structured_llm_output" input
// from the first required slot to the optional section (so the LLM part can
// be bypassed without a validation error).  Pre-2.0.0 workflows store a link
// into slot 0; after loading with the new node definition that slot belongs
// to the song_count widget.  This extension repairs such links by name when a
// graph is loaded, so old saved workflows keep working.
//
// The repair is deliberately conservative: see shouldRepairParserLink() in
// migration_utils.js.  In particular, the 2.0.0 parser also has STRING links
// for user_prompt, source_name_override and model_check_report - those must
// never be moved, or the model-check report would be parsed as LLM output.
//
// The same migration exists for serialized JSON files as
// workflow_schema.migrate_workflow(...).

const NODE_TYPE = "MiniMaxParseExternalLLMOutputV16";
const INPUT_NAME = PARSER_INPUT_NAME;

function inputIndexByName(node, name) {
    return node.inputs?.findIndex((input) => input?.name === name);
}

function repairNode(node) {
    try {
        const targetIndex = inputIndexByName(node, INPUT_NAME);
        if (targetIndex < 0) return false;
        const links = node.graph?.links;
        if (!links) return false;

        const structuredInput = node.inputs[targetIndex];
        let structuredLinked = Boolean(structuredInput?.link != null);

        let repaired = false;
        for (const link of Object.values(links)) {
            if (!link || link.target_id !== node.id) continue;
            const slotInput = node.inputs[link.target_slot];
            if (!slotInput) continue;
            if (link.target_slot === targetIndex) {
                structuredLinked = true;
                continue;
            }
            if (!shouldRepairParserLink(link.type, slotInput.name, slotInput.type, structuredLinked)) {
                continue;
            }
            const oldIndex = link.target_slot;
            link.target_slot = targetIndex;
            if (structuredInput) structuredInput.link = link.id;
            if (node.inputs[oldIndex]) node.inputs[oldIndex].link = null;
            structuredLinked = true;
            repaired = true;
            console.info(
                `[MiniMax Music Production Toolkit] Migrated old ${NODE_TYPE} link #${link.id} from slot ${oldIndex} to ${targetIndex} (${INPUT_NAME}).`
            );
        }
        if (repaired) {
            node.setDirtyCanvas?.(true, true);
            node.graph?.setDirtyCanvas?.(true, true);
        }
        return repaired;
    } catch (error) {
        console.warn(`[MiniMax Music Production Toolkit] Workflow migration failed for ${NODE_TYPE}:`, error);
        return false;
    }
}

function repairJsonNode(node) {
    // MiniMaxSaveProductionJSON: pre-2.0.0 workflows stored metadata_json as
    // the first input; in 2.0.0 it moved to the optional section.  A link
    // whose origin output is named "metadata_json" must target the
    // metadata_json slot, not the slot it landed on positionally.
    try {
        const targetIndex = inputIndexByName(node, JSON_METADATA_INPUT_NAME);
        if (targetIndex < 0) return false;
        const links = node.graph?.links;
        if (!links) return false;

        const metadataInput = node.inputs[targetIndex];
        let metadataLinked = Boolean(metadataInput?.link != null);

        let repaired = false;
        for (const link of Object.values(links)) {
            if (!link || link.target_id !== node.id) continue;
            if (link.target_slot === targetIndex) {
                metadataLinked = true;
                continue;
            }
            const originNode = node.graph?.getNodeById?.(link.origin_id);
            const originOutput = originNode?.outputs?.[link.origin_slot];
            const originOutputName = typeof originOutput?.name === "string" ? originOutput.name : null;
            const slotInput = node.inputs[link.target_slot];
            if (!slotInput) continue;
            if (!shouldRepairJsonMetadataLink(originOutputName, slotInput.name, metadataLinked)) {
                continue;
            }
            const oldIndex = link.target_slot;
            link.target_slot = targetIndex;
            if (metadataInput) metadataInput.link = link.id;
            if (node.inputs[oldIndex]) node.inputs[oldIndex].link = null;
            metadataLinked = true;
            repaired = true;
            console.info(
                `[MiniMax Music Production Toolkit] Migrated old MiniMaxSaveProductionJSON link #${link.id} from slot ${oldIndex} to ${targetIndex} (${JSON_METADATA_INPUT_NAME}).`
            );
        }
        if (repaired) {
            node.setDirtyCanvas?.(true, true);
            node.graph?.setDirtyCanvas?.(true, true);
        }
        return repaired;
    } catch (error) {
        console.warn("[MiniMax Music Production Toolkit] Workflow migration failed for MiniMaxSaveProductionJSON:", error);
        return false;
    }
}

const STRUCTURED_PROMPT_TYPE = "MiniMaxStructuredPromptV20";

function repairStructuredPromptNode(node) {
    // v2.0.5 inserted the meter widget between tempo and key.  ComfyUI applies
    // the serialized positional widgets_values slot by slot, so a pre-2.0.5
    // workflow loads with every field from meter onwards shifted by one
    // (meter=key, key=lyrics, ..., description=system_prompt).  The named map
    // (when present) is correct by name; the positional map needs a "custom"
    // inserted at the meter slot.  Repairs run synchronously here so the
    // structured-prompt extension's queued description prefill sees the
    // corrected values.
    try {
        const widgetNames = [];
        for (const w of node.widgets || []) {
            if (!w || !w.name || w.type === "button") continue;
            widgetNames.push(w.name);
        }
        const result = structuredPromptWidgetRepairs({
            widgetNames,
            widgetsValues: node.widgets_values,
            widgetsValuesNamed: node.widgets_values_named,
        });
        if (!result || !result.valuesByName) return false;

        let applied = 0;
        for (const [name, value] of Object.entries(result.valuesByName)) {
            const w = node.widgets?.find((widget) => widget?.name === name);
            if (w && w.value !== value) {
                w.value = value;
                applied += 1;
            }
        }
        // Keep the stored serialization in the new shape so a later re-save or
        // a second load in the same session stays aligned.
        if (node.widgets_values_named && typeof node.widgets_values_named === "object") {
            node.widgets_values_named.meter = "custom";
        }
        const meterIndex = widgetNames.indexOf("meter");
        if (Array.isArray(node.widgets_values) && meterIndex >= 0) {
            const slot = node.widgets_values[meterIndex];
            if (slot !== undefined && slot !== null && !looksLikeMeterSlotValue(slot)) {
                node.widgets_values.splice(meterIndex, 0, "custom");
            }
        }
        node.setDirtyCanvas?.(true, true);
        node.graph?.setDirtyCanvas?.(true, true);
        console.info(
            `[MiniMax Music Production Toolkit] Repaired pre-2.0.5 ${STRUCTURED_PROMPT_TYPE} widget values (meter inserted; ${applied} value(s) corrected).`
        );
        return true;
    } catch (error) {
        console.warn(`[MiniMax Music Production Toolkit] Structured Song Prompt widget repair failed:`, error);
        return false;
    }
}

function looksLikeMeterSlotValue(value) {
    if (typeof value !== "string" || !value) return false;
    if (value === "changing time signatures" || value === "free time / rubato") return true;
    return /\d{1,2}\/\d{1,2}/.test(value);
}

function repairLLMChatNode(node) {
    // Older saved graphs / restored browser sessions can carry broken LLM
    // widget values (empty split_mode, tensor_split "0", boolean main_gpu)
    // that fail prompt validation or backend coercion.  Repair them on every
    // graph load so the node always works, independent of the value source.
    try {
        const values = {};
        for (const name of ["split_mode", "tensor_split", "main_gpu"]) {
            values[name] = node.widgets?.find((w) => w.name === name)?.value;
        }
        const repairs = llmWidgetRepairs(values);
        if (Object.keys(repairs).length === 0) return false;
        for (const [name, value] of Object.entries(repairs)) {
            const w = node.widgets?.find((widget) => widget.name === name);
            if (w) w.value = value;
        }
        node.setDirtyCanvas?.(true, true);
        node.graph?.setDirtyCanvas?.(true, true);
        console.info(
            "[MiniMax Music Production Toolkit] Repaired LLM chat widget values:", repairs
        );
        return true;
    } catch (error) {
        console.warn("[MiniMax Music Production Toolkit] LLM chat widget repair failed:", error);
        return false;
    }
}

app.registerExtension({
    name: "minimax_music_production_toolkit.workflow_migration_v1",
    loadedGraphNode(node) {
        if (node.comfyClass === NODE_TYPE || node.type === NODE_TYPE) {
            queueMicrotask(() => repairNode(node));
        }
        if (node.comfyClass === "MiniMaxSaveProductionJSON" || node.type === "MiniMaxSaveProductionJSON") {
            queueMicrotask(() => repairJsonNode(node));
        }
        if (node.comfyClass === "MiniMaxLLMChat" || node.type === "MiniMaxLLMChat") {
            queueMicrotask(() => repairLLMChatNode(node));
        }
        if (node.comfyClass === STRUCTURED_PROMPT_TYPE || node.type === STRUCTURED_PROMPT_TYPE) {
            // Synchronous: the structured-prompt extension's description prefill
            // is queued as a microtask and must observe the repaired values.
            repairStructuredPromptNode(node);
        }
    },
});
