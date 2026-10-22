# Hardware Verification Test Vectors (`tv/`)
**Target:** SCL 180nm Streaming Genome Sketching ASIC (`ntHash-32` + $4\times 64\times 5\text{-bit}$ Banked HLL)

All `.hex` files in this directory are formatted for direct loading via Verilog `$readmemh()`.

---

## 1. Test Vector Suites Included

| Suite | Stimulus File | Trace File | Sketch File | Clock Cycles | Description |
| :--- | :--- | :--- | :--- | ---: | :--- |
| **Corner-Case Regression** | `stimulus_dna.hex` | `expected_trace.hex` | `expected_sketch.hex` | `2,065` | Combines `synth_homopolymer_repeats.fasta` ($1,024\text{ bp}$), a contig boundary reset, and `synth_ambiguous_N_gaps.fasta` ($1,040\text{ bp}$ with `'N'` runs and a 20-bp sub-$k$ island). |
| **Full Viral Genome** | `sars_cov_2_stimulus.hex` | `sars_cov_2_expected_trace.hex` | `sars_cov_2_expected_sketch.hex` | `29,903` | Complete NCBI RefSeq **SARS-CoV-2** reference genome (`NC_045512.2`). Simulates in $< 0.2\text{ s}$ in Icarus Verilog / Verilator. |

---

## 2. Bit-Field Specifications

### 2.1 `stimulus_dna.hex` (8-bit Hex Word `[7:0]` per Clock Cycle)
| Bits | Signal Name | Description |
| :---: | :--- | :--- |
| `[7:5]` | `reserved` | Always `3'b000` |
| `[4]` | `clear_sketch` | `1'b1` = Synchronous full reset (clears all 256 HLL registers and 21-bp window) |
| `[3]` | `clear_window` | `1'b1` = Ambiguous `'N'` base or contig break (resets 21-bp warm-up counter to 0; preserves HLL registers) |
| `[2]` | `valid_in` | `1'b1` = Valid nucleotide base present on `base_in[1:0]` |
| `[1:0]` | `base_in[1:0]` | `2'b00` = A, `2'b01` = C, `2'b10` = G, `2'b11` = T |

### 2.2 `expected_trace.hex` (128-bit Hex Word `[127:0]` per Clock Cycle)
Every line represents the exact internal hardware state at the end of that clock cycle:

| Bits | Width | Signal Name | Description |
| :---: | :---: | :--- | :--- |
| `[127:96]` | 32b | `exp_h_fwd[31:0]` | Rolling forward `ntHash-32` register |
| `[95:64]` | 32b | `exp_h_rev[31:0]` | Rolling reverse-complement `ntHash-32` register |
| `[63:32]` | 32b | `exp_h_mixed[31:0]` | Avalanche-mixed canonical hash (`0` when `kmer_valid == 0`) |
| `[31:28]` | 4b | `{3'b0, exp_kmer_valid}` | `1` when window has accumulated $\ge 21$ contiguous valid bases |
| `[27:24]` | 4b | `{3'b0, exp_write_en}` | `1` when `kmer_valid && (rho > old_val)` |
| `[23:16]` | 8b | `exp_flat_idx[7:0]` | `{bank_id[1:0], sub_addr[5:0]}` ($0\dots 255$) |
| `[15:8]` | 8b | `{3'b0, exp_rho[4:0]}` | 24-bit Leading-Zero Detector output $\rho \in [1, 25]$ |
| `[7:0]` | 8b | `{3'b0, exp_new_val[4:0]}` | Updated 5-bit register value stored at `exp_flat_idx` |

### 2.3 `expected_sketch.hex` (256 Lines, 8-bit Hex Word `[7:0]` per Line)
* Lines `0` to `255` hold the final 5-bit HLL register values (`8'h00` to `8'h19`) in linear address order `{bank_id[1:0], sub_addr[5:0]}`.
