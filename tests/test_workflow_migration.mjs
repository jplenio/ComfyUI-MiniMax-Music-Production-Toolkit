// Unit test for the workflow-migration decision logic (plain Node, ESM).
// Run:  node tests/test_workflow_migration.mjs
import assert from "node:assert/strict";
import { JSON_METADATA_INPUT_NAME, PARSER_INPUT_NAME, llmWidgetRepairs, shouldRepairJsonMetadataLink, shouldRepairParserLink } from "../web/migration_utils.js";

const STRING = "STRING";
const INT = "INT";

// --- 2.0.0 workflow: nothing must ever be moved ---------------------------

// LLM text is already wired to structured_llm_output.
assert.equal(
    shouldRepairParserLink(STRING, PARSER_INPUT_NAME, STRING, true),
    false,
    "correctly wired LLM link must not be moved"
);

// model_check_report carries the model-check report; it must stay put even
// though its slot differs from the structured_llm_output slot.
assert.equal(
    shouldRepairParserLink(STRING, "model_check_report", STRING, false),
    false,
    "model_check_report link must never be moved to structured_llm_output"
);

// Same for the provenance links.
assert.equal(
    shouldRepairParserLink(STRING, "user_prompt", STRING, false),
    false,
    "user_prompt link must never be moved"
);
assert.equal(
    shouldRepairParserLink(STRING, "source_name_override", STRING, false),
    false,
    "source_name_override link must never be moved"
);

// Non-string links are irrelevant.
assert.equal(
    shouldRepairParserLink(INT, "song_count", INT, false),
    false,
    "non-STRING link is never an LLM-text artifact"
);

// If structured_llm_output is already linked (bypass wiring etc.), no repair.
assert.equal(
    shouldRepairParserLink(STRING, "song_count", INT, true),
    false,
    "already-linked structured input must not be touched"
);

// --- pre-2.0.0 workflow: the old LLM-text link must be repaired ------------

assert.equal(
    shouldRepairParserLink(STRING, "song_count", INT, false),
    true,
    "old-order STRING link on the INT song_count slot is the artifact to repair"
);

// --- MiniMaxSaveProductionJSON: metadata_json moved to the optional section -

// Only a link whose ORIGIN output is named "metadata_json" is the old artifact;
// every other STRING input (configuration_prefix, audio_tags_json, ...) is
// legitimate 2.0.0 wiring and must never be moved.
assert.equal(
    shouldRepairJsonMetadataLink(JSON_METADATA_INPUT_NAME, "configuration_prefix", false),
    true,
    "old metadata link sitting on configuration_prefix must be moved"
);
assert.equal(
    shouldRepairJsonMetadataLink("configuration_prefix", "configuration_prefix", false),
    false,
    "configuration_prefix link must never be moved"
);
assert.equal(
    shouldRepairJsonMetadataLink("audio_tags_json", "metadata_json", false),
    false,
    "non-metadata links are irrelevant"
);
assert.equal(
    shouldRepairJsonMetadataLink(JSON_METADATA_INPUT_NAME, JSON_METADATA_INPUT_NAME, false),
    false,
    "a link already on metadata_json is correct"
);
assert.equal(
    shouldRepairJsonMetadataLink(JSON_METADATA_INPUT_NAME, "title", true),
    false,
    "already-linked metadata input must not be touched"
);
assert.equal(
    shouldRepairJsonMetadataLink(null, "title", false),
    false,
    "unknown origin output is never repaired"
);

// --- LLM chat widget repairs -----------------------------------------------

assert.deepEqual(
    llmWidgetRepairs({ split_mode: "", tensor_split: "0", main_gpu: false }),
    { split_mode: "none", tensor_split: "", main_gpu: 0 },
    "broken LLM widget values must be repaired to the defaults"
);
assert.deepEqual(
    llmWidgetRepairs({ split_mode: "none", tensor_split: "", main_gpu: 0 }),
    {},
    "valid LLM widget values are left untouched"
);
assert.deepEqual(
    llmWidgetRepairs({ split_mode: "layer", tensor_split: "2,3", main_gpu: 1 }),
    {},
    "deliberate non-default LLM values are preserved"
);

console.log("test_workflow_migration.mjs: all assertions passed");
