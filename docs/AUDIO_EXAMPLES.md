# Audio examples with SoundCloud

The project uses **SoundCloud for audio streaming** and **GitHub Pages for presentation**. This keeps large MP3/FLAC catalogs out of Git history while still giving visitors a polished listening page with cover art and generation metadata.

The prepared demo catalog currently contains **35 generated songs** derived from real production metadata, plus a second category with **8 cover songs** from 3 original tracks. Existing SoundCloud URLs are kept in the catalog files; newly added tracks may intentionally have an empty `soundcloudUrl` until their SoundCloud upload exists.

## Files

- `docs/index.html` — responsive demo page with a category switch, search, filters and expandable generation details.
- `docs/demo-tracks.js` — public metadata, playlist URL and SoundCloud track URLs for the generated songs.
- `docs/demo-covers.js` — the cover songs: one original track with the covers made from it underneath.
- `docs/assets/demo-covers/` — local web cover JPGs.
- `scripts/update_demo_catalog.py` — preferred helper for adding/updating generated songs from production JSON without exposing private production fields.
- `scripts/update_cover_demo_catalog.py` — the same for cover songs, grouped by the source file they were made from.
- `scripts/prepare_demo_covers.py` — prepares all cover filenames currently referenced by either catalog.

## Recommended update workflow

Production JSON files contain much more than should be exposed publicly, including the long system prompt and potentially machine-specific artifact paths. Do **not** copy production JSON directly into `docs/`.

Instead run:

```bash
python scripts/update_demo_catalog.py "D:/exports/json/*.json" --cover-source "D:/exports/artwork"
```

The helper extracts only public-facing fields such as title, collection, style, BPM, key/scale, starting user prompt, seed, sampler/release metadata and cover concept. For an existing matching track it preserves the current `soundcloudUrl`.

Use `--dry-run` first when processing a large directory:

```bash
python scripts/update_demo_catalog.py "D:/exports/json" --cover-source "D:/exports/artwork" --dry-run
```

## Cover song demos

The page has two categories, selected at the top: the generated songs, and the cover songs. A cover demo is organised around the **original**: the original track is listed first with its own SoundCloud slot, and the covers made from it appear underneath, side by side.

```bash
python scripts/update_cover_demo_catalog.py --source "D:/exports/Cover-Demos-github"
```

`--source` is a toolkit output folder, i.e. it contains `log/*.json` next to `artwork/` and the audio folders. Every `log/*.json` that records a cover run becomes one entry, grouped by the source file it was made from. The helper copies only recorded facts: the source file name and its **measured** tempo and length, the chosen style template, the musical fields, the cover and lyrics mode, the lead instrument, model, seed, sampler settings, target duration and the release sample rate. Absolute paths and the long prompt never reach the catalog.

Three fields are filled in by hand and survive every re-run of the generator:

- `soundcloudUrl` — on the original and on each cover, exactly as in the generated-song catalog.
- `comment` — your own note about an original track. Shown under its title when it is not empty; the page renders nothing while it is empty.
- `freedom` — the interpretation freedom used for that cover. The canonical production JSON does **not** record it, so the generator cannot read it; add it if you want it on the page.

Covers of one original are separate runs. The toolkit numbers colliding export file names with `_001`, `_002` …, and the page shows that as “Take 1”, “Take 2”, … — the export title itself is identical for all of them, so use `freedom` and the file name to tell them apart.

## SoundCloud links

After a new track is uploaded, open `docs/demo-tracks.js` and paste the **normal public SoundCloud track URL** into its `soundcloudUrl` field:

```javascript
"soundcloudUrl": "https://soundcloud.com/your-account/your-track"
```

No iframe code is required. The page creates the SoundCloud player automatically.

The playlist button is controlled by `MINIMAX_DEMO_CONFIG.soundcloudPlaylistUrl` in the same file.

An empty `soundcloudUrl` is valid while preparing a demo; the page shows a placeholder until the link is added.

## Cover art

The cards reference local files in `docs/assets/demo-covers/`. The current catalog can be prepared from a source artwork directory with:

```bash
python scripts/prepare_demo_covers.py --source "D:/path/to/generated/artwork"
```

The helper reads the expected filenames directly from `docs/demo-tracks.js` and `docs/demo-covers.js`, center-crops and resizes matching images to 960×960, and stores progressive JPEGs. It is therefore not tied to a fixed track count. Images that are already prepared are skipped, so a run for a new batch does not need the artwork of the earlier ones; pass `--force` to prepare everything again.

If a cover is missing, the demo page falls back gracefully instead of displaying a broken image.

## What the page shows

Each generated song presents the generated cover, title, Pelenio as artist, collection/album, genre, instrumental/vocal type, language for vocal tracks, BPM, key/scale and a concise musical description. “Generation details” additionally exposes the simple starting prompt, seed, MiniMax sampler settings, release target and the generated cover concept.

Each cover song card shows its take number, genre, lyrics mode, lead instrument, conditioning mode, target tempo band and — if you filled it in — the interpretation freedom, plus the style template and a run-details block with seed, sampler settings, target duration, release rate and the score edits the cover performed. Under the original track the page shows the source file name and the tempo and length **measured from that file**.

The long system prompt, raw LLM response and machine-specific paths are intentionally **not** exposed on the public demo page.

## Enable GitHub Pages

In GitHub open **Repository → Settings → Pages**. Under **Build and deployment** choose:

- Source: `Deploy from a branch`
- Branch: `main`
- Folder: `/docs`

The intended public URL is:

`https://jplenio.github.io/ComfyUI-MiniMax-Music-Production-Toolkit/`

After changing the page, remember that `git commit` is only local. Run `git push`, wait for the Pages deployment in **Actions**, then hard-refresh the browser if old JavaScript is cached.

## Why not store the audio in Git?

Audio files quickly add hundreds of megabytes to repository history. SoundCloud is the listening backend; GitHub stores only the lightweight page/configuration and compressed cover images. A small downloadable sample pack can still be attached to a GitHub Release if desired.
