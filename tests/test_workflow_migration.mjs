// Unit test for the workflow-migration decision logic (plain Node, ESM).
// Run:  node tests/test_workflow_migration.mjs
import assert from "node:assert/strict";
import { JSON_METADATA_INPUT_NAME, PARSER_INPUT_NAME, llmWidgetRepairs, shouldRepairJsonMetadataLink, shouldRepairParserLink, structuredPromptWidgetRepairs } from "../web/migration_utils.js";

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

// --- Structured Song Prompt: meter inserted between tempo and key (2.0.5) --

const STRUCTURED_WIDGETS = [
    "user_prompt_source", "user_prompt_directory", "user_prompt_file", "genre", "tempo",
    "meter", "key", "lyrics", "language", "voice", "theme", "length",
    "description_override", "system_prompt", "system_prompt_source", "system_prompt_directory",
    "system_prompt_file", "source_name_override",
];

// 1. No meter widget at all (older toolkit): nothing to repair.
assert.equal(
    structuredPromptWidgetRepairs({
        widgetNames: STRUCTURED_WIDGETS.filter((n) => n !== "meter"),
        widgetsValues: ["bundled_library", "", "<select a prompt>", "custom", "custom", "custom", "custom", "custom", "custom", "custom", "custom", "", "SYS", "manual", "", "<select a prompt>", ""],
        widgetsValuesNamed: undefined,
    }),
    null,
    "nodes without a meter widget need no repair"
);

// 2. Named serialization that already carries meter (new shape): no repair.
assert.equal(
    structuredPromptWidgetRepairs({
        widgetNames: STRUCTURED_WIDGETS,
        widgetsValues: null,
        widgetsValuesNamed: { genre: "House", tempo: "custom", meter: "custom", key: "A minor" },
    }),
    null,
    "named serialization with meter is already in the new shape"
);

// 3. Pre-2.0.5 named serialization (no meter key): values are correct by
//    name; meter defaults to custom and every other field keeps its own value.
assert.deepEqual(
    structuredPromptWidgetRepairs({
        widgetNames: STRUCTURED_WIDGETS,
        widgetsValues: ["bundled_library", "", "<select a prompt>", "custom", "custom", "custom", "custom", "custom", "custom", "custom", "custom", "", "SYS", "manual", "", "<select a prompt>", "", null, null],
        widgetsValuesNamed: {
            user_prompt_source: "bundled_library",
            user_prompt_file: "<select a prompt>",
            genre: "House",
            tempo: "Midtempo (100-120 BPM)",
            key: "A minor",
            lyrics: "sparse",
            length: "4-5 minutes",
            description_override: "My description.",
            system_prompt: "SYS",
            system_prompt_source: "manual",
        },
    }).valuesByName,
    {
        user_prompt_source: "bundled_library",
        user_prompt_file: "<select a prompt>",
        genre: "House",
        tempo: "Midtempo (100-120 BPM)",
        meter: "custom",
        key: "A minor",
        lyrics: "sparse",
        length: "4-5 minutes",
        description_override: "My description.",
        system_prompt: "SYS",
        system_prompt_source: "manual",
    },
    "named pre-2.0.5 values must be re-applied by name with meter=custom"
);

// 4. Pre-2.0.5 positional serialization: the meter slot holds the old key
//    value, so every following slot must shift back by one.
assert.deepEqual(
    structuredPromptWidgetRepairs({
        widgetNames: STRUCTURED_WIDGETS,
        widgetsValues: [
            "bundled_library", "", "<select a prompt>", "House", "Midtempo (100-120 BPM)",
            "A minor", "sparse", "Deutsch (German)", "female vocal", "love & romance",
            "4-5 minutes", "My description.", "SYS", "manual", "", "<select a prompt>", "",
            null, null,
        ],
        widgetsValuesNamed: undefined,
    }).valuesByName,
    {
        user_prompt_source: "bundled_library",
        user_prompt_directory: "",
        user_prompt_file: "<select a prompt>",
        genre: "House",
        tempo: "Midtempo (100-120 BPM)",
        meter: "custom",
        key: "A minor",
        lyrics: "sparse",
        language: "Deutsch (German)",
        voice: "female vocal",
        theme: "love & romance",
        length: "4-5 minutes",
        description_override: "My description.",
        system_prompt: "SYS",
        system_prompt_source: "manual",
        system_prompt_directory: "",
        system_prompt_file: "<select a prompt>",
        source_name_override: "",
    },
    "positional pre-2.0.5 values must be shifted back with a custom meter inserted"
);

// 5. Positional serialization already carrying an unmistakable meter value in
//    the meter slot (new shape): no repair.
assert.equal(
    structuredPromptWidgetRepairs({
        widgetNames: STRUCTURED_WIDGETS,
        widgetsValues: [
            "bundled_library", "", "<select a prompt>", "House", "Midtempo (100-120 BPM)",
            "7/8", "A minor", "sparse", "Deutsch (German)", "female vocal", "love & romance",
            "4-5 minutes", "My description.", "SYS", "manual", "", "<select a prompt>", "",
            null, null,
        ],
        widgetsValuesNamed: undefined,
    }),
    null,
    "positional serialization with a meter value in the meter slot is already repaired"
);

console.log("test_workflow_migration.mjs: all assertions passed");
