# Release Notes – v3.0.1

Release date: 2026-09-16

## Summary

More control over the sound of your YuE2, YuE2 Cover and MiniMax productions:
**10 Auto-EQ presets, 24 manual EQ presets and experimental artifact reduction**.
The main workflow returns to **Warm - gentle** Auto-EQ, requiring no reference
audio. YuE2 Cover and its ABC-informed arrangement remain the flagship 3.0 feature.

## Added

- **EQ presets with explanations and Custom.** Ten Auto-EQ recipes cover Warm,
  Bright and Reference targets; 24 manual recipes include Flat and two clearly
  labeled **YuE2 - Smooth highs** options. Individual controls stay editable,
  custom settings persist, and the manual editor supports Undo. These are
  starting points to audition, not automatic fixes for every recording.
- **Experimental AI Audio Artifact Reduction.** A new node attenuates brief
  spectral whistles/spikes using a local time/frequency outlier heuristic,
  linked channel masks, transient protection and a bounded reduction amount.
  No new models or downloads are required. Analyze-only mode, candidate reports
  and a removed-audio output help assess what it detects.
- **An independent production switch.** In the main YuE2/MM3 workflow, artifact
  reduction runs after optional Refinement and before Mastering. Its CHOOSE
  switch defaults to **on**, sensitivity to **Balanced**, maximum reduction to
  **3 dB**. It can run with Mastering off. The original-generation exports stay
  upstream of cleanup, and the canonical Production JSON records the report.

## Changed and fixed

- Auto-EQ now has **one visible preset selector**. The former target_mode
  dropdown remains an internal serialized value for saved workflow/API
  compatibility. Numerical controls remain available.
- All three bundled workflows use **Warm - gentle (workflow default)**:
  Warm tilt, 35% strength, maximum 2 dB, four bands, 40–16000 Hz. Manual EQ starts
  **Flat**. A newly added standalone Auto-EQ node keeps its existing
  **Reference - balanced** defaults.
- Reference matching without reference audio now warns, records
  `skipped_missing_reference` and emits neutral EQ settings instead of aborting
  production. Connect a reference or select a Warm/Bright preset to apply EQ.
- Consolidated the twelve 2.x release notes into [one history file](RELEASE_NOTES_v2.x.md).
  Corrected installation, workflow, prompt/report and production-metadata docs.
- Included an [App-Mode concept](APP_MODE_KONZEPT.md) and
  [configuration selection catalog](APP_MODE_KONFIGURATIONSKATALOG.md).
  These are planning documents; this release does not add an App-Mode interface.

## Upgrade notes

Update the toolkit, restart ComfyUI and reload its browser page so the new
frontend controls load. Open the bundled
[Yue2_MM3_Production_Toolkit.json](example_workflows/Yue2_MM3_Production_Toolkit.json)
to get the artifact-reduction branch, its central switch and the new defaults.
Existing saved workflows retain their stored settings; they are not silently
rewired or reset. The classic MiniMax and Audio Enhancement Lab examples retain
their existing audio topology and gain the shared EQ preset controls.

The disabled preset field on **Apply Auto-EQ** belongs to its read-only EQ
editor; the linked analyzer output supplies the actual curve. Make manual
adjustments in the separate Manual EQ node.

Artifact reduction is experimental: candidates are not confirmed AI errors,
and wanted musical detail may also be detected. It does not reconstruct wrong
notes, lyrics or dropouts, nor eliminate every watery or metallic artifact.
Compare the processed and removed signals, and reduce its strength or switch it
off when it removes wanted material. See [artifact reduction](ARTIFACT_REDUCTION.md)
and the [EQ preset guide](EQ_PRESETS.md).

No breaking removal of existing node APIs is intended. New control/report
connections are appended, preserving existing output positions.

## Assets

- `ComfyUI-MiniMax-Music-Production-Toolkit-v3.0.1.zip`
- `Yue2_MM3_Production_Toolkit_v3.0.1.json`
- `MiniMax_Music3_Production_Toolkit_v3.0.1.json`
- `MiniMax_Music3_Production_Toolkit_AudioEnhance_v3.0.1.json`
- `SHA256SUMS.txt`
