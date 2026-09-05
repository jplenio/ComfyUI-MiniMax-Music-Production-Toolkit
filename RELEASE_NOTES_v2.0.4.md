# Release Notes – v2.0.4

Release date: 2026-09-05

## Summary

The "fields that feel right" release. The Structured Song Prompt gets a **curated tempo range list** (Slow 40-70 through Very fast 175-200 BPM, `custom` first), the key list now follows the **circle of fifths**, the lyrics choices gain **"only voice - no words"** (wordless vocalization), and the language list offers the important languages first and then **25 more languages alphabetically**. The log shows a single **ASCII progress bar** for the LLM chat and FlashSR stages instead of one line per step, and the **MiniMax prompt is now saved as an `.md` file** in the JSON folder with the same `Album - Title` basename as everything else. The prompt library was unified, consolidated and expanded to **95 world-spanning templates** with a grouped dropdown, and all pre-2.0.0 release notes were merged into one file.

## Added

- **Curated tempo range list**: the `tempo` combo now offers sensible BPM ranges (`Slow (40-70 BPM)`, `Laid-back (70-100 BPM)`, `Midtempo (100-120 BPM)`, `Dancefloor (120-130 BPM)`, `Uptempo (130-145 BPM)`, `Fast (145-175 BPM)`, `Very fast (175-200 BPM)`) with `custom` as the first entry like every other field — a selection always leaves the LLM a comfortable musical window instead of a single fixed value. All 24 prompt files with Tempo metadata were converted to the matching range, and the consistency tests enforce that Tempo values stay curated ranges.
- **"only voice - no words" lyrics mode**: the lyrics choices are now `yes`, `sparse`, `only voice - no words`, `instrumental`. Front-matter values like `wordless`, `vocalise`, `vocalese`, `scat`, `humming` and `no words` are normalized to the new choice.
- **Circle-of-fifths key list**: the key combo is ordered `C major … F major` then `A minor … D minor`, so related keys sit next to each other.
- **More languages**: after the existing important languages, 25 additional languages (Arabic, Bengali, Bulgarian, Czech, Danish, Dutch, Finnish, Greek, Hebrew, Hungarian, Indonesian, Malay, Norwegian, Persian, Polish, Romanian, Serbian, Swahili, Swedish, Tagalog, Thai, Turkish, Ukrainian, Urdu, Vietnamese) follow in alphabetical order.
- **MiniMax prompt report as Markdown file**: `MiniMaxSaveProductionJSON` gained the optional `minimax_prompt_md` input. When wired to the `MiniMaxPromptReport` node, the report is written next to the canonical JSON as `Album - Title.md` (same basename, atomic write) and recorded in the JSON's `outputs.prompt_report`. The bundled example workflow is wired accordingly (link 259).
- **Audio Enhancement Lab workflow**: a second public example workflow (`example_workflows/MiniMax_Music3_Production_Toolkit_AudioEnhance.json`, 15 nodes / 16 links) that skips the production stage — it enhances an already-finished song (LoadAudio → declip → PRE lowpass → FlashSR → hybrid crossover → HF repair → POST lowpass → release prep → tagged FLAC save) so you can experiment with the enhancement settings without generating a new song. Generic by design (no pre-selected audio file); validated by `validate_release.py` and new tests, and included in the release ZIP.
- **Log progress bars**: `progress_utils.format_progress_bar()` renders a single ASCII bar spanning 0 (left) to the maximum (right), e.g. `[##########----------]  8192/16384`. `MiniMaxLLMChat` logs it roughly every 10% of `max_tokens` (final 100% included) instead of a line per 64 tokens; `MiniMaxFlashSRAudio` logs it every 10% of the chunks instead of one line per chunk. The in-node blue progress bars are unchanged.
- **Unified, consolidated, world-spanning prompt library**: all 95 bundled user prompts follow one format — a canonical metadata block (Genre / Tempo / Key / Lyrics / Language / Voice / Theme / Length) plus a description that never repeats what a field can express. Near-duplicates were merged (EDM dance anthem, minimal electronic German vocals, absurd German novelty, chillout guitar) and heavy metal moved from `rock/` to `metal/`. New categories cover Africa (Afrobeats, Amapiano, Ethio-Jazz, Highlife, Desert Blues), Asia (K-Pop, J-Pop / City Pop, Anime, Chinese & Indian traditional, Bollywood), Latin America (Bossa Nova, Samba, Salsa, Cumbia, Tango, Reggaeton, Bachata) and Europe (Flamenco, Fado, Chanson, Schlager, Klezmer, Balkan Folk), plus Reggae/Dub/Dancehall, Hip-Hop/Trap/R&B and missing modern genres (Punk, Indie, Power Metal, Psytrance, Jungle, Synth-Pop, Opera). The curated Genre and Language lists were extended to match (including Hindi).
- **Grouped prompt dropdown**: both prompt-file dropdowns list the categories alphabetically as directory labels first, with each directory's files indented beneath them; directory labels are display-only.
- **Consistency tests**: `tests/test_prompt_consistency.py` guards the unified format, canonical field order, canonical lyrics values, the no-field-duplication rule and the alphabetical directory grouping; `tests/test_progress_utils.py` covers the log progress bar; workflow-migration tests cover the tempo conversion.

## Changed

- The log heartbeat for LLM streaming and FlashSR chunking was replaced by the ASCII progress bar described above.
- All pre-2.0.0 release notes were merged into a single `RELEASE_NOTES_v1.0.x.md`; the six per-version v1.0.x note files were removed.
- The bundled example workflow carries the user's audio-preset edits (PRE lowpass `PRE 10 kHz - strong`, FlashSR hybrid `FlashSR only`, HF repair `Cymbal clarity`) and the new `minimax_prompt_md` wiring.

## Fixed

- The smoke-test workflow converter (`scripts/comfyui_smoke_test.py`) now reads widget values from `widgets_values_named`; the positional list interleaves seed `control_after_generate` values and previously broke API validation (`main_gpu`, `tempo`).

## Breaking changes

- Eight bundled prompt files were consolidated into their successors (merged, renamed or moved); saved workflows that referenced one of them should select the successor file (see `PROMPT_LIBRARY.md`). The node reports a clear error for a missing file instead of failing silently.

## Upgrade notes

- Restart ComfyUI after updating and hard-refresh the browser (`Ctrl+F5`) to load the new tempo range list, the new dropdown grouping and the migration repairs.

## Assets

- `ComfyUI-MiniMax-Music-Production-Toolkit-v2.0.4.zip`
- `MiniMax_Music3_Production_Toolkit_v2.0.4.json`
- `SHA256SUMS.txt`
