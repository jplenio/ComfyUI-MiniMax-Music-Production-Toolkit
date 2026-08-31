# KSampler + Config Output

Core KSampler-compatible wrapper that additionally returns the effective sampler and scheduler names for reproducibility metadata.

**Node ID:** `KSamplerWithConfig`  
**Category:** `MiniMax Music Production Toolkit/utilities`

## Inputs

### Required

- **`model`** (`MODEL`) — ComfyUI model object to sample. This wrapper does not modify the model; it forwards it to the core KSampler while also returning sampler/scheduler names.
- **`positive`** (`CONDITIONING`) — Positive conditioning supplied to the KSampler. It guides sampling toward the requested content.
- **`negative`** (`CONDITIONING`) — Negative conditioning supplied to the KSampler. It guides sampling away from unwanted content; some model families use zeroed/empty negative conditioning instead.
- **`latent_image`** (`LATENT`) — Initial latent tensor to denoise/sample. Its dimensions and batch size determine the generated latent output shape.
- **`seed`** (`INT`) — Random seed for the KSampler. The same model, inputs, settings and seed are intended to reproduce the same sampling trajectory, subject to backend/device determinism.
- **`steps`** (`INT`) — Number of KSampler denoising steps. More steps increase computation and are not always better; use the range recommended for the model/workflow.
- **`cfg`** (`FLOAT`) — Classifier-free guidance scale for the KSampler. Higher values force conditioning more strongly; too high can create harsh or unstable results.
- **`sampler_name`** (choice: `euler`) — Sampling algorithm used by ComfyUI. Changing it alters the numerical denoising trajectory and can change detail, texture and reproducibility even with the same seed.
- **`scheduler`** (choice: `simple`) — Noise/sigma schedule paired with the sampler. It controls how sampling effort is distributed across the denoising trajectory and can affect character and convergence.
- **`denoise`** (`FLOAT`) — Sampling denoise strength. 1.0 performs the full denoising process; lower values retain more of an existing latent/input state where applicable.

## Outputs

- **`LATENT`** (`LATENT`)
- **`sampler_name`** (`STRING`)
- **`scheduler`** (`STRING`)

## Usage notes

Start with the defaults used by the bundled example workflow unless you have a specific reason to change this stage. Hover each input label in ComfyUI for parameter guidance.
