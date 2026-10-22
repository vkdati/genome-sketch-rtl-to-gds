#!/usr/bin/env python3
"""
Phase A (1): Automated Dataset Downloader & Synthetic Corner-Case Generator
Project: Streaming Genome Sketching ASIC (ntHash-32 + Banked HLL on SCL 180nm)

Generates & fetches the Three-Tier Verification and Benchmark Dataset Suite:
  - Tier 1 (data/synthetic/): Deterministic synthetic FASTA files testing hardware
    corner cases (reverse-complement strand invariance, 'N' gap resets, homopolymers,
    and controlled mutation rates: 0%, 1%, 5%, 10%).
  - Tier 2 (data/viral/): Complete NCBI RefSeq viral genomes (~185 KB total) for
    fast cycle-accurate RTL simulation (< 1 second per genome in Verilog).
  - Tier 3 (data/bacterial/): Complete NCBI RefSeq bacterial genomes (~18 MB total)
    for publication-grade species & strain classification vs. Mash.

Usage:
  python download_datasets.py                 # Downloads all tiers (Synthetic + Viral + Bacterial)
  python download_datasets.py --skip-bacterial # Fast mode: only Synthetic + Viral (~200 KB)
"""

import argparse
import hashlib
import json
import os
import random
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Dict, List, Tuple

# Base directory: D:\BTP\genome_sketch_asic\data
DATA_DIR = Path(__file__).resolve().parent
SYNTHETIC_DIR = DATA_DIR / "synthetic"
VIRAL_DIR = DATA_DIR / "viral"
BACTERIAL_DIR = DATA_DIR / "bacterial"
MANIFEST_PATH = DATA_DIR / "dataset_manifest.json"

NCBI_EFETCH_URL = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/efetch.fcgi"

# Tier 2: Viral Genomes (~185 KB total)
VIRAL_PANEL = [
    {
        "name": "SARS_CoV_2_Wuhan_Ref",
        "accession": "NC_045512.2",
        "filename": "SARS_CoV_2_Wuhan_NC_045512.2.fasta",
        "description": "Severe acute respiratory syndrome coronavirus 2 reference genome (Wuhan-Hu-1)",
    },
    {
        "name": "SARS_CoV_2_Omicron_BA1",
        "accession": "OL672836.1",
        "filename": "SARS_CoV_2_Omicron_BA1_OL672836.1.fasta",
        "description": "SARS-CoV-2 Omicron (B.1.1.529 / BA.1) variant for close-strain resolution testing",
    },
    {
        "name": "SARS_CoV_1_Tor2",
        "accession": "NC_004718.3",
        "filename": "SARS_CoV_1_Tor2_NC_004718.3.fasta",
        "description": "SARS coronavirus Tor2 complete genome (~80% nucleotide identity to SARS-CoV-2)",
    },
    {
        "name": "MERS_CoV",
        "accession": "NC_019843.3",
        "filename": "MERS_CoV_NC_019843.3.fasta",
        "description": "Middle East respiratory syndrome-related coronavirus (distant Betacoronavirus)",
    },
    {
        "name": "Zaire_Ebolavirus",
        "accession": "NC_002549.1",
        "filename": "Zaire_Ebolavirus_NC_002549.1.fasta",
        "description": "Zaire ebolavirus complete genome (unrelated negative-sense RNA virus control)",
    },
    {
        "name": "Enterobacteria_phage_lambda",
        "accession": "NC_001416.1",
        "filename": "Bacteriophage_lambda_NC_001416.1.fasta",
        "description": "Escherichia virus Lambda complete genome (standard genomics benchmark control)",
    },
]

