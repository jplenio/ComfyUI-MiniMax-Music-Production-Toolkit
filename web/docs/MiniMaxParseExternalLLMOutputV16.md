# Parse Structured Music LLM Output

Parses the external LLM's structured [Caption]/[Lyrics]/[Title]/[Image_Prompt] response, validates required music sections, and creates per-song seeds and provenance. Section order is tolerated defensively even though the bundled system prompt requires the canonical order.

**Node ID:** `MiniMaxParseExternalLLMOutputV16`  
**Category:** `MiniMax Music Production Toolkit/prompts`

## Inputs

### Required

- **`song_count`** (`INT`) — Number of song variants to emit from the selected source. Higher values repeat the downstream workflow for additional variants and therefore increase total generation time.
- **`seed_mode`** (choice: `random_each_song`, `increment_from_base`) — Controls how generation seeds are created for multiple songs. random_each_song chooses a fresh seed per item; increment_from_base produces reproducible sequential seeds starting from base_seed.
- **`base_seed`** (`INT`) — Base integer used when deterministic/incrementing seed generation is selected. With random_each_song it is not the source of the random values; with increment_from_base each variant is derived from this value.
- **`user_prompt`** (`STRING`) — Short user/music request sent to the external LLM or stored with the parsed result. This is the concise creative request that the long system prompt expands into MiniMax fields.
- **`source_name_override`** (`STRING`) — Optional explicit source name. When non-empty it replaces the automatically derived source identifier used for filenames/provenance.
- **`fallback_title`** (`STRING`) — Title used only when a usable [Title] cannot be extracted. It does not replace valid LLM-generated titles.

### Optional

- **`structured_llm_output`** (`STRING`, forceInput) — Complete assistant text returned by the LLM. The bundled production prompt requires the order [Caption], [Lyrics], [Title], [Image_Prompt]. The parser remains order-tolerant but malformed or empty required sections raise an error instead of silently generating with missing fields. When this input is missing (LLM bypassed/disabled), the manual fallback fields below are used.
- **`manual_caption`** / **`manual_lyrics`** / **`manual_title`** / **`manual_image_prompt`** (`STRING`) — Manual fallbacks used when the LLM section is switched off.
- **`model_check_report`** (`STRING`) — Optional report text from the Model Auto-Download / Check node; recorded in provenance only, never parsed as LLM output.
- **`llm_status`** (`STRING`) — Status text from the integrated LLM chat node. Used for diagnostics: when the LLM returned no text, the error says so and quotes this status instead of looking like a prompt-format error. In the bundled workflow it is wired to the LLM chat node's `status` output.
- **`max_prompt_tokens`** (`INT`, default `4500`) — Token budget for the combined Caption+Lyrics sent to MiniMax Music 3. The MiniMax text encoder hard-rejects prompts above 5000 tokens; the default keeps a safety margin. The estimate is conservative and calibrated against the real MiniMax tokenizer (worst measured case: German ~3.68 characters per token; estimator uses 3.5).
- **`trim_long_prompt`** (`BOOLEAN`, default ON) — When the estimate exceeds the budget: ON trims softly — whole lines are dropped from the end of the lyrics (never cutting inside a line), orphan section tags are removed, the caption stays intact, and a warning is logged. OFF raises a clear error instead, so the MiniMax encoder never fails with its own cryptic token-limit message.

## [Count] tolerance

A `[Count]` / `[Song-Count]` section is advisory. The parser extracts the first standalone integer; values outside 1-100 are clamped with a warning, and a section without any usable integer (e.g. LLM prose like `1 +8? Let's number:`) is ignored instead of failing the run.

## LLM leak tolerance

LLMs sometimes leak planning or self-check text into their answer - for example an early `[Image_Prompt]` header followed by meta-commentary and then the real sections again at the end. The parser treats a repeated top-level section header as a restart, so **the last occurrence of each section wins**; earlier drafts never pollute the parsed fields. The bundled system prompt also forbids any text outside the four sections and any mention of its own rules.

## Image-prompt text guard

The `[Image_Prompt]` sent to FLUX must never produce readable text on the cover. As a safety net, the parser appends the standard text-free prohibition (`No text, no letters, no words, ...`) whenever the resolved image prompt does not already contain it - for LLM output, manual fallbacks and prompt files alike. A log line reports when the prohibition was appended.

## Token budget behavior

The MiniMax Music 3 text encoder rejects prompts with more than 5000 tokens (ComfyUI `MiniMaxMusic3AR.generate`). If the LLM overshoots, this node either soft-trims or fails clearly, depending on `trim_long_prompt`. The applied budget is recorded in the provenance JSON (`prompt_tokens_estimated`, `prompt_trimmed`, `original_prompt_tokens_estimated`, `hard_cut_used`). The bundled system prompt also instructs the LLM to stay compact, so trimming is a rarely needed safety net.

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
