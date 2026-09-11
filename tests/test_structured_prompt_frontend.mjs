// Unit test for the structured-prompt frontend lifecycle helpers
// (plain Node, ESM).  Run:  node tests/test_structured_prompt_frontend.mjs
//
// Covers the F02 failure modes: a graph-load prefill must never overwrite
// saved edits, and a response that arrives after the selection changed must be
// discarded instead of applying stale text.
import assert from "node:assert/strict";
import {
    CUSTOM,
    PLACEHOLDER,
    STRUCTURED_FIELDS,
    applyStructuredFields,
    applyDescription,
    applySystemPromptText,
    beginRequest,
    isCurrentRequest,
    isCurrentInit,
    readSelection,
    runGuardedMetadataPrefill,
    runGuardedSystemPrefill,
    sameSelection,
    scheduleInit,
} from "../web/prompt_ui_utils.js";

const DEFERRED = [];

function deferred() {
    let resolve;
    let reject;
    const promise = new Promise((res, rej) => { resolve = res; reject = rej; });
    return { promise, resolve, reject };
}

function makeNode(overrides = {}) {
    const widgets = [];
    for (const field of STRUCTURED_FIELDS) widgets.push({ name: field, value: CUSTOM });
    widgets.push(
        { name: "user_prompt_source", value: "bundled_library" },
        { name: "user_prompt_directory", value: "" },
        { name: "user_prompt_file", value: "electronic/synth-pop-vocal.txt" },
        { name: "description_override", value: "" },
        { name: "system_prompt_source", value: "bundled_library" },
        { name: "system_prompt_directory", value: "" },
        { name: "system_prompt_file", value: "minimax-music3-production.txt" },
        { name: "system_prompt", value: "" },
    );
    const node = { id: 80, widgets, ...overrides };
    node.__get = (name) => widgets.find((w) => w.name === name).value;
    node.__set = (name, value) => { widgets.find((w) => w.name === name).value = value; };
    return node;
}

// --- pure field application -------------------------------------------------

{
    const node = makeNode();
    applyStructuredFields(node, { genre: "House", tempo: "Midtempo (100-120 BPM)" });
    assert.equal(node.__get("genre"), "House");
    assert.equal(node.__get("tempo"), "Midtempo (100-120 BPM)");
    assert.equal(node.__get("meter"), CUSTOM, "unset fields keep the CUSTOM sentinel");
    assert.equal(node.__get("key"), CUSTOM);
}

// --- description/system prompt protection ----------------------------------

{
    const node = makeNode();
    node.__set("description_override", "My edited description");
    assert.equal(applyDescription(node, "file description", { onlyIfEmpty: true }), false,
        "restore must not overwrite a saved description");
    assert.equal(node.__get("description_override"), "My edited description");
    assert.equal(applyDescription(node, "file description", { onlyIfEmpty: false }), true,
        "explicit selection may replace the description");
    assert.equal(node.__get("description_override"), "file description");

    node.__set("description_override", "   ");
    assert.equal(applyDescription(node, "file description", { onlyIfEmpty: true }), true,
        "whitespace-only description counts as empty");
}

{
    const node = makeNode();
    node.__set("system_prompt", "My edited system prompt");
    applySystemPromptText(node, "file system prompt", { onlyIfEmpty: true });
    assert.equal(node.__get("system_prompt"), "My edited system prompt");
    applySystemPromptText(node, "file system prompt", { onlyIfEmpty: false });
    assert.equal(node.__get("system_prompt"), "file system prompt");
}

// --- selection snapshots ----------------------------------------------------

{
    const node = makeNode();
    const snapshot = readSelection(node, "user");
    assert.deepEqual(snapshot, {
        source: "bundled_library", directory: "", file: "electronic/synth-pop-vocal.txt",
    });
    assert.equal(sameSelection(snapshot, readSelection(node, "user")), true);
    node.__set("user_prompt_directory", "D:/Prompts");
    assert.equal(sameSelection(snapshot, readSelection(node, "user")), false);
    const fresh = readSelection(node, "user");
    assert.equal(sameSelection(null, fresh), false);
}

// --- request generations ----------------------------------------------------

{
    const node = makeNode();
    const first = beginRequest(node, "userFields");
    assert.equal(isCurrentRequest(first), true);
    const second = beginRequest(node, "userFields");
    assert.equal(isCurrentRequest(first), false, "a newer request invalidates the older one");
    assert.equal(isCurrentRequest(second), true);
    const other = beginRequest(node, "systemText");
    assert.equal(isCurrentRequest(second), true, "keys are independent");
    assert.equal(isCurrentRequest(other), true);
}

// --- guarded prefill: delayed out-of-order responses ------------------------

