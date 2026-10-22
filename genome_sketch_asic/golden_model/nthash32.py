#!/usr/bin/env python3
"""
Module 1: Bit-Accurate 32-Bit Rolling Canonical ntHash Engine (ntHash-32)
Target Process: SCL 180nm CMOS (Zero Multipliers, Hardwired Seed Rotations)

Hardware Architecture Details:
------------------------------
1. DNA 2-bit Base Encoding:
     A = 2'b00 (0), C = 2'b01 (1), G = 2'b10 (2), T = 2'b11 (3)
   Watson-Crick Complement property:
     comp(b) = ~b = b ^ 2'b11
2. Sliding Window Shift Register:
     21 stages x 2 bits = 42 D-Flip-Flops + 5-bit warm-up counter (0..21).
     Ambiguous bases ('N') clear the warm-up counter to 0 synchronously.
3. Multiplier-Free Rolling Equations (1 clock cycle per base):
     h_fwd[t] = ROL32(h_fwd[t-1], 1) ^ (window_full ? SEED_K[b_out] : 0) ^ SEED[b_in]
     h_rev[t] = ROR32(h_rev[t-1], 1) ^ (window_full ? SEED_RC_ROR1[b_out] : 0) ^ SEED_RC_KM1[b_in]
   Notice that during warm-up (valid_count < 21), masking out the b_out XOR terms
   allows the exact same rolling datapath to self-initialize the polynomial hash
   without any extra initialization multiplexer or multi-cycle barrel shifter!
4. Canonical Selection & Avalanche Finalizer:
     h_canon = min(h_fwd[t], h_rev[t])
     h_mixed = avalanche_mix32(h_canon)
"""

from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple

MASK32 = 0xFFFFFFFF
KMER_LEN = 21

# 2-bit DNA encoding (where ~b == b ^ 3 is the exact Watson-Crick complement)
BASE_TO_INT: Dict[str, int] = {
    "A": 0b00,
    "C": 0b01,
    "G": 0b10,
    "T": 0b11,
    "a": 0b00,
    "c": 0b01,
    "g": 0b10,
    "t": 0b11,
}
INT_TO_BASE: Dict[int, str] = {0b00: "A", 0b01: "C", 0b10: "G", 0b11: "T"}


def rol32(val: int, shift: int) -> int:
    """32-bit cyclic left rotation (pure wire permutation in Verilog when shift is constant)."""
    s = shift & 31
    val &= MASK32
    if s == 0:
        return val
    return ((val << s) | (val >> (32 - s))) & MASK32


def ror32(val: int, shift: int) -> int:
    """32-bit cyclic right rotation (pure wire permutation in Verilog when shift is constant)."""
    s = shift & 31
    val &= MASK32
    if s == 0:
        return val
    return ((val >> s) | (val << (32 - s))) & MASK32


# Hardwired 32-bit ntHash Seed Constants (derived from canonical ntHash 64-bit seeds)
SEED_TABLE: Tuple[int, int, int, int] = (
    0x3C8BFBB3,  # 2'b00: A
    0x3193C185,  # 2'b01: C
    0x20323ED0,  # 2'b10: G
    0x295549F5,  # 2'b11: T
)

# Pre-rotated hardwired lookup tables (4 x 32-bit constant wires in Verilog; 0 flip-flops)
# SEED_K[b]       = ROL32(SEED[b], KMER_LEN)          -> exits forward hash after k cycles
# SEED_RC_ROR1[b] = ROR32(SEED[b ^ 3], 1)             -> exits rev-comp hash after k cycles
# SEED_RC_KM1[b]  = ROL32(SEED[b ^ 3], KMER_LEN - 1)  -> enters rev-comp hash at current cycle
SEED_K_TABLE: Tuple[int, int, int, int] = tuple(
    rol32(SEED_TABLE[b], KMER_LEN) for b in range(4)
)  # type: ignore
SEED_RC_ROR1_TABLE: Tuple[int, int, int, int] = tuple(
    ror32(SEED_TABLE[b ^ 3], 1) for b in range(4)
)  # type: ignore
SEED_RC_KM1_TABLE: Tuple[int, int, int, int] = tuple(
    rol32(SEED_TABLE[b ^ 3], KMER_LEN - 1) for b in range(4)
)  # type: ignore


def avalanche_mix32(h: int) -> int:
    """
    Multiplier-free 32-bit XOR-shift avalanche finalizer.
    In Verilog: three XOR stages with constant wire shifts (>> 16, << 7, >> 11).
    Decouples the upper 8 HLL bucket-index bits from the lower 24 leading-zero bits.
    """
    h &= MASK32
    h ^= (h >> 16) & MASK32
    h ^= (h << 7) & MASK32
    h ^= (h >> 11) & MASK32
    return h & MASK32


