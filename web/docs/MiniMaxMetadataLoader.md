# MiniMax Metadata Loader

Loads compatible values from a previously saved MiniMax production JSON (or compatible legacy sidecar JSON) for inspection or reconstruction of a generation setup.

**Node ID:** `MiniMaxMetadataLoader`  
**Category:** `Music Production Toolkit/metadata`

## Inputs

### Required

- **`metadata_file`** (`STRING`) — Path to a previously saved song production JSON. The loader reads compatible generation/settings fields from this file so a configuration can be inspected or reused.

## Outputs

- **`title`** (`STRING`)
- **`caption`** (`STRING`)
- **`lyrics`** (`STRING`)
- **`image_prompt`** (`STRING`)
- **`max_duration`** (`FLOAT`)
- **`generation_seed`** (`INT`)
- **`text_seed`** (`INT`)
- **`text_cfg_scale`** (`FLOAT`)
- **`text_top_k`** (`INT`)
- **`ksampler_seed`** (`INT`)
- **`ksampler_steps`** (`INT`)
- **`ksampler_cfg`** (`FLOAT`)
- **`sampler_name`** (`STRING`)
- **`scheduler`** (`STRING`)
- **`denoise`** (`FLOAT`)
- **`pre_preset`** (`STRING`)
- **`post_preset`** (`STRING`)
- **`metadata_json`** (`STRING`)

## Usage notes

The individual output sockets read the legacy `minimax_music3` fields. They do
not reconstruct YuE2 or YuE2 Cover settings and may return MiniMax defaults when
those fields are absent. For YuE2, inspect `song_model`, `generation`, `style`
and cover data in the complete `metadata_json` output; do not treat the scalar
outputs as a YuE2 restore workflow.

Start with the defaults used by the bundled example workflow unless you have a specific reason to change this stage. Hover each input label in ComfyUI for parameter guidance.
