#!/usr/bin/env python
"""Minimal, runnable ParallelTaskProcessor example -- no GPU and no model needed.

Each task just sleeps briefly and writes one small output file, so you can watch N
workers split the list and see claim / resume / atomic-publish in action. This is the
shape every real subclass follows; swap the bodies for your own work.

Try it (local, no scheduler) from anywhere:
    TJ_BACKEND=local bash <this dir>/launch.example.sh -j demo
Rerun it -> prints "0 leftover" (already done). Start over with:
    rm -rf "${PARALLEL_DEMO_OUT:-/tmp/parallel_demo_out}"
"""
import os
import shutil
import time

from torch_jaekwon.util.parallel.parallel_task_processor import ParallelTaskProcessor

OUT = os.environ.get("PARALLEL_DEMO_OUT", "/tmp/parallel_demo_out")
N = int(os.environ.get("PARALLEL_DEMO_N", "8"))


class ExampleTask(ParallelTaskProcessor):
    def list_tasks(self):                      # ALL units of work (any type), stable order
        return list(range(N))

    def _marker(self, t):                      # the per-task done-marker
        return os.path.join(OUT, f"task_{t:03d}.done")

    def is_task_done(self, t):                 # True iff the done-marker exists
        return os.path.exists(self._marker(t))

    def tmp_dir_path(self, t):                 # per-task temp dir; run() claims it via mkdir
        return os.path.join(OUT, f".tmp_{t:03d}")

    def process_task(self, t, tmp_dir):        # tmp_dir already exists (the claim)
        time.sleep(0.3)                        # <- pretend this is GPU work
        staged = os.path.join(tmp_dir, "out")
        with open(staged, "w") as f:
            f.write(f"task {t} done by pid {os.getpid()}\n")
        os.replace(staged, self._marker(t))    # publish the done-marker LAST (atomic rename)
        shutil.rmtree(tmp_dir, ignore_errors=True)


if __name__ == "__main__":
    os.makedirs(OUT, exist_ok=True)
    ExampleTask.main()                         # subcommands: run | count | wipe
