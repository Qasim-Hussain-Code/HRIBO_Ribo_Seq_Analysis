#!/usr/bin/env bash
# Run HRIBO with every byte confined to WORK_DIR and with explicit ceilings on
# CPU, memory and free disk.
#
#   bash scripts/05_run_hribo.sh                          full run
#   bash scripts/05_run_hribo.sh -n                       dry run
#   bash scripts/05_run_hribo.sh --conda-create-envs-only build the tool environments only
#   bash scripts/05_run_hribo.sh --keep-going             finish everything not downstream of a failure
#   bash scripts/05_run_hribo.sh --unlock                 release a stale lock after a hard stop
#
# Any argument is passed straight on to snakemake.
#
# Variables, all optional:
#   WORK_DIR      analysis directory (default: <repository>/work)
#   CPUS          cores handed to snakemake (default: 8)
#   MEM_MB        memory budget snakemake schedules against, in MB (default: 6000)
#   JOB_MEM_MB    memory every rule is assumed to need, in MB (default: 1500)
#   GUARD_PATHS   space separated paths whose free space is watched (default: WORK_DIR)
#   MIN_FREE_MB   stop the run when a guarded path drops below this (default: 3000)
#   USE_DEEPRIBO  set to 0 to run without a container engine (default: 1)
#
# Why the four cache locations are redirected: --directory only decides where
# the results go. Conda environments, package tarballs, container images and
# temporary files all default to places outside the project (the invocation
# directory, ~/miniconda3/pkgs, ~/.cache, /tmp). On this laptop the home disk
# had no room for any of that, so each of them is pointed into WORK_DIR.
#
# Why --conda-frontend conda: snakemake 8 passes --no-default-packages to the
# frontend, mamba 2.x no longer accepts that flag, conda still does.
#
# Why a disk guard: the analysis ran inside WSL 2, whose virtual disk grows
# on the Windows system drive. That drive had about 10 GB free. A watcher
# checks the guarded paths every 30 s and stops snakemake cleanly (SIGTERM)
# before the host runs out of space. Completed jobs are kept; the run can be
# resumed after making room.

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
WORK_DIR="${WORK_DIR:-${REPO_ROOT}/work}"
CPUS="${CPUS:-8}"
MEM_MB="${MEM_MB:-6000}"
JOB_MEM_MB="${JOB_MEM_MB:-1500}"
GUARD_PATHS="${GUARD_PATHS:-${WORK_DIR}}"
MIN_FREE_MB="${MIN_FREE_MB:-3000}"
USE_DEEPRIBO="${USE_DEEPRIBO:-1}"

log() { printf '[%s] %s\n' "$(date '+%Y-%m-%d %H:%M:%S')" "$*"; }
die() { printf '[error] %s\n' "$*" >&2; exit 1; }

[[ -f "${WORK_DIR}/HRIBO/Snakefile" ]]    || die "HRIBO not found in ${WORK_DIR}"
[[ -f "${WORK_DIR}/HRIBO/samples.tsv" ]] || die "sample sheet missing, run scripts/04_configure.sh first"
cd "$WORK_DIR"

# 1. Everything the run writes stays below WORK_DIR.
PROJECT_TMP="${WORK_DIR}/tmp"
PROJECT_PKGS="${WORK_DIR}/.conda_pkgs"
PROJECT_CACHE="${WORK_DIR}/.cache"
PROJECT_SIF="${WORK_DIR}/.singularity_cache"
mkdir -p "$PROJECT_TMP" "$PROJECT_PKGS" "$PROJECT_CACHE" "$PROJECT_SIF" logs

# 2. Activate the snakemake environment without an interactive shell.
find_conda() {
  if [[ -n "${CONDA_ROOT:-}" && -x "${CONDA_ROOT}/bin/conda" ]]; then echo "$CONDA_ROOT"; return; fi
  if command -v conda >/dev/null 2>&1; then conda info --base; return; fi
  local d
  for d in "$HOME/miniconda3" "$HOME/miniforge3" "$HOME/mambaforge" "$HOME/anaconda3" /opt/conda; do
    [[ -x "$d/bin/conda" ]] && { echo "$d"; return; }
  done
  die "conda was not found"
}
CONDA_ROOT="$(find_conda)"
# shellcheck disable=SC1091
source "${CONDA_ROOT}/etc/profile.d/conda.sh"
conda activate "${WORK_DIR}/.envs/snakemake"

