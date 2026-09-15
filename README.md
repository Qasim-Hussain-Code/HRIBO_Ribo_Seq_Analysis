# HRIBO Ribo-Seq Analysis

A complete, reproducible run of the HRIBO ribosome profiling workflow on the
Pseudomonas aeruginosa PAO1 dataset used as the first case study in the
Ribo-seq guide by Muhammad Aammar Tufail, carried out on a laptop with
about 10 GB of free disk and 8 GB of memory for Linux. Every stage of HRIBO
ran, from adapter trimming to ORF prediction with Reparation and DeepRibo,
on a random 10 percent subsample of each library. The scripts scale to the
full libraries on a larger machine by changing one variable.

I wrote this repository to answer a practical question: can the analysis
in the guide be reproduced end to end when the machine is nowhere near the
12 core, 31 GB, 90 GB free workstation the guide assumes? It can, with the
adjustments recorded here, and the price is sequencing depth rather than
any shortcut in the workflow.

## What is in the repository

```text
.
|-- README.md                  this file
|-- LICENSE                    MIT, covers the scripts and text in this repository
|-- CITATION.cff               how to cite this repository and the work it builds on
|-- config/pao1/
|   |-- runs.tsv               the two SRA runs, their sample names and ENA metadata
|   `-- config.yaml            HRIBO configuration, with every changed setting commented
|-- scripts/
|   |-- 00_check_system.sh     memory, cores, free disk on the paths that matter
|   |-- 01_install_hribo.sh    HRIBO 1.8.1 and two conda environments, all inside WORK_DIR
|   |-- 02_get_references.sh   PAO1 genome and annotation from RefSeq, md5 and ID checks
|   |-- 03_download_reads.sh   SRA archives from the NCBI mirror, validation, conversion, subsampling
|   |-- 04_configure.sh        sample sheet with real tabs and the configuration, with checks
|   |-- 05_run_hribo.sh        resource-capped, self-contained Snakemake runner with a disk guard
|   |-- 06_collect_results.sh  copies the small outputs into results/ with a manifest
|   |-- 07_summarise_results.py  summary tables from the logs and result files
|   |-- 08_record_environment.sh  resolved package lists and container identity
|   `-- 09_cleanup.sh          removes leftovers, caches, or the whole analysis directory
|-- patches/
|   |-- README.md              why two HRIBO environment files are replaced
|   `-- HRIBO/envs/            the replacement files, copied over HRIBO by the install script
|-- docs/
|   |-- methods.md             what was done, parameters, deviations from the guide
|   |-- system_constraints.md  the machine, its limits, and the decisions they forced
|   `-- troubleshooting.md     every problem met on the way, with cause and fix
|-- environment/               package lists of every environment used, host details
`-- results/pao1/              HRIBO outputs small enough to keep, logs, summaries, manifest
    `-- README.md              a reader's guide to the result files
```

The analysis directory itself (WORK_DIR, 36 GB at the end of the run) is
not part of the repository. It is rebuilt by the scripts.

## Background in brief

Ribosome profiling (Ribo-seq) sequences the roughly 20 to 34 nt pieces of
mRNA that translating ribosomes protect from nuclease digestion. Mapped to
the genome, these footprints show which regions are being translated and
how heavily, at a resolution that RNA-seq cannot reach. Run together with
RNA-seq from the same lysate, footprint density can be normalised by
transcript abundance to give translational efficiency. In bacteria and
archaea the method is the most effective way to find short open reading
frames that genome annotation misses.

HRIBO (Gelhausen et al., 2021) is a Snakemake workflow built for bacterial
and archaeal Ribo-seq. It trims adapters (cutadapt), removes rRNA and tRNA
reads, maps with segemehl, keeps unique mappers, builds coverage tracks,
profiles read lengths and metagene shapes, counts reads per feature, calls
ORFs independently of the annotation with Reparation and DeepRibo, and,
when the design allows, tests differential expression and translational
efficiency.

