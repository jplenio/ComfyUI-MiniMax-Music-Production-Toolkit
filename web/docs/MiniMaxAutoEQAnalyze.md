# Auto-EQ – Analyze / Propose

`enabled=false` skips analysis and returns neutral EQ settings, even without a
reference. Existing workflows default to enabled. In the optimized workflows,
Auto-EQ starts on; the separate manual EQ remains independently editable.

**Auto-EQ preset** offers 10 presets plus Custom. All bundled workflows use
**Warm - gentle (workflow default)**: Warm tilt, 35%, maximum 2 dB, four bands,
40–16000 Hz. No reference audio is needed for this preset.
This is the only preset selector: the separate target_mode dropdown is hidden.
The preset sets Warm/Bright/Reference automatically; numerical controls remain
editable. Custom explains the current target; select a preset to change it.
Presets set existing controls and never change enabled or reference connections.
Reference presets need reference audio. Editing values selects Custom; connected
parameter inputs make preset selection read-only. See `docs/EQ_PRESETS.md`.

Proposes conservative EQ settings; **does not process audio**. Feed the same
source into this node and Parametric EQ, then connect the settings output to EQ.
Reference mode requires a reference AUDIO. Warm/Bright tilt are explicit creative
choices, not an objectively correct spectrum or room correction.

If Reference track is selected without reference audio, the node warns and
returns neutral EQ settings instead of aborting the production. The report says
`skipped_missing_reference`; no spectrum analysis or matching was performed.
Choose **Warm - gentle (workflow default)** to use Auto-EQ without a reference.
The preset panel also indicates an unconnected reference input.

Start at 50% strength, 3 dB maximum and six bands or fewer. Analysis removes
level differences, compares channel power (safe for anti-phase stereo) and
ignores unreliable frequencies. Silence/short or narrow-band signals return
unity with an explanation. Audition and edit; matching unrelated arrangements
does not guarantee better sound.

One reference can serve all source batch items, or reference/source batch counts
must match. Multiple source items produce a `minimax_eq_batch_v1` envelope that
the Parametric EQ handles directly. Outputs are settings JSON, analysis JSON and
status. No models/GPU required. Details: `docs/AUDIO_MASTERING.md`.
