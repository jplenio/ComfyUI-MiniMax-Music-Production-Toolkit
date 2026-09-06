# MiniMax Structured Song Prompt (V20)

Structured prompt control for the integrated LLM. Instead of one free-form user prompt, this node exposes dedicated fields for Genre, Tempo, Time signature, Key, Lyrics, Language, Voice, Lyrics theme and Target length, plus a further-description area. The node assembles a short structured brief plus the description into the LLM user prompt.

**Node ID:** `MiniMaxStructuredPromptV20`  
**Category:** `MiniMax Music Production Toolkit/prompts`

## Prompt file metadata (optional)

Bundled or external prompt files may start with a metadata block. When such a file is selected, the structured fields are prefilled and the file's body text (the "further description") is copied into the `description_override` field; every field can still be overridden afterwards.

Select **`custom`** (the first choice in the prompt-file dropdown) for the **free mode**: no prompt file is loaded, nothing is prefilled and nothing is cleared. You compose the structured fields and the description yourself, exactly as if you were in manual mode.

The dropdown lists the bundled library alphabetically: each category appears once as a directory label, with its files indented beneath it. Directory labels are display-only — selecting one keeps the previous file selection.

Bundled prompt files follow one unified format: the metadata block contains only the canonical fields, and the free description never repeats anything a field can express (no BPM, time signature, key, lyric mode, voice gender, language or duration in the text).

```text
---
Genre: Melodic Techno
Tempo: Midtempo (100-120 BPM)
Meter: 4/4 (common time)
Key: A minor
Lyrics: sparse
Language: English
Voice: female vocal, airy
Theme: escape into the night
Length: 4-5 minutes
---
Free text describing the track in more detail.
```

- The block must be the very first thing in the file, delimited by lines containing only `---`.
- Keys are case-insensitive; aliases such as `BPM`, `Meter`, `Taktart`, `Time signature`, `Tonart`, `Sprache`, `Stimme`, `Lyrics theme` and `Song length` are accepted. Unknown keys are ignored.
- Lyrics values are normalized to `yes` / `sparse` / `only voice - no words` / `instrumental` where recognizable (`ja`, `no`, `wenig`, `ohne`, `wordless`, `vocalise`, …). Unrecognized values are kept verbatim.
- Everything after the closing `---` (or the whole file, if there is no block) is the **further description**.
- Files without a metadata block are fully supported: all fields default to `custom` and the whole file is copied into `description_override`.

## description_override is authoritative

Selecting a prompt file copies the file's body text into `description_override`. From then on **only the content of that field** is used - the file is not re-read for the description. Edit the field to change the description, or clear it to remove it entirely. On workflow load the field is only filled when it is still empty, so serialized edits are never overwritten.

## Save as custom prompt

A **Save as custom prompt** button stores the current field values and the description as a new prompt file in the active prompt library's `_custom/` folder. It asks for a file name (the `.txt` extension is added automatically), writes the metadata block (custom fields omitted) plus the description, refreshes the dropdown and selects the new file. In manual mode the file is saved into the bundled library and the node switches to it. Existing files are only overwritten after removing or renaming them.

## Combo option lists

Every structured combo offers a curated list of common options (genres, tempos, time signatures, keys, languages, voices, lyrics themes, target lengths) so the node is useful without opening the library. Keys follow the circle of fifths (minor keys first, then major keys); languages list the most important ones first and then more languages in alphabetical order; **tempo offers curated BPM ranges** (Slow 40-70 through Very fast 175-200) so a selection always leaves the LLM a comfortable musical window; **meter offers a curated time-signature list** (4/4 (common time), 3/4 (waltz), 6/8, odd meters, changing time signatures, free time / rubato). Values found in the prompt library's metadata blocks are merged into the same lists.

## Inputs

### Required

- **`user_prompt_source`** — `manual`, `bundled_library` or `external_directory`.
- **`user_prompt_directory`** — Folder for `external_directory` mode (on the machine running ComfyUI).
- **`user_prompt_file`** — Selected prompt file, or **`custom`** (the first choice) for the free mode: no file is loaded and the fields stay untouched. The dropdown groups files alphabetically under their directory labels (directories first, files indented). The frontend refreshes this list and prefills the fields below from the file's metadata.
- **`genre`**, **`tempo`**, **`meter`**, **`key`**, **`lyrics`**, **`language`**, **`voice`**, **`theme`**, **`length`** — Structured combos. Select **`custom`** (the first entry of every combo) to leave that part out of the LLM prompt entirely. Tempo offers curated BPM ranges; meter offers curated time signatures; selecting a prompt file with matching metadata prefills them. The option lists contain a curated vocabulary plus all values found in the prompt library.
- **`description_override`** — Further description appended to the structured brief. Selecting a prompt file copies its body text here; only this field's content is used from then on.
- **`system_prompt`** / **`system_prompt_source`** / **`system_prompt_directory`** / **`system_prompt_file`** — System prompt selection, identical in behavior to the LLM Prompt Library / Template node.

### Optional

- **`source_name_override`** — Stable source name for output paths/provenance. Defaults to the prompt filename stem.

## Outputs

- **`system_prompt`** (`STRING`) — resolved system prompt for the LLM chat node.
- **`user_prompt`** (`STRING`) — assembled structured brief + description for the LLM chat node.
- **`source_name`** (`STRING`)
- **`structured_summary_json`** (`STRING`) — provenance summary (origin, resolved fields, overrides, character counts).

## Assembled user prompt

Fields not set to `custom` become a short brief:

```text
Musical brief:
Genre: Melodic Techno
Tempo: Midtempo (100-120 BPM)
Lyrics: sparse

Free text describing the track in more detail.
```

When every field is `custom` and no description exists, the node raises a clear error so an empty prompt cannot silently reach the LLM.

## Cache behavior

`IS_CHANGED` includes the selected prompt file content fingerprint (editing a file invalidates the cache), the `description_override` text and all structured field values, so changing any of them re-runs the LLM step.

## Usage notes

- The bundled example workflow uses this node instead of the legacy `LLM Prompt Library / Template` node for the user prompt; the legacy node remains available for backwards compatibility.
- In `manual` mode, use the structured fields and `description_override` to compose the prompt directly.
