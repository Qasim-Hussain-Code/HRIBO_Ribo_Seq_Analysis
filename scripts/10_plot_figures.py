#!/usr/bin/env python3
"""Draw the summary figures of a collected HRIBO run.

Four PNG files are written to results/<name>/figures/:

    read_processing.png           reads per library at each processing stage
    read_length_distribution.png  footprint length distribution of the Ribo-seq library
    metagene_profile.png          5' end density around start and stop codons
    orf_predictions.png           length, start codon, annotation status and
                                  agreement of the ORF calls of both tools

Everything is read from the files scripts/06_collect_results.sh copied into
results/<name>/, so the figures can be redrawn from the repository alone.
Needs matplotlib, pandas and openpyxl; the readtools environment built by
scripts/01_install_hribo.sh has all three.

Usage:
    python scripts/10_plot_figures.py [results_name]     (default: pao1)
"""

import csv
import glob
import os
import re
import sys

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
NAME = sys.argv[1] if len(sys.argv) > 1 else "pao1"
RES = os.path.join(REPO_ROOT, "results", NAME)
OUT = os.path.join(RES, "figures")

# Colours: two categorical series, text and surface tokens. The pair was
# checked for colour-vision deficiency separation before use.
BLUE, ORANGE = "#2a78d6", "#eb6834"
INK, INK2, GRID, SURFACE, SHADE = "#0b0b0b", "#52514e", "#d9d8d3", "#fcfcfb", "#ecebe7"
METAGENE_LENGTHS = range(25, 35)     # the readLengths window of config.yaml

plt.rcParams.update({
    "figure.facecolor": SURFACE, "axes.facecolor": SURFACE, "savefig.facecolor": SURFACE,
    "axes.edgecolor": GRID, "axes.linewidth": 0.8, "axes.grid": True, "grid.color": GRID,
    "grid.linewidth": 0.8, "axes.axisbelow": True, "xtick.color": INK2, "ytick.color": INK2,
    "axes.labelcolor": INK2, "text.color": INK, "axes.titlecolor": INK, "axes.titleweight": "bold",
    "axes.titlesize": 11, "axes.labelsize": 9.5, "xtick.labelsize": 9, "ytick.labelsize": 9,
    "legend.frameon": False, "legend.fontsize": 9, "font.size": 9.5,
    "axes.spines.top": False, "axes.spines.right": False,
})


def log(msg):
    print(f"[figures] {msg}")


def tidy(ax, ygrid=True):
    ax.grid(axis="y" if ygrid else "x")
    ax.grid(False, axis="x" if ygrid else "y")
    ax.tick_params(length=0)


def thousands(v):
    return f"{int(round(v)):,}"


# ---------------------------------------------------------------------------
# 1. Reads per processing stage
# ---------------------------------------------------------------------------

def fig_read_processing():
    rows = list(csv.DictReader(open(os.path.join(RES, "summary", "read_processing.tsv")), delimiter="\t"))
    stages = [("reads_kept", "raw\n(10 percent subsample)"),
              ("cutadapt_reads_written", "after adapter\ntrimming"),
              ("reads_unique_mappers", "unique\nmappers"),
              ("reads_unique_after_rrna_removal", "after rRNA and\ntRNA removal")]
    colours = {"RIBO-GLY-1": BLUE, "RNA-GLY-1": ORANGE}
    fig, ax = plt.subplots(figsize=(8, 4.4))
    width, x = 0.36, np.arange(len(stages))
    for i, r in enumerate(rows):
        vals = [float(r[k]) for k, _ in stages]
        pos = x + (i - 0.5) * (width + 0.04)
        bars = ax.bar(pos, vals, width, color=colours.get(r["sample"], INK2), label=r["sample"], linewidth=0)
        for b, v in zip(bars, vals):
            ax.text(b.get_x() + b.get_width() / 2, v * 1.12, thousands(v), ha="center", va="bottom",
                    fontsize=8, color=INK2)
    ax.set_yscale("log")
    ax.set_ylim(1e5, 4e7)
    ax.set_xticks(x, [s for _, s in stages])
    ax.set_ylabel("reads (log scale)")
    ax.set_title("Reads surviving each processing stage")
    ax.legend(loc="upper right", ncol=2)
    tidy(ax)
    fig.tight_layout()
    fig.savefig(os.path.join(OUT, "read_processing.png"), dpi=150)
    plt.close(fig)
    log("read_processing.png")


