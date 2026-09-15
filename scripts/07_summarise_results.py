#!/usr/bin/env python3
"""Build summary tables from a collected HRIBO run.

Reads the files that scripts/06_collect_results.sh placed under
results/<name>/ and writes a few small tables into results/<name>/summary/:

    read_processing.tsv   reads per sample at each stage, from the download
                          statistics, the cutadapt reports and the MultiQC
                          general statistics
    orf_predictions.tsv   number of ORFs called by Reparation and DeepRibo,
                          before and after HRIBO's filtering
    job_timings.tsv       wall-clock time per rule, from the Snakemake logs
    run_overview.tsv      jobs finished, jobs failed and wall-clock time of
                          every Snakemake invocation

Every Snakemake log under results/<name>/logs is read, so a run that was
completed over several invocations (as this one was) is summarised as a
whole. Only the Python standard library is used, so the script runs with
any Python 3.8 or newer. Spreadsheet row counts are read straight from the
XLSX archive rather than through a spreadsheet library.

Usage:
    python scripts/07_summarise_results.py [results_name]     (default: pao1)
"""

import csv
import glob
import io
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


def read_tsv(path_or_handle):
    if isinstance(path_or_handle, str):
        with open(path_or_handle, newline="") as fh:
            return list(csv.DictReader(fh, delimiter="\t"))
    return list(csv.DictReader(path_or_handle, delimiter="\t"))


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
        rel_map = {}
        for tag in re.findall(r"<Relationship\b[^>]*/?>", rels):
            rid = re.search(r'\bId="([^"]*)"', tag)
            target = re.search(r'\bTarget="([^"]*)"', tag)
            if rid and target:
                rel_map[rid.group(1)] = target.group(1)
        for sheet_name, rid in sheets:
            target = rel_map.get(rid, "")
            member = target.lstrip("/") if target.startswith("/") else "xl/" + target
            if member not in z.namelist():
                continue
            xml = z.read(member).decode("utf-8", "replace")
            counts[sheet_name] = max(len(re.findall(r"<row\b", xml)) - 1, 0)
    return counts


# ---------------------------------------------------------------------------
# 1. Read processing
# ---------------------------------------------------------------------------

def parse_cutadapt(log_path):
    """Return {sample: {...}} from every cutadapt report in one run log."""
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


def multiqc_general_stats():
    """Return rows of multiqc_general_stats.txt, from the folder or the zip."""
    folder = os.path.join(RES, "qc", "multi", "multiqc_data", "multiqc_general_stats.txt")
    if os.path.exists(folder):
        return read_tsv(folder)
    zpath = os.path.join(RES, "qc", "multi", "multiqc_data.zip")
    if os.path.exists(zpath):
        with zipfile.ZipFile(zpath) as z:
            for member in z.namelist():
                if member.endswith("multiqc_general_stats.txt"):
                    return read_tsv(io.StringIO(z.read(member).decode("utf-8", "replace")))
    return []


def parse_two_column(path):
    """Return {name: value} for HRIBO's small per-library text files."""
    out = {}
    with open(path, errors="replace") as fh:
        for line in fh:
            parts = line.strip().split()
            if len(parts) >= 2 and re.match(r"^[\d.]+$", parts[-1]):
                out[parts[0]] = parts[-1]
    return out


def read_processing(run_logs):
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
    for lg in run_logs:
        for s, d in parse_cutadapt(lg).items():
            samples.setdefault(s, {"sample": s}).update(d)

    # FastQC totals per processing stage. HRIBO runs FastQC in one folder per
    # stage (qc/1raw, qc/2trimmed, ...) and MultiQC names each row
    # "qc | <stage> | <sample>". Rows without a read count (the rRNA and
    # tRNA content checks) are skipped.
    stage_columns = []
    rows = multiqc_general_stats()
    if rows:
        col = next((c for c in rows[0] if c and c.endswith("total_sequences")), None)
        if col:
            for r in rows:
                parts = [p.strip() for p in r.get("Sample", "").split("|")]
                if len(parts) >= 3:
                    stage, s = parts[-2], parts[-1]
                else:
                    s = next((x for x in samples if r.get("Sample", "").startswith(x)), None)
                    stage = r["Sample"][len(s):].strip("-_") if s else ""
                if s not in samples or not r.get(col):
                    continue
                key = f"fastqc_{stage}_reads"
                if key not in stage_columns:
                    stage_columns.append(key)
                try:
                    samples[s][key] = str(int(float(r[col])))
                except ValueError:
                    pass
    for fname, key in (("total_mapped_reads.txt", "alignments_all_mappers"),
                       ("unique_mapped_reads.txt", "reads_unique_mappers"),
                       ("bam_mapped_reads.txt", "reads_unique_after_rrna_removal"),
                       ("unique_average_read_lengths.txt", "mean_length_unique_mappers"),
                       ("bam_average_read_lengths.txt", "mean_length_final")):
        p = os.path.join(RES, "readcounts", fname)
        if os.path.exists(p):
            for name, value in parse_two_column(p).items():
                for s in samples:
                    if name.startswith(s):
                        samples[s][key] = value
    columns = (["sample", "run_accession", "reads_in_archive", "subsample_fraction", "reads_kept",
                "cutadapt_reads_processed", "cutadapt_reads_with_adapter", "cutadapt_reads_with_adapter_pct",
                "cutadapt_reads_too_short", "cutadapt_reads_written", "cutadapt_bases_written_pct"]
               + stage_columns
               + ["alignments_all_mappers", "reads_unique_mappers", "reads_unique_after_rrna_removal",
                  "mean_length_unique_mappers", "mean_length_final"])
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
                          ("GLY.merged.gff", "both callers, merged per condition"),
                          ("all.gff", "both callers, all conditions")):
        p = os.path.join(RES, "tracks", fname)
        if os.path.exists(p):
            rows.append({"caller": caller, "sample": "all", "stage": f"filtered track ({fname})",
                         "orfs": count_lines(p, skip_header=False)})
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
# 3. Job timings from the Snakemake logs
# ---------------------------------------------------------------------------

