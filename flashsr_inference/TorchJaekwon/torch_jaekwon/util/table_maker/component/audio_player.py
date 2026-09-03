"""Waveform audio player component for TableMaker pages.

An enhanced replacement for the plain ``<audio>`` tag that renders:
  * the audio waveform,
  * a moving play-head / progress bar while playing,
  * one waveform per channel (so stereo shows two stacked waveforms).

Design
------
This class is a self-contained *page component*. The host (``HTMLUtil``) only
needs three things and never has to know how the player works internally:

  * ``used``                      -- flag it sets once it emits at least one cell
  * ``head_assets()``             -- css to drop into <head>
  * ``page_body_html(page_dir)``  -- copies its assets next to the page and
                                     returns the <script> tags for <body>

and per cell it calls ``audio_html(...)``. Everything player-specific -- peaks
pre-computation, the vendored library, css/js, ``file://`` support -- lives here.

Offline / ``file://`` support
-----------------------------
The page works with no internet, even opened by double-click, because:

  1. wavesurfer.js is vendored (``assets/wavesurfer.min.js``, the UMD build with
     a global ``WaveSurfer``) and loaded via a classic ``<script>`` -- no CDN,
     no ES-module server.
  2. Waveform peaks are pre-computed in Python and embedded as JSON, and playback
     goes through a native ``<audio>`` element -- so the browser never has to
     ``fetch()`` the audio (which Chrome blocks under ``file://``).
"""

import json
import os
import shutil

_ASSETS_DIR = os.path.join(os.path.dirname(__file__), 'assets')


def _css_len(value) -> str:
    """int -> '250px'; str passthrough (e.g. '80%'); None -> ''."""
    if value is None:
        return ''
    return value if isinstance(value, str) else f'{value}px'


