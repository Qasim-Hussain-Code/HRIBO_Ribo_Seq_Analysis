#!/usr/bin/env bash
# Print what this machine can offer the analysis: memory, cores, free disk on
# the paths that matter, and whether conda and a container engine are present.
#
# Usage:
#   WORK_DIR=/path/to/work bash scripts/00_check_system.sh
#
# Nothing is changed. Run it before deciding how much data to process.

set -uo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
WORK_DIR="${WORK_DIR:-${REPO_ROOT}/work}"

echo "== host =="
echo "kernel      : $(uname -sr)"
if grep -qi microsoft /proc/version 2>/dev/null; then
  echo "environment : WSL 2 (the virtual disk lives on the Windows system drive; watch its free space, not just df here)"
else
  echo "environment : native Linux"
fi
echo "cpu threads : $(nproc)"
awk '/MemTotal|MemAvailable|SwapTotal/ { printf "%-12s: %.1f GB\n", $1, $2 / 1048576 }' /proc/meminfo

echo
echo "== disk =="
printf '%-40s %10s %10s\n' "path" "free_GB" "size_GB"
for p in "$WORK_DIR" "$HOME" /tmp /mnt/c; do
  [[ -e "$p" ]] || continue
  df -B1G --output=avail,size "$p" 2>/dev/null | tail -n 1 \
    | awk -v p="$p" '{ printf "%-40s %10s %10s\n", p, $1, $2 }'
done

echo
echo "== software =="
for t in conda mamba apptainer singularity snakemake wget curl; do
  if command -v "$t" >/dev/null 2>&1; then
    printf '%-12s %s\n' "$t" "$(command -v "$t")"
  else
    printf '%-12s %s\n' "$t" "not on PATH"
  fi
done
for d in "$HOME/miniconda3" "$HOME/miniforge3" "$HOME/mambaforge" "$HOME/anaconda3" /opt/conda; do
  [[ -x "$d/bin/conda" ]] && echo "conda root   $d ($("$d/bin/conda" --version 2>/dev/null))"
done
[[ -f /proc/sys/user/max_user_namespaces ]] && echo "user namespaces: $(cat /proc/sys/user/max_user_namespaces) (needed for unprivileged containers)"

echo
echo "== this repository's analysis directory =="
echo "WORK_DIR    : $WORK_DIR"
if [[ -d "$WORK_DIR" ]]; then
  du -sh "$WORK_DIR" 2>/dev/null
  for sub in .envs .snakemake/conda .snakemake/singularity .conda_pkgs fastq sra; do
    [[ -d "${WORK_DIR}/${sub}" ]] && du -sh "${WORK_DIR}/${sub}" 2>/dev/null
  done
else
  echo "(does not exist yet)"
fi
