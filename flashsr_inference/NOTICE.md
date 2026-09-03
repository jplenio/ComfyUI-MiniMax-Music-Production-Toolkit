# Third-party code bundled in this directory

This directory contains vendored inference code from the following upstream
projects, copied verbatim (except for excluded training data, scripts and
Python caches) so the `MiniMaxFlashSRAudio` node is fully self-contained:

- **FlashSR_Inference** — https://github.com/jakeoneijk/FlashSR_Inference
  Paper: *FlashSR: One-step Versatile Audio Super-resolution via Diffusion
  Distillation*, Jaekwon Im and Juhan Nam, arXiv:2501.10807 (2025).
  Vendored: `FlashSR/` (package code only; `BigVGAN/LibriTTS` training data,
  `parse_scripts` and training scripts were not copied).
- **TorchJaekwon** — https://github.com/jakeoneijk/TorchJaekwon
  Personal research framework by Jaekwon Im, required by FlashSR_Inference.
  Vendored: `TorchJaekwon/` (code only; shell install scripts, notebook
  helpers and developer notes were not copied).

## License status

The upstream repositories do **not** ship a root `LICENSE` file and their
package metadata declares `license = ""`. The components they contain carry
the following per-component licenses:

- `FlashSR/BigVGAN` — MIT (NVIDIA CORPORATION), plus included third-party
  licenses in `BigVGAN/incl_licenses/` (MIT, Apache-2.0, BSD-3-Clause).
- `FlashSR/AudioSR/hifigan` — MIT (Jungil Kong).
- `FlashSR/AudioSR/latent_diffusion/.../text` — MIT (Keith Ito).

If you distribute this package, treat the FlashSR/TorchJaekwon code as
source-available with the authors' names and this notice preserved, and keep
the per-component license files intact. The toolkit does **not** copy the
FlashSR model *weights*; those are downloaded from the official
`jakeoneijk/FlashSR_weights` Hugging Face dataset on first use (see
`models_config.json`).

Please cite the FlashSR paper when using the audio super-resolution stage:

```bibtex
@article{im2025flashsr,
  title={FlashSR: One-step Versatile Audio Super-resolution via Diffusion Distillation},
  author={Im, Jaekwon and Nam, Juhan},
  journal={arXiv preprint arXiv:2501.10807},
  year={2025}
}
```
