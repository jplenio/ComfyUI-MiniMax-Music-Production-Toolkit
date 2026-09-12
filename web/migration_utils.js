// Pure decision logic for the workflow migration (no ComfyUI imports, so it
// can be unit-tested with plain Node).  See workflow_migration.js.

export const PARSER_INPUT_NAME = "structured_llm_output";
export const JSON_METADATA_INPUT_NAME = "metadata_json";
export const LLM_SPLIT_MODE_OPTIONS = ["none", "layer", "row"];

// ComfyUI's removeInput updates inbound link slots and disconnects the removed
// wire. Do not splice the input array directly or touch the source node: its
// seed output may still be in use elsewhere in a personal workflow.
export function removeLegacyLLMSessionInput(node) {
    const index = node.inputs?.findIndex(input => input.name === "session_id") ?? -1;
    if (index < 0 || typeof node.removeInput !== "function") return false;
    node.removeInput(index);
    return true;
}

// Historical positional widget orders of MiniMaxStructuredPromptV20, used to
// repair positional-only serializations.  Pre-2.0.5 had no meter; 2.0.5 added
// meter but kept the old system-prompt field order.  The current order moved
// system_prompt after source_name_override.
const OLD_PRE_METER_ORDER = [
    "user_prompt_source", "user_prompt_directory", "user_prompt_file",
    "genre", "tempo", "key", "lyrics", "language", "voice", "theme", "length",
    "description_override", "system_prompt", "system_prompt_source",
    "system_prompt_directory", "system_prompt_file", "source_name_override",
];
const OLD_METER_ORDER = [
    "user_prompt_source", "user_prompt_directory", "user_prompt_file",
    "genre", "tempo", "meter", "key", "lyrics", "language", "voice", "theme", "length",
    "description_override", "system_prompt", "system_prompt_source",
    "system_prompt_directory", "system_prompt_file", "source_name_override",
];

function looksLikeSourceKind(value) {
    return value === "manual" || value === "bundled_library" || value === "external_directory";
}

/**
 * Compute widget repairs for the integrated LLM chat node.
 *
 * Older saved graphs / restored browser sessions can carry broken values that
 * the backend rejects: an empty split_mode (COMBO validation fails), a
 * tensor_split of "0" (meant to be empty), or a boolean/empty main_gpu.  The
 * repair maps them back to their defaults so the node always validates.
 *
 * @param {{split_mode: any, tensor_split: any, main_gpu: any}} values
 * @returns {Record<string, any>} widget-name -> repaired value (empty = nothing to do)
 */
export function llmWidgetRepairs(values) {
    const repairs = {};
    if (!LLM_SPLIT_MODE_OPTIONS.includes(values.split_mode)) repairs.split_mode = "none";
    if (values.tensor_split === "0" || values.tensor_split === 0) repairs.tensor_split = "";
    if (
        values.main_gpu === "" ||
        values.main_gpu === null ||
        values.main_gpu === undefined ||
        typeof values.main_gpu === "boolean"
    ) {
        repairs.main_gpu = 0;
    }
    return repairs;
}

/**
 * Decide whether a link targeting MiniMaxParseExternalLLMOutputV16 is an
 * old-order artifact that must be moved to the structured_llm_output slot.
 *
 * In the pre-2.0.0 input order, slot 0 was structured_llm_output.  When such
 * a workflow is loaded with the 2.0.0 definition, its STRING link lands on
 * song_count (an INT widget slot) and needs repair.
 *
 * Since 2.0.0 the parser additionally has STRING links for user_prompt,
 * source_name_override and model_check_report.  Those are NOT artifacts and
 * must never be moved, even when their slots differ from the intended input
 * name.  Two guards make this unambiguous:
 *
 * 1. If structured_llm_output already has a link, the node is wired correctly
 *    (or was already repaired) - never touch it.
 * 2. Only a STRING link sitting on a non-STRING slot can be the old artifact;
 *    STRING links on STRING slots are legitimate 2.0.0 wiring.
 *
 * @param {string|null} linkType - type of the link (e.g. "STRING").
 * @param {string} slotInputName - name of the input the link currently targets.
 * @param {string} slotInputType - type of that input (e.g. "INT", "STRING").
 * @param {boolean} structuredInputLinked - whether structured_llm_output already has a link.
 * @returns {boolean}
 */
export function shouldRepairParserLink(linkType, slotInputName, slotInputType, structuredInputLinked) {
    if (structuredInputLinked) return false;
    if (linkType !== "STRING") return false;
    if (slotInputName === PARSER_INPUT_NAME) return false;
    return slotInputType !== "STRING";
}

