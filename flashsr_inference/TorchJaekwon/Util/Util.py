from typing import Literal
import os, sys

PURPLE = '\033[95m'
CYAN = '\033[96m'
DARKCYAN = '\033[36m'
BLUE = '\033[94m'
GREEN = '\033[92m'
YELLOW = '\033[93m'
RED = '\033[91m'
BOLD = '\033[1m'
UNDERLINE = '\033[4m'
END = '\033[0m'

class Util:
    @staticmethod 
    def print(text:str, type:Literal['info', 'success', 'warning', 'error'] = None) -> None:
        template_dict:dict = {
            'info': {
                'color': BOLD + BLUE,
                'prefix': '[Info]: '
            },
            'success': {
                'color': BOLD + GREEN,
                'prefix': '[Success]: '
            },
            'warning': {
                'color': BOLD + YELLOW,
                'prefix': '[Warning]: '
            },
            'error': {
                'color': BOLD + RED,
                'prefix': '[Error]: '
            }
        }
        color:str = template_dict.get(type, {}).get('color', '')
        prefix:str = template_dict.get(type, {}).get('prefix', '')
        print(f"{color + prefix + text + END}")

    @staticmethod
    def set_sys_path_to_parent_dir(file:str, # __file__
                                   depth_to_dir_from_file:int = 1,
                                   ) -> None:
        dir : str = os.path.abspath(os.path.dirname(file))
        for _ in range(depth_to_dir_from_file): dir = os.path.dirname(dir)
        sys.path[0] = os.path.abspath(dir)
    
    @staticmethod
    def system(command:str) -> None:
        result_id:int = os.system(command)
        assert result_id == 0, f'[Error]: Something wrong with the command [{command}]'
    
    @staticmethod
    def wget(link:str, save_dir:str) -> None:
        os.makedirs(save_dir, exist_ok=True)
        Util.system(f'wget {link} -P {save_dir}')
    
    @staticmethod
    def unzip(file_path:str, unzip_dir:str) -> None:
        os.makedirs(unzip_dir, exist_ok=True)
        file_name:str = file_path.split('/')[-1]
        if '.tar.gz' in file_name:
            Util.system(f'''tar -xzvf {file_path} -C {unzip_dir}''')
        else:
            Util.system(f'''unzip {file_path} -d {unzip_dir}''')