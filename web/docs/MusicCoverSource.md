# Cover song · source audio

For **YuE2 Cover**, upload or select an audio file. Other song models ignore this
node, including an empty selection. The filename without its last extension
plus `-cover` becomes the final title, independent of LLM or manual title fields.

`full` (default) retains melody and harmony; `melody` allows a new accompaniment.
This single choice controls both transcription and generation, overriding the
new-song `yue2_mode` setting. The default encoder is
`sheetsage2_bf16.safetensors` in `models/audio_encoders`.

Connect the source JSON to transcription, Structured Song Prompt, parser,
Music settings and Generate song, as in the bundled workflow. The optional
title output is a preview/convenience output; the parser enforces the same rule.
