# ParallelTaskProcessor -- the WORK each worker does (claim -> process -> repeat).
# Where this sits in a run: see the flow map in util/parallel/run_parallel_tasks.sh.
import os
import shutil
from typing import Any

from tqdm import tqdm

from .. import util


class ParallelTaskProcessor:
    """Parallel processor for INDEPENDENT tasks needing no inter-process
    communication -- unlike the collective/NCCL `TorchrunPreprocessor`.

    Use this when the dataset splits into independent "tasks" (units of work)
    that can each be processed and written on their own (enhance / re-encode /
    feature-extract many files or shards). There is *zero* cross-rank
    communication, so the work is embarrassingly parallel.

    ## Why not torch.distributed / NCCL
    A multi-node NCCL job has one `srun` hold the whole allocation until the
    slowest rank exits, and the rendezvous/barrier can hang. For embarrassingly
    parallel work that buys nothing and wastes GPUs. Instead, launch MANY
    independent single-GPU jobs (a loop of 1-GPU submissions, or a concurrent
    SLURM array). The scheduler fills whatever GPUs are free, each job exits the
    moment its work runs out -> the GPU is freed immediately (no allocated-idle,
    no "idle GPU" alerts), and you avoid multi-node scheduling waits entirely.

    ## Strategy this class encodes (read before subclassing)
    1. **Task = the unit of work and the unit of resume.** Each task is
       processed independently and published *atomically* (see below). Restart
       cost is at most one task.
    2. **Atomic publish (kill-safe).** `process_task` must write into the temp
       dir and then atomically rename artifacts into place, publishing the
       "done marker" (whatever `is_task_done` checks) LAST. Then an abrupt kill
       (wall-clock timeout / preemption) can only leave a temp dir behind; a
       half-written task never looks finished.
    3. **Temp dir doubles as the claim, claimed by `run()`.** Each task maps to
       a temp dir (`tmp_dir_path`). `run()` creates it with `claim()` (atomic
       `mkdir`) BEFORE calling `process_task`: the first worker to create it
       wins the task, everyone else skips it. So many *identical* workers can
       race over the same task list with no duplicated work and no rank/world
       ranges -- and subclasses can't forget to claim. A worker killed mid-task
       leaves an orphan temp dir.
    4. **Clean temps only BETWEEN waves.** Because a live claim and a dead
       worker's leftover look identical on disk, do NOT try to detect liveness.
       Instead the launcher wipes all temp dirs *before* submitting the next
       wave (when nothing is running) and reruns. A task abandoned by a timeout
       is simply redone next wave. This removes any need for heartbeats/leases.
    5. **Leftover-driven + self-rebalancing.** `run()` recomputes the leftover
       (not-yet-done) set at startup, so each wave only works on what's left and
       work is naturally rebalanced across waves. Re-run the launcher until the
       leftover is empty.

    Subclasses implement `list_tasks`, `is_task_done`, `tmp_dir_path`, and
    `process_task` (atomic rename inside; claim is handled by `run()`).

    ## Driving it (cluster-agnostic CLI)
    A subclass module ending in `Subclass.main()` exposes three subcommands so a
    launcher needs no dataset-specific bash:
      - `run`   : process leftover tasks on this GPU (the per-worker entrypoint).
      - `count` : print the leftover count (login-node safe; used to size a wave).
      - `wipe`  : remove all per-task temp dirs (run BETWEEN waves, see point 4).
    Typical launcher loop (one wave): `python -m M wipe`; `N=$(python -m M count)`;
    submit N independent 1-GPU jobs each running `python -m M run`; rerun until 0.
    NOTE: keep the subclass's `__init__` / `list_tasks` / `is_task_done` /
    `tmp_dir_path` free of heavy imports (torch, etc.) so `count`/`wipe` stay
    cheap on the login node; do heavy imports lazily inside `process_task`.
    """

    # ==========================
    # Methods to Override (Start)
    # ==========================

    def list_tasks(self) -> list:
        """Return ALL tasks in a stable order (e.g. sorted by size descending so
        heavy tasks start first). Items can be any type process_task accepts."""
        raise NotImplementedError("Subclasses must implement this method.")

    def is_task_done(self, task: Any) -> bool:
        """True iff the task's final 'done marker' artifact exists. Must key on
        the artifact published LAST by process_task, so truthiness == complete."""
        raise NotImplementedError("Subclasses must implement this method.")

    def tmp_dir_path(self, task: Any) -> str:
        """Path of the per-task temp dir. `run()` claims it (atomic mkdir) before
        calling process_task; process_task writes its outputs here, then
        atomically renames them out. Make it unique per task and co-located with
        the output (same filesystem) so the rename is atomic."""
        raise NotImplementedError("Subclasses must implement this method.")

    def process_task(self, task: Any, tmp_dir: str) -> None:
        """Process one already-claimed task. `tmp_dir` exists (created by run()'s
        claim). Must: (1) write outputs into tmp_dir, (2) atomically rename them
        into place with the done-marker (what is_task_done checks) LAST, (3)
        remove tmp_dir on success."""
        raise NotImplementedError("Subclasses must implement this method.")

    def setup(self) -> None:
        """Optional one-time per-worker setup, run by `run()` BEFORE the task loop
        (and never by `count`/`wipe`, so it stays off the login node). Use it for
        work that must happen once per worker rather than once per task -- most
        importantly loading a model onto the GPU. Default no-op."""
        pass

    def final_process(self) -> None:
        pass

    # ==========================
    # Methods to Override (End)
    # ==========================

    @staticmethod
    def claim(path: str) -> bool:
        """Atomically claim a task by creating `path` (its temp dir). Returns
        True if this worker created it (claim won), False if it already exists
        (claimed by a live worker, or an orphan to be wiped between waves).
        os.makedirs without exist_ok is atomic on POSIX, so this is race-safe."""
        try:
            os.makedirs(path)
            return True
        except FileExistsError:
            return False

    def run(self, show_progress: bool = True) -> None:
        self.setup()  # one-time per-worker (e.g. load model); skipped by count/wipe
        tasks = self.list_tasks()
        leftover = [t for t in tasks if not self.is_task_done(t)]
        util.log(f"ParallelTaskProcessor: {len(leftover)}/{len(tasks)} tasks left to process", msg_type='info')
        processed = 0
        for task in tqdm(leftover, disable=not show_progress):
            if self.is_task_done(task):
                continue  # finished by another worker since we listed
            if not self.claim(self.tmp_dir_path(task)):
                continue  # claimed by another worker (or an orphan to wipe next wave)
            self.process_task(task, self.tmp_dir_path(task))
            processed += 1
        util.log(f"ParallelTaskProcessor: this worker processed {processed} tasks", msg_type='success')
        self.final_process()

    def count_leftover(self) -> int:
        return sum(0 if self.is_task_done(t) else 1 for t in self.list_tasks())

    def wipe_tmp_dirs(self) -> int:
        """Remove every per-task temp dir (orphan claims from a prior wave).
        Call ONLY between waves, when no worker is running (see strategy point 4)."""
        n = 0
        for task in self.list_tasks():
            d = self.tmp_dir_path(task)
            if os.path.isdir(d):
                shutil.rmtree(d, ignore_errors=True)
                n += 1
        return n

    # ---- CLI extension hooks (override in subclasses that take args) ----
    @classmethod
    def add_args(cls, parser) -> None:
        """Override to register subclass-specific argparse args on `parser`
        (default: none). Paired with `build` to construct the instance."""
        pass

    @classmethod
    def build(cls, args):
        """Override to build (construct) the instance from the parsed argparse
        Namespace (default: no-arg `cls()`). `args` carries `command` plus whatever
        `add_args` registered."""
        return cls()

    @classmethod
    def main(cls) -> None:
        """CLI entrypoint: `python -m <subclass_module> {run,count,wipe} [args]`.
        Builds the parser (+ subclass `add_args`), constructs via `build`, then
        dispatches. `count` prints only the integer so a launcher can do
        `N=$(python -m M count)`."""
        import argparse
        parser = argparse.ArgumentParser()
        parser.add_argument("command", nargs="?", default="run", choices=["run", "count", "wipe"])
        cls.add_args(parser)
        args = parser.parse_args()
        self = cls.build(args)
        if args.command == "count":
            print(self.count_leftover())
        elif args.command == "wipe":
            util.log(f"ParallelTaskProcessor: wiped {self.wipe_tmp_dirs()} temp dir(s)", msg_type='info')
        else:
            self.run()