The data are one Ribo-seq and one RNA-seq library of P. aeruginosa PAO1
grown on glycerol, from Grady et al. (2017), SRA runs SRR5356907 and
SRR5356908. A single condition without replicates is the smallest design
that exercises the whole workflow; it cannot support differential analysis
or PCA, and the run shows exactly where that limit bites.

## How the analysis was run

The full account is in docs/methods.md. In short:

1. HRIBO 1.8.1 and a pinned Snakemake 8.10.7 environment were installed
   inside a single analysis directory in WSL 2 (Ubuntu 26.04) on Windows 11.
2. The PAO1 genome and annotation (RefSeq GCF_000006765.1) were downloaded
   from one assembly directory and checked against NCBI's md5 sums and
   against each other.
3. The two runs were fetched as SRA archives from NCBI's cloud mirror with
   parallel range requests, verified with vdb-validate, converted with
   fastq-dump and subsampled to 10 percent with seqtk (seed 11) in the same
   stream. Read counts were checked against the ENA record of each run.
4. HRIBO ran with 8 cores, a 6 GB scheduling budget, DeepRibo in an
   Apptainer container, and a watcher that would stop the run if the
   Windows system drive fell below 2 GB free. `--keep-going` was used
   because the PCA step cannot work with two samples.
5. The small outputs were copied into results/ with a manifest, and the
   resolved package list of every environment was written to environment/.

## Results

The complete tables are in results/pao1/summary/, the files they were
built from are in results/pao1/, and results/pao1/README.md explains what
each file is. What follows is the short version.

### Reads

| | RIBO-GLY-1 | RNA-GLY-1 |
| --- | ---: | ---: |
| Reads in the SRA archive | 73,952,429 | 98,145,010 |
| Reads kept (random 10 percent, seed 11) | 7,394,173 | 9,811,418 |
| Reads with adapter (cutadapt) | 95.6 percent | 91.5 percent |
| Reads too short after trimming | 0.7 percent | 0.5 percent |
| Bases retained after trimming | 53.5 percent | 68.0 percent |
| Reads surviving trimming | 7,341,712 | 9,764,868 |
| Reads mapping uniquely (segemehl) | 900,858 | 1,405,641 |
| Unique mappers after rRNA and tRNA removal | 639,010 | 382,107 |
| Mean read length of the final alignments | 32.0 nt | 33.2 nt |

The trimming statistics reproduce the guide's full-depth values to the
first decimal (95.7 and 91.5 percent adapter content, 53.5 and 68.0
percent of bases retained), which is what one expects from a random
subsample: adapter content and insert length are properties of the
library, not of the depth. The Ribo-seq library retains far fewer bases
because footprints of 25 to 34 nt are much shorter than the 50 nt read.

Only 12 percent of the Ribo-seq reads and 14 percent of the RNA-seq reads
map uniquely. Both libraries are dominated by rRNA, which maps to four
near-identical operons in PAO1 and is discarded with the other
multi-mappers; the explicit rRNA and tRNA filter removes a further third
of the Ribo-seq and three quarters of the RNA-seq unique mappers.

### ORF predictions

| Caller | ORFs | File |
| --- | ---: | --- |
| Reparation | 1,965 | auxiliary/predictions_reparation.xlsx |
| DeepRibo (of 14,001 candidates scored) | 3,209 | auxiliary/predictions_deepribo.xlsx |
| Merged overview, all rows | 8,775 | auxiliary/overview.xlsx |
| Merged overview, annotated genes | 5,677 | auxiliary/overview.xlsx, sheet annotated |

Both callers ran to completion, with their diagnostic plots (P-site
offsets, metagene profile, precision-recall and ROC curves for
Reparation; estimated coverage parameters for DeepRibo). At a tenth of the
depth these are not the calls the full library would give, and the guide
does not report counts for its full-depth run, so no comparison is
offered here. The metagene profiles and the read length distribution of
the footprint library are in results/pao1/metageneprofiling/.

### What did not run

