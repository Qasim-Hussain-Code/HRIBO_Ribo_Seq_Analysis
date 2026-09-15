#!/usr/bin/env bash
# Install HRIBO and build the conda environments used by this analysis.
#
# Everything lands below WORK_DIR, so the complete installation can be removed
# again with a single rm -rf. Nothing is written to the home directory or to
# the system. I needed this because the analysis ran on a laptop whose system
# disk was almost full, but it is good practice on any shared machine.
#
# Usage:
#   WORK_DIR=/path/to/work bash scripts/01_install_hribo.sh
#
# Variables, all optional:
#   WORK_DIR        where HRIBO, the environments and the results live
#                   (default: <repository>/work)
#   HRIBO_VERSION   HRIBO release to install (default: 1.8.1)
#   CONDA_ROOT      conda installation to use (default: the one on PATH, or
#                   ~/miniconda3 and the usual alternatives)

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
WORK_DIR="${WORK_DIR:-${REPO_ROOT}/work}"
HRIBO_VERSION="${HRIBO_VERSION:-1.8.1}"

ENV_DIR="${WORK_DIR}/.envs"
PKGS_DIR="${WORK_DIR}/.conda_pkgs"

log() { printf '[%s] %s\n' "$(date '+%Y-%m-%d %H:%M:%S')" "$*"; }

# Find conda without depending on an interactive shell.
find_conda() {
  if [[ -n "${CONDA_ROOT:-}" && -x "${CONDA_ROOT}/bin/conda" ]]; then
    echo "$CONDA_ROOT"; return
  fi
  if command -v conda >/dev/null 2>&1; then
    conda info --base; return
  fi
  local d
  for d in "$HOME/miniconda3" "$HOME/miniforge3" "$HOME/mambaforge" "$HOME/anaconda3" /opt/conda; do
    if [[ -x "$d/bin/conda" ]]; then echo "$d"; return; fi
  done
  echo "conda was not found. Install Miniconda or set CONDA_ROOT." >&2
  exit 1
}

CONDA_ROOT="$(find_conda)"
# shellcheck disable=SC1091
source "${CONDA_ROOT}/etc/profile.d/conda.sh"

mkdir -p "$WORK_DIR" "$ENV_DIR" "$PKGS_DIR" "${WORK_DIR}/fastq" "${WORK_DIR}/logs"
cd "$WORK_DIR"
log "work directory : ${WORK_DIR}"
log "conda          : ${CONDA_ROOT} ($(conda --version))"

# 1. HRIBO source. The release tarball is unpacked into WORK_DIR/HRIBO, which is
#    where the Snakefile expects to find itself (configfile: HRIBO/config.yaml).
if [[ -f HRIBO/Snakefile ]]; then
  log "HRIBO is already present, skipping the download"
else
  log "downloading HRIBO ${HRIBO_VERSION}"
  wget -q -c -O "HRIBO-${HRIBO_VERSION}.tar.gz" \
    "https://github.com/RickGelhausen/HRIBO/archive/refs/tags/${HRIBO_VERSION}.tar.gz"
  tar -xzf "HRIBO-${HRIBO_VERSION}.tar.gz"
  mv "HRIBO-${HRIBO_VERSION}" HRIBO
  rm -f "HRIBO-${HRIBO_VERSION}.tar.gz"
  echo "${HRIBO_VERSION}" > HRIBO/VERSION_INSTALLED
fi

# 1b. Local patches. Any file under <repository>/patches/HRIBO/ replaces the
#     file at the same relative path inside the installed HRIBO tree. Each
#     patch is explained in patches/README.md. This is how the metagene
#     environment is pinned to a plotting stack that works without a system
#     browser; the files are copied on every run so that a patch added later
#     is applied by simply rerunning this script.
if [[ -d "${REPO_ROOT}/patches/HRIBO" ]]; then
  while IFS= read -r -d '' p; do
    rel="${p#"${REPO_ROOT}/patches/HRIBO/"}"
    mkdir -p "HRIBO/$(dirname "$rel")"
    cp -p "$p" "HRIBO/${rel}"
    log "patch applied: HRIBO/${rel}"
  done < <(find "${REPO_ROOT}/patches/HRIBO" -type f -print0)
fi

# 2. Package cache. New downloads go into the project cache. The existing conda
#    cache is listed second so that packages already on the machine are reused
#    instead of downloaded again. Conda only writes to the first entry.
export CONDA_PKGS_DIRS="${PKGS_DIR}:${CONDA_ROOT}/pkgs"

# 3. The Snakemake environment, pinned by HRIBO's own environment.yaml. It is
#    created by path rather than by name so that it stays inside WORK_DIR.
if [[ -x "${ENV_DIR}/snakemake/bin/snakemake" ]]; then
  log "snakemake environment already exists"
else
  log "creating the snakemake environment, this takes a few minutes"
  conda env create -q -p "${ENV_DIR}/snakemake" --file HRIBO/environment.yaml
fi

# 4. A small helper environment for fetching and subsampling reads and for
#    drawing the summary figures (scripts/10_plot_figures.py).
if [[ -x "${ENV_DIR}/readtools/bin/fastq-dump" ]]; then
  log "readtools environment already exists"
else
  log "creating the readtools environment (sra-tools, seqtk, pigz, matplotlib, pandas, openpyxl)"
  conda create -q -y -p "${ENV_DIR}/readtools" -c conda-forge -c bioconda \
    "sra-tools>=3.0" seqtk pigz matplotlib pandas openpyxl
fi
# The plotting libraries were added after the environment was first built;
# this adds them to an existing environment that lacks them.
if ! "${ENV_DIR}/readtools/bin/python" -c "import matplotlib, pandas, openpyxl" >/dev/null 2>&1; then
  log "adding matplotlib, pandas and openpyxl to the readtools environment"
  conda install -q -y -p "${ENV_DIR}/readtools" -c conda-forge matplotlib pandas openpyxl
fi

# 5. Record exactly what was installed.
conda list -p "${ENV_DIR}/snakemake" --export > "${WORK_DIR}/logs/env_snakemake_packages.txt"
conda list -p "${ENV_DIR}/readtools" --export > "${WORK_DIR}/logs/env_readtools_packages.txt"

log "done. HRIBO ${HRIBO_VERSION} and both environments are inside ${WORK_DIR}"
