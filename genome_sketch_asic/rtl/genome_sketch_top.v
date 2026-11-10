// ============================================================================
// Module: genome_sketch_top.v
// Project: Streaming Genome Sketching ASIC (180nm CMOS)
//
// Description:
//   Top-level wrapper integrating nthash32_engine, lzd24, and hll_banked_mem
//   with a 22-pin interface (clk, rst_n, 5-bit stream in, 13-bit readout, 2 status).
// ============================================================================

`timescale 1ns / 1ps

module genome_sketch_top (
    // Clock and Active-Low Reset (2 pins)
    input  wire       clk,
    input  wire       rst_n,

    // Streaming DNA Input Interface (5 pins)
    input  wire       clear_sketch,  // 1 = Synchronous clear of HLL registers & window
    input  wire       clear_window,  // 1 = Ambiguous 'N' base or contig break (resets window)
    input  wire       valid_in,      // 1 = Valid nucleotide base present on base_in[1:0]
    input  wire [1:0] base_in,       // 2'b00=A, 2'b01=C, 2'b10=G, 2'b11=T

    // Host Sketch Readout Interface (13 pins)
    input  wire [7:0] read_addr,     // Register address 0..255 ({bank_id[1:0], sub_addr[5:0]})
    output wire [4:0] read_data,     // 5-bit HLL register value (0..25)

    // Pipeline Activity Status Outputs (2 pins)
    output wire       kmer_valid,    // 1 when 21 contiguous valid bases are in window
    output wire       write_en       // 1 when HLL register is updated (rho > old_val)
);

    // ========================================================================
    // Internal Inter-Stage Pipeline Nets (Probed by Self-Checking Testbench)
    // ========================================================================
    wire [4:0]  w_valid_count;
    wire [31:0] w_h_fwd;
    wire [31:0] w_h_rev;
    wire [31:0] w_h_canon;
    wire [31:0] w_h_mixed;

    wire [1:0]  w_bank_id;
    wire [5:0]  w_sub_addr;
    wire [7:0]  w_flat_idx;
    wire [4:0]  w_rho;

    wire [4:0]  w_old_val;
    wire [4:0]  w_new_val;

    // ========================================================================
    // Stage 1 & 2: 21-bp Sliding Window & Rolling Canonical ntHash-32 Engine
    // ========================================================================
    nthash32_engine u_nthash32 (
        .clk          (clk),
        .rst_n        (rst_n),
        .clear_sketch (clear_sketch),
        .clear_window (clear_window),
        .valid_in     (valid_in),
        .base_in      (base_in),
        .kmer_valid   (kmer_valid),
        .valid_count  (w_valid_count),
        .h_fwd        (w_h_fwd),
        .h_rev        (w_h_rev),
        .h_canon      (w_h_canon),
        .h_mixed      (w_h_mixed)
    );

    // ========================================================================
    // Stage 3: Address Decoder & 24-Bit Leading-Zero Detector (LZD24)
    // ========================================================================
    lzd24 u_lzd24 (
        .kmer_valid   (kmer_valid),
        .h_mixed      (w_h_mixed),
        .bank_id      (w_bank_id),
        .sub_addr     (w_sub_addr),
        .flat_idx     (w_flat_idx),
        .rho          (w_rho)
    );

    // ========================================================================
    // Stage 4: 4-Bank x 64-Reg x 5-Bit Standard-Cell DFF HLL Memory
    // ========================================================================
    hll_banked_mem u_hll_mem (
        .clk          (clk),
        .rst_n        (rst_n),
        .clear_sketch (clear_sketch),
        .kmer_valid   (kmer_valid),
        .bank_id      (w_bank_id),
        .sub_addr     (w_sub_addr),
        .rho          (w_rho),
        .write_en     (write_en),
        .old_val      (w_old_val),
        .new_val      (w_new_val),
        .read_addr    (read_addr),
        .read_data    (read_data)
    );

endmodule
