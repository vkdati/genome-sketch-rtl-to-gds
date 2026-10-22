#!/usr/bin/env python3
"""
Module 3: End-to-End Cycle-Accurate Streaming Genome Sketching Pipeline
          & Host Post-Processing (Cardinality, Jaccard Index, Mash Distance)

Connects:
  Stage 1 & 2: NtHash32Engine (21-bp Shift Register + Rolling Canonical ntHash-32)
  Stage 3 & 4: BankedHLL256   (24-bit LZD + 4-Bank x 64-Reg x 5-bit HLL Array)

Also provides exact mathematical post-processing functions executed by the host
after reading out the 256 x 5-bit sketch registers over the serial/8-bit I/O bus.
"""

import math
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Tuple

from .banked_hll import TOTAL_REGS, BankedHLL256, HLLUpdateResult
from .nthash32 import BASE_TO_INT, KMER_LEN, NtHash32Engine, NtHashStepOutput

# Standard HyperLogLog bias correction factor alpha_M for M = 256 registers:
# alpha_256 = 0.7213 / (1 + 1.079 / 256) ≈ 0.7182726
ALPHA_256 = 0.7213 / (1.0 + 1.079 / TOTAL_REGS)


@dataclass
class CycleTrace:
    """Complete cycle-by-cycle hardware transaction trace for RTL verification."""

    cycle: int
    char_in: str
    b_in: int
    is_ambiguous: bool
    kmer_valid: bool
    valid_count: int
    h_fwd: int
    h_rev: int
    h_canon: int
    h_mixed: int
    bank_id: int
    sub_addr: int
    flat_idx: int
    rho: int
    old_val: int
    new_val: int
    write_en: bool


