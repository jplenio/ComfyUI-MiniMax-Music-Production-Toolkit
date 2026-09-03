from typing import Callable

import importlib

def instantiate_class_meta(
    class_meta:dict = dict()
) -> Callable:
    if isinstance(class_meta, dict) and 'path' not in class_meta: # type guard first, so a non-dict nested value doesn't hit '... not in <non-dict>'
        return {k: instantiate_class_meta(class_meta=v) for k,v in class_meta.items()}
    else:
        return instantiate(module_name=class_meta.get('path'), arg_dict=class_meta.get('args', dict()))

def instantiate(
    module_name:str = None,
    arg_dict:dict = dict(),
) -> Callable:
    module_class:type = import_class(module_name)
    module_instance = module_class(**arg_dict)
    return module_instance

def import_class(
    module_name:str = None, # fully-qualified dotted import path: '<module>.<ClassName>' (e.g. 'model.unet.UNet', 'torch_jaekwon.train.trainer.trainer.Trainer')
) -> type:
    if not isinstance(module_name, str) or '.' not in module_name:
        raise ValueError(f"[import_class] module_name must be a fully-qualified dotted path '<module>.<ClassName>', got {module_name!r}")
    module_path, class_name = module_name.rsplit('.', 1)
    module_from = importlib.import_module(module_path)
    return getattr(module_from, class_name)
