#!/usr/bin/env python3
"""Build summary tables from a collected HRIBO run.

Reads the files that scripts/06_collect_results.sh placed under
results/<name>/ and writes a few small tables into results/<name>/summary/:

    read_processing.tsv   reads per sample at each stage, from the download
                          statistics, the cutadapt reports and the MultiQC
                          general statistics
    orf_predictions.tsv   number of ORFs called by Reparation and DeepRibo,
                          before and after HRIBO's filtering
    job_timings.tsv       wall-clock time per rule, from the Snakemake log
    run_overview.tsv      jobs finished, jobs failed, total wall-clock time

Only the Python standard library is used, so the script runs with any
Python 3.8 or newer. Spreadsheet row counts are read straight from the
XLSX archive rather than through a spreadsheet library.

Usage:
    python scripts/07_summarise_results.py [results_name]     (default: pao1)
"""

import csv
import glob
import os
import re
import sys
import zipfile
from collections import defaultdict
from datetime import datetime

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
NAME = sys.argv[1] if len(sys.argv) > 1 else "pao1"
RES = os.path.join(REPO_ROOT, "results", NAME)
OUT = os.path.join(RES, "summary")


def log(msg):
    print(f"[summarise] {msg}")


def read_tsv(path):
    with open(path, newline="") as fh:
        return list(csv.DictReader(fh, delimiter="\t"))


def write_tsv(path, rows, columns):
    with open(path, "w", newline="") as fh:
        w = csv.writer(fh, delimiter="\t", lineterminator="\n")
        w.writerow(columns)
        for r in rows:
            w.writerow([r.get(c, "") for c in columns])
    log(f"wrote {os.path.relpath(path, REPO_ROOT)} ({len(rows)} rows)")


def count_lines(path, skip_header=True, comment="#"):
    n = 0
    with open(path, errors="replace") as fh:
        for i, line in enumerate(fh):
            if comment and line.startswith(comment):
                continue
            if skip_header and i == 0:
                continue
            if line.strip():
                n += 1
    return n


def xlsx_row_counts(path):
    """Return {sheet name: data rows} for an XLSX file, header row excluded."""
    counts = {}
    with zipfile.ZipFile(path) as z:
        wb = z.read("xl/workbook.xml").decode("utf-8", "replace")
        sheets = re.findall(r'<sheet\b[^>]*\bname="([^"]*)"[^>]*\br:id="([^"]*)"', wb)
        rels = z.read("xl/_rels/workbook.xml.rels").decode("utf-8", "replace")
        rel_map = dict(re.findall(r'<Relationship\b[^>]*\bId="([^"]*)"[^>]*\bTarget="([^"]*)"', rels))
        if not rel_map:
            rel_map = {b: a for a, b in re.findall(r'<Relationship\b[^>]*\bTarget="([^"]*)"[^>]*\bId="([^"]*)"', rels)}
        for sheet_name, rid in sheets:
            target = rel_map.get(rid, "")
            member = "xl/" + target.lstrip("/").replace("xl/", "", 1) if not target.startswith("/") else target.lstrip("/")
            if member not in z.namelist():
                continue
            xml = z.read(member).decode("utf-8", "replace")
            rows = len(re.findall(r"<row\b", xml))
            counts[sheet_name] = max(rows - 1, 0)
    return counts


# ---------------------------------------------------------------------------
# 1. Read processing
# ---------------------------------------------------------------------------

def parse_cutadapt(log_path):
    """Return {sample: {...}} from every cutadapt report in the run log."""
    out = {}
    sample = None
    with open(log_path, errors="replace") as fh:
        for line in fh:
            m = re.search(r"-o trimmed(?:paired)?/([^\s/]+?)(?:_q)?\.fastq", line)
            if line.startswith("Command line parameters:") and m:
                sample = m.group(1)
                out[sample] = {}
                continue
            if sample is None:
                continue
            for key, pat in (
                ("cutadapt_reads_processed", r"Total reads processed:\s+([\d,]+)"),
                ("cutadapt_reads_with_adapter", r"Reads with adapters:\s+([\d,]+)\s+\(([\d.]+)%\)"),
                ("cutadapt_reads_too_short", r"Reads that were too short:\s+([\d,]+)\s+\(([\d.]+)%\)"),
                ("cutadapt_reads_written", r"Reads written \(passing filters\):\s+([\d,]+)\s+\(([\d.]+)%\)"),
                ("cutadapt_bases_written", r"Total written \(filtered\):\s+([\d,]+) bp\s+\(([\d.]+)%\)"),
            ):
                mm = re.search(pat, line)
                if mm:
                    out[sample][key] = mm.group(1).replace(",", "")
                    if mm.lastindex and mm.lastindex >= 2:
                        out[sample][key + "_pct"] = mm.group(2)
            if "Total written (filtered)" in line:
                sample = None
    return out


