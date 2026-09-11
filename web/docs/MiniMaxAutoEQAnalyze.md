# Auto-EQ – Analyze / Propose

`enabled=false` skips analysis and returns neutral EQ settings, even without a
reference. Existing workflows default to enabled. In the optimized workflows,
Auto-EQ starts on in the 2.5 workflows; the separate manual EQ remains independently editable.

Proposes conservative EQ settings; **does not process audio**. Feed the same
source into this node and Parametric EQ, then connect the settings output to EQ.
Reference mode requires a reference AUDIO. Warm/Bright tilt are explicit creative
choices, not an objectively correct spectrum or room correction.

Start at 50% strength, 3 dB maximum and six bands or fewer. Analysis removes
level differences, compares channel power (safe for anti-phase stereo) and
ignores unreliable frequencies. Silence/short or narrow-band signals return
unity with an explanation. Audition and edit; matching unrelated arrangements
does not guarantee better sound.

One reference can serve all source batch items, or reference/source batch counts
must match. Multiple source items produce a `minimax_eq_batch_v1` envelope that
the Parametric EQ handles directly. Outputs are settings JSON, analysis JSON and
status. No models/GPU required. Details: `AUDIO_MASTERING.md`.
