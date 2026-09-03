#!/bin/bash
# ══ Parallel task driver ═══════════════════════════════ run on the LOGIN node ══
# Runs ANY ParallelTaskProcessor subclass as N independent 1-GPU workers racing a
# shared task list (crash-safe, resumable). This file is the orchestrator; it holds
# ZERO cluster-specific literals -- VALUES come from a sourced env file, and HOW to
# launch comes from a swappable backend.
#
# ── HOW A RUN FLOWS ──────────────────────────────────────────────────────────
# STRUCTURE:  run_parallel_tasks.sh  →  backends/$TJ_BACKEND.sh  →  worker/
#               [login] orchestrate       [login] submit N workers    [compute] run each
# ------------------------------------------------------------------------------
# [LOGIN] run_parallel_tasks.sh (this file)  driver: wipe → count leftover → tj_submit_wave()
#
# tj_submit_wave() = "launch a wave" -- the ONE function a backend defines. The driver sources
# backends/$TJ_BACKEND.sh, sets the per-wave vars (TJ_NJOBS/TJ_JOB/TJ_HOURS/TJ_MODULE/
# TJ_APP_ARGS), then calls it with NO args. Its body, per backend:
#
#   backends/local.sh         no scheduler
#     tj_submit_wave():  run $TJ_NJOBS× worker/run_one_worker.sh   background, one per GPU
#
#   backends/slurm_pyxis.sh   cluster + pyxis container
#     tj_submit_wave():  sbatch --array=1-$TJ_NJOBS               independent 1-GPU jobs; each runs:
#                          worker/run_in_container.sh             [compute · OUTSIDE container]
#                            srun --container-image →
#                              worker/run_one_worker.sh           [compute · INSIDE  container]
#
# both backends converge on the same worker:
#   worker/run_one_worker.sh   set caches/env → python -m $TJ_MODULE run
#     └─ ParallelTaskProcessor.run()   loop: claim task (atomic mkdir) → process → repeat
# ─────────────────────────────────────────────────────────────────────────────
#
# Contract: the sourced $TJ_CLUSTER_ENV exports TJ_PYTHON / TJ_PKG / TJ_REPO (+ whatever the
# chosen backend needs, e.g. TJ_IMAGE). The driver sources backends/$BACKEND.sh (-b, default
# slurm_pyxis), hands the wave to tj_submit_wave via the TJ_* vars above, and calls it (no args).
# Escape hatch: if the env file already defines tj_submit_wave, the driver keeps it (no backend).
#
# App args after `--` are forwarded verbatim to `python -m <module> {run,count,wipe}`.
# RULE: no spaces/commas in forwarded values (they word-split through the scheduler);
# keep comma-bearing constants in the backend/env (e.g. TJ_MOUNTS).
set -euo pipefail

log()   { echo "[driver] $*"; }
usage() { echo "Usage: $0 -M <python.module> [-b backend] [-j job_name] [-t hours] [-m max_tasks] [-- <app args>]" >&2; }

parse_args() {
  MODULE="" JOB_NAME="parallel_tasks" HOURS=4 MAX_TASKS=40 BACKEND="${TJ_BACKEND:-slurm_pyxis}"
  local OPTIND=1 opt
  while getopts "M:b:j:t:m:" opt; do
    case $opt in
      M) MODULE="$OPTARG" ;;  b) BACKEND="$OPTARG" ;;  j) JOB_NAME="$OPTARG" ;;
      t) HOURS="$OPTARG" ;;   m) MAX_TASKS="$OPTARG" ;;
      *) usage; exit 1 ;;
    esac
  done
  shift $((OPTIND - 1))
  [[ "${1:-}" == "--" ]] && shift   # everything after -- is forwarded to the module
  APP_ARGS=("$@")                    # opaque per-run args (e.g. --config ... --ckpt ...)
  [[ -n "$MODULE" ]] || { echo "ERROR: -M <python.module> is required (e.g. src.preprocess.fisher)" >&2; exit 1; }
}

load_cluster_contract() {
  : "${TJ_CLUSTER_ENV:?set TJ_CLUSTER_ENV=/path/to/cluster/env_setup.sh}"
  # shellcheck disable=SC1090
  source "$TJ_CLUSTER_ENV"   # provides TJ_PYTHON/TJ_PKG/TJ_REPO (+ the backend's vars)
}

