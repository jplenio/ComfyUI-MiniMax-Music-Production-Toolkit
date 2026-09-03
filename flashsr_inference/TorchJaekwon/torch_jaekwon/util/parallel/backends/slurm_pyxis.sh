#!/bin/bash
# [backend] sbatch + pyxis/enroot · flow map: run_parallel_tasks.sh
# Submits one wave as an `sbatch --array` of independent 1-GPU jobs, each entering the
# container via run_in_container.sh. Selected by TJ_BACKEND=slurm_pyxis (or -b).
#
# Config (env file): TJ_PYTHON TJ_REPO TJ_PKG TJ_ACCOUNT TJ_PARTITION TJ_IMAGE
#   TJ_MOUNTS (may contain commas) · optional TJ_LOG_DIR (default $TJ_REPO/artifacts/slurm_log)
# Per-wave (set by the driver): TJ_JOB TJ_NJOBS TJ_HOURS TJ_MODULE TJ_APP_ARGS

tj_submit_wave() {   # no args -- reads the TJ_* contract vars above
  local log="${TJ_LOG_DIR:-$TJ_REPO/artifacts/slurm_log}/$TJ_JOB"; mkdir -p "$log"
  # image/mounts/worker/cmdline go POSITIONALLY to run_in_container.sh (never --export:
  # SLURM splits --export on commas, and TJ_MOUNTS has commas).
  sbatch \
    --array="1-$TJ_NJOBS" --nodes=1 --gpus-per-node=1 --ntasks-per-node=1 \
    --partition="$TJ_PARTITION" --account="$TJ_ACCOUNT" \
    --time="$TJ_HOURS:00:00" --job-name="$TJ_JOB" \
    --output="$log/%A_%a.out" --error="$log/%A_%a.err" \
    "$TJ_PKG/util/parallel/worker/run_in_container.sh" \
    "$TJ_IMAGE" "$TJ_MOUNTS" "$TJ_PKG/util/parallel/worker/run_one_worker.sh" \
    "-m $TJ_MODULE -p $TJ_PYTHON -r $TJ_REPO -- $TJ_APP_ARGS"
}
