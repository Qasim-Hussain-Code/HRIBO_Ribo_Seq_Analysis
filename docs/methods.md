# Methods

This page describes what was done, in the order it was done, with the
parameters that were used. The scripts under scripts/ are the executable
version of this page; where the two disagree, the scripts are right and this
page needs fixing.

## 1. Data

### Sequencing reads

Both libraries come from BioProject PRJNA379630 (SRA study SRP102099),
deposited by Lawrence Livermore National Laboratory for Grady et al. (2017),
a study of Pseudomonas aeruginosa PAO1 and the environmental isolate
ATCC 33988 grown on glycerol or on n-alkanes. I used the two runs that the
HRIBO guide uses for its first case study: replicate 1 of PAO1 grown on
glycerol, one ribosome profiling library and one matched RNA-seq library
from the same BioSample.

| Run | Sample name here | Library | BioSample | Reads | Bases |
| --- | --- | --- | --- | ---: | ---: |
| SRR5356907 | RIBO-GLY-1 | ribosome profiling | SAMN06617368 | 73,952,429 | 3,697,621,450 |
| SRR5356908 | RNA-GLY-1 | RNA-seq | SAMN06617368 | 98,145,010 | 4,907,250,500 |

Both are 50 nt single-end reads from an Illumina HiSeq 2500. According to
the methods of Grady et al., cells were grown in M9 minimal medium with
5 percent glycerol to OD600 0.8, translation was stopped with
chloramphenicol, lysates were digested with micrococcal nuclease, and
libraries were built with the NEBNext Multiplex Small RNA kit with an
intended insert of about 30 nt. The 3' adapter of that kit reads
AGATCGGAAGAGCACACGTCTGAACTCCAGTCAC into the read, the same sequence as the
Illumina TruSeq adapter, which is what the configuration trims.

The full table of runs, with the ENA checksums of the original FASTQ files,
is in config/pao1/runs.tsv.

### Reference genome and annotation

RefSeq assembly GCF_000006765.1 (ASM676v1), the complete PAO1 chromosome
NC_002516.2, 6,264,404 bp. Genome and annotation were downloaded from the
same assembly directory on the NCBI FTP server and verified against the
md5checksums.txt file published there. The script checks that the sequence
identifier in the FASTA header and in column 1 of the GFF are identical
before anything else runs (scripts/02_get_references.sh). The provenance
record written by that script is kept in
results/pao1/logs/reference_provenance.tsv.

## 2. Obtaining and subsampling the reads

The HRIBO guide downloads gzipped FASTQ from the ENA FTP server. From my
network that server delivered about 0.1 MB/s (measured, see
docs/system_constraints.md), so the same two runs were fetched as SRA
archives from the NCBI mirror on Amazon S3 (sra-pub-run-odp) using six
parallel HTTP range requests, and converted locally with fastq-dump from
sra-tools. Every archive was checked with vdb-validate, which verifies the
stored md5 sums of every data column, before conversion.

Because of the disk limits described in docs/system_constraints.md, the
complete workflow was run on a random subsample of each library rather
than on all reads. Subsampling was done in the same stream as the
conversion:

    fastq-dump -Z --defline-seq '@$ac.$si' --defline-qual '+' RUN.sra \
      | seqtk sample -s 11 - 0.10 \
      | pigz > SAMPLE.fastq.gz

seqtk sample with a fraction is a Bernoulli draw over the whole file, so
every read had the same probability of being kept regardless of its
position in the run. The seed (11) and the fraction (0.10) are recorded
next to the resulting read counts and checksums in
results/pao1/logs/read_download_stats.tsv. The number of reads passing
through fastq-dump was counted independently and matched the read count ENA
lists for each run, which confirms that the archives were complete.

Setting SUBSAMPLE_FRACTION=1 in scripts/03_download_reads.sh converts the
full libraries instead. Nothing else in the repository changes.

## 3. HRIBO

HRIBO 1.8.1 (release tarball from GitHub) was unpacked into the analysis
directory. Version 1.8.1 differs from the 1.8.0 used in the guide by one
fix, an off-by-one error in the rRNA filtering rule, which is why I chose
the newer one. The Snakemake environment was created from HRIBO's own
pinned environment.yaml (Snakemake 8.10.7) by path, inside the analysis
directory, so that nothing was installed into the home directory.

