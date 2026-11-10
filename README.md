# Streaming Genome Sketching ASIC in 180nm CMOS

**B.Tech Capstone Project (BTP)**  
Department of Electrical Engineering, Indian Institute of Technology Jodhpur  
**Students:** K Nithin Rohit (`B23EE1030`), Vasu Kodati (`B23EE1079`)  
**Advisor:** Dr. Bhupendra Singh Reniwal  

---

## 1. Overview

This repository contains the design, verification, and physical design files for an application-specific integrated circuit (ASIC) that performs streaming genome sketching. 

Genome sketching algorithms (such as Mash and Dashing) estimate sequence similarity and mutation distance without performing computationally expensive, memory-heavy base-by-base sequence alignment. Our hardware design streams DNA sequences in real time, computes rolling canonical 21-mer hashes, and constructs a compact 256-register HyperLogLog (HLL) sketch on-chip.

The architecture is specifically tailored for the constraints of academic 180nm CMOS processes (such as SCL Mohali):
- **SRAM-free architecture:** The default academic SCL 180nm PDK lacks an SRAM compiler. The entire sketch memory is built using standard-cell D-flip-flops, requiring only 160 bytes (1,280 DFFs) of state.
- **Multiplier-free hashing:** Instead of area-heavy integer multipliers (e.g., MurmurHash), we implement a cyclic polynomial rolling hash (`ntHash-32`) using only wire rotations and XOR gates, updating the hash in a single clock cycle.
- **4-metal routing optimization:** To prevent wiring congestion during detailed routing on a 4-metal layer stack, the 256-register memory is partitioned into 4 independent banks of 64 registers each.
- **Low dynamic power:** Registers are conditionally updated only when an incoming hash rank exceeds the stored value (`write_en = kmer_valid && (rho > old_val)`). On real genomic data, over 99% of clock cycles are write-gated.

---

## 2. Hardware Architecture

```text
               DNA Base Stream (2-bit: A=00, C=01, G=10, T=11)
                                      │
                                      ▼
    ┌──────────────────────────────────────────────────────────────────┐
    │ Stage 1: 21-Base Shift Register & Warmup Counter                 │
    │ - Tracks 21-bp sliding window and handles 'N' base resets.       │
    └──────────────────────────────────────────────────────────────────┘
                                      │
                                      ▼
    ┌──────────────────────────────────────────────────────────────────┐
    │ Stage 2: Rolling Canonical ntHash-32 & Avalanche Mixer           │
    │ - Computes forward and reverse-complement 32-bit hashes in 1 cyc │
    │ - Picks canonical hash: h_canon = min(h_fwd, h_rev)              │
    │ - 3-stage XOR-shift avalanche mixer                              │
    └──────────────────────────────────────────────────────────────────┘
                                      │
                                      ▼
    ┌──────────────────────────────────────────────────────────────────┐
    │ Stage 3: Address Decoder & 24-Bit Leading Zero Detector (LZD)    │
    │ - Bank Select:  h_mixed[31:30] -> Bank 0..3                      │
    │ - Register:     h_mixed[29:24] -> Register 0..63                 │
    │ - Rank (rho):   LZC(h_mixed[23:0]) + 1 -> 5-bit value (1..25)    │
    └──────────────────────────────────────────────────────────────────┘
                                      │
                                      ▼
    ┌──────────────────────────────────────────────────────────────────┐
    │ Stage 4: 4-Bank x 64 x 5-bit HLL Register Array (1,280 DFFs)     │
    │ - Reads stored value: old_val = Bank[bank_id][sub_addr]          │
    │ - Updates only if rho > old_val (clock-gating friendly)          │
    └──────────────────────────────────────────────────────────────────┘
```

The top-level chip interface uses 22 functional pins (clock, reset, 5-pin streaming input, 13-pin host readout bus, and 2 status pins), avoiding a pad-limited die.

---

## 3. Physical Implementation Summary (180nm, 4-Metal)

A trial physical implementation flow was completed targeting a 180nm standard-cell library (`gf180mcuD`, 9-track, 5V-tolerant) strictly restricted to a 4-metal routing stack (`Metal1` to `Metal4`, `Metal5 = 0`) to mirror SCL Mohali's interconnect rules.

| Metric | Result |
| :--- | :--- |
| **Technology Node** | 180nm CMOS |
| **Routing Layers** | 4-Metal (`Metal1`–`Metal4`, `Metal5` unused) |
| **Die Dimensions / Area** | 781.76 µm × 781.76 µm (0.611 mm²) |
| **Core Area / Utilization** | 733.76 µm × 733.76 µm (0.538 mm²), ~75% density |
| **Total Standard Cells** | 5,610 synthesis cells (6,853 post-route with CTS & hold buffers) |
| **Sequential Elements** | 1,392 DFFs (112 in ntHash engine, 1,280 in HLL array; 0 SRAMs) |
| **Clock Tree (CTS)** | 4-level balanced tree (172 buffers driving 1,392 sinks) |
| **Total Wirelength / Vias** | 646.97 mm / 58,480 vias |
| **DRC Violations** | 0 violations after detailed routing |
| **Timing (Hold Slack)** | WNS: +0.726 ns across corners (0 hold violations) |
| **Max Clock Frequency** | 64.05 MHz on thick-oxide 5V library (~225 MHz projected on 1.8V thin-oxide SCL core cells) |
| **Power (SARS-CoV-2 run @ 1.8V)** | 61.80 mW with write-gating (24.1% reduction vs. ungated baseline) |