def parse_multiqc_general(path):
    """Return {sample: total_sequences} from multiqc_general_stats.txt."""
    out = {}
    rows = read_tsv(path)
    if not rows:
        return out
    col = next((c for c in rows[0] if c and c.endswith("total_sequences")), None)
    if col is None:
        return out
    for r in rows:
        try:
            out[r["Sample"]] = str(int(float(r[col])))
        except (KeyError, ValueError):
            pass
    return out


def parse_two_column(path):
    """Return {name: value} for HRIBO's small read-count text files."""
    out = {}
    with open(path, errors="replace") as fh:
        for line in fh:
            parts = line.strip().split()
            if len(parts) >= 2 and re.match(r"^[\d.]+$", parts[-1]):
                out[parts[0]] = parts[-1]
    return out


def read_processing(run_log):
    stats_path = os.path.join(RES, "logs", "read_download_stats.tsv")
    samples = {}
    if os.path.exists(stats_path):
        for r in read_tsv(stats_path):
            samples[r["sample_name"]] = {
                "sample": r["sample_name"],
                "run_accession": r["run_accession"],
                "reads_in_archive": r["reads_in_archive"],
                "subsample_fraction": r["subsample_fraction"],
                "reads_kept": r["reads_kept"],
            }
    if run_log:
        for s, d in parse_cutadapt(run_log).items():
            samples.setdefault(s, {"sample": s}).update(d)
    mqc = os.path.join(RES, "qc", "multi", "multiqc_data", "multiqc_general_stats.txt")
    if os.path.exists(mqc):
        totals = parse_multiqc_general(mqc)
        for s in samples:
            for stage in ("raw", "trimmed", "norRNA", "unique"):
                for key in (f"{s}-{stage}", f"{s}_{stage}", f"{s}-{stage}_fastqc"):
                    if key in totals:
                        samples[s][f"fastqc_{stage}_reads"] = totals[key]
                        break
    for fname, key in (("bam_mapped_reads.txt", "mapped_reads_unique_norrna"),
                       ("bam_average_read_lengths.txt", "mean_read_length_final")):
        p = os.path.join(RES, "readcounts", fname)
        if os.path.exists(p):
            for name, value in parse_two_column(p).items():
                for s in samples:
                    if name.startswith(s):
                        samples[s][key] = value
    columns = ["sample", "run_accession", "reads_in_archive", "subsample_fraction", "reads_kept",
               "cutadapt_reads_processed", "cutadapt_reads_with_adapter", "cutadapt_reads_with_adapter_pct",
               "cutadapt_reads_too_short", "cutadapt_reads_written", "cutadapt_bases_written_pct",
               "fastqc_raw_reads", "fastqc_trimmed_reads", "fastqc_norRNA_reads", "fastqc_unique_reads",
               "mapped_reads_unique_norrna", "mean_read_length_final"]
    write_tsv(os.path.join(OUT, "read_processing.tsv"), list(samples.values()), columns)


# ---------------------------------------------------------------------------
# 2. ORF predictions
# ---------------------------------------------------------------------------

