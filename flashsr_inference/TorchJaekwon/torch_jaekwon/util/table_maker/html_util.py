from typing import List, Literal, Union, Tuple
try: import IPython.display as ipd
except:  print('[error] there is no IPython package')
try: import pandas as pd
except:  print('[error] there is no pandas package')

import re
import librosa
import numpy as np

from torch_jaekwon.util import util, util_audio, util_data, util_audio_stft
from torch_jaekwon.util.util_audio_mel import UtilAudioMelSpec, get_default_config
from torch_jaekwon.util.table_maker.component import WaveformAudioPlayer
from torch_jaekwon.util.table_maker.component.audio_player import _css_len

LOWER_IS_BETTER_SYMBOL = "↓"
HIGHER_IS_BETTER_SYMBOL = "↑"
PLUS_MINUS_SYMBOL = "±"

# Modern table/page styling shared by every page TableMaker emits. Kept as a
# module-level constant (not rebuilt per HTMLUtil) so it's easy to read/edit as
# real CSS. ``__TD_WIDTH__`` is the only per-instance knob (see ``table_data_width``).
_TABLE_CSS = """\
:root {
  --bg: #f6f7f9;
  --surface: #ffffff;
  --border: #e6e8eb;
  --text: #1f2933;
  --muted: #6b7280;
  --header-bg: #f1f3f5;
  --accent: #4f46e5;
  --row-alt: #fafbfc;
  --row-hover: #eef2ff;
}
* { box-sizing: border-box; }
body {
  margin: 0;
  background: var(--bg);
  color: var(--text);
  font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
  line-height: 1.5;
}
#root {
  max-width: 1600px;
  margin: 0 auto;
  padding: 32px 24px 64px;
}
h1 { font-size: 26px; font-weight: 700; letter-spacing: -0.01em; margin: 0 0 4px; }
h2 { font-size: 16px; font-weight: 400; color: var(--muted); margin: 0 0 24px; }
h3 {
  font-size: 13px; font-weight: 600; text-transform: uppercase; letter-spacing: 0.05em;
  color: var(--accent); margin: 36px 0 12px; padding-left: 10px;
  border-left: 3px solid var(--accent);
}
table {
  border-collapse: separate;
  border-spacing: 0;
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: 12px;
  overflow: hidden;
  margin-bottom: 28px;
  box-shadow: 0 1px 2px rgba(16,24,40,0.04), 0 1px 3px rgba(16,24,40,0.06);
  font-size: 14px;
}
thead th {
  background: var(--header-bg);
  color: var(--text);
  font-weight: 600;
  text-align: center;
  padding: 12px 14px;
  border-bottom: 1px solid var(--border);
  white-space: nowrap;
}
tbody td {
  width: __TD_WIDTH__;
  padding: 12px 14px;
  border-bottom: 1px solid var(--border);
  vertical-align: middle;
  text-align: center;
}
tbody tr:last-child td { border-bottom: none; }
tbody tr:nth-child(even) { background: var(--row-alt); }
tbody tr:hover { background: var(--row-hover); }
.media-div {
  display: flex;
  align-items: center;
  justify-content: center;
}
audio { width: 100%; max-width: 300px; }"""

# Full document head (doctype .. </head>), with the CSS inlined. ``<body>`` and the
# ``#root`` wrapper stay as separate list items in html_start_list so save_html's
# indentation still nests the table body under them.
_HTML_HEAD = """\
<!DOCTYPE html>
<head>
<meta charset="utf-8" />
<meta name="viewport" content="width=device-width, initial-scale=1" />
<meta name="theme-color" content="#000000" />
<style>
%s
</style>
</head>""" % _TABLE_CSS


def _spec_to_channel_list(spec) -> List:
    """Split a spectrogram into a list of 2d [freq, time] specs, one per channel."""
    while getattr(spec, 'ndim', len(spec.shape)) > 3:
        spec = spec[0]
    if len(spec.shape) == 2:
        return [spec]
    return [spec[i] for i in range(spec.shape[0])]  # (channel, freq, time)


def _stack_vertical(html_list: List[str]) -> str:
    """Stack multiple media html snippets vertically (used for per-channel specs)."""
    if len(html_list) == 1:
        return html_list[0]
    inner = ''.join(html_list)
    return (
        '<div style="display:flex; flex-direction:column; gap:4px; '
        f'align-items:center; width:100%;">{inner}</div>'
    )


