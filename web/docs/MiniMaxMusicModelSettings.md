# Music settings

Connect the same model profile as the song generator. Both sampler groups remain
editable; only the selected model's group is used. Seeds, duration ceiling,
text-generation settings and effective sampler values are stored in
`settings_json`. Connect it to Generate song. `yue2_max_duration` is a separate
YuE2 ceiling (new default 360 seconds); `max_duration` controls MiniMax. Older
workflows without the new field retain their previous shared duration.

YuE2 full/melody controls ABC planning. max_duration is an upper bound; the model
can finish earlier. The requested duration in the song brief is not an exact
runtime guarantee. MiniMax's previous settings node remains available unchanged.

Connect the parser's `prompt_provenance_json` to this node. For YuE2, Length is
an approximate musical target and never reduces the configured generation limit.
`3-4 minutes` plans for about 210 seconds; `1 minute` aims for about 60 seconds.
With `yue2_max_duration = 360`, both may continue beyond their target to finish
phrases and decay naturally. A target above the ceiling raises an actionable
error instead of silently shortening the song. Without a structured Length, an explicit
`Target duration: N seconds.` in the final Style can supply the plan. Otherwise,
legacy graphs retain their configured ceiling. The request, its origin and
configured limit are recorded in `settings_json`, with
`duration_policy = approximate_target_natural_ending`.

For **YuE2 Cover**, connect `cover_source_json`. The source node's full/melody
choice controls both transcription and generation and is recorded as the
effective mode here. All other YuE2 settings also apply to cover songs.
