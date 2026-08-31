# Maintainer publishing guide

Repository target:

https://github.com/jplenio/ComfyUI-MiniMax-Music-Production-Toolkit

## GitHub first publication

Create an **empty** public repository named:

```text
ComfyUI-MiniMax-Music-Production-Toolkit
```

Do not initialize it with another README, license or `.gitignore`, because those files already exist locally.

From the extracted release folder:

```bash
git init
git add .
git commit -m "Release v1.0.1"
git branch -M main
git remote add origin https://github.com/jplenio/ComfyUI-MiniMax-Music-Production-Toolkit.git
git push -u origin main
```

Alternatively, with GitHub CLI after authentication:

```bash
gh repo create jplenio/ComfyUI-MiniMax-Music-Production-Toolkit --public --source=. --remote=origin --push
```

## Comfy Registry publisher

A Comfy Registry **Publisher ID** is created on the Comfy Registry website; it is not automatically the GitHub username. It is globally unique and cannot be changed later.

Recommended publisher ID for this repository:

```text
jplenio
```

The repository's `pyproject.toml` is already prepared with:

```toml
[tool.comfy]
PublisherId = "jplenio"
DisplayName = "MiniMax Music Production Toolkit"
```

If `jplenio` is unavailable in the Registry, choose another permanent publisher ID and change `PublisherId` before the first Registry publish.

After creating the publisher, create a **Registry Publishing API Key** for it.

## GitHub Action secret

In the GitHub repository:

**Settings → Secrets and variables → Actions → New repository secret**

Name:

```text
REGISTRY_ACCESS_TOKEN
```

Value: the Comfy Registry publishing API key.

`.github/workflows/publish_action.yml` can then publish manually or when a GitHub Release is published.

## Manual Registry publish

Install Comfy CLI and run from the repository root:

```bash
comfy node publish
```

The CLI prompts for the publisher API key.

## Versioning

Registry versions are immutable. Before each new release:

1. update `VERSION`;
2. update `project_info.py`;
3. update `pyproject.toml` version;
4. add a `CHANGELOG.md` entry;
5. run `python scripts/validate_release.py` and tests;
6. commit/tag/release;
7. publish the matching Registry version.

## Build release assets

Before creating a GitHub Release, build and validate the release files from the repository root:

```bash
python scripts/package_release.py --output-dir dist
```

The command runs the static release validator and unit tests, then creates:

```text
ComfyUI-MiniMax-Music-Production-Toolkit-vX.Y.Z.zip
MiniMax_Music3_Production_Toolkit_vX.Y.Z.json
SHA256SUMS.txt
```

Upload these files as GitHub Release assets. The ZIP contains a single top-level repository folder and excludes Python caches, VCS state and generated release archives.