Tool environments for the individual rules were created by Snakemake with
`--use-conda`, using conda as the frontend because mamba 2.x no longer
accepts a flag Snakemake 8 passes. DeepRibo runs from the
docker://gelhausr/deepribo image, pulled and executed by Apptainer 1.4.5,
which answers to the singularity command that Snakemake calls.

### Configuration

config/pao1/config.yaml is a copy of HRIBO's template with these settings:

| Setting | Value | Reason |
| --- | --- | --- |
| adapterS3 | AGATCGGAAGAGCACACGTCTGAACTCCAGTCAC | adapter of the library kit, see above |
| alternativeStartCodons | GTG, TTG | usual alternative initiation codons in bacteria |
| differentialExpression | off | a single condition has nothing to contrast; HRIBO refuses to start otherwise |
| deepribo | on | second ORF caller, better recall on short ORFs |
| metagene readLengths | 25 to 34 | HRIBO default; consistent with the roughly 30 nt inserts the library was built for |
| readstat readLengths | 10 to 80 | HRIBO default |
| includePlotlyJS | online | keeps the interactive HTML plots small enough to commit; SVG copies need no network |
| workflow | full | all stages |

The sample sheet has two rows, RIBO and RNA, both condition GLY, replicate 1.
It is generated with real tab characters by scripts/04_configure.sh, which
also checks that every FASTQ path exists and that the condition name
contains letters only (HRIBO matches it against [a-zA-Z]+).

### Resource settings

The run script (scripts/05_run_hribo.sh) confines every file to the
analysis directory (conda environments, package cache, container image,
temporary files, tool caches) and runs Snakemake with 8 cores, a scheduling
budget of 6000 MB with 1500 MB assumed per job, one Reparation instance at
a time, `--rerun-incomplete`, and a watcher that stops the run if free space
on the Windows system drive falls below 3 GB.

The run was started with `--keep-going`. With only two samples HRIBO's PCA
step cannot produce a third principal component and fails, and because the
Snakefile lists the 3-D PCA plot as a required output there is no switch to
turn it off. `--keep-going` lets every job that does not depend on the PCA
finish. This behaviour is documented in the guide and was expected.

## 4. Deviations from the guide

For a reader comparing this repository with the guide's chapter on PAO1:

1. Reads were fetched from the NCBI SRA mirror as archives and converted
   locally, not as FASTQ from ENA (network speed).
2. A random 10 percent of each library was analysed, not the whole library
   (disk space and time). All downstream steps are unchanged.
3. HRIBO 1.8.1 instead of 1.8.0 (bug fix release).
4. Interactive plots reference plotly.js online instead of embedding it
   (file size).
5. The analysis ran inside WSL 2 on Windows 11 with Apptainer as the
   container engine, rather than on a Linux workstation with Singularity.
6. The final report bundle (HRIBO/scripts/makereport.sh) was not built. It
   copies the BigWig coverage tracks, which are too large for the
   repository; scripts/06_collect_results.sh gathers the small outputs
   instead and writes a manifest with the size and md5 of every file.
7. One HRIBO environment file was replaced. HRIBO/envs/metageneprofiling.yaml
   pins nothing, and in September 2026 conda resolved it to the
   free-threaded build of Python 3.14 and to Kaleido 1.3, which broke two
   rules (a pysam segmentation fault and a missing Chrome for SVG export).
   The copy under patches/ pins Python below 3.13, pandas 2, plotly 5 and
   python-kaleido 0.2.1. Nothing computed by the scripts changes; see
   patches/README.md and docs/troubleshooting.md.

## 5. What the subsampling means for the results

Every stage of HRIBO ran on real data with the real parameters, so the
outputs show what the workflow produces and are suitable for checking that
an installation works and for learning to read HRIBO output. They should
not be used for biological claims about PAO1:

- ORF prediction depends on coverage. With a tenth of the footprints,
  Reparation and DeepRibo see fewer reads per ORF and will miss weakly
  translated and short ORFs that the full library supports, and their
  confidence scores are not comparable with a full-depth run.
- Per-gene counts are a tenth of the full values, so RPKM-style thresholds
  in the metagene filtering (rpkmThreshold 10) exclude more genes.
- Library-level quality metrics (adapter content, read-length distribution,
  fraction of rRNA, metagene shape) are properties of the library, not of
  the depth, and are expected to match the full-depth run closely.

To reproduce the guide's full-depth numbers, rerun scripts 03 to 06 with
SUBSAMPLE_FRACTION=1 on a machine with about 100 GB free.
