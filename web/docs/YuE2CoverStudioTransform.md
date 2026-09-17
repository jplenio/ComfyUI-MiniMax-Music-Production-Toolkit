# YuE2 Cover Studio · 2 transform score

Folds the planner's answer into the studio state and builds the transformation
prompt for a second LLM Chat node.

The prompt always contains, in this order: the transformer role, the **explicit
local YuE2 ABC reference** (`docs/references/YUE2_ABC_COVER_RULES.md`, injected
automatically), the interpretation profile, the cover plan, the requested vocal
range and the structured request with the source score.

The role text lives in `resources/yue2/abc-transformer.txt` and is read on each
call, so editing that file takes effect on the next queue. It is not in
`prompts/system/`: that directory is the user-facing template library whose
contents appear in the prompt nodes' dropdowns.

The model must answer with exactly one JSON object:
`{"abc": "...", "changes": [...], "warnings": []}`. Prose and code fences around
it are tolerated and removed, but a score that fails validation is never used.

A missing or unusable plan is not fatal - the transformation then follows the
interpretation profile alone. A plan that promises to change an element the
profile pins is not silently averaged away: the contradiction is recorded in the
state and reported.

This node makes no model call itself; it only prepares the prompt and the state.
See [the YuE2 guide](../../docs/YUE2.md#yue2-cover-studio).

## Inputs

- **studio_json** - the profile from the plan step: freedom, preserved elements, key and tempo
  changes, lyrics policy.
- **plan_text** (optional) - the planner's answer. The transformation prompt is built from it;
  leave it unconnected to inspect the prompt without a model answer.
- **enabled** - off passes the score through unchanged.
