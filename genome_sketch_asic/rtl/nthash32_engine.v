// ============================================================================
// Module: nthash32_engine.v
// Project: Streaming Genome Sketching ASIC (180nm CMOS)
//
// Description:
//   Multiplier-free 32-bit Rolling Canonical ntHash Engine for k = 21 DNA k-mers.
//   - 21-base sliding-window shift register (42 DFFs) + 5-bit warm-up counter.
//   - Dual rolling polynomial hash datapaths (Forward & Reverse-Complement).
//   - Canonical comparator min(h_fwd, h_rev) and 3-stage XOR-shift avalanche mixer.
// ============================================================================

`timescale 1ns / 1ps

module nthash32_engine (
    input  wire        clk,
    input  wire        rst_n,         // Active-low asynchronous/synchronous reset
    input  wire        clear_sketch,  // Synchronous full reset
    input  wire        clear_window,  // Synchronous window reset ('N' base or contig break)
    input  wire        valid_in,      // 1 = valid nucleotide base on base_in[1:0]
    input  wire [1:0]  base_in,       // 2'b00=A, 2'b01=C, 2'b10=G, 2'b11=T

    output wire        kmer_valid,    // 1 when window holds 21 contiguous valid bases
    output wire [4:0]  valid_count,   // Current warm-up count (0..21)
    output wire [31:0] h_fwd,         // Rolling forward 32-bit hash register
    output wire [31:0] h_rev,         // Rolling reverse-complement 32-bit hash register
    output wire [31:0] h_canon,       // Canonical hash = min(h_fwd, h_rev) (0 if invalid)
    output wire [31:0] h_mixed        // Avalanche-mixed canonical hash (0 if invalid)
);

    // Include auto-generated hardwired 32-bit seed constants for k = 21
    `include "nthash32_seeds.vh"

    // ========================================================================
    // 1. Sequential State Registers (42 + 5 + 32 + 32 + 1 = 112 DFFs total)
    // ========================================================================
    reg [41:0] shift_reg;       // 21 bases x 2 bits: [1:0] = newest, [41:40] = oldest (b_out)
    reg [4:0]  valid_cnt_reg;   // Saturation counter: 0 to 21 (5'd21)
    reg [31:0] h_fwd_reg;       // Rolling forward ntHash-32 state
    reg [31:0] h_rev_reg;       // Rolling reverse-complement ntHash-32 state
    reg        step_active_reg; // Tracks whether the latest cycle had an active base step

    // Oldest base leaving the 21-mer sliding window
    wire [1:0] b_out = shift_reg[41:40];
    wire       window_was_full = (valid_cnt_reg == 5'd21);

    // ========================================================================
    // 2. Hardwired Constant Seed Lookups (4-to-1 Muxes -> Pure Logic Gates)
    // ========================================================================
    reg [31:0] lut_seed_in;
    reg [31:0] lut_seed_rc_km1_in;
    reg [31:0] lut_seed_k_out;
    reg [31:0] lut_seed_rc_ror1_out;

    always @(*) begin
        case (base_in)
            2'b00: begin
                lut_seed_in        = SEED_A;
                lut_seed_rc_km1_in = SEED_RC_KM1_A;
            end
            2'b01: begin
                lut_seed_in        = SEED_C;
                lut_seed_rc_km1_in = SEED_RC_KM1_C;
            end
            2'b10: begin
                lut_seed_in        = SEED_G;
                lut_seed_rc_km1_in = SEED_RC_KM1_G;
            end
            2'b11: begin
                lut_seed_in        = SEED_T;
                lut_seed_rc_km1_in = SEED_RC_KM1_T;
            end
            default: begin
                lut_seed_in        = 32'd0;
                lut_seed_rc_km1_in = 32'd0;
            end
        endcase
    end

    always @(*) begin
        case (b_out)
            2'b00: begin
                lut_seed_k_out       = SEED_K_A;
                lut_seed_rc_ror1_out = SEED_RC_ROR1_A;
            end
            2'b01: begin
                lut_seed_k_out       = SEED_K_C;
                lut_seed_rc_ror1_out = SEED_RC_ROR1_C;
            end
            2'b10: begin
                lut_seed_k_out       = SEED_K_G;
                lut_seed_rc_ror1_out = SEED_RC_ROR1_G;
            end
            2'b11: begin
                lut_seed_k_out       = SEED_K_T;
                lut_seed_rc_ror1_out = SEED_RC_ROR1_T;
            end
            default: begin
                lut_seed_k_out       = 32'd0;
                lut_seed_rc_ror1_out = 32'd0;
            end
        endcase
    end

    // Gate off exiting base contribution during the 21-cycle warm-up window
    wire [31:0] out_fwd_term = window_was_full ? lut_seed_k_out       : 32'd0;
    wire [31:0] out_rev_term = window_was_full ? lut_seed_rc_ror1_out : 32'd0;

    // ========================================================================
    // 3. 1-Cycle Rolling Hash Combinational Datapath (Wire Rotations + XOR)
    // ========================================================================
    wire [31:0] rol1_h_fwd = {h_fwd_reg[30:0], h_fwd_reg[31]};
    wire [31:0] ror1_h_rev = {h_rev_reg[0],    h_rev_reg[31:1]};

    wire [31:0] next_h_fwd = rol1_h_fwd ^ out_fwd_term ^ lut_seed_in;
    wire [31:0] next_h_rev = ror1_h_rev ^ out_rev_term ^ lut_seed_rc_km1_in;

    // ========================================================================
    // 4. Sequential Register Update
    // ========================================================================
    always @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            shift_reg       <= 42'd0;
            valid_cnt_reg   <= 5'd0;
            h_fwd_reg       <= 32'd0;
            h_rev_reg       <= 32'd0;
            step_active_reg <= 1'b0;
        end else if (clear_sketch || clear_window) begin
            shift_reg       <= 42'd0;
            valid_cnt_reg   <= 5'd0;
            h_fwd_reg       <= 32'd0;
            h_rev_reg       <= 32'd0;
            step_active_reg <= 1'b0;
        end else if (valid_in) begin
            shift_reg       <= {shift_reg[39:0], base_in};
            valid_cnt_reg   <= (valid_cnt_reg < 5'd21) ? (valid_cnt_reg + 5'd1) : 5'd21;
            h_fwd_reg       <= next_h_fwd;
            h_rev_reg       <= next_h_rev;
            step_active_reg <= 1'b1;
        end else begin
            step_active_reg <= 1'b0;
        end
    end

    // ========================================================================
    // 5. Canonical Selection & 3-Stage XOR-Shift Avalanche Mixer
    // ========================================================================
    wire        window_full_now = (valid_cnt_reg == 5'd21) && step_active_reg;
    wire [31:0] h_canon_raw     = (h_fwd_reg <= h_rev_reg) ? h_fwd_reg : h_rev_reg;

    // Multiplier-free 32-bit avalanche mixer:
    //   h ^= (h >> 16); h ^= (h << 7); h ^= (h >> 11);
    wire [31:0] mix_s1 = h_canon_raw ^ {16'd0, h_canon_raw[31:16]};
    wire [31:0] mix_s2 = mix_s1      ^ {mix_s1[24:0], 7'd0};
    wire [31:0] mix_s3 = mix_s2      ^ {11'd0, mix_s2[31:11]};

    assign kmer_valid  = window_full_now;
    assign valid_count = valid_cnt_reg;
    assign h_fwd       = h_fwd_reg;
    assign h_rev       = h_rev_reg;
    assign h_canon     = window_full_now ? h_canon_raw : 32'd0;
    assign h_mixed     = window_full_now ? mix_s3      : 32'd0;

endmodule
