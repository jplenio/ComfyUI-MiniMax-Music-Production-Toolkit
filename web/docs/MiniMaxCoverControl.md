# FLUX.2 Cover — On / Off

**Node ID:** `MiniMaxCoverControl`

One switch for optional FLUX.2 artwork; **enabled defaults to true**.
In the bundled Production workflow it sits in **05 · ILLUSTRATE / Cover artwork**,
together with the cover nodes it controls: its `cover_artwork_enabled` output feeds the
image saver and the FLUX.2 preflight download right there. Search for
**FLUX.2 Cover** to add it
to an existing workflow. An update does not insert nodes into personal workflows;
open the updated bundled workflow or add and connect the switch as described below.
Connect its `cover_artwork_enabled` BOOLEAN output to both:

- `SaveImageSmartPrefix.enabled`
- `MiniMaxModelAutodownload.flux2_models`

Off skips FLUX preflight downloads and the saver's lazy image input. Audio
exports receive an empty artwork path and continue without a generated cover.
On preserves the existing render/save/embed chain. Previously written JPGs are
not deleted. The switch does not unload cached models or disable other image
output nodes that independently request the same branch.

Keep the cover saver active. Some ComfyUI versions validate missing model
dropdowns before execution even for lazy branches; see `docs/LLM_PROVIDERS.md` for the
workaround when FLUX models are not installed.
