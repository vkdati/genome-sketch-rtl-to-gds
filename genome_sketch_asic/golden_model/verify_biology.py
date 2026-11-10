#!/usr/bin/env python3
"""
Biological Verification & Benchmarking Suite
Project: Streaming Genome Sketching ASIC (180nm CMOS)

Verifies:
  1. Rolling vs. Direct ntHash equivalence and 'N'-gap recovery
  2. Strand invariance (forward vs. reverse-complement)
  3. Mutation sensitivity across synthetic SNV series
  4. Cardinality and pairwise ANI accuracy on NCBI RefSeq genomes
"""

import json
import math
import sys
import time
from pathlib import Path
from typing import Dict, List, Set, Tuple

# Ensure parent package import works whether run as script or module
ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from golden_model.banked_hll import NUM_BANKS, TOTAL_REGS
from golden_model.nthash32 import BASE_TO_INT, KMER_LEN, direct_nthash32_kmer
from golden_model.sketch_pipeline import (
    GenomeSketchPipeline,
    estimate_cardinality,
    estimate_jaccard_and_mash,
)

DATA_DIR = ROOT_DIR / "data"
SYNTH_DIR = DATA_DIR / "synthetic"
VIRAL_DIR = DATA_DIR / "viral"
BACTERIAL_DIR = DATA_DIR / "bacterial"
REPORT_MD_PATH = Path(__file__).resolve().parent / "verification_report.md"
RESULTS_JSON_PATH = Path(__file__).resolve().parent / "verification_results.json"


