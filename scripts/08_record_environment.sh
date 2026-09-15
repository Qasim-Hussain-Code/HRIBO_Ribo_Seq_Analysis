#!/usr/bin/env bash
# Record the software that was actually used, package by package.
#
# HRIBO pins its Snakemake environment but lets conda resolve the tool
# environments of the individual rules at run time, so two installations
# made a year apart can differ. This script writes the resolved package list
# of every environment, the container image identity and the host details
# into environment/ so that the run can be repeated with the same versions.
#
# Usage:
#   WORK_DIR=/path/to/work bash scripts/08_record_environment.sh
#
# Variables, all optional:
#   WORK_DIR   analysis directory (default: <repository>/work)

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
WORK_DIR="${WORK_DIR:-${REPO_ROOT}/work}"
OUT="${REPO_ROOT}/environment"

log() { printf '[%s] %s\n' "$(date '+%Y-%m-%d %H:%M:%S')" "$*"; }
die() { printf '[error] %s\n' "$*" >&2; exit 1; }

[[ -d "${WORK_DIR}/.envs/snakemake" ]] || die "snakemake environment not found under ${WORK_DIR}/.envs"
mkdir -p "${OUT}/rule_environments"

find_conda() {
  if command -v conda >/dev/null 2>&1; then conda info --base; return; fi
  local d
  for d in "$HOME/miniconda3" "$HOME/miniforge3" "$HOME/mambaforge" "$HOME/anaconda3" /opt/conda; do
    [[ -x "$d/bin/conda" ]] && { echo "$d"; return; }
  done
  die "conda was not found"
}
CONDA_ROOT="$(find_conda)"
CONDA="${CONDA_ROOT}/bin/conda"

# 1. Host.
{
  printf 'recorded\t%s\n' "$(date -u '+%Y-%m-%dT%H:%M:%SZ')"
  printf 'kernel\t%s\n' "$(uname -sr)"
  printf 'os\t%s\n' "$(. /etc/os-release && echo "$PRETTY_NAME")"
  if grep -qi microsoft /proc/version 2>/dev/null; then printf 'platform\tWSL 2 on Windows\n'; else printf 'platform\tLinux\n'; fi
  printf 'cpu\t%s\n' "$(grep -m1 'model name' /proc/cpuinfo | cut -d: -f2 | sed 's/^ //')"
  printf 'cpu_threads\t%s\n' "$(nproc)"
  printf 'memory_total_gb\t%s\n' "$(awk '/MemTotal/ { printf "%.1f", $2 / 1048576 }' /proc/meminfo)"
  printf 'conda\t%s\n' "$("$CONDA" --version)"
  printf 'conda_solver\t%s\n' "$("$CONDA" config --show solver | awk '{print $2}')"
  command -v apptainer >/dev/null 2>&1 && printf 'apptainer\t%s\n' "$(apptainer --version)"
  printf 'hribo\t%s\n' "$(cat "${WORK_DIR}/HRIBO/VERSION_INSTALLED" 2>/dev/null || echo unknown)"
  printf 'snakemake\t%s\n' "$("${WORK_DIR}/.envs/snakemake/bin/snakemake" --version)"
} > "${OUT}/host.tsv"
log "host details written"

# 2. The two environments this repository creates itself.
"$CONDA" list -p "${WORK_DIR}/.envs/snakemake" --export > "${OUT}/env_snakemake.txt"
"$CONDA" list -p "${WORK_DIR}/.envs/readtools" --export > "${OUT}/env_readtools.txt"
log "snakemake and readtools environments recorded"

# 3. The tool environments Snakemake created for HRIBO's rules. Snakemake
#    keeps a copy of the environment definition next to each environment,
#    which tells us which HRIBO envs/*.yaml the hash belongs to.
n=0
for envdir in "${WORK_DIR}"/.snakemake/conda/*_/; do
  [[ -d "$envdir" ]] || continue
  hash="$(basename "$envdir")"
  spec="${WORK_DIR}/.snakemake/conda/${hash%_}.yaml"
  name="$hash"
  if [[ -f "$spec" ]]; then
    # Match the copy against HRIBO's own files to recover the readable name.
    for y in "${WORK_DIR}"/HRIBO/envs/*.yaml; do
      if cmp -s "$y" "$spec"; then name="$(basename "$y" .yaml)"; break; fi
    done
  fi
  "$CONDA" list -p "$envdir" --export > "${OUT}/rule_environments/${name}.txt"
  n=$(( n + 1 ))
done
log "${n} rule environments recorded"

# 4. The container image.
{
  printf 'image\tdocker://gelhausr/deepribo:latest\n'
  for img in "${WORK_DIR}"/.snakemake/singularity/*.simg; do
    [[ -f "$img" ]] || continue
    printf 'file\t%s\n' "$(basename "$img")"
    printf 'bytes\t%s\n' "$(stat -c %s "$img")"
    printf 'sha256\t%s\n' "$(sha256sum "$img" | cut -d' ' -f1)"
    if command -v apptainer >/dev/null 2>&1; then
      printf 'labels\t%s\n' "$(apptainer inspect --labels "$img" 2>/dev/null | tr '\n' ';')"
    fi
  done
} > "${OUT}/container_deepribo.tsv"
log "container image recorded"

log "done. See ${OUT}"