class HTMLUtil():
    def __init__(
        self,
        output_dir:str = None,
        table_data_width:int = None,
        audio_sr:int = 44100
    ) -> None:
        self.indent:str = '  '
        self.media_idx_dict:dict = {'audio':0, 'img':0, 'video':0}
        td_width:str = 'fit-content' if table_data_width is None else f'{table_data_width}px'
        # Enhanced <audio> replacement (waveform + play-head + per-channel view).
        # It's a self-contained page component: get_html_audio just calls it per
        # cell, and save_html asks every used component for its <head>/<body>
        # assets -- HTMLUtil needs no knowledge of the player's internals.
        self.audio_player = WaveformAudioPlayer()
        self.html_component_list:list = [self.audio_player]
        self.html_start_list:List[str] = [
            _HTML_HEAD.replace('__TD_WIDTH__', td_width),
            '<body>',
            '<div id="root">',
        ]
        self.html_end_list:List[str] = [
            '</div>',
            '</body>',
            '</html>',
        ]
        self.output_dir:str = output_dir
        self.media_save_dir_name:str = 'media'

        mel_spec_config = get_default_config(audio_sr)
        self.mel_spec_util = UtilAudioMelSpec(**mel_spec_config)
    
    @staticmethod
    def get_table_html_list(
        dict_list: List[dict],
        use_pandas:bool = False
    ) -> List[str]:
        '''
        Keys will be the table head items
        Values will be the table body items

        dict_list = [
        {'name':'test_sample_name', 'model1': html_code/float/str, 'model2': html_code/float/str, ...},
        /
        {'name':'model_name', 'metric1': html_code/float/str, 'metric2': html_code/float/str, ...},
        ...
        ]
        '''
        if use_pandas:
            df = pd.DataFrame(dict_list)
            return df.to_html(escape=False,index=False)
        
        html_list = list()
        table_head_item_list = list(dict_list[0].keys())
        html_list.append('<table>')
        html_list.append('<thead>')
        html_list.append('<tr>')
        for table_head_item in table_head_item_list:
            html_list.append(f'<th>{table_head_item}</th>')
        html_list.append('</tr>')
        html_list.append('</thead>')

        html_list.append('<tbody>')
        for html_dict in dict_list:
            html_list.append('<tr>')
            for table_head_item in table_head_item_list:
                html_list.append(f'''<td><div class="media-div">{html_dict.get(table_head_item,'')}</div></td>''')
            html_list.append('</tr>')
        html_list.append('</tbody>')
        html_list.append('</table>')

        return html_list
    
    def save_html(self, html_list:List[str], file_name:str = 'plot.html') -> None:
        html_start_list:list = list(self.html_start_list)
        html_end_list:list = list(self.html_end_list)
        # Let every component that got used contribute its own <head>/<body>
        # assets (css, scripts, copied files). HTMLUtil stays agnostic of what
        # each component actually needs.
        head_assets, body_assets = self._collect_component_assets()
        if head_assets:
            html_start_list[0] = html_start_list[0].replace('</style>', f'{head_assets}\n</style>')
        if body_assets:
            html_end_list = ['</div>', body_assets, '</body>', '</html>']
        final_html_list:list = html_start_list + html_list + html_end_list
        indent_depth:int = 0
        for idx in range(1, len(final_html_list)):
            indent_depth += self.get_indent_depth_changed(final_html_list[idx - 1], final_html_list[idx])
            final_html_list[idx] = self.indent * indent_depth + final_html_list[idx]
        util_data.txt_save(f'{self.output_dir}/{file_name}', final_html_list)

    def _collect_component_assets(self) -> Tuple[str, str]:
        """Gather <head> css and <body> html from every component that was used."""
        head_parts:List[str] = list()
        body_parts:List[str] = list()
        for component in self.html_component_list:
            if not getattr(component, 'used', False):
                continue
            head_parts.append(component.head_assets())
            body_parts.append(component.page_body_html(self.output_dir, self.media_save_dir_name))
        return '\n'.join(head_parts), '\n'.join(body_parts)

    def get_html_text(
        self, 
        text:str,
        tag:Literal['h1','h2','h3','h4','h5','h6','p'] = 'h1'
    ) -> str:
        return f'<{tag}>{text}</{tag}>'
    
    def get_html_img(
        self,
        src_path:str = None,
        width:int=150
    ) -> str: #html code
        style:str = '' if width is None else f'style="width:{_css_len(width)}"'
        return f'''<img src="{src_path}" {style}/>'''
    
    def get_media_path(self, type:Literal['audio','img']) -> str:
        ext_dict = {'audio':'wav', 'img':'png', 'video': 'mp4'}
        path_dict = dict()
        path_dict['abs'] = f'{self.output_dir}/{self.media_save_dir_name}/{type}_{str(self.media_idx_dict[type]).zfill(5)}.{ext_dict[type]}'
        path_dict['relative'] = f'''./{self.media_save_dir_name}{path_dict['abs'].split(self.media_save_dir_name)[-1]}'''
        self.media_idx_dict[type] += 1
        return path_dict
    
    def get_html_audio(
        self,
        audio_path:str = None,
        cp_to_html_dir:bool = True,
        sample_rate:int = None,
        normalize_loudness:bool = False,
        spec_type:Literal['mel', 'stft', 'x'] = 'mel',
        spec_path:str = None,
        width:Union[int,str]=300,          # px int, or css string e.g. '80%' of the cell
        audio_player:Literal['html', 'waveform'] = 'html',
        max_second:float = None,           # cap audio/spec/waveform length; None = full audio
        waveform_height:int = None,        # per-channel waveform height (px); None = component default
    ) -> Union[str, Tuple[str,str]]: #audio_html_code, img_html_code
        style:str = '' if width is None else f'style="width:{_css_len(width)}"'
        if cp_to_html_dir:
            audio, sr = util_audio.read(audio_path = audio_path, sample_rate=sample_rate, module_name='soundfile')
            if normalize_loudness:
                audio = util_audio.normalize_loudness(audio, sample_rate=sr)
            if max_second is not None:
                max_len:int = int(max_second * sr)
                if audio.shape[-1] > max_len:
                    audio = audio[..., :max_len]
            path_dict = self.get_media_path('audio')
            util_audio.write(audio_path=path_dict['abs'], audio=audio, sample_rate=sr)
            audio_path = path_dict['relative']

        html_code_dict = dict()
        if audio_player == 'waveform':
            # Hand the in-memory samples to the player so it can embed peaks for
            # offline / file:// use; it falls back to fetching when audio is None.
            html_code_dict['audio'] = self.audio_player.audio_html(
                audio_src=audio_path,
                audio=audio if cp_to_html_dir else None,
                sample_rate=sr if cp_to_html_dir else None,
                width=width, height=waveform_height,
            )
        else:
            html_code_dict['audio'] = f'''<audio controls {style}> <source src="{audio_path}" type="audio/wav" /> </audio>'''

        if spec_type in ['mel', 'stft']:
            spec = self.mel_spec_util.get_hifigan_mel_spec(audio) if spec_type == 'mel' else librosa.amplitude_to_db(self.mel_spec_util.stft(audio)["mag"])
            # One spectrogram per audio channel -> stereo shows two stacked specs.
            img_html_list:List[str] = list()
            for ch_spec in _spec_to_channel_list(spec):
                path_dict = self.get_media_path('img')
                util_audio_stft.plot(save_path=path_dict['abs'], spec=ch_spec, hop_size=self.mel_spec_util.hop_size, sr=self.mel_spec_util.sample_rate)
                img_html_list.append(self.get_html_img(path_dict['relative'], width))
            html_code_dict['spec'] = _stack_vertical(img_html_list)
        
        if spec_path is not None:
            path_dict = self.get_media_path('img')
            util.cp(spec_path, path_dict["abs"])
            html_code_dict['spec'] = self.get_html_img(path_dict['relative'], width)
        
        return html_code_dict

    def get_html_video(
        self,
        file_path:str = None,
        cp_to_html_dir:bool = True,
        width: int = 480,
        height: int = 270,
    ) -> List[str]: #[html_code]
        style = ''
        if width is not None and height is not None:
            style = f'style="width:{width}px; height:{height}px;"'
        elif width is not None:
            style = f'style="width:{width}px"'

        if cp_to_html_dir:
            path_dict = self.get_media_path('video')
            util.cp(src_path = file_path, dst_path = path_dict['abs'])
            file_path = path_dict['relative']

        html_code:str = f'''<video controls {style}> <source src="{file_path}" type="video/mp4" /> Your browser does not support the video tag. </video>'''
        
        return [html_code]
    
    def get_html_tag_list(self, html_str:str) -> List[str]:
        html_tag_list = re.findall(r'</?[^>]+>', html_str)
        for idx in range(len(html_tag_list)):
            html_str_split = html_tag_list[idx].split(' ')
            if len(html_str_split) > 1:
                html_tag_list[idx] = html_str_split[0] + html_str_split[-1]
        return html_tag_list
    
    def get_indent_depth_changed(self, prev_str:str, current_str:str) -> bool:
        prev_tag_list = self.get_html_tag_list(prev_str)
        current_tag_list = self.get_html_tag_list(current_str)
        if len(current_tag_list) == 0 or len(prev_tag_list) == 0:
            return 0
        
        if prev_tag_list[0] == current_tag_list[0]:
            return 0

        if '</' in current_tag_list[0]:
            return -1
        
        for prev_tag in prev_tag_list: 
            if '/' in prev_tag: 
                return 0
        
        if len(prev_tag_list) < 2 and not '</' in prev_tag_list[0]:
            return 1
        return 0
    
    @staticmethod
    def display_html_list(html_list:list) -> None:
        for html_result in html_list:
            ipd.display(ipd.HTML(html_result))
    