# ---------------------------------------------------------------------------
# 2. Footprint length distribution
# ---------------------------------------------------------------------------

def fig_read_length_distribution():
    d = pd.read_excel(os.path.join(RES, "metageneprofiling", "read_length_fractions.xlsx"))
    sample = [c for c in d.columns if c != "read_lengths"][0]
    d = d[(d["read_lengths"] >= 12) & (d["read_lengths"] <= 50)]
    frac = d[sample] * 100
    fig, ax = plt.subplots(figsize=(8, 4.2))
    ax.axvspan(METAGENE_LENGTHS.start - 0.5, METAGENE_LENGTHS.stop - 0.5, color=SHADE, zorder=0, linewidth=0)
    ax.bar(d["read_lengths"], frac, width=0.72, color=BLUE, linewidth=0)
    mode = int(d.loc[frac.idxmax(), "read_lengths"])
    in_window = frac[d["read_lengths"].isin(METAGENE_LENGTHS)].sum()
    ax.annotate(f"mode {mode} nt, {frac.max():.1f} percent of reads",
                xy=(mode, frac.max()), xytext=(mode + 6, frac.max() * 0.95),
                color=INK2, fontsize=9, arrowprops={"arrowstyle": "-", "color": INK2, "lw": 0.8})
    ax.text(METAGENE_LENGTHS.start - 0.3, ax.get_ylim()[1] * 0.97 if ax.get_ylim()[1] > 0 else 1,
            f"metagene window\n25 to 34 nt\n({in_window:.0f} percent of reads)", va="top", ha="left",
            fontsize=8.5, color=INK2)
    with open(os.path.join(RES, "summary", "read_length_window.tsv"), "w", newline="") as fh:
        fh.write("sample\tmode_nt\tpercent_at_mode\tpercent_in_25_to_34\n")
        fh.write(f"{sample}\t{mode}\t{frac.max():.2f}\t{in_window:.2f}\n")
    ax.set_xlabel("read length after trimming (nt)")
    ax.set_ylabel("percent of unique, rRNA-free reads")
    ax.set_title(f"Read length distribution of the Ribo-seq library ({sample})")
    ax.set_xlim(11, 51)
    tidy(ax)
    fig.tight_layout()
    fig.savefig(os.path.join(OUT, "read_length_distribution.png"), dpi=150)
    plt.close(fig)
    log("read_length_distribution.png")


# ---------------------------------------------------------------------------
# 3. Metagene profile around start and stop codons
# ---------------------------------------------------------------------------

def included_genes():
    """Number of genes HRIBO kept for the metagene profile, from the run logs."""
    n = None
    for lg in sorted(glob.glob(os.path.join(RES, "logs", "snakemake_*.log"))):
        for line in open(lg, errors="replace"):
            m = re.match(r"Included genes: (\d+)", line)
            if m:
                n = int(m.group(1))
    return n


def fig_metagene():
    base = os.path.join(RES, "metageneprofiling", "RIBO-GLY-1", "cpm")
    fig, axes = plt.subplots(1, 2, figsize=(10, 4), sharey=True)
    panels = ((axes[0], "fiveprime", "start", "5' end position relative to the start codon (nt)", "5' ends around the start codon"),
              (axes[1], "threeprime", "stop", "3' end position relative to the stop codon (nt)", "3' ends around the stop codon"))
    for ax, end, which, xlabel, title in panels:
        d = pd.read_excel(os.path.join(base, f"{end}_readcounts_{which}.xlsx"))
        cols = [c for c in d.columns if str(c).isdigit() and int(c) in METAGENE_LENGTHS]
        y = d[cols].sum(axis=1)
        x = d["coordinates"]
        ax.axvline(0, color=INK2, linewidth=0.8, zorder=1)
        ax.plot(x, y, color=BLUE, linewidth=1.6, zorder=2)
        ax.set_xlabel(xlabel)
        ax.set_title(title)
        tidy(ax)
    axes[0].set_ylabel("reads per million, 25 to 34 nt footprints")
    n = included_genes()
    genes = f", {n:,} filtered genes" if n else ""
    fig.suptitle(f"Metagene profile of the Ribo-seq library{genes}", fontweight="bold")
    fig.tight_layout()
    fig.savefig(os.path.join(OUT, "metagene_profile.png"), dpi=150)
    plt.close(fig)
    log("metagene_profile.png")


# ---------------------------------------------------------------------------
# 4. ORF predictions
# ---------------------------------------------------------------------------

