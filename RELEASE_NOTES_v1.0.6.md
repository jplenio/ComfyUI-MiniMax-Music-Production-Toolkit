# MiniMax Music Production Toolkit 1.0.6

This release fixes the bundled workflow validation error in **Save Cover JPG – same song name** and includes the repository's expanded prompt library and SoundCloud demo-page updates.

## Fixed

- Corrected the serialized input order of `Save Image Smart Prefix`.
- `collision_mode` now maps to its choice widget again (`auto_increment` by default).
- `jpeg_quality` now maps to its integer widget again (`95` by default).
- The connected `title` and `audio_tags_json` sockets remain intact, so artwork still uses the same `Album - Title` basename as FLAC, MP3 and the centralized production JSON.
- `scripts/build_public_workflow.py` now normalizes this node automatically and repairs target-slot indices after reordering.
- Release validation and unit tests now assert the exact artwork-saver slot order and widget types.

## Included in this release

- 62 bundled user prompt files, including the additional alternative, EDM, electronic, house, rock and metal prompts supplied with the release package.
- SoundCloud demo-gallery configuration and public demo links already present in the repository.
- Existing v1.0.5 output naming, centralized JSON, metadata, artwork, audio processing and LLM settings are otherwise retained.

## Upgrade note

If an older v1.0.5 workflow already shows the `collision_mode` / `jpeg_quality` validation error, load the bundled v1.0.6 example workflow. Recreating only the `Save Image Smart Prefix` node and reconnecting its inputs also resolves the stale serialized slot order.
