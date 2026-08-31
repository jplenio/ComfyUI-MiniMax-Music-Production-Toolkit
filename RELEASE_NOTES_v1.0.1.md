# MiniMax Music Production Toolkit 1.0.1

This hotfix repairs the public example workflow's embedded MiniMax Music 3 subgraph.

## Fixed

- Restored all subgraph boundary links between the parent MiniMax node and its internal model, text encoder, sampler and VAE nodes.
- Fixes ComfyUI errors such as `No link found in parent graph for id [37:6] slot [0] unet_name`.
- Release validation now recursively checks subgraph link integrity so this class of packaging regression is caught before a release is built.
- Public workflow version metadata is now generated from the repository `VERSION` file.

No audio-processing defaults or generation defaults were changed.