/**
 * Decide whether a link targeting MiniMaxSaveProductionJSON is an old-order
 * artifact that must be moved to the metadata_json slot.
 *
 * Pre-2.0.0 the JSON node's first input was metadata_json.  In 2.0.0 it moved
 * to the optional section (the song-metadata node left the example workflow),
 * so an old link that once fed metadata_json may land on another STRING slot
 * (e.g. configuration_prefix).  Every other input of this node is a STRING
 * too, so slot type cannot discriminate - the link's ORIGIN output name can:
 * only a link coming from an output literally named "metadata_json" is the
 * old artifact.
 *
 * @param {string|null} originOutputName - name of the source node's output slot.
 * @param {string} slotInputName - name of the input the link currently targets.
 * @param {boolean} metadataInputLinked - whether metadata_json already has a link.
 * @returns {boolean}
 */
export function shouldRepairJsonMetadataLink(originOutputName, slotInputName, metadataInputLinked) {
    if (metadataInputLinked) return false;
    if (originOutputName !== JSON_METADATA_INPUT_NAME) return false;
    return slotInputName !== JSON_METADATA_INPUT_NAME;
}

/**
 * Widget-value repairs for MiniMaxStructuredPromptV20 (meter migration).
 *
 * v2.0.5 inserted the ``meter`` widget between ``tempo`` and ``key``.  ComfyUI
 * applies the serialized positional ``widgets_values`` array slot by slot, so
 * a workflow saved before 2.0.5 loads with every field from ``meter`` onwards
 * showing the NEXT field's old value (meter=key, key=lyrics, ..., length=
 * description, description=system_prompt, ...).  ``widgets_values_named`` is
 * always correct (values are stored by name) - it just has no ``meter`` key.
 *
 * This function computes the corrected value for every non-button widget of
 * the node.  Returns ``{ valuesByName }`` when the loaded serialization is the
 * old shape, or ``null`` when nothing needs repairing (no meter widget, or the
 * serialization already carries meter).  A positional-only serialization is
 * always treated as the old shape unless its meter slot already holds an
 * unmistakable meter value - positional-only files come from frontends that
 * predate the meter field.
 *
 * @param {{widgetNames: string[], widgetsValues: any, widgetsValuesNamed: any}} data
 * @returns {{valuesByName: Record<string, any>} | null}
 */
export function structuredPromptWidgetRepairs({ widgetNames, widgetsValues, widgetsValuesNamed }) {
    const named = widgetsValuesNamed && typeof widgetsValuesNamed === "object";

    if (named) {
        // Named serializations are correct by name regardless of widget order,
        // so re-apply every known widget value by name.  This resolves both the
        // meter insertion and the system-prompt field reorder at once.
        const valuesByName = {};
        for (const name of widgetNames) {
            if (name in widgetsValuesNamed) valuesByName[name] = widgetsValuesNamed[name];
        }
        if (widgetNames.includes("meter") && !("meter" in widgetsValuesNamed)) {
            valuesByName.meter = "custom";
        }
        return { valuesByName };
    }

    if (!Array.isArray(widgetsValues) || !widgetNames.includes("meter")) return null;

    // Strip trailing button placeholders (null) to find the non-button count.
    let count = widgetsValues.length;
    while (count > 0 && widgetsValues[count - 1] == null) count--;

    let oldOrder = null;
    if (count === OLD_PRE_METER_ORDER.length) {
        oldOrder = OLD_PRE_METER_ORDER;
    } else if (count === OLD_METER_ORDER.length) {
        // 18 non-button values can be either the 2.0.5 order or the current
        // order.  In the current order system_prompt_source sits at its new
        // slot, so a source-kind value there means the file is already new.
        const newSourceSlot = widgetNames.indexOf("system_prompt_source");
        if (newSourceSlot >= 0 && looksLikeSourceKind(widgetsValues[newSourceSlot])) {
            return null;
        }
        oldOrder = OLD_METER_ORDER;
    }
    if (!oldOrder) return null;

    const valuesByName = {};
    for (let i = 0; i < oldOrder.length; i++) {
        const name = oldOrder[i];
        if (!widgetNames.includes(name)) continue;
        const value = widgetsValues[i];
        if (value !== undefined && value !== null) valuesByName[name] = value;
    }
    if (widgetNames.includes("meter") && !("meter" in valuesByName)) {
        valuesByName.meter = "custom";
    }
    return { valuesByName };
}

// ---------------------------------------------------------------------------
// Graph/widget mutation adapters.
//
// These operate on plain, duck-typed node objects (``id``, ``inputs``,
// ``widgets``, ``widgets_values``, ``widgets_values_named``, ``graph.links``,
// ``graph.getNodeById``) and deliberately import nothing from ComfyUI, so the
// exact mutations the extension performs can be unit-tested with plain Node.
// ``node.setDirtyCanvas`` is optional-chained; tests may omit it.
// ---------------------------------------------------------------------------