Three of the 163 jobs did not complete: runDeseqPreprocessing, plotPCA
and the top-level all target. This is the outcome the guide describes for
this two-sample design; HRIBO's PCA script asks for a third principal
component that two samples cannot provide. Every other output was
produced.

### Time and space

| Item | Measured |
| --- | --- |
| Jobs completed | 160 of 163 |
| Snakemake wall clock, all invocations | 2 h 4 min (8 cores) |
| Reparation alone | 44 min, almost all of it BLAST against Swiss-Prot |
| segemehl mapping, both libraries | 12.7 min (7.9 min for the RNA-seq library) |
| DeepRibo, parsing to prediction | 13 min |
| Analysis directory at the end | 36 GB: 9.9 GB tool environments, 1.3 GB Snakemake and helper environments, 1.8 GB DeepRibo image, 8.6 GB of uncompressed SAM leftovers HRIBO never deletes, 4.5 GB and 865,913 files under deepribo/ |
| Growth of the WSL virtual disk file | none; drive C ended with 9.3 GB free |

The wall clock includes one failed Reparation attempt of 40 minutes that
had to be repeated after the environment fix described in
docs/troubleshooting.md. The run was completed in three Snakemake
invocations; results/pao1/summary/run_overview.tsv lists each one.

## Reproducing it

Requirements: Linux or WSL 2, conda (Miniconda or Miniforge), Apptainer or
Singularity for DeepRibo, about 25 GB of disk for the subsampled run or
about 100 GB for the full libraries, and an internet connection.

```bash
git clone https://github.com/Qasim-Hussain-Code/HRIBO_Ribo_Seq_Analysis.git
cd HRIBO_Ribo_Seq_Analysis

export WORK_DIR=/path/with/enough/space/hribo_pao1   # default: ./work

bash scripts/00_check_system.sh
bash scripts/01_install_hribo.sh
bash scripts/02_get_references.sh
SUBSAMPLE_FRACTION=0.10 SUBSAMPLE_SEED=11 bash scripts/03_download_reads.sh
bash scripts/04_configure.sh pao1
bash scripts/05_run_hribo.sh -n              # dry run: 163 jobs expected
bash scripts/05_run_hribo.sh --keep-going    # the run
bash scripts/06_collect_results.sh pao1
python scripts/07_summarise_results.py
bash scripts/08_record_environment.sh
```

Set SUBSAMPLE_FRACTION=1 for the full libraries. Every script explains its
variables in its header, and every script can be rerun; finished steps are
skipped.

On WSL 2, run the scripts from a WSL shell with WORK_DIR pointing inside the
Linux file system, not under /mnt/c, and read docs/system_constraints.md
first.

## Resource use on this machine

| Item | Measured |
| --- | --- |
| SRA archives downloaded | 4.4 GB, about 5 minutes with six streams |
| Subsampled FASTQ | 153 MB (RIBO) and 281 MB (RNA) |
| Conda environments (18 tool environments plus Snakemake and helpers) | 11.2 GB |
| DeepRibo container image | 1.8 GB |
| Memory inside WSL | stayed under the 8 GB cap, swap unused |

The timing and disk figures of the workflow itself are in the results
section above and in results/pao1/logs.

## Limitations

- Ten percent of the reads. Library-level quality metrics are properties
  of the library and should match a full-depth run; ORF calls and per-gene
  counts are not comparable with the guide's full-depth numbers and must
  not be used for biological claims about PAO1. docs/methods.md explains
  what changes with depth.
- One condition, no replicates. Differential expression, translational
  efficiency and PCA are out of reach by design.
- The results were produced on WSL 2 with Apptainer rather than on a Linux
  workstation with Singularity. I saw no difference in behaviour, but it is
  a different platform from the guide's.

## References

1. Gelhausen R, Svensson SL, Froschauer K, Heyl F, Hadjeras L, Sharma CM,
   Eggenhofer F, Backofen R. HRIBO: high-throughput analysis of bacterial
   ribosome profiling data. Bioinformatics. 2021;37(14):2061-2063.
   <https://doi.org/10.1093/bioinformatics/btaa959>
