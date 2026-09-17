# Audio examples with SoundCloud

The project uses **SoundCloud for audio streaming** and **GitHub Pages for presentation**. This keeps large MP3/FLAC catalogs out of Git history while still giving visitors a polished listening page with cover art and generation metadata.

The prepared demo catalog currently contains **25 tracks** derived from real production metadata. Existing SoundCloud URLs are kept in `docs/demo-tracks.js`; newly added tracks may intentionally have an empty `soundcloudUrl` until their SoundCloud upload exists.

## Files

- `docs/index.html` — responsive demo page with search, filters and expandable generation details.
- `docs/demo-tracks.js` — public track metadata, playlist URL and SoundCloud track URLs.
- `docs/assets/demo-covers/` — local web cover JPGs.
- `scripts/update_demo_catalog.py` — preferred helper for adding/updating demos from production JSON without exposing private production fields.
- `scripts/prepare_demo_covers.py` — prepares all cover filenames currently referenced by the catalog.

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

The helper reads the expected filenames directly from `docs/demo-tracks.js`, center-crops and resizes matching images to 960×960, and stores progressive JPEGs. It is therefore not tied to a fixed track count.

If a cover is missing, the demo page falls back gracefully instead of displaying a broken image.

## What the page shows

Each demo presents the generated cover, title, Pelenio as artist, collection/album, genre, instrumental/vocal type, language for vocal tracks, BPM, key/scale and a concise musical description. “Generation details” additionally exposes the simple starting prompt, seed, MiniMax sampler settings, release target and the generated cover concept.

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