class GenomeSketchPipeline:
    """
    Top-level cycle-accurate Golden Model of the SCL 180nm Genome Sketching ASIC.
    """

    def __init__(self) -> None:
        self.nthash = NtHash32Engine(k=KMER_LEN)
        self.hll = BankedHLL256()
        self.cycle_count = 0

    def reset(self) -> None:
        """Full chip reset (clears both the ntHash pipeline and the HLL registers)."""
        self.nthash.reset()
        self.hll.reset()
        self.cycle_count = 0

    def reset_stream_only(self) -> None:
        """
        Clears the 21-bp sliding window (e.g., at contig/read boundary '>' in FASTA)
        while preserving the accumulated HLL sketch registers.
        """
        self.nthash.reset()

    def step_char(self, ch: str) -> CycleTrace:
        """Processes a single nucleotide character ('A', 'C', 'G', 'T', or 'N') in 1 clock cycle."""
        self.cycle_count += 1
        if ch in BASE_TO_INT:
            b_in = BASE_TO_INT[ch]
            is_ambig = False
        else:
            b_in = 0
            is_ambig = True

        nt_out: NtHashStepOutput = self.nthash.step(b_in, is_ambiguous=is_ambig)
        hll_out: HLLUpdateResult = self.hll.update(
            nt_out.h_mixed, kmer_valid=nt_out.kmer_valid
        )

        return CycleTrace(
            cycle=self.cycle_count,
            char_in=ch.upper(),
            b_in=b_in,
            is_ambiguous=is_ambig,
            kmer_valid=nt_out.kmer_valid,
            valid_count=nt_out.valid_count,
            h_fwd=nt_out.h_fwd,
            h_rev=nt_out.h_rev,
            h_canon=nt_out.h_canon,
            h_mixed=nt_out.h_mixed,
            bank_id=hll_out.bank_id,
            sub_addr=hll_out.sub_addr,
            flat_idx=hll_out.flat_idx,
            rho=hll_out.rho,
            old_val=hll_out.old_val,
            new_val=hll_out.new_val,
            write_en=hll_out.write_en,
        )

    def stream_sequence(
        self, sequence: str, record_trace: bool = False
    ) -> List[CycleTrace]:
        """Streams a raw nucleotide string through the hardware model."""
        traces: List[CycleTrace] = []
        for ch in sequence:
            if ch.isspace():
                continue
            tr = self.step_char(ch)
            if record_trace:
                traces.append(tr)
        return traces

    def stream_fasta_file(
        self, fasta_path: Path, record_trace: bool = False
    ) -> List[CycleTrace]:
        """
        Streams an entire FASTA file through the hardware model.
        Resets the 21-mer sliding window at each '>' record header while accumulating
        all records into the same 256-register HLL sketch.
        """
        self.reset()
        traces: List[CycleTrace] = []
        with open(fasta_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                if line.startswith(">"):
                    self.reset_stream_only()
                    continue
                for ch in line:
                    tr = self.step_char(ch)
                    if record_trace:
                        traces.append(tr)
        return traces

    def get_sketch(self) -> List[int]:
        """Returns the 256 x 5-bit HLL register array."""
        return self.hll.get_flat_registers()


# ============================================================================
# Host-Side Mathematical Post-Processing (Off-Chip Software)
# ============================================================================


def estimate_cardinality(registers: List[int]) -> float:
    """
    Computes the estimated number of unique canonical k-mers from a 256-register
    HLL sketch using Flajolet's harmonic mean estimator + small-range LinearCounting.
    """
    if len(registers) != TOTAL_REGS:
        raise ValueError(f"Expected {TOTAL_REGS} registers, got {len(registers)}")

    m = float(TOTAL_REGS)
    harmonic_denom = sum(2.0 ** (-r) for r in registers)
    raw_est = ALPHA_256 * (m * m) / harmonic_denom

    # Small-range correction (LinearCounting) when empty buckets exist and E <= 2.5 * M
    zero_buckets = sum(1 for r in registers if r == 0)
    if raw_est <= 2.5 * m and zero_buckets > 0:
        return m * math.log(m / float(zero_buckets))

    # Large-range saturation correction for 24-bit geometric rank space (L = 2^32)
    two_pow_32 = float(1 << 32)
    if raw_est > (two_pow_32 / 30.0):
        ratio = raw_est / two_pow_32
        if ratio < 1.0:
            return -two_pow_32 * math.log(1.0 - ratio)

    return raw_est


def union_sketches(sketch_a: List[int], sketch_b: List[int]) -> List[int]:
    """
    Exact HLL Union Sketch property:
      Reg_{A U B}[i] = max(Reg_A[i], Reg_B[i]) for i in 0..255.
    """
    return [max(a, b) for a, b in zip(sketch_a, sketch_b)]


def estimate_jaccard_and_mash(
    sketch_a: List[int], sketch_b: List[int], k: int = KMER_LEN
) -> Dict[str, float]:
    """
    Estimates pairwise genomic similarity (Jaccard index J) and Mash evolutionary
    distance D between two 256-register hardware HLL sketches.

    Uses the Inclusion-Exclusion HLL Union estimator:
      |A|, |B|, |A U B| = estimate_cardinality(A), estimate_cardinality(B), estimate_cardinality(max(A, B))
      |A n B| = max(0, |A| + |B| - |A U B|)
      J_hll   = |A n B| / |A U B|
      D_mash  = -1/k * ln(2 * J / (1 + J))
    """
    if sketch_a == sketch_b:
        card = estimate_cardinality(sketch_a)
        return {
            "card_a": card,
            "card_b": card,
            "card_union": card,
            "card_intersect": card,
            "jaccard": 1.0 if card > 0 else 0.0,
            "mash_distance": 0.0,
            "mash_ani_pct": 100.0,
        }

    card_a = estimate_cardinality(sketch_a)
    card_b = estimate_cardinality(sketch_b)
    sketch_u = union_sketches(sketch_a, sketch_b)
    card_u = estimate_cardinality(sketch_u)

    if card_u <= 0.0:
        return {
            "card_a": 0.0,
            "card_b": 0.0,
            "card_union": 0.0,
            "card_intersect": 0.0,
            "jaccard": 0.0,
            "mash_distance": 1.0,
            "mash_ani_pct": 0.0,
        }

    card_intersect = max(0.0, card_a + card_b - card_u)
    jaccard = min(1.0, max(0.0, card_intersect / card_u))

    if jaccard <= 0.0:
        mash_dist = 1.0
    else:
        mash_dist = max(0.0, -1.0 / float(k) * math.log(2.0 * jaccard / (1.0 + jaccard)))
        mash_dist = min(1.0, mash_dist)

    ani_pct = max(0.0, (1.0 - mash_dist) * 100.0)

    return {
        "card_a": card_a,
        "card_b": card_b,
        "card_union": card_u,
        "card_intersect": card_intersect,
        "jaccard": jaccard,
        "mash_distance": mash_dist,
        "mash_ani_pct": ani_pct,
    }
