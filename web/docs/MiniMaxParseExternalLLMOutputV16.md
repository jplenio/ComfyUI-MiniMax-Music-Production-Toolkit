# Parse Structured Music LLM Output

Parses the external LLM's structured [Caption]/[Lyrics]/[Title]/[Image_Prompt] response, validates required music sections, and creates per-song seeds and provenance. Section order is tolerated defensively even though the bundled system prompt requires the canonical order.

**Node ID:** `MiniMaxParseExternalLLMOutputV16`  
**Category:** `MiniMax Music Production Toolkit/prompts`

## Inputs

### Required

- **`structured_llm_output`** (`STRING`) — Complete assistant text returned by the external LLM. The bundled production prompt requires the order [Caption], [Lyrics], [Title], [Image_Prompt]. The parser remains order-tolerant but malformed or empty required sections raise an error instead of silently generating with missing fields.
- **`song_count`** (`INT`) — Number of song variants to emit from the selected source. Higher values repeat the downstream workflow for additional variants and therefore increase total generation time.
- **`seed_mode`** (choice: `random_each_song`, `increment_from_base`) — Controls how generation seeds are created for multiple songs. random_each_song chooses a fresh seed per item; increment_from_base produces reproducible sequential seeds starting from base_seed.
- **`base_seed`** (`INT`) — Base integer used when deterministic/incrementing seed generation is selected. With random_each_song it is not the source of the random values; with increment_from_base each variant is derived from this value.
- **`user_prompt`** (`STRING`) — Short user/music request sent to the external LLM or stored with the parsed result. This is the concise creative request that the long system prompt expands into MiniMax fields.
- **`source_name_override`** (`STRING`) — Optional explicit source name. When non-empty it replaces the automatically derived source identifier used for filenames/provenance.
- **`fallback_title`** (`STRING`) — Title used only when a usable [Title] cannot be extracted. It does not replace valid LLM-generated titles.

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
