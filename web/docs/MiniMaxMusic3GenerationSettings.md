# MiniMax Music 3 Generation Settings

Derives MiniMax Music generation parameters and reproducible text/sampler seeds from the primary generation seed.

**Node ID:** `MiniMaxMusic3GenerationSettings`  
**Category:** `MiniMax Music Production Toolkit/config`

## Inputs

### Required

- **`generation_seed`** (`INT`) — Primary song seed. In this workflow it is the reproducibility anchor used to derive MiniMax text/sampler seeds and can also be reused for artwork generation.
- **`max_duration`** (`FLOAT`) — Maximum MiniMax Music generation duration in seconds. This is an upper bound; the model can still end earlier if the musical/Lyrics structure encourages a shorter track.
- **`text_cfg_scale`** (`FLOAT`) — Classifier-free guidance strength for the MiniMax text/autoregressive stage. Higher values generally enforce the prompt more strongly but can reduce naturalness or introduce artifacts when pushed too far.
- **`text_top_k`** (`INT`) — Top-k sampling limit for the MiniMax text/autoregressive stage. Lower values make sampling more conservative/repetitive; higher values allow more alternatives and variability.
- **`ksampler_seed_offset`** (`INT`) — Integer offset added to generation_seed to create the diffusion/audio sampler seed. 0 keeps text and sampler seeds aligned; changing it lets you vary the sampler while retaining the same primary generation seed reference.
- **`ksampler_steps`** (`INT`) — Number of diffusion/sampling steps used by the MiniMax audio sampler. More steps cost more time and are not guaranteed to improve quality beyond the model's useful range.
- **`ksampler_cfg`** (`FLOAT`) — Guidance strength for the MiniMax diffusion/audio sampler. Higher values follow conditioning more aggressively but excessive values can sound strained or artificial.
- **`denoise`** (`FLOAT`) — Sampling denoise strength. 1.0 performs the full denoising process; lower values retain more of an existing latent/input state where applicable.

## Outputs

- **`max_duration`** (`FLOAT`)
- **`text_seed`** (`INT`)
- **`text_cfg_scale`** (`FLOAT`)
- **`text_top_k`** (`INT`)
- **`ksampler_seed`** (`INT`)
- **`ksampler_steps`** (`INT`)
- **`ksampler_cfg`** (`FLOAT`)
- **`denoise`** (`FLOAT`)

## Usage notes

Start with the defaults used by the bundled example workflow unless you have a specific reason to change this stage. Hover each input label in ComfyUI for parameter guidance.