# Tier 3: Bacterial Complete Genomes (~18 MB total)
BACTERIAL_PANEL = [
    {
        "name": "E_coli_K12_MG1655",
        "accession": "NC_000913.3",
        "filename": "E_coli_K12_MG1655_NC_000913.3.fasta",
        "description": "Escherichia coli str. K-12 substr. MG1655 (commensal reference strain, ~4.64 Mbp)",
    },
    {
        "name": "E_coli_O157_H7_Sakai",
        "accession": "NC_002695.2",
        "filename": "E_coli_O157_H7_Sakai_NC_002695.2.fasta",
        "description": "Escherichia coli O157:H7 str. Sakai (pathogenic strain, ~5.50 Mbp, tests intraspecies strain separation)",
    },
    {
        "name": "Salmonella_enterica_CT18",
        "accession": "NC_003198.1",
        "filename": "Salmonella_enterica_CT18_NC_003198.1.fasta",
        "description": "Salmonella enterica subsp. enterica serovar Typhi str. CT18 (related Enterobacteriaceae genus, ~4.81 Mbp)",
    },
    {
        "name": "Staphylococcus_aureus_NCTC8325",
        "accession": "NC_007795.1",
        "filename": "Staphylococcus_aureus_NCTC8325_NC_007795.1.fasta",
        "description": "Staphylococcus aureus subsp. aureus NCTC 8325 (Gram-positive pathogen control, ~2.82 Mbp)",
    },
]


def reverse_complement(seq: str) -> str:
    """Computes the exact Watson-Crick reverse complement of a DNA string."""
    comp_table = str.maketrans("ACGTacgtNn", "TGCAtgcaNn")
    return seq.translate(comp_table)[::-1]


def write_fasta(filepath: Path, header: str, sequence: str, line_width: int = 80) -> None:
    """Writes a sequence in standard wrapped FASTA format."""
    filepath.parent.mkdir(parents=True, exist_ok=True)
    with open(filepath, "w", encoding="utf-8", newline="\n") as f:
        f.write(f">{header}\n")
        for i in range(0, len(sequence), line_width):
            f.write(sequence[i : i + line_width] + "\n")


