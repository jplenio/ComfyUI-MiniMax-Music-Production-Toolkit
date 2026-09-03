"""Build a static HTML comparison table from audio/video/custom cells.

A page is a grid: rows are ``data_name`` samples, columns are entries of
``model_meta_list``. Each column decides how its cell is rendered via ``ext``:

  * ``wav``      -> audio player (+ optional spectrogram), via ``HTMLUtil.get_html_audio``
  * ``mp4``      -> video, via ``HTMLUtil.get_html_video``
  * ``function`` -> your ``get_item(...)`` returns the cell html (one string, or a
                    list of strings = one table row each)

``make_table`` walks the grid and delegates all html/asset work to ``HTMLUtil``;
the small ``_render_*`` helpers below keep each cell type isolated and readable.
See ``table_config_example.yaml`` and ``README.md`` in this folder.
"""

from typing import Literal, Callable

import os
import unicodedata
from tqdm import tqdm
from .. import util, util_data
from . import HTMLUtil

TD_WIDTH = 300
BLANK_COMPONENT = f'<div style="width:{TD_WIDTH}px"> X <div>'
NAME_TAG = 'name'


def _wrap_name(text) -> str:
    """Wrap a row/column label in a fixed-width, wrapping div (the 'name' cell)."""
    return f'<div style="width:{TD_WIDTH}px; overflow-wrap: break-word;">{text}<div>'


