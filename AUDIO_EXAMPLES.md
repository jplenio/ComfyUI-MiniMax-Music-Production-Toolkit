# Audio examples with SoundCloud

The project uses **SoundCloud for audio streaming** and **GitHub Pages for presentation**. This keeps large MP3/FLAC catalogs out of Git history while still giving visitors a polished listening page with cover art and generation metadata.

The prepared demo currently contains **17 tracks** derived from real production metadata.

## Files

- `docs/index.html` — responsive demo page with search, filters and expandable generation details
- `docs/demo-tracks.js` — track metadata plus the current SoundCloud playlist/track URLs; edit this when adding or replacing demos
- `docs/assets/demo-covers/` — web-optimized cover JPGs
- `scripts/prepare_demo_covers.py` — optional helper that resizes/copies generated cover art into the correct filenames

## SoundCloud links

The current demo configuration already contains the prepared public SoundCloud URLs. When adding or replacing a demo, open `docs/demo-tracks.js` and paste the **normal public track URL** into its `soundcloudUrl` field:

```javascript
soundcloudUrl: "https://soundcloud.com/your-account/your-track"
```

No iframe code is required. The page creates the SoundCloud player automatically.

The playlist button at the top of the page is controlled by:

```javascript
soundcloudPlaylistUrl: "https://soundcloud.com/your-account/sets/your-playlist"
```

## Add cover art

The cards are already configured with an expected local cover filename. Copy your generated covers to `docs/assets/demo-covers/`. Exact filenames are listed in `docs/assets/demo-covers/README.txt`.

For a lighter repository, 960×960 progressive JPEGs at roughly quality 86 are more than enough for the demo page. If Pillow is available, the included helper can prepare them automatically:

```bash
python scripts/prepare_demo_covers.py --source "/path/to/generated/artwork"
```

A missing cover never produces a broken-image icon; the page falls back to a styled title card.

## What the page shows

Each demo presents the generated cover, title, Pelenio as artist, collection/album, genre, instrumental/vocal type, language for vocal tracks, BPM, key/scale and a short musical description. “Generation details” additionally exposes the simple starting prompt, seed, MiniMax sampler settings, release target and the generated cover concept.

The long system prompt and raw LLM response are intentionally **not** exposed on the public demo page.

## Enable GitHub Pages

In GitHub open **Repository → Settings → Pages**. Under **Build and deployment** choose:

- Source: `Deploy from a branch`
- Branch: `main`
- Folder: `/docs`

The intended URL is:

`https://jplenio.github.io/ComfyUI-MiniMax-Music-Production-Toolkit/`

## Why not store the audio in Git?

Audio files quickly add hundreds of megabytes to repository history. SoundCloud is the listening backend; GitHub only stores the lightweight page, configuration and optionally compressed cover images. A small downloadable sample pack can still be attached to a GitHub Release if desired.
