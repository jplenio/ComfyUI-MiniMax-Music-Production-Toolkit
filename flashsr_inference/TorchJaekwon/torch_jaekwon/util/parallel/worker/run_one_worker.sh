#!/bin/bash
# [compute node · INSIDE container] the worker · flow map: ../run_parallel_tasks.sh
# Runs `python -m <module> run`, which races the shared task list via atomic claims.
# One of these per GPU. Args are NAMED FLAGS, passed as a string (not env -- SLURM
# splits --export on commas), each value space-free so it word-splits cleanly:
#   -m <module>  -p <python>  -r <repo (→PYTHONPATH)>  -- <app args to `... run`>
set -euo pipefail

MODULE="" PYTHON="" REPO=""
while getopts "m:p:r:" opt; do
  case $opt in
    m) MODULE="$OPTARG" ;;
    p) PYTHON="$OPTARG" ;;
    r) REPO="$OPTARG" ;;
    *) echo "usage: run_one_worker.sh -m <module> -p <python> -r <repo> [-- <app args>]" >&2; exit 1 ;;
  esac
done
shift $((OPTIND - 1))
[[ "${1:-}" == "--" ]] && shift   # remaining "$@" = app args forwarded to the module
: "${MODULE:?-m <module> required}" "${PYTHON:?-p <python> required}" "${REPO:?-r <repo> required}"
cd "$REPO"

# Default to HF offline: from_pretrained() calls (parakeet / semamba / voxcpm /
# tokenizers) then use the warm cache instead of stalling on hub network retries on a
# compute node with no/firewalled internet (a silent slow-import, not an error).
# Overridable -- set HF_HUB_OFFLINE=0 for a run that must download (e.g. first-time local).
export HF_HUB_OFFLINE="${HF_HUB_OFFLINE:-1}"
export TRANSFORMERS_OFFLINE="${TRANSFORMERS_OFFLINE:-1}"
export PYTHONUNBUFFERED=1
export PYTHONPATH="$REPO:${PYTHONPATH:-}"

# Worker identity. Prefer a backend-neutral TJ_WORKER_ID (set by the local backend);
# fall back to SLURM's per-task rank, then this shell's PID -- so the SAME worker runs
# unchanged under any backend (scheduler or bare background processes).
WORKER_ID="${TJ_WORKER_ID:-${SLURM_PROCID:-$$}}"
JOB_ID="${SLURM_JOB_ID:-local}"

# Per-worker LOCAL caches so concurrent workers don't contend on a shared filesystem
# lock (Triton/Inductor/Numba/HF jit caches were a multi-node stall source). Keyed on
# (job, worker) so every worker -- on any backend -- gets its own.
CACHE_BASE="/tmp/parallel_task_cache_${JOB_ID}_${WORKER_ID}"
mkdir -p "$CACHE_BASE"
export TRITON_CACHE_DIR="$CACHE_BASE/triton"
export TORCHINDUCTOR_CACHE_DIR="$CACHE_BASE/inductor"
export NUMBA_CACHE_DIR="$CACHE_BASE/numba"
export XDG_CACHE_HOME="$CACHE_BASE/xdg"

# Identity for the Python side (informational; the atomic-claim race needs no ranks).
# Each prefers its neutral override, then SLURM, then a safe default.
export LOCAL_RANK="${TJ_WORKER_ID:-${SLURM_LOCALID:-0}}"
export RANK="${TJ_WORKER_ID:-${SLURM_PROCID:-0}}"
export WORLD_SIZE="${TJ_WORLD_SIZE:-${SLURM_NTASKS:-1}}"

echo "[worker] host=$(hostname) module=$MODULE WORKER_ID=$WORKER_ID RANK=$RANK LOCAL_RANK=$LOCAL_RANK WORLD_SIZE=$WORLD_SIZE"
"$PYTHON" -m "$MODULE" run "$@"   # "$@" = the forwarded app args (empty for arg-free modules)
