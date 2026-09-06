# Prompt library

## Purpose

Prompt files separate reusable prompts from the workflow JSON. The `LLM Prompt Library / Template` node (legacy) and the new `Structured Song Prompt` node both read the same library; the structured node additionally understands the optional metadata block described below.

User and system prompts can use different source modes at the same time.

## Source modes

### `manual`

Use the multiline field stored directly in the workflow.

### `bundled_library`

Reads from this repository:

```text
prompts/user/
prompts/system/
```

The file dropdown shows the categories as alphabetical directory labels first, with the files of each directory indented beneath them. The values themselves stay the resolvable relative paths (`category/file.txt`).

### `external_directory`

Enter an absolute or environment-variable-based path on the machine running ComfyUI. The node recursively discovers supported prompt files below that root and displays them as relative paths in the dropdown.

Supported file types:

- `.txt`
- `.md`
- `.prompt`

Text must be UTF-8. UTF-8 with BOM is accepted.

## Structured metadata block (optional)

Prompt files may start with a metadata block. `MiniMaxStructuredPromptV20` uses it to prefill the structured fields when the file is selected:

```text
---
Genre: Melodic Techno
Tempo: Midtempo (100-120 BPM)
Meter: 4/4 (common time)
Key: A minor
Lyrics: sparse
Language: English
Voice: female vocal, airy
Theme: escape into the night
Length: 4-5 minutes
---
Free text describing the track in more detail.
```

- The block must be the very first thing in the file, delimited by lines containing only `---`.
- Keys are case-insensitive; aliases such as `BPM`, `Meter`, `Taktart`, `Time signature`, `Tonart`, `Sprache`, `Stimme`, `Lyrics theme` and `Song length` are accepted. Unknown keys are ignored.
- Lyrics values are normalized to `yes` / `sparse` / `only voice - no words` / `instrumental` where recognizable (`ja`, `no`, `wenig`, `wordless`, `vocalise`, …).
- Everything after the closing `---` (or the whole file, if there is no block) is the **further description**.
- Files without a metadata block are fully supported: all fields default to `custom` and the whole file is used as the description.
- Every prefilled field can be overridden in the node; `custom` leaves that part out of the LLM prompt entirely.

The bundled library ships with metadata for all 239 user prompts; regenerate it with:

```bash
python scripts/annotate_prompt_metadata.py --dry-run
python scripts/annotate_prompt_metadata.py
```

## Refreshing the dropdown

The browser extension refreshes when source/directory values change and also adds a **Refresh prompt lists** button. Use it after creating, renaming or deleting files while ComfyUI is already open. Selecting a prompt file prefills the structured fields of `MiniMaxStructuredPromptV20` via the `/minimax_music_toolkit/prompt_metadata` route.

## Cache behavior

File content is fingerprinted. If a selected file is edited but keeps the same filename, ComfyUI sees the changed fingerprint and recomputes the prompt node.

This is separate from an LLM runtime's own KV/prompt cache.

## Safety and validation

The loader:

- rejects missing/empty directories;
- rejects unsupported extensions;
- rejects files larger than 2 MiB;
- rejects invalid UTF-8;
- rejects absolute selections and `..` traversal outside the configured root;
- ignores symlinks that resolve outside the configured library root;
- returns clear user-facing errors instead of silently substituting another prompt.

## Adding bundled user prompts

Create a descriptive UTF-8 file under a category, for example:

```text
prompts/user/house/my-house-prompt.txt
```

After restarting or refreshing the prompt list, it appears under its directory label as an indented entry:

```text
house/
    my-house-prompt.txt
```

Every bundled prompt follows the same unified format: a metadata block with only the canonical fields (Genre, Tempo, Meter, Key, Lyrics, Language, Voice, Theme, Length — omit fields that should stay `custom`) plus a description that never repeats what the fields already express (no BPM, time signature, key, lyric mode, voice gender, language or duration in the free text). Tempo values are curated BPM ranges (Slow 40-70 through Very fast 175-200), never single fixed values; meter values are curated time signatures (4/4 (common time) through free time / rubato).

## Adding system prompts

Place alternate system prompts in:

```text
prompts/system/
```

A system prompt should document the output contract expected by your downstream parser. The bundled production prompt currently expects Caption → Lyrics → Title → Image Prompt.

## Current bundled library

The v2.0.5 repository contains **239 user prompt files** across:

`african`, `alternative`, `ambient`, `asian`, `blues`, `cinematic`, `classical`, `comedy`, `country`, `disco`, `edm`, `electronic`, `european`, `folk`, `funk`, `gospel`, `hiphop`, `house`, `jazz`, `kids`, `latin`, `meditation`, `metal`, `musical`, `pop`, `punk`, `reggae`, `rock`, `seasonal`, `soul`, and `world`.

All 95 files were unified in v2.0.3: every file carries a canonical metadata block, near-duplicates were consolidated (EDM dance anthem, minimal electronic German vocals, absurd German novelty, chillout guitar, heavy metal moved from `rock/` to `metal/`), the free text no longer repeats anything a structured field can express, and the library covers world styles from Asia (K-Pop, City Pop, Chinese/Indian traditional, Bollywood), Europe (Flamenco, Fado, Chanson, Schlager, Klezmer, Balkan), Africa (Afrobeats, Amapiano, Ethio-Jazz, Highlife, Desert Blues) and Latin America (Bossa Nova, Samba, Salsa, Cumbia, Tango, Reggaeton, Bachata) alongside the classic Western and electronic genres.

In v2.0.5 the library was expanded to 239 templates and every template gained the canonical **Meter** (time signature) field. New categories cover blues, country, disco, gospel, kids, meditation, musical, punk, seasonal, soul, cinematic, and world music; the existing categories gained dozens of new subgenres (UK drill, phonk, cloud rap, dubstep, hardstyle, big room, eurodance, future bass, goa trance, acid/french/disco house, Berlin school, vaporwave, chiptune, IDM, EBM, electro swing, bebop, cool jazz, dixieland, swing, gypsy jazz, baroque, choral, string quartet, minimalism, death/black/folk/nu metal, metalcore, djent, britpop, new wave, shoegaze, garage rock, psychedelic rock, surf rock, rockabilly, post-rock, stoner rock, cumbia, merengue, son cubano, bachata, dancehall, rocksteady, ska, enka, mandopop, gqom, soukous, and many more). The structured-field vocabulary was extended to match: the curated genre, voice and language lists now cover the full world map, the key list follows the circle of fifths starting with the minor keys, and the new time-signature combo offers common, odd and free meters.

The production system prompt is stored only in `prompts/system/minimax-music3-production.txt`; avoid duplicating that long prompt in Python source.

## Implementation notes for developers

The dropdown is populated through the toolkit's `/minimax_music_toolkit/prompt_files` route and `web/prompt_library.js` / `web/structured_prompt.js`. It lists the files alphabetically with each directory shown once as a display-only group label; selecting a directory label keeps the previous file selection. Because the choices are dynamic, the node performs authoritative path/file validation at execution time rather than assuming a saved combo value is permanently valid.

`IS_CHANGED` includes a content fingerprint for file-backed prompts, so an edit to a selected file invalidates ComfyUI caching even when its filename is unchanged.

The selected external path refers to the filesystem of the machine running ComfyUI. A generic browser-side server filesystem explorer is intentionally not exposed by default; typed/configured server paths are the safer baseline for local and remote ComfyUI deployments.