class WaveformAudioPlayer:
    CSS_CLASS = 'tj-wave-player'

    #: Vendored UMD build (global ``WaveSurfer``); copied next to each page.
    LIB_FILENAME = 'wavesurfer.min.js'
    VENDORED_LIB_PATH = os.path.join(_ASSETS_DIR, LIB_FILENAME)

    #: Number of peak points per channel to precompute/embed. ~800 is plenty for
    #: a <=1000px waveform and keeps the embedded JSON to a few KB per clip.
    NUM_PEAK_POINTS = 800

    #: css injected once inside <head> (before </style>).
    _CSS = """
/* waveform audio player */
.tj-wave-player { display: inline-flex; flex-direction: column; gap: 6px; }
.tj-wave-player .tj-wave { width: 100%; }
.tj-wave-player .tj-controls {
  display: flex; align-items: center; gap: 8px;
  font-size: 12px; color: var(--muted);
}
.tj-wave-player .tj-play {
  border: 1px solid var(--border); background: var(--surface); color: var(--text);
  border-radius: 6px; width: 28px; height: 24px; cursor: pointer; line-height: 1;
  font-size: 12px; display: inline-flex; align-items: center; justify-content: center;
}
.tj-wave-player .tj-play:hover { background: var(--row-hover); }
.tj-wave-player .tj-time { font-variant-numeric: tabular-nums; }"""

    #: Classic (non-module) init script. Lazily initialises a wavesurfer instance
    #: per player when it scrolls into view (keeps pages with many clips snappy).
    #: Uses embedded peaks + a native <audio> element => no fetch => file:// safe.
    _INIT_SCRIPT = f"""<script>
(function () {{
  var players = document.querySelectorAll('.{CSS_CLASS}');
  if (!players.length || !window.WaveSurfer) return;
  var WaveSurfer = window.WaveSurfer;

  function fmt(s) {{
    if (!isFinite(s) || s < 0) s = 0;
    var m = Math.floor(s / 60), sec = Math.floor(s % 60);
    return m + ':' + String(sec).padStart(2, '0');
  }}

  function init(el) {{
    if (el.dataset.tjInit) return;
    el.dataset.tjInit = '1';
    var btn = el.querySelector('.tj-play');
    var time = el.querySelector('.tj-time');
    var opts = {{
      container: el.querySelector('.tj-wave'),
      height: parseInt(el.dataset.height || '48', 10),
      waveColor: '#9aa4b2',
      progressColor: '#4f46e5',
      cursorColor: '#1f2933',
      cursorWidth: 1,
      normalize: true,
      // One options object per channel -> mono renders 1 waveform, stereo renders 2.
      splitChannels: [{{}}, {{}}]
    }};
    var peaksEl = el.querySelector('.tj-peaks');
    var audioEl = el.querySelector('.tj-audio');
    if (peaksEl && audioEl) {{
      var d = JSON.parse(peaksEl.textContent);
      opts.media = audioEl;          // playback via native <audio> (file:// ok)
      opts.peaks = d.peaks;          // draw from embedded peaks (no fetch)
      opts.duration = d.duration;
    }} else {{
      opts.url = el.dataset.audioSrc; // fallback: fetch (needs http/https)
    }}
    var ws = WaveSurfer.create(opts);
    if (opts.duration) time.textContent = '0:00 / ' + fmt(opts.duration);
    btn.addEventListener('click', function () {{ ws.playPause(); }});
    ws.on('play',   function () {{ btn.textContent = '⏸'; }});
    ws.on('pause',  function () {{ btn.textContent = '▶'; }});
    ws.on('finish', function () {{ btn.textContent = '▶'; }});
    ws.on('decode', function (dur) {{ time.textContent = '0:00 / ' + fmt(dur); }});
    ws.on('timeupdate', function (cur) {{ time.textContent = fmt(cur) + ' / ' + fmt(ws.getDuration()); }});
  }}

  if ('IntersectionObserver' in window) {{
    var io = new IntersectionObserver(function (entries) {{
      entries.forEach(function (e) {{
        if (e.isIntersecting) {{ init(e.target); io.unobserve(e.target); }}
      }});
    }}, {{ rootMargin: '300px' }});
    players.forEach(function (p) {{ io.observe(p); }});
  }} else {{
    players.forEach(init);
  }}
}})();
</script>"""

    def __init__(self, height: int = 48) -> None:
        #: default per-channel waveform height in px
        self.height = height
        #: set True once this player has emitted at least one cell on the page,
        #: so the host only injects assets / copies the lib when actually needed.
        self.used = False

    # ---- host-facing page-component interface -----------------------------
    def audio_html(
        self,
        audio_src: str,
        audio=None,
        sample_rate: int = None,
        width=300,
        height: int = None,
    ) -> str:
        """Return the html for one audio cell (the host's single entry point).

        ``audio`` (numpy/torch, shape ``(channel, samples)`` or ``(samples,)``)
        and ``sample_rate`` are the in-memory samples; when given, peaks are
        pre-computed and embedded so the cell needs no network (``file://`` ok).
        When omitted, the player falls back to fetching ``audio_src`` (which
        needs the page served over http/https).
        """
        self.used = True
        peaks, duration = None, None
        if audio is not None and sample_rate:
            peaks = self.compute_peaks(audio)
            duration = float(audio.shape[-1]) / float(sample_rate)
        return self._player_html(audio_src, width=width, height=height, peaks=peaks, duration=duration)

    def head_assets(self) -> str:
        """css for <head> (no <style> wrapper; the host inlines it)."""
        return self._CSS

    def page_body_html(self, page_dir: str, media_dir_name: str = 'media') -> str:
        """Copy the vendored (offline) lib next to the page; return <body> scripts.

        ``page_dir`` is where the page (plot.html) is written; the lib is copied
        into ``page_dir/media_dir_name`` and referenced with a relative url so it
        keeps working when the folder is moved / opened from ``file://``.
        """
        lib_dst = os.path.join(page_dir, media_dir_name, self.LIB_FILENAME)
        os.makedirs(os.path.dirname(lib_dst), exist_ok=True)
        shutil.copyfile(self.VENDORED_LIB_PATH, lib_dst)
        lib_src = f'./{media_dir_name}/{self.LIB_FILENAME}'
        return f'<script src="{lib_src}"></script>\n{self._INIT_SCRIPT}'

    # ---- internals --------------------------------------------------------
    @classmethod
    def compute_peaks(cls, audio, num_points: int = None) -> list:
        """Downsample ``audio`` -> per-channel peak envelope in [-1, 1].

        Returns ``list[list[float]]`` (one inner list per channel), each value the
        signed sample of max magnitude in its bucket, scaled so the global peak is
        1.0 and rounded to 3 decimals to keep the embedded JSON small.
        """
        import numpy as np

        num_points = cls.NUM_PEAK_POINTS if num_points is None else num_points
        if hasattr(audio, 'detach'):  # torch tensor
            audio = audio.detach().cpu().numpy()
        audio = np.asarray(audio, dtype=np.float32)
        if audio.ndim == 1:
            audio = audio[None, :]

        scale = float(np.max(np.abs(audio))) or 1.0
        peaks = []
        for ch in audio:
            n = ch.shape[0]
            edges = np.linspace(0, n, num_points + 1, dtype=int)
            ch_peaks = []
            for i in range(num_points):
                seg = ch[edges[i]:edges[i + 1]]
                if seg.size == 0:
                    ch_peaks.append(0.0)
                    continue
                v = seg[int(np.argmax(np.abs(seg)))]
                ch_peaks.append(round(float(v) / scale, 3))
            peaks.append(ch_peaks)
        return peaks

    def _player_html(self, audio_src, width=300, height=None, peaks=None, duration=None) -> str:
        height = self.height if height is None else height
        width_css = _css_len(width)
        style = f' style="width:{width_css};"' if width_css else ''

        offline_nodes = ''
        if peaks is not None:
            # Raw JSON: entities are NOT decoded inside <script>, so we must not
            # html-escape. Only neutralise "</" so the peaks can't close the tag
            # early (numeric peaks never contain it, but stay safe).
            data_json = json.dumps(
                {'peaks': peaks, 'duration': duration}, separators=(',', ':')
            ).replace('</', '<\\/')
            offline_nodes = (
                f'<audio class="tj-audio" src="{audio_src}" preload="none"></audio>'
                f'<script type="application/json" class="tj-peaks">{data_json}</script>'
            )

        return (
            f'<div class="{self.CSS_CLASS}" data-audio-src="{audio_src}" '
            f'data-height="{height}"{style}>'
            f'{offline_nodes}'
            f'<div class="tj-wave"></div>'
            f'<div class="tj-controls">'
            f'<button type="button" class="tj-play">▶</button>'
            f'<span class="tj-time">0:00 / 0:00</span>'
            f'</div></div>'
        )
