#!/bin/bash
# EXAMPLE cluster contract for run_parallel_tasks.sh -- VARIABLES ONLY. Copy this into
# your project, set the values, and point TJ_CLUSTER_ENV at your copy. The driver
# sources the backend named by TJ_BACKEND (or -b; default slurm_pyxis), so this file
# no longer defines tj_submit_wave -- it just declares what the backend consumes.
# (See ../README.md and ../backends/<name>.sh for each backend's required vars.)

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

export TJ_PYTHON="${TJ_PYTHON:-python}"              # interpreter (login node + jobs)
export TJ_REPO="$HERE"                                # repo root; here = this examples dir
# Make the task module importable on the login node (count/wipe) regardless of CWD.
export PYTHONPATH="$TJ_REPO:${PYTHONPATH:-}"
# torch_jaekwon install dir, so "$TJ_PKG/util/parallel/..." resolves.
export TJ_PKG="${TJ_PKG:-$("$TJ_PYTHON" -c 'import torch_jaekwon, os; print(os.path.dirname(torch_jaekwon.__file__))')}"

# --- pick a backend + its values --------------------------------------------
# The driver picks the backend from TJ_BACKEND (or -b); default slurm_pyxis.
#   export TJ_BACKEND=local          # backends/local.sh: no scheduler, nothing else needed
#   export TJ_BACKEND=slurm_pyxis    # backends/slurm_pyxis.sh: set the vars below
#     export TJ_ACCOUNT="PLACEHOLDER_ACCOUNT"
#     export TJ_PARTITION="PLACEHOLDER_PARTITION"
#     export TJ_IMAGE="/path/to/container.sqsh"
#     export TJ_MOUNTS="$HOME:$HOME,/data:/data"   # commas OK (passed positionally)
#
# Escape hatch: for a cluster no shipped backend fits, define tj_submit_wave HERE and
# the driver uses it as-is (it sources a backend only when none is already defined): tj_submit_wave()
