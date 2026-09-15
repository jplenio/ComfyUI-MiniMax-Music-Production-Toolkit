# Music settings

Connect the same model profile as the song generator. Both sampler groups remain
editable; only the selected model's group is used. Seeds, duration ceiling,
text-generation settings and effective sampler values are stored in
`settings_json`. Connect it to Generate song. `yue2_max_duration` is a separate
YuE2 ceiling (new default 360 seconds); `max_duration` controls MiniMax. Older
workflows without the new field retain their previous shared duration.

YuE2 full/melody controls ABC planning. max_duration is an upper bound; the model
can finish earlier. The requested duration in the song brief is not an exact
runtime control. MiniMax's previous settings node remains available unchanged.
