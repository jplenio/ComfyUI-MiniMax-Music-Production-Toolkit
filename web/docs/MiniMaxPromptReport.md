# MiniMax Prompt Report (Markdown)

Shows exactly what MiniMax Music 3 received for the current song, as readable Markdown — the cleaned musical caption, the normalized lyrics, the character-exact final prompt that the MiniMax tokenizer consumed, and (clearly separated) the FLUX.2 image prompt that was used for the cover artwork.

**Node ID:** `MiniMaxPromptReport`  
**Category:** `MiniMax Music Production Toolkit/prompt`

## Inputs

### Required

- **`caption`** (`STRING`) — The parsed musical caption (from `MiniMaxParseExternalLLMOutputV16`).
- **`lyrics`** (`STRING`) — The parsed lyrics.
- **`title`** (`STRING`) — The parsed song title (shown in the report header).
- **`image_prompt`** (`STRING`) — The parsed FLUX.2 cover prompt; displayed in its own section, marked as *not* sent to MiniMax.

## Outputs

- **`markdown`** (`STRING`) — The full report. Also rendered directly in the node's UI text area, so no downstream connection is required to read it.

## How the report is built

- The **Caption** and **Lyrics** sections use the same cleaning rules as the MiniMax tokenizer (`comfy.ldm.minimax_music.prompt`), so they show the text exactly as MiniMax interpreted it.
- The **Final prompt (verbatim)** section is the character-for-character string handed to the MiniMax tokenizer (`<|caption_start|>…<|caption_end|><|lyrics_start|>…<|lyrics_end|><|audio_start|>`), for full transparency.
- The **Image Prompt** section contains the FLUX.2 cover prompt; it is never part of the MiniMax prompt.
- If the ComfyUI build does not expose the MiniMax prompt builder, the raw caption/lyrics are shown with a note instead.

## Usage notes

- Wire it from the parser (`MiniMaxParseExternalLLMOutputV16`): `caption`, `lyrics`, `title`, `image_prompt`.
- Place it near the Save Audio section; it has no downstream requirement — its value is the visible report.
