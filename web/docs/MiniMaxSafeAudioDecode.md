# MiniMax Safe Audio Decode

Checks audio latents before decoding and validates the decoded waveform and
normalization. Valid audio follows ComfyUI's standard `std * 5`, minimum-divisor-1
gain rule. Returns AUDIO with the latent's explicit sample rate, or the VAE rate.

- `samples`: audio latent tensor `[batch, channels, frames]`.
- `vae`: audio VAE (the production workflow uses MiniMax Music 3 DAV).
- `tiled`: use tiled decoding (default on).
- `tile_size`: latent frames per tile, default 512.
- `overlap`: default 64; must be smaller than the tile size.

Invalid sampler latents stop decoding immediately. If latents are finite but
decoded audio or normalization contains NaN/Infinity, retry **once** with a smaller
tile (at most 512, overlap at most 32). The failed buffer is released first.
This can recover tile-dependent decoder failures; it cannot repair corrupt weights
or invalid sampler output. A failed retry is reported before audio export.

Bad samples are never replaced with silence. Music sampling is not repeated;
global GPU settings, precision settings, model patches and weights stay untouched.
Cancellation and other decoder exceptions propagate. The host VAE's public
`decode` / `decode_tiled` methods and its out-of-memory handling are used.

Both decoder alternatives inside the bundled MiniMax Music 3 subgraph use this
node. The existing `tiled_decode` switch and configured tile size are preserved.
Personal workflows can replace their core audio decoder with this node, keeping
the same LATENT, VAE and AUDIO connections.
