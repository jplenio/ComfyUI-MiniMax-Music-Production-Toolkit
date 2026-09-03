# Parallel task running

Run embarrassingly-parallel GPU work — preprocess shards, batched inference, feature
dumps — as **many independent 1-GPU workers racing a shared task list**. No ranks, no
inter-process communication; crash-safe and resumable.

## The idea in 30 seconds

- Split the work into **tasks** (one shard / one utterance / one file).
- Every worker walks the **whole** list and, for each task, tries to **claim** it with a
  single atomic `mkdir`. First to `mkdir` wins; everyone else skips it. That one
  filesystem op is the *only* coordination between workers.
- A worker writes its output, then publishes a **done-marker last**. So:
  - N workers split the list with zero bookkeeping (no "worker 0 gets 0–9");
  - a killed worker leaves only a temp dir, never a half-written "done" task;
  - **rerun = resume** — only unfinished tasks remain.

You launch one **wave** of workers and rerun until 0 are left (the local backend loops
for you). That's the whole model.

## How a run flows

```
STRUCTURE:  run_parallel_tasks.sh  →  backends/<TJ_BACKEND>.sh  →  worker/
              [login] orchestrate       [login] submit N workers     [compute] run each
──────────────────────────────────────────────────────────────────────────────────────
[LOGIN]  run_parallel_tasks.sh   driver (generic): wipe → count leftover → tj_submit_wave()

# tj_submit_wave() = "launch a wave" — the ONE function a backend defines. The driver picks the
# backend (TJ_BACKEND / -b), sets the per-wave vars (TJ_NJOBS/TJ_JOB/TJ_HOURS/TJ_MODULE/
# TJ_APP_ARGS), and calls it with no args. Its body, per backend:

backends/local.sh                           # no scheduler
  tj_submit_wave():  run $TJ_NJOBS× worker/run_one_worker.sh  # background, one per GPU

backends/slurm_pyxis.sh                     # cluster + pyxis container
  tj_submit_wave():  sbatch --array=1-$TJ_NJOBS              # independent 1-GPU jobs; each runs:
                       worker/run_in_container.sh            #   [compute · OUTSIDE container]
                         srun --container-image →
                           worker/run_one_worker.sh          #   [compute · INSIDE  container]

# both backends converge on the same worker:
worker/run_one_worker.sh   set caches/env → python -m $TJ_MODULE run
  └─ ParallelTaskProcessor.run()   loop: claim task (atomic mkdir) → process → repeat
```

Three layers, one job each:
- **driver** (`run_parallel_tasks.sh`) — generic orchestration on the login node; zero
  cluster-specific literals.
- **backend** (`backends/<name>.sh`) — defines `tj_submit_wave()`, the *only* cluster-specific
  piece: turns "launch a wave" into real launches (`sbatch`, background procs, …). Swap to move clusters.
- **worker** (`worker/run_one_worker.sh`) — generic per-GPU entry that runs your Python.

## The claim mechanism (why there's no sharding)

Workers are *not* assigned slices. Every worker runs the same loop over the full list:

```python
for task in self.list_tasks():                            # everyone sees the FULL list
    if self.is_task_done(task):                 continue  # done -> skip (resume)
    if not self.claim(self.tmp_dir_path(task)): continue  # someone else owns it -> skip
    self.process_task(task, self.tmp_dir_path(task))      # won it -> do it
```

`claim()` is just an atomic `mkdir` — the temp dir IS the claim:

```python
def claim(path):
    try:    os.makedirs(path); return True   # only ONE process can create a given dir
    except FileExistsError:    return False  # already taken
```

`mkdir` is atomic on POSIX, so if two workers race for a task exactly one wins. This
**self-balances** (a slow worker just claims fewer) and needs no ranks — which is why the
same code runs unchanged as 1 local process or 40 cluster jobs.

## Backends (pick one; add more later)

The driver sources one backend, chosen by `TJ_BACKEND` (or `-b`). Shipped today:

| `TJ_BACKEND` | file | what it does | extra vars it needs |
|---|---|---|---|
| `slurm_pyxis` *(default)* | `backends/slurm_pyxis.sh` | `sbatch --array` of 1-GPU jobs, each in a pyxis/enroot container | `TJ_ACCOUNT TJ_PARTITION TJ_IMAGE TJ_MOUNTS` |
| `local` | `backends/local.sh` | background processes on this machine, one per GPU (no scheduler) | — |

Adding a system = **drop a `backends/<name>.sh`** that defines `tj_submit_wave`; the
driver, worker, and Python stay untouched. Natural next entries: `slurm` (plain, no
container), `slurm_singularity`. **Escape hatch:** if your env file already defines
`tj_submit_wave`, the driver keeps it and sources no backend — for a cluster nothing
shipped fits.

## Writing a backend (custom `tj_submit_wave`)

A backend is one function, `tj_submit_wave`, that launches the current wave. It takes **no
arguments** — the driver hands it everything through `TJ_*` variables, so you just read them:

| variable | meaning |
|---|---|
| `TJ_NJOBS` | number of workers to launch this wave |
| `TJ_MODULE` | python module to run (`python -m $TJ_MODULE run`) |
| `TJ_JOB` | job name (logs / scheduler) |
| `TJ_HOURS` | walltime budget per worker |
| `TJ_APP_ARGS` | extra args forwarded to the module (space-joined; no spaces *within* a value) |
| `TJ_PYTHON` · `TJ_REPO` · `TJ_PKG` | interpreter, repo root, torch_jaekwon dir (from your env file) |
| *(your own)* | anything else your env file exports (e.g. `TJ_IMAGE`, `TJ_ACCOUNT`, `TJ_MOUNTS`) |

