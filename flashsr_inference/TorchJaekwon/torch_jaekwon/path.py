from typing import Literal, Union, Any
import os
import re
import importlib.util
from dataclasses import dataclass, asdict

def get_package_root(package_name: str) -> str:
    spec = importlib.util.find_spec(package_name)
    if spec and spec.origin:
        return os.path.dirname(spec.origin)
    raise ImportError(f"Package '{package_name}' not found.")

TORCH_JAEKWON_PATH:str = get_package_root("torch_jaekwon")
CONFIG_DIR = "./config"
ARTIFACTS_ROOT = os.environ.get("ARTIFACTS_ROOT", "./artifacts") # export ARTIFACTS_ROOT=/path/to/your/output

START_DIR_MAP = {'artifacts': ARTIFACTS_ROOT}
SOURCE_DATA_DIR = os.environ.get('SOURCE_DATA_DIR', f'{ARTIFACTS_ROOT}/data/source')
if SOURCE_DATA_DIR.startswith('['):
    START_DIR_MAP.update({f'source_data_{i}': data_dir.strip() for i, data_dir in enumerate(SOURCE_DATA_DIR[1:-1].split(','))})
elif SOURCE_DATA_DIR.startswith('{'):
    import json
    data_dir_dict = json.loads(SOURCE_DATA_DIR)
    START_DIR_MAP.update({f'source_data_{key}': data_dir for key, data_dir in data_dir_dict.items()})
else:
    START_DIR_MAP['source_data'] = SOURCE_DATA_DIR

def get_source_data_key_list() -> list:
    return [key for key in START_DIR_MAP.keys() if key.startswith('source_data')]

_ENV_PATTERN = re.compile(r'\$\{oc\.env:([^},]+)(?:,([^}]*))?\}') # matches '${oc.env:VAR}' and '${oc.env:VAR,default}'

def _resolve_env_match(match:re.Match) -> str:
    var_name:str = match.group(1).strip()
    default:str = match.group(2) # None when no ',default' is given
    if var_name in os.environ: return os.environ[var_name]
    if default is not None: return default
    raise KeyError(f"[resolve_env] environment variable '{var_name}' is not set and has no default")

def resolve_env(config:Any) -> Any: # recursively substitute '${oc.env:VAR}' / '${oc.env:VAR,default}' with os.environ values
    if isinstance(config, str): return _ENV_PATTERN.sub(_resolve_env_match, config)
    if isinstance(config, dict): return {key: resolve_env(value) for key, value in config.items()}
    if isinstance(config, list): return [resolve_env(item) for item in config]
    return config

@dataclass
class ArtifactsDirs:
    data:str = f'{ARTIFACTS_ROOT}/data'
    preprocessed_data:str = f'{ARTIFACTS_ROOT}/data/preprocessed'
    train:str = f'{ARTIFACTS_ROOT}/train'
    inference:str = f'{ARTIFACTS_ROOT}/inference'
    evaluate:str = f'{ARTIFACTS_ROOT}/evaluate'
ARTIFACTS_DIRS = ArtifactsDirs()

def relpath(
    file_path:str,
    start_dir_type:Literal['source_data', 'artifacts'] = 'source_data',
    start_dir_path:str = None
) -> str:
    file_path_abs:str = os.path.abspath(file_path)
    start_dir_path_abs:str = os.path.abspath(START_DIR_MAP.get(start_dir_type) if start_dir_path is None else start_dir_path)
    if file_path_abs.startswith(start_dir_path_abs):
        return os.path.relpath(file_path_abs, start=start_dir_path_abs)
    else:
        return None

def abspath(
    file_path:str,
    start_dir_type:Literal['source_data', 'artifacts'] = 'source_data',
    start_dir_path:str = None
) -> str:
    start_dir_path_abs:str = os.path.abspath(START_DIR_MAP.get(start_dir_type) if start_dir_path is None else start_dir_path)
    if os.path.abspath(file_path).startswith(start_dir_path_abs):
        return os.path.abspath(file_path)
    abs_path:str = f'{start_dir_path_abs}/{file_path}'
    return abs_path

def abspath_search(file_path:str, start_dir_path_list:list = None, strict:bool = True) -> Union[str, list]:
    if not file_path or not isinstance(file_path, str): return file_path
    
    file_path_list = list()
    if start_dir_path_list is None:
        start_dir_path_list = list(START_DIR_MAP.values()) + list(asdict(ARTIFACTS_DIRS).values())
    for start_dir_path in start_dir_path_list:
        file_abspath = abspath(file_path, start_dir_path=start_dir_path)
        if os.path.exists(file_abspath): file_path_list.append(file_abspath)
    
    file_path_list = list(set(file_path_list))
    if len(file_path_list) == 1: return file_path_list[0]
    elif len(file_path_list) == 0: return file_path
    else:
        if strict: raise FileNotFoundError(f'Multiple files found: {file_path}, found: {file_path_list}')
        return file_path_list

def abspaths(file_paths: Union[list, dict], include_key_filter:str = 'path') -> Union[list, dict]:
    if isinstance(file_paths, list):
        return [abspath_search(file_path) if isinstance(file_path, str) else file_path for file_path in file_paths]
    elif isinstance(file_paths, dict):
        is_search = lambda key,value: isinstance(value, str) and value not in ['.'] and (include_key_filter is None or include_key_filter in key)
        return {key: abspath_search(value) if is_search(key,value) else value for key, value in file_paths.items()}
    else:
        raise ValueError(f'file_paths should be list or dict, but got {type(file_paths)}')