# 3. Container engine. Apptainer answers to the name singularity, which is
#    what snakemake calls. A one entry bin directory puts the system Apptainer
#    ahead of the conda build without shadowing anything else.
CONTAINER_FLAGS=()
if [[ "$USE_DEEPRIBO" == "1" ]]; then
  if command -v apptainer >/dev/null 2>&1; then
    mkdir -p "${WORK_DIR}/.bin"
    ln -sf "$(command -v apptainer)" "${WORK_DIR}/.bin/singularity"
    export PATH="${WORK_DIR}/.bin:${PATH}"
  fi
  command -v singularity >/dev/null 2>&1 || die "neither apptainer nor singularity is available; set USE_DEEPRIBO=0 and deepribo: \"off\""
  CONTAINER_FLAGS=(--use-singularity
                   --singularity-prefix "${WORK_DIR}/.snakemake/singularity"
                   --singularity-args "--bind ${WORK_DIR}")
fi

# 4. Disk guard.
free_mb() { df --output=avail -B1M "$1" 2>/dev/null | tail -n 1 | tr -d ' '; }
guard() {
  local pid="$1" p free
  while kill -0 "$pid" 2>/dev/null; do
    for p in $GUARD_PATHS; do
      free="$(free_mb "$p")"
      if [[ -n "$free" ]] && (( free < MIN_FREE_MB )); then
        log "only ${free} MB free on ${p}, below the ${MIN_FREE_MB} MB limit: stopping snakemake"
        date > "${WORK_DIR}/logs/DISK_GUARD_TRIGGERED"
        kill -TERM "$pid" 2>/dev/null || true
        return
      fi
    done
    sleep 30
  done
}

RUN_LOG="${WORK_DIR}/logs/snakemake_$(date '+%Y%m%d_%H%M%S').log"
log "project  : ${WORK_DIR}"
log "snakemake: $(snakemake --version)   conda: $(conda --version)   container: $(command -v singularity >/dev/null 2>&1 && singularity --version || echo none)"
log "limits   : ${CPUS} cores, ${MEM_MB} MB budget, ${JOB_MEM_MB} MB per job, stop below ${MIN_FREE_MB} MB free on: ${GUARD_PATHS}"
log "log      : ${RUN_LOG}"

# 5. The run itself.
set +e
env TMPDIR="$PROJECT_TMP" \
    SINGULARITY_TMPDIR="$PROJECT_TMP" SINGULARITY_CACHEDIR="$PROJECT_SIF" \
    APPTAINER_TMPDIR="$PROJECT_TMP"   APPTAINER_CACHEDIR="$PROJECT_SIF" \
    XDG_CACHE_HOME="$PROJECT_CACHE" \
    CONDA_PKGS_DIRS="${PROJECT_PKGS}:${CONDA_ROOT}/pkgs" \
snakemake \
  --snakefile HRIBO/Snakefile \
  --directory "$WORK_DIR" \
  --use-conda \
  --conda-prefix "${WORK_DIR}/.snakemake/conda" \
  --conda-frontend conda \
  "${CONTAINER_FLAGS[@]}" \
  --shadow-prefix "${WORK_DIR}/.snakemake/shadow" \
  --cores "$CPUS" \
  --max-threads "$CPUS" \
  --resources mem_mb="$MEM_MB" reparation_instances=1 \
  --default-resources mem_mb="$JOB_MEM_MB" disk_mb=4000 tmpdir="'${PROJECT_TMP}'" \
  --latency-wait 60 \
  --rerun-incomplete \
  --printshellcmds \
  "$@" > >(tee -a "$RUN_LOG") 2>&1 &
SNAKE_PID=$!
guard "$SNAKE_PID" &
GUARD_PID=$!
wait "$SNAKE_PID"
STATUS=$?
kill "$GUARD_PID" 2>/dev/null || true
set -e

if [[ -f "${WORK_DIR}/logs/DISK_GUARD_TRIGGERED" ]]; then
  log "the run was stopped by the disk guard. Free some space, then rerun; snakemake resumes from the finished jobs."
  exit 75
fi
log "snakemake finished with exit status ${STATUS}"
exit "$STATUS"
