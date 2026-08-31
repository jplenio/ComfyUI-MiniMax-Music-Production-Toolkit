# LLM Prompt Library / Template

Resolves manual, bundled-library or external-directory user/system prompts for any external ComfyUI LLM. It performs no network/model call itself and keeps legacy workflow compatibility while providing a reusable file-backed prompt library.

**Node ID:** `MiniMaxLLMTemplateV16`  
**Category:** `MiniMax Music Production Toolkit/prompts`

## Inputs

### Required

- **`user_prompt`** (`STRING`) — Short user/music request sent to the external LLM or stored with the parsed result. This is the concise creative request that the long system prompt expands into MiniMax fields.
- **`system_prompt`** (`STRING`) — Editable manual system prompt. It is used only when system_prompt_source=manual; library modes load the selected system-prompt file instead. The bundled production prompt enforces Caption → Lyrics → Title → Image_Prompt, robust instrumental structure and artifact-avoidance guidance.
- **`source_name_override`** (`STRING`) — Optional stable source label. Leave empty to derive a name from the selected user-prompt filename in library mode; manual mode may leave it empty and let the downstream parser derive the song title/source.

### Optional

- **`user_prompt_source`** (choice: `manual`, `bundled_library`, `external_directory`) — Select where the effective user/music prompt comes from. manual uses the editable user_prompt field; bundled_library loads a file shipped in prompts/user; external_directory loads the selected UTF-8 prompt file from user_prompt_directory.
- **`user_prompt_directory`** (`STRING`) — External user-prompt library directory. Used only when user_prompt_source is external_directory. Type or paste an absolute/local path; the frontend refreshes the file dropdown recursively for .txt, .md and .prompt files. Bundled-library mode ignores this field.
- **`user_prompt_file`** (choice: `<select a prompt>`, `ambient/ambient-guitar.txt`, `ambient/chillout-guitar-organic-no-metallic.txt`, `ambient/chillout-sentimental-pads-strings.txt`, `classical/cello-and-piano.txt`, `classical/cinematic-romance.txt`, `classical/mystical-neoclassical.txt`, `classical/neoclassical-piano.txt`, `classical/piano-and-strings.txt`, `classical/romantic-string-ensemble.txt`, `comedy/german-novelty-generic.txt`, `comedy/german-progressive-house-absurd.txt` …) — Prompt file selected from the active user-prompt library. The dropdown is populated recursively and shows paths relative to the library root. Use Refresh prompt lists after adding files while ComfyUI is running.
- **`system_prompt_source`** (choice: `manual`, `bundled_library`, `external_directory`) — Select where the effective LLM system prompt comes from. manual uses the editable system_prompt field; bundled_library loads a file shipped in prompts/system; external_directory loads the selected file from system_prompt_directory.
- **`system_prompt_directory`** (`STRING`) — External system-prompt library directory. Used only when system_prompt_source is external_directory. Keep reusable system prompts as UTF-8 .txt, .md or .prompt files and refresh the dropdown after changes.
- **`system_prompt_file`** (choice: `<select a prompt>`, `minimax-music3-production.txt`) — System-prompt file selected from the active library. The bundled default is the production system prompt included with this toolkit; external files remain outside the repository and are read only when selected.

## Outputs

- **`system_prompt`** (`STRING`)
- **`user_prompt`** (`STRING`)
- **`source_name`** (`STRING`)

## Usage notes

Start with the defaults used by the bundled example workflow unless you have a specific reason to change this stage. Hover each input label in ComfyUI for parameter guidance.
