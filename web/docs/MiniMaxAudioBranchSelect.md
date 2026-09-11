# Audio Branch Select (lazy)

Chooses **which audio branch** the workflow uses, explicitly, and uses ComfyUI's
lazy evaluation so only the needed branch is executed.

## Profiles

- **Keep original** — the input is passed through unchanged. No replacement
  branch is requested, so a restoration or reconstruction branch does not run at
  all.
- **Careful restore** — a restored branch (`restored_audio`) is blended into the
  original with the explicit `mix`.
- **Reconstruct bandwidth** — a reconstruction branch (`bandwidth_audio`) is
  blended in.

The bundled example stores "strong PRE low-pass + full FlashSR replacement".
That is a deliberate choice for damaged sources; it is **not** the default for
clean ones. This node makes the decision visible instead of implicit.

## Output contract

The output **sample rate and length always come from `original_audio`**, never
from the replacement branch. A replacement at another rate is resampled, and a
replacement of another length is trimmed or padded; every such action is listed
in `branch_report_json`. This is the trap the older `Original SRC only` mode had:
it took rate and length from the replacement input, so skipping the replacement
silently changed them.

## Inputs

- `original_audio` (required) — the source.
- `restored_audio`, `bandwidth_audio` (optional, lazy) — connected only when the
  chosen profile needs them. `check_lazy_status()` asks ComfyUI for exactly the
  missing ones, so an unconnected or unneeded branch is never computed.

## Preview

`preview_seconds` (0 = full render) trims the **result** to a 15–30 s window
(requested values are clamped to that range, longer values included). Use it to
judge parameters cheaply, then run the same setup with `preview_seconds = 0` for
the full render.

Beware of the honest limit: the preview trims after the chosen branch has run, so
it saves the **save/encode** stages, not the branch's own inference. Only the
*other* branches are skipped — and that is what lazy evaluation is for.

## Outputs

- `audio` — the selected branch as `[B, C, T]` at the original rate and length.
- `branch_report_json` — schema `minimax_audio_branch_v1`: profile, source
  metadata, replacement source, mix, output shape, preview window and every note
  (resampled, trimmed, padded, mix = 0, preview applied).
- `info` — a one-line summary.
