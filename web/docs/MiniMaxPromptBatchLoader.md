# MiniMax Prompt Batch Loader

Loads prompt files or manual prompt fields and emits one or more song variants with reproducible source metadata and seeds.

**Node ID:** `MiniMaxPromptBatchLoader`  
**Category:** `MiniMax Music Production Toolkit/batch`

## Inputs

### Required

- **`mode`** (choice: `folder`, `manual`) — Choose folder to read multiple prompt files or manual to use the fields in this node. Folder mode ignores the manual caption/lyrics/title except as implementation fallbacks.
- **`prompt_directory`** (`STRING`) — Directory containing prompt files for folder mode. Files are read according to the configured extensions and recursive setting.
- **`song_count`** (`INT`) — Number of song variants to emit from the selected source. Higher values repeat the downstream workflow for additional variants and therefore increase total generation time.
- **`seed_mode`** (choice: `random_each_song`, `increment_from_base`) — Controls how generation seeds are created for multiple songs. random_each_song chooses a fresh seed per item; increment_from_base produces reproducible sequential seeds starting from base_seed.
- **`base_seed`** (`INT`) — Base integer used when deterministic/incrementing seed generation is selected. With random_each_song it is not the source of the random values; with increment_from_base each variant is derived from this value.
- **`extensions`** (`STRING`) — Comma-separated filename extensions accepted in folder mode, for example .txt,.prompt,.md. Other files are ignored.
- **`recursive`** (`BOOLEAN`) — When enabled, prompt files are also discovered in subfolders below prompt_directory. Disable it to process only files directly inside the selected folder.
- **`manual_title`** (`STRING`) — Fallback/manual song title used in manual source mode. It may later be replaced by an LLM-generated title depending on the workflow branch.
- **`manual_caption`** (`STRING`) — Manual MiniMax Music caption used when manual source mode is selected. Put musical/production instructions here, not structural Lyrics tags.
- **`manual_lyrics`** (`STRING`) — Manual MiniMax Music Lyrics field. Use supported section tags and lyric text only; instrumental tracks should contain structural tags rather than prose production instructions.

## Outputs

- **`caption`** (`STRING`)
- **`lyrics`** (`STRING`)
- **`title`** (`STRING`)
- **`source_name`** (`STRING`)
- **`seed`** (`INT`)
- **`run_index`** (`INT`)
- **`source_path`** (`STRING`)

## Usage notes

Start with the defaults used by the bundled example workflow unless you have a specific reason to change this stage. Hover each input label in ComfyUI for parameter guidance.
