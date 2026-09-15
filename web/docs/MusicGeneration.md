# Generate song · MiniMax / YuE2

Expands only the selected engine into native ComfyUI nodes. Connect profile,
settings, style (the parser's caption output) and lyrics. Enter the installed
model filenames; unused engine files are not loaded. The upstream Model Check
downloads missing configured weights when enabled. The default YuE2 file is
`yue2_3b_bf16.safetensors`.

YuE2 uses CheckpointLoaderSimple, Generate ABC, Generate Music, Empty YuE2 Latent
Audio, the toolkit sampler and checked audio decoder. MiniMax uses its separate
diffusion/text/VAE loaders and native text encoder. The same downstream audio
chain accepts either model's output.

The final output is a generation record containing effective settings, model
filenames, generated duration and, for YuE2, ABC. Connect it to the production
JSON's model_identity_json input. Tiled decoding reduces decoder working memory.
