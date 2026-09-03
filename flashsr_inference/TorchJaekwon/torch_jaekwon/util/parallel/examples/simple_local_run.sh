#!/bin/bash
# simple_local_run.sh -- the bare essence: NO driver, NO contract, NO wave loop.
#
# Launches N copies of `python -m <module> run` in the background, each pinned to its own
# GPU with its own cache dir, then waits. That's the whole thing. The atomic-claim
# mechanism (see ../README.md) guarantees the N workers process DISJOINT tasks with zero
# coordination -- so you do NOT need run_parallel_tasks.sh, a backend, or TJ_SYNC
# here. Those only add convenience on top of this: GPU pinning, resume-by-wave, crash
# recovery, and the auto-loop.
#
# Notes:
#   - Correctness needs only "run it N times" -- the claim does the rest.
#   - CUDA_VISIBLE_DEVICES + the per-worker cache below are hygiene, not correctness
#     (spread across GPUs; don't share one torch-compile cache).
#   - One pass completes the whole list (each worker drains all leftover); rerun only if
#     a worker was killed.
#
# Usage (run from your repo root so `-m <module>` resolves):
#   bash simple_local_run.sh src.preprocess.my_task 3
set -euo pipefail

MODULE="${1:?usage: simple_local_run.sh <python.module> [n_workers]}"
N="${2:-3}"
PYTHON="${TJ_PYTHON:-python}"
REPO="$(pwd)"

pids=()
for (( i=0; i<N; i++ )); do
  cache="/tmp/simple_worker_$i"
  CUDA_VISIBLE_DEVICES="$i" \
  PYTHONPATH="$REPO:${PYTHONPATH:-}" \
  TRITON_CACHE_DIR="$cache/triton" TORCHINDUCTOR_CACHE_DIR="$cache/inductor" \
  NUMBA_CACHE_DIR="$cache/numba" XDG_CACHE_HOME="$cache/xdg" \
    "$PYTHON" -m "$MODULE" run &
  pids+=($!)
done

rc=0
for p in "${pids[@]}"; do wait "$p" || rc=1; done
exit "$rc"
