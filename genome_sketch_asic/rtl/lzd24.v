// ============================================================================
// Module: lzd24.v (Phase B - Step 2: Stage 3 Address Decode & 24-Bit LZD)
// Project: SCL 180nm Streaming Genome Sketching ASIC (genome-sketch-rtl-to-gds)
//
// Description:
//   Purely combinational Stage 3 decoder that extracts the HLL bank/register
//   address from the upper 8 bits of `h_mixed[31:0]` and computes the 5-bit
//   HyperLogLog geometric rank `rho` (1..25) from the lower 24 bits
//   `h_mixed[23:0]` via a 24-bit Leading-Zero Detector + 1 (LZD24).
//
// Bit-Field Mapping (matching golden_model/banked_hll.py):
//   - bank_id[1:0]  = h_mixed[31:30] (selects Bank 0..3)
//   - sub_addr[5:0] = h_mixed[29:24] (selects Register 0..63 within Bank)
//   - flat_idx[7:0] = h_mixed[31:24] ({bank_id, sub_addr}, 0..255)
//   - rho[4:0]      = LZC(h_mixed[23:0]) + 1  (5-bit unsigned in 1..25)
// ============================================================================

`timescale 1ns / 1ps

module lzd24 (
    input  wire        kmer_valid, // 1 when h_mixed holds a valid 21-mer hash
    input  wire [31:0] h_mixed,    // 32-bit avalanche-mixed canonical hash

    output wire [1:0]  bank_id,    // 2-bit Bank select (0..3)
    output wire [5:0]  sub_addr,   // 6-bit Intra-bank register offset (0..63)
    output wire [7:0]  flat_idx,   // 8-bit Linear register index (0..255)
    output wire [4:0]  rho         // 5-bit Leading-zero rank (1..25, or 0 if !kmer_valid)
);

    wire [23:0] w = h_mixed[23:0];
    reg  [4:0]  lzd_raw;

    // Synthesizable 24-bit Priority Encoder (MSB bit 23 down to LSB bit 0)
    always @(*) begin
        casez (w)
            24'b1???_????_????_????_????_????: lzd_raw = 5'd1;
            24'b01??_????_????_????_????_????: lzd_raw = 5'd2;
            24'b001?_????_????_????_????_????: lzd_raw = 5'd3;
            24'b0001_????_????_????_????_????: lzd_raw = 5'd4;
            24'b0000_1???_????_????_????_????: lzd_raw = 5'd5;
            24'b0000_01??_????_????_????_????: lzd_raw = 5'd6;
            24'b0000_001?_????_????_????_????: lzd_raw = 5'd7;
            24'b0000_0001_????_????_????_????: lzd_raw = 5'd8;
            24'b0000_0000_1???_????_????_????: lzd_raw = 5'd9;
            24'b0000_0000_01??_????_????_????: lzd_raw = 5'd10;
            24'b0000_0000_001?_????_????_????: lzd_raw = 5'd11;
            24'b0000_0000_0001_????_????_????: lzd_raw = 5'd12;
            24'b0000_0000_0000_1???_????_????: lzd_raw = 5'd13;
            24'b0000_0000_0000_01??_????_????: lzd_raw = 5'd14;
            24'b0000_0000_0000_001?_????_????: lzd_raw = 5'd15;
            24'b0000_0000_0000_0001_????_????: lzd_raw = 5'd16;
            24'b0000_0000_0000_0000_1???_????: lzd_raw = 5'd17;
            24'b0000_0000_0000_0000_01??_????: lzd_raw = 5'd18;
            24'b0000_0000_0000_0000_001?_????: lzd_raw = 5'd19;
            24'b0000_0000_0000_0000_0001_????: lzd_raw = 5'd20;
            24'b0000_0000_0000_0000_0000_1???: lzd_raw = 5'd21;
            24'b0000_0000_0000_0000_0000_01??: lzd_raw = 5'd22;
            24'b0000_0000_0000_0000_0000_001?: lzd_raw = 5'd23;
            24'b0000_0000_0000_0000_0000_0001: lzd_raw = 5'd24;
            default:                           lzd_raw = 5'd25; // All 24 bits are 0
        endcase
    end

    assign bank_id  = kmer_valid ? h_mixed[31:30] : 2'd0;
    assign sub_addr = kmer_valid ? h_mixed[29:24] : 6'd0;
    assign flat_idx = kmer_valid ? h_mixed[31:24] : 8'd0;
    assign rho      = kmer_valid ? lzd_raw        : 5'd0;

endmodule