def read_gff(path):
    rows = []
    with open(path) as fh:
        for line in fh:
            if line.startswith("#") or not line.strip():
                continue
            f = line.rstrip("\n").split("\t")
            rows.append({"chrom": f[0], "start": int(f[3]), "end": int(f[4]), "strand": f[6], "attr": f[8]})
    return pd.DataFrame(rows)


def stop_key(df):
    """(chromosome, stop coordinate, strand): the stop codon identifies an ORF
    family regardless of which start codon a tool chose."""
    stop = np.where(df["strand"] == "+", df["end"], df["start"])
    return list(zip(df["chrom"], stop, df["strand"]))


def fig_orf_predictions():
    # Annotated coding sequences, from the annotation HRIBO counted against.
    ann_gff = os.path.join(RES, "readcounts", "unique_annotation.gtf")
    cds = []
    with open(ann_gff) as fh:
        for line in fh:
            f = line.rstrip("\n").split("\t")
            if len(f) > 8 and f[2] == "CDS":
                cds.append({"chrom": f[0], "start": int(f[3]), "end": int(f[4]), "strand": f[6]})
    cds = pd.DataFrame(cds)
    annotated_stops = set(stop_key(cds))

    # The raw tables of both tools give coordinates without the stop codon
    # (Reparation ends three bases early, DeepRibo's stop_site is the first
    # base of the stop codon) while HRIBO's GFF tracks include it. The start
    # codon position, which is the same in both, identifies each ORF.
    def start_position(df):
        return list(zip(np.where(df["strand"] == "+", df["start"], df["end"]), df["strand"]))

    # Reparation: coordinates from the filtered track, start codons from the raw table.
    rep = read_gff(os.path.join(RES, "tracks", "reparation_annotated.gff"))
    rep_raw = pd.read_csv(os.path.join(RES, "reparation", "GLY-1", "Predicted_ORFs.txt"), sep="\t")
    rep_codon = {}
    for _, r in rep_raw.iterrows():
        m = re.match(r"(\S+):(\d+)-(\d+)", r["ORF_locus"])
        pos = int(m.group(2)) if r["strand"] == "+" else int(m.group(3))
        rep_codon[(pos, r["strand"])] = r["start_codon"]
    rep["codon"] = [rep_codon.get(k, "other") for k in start_position(rep)]

    # DeepRibo: coordinates from the filtered track, start codons from the scored candidates.
    dr = read_gff(os.path.join(RES, "tracks", "deepribo_merged.gff"))
    dr_raw = pd.read_csv(os.path.join(RES, "deepribo", "GLY-1", "predictions.csv"), index_col=0)
    dr_codon = {(int(r["start_site"]), r["strand"]): r["start_codon"] for _, r in dr_raw.iterrows()}
    dr["codon"] = [dr_codon.get(k, "other") for k in start_position(dr)]
    for name, df in (("Reparation", rep), ("DeepRibo", dr)):
        unmatched = int((df["codon"] == "other").sum())
        if unmatched:
            log(f"{name}: {unmatched} ORFs without a start codon in the raw table")

    for df in (rep, dr):
        df["length"] = df["end"] - df["start"] + 1
        df["annotated_stop"] = [k in annotated_stops for k in stop_key(df)]

    rep_stops, dr_stops = set(stop_key(rep)), set(stop_key(dr))
    rep_exact = set(zip(rep["chrom"], rep["start"], rep["end"], rep["strand"]))
    dr_exact = set(zip(dr["chrom"], dr["start"], dr["end"], dr["strand"]))

    def agreement(df, own_exact, other_exact, other_stops):
        keys_exact = list(zip(df["chrom"], df["start"], df["end"], df["strand"]))
        keys_stop = stop_key(df)
        identical = sum(1 for k in keys_exact if k in other_exact)
        same_stop = sum(1 for ke, ks in zip(keys_exact, keys_stop) if ke not in other_exact and ks in other_stops)
        only = len(df) - identical - same_stop
        return identical, same_stop, only

    callers = [("Reparation", rep, BLUE), ("DeepRibo", dr, ORANGE)]
    fig, axes = plt.subplots(2, 2, figsize=(10, 7.2))

    # (a) length distribution
    ax = axes[0, 0]
    bins = np.logspace(np.log10(30), np.log10(15000), 40)
    for name, df, colour in callers:
        ax.hist(df["length"], bins=bins, histtype="step", linewidth=1.8, color=colour, label=f"{name} ({len(df):,})")
    ax.set_xscale("log")
    ax.set_xlabel("ORF length (nt, log scale)")
    ax.set_ylabel("ORFs")
    ax.set_title("Length of the predicted ORFs")
    ax.legend(loc="upper right")
    tidy(ax)

    # (b) start codon usage
    ax = axes[0, 1]
    codons = ["ATG", "GTG", "TTG"]
    x, w = np.arange(len(codons)), 0.36
    for i, (name, df, colour) in enumerate(callers):
        share = [100 * (df["codon"] == c).mean() for c in codons]
        bars = ax.bar(x + (i - 0.5) * (w + 0.04), share, w, color=colour, linewidth=0)
        for b, v in zip(bars, share):
            ax.text(b.get_x() + b.get_width() / 2, v + 1, f"{v:.0f}", ha="center", va="bottom", fontsize=8, color=INK2)
    ax.set_xticks(x, codons)
    ax.set_ylabel("percent of predicted ORFs")
    ax.set_title("Start codon of the predicted ORFs")
    ax.set_ylim(0, 100)
    tidy(ax)

    # (c) annotation status
    ax = axes[1, 0]
    cats = ["stop codon shared with\nan annotated CDS", "no annotated CDS\nends at the same stop"]
    for i, (name, df, colour) in enumerate(callers):
        n_ann = int(df["annotated_stop"].sum())
        vals = [n_ann, len(df) - n_ann]
        bars = ax.bar(x[:2] + (i - 0.5) * (w + 0.04), vals, w, color=colour, linewidth=0)
        for b, v in zip(bars, vals):
            ax.text(b.get_x() + b.get_width() / 2, v + 25, f"{v:,}", ha="center", va="bottom", fontsize=8, color=INK2)
    ax.set_xticks(x[:2], cats)
    ax.set_ylabel("ORFs")
    ax.set_title("Predicted ORFs against the RefSeq annotation")
    tidy(ax)

    # (d) agreement between the two callers
    ax = axes[1, 1]
    cats = ["identical ORF\nin both", "same stop,\ndifferent start", "only this\ncaller"]
    for i, (name, df, colour) in enumerate(callers):
        other_exact, other_stops = (dr_exact, dr_stops) if name == "Reparation" else (rep_exact, rep_stops)
        own_exact = rep_exact if name == "Reparation" else dr_exact
        vals = agreement(df, own_exact, other_exact, other_stops)
        bars = ax.bar(np.arange(3) + (i - 0.5) * (w + 0.04), vals, w, color=colour, linewidth=0)
        for b, v in zip(bars, vals):
            ax.text(b.get_x() + b.get_width() / 2, v + 25, f"{v:,}", ha="center", va="bottom", fontsize=8, color=INK2)
    ax.set_xticks(np.arange(3), cats)
    ax.set_ylabel("ORFs")
    ax.set_title("Agreement between the two callers")
    tidy(ax)

    fig.suptitle("ORF predictions on the subsampled PAO1 Ribo-seq library", fontweight="bold")
    fig.tight_layout()
    fig.savefig(os.path.join(OUT, "orf_predictions.png"), dpi=150)
    plt.close(fig)
    log("orf_predictions.png")

    # The numbers behind panels (c) and (d), for the text.
    with open(os.path.join(RES, "summary", "orf_agreement.tsv"), "w", newline="") as fh:
        w_ = csv.writer(fh, delimiter="\t", lineterminator="\n")
        w_.writerow(["caller", "orfs", "stop_shared_with_annotated_cds", "novel_stop", "identical_in_other_caller",
                     "same_stop_different_start", "only_this_caller", "ATG", "GTG", "TTG"])
        for name, df, _ in callers:
            other_exact, other_stops = (dr_exact, dr_stops) if name == "Reparation" else (rep_exact, rep_stops)
            own_exact = rep_exact if name == "Reparation" else dr_exact
            ident, same, only = agreement(df, own_exact, other_exact, other_stops)
            n_ann = int(df["annotated_stop"].sum())
            w_.writerow([name, len(df), n_ann, len(df) - n_ann, ident, same, only]
                        + [int((df["codon"] == c).sum()) for c in codons])
    log("summary/orf_agreement.tsv")


def main():
    if not os.path.isdir(RES):
        sys.exit(f"results directory not found: {RES}")
    os.makedirs(OUT, exist_ok=True)
    fig_read_processing()
    fig_read_length_distribution()
    fig_metagene()
    fig_orf_predictions()
    log("done")


if __name__ == "__main__":
    main()
