#!/usr/bin/env bash
# Fetch the sequencing runs from the NCBI SRA cloud mirror, convert them to
# FASTQ and, if asked, draw a random subsample.
#
# Why the SRA mirror and not the ENA FASTQ files: from my network the ENA FTP
# server delivered about 0.1 MB/s, while the NCBI mirror on Amazon S3 gave
# about 3 MB/s per connection and scaled with parallel range requests. Both
# hold the same runs. The ENA route is the one the original guide uses and is
# described in docs/methods.md for anyone with a fast link to EMBL-EBI.
#
# Each run is handled in turn: download, validate the archive with
# vdb-validate, stream it through fastq-dump and (optionally) seqtk sample,
# compress, record read counts and checksums, then delete the archive. Peak
# disk use is therefore one archive plus one FASTQ file, not the whole dataset.
#
# Usage:
#   WORK_DIR=/path/to/work bash scripts/03_download_reads.sh [download|convert|all]
#
# Variables, all optional:
#   WORK_DIR             analysis directory (default: <repository>/work)
#   RUNS_TABLE           table of runs (default: config/pao1/runs.tsv)
#   SUBSAMPLE_FRACTION   fraction of reads to keep, 1 keeps every read (default: 1)
#   SUBSAMPLE_SEED       random seed handed to seqtk (default: 11)
#   STREAMS              parallel range requests per archive (default: 6)
#   KEEP_SRA             set to 1 to keep the .sra archives (default: 0)

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
WORK_DIR="${WORK_DIR:-${REPO_ROOT}/work}"
RUNS_TABLE="${RUNS_TABLE:-${REPO_ROOT}/config/pao1/runs.tsv}"
SUBSAMPLE_FRACTION="${SUBSAMPLE_FRACTION:-1}"
SUBSAMPLE_SEED="${SUBSAMPLE_SEED:-11}"
STREAMS="${STREAMS:-6}"
KEEP_SRA="${KEEP_SRA:-0}"
STEP="${1:-all}"

ENV_DIR="${WORK_DIR}/.envs"
SRA_DIR="${WORK_DIR}/sra"
FASTQ_DIR="${WORK_DIR}/fastq"
STATS="${WORK_DIR}/logs/read_download_stats.tsv"

log() { printf '[%s] %s\n' "$(date '+%Y-%m-%d %H:%M:%S')" "$*"; }
die() { printf '[error] %s\n' "$*" >&2; exit 1; }

case "$STEP" in download|convert|all) ;; *) die "step must be download, convert or all";; esac
[[ -f "$RUNS_TABLE" ]] || die "runs table not found: ${RUNS_TABLE}"
mkdir -p "$SRA_DIR" "$FASTQ_DIR" "${WORK_DIR}/logs"

odp_url() { printf 'https://sra-pub-run-odp.s3.amazonaws.com/sra/%s/%s' "$1" "$1"; }

remote_size() {
  curl -sSI -L --retry 5 --retry-delay 10 "$1" | tr -d '\r' \
    | awk 'tolower($1)=="content-length:" {print $2}' | tail -n 1
}

# Download one object with several concurrent range requests. Every part
# resumes from its own length, so an interrupted download continues where it
# stopped. The parts are joined and the final size compared with the server's.
fetch_parallel() {
  local url="$1" dest="$2" size="$3" n="$4"
  local chunk=$(( (size + n - 1) / n ))
  local i start end part have pids=() failed=0
  for (( i = 0; i < n; i++ )); do
    start=$(( i * chunk )); end=$(( (i + 1) * chunk - 1 ))
    (( end >= size )) && end=$(( size - 1 ))
    (( start > end )) && continue
    part="${dest}.part${i}"
    have=0; [[ -f "$part" ]] && have="$(stat -c %s "$part")"
    (( have >= end - start + 1 )) && continue
    curl -sS -L --retry 10 --retry-delay 15 --retry-all-errors \
         -r "$(( start + have ))-${end}" "$url" >> "$part" &
    pids+=("$!")
  done
  local p
  for p in "${pids[@]}"; do
    wait "$p" || failed=1
  done
  (( failed )) && die "one or more range requests failed for ${url}; rerun to resume"
  : > "${dest}.tmp"
  for (( i = 0; i < n; i++ )); do
    [[ -f "${dest}.part${i}" ]] && cat "${dest}.part${i}" >> "${dest}.tmp"
  done
  local got; got="$(stat -c %s "${dest}.tmp")"
  (( got == size )) || die "size mismatch for ${dest}: expected ${size}, got ${got}"
  mv -f "${dest}.tmp" "$dest"
  rm -f "${dest}".part*
}

