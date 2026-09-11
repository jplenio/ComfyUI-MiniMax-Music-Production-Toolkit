# MiniMax Music Production Toolkit 2.5

Release 2.5 brings a clearer workflow, more efficient everyday operation and a
complete mastering section to music generation and existing-audio enhancement.

## Highlights

- Redesigned, numbered working areas make both workflows easier to navigate.
- Auto-EQ is on by default, with a gentle Warm tilt preset (35%, maximum 2 dB).
- A separate manual 8-band EQ stays editable with Auto-EQ on or off.
- Stereo-linked compression, LUFS targeting and true-peak limiting finish the
  release signal. Compression can be disabled independently of the limiter.
- Final output defaults to 44.1 kHz; 48 kHz is selectable before mastering.
- Improvements throughout memory/resource handling, audio processing, downloads,
  prompts, metadata and file output support a wider range of computers.

## Updating

Update the toolkit and dependencies in the ComfyUI environment, restart ComfyUI
and refresh the browser. Open the bundled production or AudioEnhance JSON again.
The redesigned examples now have the original filenames; the temporary optimized
copies and the older example contents are retired. Keep personal workflows under
separate filenames. Existing saved workflows are not silently replaced.

The production release chain now uses dynamic mastering in place of static gain;
the resulting audio can differ. Auto-EQ can be switched off. Manual EQ starts
neutral. Check the master at matched loudness; target loudness may remain below
the requested value when peak/gain-reduction limits take priority.

Mastering runs on CPU. Generation models still require adequate memory; the
bundled large LLM settings should be reduced for smaller machines. This release
does not promise that every model fits every GPU.

## Distribution

The release package contains the toolkit and both canonical workflows. Standalone
versioned workflow JSON files and SHA-256 checksums accompany the ZIP. Model
weights are not included. See INSTALLATION.md for dependencies and model setup.

Prepared locally for tag `v2.5.0`. Building these assets does not publish a GitHub
release or submit the package to Comfy Registry.

## Local validation

The Python suite completed 809 tests with no failures and one skipped test
(optional metadata dependency unavailable in the validation interpreter).
The EQ coefficient parity, prompt UI, workflow migration and headless EQ browser
tests passed. Release structure/version/privacy validation passed as well.
This does not constitute a fresh full-model GPU generation or listening test;
the workflows were previously tested interactively by the maintainer.
