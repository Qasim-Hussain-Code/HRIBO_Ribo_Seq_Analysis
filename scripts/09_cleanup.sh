#!/usr/bin/env bash
# Remove what a finished HRIBO run no longer needs, in three levels.
#
#   bash scripts/09_cleanup.sh leftovers   files HRIBO creates but never deletes
#   bash scripts/09_cleanup.sh caches      leftovers plus package caches, temp and shadow directories
#   bash scripts/09_cleanup.sh all         the entire analysis directory
#
# Level one is safe after any run and recovers most of the space: segemehl's
# SAM output is declared temporary in HRIBO, but the filtered copy written by
# the samuniq rule (sammulti/*.sam.mapped) is not, and for deep libraries it
# is the single largest file on disk. Level two keeps results and
# environments. Level three removes everything, including the environments
# and the container image, and asks for confirmation.
#
# Variables, all optional:
#   WORK_DIR   analysis directory (default: <repository>/work)

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
WORK_DIR="${WORK_DIR:-${REPO_ROOT}/work}"
LEVEL="${1:-leftovers}"

log() { printf '[%s] %s\n' "$(date '+%Y-%m-%d %H:%M:%S')" "$*"; }
die() { printf '[error] %s\n' "$*" >&2; exit 1; }

[[ -d "$WORK_DIR" ]] || die "analysis directory not found: ${WORK_DIR}"
cd "$WORK_DIR"

before="$(du -sm . | cut -f1)"

case "$LEVEL" in
  leftovers|caches|all) ;;
  *) die "level must be leftovers, caches or all" ;;
esac

log "before: ${before} MB in ${WORK_DIR}"

# Level one.
find sammulti -name '*.sam.mapped' -type f -delete 2>/dev/null || true
find sammulti -name '*.sam.unmapped' -type f -delete 2>/dev/null || true
rm -rf sra
log "leftovers removed"

if [[ "$LEVEL" == "caches" || "$LEVEL" == "all" ]]; then
  rm -rf tmp .cache .conda_pkgs .singularity_cache .snakemake/shadow .snakemake/metadata
  log "caches removed"
fi

if [[ "$LEVEL" == "all" ]]; then
  printf 'This deletes %s completely, including environments and results. Type yes to continue: ' "$WORK_DIR"
  read -r answer
  [[ "$answer" == "yes" ]] || die "aborted"
  cd "$REPO_ROOT"
  rm -rf "$WORK_DIR"
  log "analysis directory removed"
  exit 0
fi

after="$(du -sm . | cut -f1)"
log "after : ${after} MB (freed $(( before - after )) MB)"