def orf_predictions():
    rows = []
    for p in sorted(glob.glob(os.path.join(RES, "reparation", "*", "Predicted_ORFs.txt"))):
        rows.append({"caller": "Reparation", "sample": os.path.basename(os.path.dirname(p)),
                     "stage": "raw output (Predicted_ORFs.txt)", "orfs": count_lines(p)})
    for p in sorted(glob.glob(os.path.join(RES, "deepribo", "*", "predictions.csv"))):
        rows.append({"caller": "DeepRibo", "sample": os.path.basename(os.path.dirname(p)),
                     "stage": "raw output (predictions.csv, every candidate ORF scored)", "orfs": count_lines(p)})
    for fname, caller in (("reparation_annotated.gff", "Reparation"), ("deepribo_merged.gff", "DeepRibo"),
                          ("totalAnnotation.gff", "both, merged with the annotation")):
        p = os.path.join(RES, "tracks", fname)
        if os.path.exists(p):
            rows.append({"caller": caller, "sample": "all", "stage": f"filtered track ({fname})", "orfs": count_lines(p, skip_header=False)})
    for fname, caller in (("predictions_reparation.xlsx", "Reparation"), ("predictions_deepribo.xlsx", "DeepRibo"),
                          ("overview.xlsx", "overview table")):
        p = os.path.join(RES, "auxiliary", fname)
        if os.path.exists(p):
            try:
                for sheet, n in xlsx_row_counts(p).items():
                    rows.append({"caller": caller, "sample": "all", "stage": f"{fname}, sheet {sheet}", "orfs": n})
            except (zipfile.BadZipFile, KeyError) as exc:
                log(f"could not read {fname}: {exc}")
    write_tsv(os.path.join(OUT, "orf_predictions.tsv"), rows, ["caller", "sample", "stage", "orfs"])


# ---------------------------------------------------------------------------
# 3. Job timings from the Snakemake log
# ---------------------------------------------------------------------------

STAMP = re.compile(r"^\[(\w{3} \w{3} +\d+ \d\d:\d\d:\d\d \d{4})\]\s*$")


def parse_timestamp(s):
    return datetime.strptime(re.sub(r"\s+", " ", s), "%a %b %d %H:%M:%S %Y")


def job_timings(run_log):
    starts, rule_of, finished, failed = {}, {}, {}, set()
    last_stamp = None
    pending_rule = None
    first, last = None, None
    with open(run_log, errors="replace") as fh:
        for line in fh:
            m = STAMP.match(line)
            if m:
                last_stamp = parse_timestamp(m.group(1))
                first = first or last_stamp
                last = last_stamp
                continue
            m = re.match(r"^(?:local)?rule (\w+):", line)
            if m:
                pending_rule = m.group(1)
                continue
            m = re.match(r"^\s+jobid: (\d+)", line)
            if m and pending_rule and last_stamp:
                starts[m.group(1)] = last_stamp
                rule_of[m.group(1)] = pending_rule
                pending_rule = None
                continue
            m = re.match(r"^Finished job (\d+)\.", line)
            if m and last_stamp:
                finished[m.group(1)] = last_stamp
                continue
            m = re.match(r"^Error in rule (\w+):", line)
            if m:
                failed.add(m.group(1))
    per_rule = defaultdict(lambda: {"rule": "", "jobs": 0, "total_seconds": 0, "longest_seconds": 0})
    for jid, t0 in starts.items():
        if jid in finished:
            d = int((finished[jid] - t0).total_seconds())
            r = per_rule[rule_of[jid]]
            r["rule"] = rule_of[jid]
            r["jobs"] += 1
            r["total_seconds"] += d
            r["longest_seconds"] = max(r["longest_seconds"], d)
    rows = sorted(per_rule.values(), key=lambda r: -r["total_seconds"])
    write_tsv(os.path.join(OUT, "job_timings.tsv"), rows, ["rule", "jobs", "total_seconds", "longest_seconds"])
    overview = [
        {"item": "run_log", "value": os.path.basename(run_log)},
        {"item": "jobs_started", "value": len(starts)},
        {"item": "jobs_finished", "value": len(finished)},
        {"item": "rules_with_errors", "value": ", ".join(sorted(failed)) or "none"},
        {"item": "wall_clock_seconds", "value": int((last - first).total_seconds()) if first and last else ""},
        {"item": "first_timestamp", "value": first.isoformat(sep=" ") if first else ""},
        {"item": "last_timestamp", "value": last.isoformat(sep=" ") if last else ""},
    ]
    write_tsv(os.path.join(OUT, "run_overview.tsv"), overview, ["item", "value"])


def main():
    if not os.path.isdir(RES):
        sys.exit(f"results directory not found: {RES}")
    os.makedirs(OUT, exist_ok=True)
    logs = sorted(glob.glob(os.path.join(RES, "logs", "snakemake_*.log")))
    run_log = logs[-1] if logs else None
    if run_log is None:
        log("no snakemake_*.log under results/logs; timing and cutadapt tables will be incomplete")
    read_processing(run_log)
    orf_predictions()
    if run_log:
        job_timings(run_log)
    log("done")


if __name__ == "__main__":
    main()