download_run() {
  local acc="$1" dest="${SRA_DIR}/$1.sra" url size
  url="$(odp_url "$acc")"
  size="$(remote_size "$url")"
  [[ -n "$size" ]] || die "could not read the size of ${url}"
  if [[ -f "$dest" && "$(stat -c %s "$dest")" == "$size" ]]; then
    log "${acc}: archive already complete (${size} bytes)"
    return
  fi
  log "${acc}: downloading ${size} bytes with ${STREAMS} streams"
  fetch_parallel "$url" "$dest" "$size" "$STREAMS"
  log "${acc}: download complete"
}

activate_readtools() {
  [[ -x "${ENV_DIR}/readtools/bin/fastq-dump" ]] \
    || die "readtools environment missing, run scripts/01_install_hribo.sh first"
  export PATH="${ENV_DIR}/readtools/bin:${PATH}"
  # sra-tools keeps a small settings file; keep that inside the project too.
  export NCBI_SETTINGS="${WORK_DIR}/.ncbi/user-settings.mkfg"
  mkdir -p "${WORK_DIR}/.ncbi"
  if [[ ! -f "$NCBI_SETTINGS" ]]; then
    printf '/LIBS/GUID = "%s"\n/libs/cloud/report_instance_identity = "false"\n' \
      "$(cat /proc/sys/kernel/random/uuid)" > "$NCBI_SETTINGS"
  fi
}

convert_run() {
  local acc="$1" name="$2" expected_reads="$3"
  local sra="${SRA_DIR}/${acc}.sra" out="${FASTQ_DIR}/${name}.fastq.gz"
  local counter="${WORK_DIR}/logs/${name}.dumped_reads.txt"
  if [[ -s "$out" && -s "$counter" ]]; then
    log "${name}: FASTQ already present, skipping conversion"
    return
  fi
  [[ -f "$sra" ]] || die "archive missing: ${sra}"

  log "${acc}: validating the archive"
  vdb-validate "$sra" > "${WORK_DIR}/logs/${acc}.vdb-validate.log" 2>&1 \
    || die "vdb-validate failed for ${sra}, see logs/${acc}.vdb-validate.log"

  # fastq-dump streams the reads to stdout. The compact defline keeps the
  # files small. The line count of the full stream is captured on the side so
  # that the number of reads actually dumped can be checked against ENA.
  local sampler="cat"
  if awk -v f="$SUBSAMPLE_FRACTION" 'BEGIN { exit !(f < 1) }'; then
    sampler="seqtk sample -s ${SUBSAMPLE_SEED} - ${SUBSAMPLE_FRACTION}"
    log "${acc}: converting and keeping a random fraction of ${SUBSAMPLE_FRACTION} (seed ${SUBSAMPLE_SEED})"
  else
    log "${acc}: converting all reads"
  fi
  fastq-dump -Z --defline-seq '@$ac.$si' --defline-qual '+' "$sra" \
    | tee >(awk 'END { print NR / 4 }' > "$counter") \
    | $sampler \
    | pigz -p 4 > "${out}.tmp"
  mv -f "${out}.tmp" "$out"

  local dumped kept md5
  dumped="$(cat "$counter")"
  kept="$(pigz -dc "$out" | awk 'END { print NR / 4 }')"
  md5="$(md5sum "$out" | cut -d' ' -f1)"
  if [[ "$dumped" != "$expected_reads" ]]; then
    die "${acc}: dumped ${dumped} reads but ENA lists ${expected_reads}"
  fi
  log "${name}: ${dumped} reads in the archive, ${kept} reads written, md5 ${md5}"
  if [[ ! -s "$STATS" ]]; then
    printf 'run_accession\tsample_name\treads_in_archive\treads_kept\tsubsample_fraction\tsubsample_seed\tfastq_md5\tfastq_bytes\n' > "$STATS"
  fi
  printf '%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\n' "$acc" "$name" "$dumped" "$kept" \
    "$SUBSAMPLE_FRACTION" "$SUBSAMPLE_SEED" "$md5" "$(stat -c %s "$out")" >> "$STATS"

  if [[ "$KEEP_SRA" != "1" ]]; then
    rm -f "$sra"
    log "${acc}: archive removed to save disk"
  fi
}

[[ "$STEP" != "download" ]] && activate_readtools

# The runs table is tab separated; the first line is the header.
while IFS=$'\t' read -r acc name method condition replicate _rest; do
  [[ -z "$acc" || "$acc" == "run_accession" ]] && continue
  expected="$(awk -F'\t' -v a="$acc" 'NR==1 { for (i = 1; i <= NF; i++) if ($i == "read_count") c = i } $1 == a { print $c }' "$RUNS_TABLE")"
  log "=== ${acc} -> ${name} (${method}, ${condition}, replicate ${replicate}) ==="
  case "$STEP" in
    download) download_run "$acc" ;;
    convert)  convert_run "$acc" "$name" "$expected" ;;
    all)      download_run "$acc"; convert_run "$acc" "$name" "$expected" ;;
  esac
done < "$RUNS_TABLE"

log "done. FASTQ files:"
ls -lh "$FASTQ_DIR"
