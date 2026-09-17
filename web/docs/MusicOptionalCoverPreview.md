# Cover preview · follows production choice

Previews and passes through cover artwork when enabled. When disabled it clears
the preview and skips image generation. Connect the same central cover switch
to this preview, the cover saver and the model check's FLUX.2 input.

This replaces the always-active native image preview in the dual-model workflow;
otherwise the preview could render artwork even when saving it was disabled.

## Inputs and output

- **images** - artwork to preview. Lazy: only evaluated while `enabled` is on, so a disabled
  cover does not render anything just to be discarded.
- **enabled** - connect the central artwork switch here.

The artwork is passed through unchanged, so the saver behind it still receives the image.