const PARSER_NODE_TYPE = "MiniMaxParseExternalLLMOutputV16";
const JSON_NODE_TYPE = "MiniMaxSaveProductionJSON";
const STRUCTURED_PROMPT_TYPE = "MiniMaxStructuredPromptV20";

function inputIndexByName(node, name) {
    return node.inputs?.findIndex((input) => input?.name === name) ?? -1;
}

function linkEntries(node) {
    const links = node.graph?.links;
    if (!links) return [];
    return Array.isArray(links) ? links.filter(Boolean) : Object.values(links).filter(Boolean);
}

function markDirty(node) {
    node.setDirtyCanvas?.(true, true);
    node.graph?.setDirtyCanvas?.(true, true);
}

/**
 * Move a pre-2.0.0 parser STRING link onto the structured_llm_output slot.
 *
 * @returns {boolean} whether anything changed
 */
export function repairParserNodeLinks(node) {
    try {
        const targetIndex = inputIndexByName(node, PARSER_INPUT_NAME);
        if (targetIndex < 0) return false;
        const links = linkEntries(node);
        if (!links.length) return false;

        const structuredInput = node.inputs[targetIndex];
        let structuredLinked = Boolean(structuredInput?.link != null);
        let repaired = false;
        for (const link of links) {
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
                `[MiniMax Music Production Toolkit] Migrated old ${PARSER_NODE_TYPE} link #${link.id} from slot ${oldIndex} to ${targetIndex} (${PARSER_INPUT_NAME}).`
            );
        }
        if (repaired) markDirty(node);
        return repaired;
    } catch (error) {
        console.warn(`[MiniMax Music Production Toolkit] Workflow migration failed for ${PARSER_NODE_TYPE}:`, error);
        return false;
    }
}

/**
 * Move an old metadata_json link onto the metadata_json slot.
 *
 * @returns {boolean} whether anything changed
 */
export function repairJsonNodeLinks(node) {
    try {
        const targetIndex = inputIndexByName(node, JSON_METADATA_INPUT_NAME);
        if (targetIndex < 0) return false;
        const links = linkEntries(node);
        if (!links.length) return false;

        const metadataInput = node.inputs[targetIndex];
        let metadataLinked = Boolean(metadataInput?.link != null);
        let repaired = false;
        for (const link of links) {
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
                `[MiniMax Music Production Toolkit] Migrated old ${JSON_NODE_TYPE} link #${link.id} from slot ${oldIndex} to ${targetIndex} (${JSON_METADATA_INPUT_NAME}).`
            );
        }
        if (repaired) markDirty(node);
        return repaired;
    } catch (error) {
        console.warn(`[MiniMax Music Production Toolkit] Workflow migration failed for ${JSON_NODE_TYPE}:`, error);
        return false;
    }
}

/**
 * Re-apply MiniMaxStructuredPromptV20 widget values after the meter insertion
 * and the system-prompt field reorder.
 *
 * The named map keeps its own values (including a valid saved meter); only a
 * named serialization that predates the meter field gets `meter = "custom"`.
 * The stored positional array is rebuilt in the current widget order and the
 * named map is kept in sync with the value that was actually applied.
 *
 * @returns {boolean} whether anything changed
 */
export function repairStructuredPromptWidgets(node) {
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
        if (Array.isArray(node.widgets_values)) {
            const rebuilt = [];
            for (const w of node.widgets || []) {
                if (w.type === "button") {
                    rebuilt.push(null);
                } else if (w.name in result.valuesByName) {
                    rebuilt.push(result.valuesByName[w.name]);
                } else {
                    rebuilt.push(w.value ?? null);
                }
            }
            node.widgets_values = rebuilt;
        }
        if (node.widgets_values_named && typeof node.widgets_values_named === "object") {
            // Keep the value that was actually resolved/applied; never reset a
            // saved meter back to "custom".
            const resolved = result.valuesByName.meter;
            if (resolved !== undefined && resolved !== null) {
                node.widgets_values_named.meter = resolved;
            }
        }
        markDirty(node);
        console.info(
            `[MiniMax Music Production Toolkit] Repaired ${STRUCTURED_PROMPT_TYPE} widget values (${applied} value(s) corrected).`
        );
        return true;
    } catch (error) {
        console.warn(`[MiniMax Music Production Toolkit] Structured Song Prompt widget repair failed:`, error);
        return false;
    }
}

/**
 * Map invalid LLM chat widget values back to their defaults.
 *
 * @returns {boolean} whether anything changed
 */
export function repairLLMChatWidgets(node) {
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
        markDirty(node);
        console.info("[MiniMax Music Production Toolkit] Repaired LLM chat widget values:", repairs);
        return true;
    } catch (error) {
        console.warn("[MiniMax Music Production Toolkit] LLM chat widget repair failed:", error);
        return false;
    }
}
