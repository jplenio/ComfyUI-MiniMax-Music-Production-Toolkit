// Pure decision logic for the workflow migration (no ComfyUI imports, so it
// can be unit-tested with plain Node).  See workflow_migration.js.

export const PARSER_INPUT_NAME = "structured_llm_output";
export const JSON_METADATA_INPUT_NAME = "metadata_json";
export const LLM_SPLIT_MODE_OPTIONS = ["none", "layer", "row"];

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