STAMP = re.compile(r"^\[(\w{3} \w{3} +\d+ \d\d:\d\d:\d\d \d{4})\]\s*$")


def parse_timestamp(s):
    return datetime.strptime(re.sub(r"\s+", " ", s), "%a %b %d %H:%M:%S %Y")


def parse_run_log(path):
    """Return (starts, rule_of, finished, failed_rules, first, last) for one log."""
    starts, rule_of, finished, failed = {}, {}, {}, []
    last_stamp, pending_rule, first, last = None, None, None, None
    with open(path, errors="replace") as fh:
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
                failed.append(m.group(1))
    return starts, rule_of, finished, failed, first, last


def job_timings(run_logs):
    per_rule = defaultdict(lambda: {"rule": "", "jobs": 0, "total_seconds": 0, "longest_seconds": 0})
    overview = []
    for lg in run_logs:
        with open(lg, errors="replace") as fh:
            text = fh.read()
        if "This was a dry-run" in text:
            continue
        starts, rule_of, finished, failed, first, last = parse_run_log(lg)
        if not starts:
            continue
        for jid, t0 in starts.items():
            if jid in finished:
                d = int((finished[jid] - t0).total_seconds())
                r = per_rule[rule_of[jid]]
                r["rule"] = rule_of[jid]
                r["jobs"] += 1
                r["total_seconds"] += d
                r["longest_seconds"] = max(r["longest_seconds"], d)
        overview.append({
            "run_log": os.path.basename(lg),
            "jobs_started": len(starts),
            "jobs_finished": len(finished),
            "rules_with_errors": ", ".join(sorted(set(failed))) or "none",
            "wall_clock_seconds": int((last - first).total_seconds()) if first and last else "",
            "first_timestamp": first.isoformat(sep=" ") if first else "",
            "last_timestamp": last.isoformat(sep=" ") if last else "",
        })
    rows = sorted(per_rule.values(), key=lambda r: -r["total_seconds"])
    write_tsv(os.path.join(OUT, "job_timings.tsv"), rows, ["rule", "jobs", "total_seconds", "longest_seconds"])
    overview.append({
        "run_log": "all invocations",
        "jobs_started": sum(o["jobs_started"] for o in overview),
        "jobs_finished": sum(o["jobs_finished"] for o in overview),
        "rules_with_errors": overview[-1]["rules_with_errors"] if overview else "",
        "wall_clock_seconds": sum(o["wall_clock_seconds"] for o in overview if o["wall_clock_seconds"] != ""),
        "first_timestamp": overview[0]["first_timestamp"] if overview else "",
        "last_timestamp": overview[-1]["last_timestamp"] if overview else "",
    })
    write_tsv(os.path.join(OUT, "run_overview.tsv"), overview,
              ["run_log", "jobs_started", "jobs_finished", "rules_with_errors",
               "wall_clock_seconds", "first_timestamp", "last_timestamp"])


def main():
    if not os.path.isdir(RES):
        sys.exit(f"results directory not found: {RES}")
    os.makedirs(OUT, exist_ok=True)
    # Only logs that executed jobs: the dry run and the environment build
    # contain no job timestamps and are skipped by parse_run_log anyway.
    run_logs = sorted(glob.glob(os.path.join(RES, "logs", "snakemake_*.log")))
    if not run_logs:
        log("no snakemake_*.log under results/logs; timing and cutadapt tables will be incomplete")
    read_processing(run_logs)
    orf_predictions()
    if run_logs:
        job_timings(run_logs)
    log("done")


if __name__ == "__main__":
    main()