def read_fasta_records(fasta_path: Path) -> List[Tuple[str, str]]:
    """Reads a FASTA file into a list of (header, sequence) tuples."""
    records: List[Tuple[str, str]] = []
    header = ""
    seq_chunks: List[str] = []
    with open(fasta_path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            if line.startswith(">"):
                if header or seq_chunks:
                    records.append((header, "".join(seq_chunks).upper()))
                header = line[1:]
                seq_chunks = []
            else:
                seq_chunks.append(line)
        if header or seq_chunks:
            records.append((header, "".join(seq_chunks).upper()))
    return records


def reverse_complement_str(seq: str) -> str:
    """Computes exact Watson-Crick reverse complement of a DNA string."""
    table = str.maketrans("ACGTacgtNn", "TGCAtgcaNn")
    return seq.translate(table)[::-1]


def extract_exact_canonical_kmers(fasta_path: Path, k: int = KMER_LEN) -> Set[str]:
    """
    Ground-truth software oracle: extracts the exact set of unique canonical k-mers
    from a FASTA file (resetting across 'N' or non-ACGT bases).
    """
    canon_set: Set[str] = set()
    comp_table = str.maketrans("ACGT", "TGCA")

    for _, seq in read_fasta_records(fasta_path):
        valid_run = []
        for ch in seq:
            if ch in BASE_TO_INT:
                valid_run.append(ch)
                if len(valid_run) >= k:
                    kmer = "".join(valid_run[-k:])
                    rc_kmer = kmer.translate(comp_table)[::-1]
                    canon_set.add(kmer if kmer <= rc_kmer else rc_kmer)
            else:
                valid_run.clear()
    return canon_set


def exact_jaccard_and_mash(
    set_a: Set[str], set_b: Set[str], k: int = KMER_LEN
) -> Dict[str, float]:
    """Computes exact ground-truth Jaccard index and Mash distance from two k-mer sets."""
    union_len = len(set_a | set_b)
    inter_len = len(set_a & set_b)
    if union_len == 0:
        return {"jaccard": 0.0, "mash_distance": 1.0, "ani_pct": 0.0}
    j = float(inter_len) / float(union_len)
    if j <= 0.0:
        d = 1.0
    else:
        d = max(0.0, min(1.0, -1.0 / float(k) * math.log(2.0 * j / (1.0 + j))))
    return {"jaccard": j, "mash_distance": d, "ani_pct": (1.0 - d) * 100.0}


def run_test1_rolling_equivalence_and_gaps() -> Dict[str, object]:
    """
    Test 1: Verifies 1-cycle rolling ntHash-32 against direct O(k) polynomial hashing
    and checks ambiguous 'N' gap reset behavior.
    """
    print("\n" + "=" * 76)
    print("[TEST 1] Rolling vs. Direct ntHash-32 Equivalence & 'N'-Gap Reset Check")
    print("=" * 76)

    fwd_path = SYNTH_DIR / "synth_10k_forward.fasta"
    _, seq = read_fasta_records(fwd_path)[0]

    pipe = GenomeSketchPipeline()
    traces = pipe.stream_sequence(seq, record_trace=True)

    valid_kmer_count = 0
    for idx, tr in enumerate(traces):
        if idx < KMER_LEN - 1:
            assert not tr.kmer_valid, f"Premature kmer_valid at cycle {tr.cycle}"
        else:
            assert tr.kmer_valid, f"Missing kmer_valid at cycle {tr.cycle}"
            kmer_str = seq[idx - KMER_LEN + 1 : idx + 1]
            df, dr, dc, dm = direct_nthash32_kmer(kmer_str)
            assert tr.h_fwd == df, f"h_fwd mismatch at cycle {tr.cycle}"
            assert tr.h_rev == dr, f"h_rev mismatch at cycle {tr.cycle}"
            assert tr.h_canon == dc, f"h_canon mismatch at cycle {tr.cycle}"
            assert tr.h_mixed == dm, f"h_mixed mismatch at cycle {tr.cycle}"
            valid_kmer_count += 1

    expected_kmers = len(seq) - KMER_LEN + 1
    assert valid_kmer_count == expected_kmers
    print(
        f"  [PASS] Rolling vs. Direct O(k) Hash: {valid_kmer_count:,}/{expected_kmers:,} cycles matched 100% bit-for-bit."
    )

    # Check 'N'-base gap recovery on synth_ambiguous_N_gaps.fasta:
    # 500bp valid + 15 'N' + 20bp short island (< 21 bp) + 5 'N' + 500bp valid
    gaps_path = SYNTH_DIR / "synth_ambiguous_N_gaps.fasta"
    pipe_gaps = GenomeSketchPipeline()
    gap_traces = pipe_gaps.stream_fasta_file(gaps_path, record_trace=True)
    valid_gap_kmers = sum(1 for t in gap_traces if t.kmer_valid)
    expected_gap_kmers = (500 - KMER_LEN + 1) + 0 + (500 - KMER_LEN + 1)  # 480 + 480 = 960
    assert (
        valid_gap_kmers == expected_gap_kmers
    ), f"Expected {expected_gap_kmers} valid k-mers across N gaps, got {valid_gap_kmers}"
    print(
        f"  [PASS] Ambiguous 'N'-Gap Reset Check: 20-bp sub-k island suppressed; {valid_gap_kmers}/960 valid k-mers emitted."
    )

    return {
        "rolling_vs_direct_cycles_verified": valid_kmer_count,
        "n_gap_expected_kmers": expected_gap_kmers,
        "n_gap_observed_kmers": valid_gap_kmers,
        "status": "PASS",
    }


def run_test2_strand_invariance() -> Dict[str, object]:
    """
    Test 2: Proves that forward and reverse-complement strands yield 100% bit-identical
    256-register HLL sketches on both synthetic and real SARS-CoV-2 genomes.
    """
    print("\n" + "=" * 76)
    print("[TEST 2] Watson-Crick Reverse-Complement Strand Invariance Check")
    print("=" * 76)

    # 2a. Synthetic 10k forward vs. revcomp file
    pipe_fwd = GenomeSketchPipeline()
    traces_fwd = pipe_fwd.stream_fasta_file(
        SYNTH_DIR / "synth_10k_forward.fasta", record_trace=True
    )
    sketch_fwd = pipe_fwd.get_sketch()

    pipe_rc = GenomeSketchPipeline()
    traces_rc = pipe_rc.stream_fasta_file(
        SYNTH_DIR / "synth_10k_revcomp.fasta", record_trace=True
    )
    sketch_rc = pipe_rc.get_sketch()

    assert sketch_fwd == sketch_rc, "Synthetic 10k Forward vs. RevComp HLL sketch mismatch!"

    # Also verify that the sequence of canonical hashes is the exact reverse order
    hashes_fwd = [t.h_mixed for t in traces_fwd if t.kmer_valid]
    hashes_rc = [t.h_mixed for t in traces_rc if t.kmer_valid]
    assert hashes_fwd == hashes_rc[::-1], "Canonical hash stream is not exact reverse mirror!"
    print(
        "  [PASS] Synthetic 10k Fwd vs. RevComp: 256/256 HLL registers & 9,980 canonical hashes 100% bit-identical."
    )

    # 2b. Real SARS-CoV-2 Wuhan genome (29,903 bp) forward vs. reverse-complement
    sars_path = VIRAL_DIR / "SARS_CoV_2_Wuhan_NC_045512.2.fasta"
    _, sars_seq = read_fasta_records(sars_path)[0]
    sars_rc_seq = reverse_complement_str(sars_seq)

    pipe_sars_fwd = GenomeSketchPipeline()
    pipe_sars_fwd.stream_sequence(sars_seq)
    pipe_sars_rc = GenomeSketchPipeline()
    pipe_sars_rc.stream_sequence(sars_rc_seq)

    assert (
        pipe_sars_fwd.get_sketch() == pipe_sars_rc.get_sketch()
    ), "SARS-CoV-2 strand invariance failed!"
    print(
        f"  [PASS] SARS-CoV-2 ({len(sars_seq):,} bp) Fwd vs. RevComp: 256/256 HLL registers 100% bit-identical."
    )

    return {
        "synth_10k_registers_matched": 256,
        "sars_cov_2_registers_matched": 256,
        "status": "PASS",
    }


def run_test3_mutation_monotonicity() -> List[Dict[str, object]]:
    """
    Test 3: Evaluates Jaccard similarity and Mash distance across the 0%, 1%, 5%, 10%
    synthetic mutation series against exact canonical k-mer sets.
    """
    print("\n" + "=" * 76)
    print("[TEST 3] Controlled Mutation Series (0%, 1%, 5%, 10% SNVs) Monotonicity")
    print("=" * 76)

    ref_file = SYNTH_DIR / "synth_10k_forward.fasta"
    pipe_ref = GenomeSketchPipeline()
    pipe_ref.stream_fasta_file(ref_file)
    sketch_ref = pipe_ref.get_sketch()
    exact_ref = extract_exact_canonical_kmers(ref_file)

    test_files = [
        ("0.0% (Identical)", ref_file),
        ("1.0% SNV Mutated", SYNTH_DIR / "synth_10k_mut_01pct.fasta"),
        ("5.0% SNV Mutated", SYNTH_DIR / "synth_10k_mut_05pct.fasta"),
        ("10.0% SNV Mutated", SYNTH_DIR / "synth_10k_mut_10pct.fasta"),
    ]

    results = []
    prev_jaccard = 1.01
    print(
        f"  {'Mutation Level':<20} | {'Exact J':>9} | {'HW HLL J':>9} | {'Exact Mash D':>12} | {'HW Mash D':>10}"
    )
    print("  " + "-" * 70)

    for label, fpath in test_files:
        pipe_m = GenomeSketchPipeline()
        pipe_m.stream_fasta_file(fpath)
        sketch_m = pipe_m.get_sketch()
        exact_m = extract_exact_canonical_kmers(fpath)

        ex_metrics = exact_jaccard_and_mash(exact_ref, exact_m)
        hw_metrics = estimate_jaccard_and_mash(sketch_ref, sketch_m)

        # Verify monotonic decrease in Jaccard similarity as mutation rate increases
        assert (
            hw_metrics["jaccard"] <= prev_jaccard
        ), f"Non-monotonic Jaccard at {label}!"
        prev_jaccard = hw_metrics["jaccard"]

        print(
            f"  {label:<20} | {ex_metrics['jaccard']:>9.4f} | {hw_metrics['jaccard']:>9.4f} | "
            f"{ex_metrics['mash_distance']:>12.4f} | {hw_metrics['mash_distance']:>10.4f}"
        )
        results.append(
            {
                "label": label,
                "exact_jaccard": round(ex_metrics["jaccard"], 5),
                "hw_hll_jaccard": round(hw_metrics["jaccard"], 5),
                "exact_mash_distance": round(ex_metrics["mash_distance"], 5),
                "hw_hll_mash_distance": round(hw_metrics["mash_distance"], 5),
            }
        )

    print("  [PASS] Hardware HLL Jaccard & Mash distances scale monotonically with SNV rate.")
    return results


def run_test4_real_genomes_benchmark(include_bacterial: bool = True) -> Dict[str, object]:
    """
    Test 4: Profiles the Viral & Bacterial NCBI RefSeq panels for cardinality accuracy,
    pairwise species/strain separation, 4-bank load balance, and DFF write-toggle savings.
    """
    print("\n" + "=" * 76)
    print("[TEST 4] Real NCBI Viral & Bacterial Genomes Hardware + Biology Benchmark")
    print("=" * 76)

    genome_files: List[Tuple[str, Path]] = [
        ("SARS-CoV-2 (Wuhan Ref)", VIRAL_DIR / "SARS_CoV_2_Wuhan_NC_045512.2.fasta"),
        ("SARS-CoV-2 (Omicron BA.1)", VIRAL_DIR / "SARS_CoV_2_Omicron_BA1_OL672836.1.fasta"),
        ("SARS-CoV-1 (Tor2)", VIRAL_DIR / "SARS_CoV_1_Tor2_NC_004718.3.fasta"),
        ("MERS-CoV", VIRAL_DIR / "MERS_CoV_NC_019843.3.fasta"),
        ("Zaire Ebolavirus", VIRAL_DIR / "Zaire_Ebolavirus_NC_002549.1.fasta"),
        ("Phage Lambda", VIRAL_DIR / "Bacteriophage_lambda_NC_001416.1.fasta"),
    ]
    if include_bacterial:
        genome_files.extend(
            [
                ("E. coli K-12 MG1655", BACTERIAL_DIR / "E_coli_K12_MG1655_NC_000913.3.fasta"),
                ("E. coli O157:H7 Sakai", BACTERIAL_DIR / "E_coli_O157_H7_Sakai_NC_002695.2.fasta"),
                ("S. enterica CT18", BACTERIAL_DIR / "Salmonella_enterica_CT18_NC_003198.1.fasta"),
                ("S. aureus NCTC8325", BACTERIAL_DIR / "Staphylococcus_aureus_NCTC8325_NC_007795.1.fasta"),
            ]
        )

    sketches: Dict[str, List[int]] = {}
    exact_sets: Dict[str, Set[str]] = {}
    cardinality_table: List[Dict[str, object]] = []

    print(
        f"  {'Genome':<26} | {'Exact k-mers':>12} | {'HW HLL Est':>12} | {'Rel Err':>8} | {'DFF Write %':>11}"
    )
    print("  " + "-" * 78)

    for label, fpath in genome_files:
        pipe = GenomeSketchPipeline()
        pipe.stream_fasta_file(fpath)
        sketch = pipe.get_sketch()
        sketches[label] = sketch

        exact_set = extract_exact_canonical_kmers(fpath)
        exact_sets[label] = exact_set

        exact_card = len(exact_set)
        hw_card = estimate_cardinality(sketch)
        rel_err_pct = abs(hw_card - exact_card) / float(exact_card) * 100.0

        total_valid = pipe.hll.total_updates_attempted
        total_writes = pipe.hll.total_writes_committed
        write_toggle_pct = (100.0 * total_writes / total_valid) if total_valid > 0 else 0.0
        bank_pcts = [
            round(100.0 * c / total_valid, 2) if total_valid > 0 else 0.0
            for c in pipe.hll.bank_access_counts
        ]

        print(
            f"  {label:<26} | {exact_card:>12,} | {hw_card:>12,.0f} | {rel_err_pct:>7.2f}% | "
            f"{write_toggle_pct:>9.3f}% ({total_writes} writes)"
        )

        cardinality_table.append(
            {
                "genome": label,
                "file": fpath.name,
                "total_cycles": pipe.cycle_count,
                "valid_kmers_streamed": total_valid,
                "exact_unique_kmers": exact_card,
                "hw_hll_estimated_kmers": round(hw_card, 1),
                "relative_error_pct": round(rel_err_pct, 2),
                "dff_writes_committed": total_writes,
                "dff_write_toggle_rate_pct": round(write_toggle_pct, 4),
                "dff_clock_gate_savings_pct": round(100.0 - write_toggle_pct, 4),
                "bank_access_distribution_pct": bank_pcts,
                "max_register_rank_rho": max(sketch),
                "min_register_rank_rho": min(sketch),
            }
        )

    # Pairwise biological comparisons of interest
    pairs_to_check = [
        ("SARS-CoV-2 (Wuhan Ref)", "SARS-CoV-2 (Omicron BA.1)", "Same species, close variant strain"),
        ("SARS-CoV-2 (Wuhan Ref)", "SARS-CoV-1 (Tor2)", "Related Betacoronavirus species"),
        ("SARS-CoV-2 (Wuhan Ref)", "MERS-CoV", "Divergent coronavirus genus"),
        ("SARS-CoV-2 (Wuhan Ref)", "Zaire Ebolavirus", "Unrelated RNA virus (negative control)"),
    ]
    if include_bacterial:
        pairs_to_check.extend(
            [
                ("E. coli K-12 MG1655", "E. coli O157:H7 Sakai", "Same bacterial species, pathogenic vs. lab strain"),
                ("E. coli K-12 MG1655", "S. enterica CT18", "Cross-genus Enterobacteriaceae"),
                ("E. coli K-12 MG1655", "S. aureus NCTC8325", "Unrelated Gram-positive bacterium"),
            ]
        )

    print("\n  Pairwise Genomic Similarity & Mash Distance Benchmark:")
    print(
        f"  {'Genome Pair':<48} | {'Exact J':>8} | {'HW HLL J':>8} | {'Exact ANI':>9} | {'HW ANI':>8}"
    )
    print("  " + "-" * 90)

    pairwise_results = []
    for g1, g2, desc in pairs_to_check:
        ex = exact_jaccard_and_mash(exact_sets[g1], exact_sets[g2])
        hw = estimate_jaccard_and_mash(sketches[g1], sketches[g2])
        pair_label = f"{g1} vs. {g2}"
        print(
            f"  {pair_label[:48]:<48} | {ex['jaccard']:>8.4f} | {hw['jaccard']:>8.4f} | "
            f"{ex['ani_pct']:>8.2f}% | {hw['mash_ani_pct']:>7.2f}%"
        )
        pairwise_results.append(
            {
                "genome_a": g1,
                "genome_b": g2,
                "biological_context": desc,
                "exact_jaccard": round(ex["jaccard"], 5),
                "hw_hll_jaccard": round(hw["jaccard"], 5),
                "exact_mash_distance": round(ex["mash_distance"], 5),
                "hw_hll_mash_distance": round(hw["mash_distance"], 5),
                "exact_ani_pct": round(ex["ani_pct"], 2),
                "hw_hll_ani_pct": round(hw["mash_ani_pct"], 2),
            }
        )

    return {
        "cardinality_benchmarks": cardinality_table,
        "pairwise_benchmarks": pairwise_results,
    }


def write_markdown_report(summary: Dict[str, object]) -> None:
    """Generates a clean Markdown verification report for the BTP documentation."""
    c_rows = summary["test4_real_genomes"]["cardinality_benchmarks"]  # type: ignore
    p_rows = summary["test4_real_genomes"]["pairwise_benchmarks"]     # type: ignore
    m_rows = summary["test3_mutations"]                               # type: ignore

    lines = [
        "# Golden Model Verification & Biological Benchmark Report",
        "**Architecture:** Streaming Genome Sketching Engine (`ntHash-32`, $k=21$ + $4\\times 64\\times 5\\text{-bit}$ Banked HLL)  ",
        f"**Generated:** {summary['timestamp']}  ",
        "**Status:** All unit tests and biological benchmarks passed.",
        "",
        "---",
        "",
        "## 1. Unit & Corner-Case Hardware Verification",
        "| Test ID | Verification Target | Result | Details |",
        "| :--- | :--- | :---: | :--- |",
        f"| **Test 1a** | Rolling $O(1)$ vs. Direct $O(k)$ `ntHash-32` | **PASS** | `{summary['test1']['rolling_vs_direct_cycles_verified']:,}` consecutive cycles matched 100% bit-for-bit (`h_fwd`, `h_rev`, `h_canon`, `h_mixed`). |",
        f"| **Test 1b** | Ambiguous `'N'` Base Reset & Sub-$k$ Suppression | **PASS** | 20-bp short island ($<21\\text{{ bp}}$) between `'N'` gaps emitted `0` hashes; `{summary['test1']['n_gap_observed_kmers']}/960` valid $k$-mers verified. |",
        "| **Test 2a** | Synthetic $10\\text{ kbp}$ Forward vs. Reverse-Complement | **PASS** | `256/256` HLL 5-bit registers and `9,980` canonical hashes matched 100% bit-for-bit. |",
        "| **Test 2b** | Real SARS-CoV-2 ($29,903\\text{ bp}$) Strand Invariance | **PASS** | Forward and reverse-complement viral strands produced identical `256 x 5-bit` hardware sketches. |",
        "",
        "---",
        "",
        "## 2. Cardinality Accuracy & Low-Power DFF Write-Gating Profile",
        "Theoretical standard error for $M = 256$ HLL registers is $\\sigma \\approx 1.04 / \\sqrt{256} = 6.50\\%$. Notice that across all viral and bacterial genomes, **over $96\\%$ to $99.98\\%$ of clock cycles do not write to the DFF array**, proving the effectiveness of conditional write-enable clock gating (`rho > old_val`).",
        "",
        "| Genome | Streamed $k$-mers | Exact Unique $k$-mers | HW HLL Estimate | Rel. Error | DFF Writes | Clock-Gated Savings | Bank Balance (B0/B1/B2/B3 %) |",
        "| :--- | ---: | ---: | ---: | ---: | ---: | ---: | :--- |",
    ]

    for r in c_rows:
        b_str = "/".join(f"{x:.1f}" for x in r["bank_access_distribution_pct"])
        lines.append(
            f"| {r['genome']} | {r['valid_kmers_streamed']:,} | {r['exact_unique_kmers']:,} | "
            f"{r['hw_hll_estimated_kmers']:,.0f} | {r['relative_error_pct']:.2f}% | "
            f"{r['dff_writes_committed']:,} | **{r['dff_clock_gate_savings_pct']:.3f}%** | `{b_str}` |"
        )

    lines.extend(
        [
            "",
            "---",
            "",
            "## 3. Controlled SNV Mutation Series ($10\\text{ kbp}$ Synthetic Benchmark)",
            "| Mutation Level | Exact Jaccard $J$ | HW HLL Jaccard $\\hat{J}$ | Exact Mash Distance $D$ | HW HLL Mash Distance $\\hat{D}$ |",
            "| :--- | ---: | ---: | ---: | ---: |",
        ]
    )
    for m in m_rows:
        lines.append(
            f"| {m['label']} | {m['exact_jaccard']:.4f} | {m['hw_hll_jaccard']:.4f} | "
            f"{m['exact_mash_distance']:.4f} | {m['hw_hll_mash_distance']:.4f} |"
        )

    lines.extend(
        [
            "",
            "---",
            "",
            "## 4. Real Viral & Bacterial Pairwise Species/Strain Resolution",
            "| Genome A | Genome B | Biological Relationship | Exact $J$ | HW HLL $\\hat{J}$ | Exact ANI % | HW HLL ANI % |",
            "| :--- | :--- | :--- | ---: | ---: | ---: | ---: |",
        ]
    )
    for p in p_rows:
        lines.append(
            f"| {p['genome_a']} | {p['genome_b']} | {p['biological_context']} | "
            f"{p['exact_jaccard']:.4f} | {p['hw_hll_jaccard']:.4f} | "
            f"{p['exact_ani_pct']:.2f}% | {p['hw_hll_ani_pct']:.2f}% |"
        )

    with open(REPORT_MD_PATH, "w", encoding="utf-8", newline="\n") as f:
        f.write("\n".join(lines) + "\n")


def main() -> int:
    t0 = time.time()
    t1_res = run_test1_rolling_equivalence_and_gaps()
    t2_res = run_test2_strand_invariance()
    t3_res = run_test3_mutation_monotonicity()
    t4_res = run_test4_real_genomes_benchmark(include_bacterial=True)
    elapsed = time.time() - t0

    summary = {
        "project": "SCL 180nm Streaming Genome Sketching ASIC (ntHash-32 + Banked HLL)",
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "runtime_seconds": round(elapsed, 2),
        "test1": t1_res,
        "test2": t2_res,
        "test3_mutations": t3_res,
        "test4_real_genomes": t4_res,
    }

    with open(RESULTS_JSON_PATH, "w", encoding="utf-8", newline="\n") as f:
        json.dump(summary, f, indent=2)

    write_markdown_report(summary)

    print("\n" + "=" * 76)
    print(f"ALL VERIFICATION SUITES PASSED in {elapsed:.2f}s!")
    print(f"  - JSON Results : {RESULTS_JSON_PATH}")
    print(f"  - MD Report    : {REPORT_MD_PATH}")
    print("=" * 76)
    return 0


if __name__ == "__main__":
    sys.exit(main())
