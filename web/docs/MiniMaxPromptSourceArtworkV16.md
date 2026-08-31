# Structured Song Prompt Source (Folder / Manual)

Folder/manual structured prompt source retained for non-LLM or file-driven workflows.

**Node ID:** `MiniMaxPromptSourceArtworkV16`  
**Category:** `MiniMax Music Production Toolkit/batch`

## Inputs

### Required

- **`source_mode`** (choice: `folder`, `manual`) — Choose folder to parse structured prompt files or manual to use the fields entered in this node. This legacy/source node does not call an LLM itself; it remains available for structured file/manual workflows and backward compatibility.
- **`song_count`** (`INT`) — Number of song variants to emit from the selected source. Higher values repeat the downstream workflow for additional variants and therefore increase total generation time.
- **`seed_mode`** (choice: `random_each_song`, `increment_from_base`) — Controls how generation seeds are created for multiple songs. random_each_song chooses a fresh seed per item; increment_from_base produces reproducible sequential seeds starting from base_seed.
- **`base_seed`** (`INT`) — Base integer used when deterministic/incrementing seed generation is selected. With random_each_song it is not the source of the random values; with increment_from_base each variant is derived from this value.
- **`prompt_directory`** (`STRING`) — Directory containing prompt files for folder mode. Files are read according to the configured extensions and recursive setting.
- **`extensions`** (`STRING`) — Comma-separated filename extensions accepted in folder mode, for example .txt,.prompt,.md. Other files are ignored.
- **`recursive`** (`BOOLEAN`) — When enabled, prompt files are also discovered in subfolders below prompt_directory. Disable it to process only files directly inside the selected folder.
- **`manual_title`** (`STRING`) — Fallback/manual song title used in manual source mode. It may later be replaced by an LLM-generated title depending on the workflow branch.
- **`manual_caption`** (`STRING`) — Manual MiniMax Music caption used when manual source mode is selected. Put musical/production instructions here, not structural Lyrics tags.
- **`manual_lyrics`** (`STRING`) — Manual MiniMax Music Lyrics field. Use supported section tags and lyric text only; instrumental tracks should contain structural tags rather than prose production instructions.
- **`manual_image_prompt`** (`STRING`) — Manual positive image prompt used for artwork in manual mode. Describe concrete visual content; avoid text/logos when you want a text-free album cover.

## Outputs

- **`caption`** (`STRING`)
- **`lyrics`** (`STRING`)
- **`title`** (`STRING`)
- **`image_prompt`** (`STRING`)
- **`source_name`** (`STRING`)
- **`generation_seed`** (`INT`)
- **`run_index`** (`INT`)
- **`variant_count`** (`INT`)
- **`source_path`** (`STRING`)
- **`prompt_origin`** (`STRING`)
- **`prompt_provenance_json`** (`STRING`)

## Usage notes

Start with the defaults used by the bundled example workflow unless you have a specific reason to change this stage. Hover each input label in ComfyUI for parameter guidance.
