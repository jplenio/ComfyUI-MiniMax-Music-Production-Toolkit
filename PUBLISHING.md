# Maintainer publishing guide

Repository:

https://github.com/jplenio/ComfyUI-MiniMax-Music-Production-Toolkit

Comfy Publisher ID configured in `pyproject.toml`:

```text
jplenio
```

## Release checklist

Before every release:

1. Update `VERSION`.
2. Update `[project].version` in `pyproject.toml`.
3. Update `project_info.py`.
4. Update `CITATION.cff`.
5. Add a `CHANGELOG.md` entry.
6. Add `RELEASE_NOTES_vX.Y.Z.md`.
7. Make sure the example workflow contains the intended public/generic metadata and matching workflow version.
8. Run validation/tests.
9. Build release assets.
10. Commit/push.
11. Create the matching GitHub Release/tag.
12. Let the GitHub Action publish the same immutable version to the Comfy Registry.

## Validation

From the repository root:

```bash
python scripts/validate_release.py
python -m unittest discover -s tests -v
```

The release validator checks required files, Python syntax, version consistency, publisher metadata, example-workflow links including subgraph boundary links, prompt-library integrity, privacy/placeholders and node documentation.

## Build release assets

```bash
python scripts/package_release.py --output-dir dist
```

This runs validation/tests first and creates:

```text
ComfyUI-MiniMax-Music-Production-Toolkit-vX.Y.Z.zip
MiniMax_Music3_Production_Toolkit_vX.Y.Z.json
SHA256SUMS.txt
```

The ZIP excludes VCS state, Python caches and already-built ZIP files.

## Commit v1.0.5

For an existing checkout:

```bash
git add -A
git commit -m "Release v1.0.5"
git push
```

Do not re-run `git init` for an already existing repository.

## GitHub Release

Create a new GitHub Release with:

```text
Tag:   v1.0.5
Title: MiniMax Music Production Toolkit 1.0.5
```

Use `RELEASE_NOTES_v1.0.5.md` as the release description and upload the three generated release assets.

The Git tag uses a leading `v`; the package/Registry version remains `1.0.5` without the leading `v`.

## Comfy Registry

The project is configured with:

```toml
[tool.comfy]
PublisherId = "jplenio"
DisplayName = "MiniMax Music Production Toolkit"
```

Create a Registry Publishing API Key for the publisher and store it in GitHub:

**Repository → Settings → Secrets and variables → Actions → New repository secret**

Secret name:

```text
REGISTRY_ACCESS_TOKEN
```

`.github/workflows/publish_action.yml` runs on a published GitHub Release or manually through **Actions → Publish to Comfy Registry → Run workflow**.

Registry versions are immutable. Never republish different contents under an already published version; bump the version instead.

## Manual Registry publish

If needed, use Comfy CLI from the repository root:

```bash
comfy node publish
```

## GitHub Pages audio demos

The repository includes `docs/index.html` for SoundCloud-backed listening examples.

After adding normal SoundCloud track URLs to the `tracks` array, enable Pages:

**Settings → Pages → Build and deployment**

- Source: `Deploy from a branch`
- Branch: `main`
- Folder: `/docs`

Expected URL:

https://jplenio.github.io/ComfyUI-MiniMax-Music-Production-Toolkit/

The demo HTML belongs in GitHub source control. Large MP3 catalogs should remain on SoundCloud rather than in Git history.
