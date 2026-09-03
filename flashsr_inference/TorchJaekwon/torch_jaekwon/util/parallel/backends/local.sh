#!/bin/bash
# [backend] local, no scheduler · flow map: run_parallel_tasks.sh
# Runs the wave as background processes on THIS machine (one per visible GPU) and blocks
# until done. Selected by TJ_BACKEND=local (or -b local). Sets TJ_SYNC=1 so the
# driver loops wave→wave to completion. Needs: TJ_PYTHON TJ_PKG TJ_REPO.

export TJ_SYNC=1

# Spawn the wave locally and wait. Each worker drains the shared claim list, so the
# worker COUNT is just the parallelism width -- we cap it at the number of GPUs (the
# driver's njobs is sized for the scheduler's many-small-jobs model). Leftover beyond
# one wave is mopped up by the driver's blocking loop.
tj_submit_wave() {   # no args -- reads TJ_NJOBS TJ_MODULE TJ_APP_ARGS (TJ_JOB/TJ_HOURS unused locally)
  local njobs="$TJ_NJOBS" module="$TJ_MODULE"
  local worker="$TJ_PKG/util/parallel/worker/run_one_worker.sh"
  local ngpu=1 pids=() rc=0 i p

  # GPU count, default 1 (CPU / single device). Guard nvidia-smi: under the driver's
  # `set -o pipefail` a bare `nvidia-smi | wc -l` would abort the whole run on a box
  # without it (the pipeline inherits nvidia-smi's 127 exit).
  if command -v nvidia-smi >/dev/null 2>&1; then
    ngpu=$(nvidia-smi -L 2>/dev/null | wc -l) || ngpu=1
    (( ngpu >= 1 )) || ngpu=1
  fi
  (( njobs > ngpu )) && njobs=$ngpu
  echo "[local] launching $njobs worker(s) across $ngpu GPU(s) for module=$module"

  for (( i=0; i<njobs; i++ )); do
    CUDA_VISIBLE_DEVICES=$(( i % ngpu )) TJ_WORKER_ID="$i" TJ_WORLD_SIZE="$njobs" \
      bash "$worker" -m "$module" -p "$TJ_PYTHON" -r "$TJ_REPO" -- $TJ_APP_ARGS &
    pids+=($!)
  done

  # Block until every worker exits; surface a non-zero status if any failed.
  for p in "${pids[@]}"; do wait "$p" || rc=1; done
  return $rc
}
