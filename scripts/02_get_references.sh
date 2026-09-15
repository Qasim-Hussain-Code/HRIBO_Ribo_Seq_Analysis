#!/usr/bin/env bash
# Fetch the Pseudomonas aeruginosa PAO1 reference genome and annotation.
#
# Both files are taken from the same RefSeq assembly directory
# (GCF_000006765.1, ASM676v1) so that the sequence identifier in the FASTA
# header and in column 1 of the GFF agree. If they did not, HRIBO would run to
# the end and count zero reads on every feature without ever complaining, so
# the script checks this explicitly at the end.
#
# Usage:
#   WORK_DIR=/path/to/work bash scripts/02_get_references.sh
#
# Variables, all optional:
#   WORK_DIR   analysis directory (default: <repository>/work)
#   ASSEMBLY   RefSeq assembly name (default: GCF_000006765.1_ASM676v1)

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
WORK_DIR="${WORK_DIR:-${REPO_ROOT}/work}"
ASSEMBLY="${ASSEMBLY:-GCF_000006765.1_ASM676v1}"

# RefSeq lays its FTP tree out by accession digits: GCF/000/006/765/<assembly>
acc="${ASSEMBLY%%_ASM*}"                 # GCF_000006765.1
prefix="${acc%%_*}"                      # GCF
digits="${acc#*_}"; digits="${digits%%.*}"   # 000006765
BASE="https://ftp.ncbi.nlm.nih.gov/genomes/all/${prefix}/${digits:0:3}/${digits:3:3}/${digits:6:3}/${ASSEMBLY}"

log() { printf '[%s] %s\n' "$(date '+%Y-%m-%d %H:%M:%S')" "$*"; }

mkdir -p "${WORK_DIR}/reference" "${WORK_DIR}/logs"
cd "${WORK_DIR}/reference"
log "assembly : ${ASSEMBLY}"
log "source   : ${BASE}"

for f in "${ASSEMBLY}_genomic.fna.gz" "${ASSEMBLY}_genomic.gff.gz" md5checksums.txt; do
  wget -q -c -O "$f" "${BASE}/${f}"
done

# NCBI publishes md5 sums for every file in the assembly directory.
for f in "${ASSEMBLY}_genomic.fna.gz" "${ASSEMBLY}_genomic.gff.gz"; do
  want="$(grep -F "./${f}" md5checksums.txt | cut -d' ' -f1)"
  have="$(md5sum "$f" | cut -d' ' -f1)"
  if [[ "$want" != "$have" ]]; then
    echo "md5 mismatch for ${f}: expected ${want}, got ${have}" >&2
    exit 1
  fi
  log "md5 verified: ${f}"
done

gunzip -c "${ASSEMBLY}_genomic.fna.gz" > "${WORK_DIR}/genome.fa"
gunzip -c "${ASSEMBLY}_genomic.gff.gz" > "${WORK_DIR}/annotation.gff"

# The sequence identifiers must agree between the two files.
fasta_ids="$(grep '^>' "${WORK_DIR}/genome.fa" | sed 's/^>//' | cut -d' ' -f1 | sort -u)"
gff_ids="$(grep -v '^#' "${WORK_DIR}/annotation.gff" | cut -f1 | sort -u)"
log "FASTA sequence IDs: $(echo "$fasta_ids" | tr '\n' ' ')"
log "GFF sequence IDs  : $(echo "$gff_ids" | tr '\n' ' ')"
if [[ "$fasta_ids" != "$gff_ids" ]]; then
  echo "sequence identifiers differ between genome.fa and annotation.gff" >&2
  exit 1
fi

# A short provenance record next to the logs.
{
  printf 'assembly\t%s\n' "$ASSEMBLY"
  printf 'source\t%s\n' "$BASE"
  printf 'retrieved\t%s\n' "$(date -u '+%Y-%m-%dT%H:%M:%SZ')"
  printf 'genome_md5_gz\t%s\n' "$(md5sum "${ASSEMBLY}_genomic.fna.gz" | cut -d' ' -f1)"
  printf 'annotation_md5_gz\t%s\n' "$(md5sum "${ASSEMBLY}_genomic.gff.gz" | cut -d' ' -f1)"
  printf 'genome_length_bp\t%s\n' "$(grep -v '^>' "${WORK_DIR}/genome.fa" | tr -d '\n' | wc -c)"
  printf 'sequence_ids\t%s\n' "$(echo "$fasta_ids" | tr '\n' ',')"
} > "${WORK_DIR}/logs/reference_provenance.tsv"

log "annotated features by type:"
grep -v '^#' "${WORK_DIR}/annotation.gff" | cut -f3 | sort | uniq -c | sort -rn | head -12
log "done. genome.fa and annotation.gff are in ${WORK_DIR}"
