# MiniMax Square Image Size

Produces equal width/height values for square album artwork using common presets or a custom size.

**Node ID:** `MiniMaxSquareImageSize`  
**Category:** `MiniMax Music Production Toolkit/artwork`

## Inputs

### Required

- **`size_preset`** (choice: `256x256`, `512x512`, `1024x1024`, `1536x1536`, `2048x2048`, `3072x3072`, `3096x3096`, `custom`) — Square artwork resolution preset. Larger images cost more VRAM/time. Choose custom to use custom_size instead of a fixed preset. The FLUX.2 latent stage quantizes dimensions to multiples of 16, so `3096x3096` is effectively rendered as 3088 — prefer `3072x3072` for an exact size.
- **`custom_size`** (`INT`) — Square width/height in pixels used only when size_preset is custom. Values are kept equal to guarantee a 1:1 cover image.

## Outputs

- **`width`** (`INT`)
- **`height`** (`INT`)

## Usage notes

Start with the defaults used by the bundled example workflow unless you have a specific reason to change this stage. Hover each input label in ComfyUI for parameter guidance.
