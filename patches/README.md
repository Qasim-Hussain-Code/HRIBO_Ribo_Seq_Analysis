# Patches applied to the HRIBO tree

Every file below patches/HRIBO/ replaces the file at the same relative path
inside the installed HRIBO directory. scripts/01_install_hribo.sh copies
them on every run, after unpacking the release tarball, so a fresh
installation ends up in the same state as the one used for the results.
HRIBO's own source is not modified in any other way.

| File | What it changes | Why |
| --- | --- | --- |
| HRIBO/envs/metageneprofiling.yaml | pins python below 3.13, pandas 2, plotly 5, python-kaleido 0.2.1 | unpinned, conda resolved free-threaded Python 3.14 and Kaleido 1.3 in September 2026; pysam then segfaulted and Kaleido demanded a system Chrome. Details in docs/troubleshooting.md. |

The pins are the loosest that fix the problem; they do not change what the
scripts compute, only which builds of the libraries run them.
