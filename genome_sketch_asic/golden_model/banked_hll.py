#!/usr/bin/env python3
"""
Module 2: 24-Bit Leading-Zero Detector (LZD24) & 4-Bank x 64-Reg x 5-Bit HLL Array
Target Process: SCL 180nm CMOS (Standard-Cell D-Flip-Flop Memory, Zero SRAM)

Hardware Architecture Details:
------------------------------
1. Why Banked Register File?
   The default SCL 180nm PDK lacks an SRAM compiler, so all 256 HyperLogLog (HLL)
   registers (5 bits each = 1,280 DFFs) are synthesized as standard D-flip-flops.
   Instead of a single 256-to-1 global multiplexer (which causes severe routing
   congestion on a 4-Metal stack), the register file is partitioned into:
     - 4 Independent Banks (selected by h_mixed[31:30])
     - 64 Registers per Bank (selected by h_mixed[29:24])
     - 5 Bits per Register (storing maximum leading-zero rank rho in [1..25])
2. 24-Bit Leading-Zero Detector (LZD24):
   Examines the lower 24 bits of the mixed hash (h_mixed[23:0]) from MSB (bit 23)
   down to LSB (bit 0) and returns:
     rho = leading_zeros(h_mixed[23:0]) + 1   (5-bit unsigned integer in 1..25)
3. Low-Power Conditional Write Enable:
   A register is clocked/updated ONLY when `kmer_valid && (rho > old_val)`.
   After brief initial warm-up, >98% of clock cycles do not toggle the DFFs,
   drastically reducing dynamic switching power.
"""

from dataclasses import dataclass
from typing import List, Tuple

NUM_BANKS = 4
REGS_PER_BANK = 64
TOTAL_REGS = NUM_BANKS * REGS_PER_BANK  # 256 registers
REG_WIDTH_BITS = 5                       # Holds values 0..25 (5-bit unsigned: 0..31)
LZD_INPUT_BITS = 24                      # h_mixed[23:0]
MASK24 = 0xFFFFFF


def lzd24(val_24b: int) -> int:
    """
    Bit-accurate 24-bit Leading-Zero Detector + 1 (computes HLL rank rho).
    Examines bits [23:0] from MSB (bit 23) to LSB (bit 0).

    Examples:
      - If bit 23 == 1 (val_24b >= 0x800000) -> 0 leading zeros -> rho = 1
      - If bit 23 == 0, bit 22 == 1          -> 1 leading zero  -> rho = 2
      - If val_24b == 0                      -> 24 leading zeros -> rho = 25 (5'd25)
    """
    w = val_24b & MASK24
    if w == 0:
        return LZD_INPUT_BITS + 1  # 25 (5'b11001)
    # Priority encoder from bit 23 down to bit 0
    leading_zeros = 0
    for bit_idx in range(LZD_INPUT_BITS - 1, -1, -1):
        if (w >> bit_idx) & 1:
            break
        leading_zeros += 1
    return leading_zeros + 1


def decode_hash_to_hll(h_mixed: int) -> Tuple[int, int, int, int]:
    """
    Splits a 32-bit mixed canonical hash into HLL hardware fields:
      - bank_id  = h_mixed[31:30] (2 bits, 0..3)
      - sub_addr = h_mixed[29:24] (6 bits, 0..63)
      - flat_idx = h_mixed[31:24] (8 bits, 0..255)
      - rho      = lzd24(h_mixed[23:0]) (5 bits, 1..25)
    """
    h = h_mixed & 0xFFFFFFFF
    bank_id = (h >> 30) & 0x3
    sub_addr = (h >> 24) & 0x3F
    flat_idx = (h >> 24) & 0xFF
    rho = lzd24(h & MASK24)
    return bank_id, sub_addr, flat_idx, rho


@dataclass
class HLLUpdateResult:
    """Cycle-level result of probing/updating the Banked HLL array."""

    bank_id: int
    sub_addr: int
    flat_idx: int
    rho: int
    old_val: int
    new_val: int
    write_en: bool


class BankedHLL256:
    """
    Cycle-accurate model of the 4-Bank x 64-Register x 5-bit HLL DFF Array.
    Total on-chip storage: 256 x 5 = 1,280 bits (160 bytes).
    """

    def __init__(self) -> None:
        self.reset()

    def reset(self) -> None:
        """Clears all 256 5-bit registers and hardware performance counters."""
        self.banks: List[List[int]] = [
            [0] * REGS_PER_BANK for _ in range(NUM_BANKS)
        ]
        self.bank_access_counts: List[int] = [0] * NUM_BANKS
        self.bank_write_counts: List[int] = [0] * NUM_BANKS
        self.total_updates_attempted: int = 0
        self.total_writes_committed: int = 0

    def update(self, h_mixed: int, kmer_valid: bool = True) -> HLLUpdateResult:
        """
        Executes Stage 3 (LZD24 + Decode) and Stage 4 (Banked Register Max-Update).
        """
        if not kmer_valid:
            return HLLUpdateResult(
                bank_id=0,
                sub_addr=0,
                flat_idx=0,
                rho=0,
                old_val=0,
                new_val=0,
                write_en=False,
            )

        bank_id, sub_addr, flat_idx, rho = decode_hash_to_hll(h_mixed)
        old_val = self.banks[bank_id][sub_addr]
        write_en = rho > old_val
        new_val = rho if write_en else old_val

        self.total_updates_attempted += 1
        self.bank_access_counts[bank_id] += 1
        if write_en:
            self.banks[bank_id][sub_addr] = new_val & 0x1F  # 5-bit register mask
            self.bank_write_counts[bank_id] += 1
            self.total_writes_committed += 1

        return HLLUpdateResult(
            bank_id=bank_id,
            sub_addr=sub_addr,
            flat_idx=flat_idx,
            rho=rho,
            old_val=old_val,
            new_val=new_val,
            write_en=write_en,
        )

    def get_flat_registers(self) -> List[int]:
        """Returns all 256 5-bit registers in linear address order [0..255]."""
        flat: List[int] = []
        for b in range(NUM_BANKS):
            flat.extend(self.banks[b])
        return flat

    def nonzero_buckets(self) -> int:
        """Returns the number of registers with value > 0."""
        return sum(1 for v in self.get_flat_registers() if v > 0)