class TableMaker:
    @staticmethod
    def get_yaml_example(output_dir:str = './') -> None:
        file_path:str = f'{os.path.dirname(__file__)}/table_config_example.yaml'
        util.system(f'cp {file_path} {output_dir}')

    @staticmethod
    def make_table_from_config_path(
        yaml_path:str,
        output_dir:str = None,
        max_num_tr:int = 5,
        get_item:Callable = lambda model_meta, data_name, case_name, html_util, **kwargs: {'item':None, 'type':None},
        get_data_name_list:Callable = None, #lambda meta_data: []
        get_file_path:Callable = None, #lambda (data_name, model_meta, ext): str
    ) -> None:
        meta_data:dict = util_data.yaml_load(yaml_path)
        if not meta_data.get('title',None): meta_data['title'] = util_data.get_file_name(yaml_path)
        TableMaker.make_table(output_dir = output_dir, max_num_tr = max_num_tr, get_item = get_item, get_data_name_list=get_data_name_list, get_file_path=get_file_path, **meta_data)

    @staticmethod
    def make_table(
        output_dir:str = None,
        title:str = '',
        sub_title:str = '',
        model_meta_list:list = list(),
        data_name_list:list = None,
        data_name_list_ref_dir:str = None,
        max_num_tr:int = 5,
        return_html:bool = False,
        transpose:bool = False,
        get_item:Callable = lambda model_meta, data_name, case_name, html_util, **kwargs: {'item':None, 'type':None},
        get_data_name_list:Callable = None, #lambda meta_data: []
        get_file_path:Callable = None, #lambda (data_name, model_meta, ext): str
        audio_config:dict = dict(),
        html_util:HTMLUtil = None,
    ) -> None:
        if output_dir is None: output_dir = f'./output/{title}'
        if os.path.exists(output_dir):
            util.log(f'Output directory {output_dir} already exists. Removing it.', msg_type='warning')
            util.system(f'rm -rf {output_dir}')

        # {case_name: [data_name, ...]} -- a table (section) per case.
        data_name_dict:dict = TableMaker._resolve_data_name_dict(data_name_list, data_name_list_ref_dir, get_data_name_list)

        if html_util is None:
            html_util = HTMLUtil(
                output_dir=output_dir,
                audio_sr=audio_config.get('audio_sr', 44100),
            )
        html_list:list = [
            html_util.get_html_text(title),
            html_util.get_html_text(sub_title, tag='h2'),
        ]

        for case_name, case_data_name_list in tqdm(data_name_dict.items(), desc='data category'):
            if case_name: html_list.append(html_util.get_html_text(case_name, tag='h3'))
            html_dict_list:list = list()
            for data_name in tqdm(case_data_name_list, desc='data'):
                # flush accumulated rows into a table once it grows past max_num_tr
                if len(html_dict_list) > max_num_tr:
                    html_list += TableMaker.get_table_html_list(html_dict_list, transpose=transpose)
                    html_dict_list = list()
                html_dict_list += TableMaker._build_data_rows(
                    model_meta_list, data_name, case_name, html_util, audio_config, get_item, get_file_path,
                )
            if len(html_dict_list) > 0:
                html_list += TableMaker.get_table_html_list(html_dict_list, transpose=transpose)

        if return_html: return html_list
        else: html_util.save_html(html_list)

    # ---- data-name resolution --------------------------------------------
    @staticmethod
    def _resolve_data_name_dict(data_name_list, data_name_list_ref_dir, get_data_name_list) -> dict:
        """Resolve the data names into a ``{case_name: [data_name, ...]}`` dict.

        Priority: explicit ``get_data_name_list`` callback > ``data_name_list`` >
        walking ``data_name_list_ref_dir`` for media files. A bare list is wrapped
        as a single unnamed case ``{'': [...]}``.
        """
        if get_data_name_list is not None:
            data_name_list = get_data_name_list({'data_name_list_ref_dir': data_name_list_ref_dir})
        elif data_name_list is None and data_name_list_ref_dir is not None:
            data_name_list = sorted(meta['file_name'] for meta in util_data.walk(data_name_list_ref_dir, ext=['.wav', '.mp4']))
        if isinstance(data_name_list, list):
            data_name_list = {'': data_name_list}
        return data_name_list

    # ---- row / cell building ---------------------------------------------
    @staticmethod
    def _build_data_rows(model_meta_list, data_name, case_name, html_util, audio_config, get_item, get_file_path) -> list:
        """Build the table row-dicts for one ``data_name`` across all model columns.

        A column may contribute several stacked rows (e.g. text / spec / audio);
        each becomes its own row-dict, all sharing the same 'name' cell.
        """
        table_row_dict_list:list = [{NAME_TAG: _wrap_name(data_name)}]
        for model_meta in model_meta_list:
            model_name:str = _wrap_name(model_meta.get(NAME_TAG, model_meta['dir'].split('/')[-1]))
            html_code_list:list = TableMaker._render_cell(
                model_meta, data_name, case_name, html_util, audio_config, get_item, get_file_path,
            )
            for i, html_code in enumerate(html_code_list):
                if i >= len(table_row_dict_list):
                    table_row_dict_list.append({NAME_TAG: _wrap_name(data_name)})
                table_row_dict_list[i][model_name] = html_code
        return table_row_dict_list

    @staticmethod
    def _render_cell(model_meta, data_name, case_name, html_util, audio_config, get_item, get_file_path) -> list:
        """Render one cell -> list of html strings (one per stacked row).

        Dispatches on ``model_meta['ext']``. On any failure, honours
        ``file_strict`` (default True -> raise; False -> render a blank cell).
        """
        ext:str = model_meta.get('ext', 'wav')
        try:
            if ext == 'function':
                return TableMaker._render_function_cell(get_item, model_meta, data_name, case_name, html_util, audio_config)
            elif ext == 'wav':
                return TableMaker._render_audio_cell(model_meta, data_name, html_util, audio_config, get_file_path)
            elif ext in ['mp4']:
                file_path:str = get_default_file_path(data_name, model_meta, ext) if get_file_path is None else get_file_path(data_name, model_meta, ext)
                return html_util.get_html_video(file_path=file_path)
            else:
                raise NotImplementedError(f"ext '{ext}' is not implemented.")
        except Exception:
            if model_meta.get('file_strict', True):
                util.log(f"Failed to build cell (data_name='{data_name}', model='{model_meta.get(NAME_TAG, model_meta.get('dir'))}')", msg_type='error')
                raise FileNotFoundError
            return [BLANK_COMPONENT]

    @staticmethod
    def _render_function_cell(get_item, model_meta, data_name, case_name, html_util, audio_config) -> list:
        """ext='function': the user callback returns the cell html."""
        item_dict = get_item(
            model_meta=model_meta,
            data_name=data_name,
            case_name=case_name,
            html_util=html_util,
            audio_config=audio_config,
        )
        if not isinstance(item_dict, dict): item_dict = {'item': item_dict}
        item = item_dict.get('item', None)
        item_type:str = item_dict.get('type', None)
        if item_type is not None:
            raise NotImplementedError(f"item type '{item_type}' is not implemented.")
        # item may be a single html string OR a list of html strings (one per row)
        return list(item) if isinstance(item, (list, tuple)) else [item]

    @staticmethod
    def _render_audio_cell(model_meta, data_name, html_util, audio_config, get_file_path) -> list:
        """ext='wav': [audio_html, spec_html]; spec omitted (blank) when off."""
        file_path:str = get_default_file_path(data_name, model_meta, 'wav') if get_file_path is None else get_file_path(data_name, model_meta, 'wav')
        media_html_dict:dict = html_util.get_html_audio(
            audio_path=file_path,
            sample_rate=audio_config.get('sample_rate', None),
            spec_type=audio_config.get('spec_type', None),
            audio_player=audio_config.get('audio_player', 'html'),
            width=audio_config.get('media_width', 300),
            max_second=audio_config.get('max_audio_second', None),
            waveform_height=audio_config.get('waveform_height', None),
        )
        return [media_html_dict.get(key, BLANK_COMPONENT) for key in ['audio', 'spec']]

    # ---- table assembly ---------------------------------------------------
    @staticmethod
    def get_table_html_list(html_dict_list:list, transpose:bool) -> list:
        if transpose:
            html_dict_list_t = list()
            comparison_name_list:list = [comparison_name for comparison_name in list(html_dict_list[0].keys()) if comparison_name != NAME_TAG]
            for comparison_name in comparison_name_list:
                html_dict_t = {NAME_TAG: comparison_name}
                for html_dict in html_dict_list:
                    html_dict_t[html_dict[NAME_TAG]] = html_dict[comparison_name]
                html_dict_list_t.append(html_dict_t)
            html_dict_list = html_dict_list_t
        return HTMLUtil.get_table_html_list(html_dict_list)


def get_default_file_path(file_name:str, model_meta:dict, ext:str = 'wav', dir_path:str = None) -> str:
    if model_meta.get('use_only_name', True): file_name = file_name.split('/')[-1]
    file_name_pre_post_fix = model_meta.get('file_name_pre_post_fix',['',''])
    audio_file_name:str = model_meta.get('file_name', None)
    if audio_file_name is None:
        audio_file_name = f'{file_name_pre_post_fix[0]}{file_name}{file_name_pre_post_fix[1]}.{ext}'
    else:
        audio_file_name = f'{file_name}/{file_name_pre_post_fix[0]}{audio_file_name}{file_name_pre_post_fix[1]}.{ext}'
    audio_path:str = f"{model_meta['dir'] if dir_path is None else dir_path}/{audio_file_name}"

    if os.path.isfile(audio_path): return audio_path
    else: return unicodedata.normalize("NFC", audio_path)
