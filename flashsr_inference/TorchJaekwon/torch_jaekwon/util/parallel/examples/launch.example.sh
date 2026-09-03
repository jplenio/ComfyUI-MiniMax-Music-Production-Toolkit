#!/bin/bash
# EXAMPLE thin launcher: wire the contract, then run the demo task through the driver.
# Copy this pattern into your project (set TJ_CLUSTER_ENV, exec the driver with -M).
#
#   TJ_BACKEND=local bash launch.example.sh -j demo     # local, runs to completion
#   bash launch.example.sh -j demo                       # cluster: rerun until 0 leftover
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
export TJ_CLUSTER_ENV="$HERE/env_setup.example.sh"

exec bash "$HERE/../run_parallel_tasks.sh" -M example_task "$@"
