# Release Notes – v2.0.5

Release date: 2026-09-06

## Summary

The **time signature and world-library release**. The Structured Song Prompt gains a dedicated **Time signature** field (curated list from `4/4 (common time)` through odd meters and `free time / rubato`, with `custom` first like every other field), and the bundled prompt library grows from 95 to **239 world-spanning templates** across 31 categories. Every template now carries the canonical **Meter** metadata, and the free description text was cleaned everywhere so it never repeats anything a structured field can select. The curated combo vocabulary was overhauled to match the expanded library: the genre list now spans the full world map, the voice list covers character, mood, ensemble and special vocal types, the language list adds ~50 more languages plus regional variants, and the key list is reordered along the circle of fifths starting with the minor keys.

## Added

- **Time signature (`meter`) field** in `MiniMaxStructuredPromptV20`, positioned between tempo and key like the canonical field order. The combo offers a curated list (`4/4 (common time)`, `3/4 (waltz)`, `6/8`, `2/4 (march / polka)`, `12/8 (shuffle / slow blues)`, `2/2 (cut time)`, `6/4`, `5/4`, `7/8`, `7/4`, `9/8`, `5/8`, `11/8`, `changing time signatures`, `free time / rubato`) with `custom` first. The assembled LLM prompt gets a `Time signature:` line; `IS_CHANGED`, the provenance summary and the frontend prefill/refresh all include the new field.
- **Front-matter aliases for the new category**: `Meter`, `Taktart`, `Time signature`, `Time_signature` and `Signature` are recognized and normalized to the canonical `meter` field (alongside the existing German aliases `Tonart`, `Sprache`, `Stimme`).
- **Expanded prompt library**: 239 templates (was 95) across 31 categories. New categories: `blues`, `cinematic`, `country`, `disco`, `gospel`, `kids`, `meditation`, `musical`, `punk`, `seasonal`, `soul`, `world`. The existing categories gained dozens of subgenres — UK drill, phonk, cloud rap, old-school hip-hop, dubstep, hardstyle, big room, eurodance, future bass, goa/uplifting/progressive trance, acid/french/disco house, Berlin school, vaporwave, chiptune, IDM, EBM, electro swing, bebop, cool jazz, dixieland, swing, gypsy jazz, vocal jazz, baroque, sacred choir, string quartet, minimalism, symphonic orchestra, death/black/folk/nu metal, metalcore, djent, britpop, new wave, shoegaze, garage rock, psychedelic rock, surf rock, rockabilly, post-rock, stoner rock, merengue, son cubano, norteño, rocksteady, ska, enka, mandopop, gqom, soukous, mbalax, and many more. Every template carries the canonical metadata block including **Meter**, and the free text never repeats anything a field can select.
- **Overhauled curated combo vocabulary**: the genre list now covers the full world map (including African, Asian, Latin American and European traditional styles plus functional music); the voice list adds character/age/mood variants, ensembles, gospel/mixed choirs, rap flows, operatic/baritone/falsetto types, screamed/growled vocals, vocoder and spoken word; the language list adds ~50 more languages (from Afrikaans to Quechua, including regional German variants and `Multilingual / mixed` and `Invented / gibberish language` special cases). All curated values are verified against the bundled library by tests.
- **Consistency tests for the new category**: `tests/test_prompt_consistency.py` now enforces the canonical field order including `meter`, that every Meter value is a curated time signature, and that no description mentions a numeric time signature (the no-field-duplication rule extended to meter).

## Changed

- The key combo now follows the circle of fifths **starting with the minor keys** (`A minor … D minor`, then `C major … F major`); the node documentation and the bundled example workflow were updated to match.
- Both public example workflows carry `workflow_version: 2.0.5`; the production workflow's Structured Song Prompt node includes the new `meter` widget (default `custom`, so existing behavior is unchanged).
- Two new ambient templates gained the missing Meter metadata (`free time / rubato`), and every description that still repeated a selectable value (lyrics mode, voice gender, duration, time signature) was cleaned across the library.
- `PROMPT_LIBRARY.md`, the node documentation and the UI help texts describe the new field and the expanded library.

## Fixed

- **Pre-2.0.5 saved workflows load with shifted widget values** in `MiniMaxStructuredPromptV20`: because ComfyUI applies the serialized positional `widgets_values` slot by slot, inserting the new `meter` widget between tempo and key made every field from meter onwards show the next field's old value (meter=key, key=lyrics, … , description=system_prompt). A load-time migration repair (`web/workflow_migration.js` + `web/migration_utils.js`, unit-tested in `tests/test_workflow_migration.mjs`) now detects the old serialization shape on graph load and re-aligns all widget values: named values are re-applied by name and `meter` defaults to `custom`; positional-only files get `custom` inserted at the meter slot. The repair runs before the structured-prompt extension's description prefill, so selecting a prompt file still fills the description correctly.
- The prompt library's free-text descriptions no longer repeat values covered by the structured fields (lyrics mode such as "sparse"/"instrumental", voice gender, durations, time signatures) — the consistency tests now pass over all 239 templates.
- `scripts/upgrade_workflow_to_v2.py` and the documentation examples were brought in line with the new canonical field order (the migration script itself was not re-run; the example workflow is user-owned).

## Breaking changes

- None. The new `meter` widget defaults to `custom`, so saved workflows and headless/API runs behave exactly as before. Prompt files that were merely renamed in v2.0.3 remain consolidated as documented in `PROMPT_LIBRARY.md`.

## Upgrade notes

- Restart ComfyUI after updating and hard-refresh the browser (`Ctrl+F5`) so the new Time signature combo, the expanded option lists and the meter-migration repair load.
- Opening a workflow saved before 2.0.5 repairs its Structured Song Prompt widget values automatically (a console line logs the repair).
- Selecting an older saved workflow that references a prompt file by name keeps working; if you want the new Meter prefills, select the file again (or press `Refresh prompt lists`).

## Assets

- `ComfyUI-MiniMax-Music-Production-Toolkit-v2.0.5.zip`
- `MiniMax_Music3_Production_Toolkit_v2.0.5.json`
- `SHA256SUMS.txt`