### Layout & Analysis Figures

| GDSII Layout | Floorplan & Memory Placement |
| :---: | :---: |
| ![Full-Chip GDSII](genome_sketch_asic/asic/figures/layout_full_gds.png) | ![Floorplan](genome_sketch_asic/asic/figures/floorplan_architecture_map.png) |

| Clock Tree Distribution | Design Summary Dashboard |
| :---: | :---: |
| ![CTS Topology](genome_sketch_asic/asic/figures/cts_clock_tree_map.png) | ![PPA Dashboard](genome_sketch_asic/asic/figures/ppa_and_metal_summary.png) |

---

## 4. Verification

The hardware was verified at multiple stages against real biological data from NCBI:

1. **Python Golden Model:**
   - Validated against NCBI RefSeq genomes: SARS-CoV-2 (Wuhan and Omicron BA.1), SARS-CoV-1, MERS-CoV, Ebola virus, *E. coli* K-12, pathogenic *E. coli* O157:H7, *Salmonella enterica*, and *Staphylococcus aureus*.
   - Cardinality estimation error on bacterial chromosomes remained between 1.70% and 6.46% using only 256 sketch registers.
   - Preserves strand invariance (forward and reverse-complement strands yield identical sketches).

2. **RTL & Gate-Level Simulation:**
   - Pre-synthesis and post-route gate-level simulations were checked cycle-by-cycle against traces generated by the golden model.
   - Verified over 31,968 clock cycles, including the complete 29,903-bp SARS-CoV-2 genome, with 0 mismatches.

---

## 5. Repository Structure

```text
├── README.md                                 # Project documentation
└── genome_sketch_asic/
    ├── rtl/                                  # Synthesizable Verilog-2005 RTL
    │   ├── nthash32_seeds.vh                 # Constant seed tables for k=21
    │   ├── nthash32_engine.v                 # Window register & rolling hash logic
    │   ├── lzd24.v                           # Leading-zero detector & address decoder
    │   ├── hll_banked_mem.v                  # 4-bank x 64 x 5-bit register array
    │   └── genome_sketch_top.v               # Top-level ASIC module
    ├── tb/                                   # Testbenches
    │   ├── tb_genome_sketch.v                # RTL testbench
    │   └── tb_genome_sketch_gl.v             # Gate-level testbench
    ├── golden_model/                         # Reference implementation in Python
    │   ├── nthash32.py                       # Bit-accurate ntHash-32 implementation
    │   ├── banked_hll.py                     # Banked HLL memory model
    │   ├── sketch_pipeline.py                # Full pipeline & distance calculations
    │   ├── verify_biology.py                 # Ground-truth comparison test suite
    │   └── generate_test_vectors.py          # Generates .hex stimulus and traces
    ├── data/                                 # Datasets & download scripts
    │   ├── download_datasets.py              # Fetches viral/bacterial genomes from NCBI
    │   ├── synthetic/                        # Corner-case test files
    │   ├── viral/                            # Viral FASTA records
    │   └── bacterial/                        # Bacterial FASTA records
    ├── tv/                                   # Generated test vectors for Verilog $readmemh
    ├── asic/                                 # Physical design flow files
    │   ├── config/                           # PDK and environment settings
    │   ├── constraints/                      # SDC timing constraints
    │   ├── scripts/                          # Open-source flow execution scripts
    │   ├── netlist/                          # Synthesized and routed netlists
    │   ├── def/                              # Floorplan and routed DEF/ODB files
    │   ├── spef/                             # Extracted parasitics
    │   ├── gds/                              # Final layout GDSII
    │   ├── reports/                          # Synthesis, timing, DRC, and power logs
    │   └── figures/                          # Layout and architecture plots
    └── run_rtl_sim.py                        # Simulation launcher script
```

---

## 6. How to Run

### Requirements
- Python 3.8+
- Icarus Verilog (`iverilog`) for simulation

### Simulation
```bash
cd genome_sketch_asic

# 1. Download/verify benchmark datasets (NCBI RefSeq)
python3 data/download_datasets.py

# 2. Run golden model verification suite
python3 golden_model/verify_biology.py

# 3. Compile and run RTL simulation (with cycle-by-cycle checking)
python3 run_rtl_sim.py
```

### Physical Design (OpenROAD / Yosys)
Detailed physical implementation scripts, timing/power reports, and GDSII metrics are documented in [`genome_sketch_asic/asic/physical_design_report.md`](genome_sketch_asic/asic/physical_design_report.md). To rerun the RTL-to-GDSII steps on Linux:
```bash
cd genome_sketch_asic
source asic/config/env_setup.sh
python3 asic/scripts/step2_synthesis.py
python3 asic/scripts/step3_floorplan_pdn.py
python3 asic/scripts/step4_place_cts_route.py
python3 asic/scripts/step5_sta_and_power.py
python3 asic/scripts/step6_gds_and_signoff.py
```
