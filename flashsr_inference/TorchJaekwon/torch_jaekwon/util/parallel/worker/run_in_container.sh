#!/bin/bash
# [compute node · OUTSIDE container] · flow map: ../run_parallel_tasks.sh
# Enter the container, hand off to run_one_worker.sh. This is the sbatch batch script
# (runs from a SLURM-spooled copy, so it can't find siblings by path). Inputs POSITIONAL,
# never --export (SLURM splits --export on commas; TJ_MOUNTS has commas):
#   $1 image   $2 mounts   $3 worker script (abs)   $4 worker arg string
set -euo pipefail
srun --container-image="$1" --container-mounts="$2" bash "$3" ${4:-}