# Source the swappable backend (backends/<name>.sh) that defines tj_submit_wave, unless
# the contract already defined it (escape hatch for a cluster no shipped backend fits).
# A backend may also set TJ_SYNC=1 (synchronous -> the driver loops wave->wave).
load_backend() {
  declare -f tj_submit_wave >/dev/null && return 0   # contract predefined it -- keep it
  local f="${TJ_PKG:?contract must export TJ_PKG}/util/parallel/backends/$BACKEND.sh"
  [[ -f "$f" ]] || { echo "ERROR: unknown backend '$BACKEND' ($f not found)" >&2; exit 1; }
  # shellcheck disable=SC1090
  source "$f"
}

# Remove orphan temp dirs from prior waves. Safe ONLY between waves: a live claim
# and a dead worker's orphan look identical on disk. The `wipe` subcommand itself
# is implemented by ParallelTaskProcessor (torch_jaekwon/util/parallel/parallel_task_processor.py).
wipe_orphan_temps() { "$TJ_PYTHON" -m "$MODULE" wipe "${APP_ARGS[@]}"; }

# Leftover (not-yet-done) task count. Prints ONLY the number to stdout (the caller
# captures it), so this must never log to stdout. The `count` subcommand itself is
# implemented by ParallelTaskProcessor (torch_jaekwon/util/parallel/parallel_task_processor.py).
count_leftover() { "$TJ_PYTHON" -m "$MODULE" count "${APP_ARGS[@]}"; }

# One wave = min(leftover, MAX_TASKS) independent 1-GPU workers. The backend packs them
# onto free GPUs; each worker races the list via atomic claims and exits when work runs
# out (no allocated-idle). The wave's inputs are handed to the backend as TJ_* vars (not
# positional args) so a custom tj_submit_wave just reads them -- see README "Writing a backend".
submit_one_wave() {
  local left="$1"
  TJ_NJOBS=$(( left < MAX_TASKS ? left : MAX_TASKS ))     # per-wave contract vars the backend reads:
  TJ_JOB="$JOB_NAME"; TJ_HOURS="$HOURS"; TJ_MODULE="$MODULE"; TJ_APP_ARGS="${APP_ARGS[*]}"
  log "submitting one wave of $TJ_NJOBS independent 1-GPU worker(s)"
  tj_submit_wave
}

# Async backends (e.g. sbatch): submission returns immediately, so do ONE wave and
# let the user rerun this script after it finishes (until 0 leftover).
run_async() {
  wipe_orphan_temps                       # 1. clear prior-wave orphans
  local left; left="$(count_leftover)"    # 2. how much work is left?
  log "module=$MODULE leftover=$left"
  (( left > 0 )) || { log "nothing left to process -- done."; return 0; }
  submit_one_wave "$left"                  # 3. submit
  log "wave submitted. Rerun this script to mop up leftovers (exits when 0)."
}

# Synchronous backend (TJ_SYNC, e.g. local): tj_submit_wave returns only after the wave's
# workers finish, so loop wave->wave here until nothing is left -- one command runs to
# completion. Aborts if a wave makes no progress, so a fast-failing backend can't spin forever.
run_sync() {
  local left prev=""
  while :; do
    wipe_orphan_temps                     # safe: between waves, nothing is running
    left="$(count_leftover)"
    log "module=$MODULE leftover=$left"
    (( left == 0 )) && { log "all tasks done."; return 0; }
    if [[ -n "$prev" ]] && (( left >= prev )); then
      log "ERROR: no progress in the last wave (leftover stuck at $left) -- aborting."
      return 1
    fi
    prev=$left
    submit_one_wave "$left"
  done
}

main() {
  parse_args "$@"
  load_cluster_contract                   # contract file: variables
  load_backend                            # defines tj_submit_wave; may set TJ_SYNC
  # A synchronous backend (e.g. local) sets TJ_SYNC=1 -> loop wave->wave to completion.
  # Async backends (sbatch/...) leave it unset -> submit one wave, you rerun.
  if [[ "${TJ_SYNC:-0}" == "1" ]]; then
    run_sync
  else
    run_async
  fi
}

main "$@"
