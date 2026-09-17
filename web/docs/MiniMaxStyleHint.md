# Style hint · template or text

Gives the **Cover Studio** the style text it may aim its rework at. Its single
`style_hint` output goes to one input in the bundled workflow:

- `target_style` on *Cover Studio · 1 plan*.

The description on *Song request · template & fields* is **not** one of its consumers.
That node fills its own `description_override` from its own template selection, so the
two nodes keep separate dropdowns on purpose: a style hint can refine the rework, but
it can never rewrite the description the LLM receives.

## Why a separate node is needed

`Song request · template & fields` is the master for what a track sounds like, but it
**consumes the studio's rewritten score** - the final prompt has to describe the
rewritten key, tempo and structure. It is therefore *downstream* of the studio, and a
link from it back into the studio is a dependency cycle: ComfyUI rejects the whole
prompt with `Dependency cycle detected`. The style text has to come from a node that
is not downstream of the studio, and this is that node.

## Inputs

The selection widgets have the **same names and the same dropdown as the structured
prompt node** (`user_prompt_source`, `user_prompt_directory`, `user_prompt_file`), and
the option list is built by the same shared frontend code: directory labels first,
their files indented beneath, and picking a directory label keeps the previous file.

- **`style_text`** - the text itself. Selecting a template copies its text here (only
  the body, without the front-matter block, exactly like the description on the
  structured prompt node). Edit it freely when `user_prompt_file` is `custom`, or type
  a hint and leave the file unselected.
- **`user_prompt_source`** - `bundled_library` (the shipped prompt files),
  `external_directory` (a folder on the ComfyUI machine) or `manual`.
- **`user_prompt_directory`** - the folder for `external_directory`; environment
  variables and `~` are expanded and files stay inside it.
- **`user_prompt_file`** - the template whose text becomes the hint. Select the same
  file that *Song request · template & fields* uses, so both work from one style
  definition. A selected file wins over the typed text.

An empty configuration sends an empty string, which leaves the studio exactly as it
was: the hint is optional and never stops a run. The node is inert for non-cover runs.

## What it does not do

It never overrides the song request. The requested style - template, fields and
description - stays the master, and its STYLE PRIORITY rule still governs the result.
This value is a hint for *how the source material is reworked*, and the studio's own
prompts say that it may not contradict the request.

Note that *Song request · template & fields* has its own template dropdown and fills its
own description from it, so edit the description there rather than here. This node's
selection decides only what the studio is asked to aim at.

See [the cover guide](../../docs/YUE2.md#where-each-instruction-comes-from).
