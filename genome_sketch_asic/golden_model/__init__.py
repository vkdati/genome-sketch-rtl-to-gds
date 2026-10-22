"""
Bit-Accurate Python Golden Reference Model for the SCL 180nm
Streaming Genome Sketching ASIC (ntHash-32 + 4x64x5-bit Banked HLL).
"""

from .nthash32 import (
    KMER_LEN,
    BASE_TO_INT,
    INT_TO_BASE,
    SEED_TABLE,
    SEED_K_TABLE,
    SEED_RC_ROR1_TABLE,
    SEED_RC_KM1_TABLE,
    rol32,
    ror32,
    avalanche_mix32,
    direct_nthash32_kmer,
    NtHash32Engine,
)
from .banked_hll import (
    NUM_BANKS,
    REGS_PER_BANK,
    TOTAL_REGS,
    REG_WIDTH_BITS,
    lzd24,
    decode_hash_to_hll,
    BankedHLL256,
)
from .sketch_pipeline import (
    CycleTrace,
    GenomeSketchPipeline,
    estimate_cardinality,
    union_sketches,
    estimate_jaccard_and_mash,
)

__all__ = [
    "KMER_LEN",
    "BASE_TO_INT",
    "INT_TO_BASE",
    "SEED_TABLE",
    "SEED_K_TABLE",
    "SEED_RC_ROR1_TABLE",
    "SEED_RC_KM1_TABLE",
    "rol32",
    "ror32",
    "avalanche_mix32",
    "direct_nthash32_kmer",
    "NtHash32Engine",
    "NUM_BANKS",
    "REGS_PER_BANK",
    "TOTAL_REGS",
    "REG_WIDTH_BITS",
    "lzd24",
    "decode_hash_to_hll",
    "BankedHLL256",
    "CycleTrace",
    "GenomeSketchPipeline",
    "estimate_cardinality",
    "union_sketches",
    "estimate_jaccard_and_mash",
]
