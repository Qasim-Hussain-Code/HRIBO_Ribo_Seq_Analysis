# Running HRIBO on a small laptop

This page records the machine the analysis ran on, what limited it, and the
decisions those limits forced. I am writing it down because most of the
choices in the scripts only make sense against this background, and because
the original guide assumes a 12 core, 31 GB workstation with about 90 GB of
free disk, which is not what I had.

## The machine

| Item | Value |
| --- | --- |
| Model | Laptop, Intel Core i7-13620H (10 cores, 16 threads) |
| Memory | 15.6 GB physical |
| Operating system | Windows 11 Home |
| Linux environment | WSL 2, Ubuntu 26.04 LTS |
| Memory available to WSL | 8 GB, plus 8 GB swap (set in .wslconfig) |
| System drive | 274 GB, about 10 GB free when I started |
| Second drive | none |
| Container engine | Apptainer 1.4.5 (system package inside WSL) |
| Package manager | Miniconda (conda 26.7.2, libmamba solver); mamba 2.9.0 also present |

HRIBO is a Linux Snakemake workflow, so everything computational ran inside
WSL 2. The repository itself lives on the Windows side, under Documents, and
is edited and committed from there.

## Where the disk really is

WSL 2 stores its Linux file system in a single virtual disk file
(ext4.vhdx) on the Windows system drive. Inside WSL, df reports a 1 TB disk
with 900 GB free. That number is meaningless: the file behind it grows on
drive C, which had 10 GB free. Anything written inside WSL can fill the
Windows system drive.

Two facts made the analysis possible at all:

1. The virtual disk file was already 71 GB on disk while only 24 GB were in
   use inside it. Space freed inside WSL is not returned to Windows, but it
   is reused by later writes. In practice the 6 GB of downloads and
   environments written during setup did not grow the file at all.
2. I could not rely on that. The run script therefore watches the free space
   of the Windows drive (visible from WSL as /mnt/c) every 30 seconds and
   stops Snakemake with SIGTERM when it drops below a threshold. Finished
   jobs are kept, so a stopped run resumes after space is made.

Compacting the virtual disk (diskpart, compact vdisk) or switching it to
sparse mode would have reclaimed space properly. Both need administrator
rights on Windows, which the session running the analysis did not have, so
neither was used.

## Network

Download speed decided where the reads came from.

| Source | Measured throughput |
| --- | --- |
| ENA FTP and HTTPS (ftp.sra.ebi.ac.uk) | 0.04 to 0.11 MB/s |
| NCBI SRA mirror on Amazon S3 (sra-pub-run-odp) | about 3 MB/s per connection, 8 MB/s with two |
| conda-forge | about 20 MB/s |
| NCBI genomes FTP | about 0.4 MB/s (small files, fine) |

The full PAO1 dataset is 5.6 GB as gzipped FASTQ from ENA, which would have
taken most of a day at 0.1 MB/s. The same two runs are 4.4 GB as SRA
archives on the NCBI mirror and took about five minutes with six parallel
range requests. The archives are then converted to FASTQ locally with
fastq-dump. This is the only place where I departed from the guide's
download procedure, and the scripts verify the archives with vdb-validate
and check the number of reads against the count ENA publishes for each run.

## What was scaled down, and why

The guide's full PAO1 run needs about 93 GB: 5.6 GB of reads, 8.6 GB of
conda environments, a 1.8 GB DeepRibo container and roughly 83 GB of
working data, most of it uncompressed SAM files from segemehl. That does not
fit in the space I had, and mapping 172 million reads would take well over
an hour on 8 threads.

I therefore ran the complete workflow on a random 10 percent subsample of
each library, drawn with seqtk (seed 11) while the archives were being
converted, so the full FASTQ files never had to exist on disk. Every step of
HRIBO runs unchanged; only the sequencing depth is reduced. The consequences
are discussed in docs/methods.md. The scripts accept SUBSAMPLE_FRACTION=1
to process the full libraries on a machine with the room to do so.

## Resource ceilings used

| Setting | Value | Reason |
| --- | --- | --- |
| Snakemake cores | 8 | leaves threads for Windows and the WSL host services |
| Memory budget for scheduling | 6000 MB | keeps the sum of concurrent jobs under the 8 GB WSL limit |
| Assumed memory per job | 1500 MB | at most four jobs at once |
| Reparation instances | 1 | HRIBO's own recommendation, Reparation is memory hungry |
| Stop threshold on drive C | 3000 MB | leaves Windows room to breathe |

The memory budget is a scheduling budget, not a hard limit; Snakemake does
not kill a job that uses more than it declared. The hard limit here is the
8 GB that .wslconfig gives the whole WSL virtual machine, with 8 GB of swap
behind it.
