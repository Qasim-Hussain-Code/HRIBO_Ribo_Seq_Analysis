# Troubleshooting

Problems I actually ran into while producing this repository, in the order
they appeared, with what caused them and what fixed them. The HRIBO guide
has a longer catalogue for the workflow itself; this page is limited to what
happened on this machine.

## Setup

### ENA downloads crawl

Symptom: wget from ftp.sra.ebi.ac.uk reported 40 to 110 KB/s, for both FTP
and HTTPS, while conda-forge delivered 20 MB/s from the same shell.

Cause: the route from my network to EMBL-EBI, not the machine.

Fix: fetch the same runs as SRA archives from NCBI's mirror on Amazon S3
(https://sra-pub-run-odp.s3.amazonaws.com/sra/RUN/RUN), which gave about
3 MB/s per connection and scaled with parallel range requests. The archives
are converted to FASTQ locally with fastq-dump. scripts/03_download_reads.sh
does this with six streams and verifies each archive with vdb-validate.

### Running WSL commands from Git Bash mangles paths and quotes

Symptom: `wsl -d Ubuntu -- bash -c '...'` failed with syntax errors, and a
path such as /mnt/c/Users/... arrived inside WSL as
C:/Program Files/Git/mnt/c/Users/....

Cause: Git Bash (MSYS) rewrites arguments that look like POSIX paths before
handing them to Windows programs, and wsl.exe passes the remaining text
through another shell.

Fix: write the commands to a script file and call
`MSYS_NO_PATHCONV=1 wsl -d Ubuntu -- bash /mnt/c/path/to/script.sh`.
From PowerShell the path conversion problem does not occur.

### Long shell commands are cut off

Symptom: a multi-file heredoc failed with "unexpected EOF while looking for
matching quote" at a line number well inside the text.

Cause: the Windows command line has a length limit of roughly 8 KB when a
command is passed to bash as one argument.

Fix: keep shell commands short and write longer files with an editor or a
file-writing tool.

### mamba 2.x rejects --no-default-packages

Snakemake 8 passes that flag to whichever conda frontend it finds and
prefers mamba. mamba 2.9 no longer accepts it; conda 26 does.
scripts/05_run_hribo.sh therefore passes `--conda-frontend conda`. With the
libmamba solver already configured in conda, the speed difference is small.

### conda is not on PATH in non-interactive WSL shells

`conda` is only initialised in interactive shells. Every script that needs
it locates the installation (CONDA_ROOT, or ~/miniconda3 and the usual
alternatives), sources etc/profile.d/conda.sh, and activates environments by
path rather than by name.

## Disk and memory

### df inside WSL is not the number that matters

Inside WSL the root file system reported 900 GB free. The virtual disk
behind it lives on drive C, which had 10 GB free. Deleting files inside WSL
does not shrink the virtual disk, but the space is reused by later writes,
which is why the 20 GB written by this analysis did not grow the file. The
run script watches the free space of /mnt/c (the Windows drive as seen from
WSL) and stops Snakemake with SIGTERM when it drops below a threshold; a
stopped run resumes from the finished jobs.

### Free space on the Windows drive swings by gigabytes within minutes

Symptom: drive C went from 10.4 GB free to 3 GB and back to 12 GB while the
WSL disk file did not change size.

Cause: the Windows page file. WSL 2 keeps the file cache of the Linux
guest in the host's memory. With 6.7 GB of cache in the guest, Windows was
down to 0.8 GB of free memory and grew its system-managed page file to
17 GB on drive C.

Fix: drop the guest's clean page cache periodically (as root in WSL,
`sync; echo 1 > /proc/sys/vm/drop_caches`, WSL allows `wsl -u root` without
a password). Free memory on Windows rose from 0.8 GB to 2.8 GB within a
minute and page file usage fell from 6.2 GB to 3.9 GB. A cap of 8 GB for
the WSL virtual machine in .wslconfig is the other half of the answer.
The disk guard threshold for the main run was set to 2 GB so that page file
fluctuations would not stop the run.

### Passwordless sudo and Windows administrator rights were not available

Consequences: no fstrim, no compaction of the virtual disk (diskpart), no
change to the WSL memory cap without restarting WSL. Everything in this
repository works without them.

## The workflow

### PCA fails with two samples

Expected and documented in the guide. HRIBO/scripts/analyse_variance.R
takes the third principal component, which does not exist with two
samples, and the Snakefile requires the 3-D PCA plot unconditionally. The
run was started with `--keep-going`, so every job not downstream of the PCA
completed. The three jobs left unfinished are runDeseqPreprocessing,
plotPCA and the top-level all target. See the run log under
results/pao1/logs.

### Files HRIBO creates and never deletes

The samuniq rule writes sammulti/SAMPLE.sam.mapped, an uncompressed copy of
the mapped reads, and does not declare it as output, so Snakemake never
removes it. For deep libraries this is the largest file on disk.
scripts/09_cleanup.sh removes it.