2. Grady SL, Malfatti SA, Gunasekera TS, Dalley BK, Lyman MG, Striebich RC,
   Mayhew MB, Zhou CL, Ruiz ON, Dugan LC. A comprehensive multi-omics
   approach uncovers adaptations for growth and survival of Pseudomonas
   aeruginosa on n-alkanes. BMC Genomics. 2017;18:334.
   <https://doi.org/10.1186/s12864-017-3708-4>
3. Tufail MA. Ribo-seq Guide using the HRIBO Pipeline. Codanics; 2026.
   <https://codanics.com/books/bioinfo/riboseq/HRIBO/>
4. Tufail MA, Jordan B, Hadjeras L, Gelhausen R, Cassidy L, Habenicht T,
   Gutt M, Hellwig L, Backofen R, Tholey A, Sharma CM, Schmitz RA.
   Uncovering the small proteome of Methanosarcina mazei using Ribo-seq and
   peptidomics under different nitrogen conditions. Nat Commun.
   2024;15:8659. <https://doi.org/10.1038/s41467-024-53008-8>
5. Mölder F, Jablonski KP, Letcher B, Hall MB, Tomkins-Tinch CH, Sochat V,
   Forster J, Lee S, Twardziok SO, Kanitz A, Wilm A, Holtgrewe M, Rahmann
   S, Nahnsen S, Köster J. Sustainable data analysis with Snakemake.
   F1000Research. 2021;10:33. <https://doi.org/10.12688/f1000research.29032.2>
6. Martin M. Cutadapt removes adapter sequences from high-throughput
   sequencing reads. EMBnet.journal. 2011;17(1):10-12.
   <https://doi.org/10.14806/ej.17.1.200>
7. Hoffmann S, Otto C, Kurtz S, Sharma CM, Khaitovich P, Vogel J, Stadler
   PF, Hackermüller J. Fast mapping of short sequences with mismatches,
   insertions and deletions using index structures. PLoS Comput Biol.
   2009;5(9):e1000502. <https://doi.org/10.1371/journal.pcbi.1000502>
8. Ndah E, Jonckheere V, Giess A, Valen E, Menschaert G, Van Damme P.
   REPARATION: ribosome profiling assisted (re-)annotation of bacterial
   genomes. Nucleic Acids Res. 2017;45(20):e168.
   <https://doi.org/10.1093/nar/gkx758>
9. Clauwaert J, Menschaert G, Waegeman W. DeepRibo: a neural network for
   precise gene annotation of prokaryotes by combining ribosome profiling
   signal and binding site patterns. Nucleic Acids Res. 2019;47(6):e36.
   <https://doi.org/10.1093/nar/gkz061>
10. Liao Y, Smyth GK, Shi W. featureCounts: an efficient general purpose
    program for assigning sequence reads to genomic features.
    Bioinformatics. 2014;30(7):923-930.
    <https://doi.org/10.1093/bioinformatics/btt656>
11. Quinlan AR, Hall IM. BEDTools: a flexible suite of utilities for
    comparing genomic features. Bioinformatics. 2010;26(6):841-842.
    <https://doi.org/10.1093/bioinformatics/btq033>
12. Danecek P, Bonfield JK, Liddle J, Marshall J, Ohan V, Pollard MO,
    Whitwham A, Keane T, McCarthy SA, Davies RM, Li H. Twelve years of
    SAMtools and BCFtools. GigaScience. 2021;10(2):giab008.
    <https://doi.org/10.1093/gigascience/giab008>
13. Ewels P, Magnusson M, Lundin S, Käller M. MultiQC: summarize analysis
    results for multiple tools and samples in a single report.
    Bioinformatics. 2016;32(19):3047-3048.
    <https://doi.org/10.1093/bioinformatics/btw354>

## License

The scripts, configuration and documentation in this repository are
released under the MIT License (see LICENSE). HRIBO is distributed under
its own license (GPL-3.0). The sequencing data belong to the depositors of
BioProject PRJNA379630 and are used here under the public access terms of
the Sequence Read Archive.
