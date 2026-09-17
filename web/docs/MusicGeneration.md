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

YuE2 sends the same explicit duration target and timed Style arrangement to
both ABC planning and music generation. The native `max_duration` retains the
separately configured ceiling; Length and a requested range never lower it.
Phrases and decay can finish beyond the approximate target. Style and
settings must come from the same parsed prompt; a mismatch stops generation.
The receipt records requested/target/effective/actual duration and deviation.
YuE2 may still finish early or reduce available duration for context limits;
the toolkit does not pad or stretch audio to hide that difference.

The final output is a generation record containing effective settings, model
filenames, generated duration and, for YuE2, ABC. Connect it to the production
JSON's model_identity_json input. Tiled decoding reduces decoder working memory.

**YuE2 Cover** uses the same YuE2 sampler and duration settings, but receives
`cover_source_json` and `cover_abc` from *Cover song · instrumental score / phrase map*. It
does not generate a new score. The source mode must match the effective Music
settings. The record includes source filename, fixed title, encoder, mode and the
ABC that was actually handed to the engine.

The engine also applies the selected **Cover lyrics** rewrite to the incoming
score (idempotent, so a graph that already ran the score node lands on the same
string). An instrumental cover therefore reaches `YuE2GenerateMusic` with the
vocal notes muted and transferred to Ins, with overlapping Ins material replaced.
Instrumental covers use compiled musical tags and empty section tags at the
native input. Detailed production prose remains in the report. The receipt's
`cover_conditioning` records exact native Style, Lyrics and ABC. A pinned upstream
checker validates the native score; melody mode strips harmony explicitly.
