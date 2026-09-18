# Music Prompt Report (Markdown)

Shows the selected song model's input as readable Markdown. MiniMax reports its
cleaned Caption, normalized Lyrics and native prompt string when the native
builder is available. YuE2 and YuE2 Cover report the actual Style and Lyrics
without claiming to reconstruct their internal tokenizer prompt. The artwork
prompt is displayed separately. The legacy node ID stays unchanged.

**Node ID:** `MiniMaxPromptReport`  
**Category:** `Music Production Toolkit/prompt`

## Inputs

### Required

- **`caption`** (`STRING`) — The parser's conditioning output: Caption for MiniMax, Style for YuE2 and YuE2 Cover.
- **`lyrics`** (`STRING`) — The parsed lyrics.
- **`title`** (`STRING`) — The parsed song title (shown in the report header).
- **`image_prompt`** (`STRING`) — The parsed FLUX.2 cover prompt; displayed in its own section, marked as *not* sent to MiniMax.

### Optional

Optional **`model_profile_json`** selects the format. Connect the same profile
as the parser and generator; an unconnected profile retains legacy MiniMax behavior.

## Outputs

- **`markdown`** (`STRING`) — The full report. Also rendered directly in the node's UI text area, so no downstream connection is required to read it.

## How the report is built

- The **Caption** and **Lyrics** sections use the same cleaning rules as the MiniMax tokenizer (`comfy.ldm.minimax_music.prompt`), so they show the text exactly as MiniMax interpreted it.
- The **Final prompt (verbatim)** section is the character-for-character string handed to the MiniMax tokenizer (`<|caption_start|>…<|caption_end|><|lyrics_start|>…<|lyrics_end|><|audio_start|>`), for full transparency.
- For **YuE2/YuE2 Cover**, final Style includes the approximate duration target;
  Lyrics and Style are displayed without MiniMax normalization or tokenizer calls.
- The **Image Prompt** section contains the FLUX.2 artwork prompt; it is never part of the song-generation prompt.
- If the ComfyUI build does not expose the MiniMax prompt builder, the raw caption/lyrics are shown with a note instead.

## Usage notes

- Wire it from the parser (`MiniMaxParseExternalLLMOutputV16`): `caption`, `lyrics`, `title`, `image_prompt`.
- Place it near the Save Audio section; it has no downstream requirement — its value is the visible report.
- Connect `markdown` to Save Production JSON's `minimax_prompt_md` input to also
  write the report beside the production JSON. The bundled workflows do this.
## Line breaks on Windows

Lyrics and musical descriptions use literal Markdown blocks, preserving every
line in Markdown previews. Saved reports use UTF-8 with Windows CRLF line endings
for both MiniMax and YuE2. Original model input strings are not modified.
