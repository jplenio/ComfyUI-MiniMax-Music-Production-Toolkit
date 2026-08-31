# MiniMax Song Metadata

Builds the complete sidecar JSON containing prompts, seeds, MiniMax settings, FlashSR/filter/repair/release settings and optional LLM system prompt.

**Node ID:** `MiniMaxSongMetadata`  
**Category:** `MiniMax Music Production Toolkit/metadata`

## Inputs

### Required

- **`title`** (`STRING`) — Song title used for metadata, filenames or the reproducibility JSON, depending on the node. This does not alter the audio signal itself.
- **`caption`** (`STRING`) — Final structured MiniMax Music Caption generated or supplied for this song. Stored in the reproducibility JSON and fed to MiniMax Music.
- **`lyrics`** (`STRING`) — Final MiniMax Music Lyrics/structure field. For pure instrumentals this should contain only supported structural tags; for vocal tracks it contains tags plus singable lyrics.
- **`image_prompt`** (`STRING`) — Positive Flux artwork prompt associated with the song. It is stored for reproducibility and should describe visual content while avoiding requested text/logos if the workflow requires text-free covers.
- **`source_name`** (`STRING`) — Stable source identifier used to derive output paths and provenance. It normally comes from the prompt filename or manual/LLM source name.
- **`source_path`** (`STRING`) — Original prompt-file path when the song came from a file. Empty/manual values are valid for prompts entered directly in the workflow.
- **`prompt_origin`** (`STRING`) — Human-readable provenance label describing where the prompt came from, such as manual input, folder file or external LLM.
- **`prompt_provenance_json`** (`STRING`) — Structured provenance JSON from the prompt/parser stage. Preserve this input if you want to recreate how the final MiniMax prompt was produced.
- **`run_index`** (`INT`) — 1-based variant index for the current song run. It is used for reproducible metadata and optional filename suffixes.
- **`variant_count`** (`INT`) — Total number of variants produced from the current source. Used for metadata and to decide whether a variant index should be appended.
- **`generation_seed`** (`INT`) — Primary song seed. In this workflow it is the reproducibility anchor used to derive MiniMax text/sampler seeds and can also be reused for artwork generation.
- **`max_duration`** (`FLOAT`) — Maximum MiniMax Music generation duration in seconds. This is an upper bound; the model can still end earlier if the musical/Lyrics structure encourages a shorter track.
- **`text_seed`** (`INT`) — Seed used by the MiniMax text/autoregressive generation stage. Normally derived from generation_seed for reproducibility.
- **`text_cfg_scale`** (`FLOAT`) — Classifier-free guidance strength for the MiniMax text/autoregressive stage. Higher values generally enforce the prompt more strongly but can reduce naturalness or introduce artifacts when pushed too far.
- **`text_top_k`** (`INT`) — Top-k sampling limit for the MiniMax text/autoregressive stage. Lower values make sampling more conservative/repetitive; higher values allow more alternatives and variability.
- **`ksampler_seed`** (`INT`) — Seed used by the MiniMax diffusion/audio sampling stage. Normally derived from generation_seed plus the configured offset.
- **`ksampler_steps`** (`INT`) — Number of diffusion/sampling steps used by the MiniMax audio sampler. More steps cost more time and are not guaranteed to improve quality beyond the model's useful range.
- **`ksampler_cfg`** (`FLOAT`) — Guidance strength for the MiniMax diffusion/audio sampler. Higher values follow conditioning more aggressively but excessive values can sound strained or artificial.
- **`sampler_name`** (`STRING`) — Sampling algorithm used by ComfyUI. Changing it alters the numerical denoising trajectory and can change detail, texture and reproducibility even with the same seed.
- **`scheduler`** (`STRING`) — Noise/sigma schedule paired with the sampler. It controls how sampling effort is distributed across the denoising trajectory and can affect character and convergence.
- **`denoise`** (`FLOAT`) — Sampling denoise strength. 1.0 performs the full denoising process; lower values retain more of an existing latent/input state where applicable.
- **`pre_preset`** (`STRING`) — Preset for the low-pass stage before FlashSR. Lower cutoffs remove more original high-frequency content and force FlashSR to reconstruct more; use stronger presets only when the source top end is already problematic.
- **`pre_settings_json`** (`STRING`) — JSON produced by the pre-FlashSR filter settings node. Connect it to metadata so the exact effective filter settings are preserved for reproducibility.
- **`post_preset`** (`STRING`) — Preset for the low-pass stage after FlashSR. It gently removes extreme reconstructed high-frequency energy; lower cutoffs sound darker but can better hide artificial 'air' or shimmer.
- **`post_settings_json`** (`STRING`) — JSON produced by the post-FlashSR filter settings node. Connect it to metadata so the exact effective filter settings are preserved for reproducibility.
- **`flashsr_lowpass_input`** (`BOOLEAN`) — Passes the lowpass_input switch to the FlashSR node. Keep OFF when you already perform the explicit PRE low-pass in this workflow; enabling both can apply unintended extra filtering.
- **`workflow_name`** (`STRING`) — Descriptive workflow/version string written into the sidecar JSON. It has no audio effect but helps identify exactly which production workflow created a file.

### Optional

- **`llm_system_prompt`** (`STRING`) — Complete external-LLM system prompt stored in the sidecar JSON. Keeping it makes later prompt regeneration/auditing possible; it does not itself execute an LLM in this metadata node.
- **`release_prep_json`** (`STRING`) — JSON report from Audio Release Prep containing effective sample-rate, loudness, true-peak and static-gain measurements. Connect it to preserve final mastering/release settings.
- **`hybrid_crossover_json`** (`STRING`) — JSON report from the FlashSR Hybrid Crossover. It records sample rates, crossover parameters, HF mix and processing mode for reproducibility.
- **`hf_repair_json`** (`STRING`) — JSON report from HF Cymbal / Shimmer Repair. It stores the effective preset/custom parameters and measured processing statistics.
- **`declip_json`** (`STRING`) — JSON report from Audio Declip / Overload Repair. It records clipping detection, repaired/skipped regions, effective reconstruction parameters, safety gain and the algorithm limitations.

## Outputs

- **`metadata_json`** (`STRING`)
- **`summary`** (`STRING`)

## Usage notes

Start with the defaults used by the bundled example workflow unless you have a specific reason to change this stage. Hover each input label in ComfyUI for parameter guidance.
