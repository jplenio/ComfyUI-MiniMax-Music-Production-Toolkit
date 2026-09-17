# YuE2 Cover Studio · 3 validate & apply

Produces the score that finally reaches YuE2. YuE2 never receives unvalidated
model output.

Order of work:

1. **Exact knobs first.** `key_change` transposes and `tempo_change` rewrites the
   tempo, or `melody_only` removes the quoted chord symbols. Each rewrite is
   checked against the native ABC structure; a knob that cannot be applied is
   reported and skipped instead of producing a broken score.
2. **The model answer, if there is one.** The JSON is parsed, the ABC extracted,
   structurally validated (headers, fences, prose, empty voice blocks, native
   dialect) and compared with the score the model actually received.
3. **The guard.** When the profile pins the structure or the tempo, a model score
   that changed the bar/meter grid or the tempo is rejected. At the faithful end
   of the slider the same applies to the melody and the chords: with no allowed
   variation, a score that rewrites a single note or chord is rejected too, so
   *Interpretation Freedom 0* really returns the source score.
4. **Repair, once.** An optional second answer is tried only when the first one
   failed, and it passes the same validation.
5. **Fallback.** If nothing valid remains, the deterministic result is used. It is
   always a valid native score, so a bad model answer costs reinterpretation, not
   the render.

`cover_abc` replaces the score in the existing cover chain. `locked_lyrics`
carries the verbatim words when the lyrics policy asks for them (empty
otherwise); connect it to the parser's `cover_lyrics_lock` input. `studio_report_json`
records the profile, the plan, the applied changes, the warnings, the measured
lyrics/melody fit and - with `advanced_mode` - the final score.
`warnings` is a flat string for quick inspection.

With the studio switched off or unconnected, the incoming score is returned byte
for byte, so an existing workflow keeps behaving exactly as before.
See [the YuE2 guide](../../docs/YUE2.md#yue2-cover-studio).

## Inputs

- **studio_json** - the same profile the plan step produced; it decides what may be applied.
- **transform_text** (optional) - the model's rewritten score. It is validated against the
  profile and the native ABC structure, and the deterministic result is used when it does not
  hold up.
- **repair_text** (optional) - an optional second model answer, used only to repair a rejected
  score.
- **enabled** - off passes the original score through unchanged.

The node never re-orders phrases on its own and never invents a voice that the source lacks.