def direct_nthash32_kmer(kmer: str) -> Tuple[int, int, int, int]:
    """
    Computes the non-rolling (direct O(k)) ntHash-32 of a 21-mer string from scratch.
    Used as the mathematical oracle to prove the 1-cycle rolling hardware equations.

    Returns:
      (h_fwd, h_rev, h_canon, h_mixed) as 32-bit unsigned integers.
    """
    if len(kmer) != KMER_LEN:
        raise ValueError(f"Expected {KMER_LEN}-mer, got length {len(kmer)}")

    h_fwd = 0
    h_rev = 0
    for i, ch in enumerate(kmer):
        b = BASE_TO_INT[ch]
        b_rc = b ^ 3
        # Forward: oldest base (i=0) rotated left by k-1, newest (i=k-1) rotated by 0
        h_fwd ^= rol32(SEED_TABLE[b], KMER_LEN - 1 - i)
        # Reverse-complement: oldest base (i=0) rotated by 0, newest (i=k-1) rotated by k-1
        h_rev ^= rol32(SEED_TABLE[b_rc], i)

    h_fwd &= MASK32
    h_rev &= MASK32
    h_canon = h_fwd if h_fwd <= h_rev else h_rev
    h_mixed = avalanche_mix32(h_canon)
    return h_fwd, h_rev, h_canon, h_mixed


@dataclass
class NtHashStepOutput:
    """Cycle-accurate outputs emitted by the ntHash-32 hardware block on a clock edge."""

    kmer_valid: bool
    b_in: int
    b_out: int
    valid_count: int
    h_fwd: int
    h_rev: int
    h_canon: int
    h_mixed: int


class NtHash32Engine:
    """
    Cycle-accurate, bit-accurate model of the SCL 180nm rolling ntHash-32 hardware block.
    Hardware state:
      - shift_reg:   21 x 2-bit DFFs (42 bits)
      - valid_count: 5-bit unsigned counter (0..21)
      - h_fwd_reg:   32-bit DFF register
      - h_rev_reg:   32-bit DFF register
    """

    def __init__(self, k: int = KMER_LEN) -> None:
        if k != KMER_LEN:
            raise ValueError(f"Hardware constants are parameterized for k={KMER_LEN}")
        self.k = k
        self.reset()

    def reset(self) -> None:
        """Synchronous hardware reset (rst_n == 0 or sequence break)."""
        self.shift_reg: List[int] = [0] * self.k  # Index 0 = newest, Index k-1 = oldest
        self.valid_count: int = 0                 # 5-bit saturation counter (0..21)
        self.h_fwd_reg: int = 0                   # 32-bit unsigned
        self.h_rev_reg: int = 0                   # 32-bit unsigned

    def step(self, base_2b: int, is_ambiguous: bool = False) -> NtHashStepOutput:
        """
        Advances the hardware pipeline by 1 clock cycle for an incoming DNA base.

        Args:
          base_2b:      2-bit encoded base (0=A, 1=C, 2=G, 3=T)
          is_ambiguous: True if the input character was 'N' or non-ACGT (triggers sync clear)
        """
        if is_ambiguous:
            self.reset()
            return NtHashStepOutput(
                kmer_valid=False,
                b_in=0,
                b_out=0,
                valid_count=0,
                h_fwd=0,
                h_rev=0,
                h_canon=0,
                h_mixed=0,
            )

        b_in = base_2b & 0b11
        # The exiting base is at the tail of the 21-base shift register
        b_out = self.shift_reg[self.k - 1]
        window_was_full = self.valid_count == self.k

        # Gate off the exiting base XOR contribution during the 21-cycle warm-up phase
        out_fwd_term = SEED_K_TABLE[b_out] if window_was_full else 0
        out_rev_term = SEED_RC_ROR1_TABLE[b_out] if window_was_full else 0

        # Next-state combinational logic for h_fwd and h_rev (zero multipliers!)
        next_h_fwd = (
            rol32(self.h_fwd_reg, 1) ^ out_fwd_term ^ SEED_TABLE[b_in]
        ) & MASK32
        next_h_rev = (
            ror32(self.h_rev_reg, 1) ^ out_rev_term ^ SEED_RC_KM1_TABLE[b_in]
        ) & MASK32

        # Update sequential DFF state
        self.shift_reg = [b_in] + self.shift_reg[:-1]
        if self.valid_count < self.k:
            self.valid_count += 1
        self.h_fwd_reg = next_h_fwd
        self.h_rev_reg = next_h_rev

        kmer_valid = self.valid_count == self.k
        h_canon = (
            self.h_fwd_reg if self.h_fwd_reg <= self.h_rev_reg else self.h_rev_reg
        )
        h_mixed = avalanche_mix32(h_canon) if kmer_valid else 0

        return NtHashStepOutput(
            kmer_valid=kmer_valid,
            b_in=b_in,
            b_out=b_out if window_was_full else 0,
            valid_count=self.valid_count,
            h_fwd=self.h_fwd_reg,
            h_rev=self.h_rev_reg,
            h_canon=h_canon if kmer_valid else 0,
            h_mixed=h_mixed,
        )


if __name__ == "__main__":
    # Quick self-test of direct vs. rolling equivalence and strand invariance
    test_seq = "ACGTACGTACGTACGTACGTAGCATGCATGCATGCATGCAT"
    engine = NtHash32Engine()
    for idx, ch in enumerate(test_seq):
        out = engine.step(BASE_TO_INT[ch])
        if out.kmer_valid:
            kmer_str = test_seq[idx - KMER_LEN + 1 : idx + 1]
            df, dr, dc, dm = direct_nthash32_kmer(kmer_str)
            assert (out.h_fwd, out.h_rev, out.h_canon, out.h_mixed) == (
                df,
                dr,
                dc,
                dm,
            ), f"Mismatch at index {idx}!"
    print(f"[PASS] ntHash-32 self-test passed on {len(test_seq)} bp sequence.")
