# TableMaker

Generate a static HTML page that lays out audio / video / custom cells in a
comparison grid — **rows are samples (`data_name`), columns are models
(`model_meta_list`)**. Handy for A/B-ing model outputs, listening tests, and
dataset spot-checks.

```
table_maker/
├── table_maker.py            # TableMaker: walks the grid, writes the page
├── html_util.py              # HTMLUtil: renders cells (audio/img/video/text) + saves html
├── table_config_example.yaml # annotated config template
└── component/
    ├── audio_player.py        # WaveformAudioPlayer: offline waveform player
    └── assets/wavesurfer.min.js
```

## Quick start

```python
from torch_jaekwon.util.table_maker import TableMaker

TableMaker.make_table_from_config_path(
    yaml_path='my_table.yaml',
    output_dir='./html/my_table',   # overwritten if it exists
    max_num_tr=100,                 # rows per <table> before starting a new one
)
```

Open `./html/my_table/plot.html`. Media is copied into `plot.html`'s `media/`
folder, so move/zip the whole output dir to share it.

Get a config template:

```python
TableMaker.get_yaml_example('./')   # copies table_config_example.yaml here
```

## Config

Rows come from **one** of: `data_name_list`, `data_name_list_ref_dir` (auto-walk
a dir for `.wav`/`.mp4`), or a `get_data_name_list` callback. Group rows into
titled sections by passing a `Dict[str, List]`.

Each column is one `model_meta_list` entry; `ext` decides how its cell renders:

| `ext`        | cell content                                                              |
|--------------|---------------------------------------------------------------------------|
| `wav` (default) | audio player, optionally with a spectrogram row                        |
| `mp4`        | video player                                                              |
| `function`   | your `get_item(...)` returns the html (see below)                         |

See `table_config_example.yaml` for every field (`file_name`,
`file_name_pre_post_fix`, `use_only_name`, `file_strict`, …).

### `audio_config`

Applies to `ext: wav` cells and is forwarded to `get_item` so custom cells can
honour the same options.

| key                | values                                    | meaning |
|--------------------|-------------------------------------------|---------|
| `audio_sr`         | int (e.g. `24000`)                        | sample rate for spectrograms / loudness |
| `spec_type`        | `null` \| `'x'` \| `'stft'` \| `'mel'`    | spectrogram; `null`/`'x'` = off. Stereo → one spec per channel |
| `audio_player`     | `'html'` \| `'waveform'`                   | plain `<audio>` tag, or the waveform player |
| `media_width`      | int px, or css percent e.g. `'80%'`        | width of audio + spectrogram (percent of the cell) |
| `waveform_height`  | int px                                     | per-channel waveform height (waveform player) |
| `max_audio_second` | float, or `null`                           | cap audio/spec/waveform length; `null` = full audio |

### `ext: function` cells

Point a column at your own renderer:

```yaml
model_meta_list:
  - name: 'my model'
    dir: '/path/to/outputs'
    ext: 'function'
```

```python
def get_item(model_meta, data_name, case_name, html_util, **kwargs):
    audio_config = kwargs.get('audio_config', {})
    media = html_util.get_html_audio(
        audio_path=f"{model_meta['dir']}/{data_name}.wav",
        audio_player=audio_config.get('audio_player', 'html'),
        width=audio_config.get('media_width', 300),
        max_second=audio_config.get('max_audio_second', None),
        waveform_height=audio_config.get('waveform_height', None),
    )
    # return one html string, or a list = one stacked table row each
    return {'item': [media['audio'], media.get('spec', '')]}

TableMaker.make_table_from_config_path('my_table.yaml', get_item=get_item)
```

## Waveform audio player

`audio_player: 'waveform'` renders [wavesurfer.js](https://wavesurfer.xyz/)
instead of `<audio>`: a real waveform, a moving play-head, and **one waveform per
channel** (stereo shows two).

**Works fully offline — even opened by double-click (`file://`).** The library is
vendored (no CDN) and loaded as a classic script, and waveform peaks are
pre-computed in Python and embedded as JSON while playback uses a native
`<audio>` element — so the browser never has to `fetch()` the audio (which Chrome
blocks under `file://`). Cost is a few KB of JSON per clip.

### Adding your own page component

The player is a self-contained *page component*. `HTMLUtil` stays agnostic: in
`save_html` it just asks every component that was used for its assets. To add a
new one (e.g. an F0 overlay, a video variant), implement this interface and
append an instance to `HTMLUtil.html_component_list`:

```python
class MyComponent:
    def __init__(self):
        self.used = False                       # set True once you emit a cell

    def head_assets(self) -> str:               # css injected into <head>
        return "/* ... */"

    def page_body_html(self, page_dir, media_dir_name='media') -> str:
        # copy any assets next to the page (page_dir/media_dir_name/...) and
        # return the <script>/<link> tags to inject before </body>
        return "<script>/* ... */</script>"
```

`HTMLUtil.get_html_audio` / `get_html_img` / `get_html_video` remain the
low-level render entry points; components own the page-level wiring.

## Notes

- The output dir is **removed and recreated** on each run.
- `transpose: true` swaps rows/columns.
- `max_num_tr` splits long sections into multiple `<table>`s for faster rendering.
- `file_strict: false` renders a blank cell instead of raising on a missing file.
