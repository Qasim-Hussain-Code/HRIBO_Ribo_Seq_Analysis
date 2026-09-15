#!/usr/bin/env bash
# Put the sample sheet and the configuration in place for an HRIBO run.
#
# The sample sheet is generated from config/<dataset>/runs.tsv with printf so
# that the separators are real tabs, and every FASTQ path it refers to is
# checked before HRIBO ever sees it. The configuration is copied unchanged
# from config/<dataset>/config.yaml, so the file under version control is the
# one that was actually used.
#
# Usage:
#   WORK_DIR=/path/to/work bash scripts/04_configure.sh [dataset]
#
# The dataset name selects the folder under config/ (default: pao1).

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
WORK_DIR="${WORK_DIR:-${REPO_ROOT}/work}"
DATASET="${1:-pao1}"
CFG="${REPO_ROOT}/config/${DATASET}"

log() { printf '[%s] %s\n' "$(date '+%Y-%m-%d %H:%M:%S')" "$*"; }
die() { printf '[error] %s\n' "$*" >&2; exit 1; }

[[ -d "$CFG" ]] || die "no configuration folder for dataset '${DATASET}' under config/"
[[ -f "${CFG}/runs.tsv" && -f "${CFG}/config.yaml" ]] || die "config/${DATASET} needs runs.tsv and config.yaml"
[[ -f "${WORK_DIR}/HRIBO/Snakefile" ]] || die "HRIBO is not installed in ${WORK_DIR}, run scripts/01_install_hribo.sh first"
[[ -s "${WORK_DIR}/genome.fa" && -s "${WORK_DIR}/annotation.gff" ]] || die "genome.fa or annotation.gff missing, run scripts/02_get_references.sh first"

cp "${CFG}/config.yaml" "${WORK_DIR}/HRIBO/config.yaml"
log "configuration copied to ${WORK_DIR}/HRIBO/config.yaml"

# The sample sheet. HRIBO needs the five column header even when the second
# FASTQ column is empty, as it is for single-end data.
SHEET="${WORK_DIR}/HRIBO/samples.tsv"
{
  printf 'method\tcondition\treplicate\tfastqFile\tfastqFile2\n'
  tail -n +2 "${CFG}/runs.tsv" | while IFS=$'\t' read -r acc name method condition replicate _rest; do
    [[ -z "$acc" ]] && continue
    printf '%s\t%s\t%s\tfastq/%s.fastq.gz\t\n' "$method" "$condition" "$replicate" "$name"
  done
} > "$SHEET"
log "sample sheet written to ${SHEET}:"
cat -A "$SHEET" | sed 's/\$$//'

# Checks that HRIBO would otherwise report late or not at all.
missing=0
while IFS=$'\t' read -r method condition replicate fastq _rest; do
  [[ "$method" == "method" || -z "$method" ]] && continue
  case "$method" in RIBO|RNA|TIS|TTS) ;; *) log "method '${method}' is not one HRIBO knows"; missing=1 ;; esac
  [[ "$condition" =~ ^[A-Za-z]+$ ]] || { log "condition '${condition}' must contain letters only"; missing=1; }
  [[ "$replicate" =~ ^[0-9]+$ ]]    || { log "replicate '${replicate}' must be a number"; missing=1; }
  if [[ -s "${WORK_DIR}/${fastq}" ]]; then
    log "  OK   ${fastq}"
  else
    log "  MISSING ${fastq}"; missing=1
  fi
done < "$SHEET"
(( missing == 0 )) || die "fix the problems above before running HRIBO"

log "done. Next: bash scripts/05_run_hribo.sh -n"
