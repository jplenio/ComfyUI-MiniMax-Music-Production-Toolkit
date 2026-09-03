# Torch Jaekwon
This is my personal repository for the efficiency of my research.

## Set up
* Clone the repository.
    ```
    git clone https://github.com/jakeoneijk/TorchJaekwon
    ```

* Install TorchJaekwon
    ```
    source install_torchjk.sh
    ```

* Init project based on torch_jaekwon.
    ```
    python init_project.py -d target_path
    ```

## Usage

`main.py` runs `controller.run()`, which dispatches by `--stage`:

```shell
python main.py --config_path config/exp.yaml --stage preprocess   # build data
python main.py --config_path config/exp.yaml --stage train        # train
python main.py --config_path config/exp.yaml --stage inference --ckpt_name last
python main.py --config_path config/exp.yaml --stage evaluate
```

Config lives in `config/`; runs read/write under `./artifacts` (checkpoints & logs in
`artifacts/train/<config_name>`). Redirect the roots with the `ARTIFACTS_ROOT` /
`SOURCE_DATA_DIR` env vars.

### Train

```shell
python main.py --config_path config/exp.yaml --stage train                                    # run
python main.py --config_path config/exp.yaml --stage train -r                                 # resume from last checkpoint
python main.py --config_path config/exp.yaml --stage train --set train.optimizer.args.lr=1e-4 # override any config value
```

Multi-GPU / multi-node depends on the trainer chosen in the config (`train.class_meta.path`):

| trainer (`train.class_meta.path`) | how to launch |
|---|---|
| `…trainer.Trainer` | single process — the commands above |
| `…torchrun_trainer.TorchrunTrainer` | `torchrun --standalone --nproc_per_node=<G> main.py --config_path config/exp.yaml --stage train` |
| `…lightning_trainer.LightningTrainer` | set `num_nodes` / `devices` / `strategy` in its `args`; single node = plain `python main.py …` (Lightning spawns) or `torchrun`; multi-node = SLURM, one task per GPU (Lightning auto-detects). See [NOTES.md](NOTES.md). |

## Config

An experiment is one YAML in `config/`. A class is named by a `class_meta` block —
`path` (dotted import path) + `args` (constructor kwargs):

```yaml
model:
  class_meta:
    path: model.unet.UNet                               # project-relative dotted path
    args: { dim: 64 }
train:
  class_meta:
    path: torch_jaekwon.train.trainer.trainer.Trainer   # 'torch_jaekwon.'-prefix for shared classes
    args: {}
  optimizer:
    class_meta: { path: AdamW, args: { lr: 1e-4 } }     # torch built-ins: bare class name
```

- **`path`** = `<module>.<ClassName>`, resolved by import — project-relative, or
  `torch_jaekwon.`-prefixed for shared classes. Optimizers / schedulers / losses use the
  bare torch class name (`AdamW`, `StepLR`, `L1Loss`).
- **Env vars** — any value may use `${oc.env:VAR}` or `${oc.env:VAR,default}`, resolved at
  load time (one config, any server).
- **CLI overrides** — set any key without editing the file, e.g.
  `python main.py --config_path config/exp.yaml --stage train --set train.seed=42 mode.debug_mode=false`.

## Notes

Deferred TODOs and the LightningTrainer verification checklist live in [NOTES.md](NOTES.md).