async function testDelayedSelectionChange() {
    const node = makeNode();
    const slow = deferred();
    const other = deferred();
    DEFERRED.push(slow, other);

    const firstRun = runGuardedMetadataPrefill(node, "electronic/synth-pop-vocal.txt",
        () => slow.promise);
    // The user picks another file while the first request is in flight.
    node.__set("user_prompt_file", "jazz/late-night-jazz.txt");
    const secondRun = runGuardedMetadataPrefill(node, "jazz/late-night-jazz.txt",
        () => other.promise);

    // ... and the stale response arrives last.
    other.resolve({ fields: { genre: "Jazz" }, description: "second" });
    slow.resolve({ fields: { genre: "House" }, description: "first" });

    const [firstResult, secondResult] = await Promise.all([firstRun, secondRun]);
    assert.equal(secondResult.status, "applied");
    assert.equal(firstResult.status, "stale", "an outdated selection response must be discarded");
    assert.equal(node.__get("genre"), "Jazz", "the newer response wins regardless of arrival order");
    assert.equal(node.__get("description_override"), "second");
}

async function testSourceChangeWhilePending() {
    const node = makeNode();
    const slow = deferred();
    const run = runGuardedMetadataPrefill(node, "electronic/synth-pop-vocal.txt", () => slow.promise);
    node.__set("user_prompt_source", "manual");
    node.__set("user_prompt_directory", "D:/Elsewhere");
    slow.resolve({ fields: { genre: "House" }, description: "stale" });
    const result = await run;
    assert.equal(result.status, "stale");
    assert.equal(node.__get("genre"), CUSTOM, "stale payload must not touch the fields");
    assert.equal(node.__get("description_override"), "");
}

async function testErrorFromStaleRequestIsIgnored() {
    const node = makeNode();
    const slow = deferred();
    const run = runGuardedMetadataPrefill(node, "electronic/synth-pop-vocal.txt", () => slow.promise);
    beginRequest(node, "userFields"); // a newer request supersedes it
    slow.reject(new Error("network down"));
    const result = await run;
    assert.equal(result.status, "stale", "errors from superseded requests are not reported");
}

async function testSystemPrefillGuard() {
    const node = makeNode();
    const slow = deferred();
    const run = runGuardedSystemPrefill(node, "minimax-music3-production.txt", () => slow.promise);
    node.__set("system_prompt", "Edited after the request started");
    slow.resolve("file text");
    const result = await run;
    assert.equal(result.status, "applied", "the selection itself did not change");
    assert.equal(node.__get("system_prompt"), "file text",
        "explicit selection replaces the text; only the restore mode is protected");
}

async function testRestoreModeProtectsSavedEdits() {
    const node = makeNode();
    node.__set("genre", "House");
    node.__set("description_override", "Saved description");
    const result = await runGuardedMetadataPrefill(node, "electronic/synth-pop-vocal.txt",
        async () => ({ fields: { genre: "Techno", tempo: "Fast (140-175 BPM)" }, description: "file" }),
        { mode: "restore" });
    assert.equal(result.status, "applied");
    assert.equal(node.__get("genre"), "House", "restore keeps serialized structured fields");
    assert.equal(node.__get("description_override"), "Saved description",
        "restore keeps a saved description");
}

async function testRestoreFillsEmptyValues() {
    const node = makeNode();
    const result = await runGuardedMetadataPrefill(node, "electronic/synth-pop-vocal.txt",
        async () => ({ fields: { genre: "House" }, description: "file" }),
        { mode: "restore" });
    assert.equal(result.status, "applied");
    assert.equal(node.__get("genre"), CUSTOM, "restore never rewrites structured fields");
    assert.equal(node.__get("description_override"), "file", "restore fills an empty description");
}

// --- create vs restore initialization --------------------------------------

{
    const node = makeNode();
    const seen = [];
    scheduleInit(node, "create", (mode) => seen.push(`create:${mode}`));
    const restore = scheduleInit(node, "restore", (mode) => seen.push(`restore:${mode}`));
    assert.equal(isCurrentInit(node, restore), true);
    const first = scheduleInit(node, "create", () => seen.push("first"));
    assert.equal(isCurrentInit(node, restore), false, "a newer schedule supersedes the old token");
    assert.equal(isCurrentInit(node, first), true);
}

async function run() {
    await testDelayedSelectionChange();
    await testSourceChangeWhilePending();
    await testErrorFromStaleRequestIsIgnored();
    await testSystemPrefillGuard();
    await testRestoreModeProtectsSavedEdits();
    await testRestoreFillsEmptyValues();
    // Let the queued scheduleInit microtasks drain.
    await new Promise((resolve) => setTimeout(resolve, 0));
    console.log("test_structured_prompt_frontend.mjs: all assertions passed");
}

run();