Each worker must ultimately run
`worker/run_one_worker.sh -m $TJ_MODULE -p $TJ_PYTHON -r $TJ_REPO -- $TJ_APP_ARGS`
(directly, or inside a container). If your submission is **synchronous** (blocks until the wave
finishes, like `local`), also `export TJ_SYNC=1` so the driver loops wave→wave to completion;
async submitters (sbatch-style) leave it unset and the user reruns.

Example — a plain-SLURM backend (no container):

```bash
# backends/slurm.sh   (select with TJ_BACKEND=slurm or -b slurm)
tj_submit_wave() {
  sbatch --array="1-$TJ_NJOBS" --nodes=1 --gpus-per-node=1 --job-name="$TJ_JOB" \
    --partition="$TJ_PARTITION" --account="$TJ_ACCOUNT" --time="$TJ_HOURS:00:00" \
    "$TJ_PKG/util/parallel/worker/run_one_worker.sh" \
    -m "$TJ_MODULE" -p "$TJ_PYTHON" -r "$TJ_REPO" -- $TJ_APP_ARGS
}
```

Drop the file in `backends/` to share it, or — for a one-off cluster nothing shipped fits —
define `tj_submit_wave` directly in your env file; the driver keeps it and sources no backend.

## Use it in 2 steps

### 1. Write a subclass

```python
# src/preprocess/my_task.py
import os, shutil
from torch_jaekwon.util.parallel.parallel_task_processor import ParallelTaskProcessor

class MyTask(ParallelTaskProcessor):
    def list_tasks(self):                  # ALL units of work, any type, stable order
        return [...]
    def is_task_done(self, task):          # True iff the done-marker exists
        return os.path.exists(out_path(task))
    def tmp_dir_path(self, task):          # per-task temp dir; co-locate with output
        return os.path.join(out_dir(task), f".tmp_{task_id(task)}")
    def process_task(self, task, tmp_dir): # tmp_dir already created (the claim).
        ...                                # write INTO tmp_dir, then atomically rename
        ...                                # into place — done-marker LAST —
        shutil.rmtree(tmp_dir)             # and remove tmp_dir on success.

    # optional: setup() runs ONCE per worker before the loop (e.g. load a model).

if __name__ == "__main__":
    MyTask.main()                          # subcommands: run | count | wipe
```

Keep `__init__` / `list_tasks` / `is_task_done` / `tmp_dir_path` **import-light** (no
torch) so `count` / `wipe` stay cheap on the login node. Heavy imports go inside
`process_task` (or `setup`).

### 2. Run it

```bash
# Default backend (slurm_pyxis): submits a wave. Rerun until it reports 0 leftover.
TJ_CLUSTER_ENV=/path/to/your/env_setup.sh \
  bash "$TJ_PKG/util/parallel/run_parallel_tasks.sh" -M src.preprocess.my_task -j mytask

# Local (no scheduler): one worker per GPU, loops to completion in one command.
TJ_CLUSTER_ENV=/path/to/your/env_setup.sh \
  bash "$TJ_PKG/util/parallel/run_parallel_tasks.sh" -M src.preprocess.my_task -b local
```

Most projects wrap this in a one-line launcher that sets `TJ_CLUSTER_ENV` — copy
`examples/launch.example.sh`.

Driver flags: `-M <module>` (required) · `-b <backend>` · `-j <job_name>` · `-t <hours>` ·
`-m <max_workers_per_wave>` · `-- <app args>`.

**Per-run app args:** anything after `--` is forwarded verbatim to
`python -m <module> {run,count,wipe} <app args>`, so a module can take argparse config
(e.g. `-- --config a.yaml --ckpt step-150000.ckpt`). One rule: **no spaces/commas in any
value** — they word-split through the scheduler.

## The contract (your env file)

`$TJ_CLUSTER_ENV` declares **variables only** (all prefixed `TJ_`, so they never collide
with your other env vars); the driver turns them into launches. Every backend needs:

- `TJ_PYTHON` — interpreter (login node + jobs)
- `TJ_PKG` — torch_jaekwon install dir (so `$TJ_PKG/util/parallel/...` resolves)
- `TJ_REPO` — repo root (→ worker `PYTHONPATH`)
- `TJ_BACKEND` — which backend to source (or pass `-b`)

...plus the chosen backend's extra vars (see the table). Start from
`examples/env_setup.example.sh`.

## Try the demo (30 s, no GPU/scheduler)

```bash
TJ_BACKEND=local bash examples/launch.example.sh -j demo   # runs 8 trivial tasks locally
TJ_BACKEND=local bash examples/launch.example.sh -j demo   # rerun -> "0 leftover" (resume)
```

`examples/` is also the copy-paste starting point: `example_task.py` (a minimal subclass),
`env_setup.example.sh` (the contract), `launch.example.sh` (the thin launcher).

## Files

| File | Role |
|------|------|
| `parallel_task_processor.py` | `ParallelTaskProcessor` base — the claim/resume/CLI logic. Subclass this. |
| `run_parallel_tasks.sh` | Driver (login entry): source backend → wipe → count → submit one wave. |
| `backends/slurm_pyxis.sh` | SLURM + pyxis/enroot backend (`sbatch --array` of 1-GPU jobs). |
| `backends/local.sh` | No-scheduler backend (local background processes). |
| `worker/run_in_container.sh` | Compute-node entry the slurm backend `srun`s into the container. |
| `worker/run_one_worker.sh` | Worker: one per GPU, runs `python -m <module> run`. |
| `examples/` | Runnable demo + copy-paste templates. |