def parse_fasta_stats(filepath: Path) -> Dict[str, object]:
    """Parses a FASTA file and computes base composition, length, and SHA-256."""
    sha256 = hashlib.sha256()
    total_len = 0
    acgt_counts = {"A": 0, "C": 0, "G": 0, "T": 0}
    ambiguous_count = 0
    headers = []

    with open(filepath, "rb") as fb:
        while chunk := fb.read(65536):
            sha256.update(chunk)

    with open(filepath, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            if line.startswith(">"):
                headers.append(line[1:])
            else:
                seq_upper = line.upper()
                total_len += len(seq_upper)
                for ch in seq_upper:
                    if ch in acgt_counts:
                        acgt_counts[ch] += 1
                    else:
                        ambiguous_count += 1

    valid_bases = sum(acgt_counts.values())
    gc_percent = (
        round(100.0 * (acgt_counts["G"] + acgt_counts["C"]) / valid_bases, 2)
        if valid_bases > 0
        else 0.0
    )

    return {
        "file": str(filepath.relative_to(DATA_DIR)),
        "size_bytes": filepath.stat().st_size,
        "sha256": sha256.hexdigest(),
        "num_records": len(headers),
        "primary_header": headers[0] if headers else "",
        "total_bp": total_len,
        "valid_acgt_bp": valid_bases,
        "ambiguous_bp": ambiguous_count,
        "gc_percent": gc_percent,
    }


def generate_tier1_synthetic() -> List[Dict[str, object]]:
    """Generates Tier 1 deterministic synthetic corner-case FASTA files."""
    print("\n" + "=" * 72)
    print("[Tier 1] Generating Deterministic Synthetic Corner-Case Datasets...")
    print("=" * 72)
    SYNTHETIC_DIR.mkdir(parents=True, exist_ok=True)
    manifest_entries = []

    # 1. Random 10,000 bp forward sequence (Fixed seed = 20261022)
    rng = random.Random(20261022)
    bases = ["A", "C", "G", "T"]
    seq_10k_fwd = "".join(rng.choices(bases, k=10000))
    f_fwd = SYNTHETIC_DIR / "synth_10k_forward.fasta"
    write_fasta(
        f_fwd,
        "SYNTH_10K_FWD Deterministic 10,000 bp sequence (seed=20261022)",
        seq_10k_fwd,
    )

    # 2. Exact Reverse-Complement of the 10,000 bp sequence
    # Hardware requirement: Canonical ntHash + HLL sketch of this file MUST be
    # 100% bit-for-bit identical to synth_10k_forward.fasta!
    seq_10k_rc = reverse_complement(seq_10k_fwd)
    f_rc = SYNTHETIC_DIR / "synth_10k_revcomp.fasta"
    write_fasta(
        f_rc,
        "SYNTH_10K_REVCOMP Exact Watson-Crick Reverse Complement of SYNTH_10K_FWD",
        seq_10k_rc,
    )

    # 3. Homopolymer & Periodic Repeat Corner Case (1,024 bp)
    # Tests shift register saturation, leading-zero edge cases, and low-cardinality HLL buckets
    seq_homo = (
        ("A" * 64)
        + ("C" * 64)
        + ("G" * 64)
        + ("T" * 64)
        + ("ACGT" * 64)
        + ("AACCGGTT" * 64)
    )
    f_homo = SYNTHETIC_DIR / "synth_homopolymer_repeats.fasta"
    write_fasta(
        f_homo,
        "SYNTH_HOMOPOLYMER Homopolymers (64x A/C/G/T) and periodic repeats",
        seq_homo,
    )

    # 4. Ambiguous 'N' Base Gap Recovery Test (2,000 bp)
    # Hardware requirement: Warm-up counter must reset to 0 on every 'N' and wait 21 valid bases
    rng_gap = random.Random(180)
    seg1 = "".join(rng_gap.choices(bases, k=500))
    seg2 = "".join(rng_gap.choices(bases, k=20))  # < 21 bp! Must emit ZERO k-mers!
    seg3 = "".join(rng_gap.choices(bases, k=500))
    seq_gaps = seg1 + ("N" * 15) + seg2 + ("N" * 5) + seg3
    f_gaps = SYNTHETIC_DIR / "synth_ambiguous_N_gaps.fasta"
    write_fasta(
        f_gaps,
        "SYNTH_N_GAPS 500bp_valid + 15N + 20bp_short_island(<k) + 5N + 500bp_valid",
        seq_gaps,
    )

    # 5. Controlled Mutation Series (0%, 1%, 5%, 10% point mutations on 10k base sequence)
    # Proves monotonic Jaccard similarity decay & Mash evolutionary distance accuracy
    mutation_rates = [0.01, 0.05, 0.10]
    mut_files = []
    for rate in mutation_rates:
        rng_mut = random.Random(int(rate * 10000))
        seq_list = list(seq_10k_fwd)
        num_mutations = int(len(seq_list) * rate)
        positions = rng_mut.sample(range(len(seq_list)), num_mutations)
        for pos in positions:
            orig = seq_list[pos]
            alternatives = [b for b in bases if b != orig]
            seq_list[pos] = rng_mut.choice(alternatives)
        pct_str = f"{int(rate * 100):02d}pct"
        f_mut = SYNTHETIC_DIR / f"synth_10k_mut_{pct_str}.fasta"
        write_fasta(
            f_mut,
            f"SYNTH_10K_MUT_{pct_str} {rate*100:.1f}% SNV mutated from SYNTH_10K_FWD",
            "".join(seq_list),
        )
        mut_files.append(f_mut)

    for fp in [f_fwd, f_rc, f_homo, f_gaps] + mut_files:
        stats = parse_fasta_stats(fp)
        stats["tier"] = "tier1_synthetic"
        manifest_entries.append(stats)
        print(
            f"  [OK] {fp.name:<34} | {stats['total_bp']:>8,} bp | GC: {stats['gc_percent']:>5.1f}%"
        )

    return manifest_entries


def fetch_ncbi_fasta(accession: str, dest_path: Path, retries: int = 3) -> bool:
    """Downloads a nucleotide FASTA record from NCBI Entrez E-utilities."""
    if dest_path.exists() and dest_path.stat().st_size > 100:
        return True

    params = urllib.parse.urlencode(
        {
            "db": "nuccore",
            "id": accession,
            "rettype": "fasta",
            "retmode": "text",
            "tool": "iitj_btp_genome_sketch_asic",
            "email": "b23ee1030@iitj.ac.in",
        }
    )
    url = f"{NCBI_EFETCH_URL}?{params}"

    for attempt in range(1, retries + 1):
        try:
            req = urllib.request.Request(
                url,
                headers={
                    "User-Agent": "IITJ-BTP-GenomeSketchASIC/1.0 (mailto:b23ee1030@iitj.ac.in)"
                },
            )
            with urllib.request.urlopen(req, timeout=60) as resp:
                content = resp.read().decode("utf-8", errors="replace").strip()
                if not content.startswith(">"):
                    raise ValueError(f"Unexpected response format for {accession}")
                dest_path.parent.mkdir(parents=True, exist_ok=True)
                with open(dest_path, "w", encoding="utf-8", newline="\n") as f:
                    f.write(content + "\n")
            # Respect NCBI E-utilities rate limit (max 3 requests/sec without API key)
            time.sleep(0.45)
            return True
        except Exception as exc:
            print(f"    [WARN] Attempt {attempt}/{retries} failed for {accession}: {exc}")
            time.sleep(1.5 * attempt)

    return False


def download_panel(
    panel: List[Dict[str, str]], target_dir: Path, tier_label: str
) -> List[Dict[str, object]]:
    """Downloads a list of NCBI RefSeq records and returns manifest metadata."""
    target_dir.mkdir(parents=True, exist_ok=True)
    entries = []

    for item in panel:
        acc = item["accession"]
        dest = target_dir / item["filename"]
        cached = dest.exists() and dest.stat().st_size > 100
        status_tag = "CACHED" if cached else "FETCH "
        print(f"  [{status_tag}] {acc:<13} -> {item['filename']} ...", end="", flush=True)

        ok = fetch_ncbi_fasta(acc, dest)
        if not ok:
            print(" FAILED!")
            continue

        stats = parse_fasta_stats(dest)
        stats["tier"] = tier_label
        stats["name"] = item["name"]
        stats["accession"] = acc
        stats["description"] = item["description"]
        entries.append(stats)
        print(
            f" DONE ({stats['total_bp']:,} bp | {stats['size_bytes'] / 1024:.1f} KB | GC: {stats['gc_percent']:.1f}%)"
        )

    return entries


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Download & verify datasets for the Genome Sketching ASIC Golden Model."
    )
    parser.add_argument(
        "--skip-bacterial",
        action="store_true",
        help="Skip downloading the ~18 MB bacterial RefSeq genomes (only generate Synthetic + Viral).",
    )
    args = parser.parse_args()

    all_manifest: List[Dict[str, object]] = []

    # 1. Generate Tier 1 Synthetic corner cases
    all_manifest.extend(generate_tier1_synthetic())

    # 2. Download Tier 2 Viral complete genomes
    print("\n" + "=" * 72)
    print("[Tier 2] Fetching NCBI RefSeq Complete Viral Genomes (~185 KB)...")
    print("=" * 72)
    all_manifest.extend(download_panel(VIRAL_PANEL, VIRAL_DIR, "tier2_viral"))

    # 3. Download Tier 3 Bacterial complete genomes
    if not args.skip_bacterial:
        print("\n" + "=" * 72)
        print("[Tier 3] Fetching NCBI RefSeq Complete Bacterial Genomes (~18 MB)...")
        print("=" * 72)
        all_manifest.extend(
            download_panel(BACTERIAL_PANEL, BACTERIAL_DIR, "tier3_bacterial")
        )

    # Save manifest JSON
    with open(MANIFEST_PATH, "w", encoding="utf-8", newline="\n") as f:
        json.dump(
            {
                "project": "SCL 180nm Streaming Genome Sketching ASIC (ntHash-32 + Banked HLL)",
                "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                "total_files": len(all_manifest),
                "total_size_bytes": sum(int(x["size_bytes"]) for x in all_manifest),
                "datasets": all_manifest,
            },
            f,
            indent=2,
        )

    total_mb = sum(int(x["size_bytes"]) for x in all_manifest) / (1024 * 1024)
    print("\n" + "=" * 72)
    print(
        f"Dataset Suite Ready: {len(all_manifest)} files ({total_mb:.2f} MB total)"
    )
    print(f"Manifest written to: {MANIFEST_PATH}")
    print("=" * 72)
    return 0


if __name__ == "__main__":
    sys.exit(main())
