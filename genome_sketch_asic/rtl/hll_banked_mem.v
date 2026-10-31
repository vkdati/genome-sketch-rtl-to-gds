// ============================================================================
// Module: hll_banked_mem.v (Phase B - Step 3: Stage 4 Banked HLL DFF Memory)
// Project: SCL 180nm Streaming Genome Sketching ASIC (genome-sketch-rtl-to-gds)
//
// Description:
//   Synthesizable, SRAM-less 256 x 5-bit HyperLogLog (HLL) Register File
//   implemented using standard D-Flip-Flops (1,280 DFFs total = 160 bytes)
//   and partitioned into 4 independent banks of 64 registers each.
//
// SCL 180nm Physical Design Optimizations:
//   1. No SRAM Compiler Required: Fits in < 0.1 mm^2 of standard-cell logic.
//   2. 4-Bank Partitioning (4 x 64 x 5-bit): Replaces a congested 256-to-1
//      global multiplexer crossbar with four local 64-to-1 bank muxes + a
//      4-to-1 bank selector, ensuring clean routing on the 4-Metal (4M) stack.
//   3. Ultra-Low-Power Write Gating: Flip-flops update ONLY when
//      `kmer_valid && (rho > old_val)`. Over 99.95% of clock cycles on
//      bacterial genomes are write-gated, enabling Cadence Genus to insert
//      Integrated Clock Gating (ICG) cells per bank/register.
//   4. Narrow Host Readout Port: Provides an indexed 8-bit `read_addr[7:0]`
//      to 5-bit `read_data[4:0]` readout port to avoid pad limitation.
// ============================================================================

`timescale 1ns / 1ps

module hll_banked_mem (
    input  wire       clk,
    input  wire       rst_n,         // Active-low reset
    input  wire       clear_sketch,  // Synchronous clear of all 256 HLL registers

    // Stage 3 Pipeline Inputs
    input  wire       kmer_valid,    // 1 when incoming hash/rank is valid
    input  wire [1:0] bank_id,       // 2-bit Bank select (0..3)
    input  wire [5:0] sub_addr,      // 6-bit Intra-bank register address (0..63)
    input  wire [4:0] rho,           // 5-bit Leading-zero rank (1..25)

    // Cycle-Accurate Trace / Status Outputs
    output wire       write_en,      // 1 when kmer_valid && (rho > old_val)
    output wire [4:0] old_val,       // Current 5-bit value at Bank[bank_id][sub_addr]
    output wire [4:0] new_val,       // Updated 5-bit value = max(old_val, rho)

    // Narrow Host Readout Port (for serial/indexed readout after streaming)
    input  wire [7:0] read_addr,     // {rd_bank[1:0], rd_offset[5:0]} (0..255)
    output reg  [4:0] read_data      // 5-bit HLL register value at read_addr
);

    // ========================================================================
    // 1. Four Independent 64 x 5-bit Standard-Cell DFF Banks (1,280 DFFs)
    // ========================================================================
    reg [4:0] bank0 [0:63];
    reg [4:0] bank1 [0:63];
    reg [4:0] bank2 [0:63];
    reg [4:0] bank3 [0:63];

    // ========================================================================
    // 2. Per-Bank 64-to-1 Local Read Multiplexers & 4-to-1 Bank Selector
    // ========================================================================
    wire [4:0] rd_b0 = bank0[sub_addr];
    wire [4:0] rd_b1 = bank1[sub_addr];
    wire [4:0] rd_b2 = bank2[sub_addr];
    wire [4:0] rd_b3 = bank3[sub_addr];

    reg [4:0] selected_old_val;
    always @(*) begin
        case (bank_id)
            2'b00:   selected_old_val = rd_b0;
            2'b01:   selected_old_val = rd_b1;
            2'b10:   selected_old_val = rd_b2;
            2'b11:   selected_old_val = rd_b3;
            default: selected_old_val = 5'd0;
        endcase
    end

    // ========================================================================
    // 3. Conditional Max-Update Comparator & Bank Write-Enable Gating
    // ========================================================================
    wire do_write = kmer_valid && (rho > selected_old_val);

    wire we_bank0 = do_write && (bank_id == 2'b00);
    wire we_bank1 = do_write && (bank_id == 2'b01);
    wire we_bank2 = do_write && (bank_id == 2'b10);
    wire we_bank3 = do_write && (bank_id == 2'b11);

    assign write_en = do_write;
    assign old_val  = kmer_valid ? selected_old_val : 5'd0;
    assign new_val  = kmer_valid ? (do_write ? rho : selected_old_val) : 5'd0;

    // ========================================================================
    // 4. Synchronous Banked Register Update (Clock-Gating Friendly)
    // ========================================================================
    integer i;
    always @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            for (i = 0; i < 64; i = i + 1) begin
                bank0[i] <= 5'd0;
                bank1[i] <= 5'd0;
                bank2[i] <= 5'd0;
                bank3[i] <= 5'd0;
            end
        end else if (clear_sketch) begin
            for (i = 0; i < 64; i = i + 1) begin
                bank0[i] <= 5'd0;
                bank1[i] <= 5'd0;
                bank2[i] <= 5'd0;
                bank3[i] <= 5'd0;
            end
        end else begin
            if (we_bank0) bank0[sub_addr] <= rho;
            if (we_bank1) bank1[sub_addr] <= rho;
            if (we_bank2) bank2[sub_addr] <= rho;
            if (we_bank3) bank3[sub_addr] <= rho;
        end
    end

    // ========================================================================
    // 5. Host Readout Multiplexer (read_addr[7:0] -> read_data[4:0])
    // ========================================================================
    wire [1:0] host_bank_sel = read_addr[7:6];
    wire [5:0] host_sub_addr = read_addr[5:0];

    always @(*) begin
        case (host_bank_sel)
            2'b00:   read_data = bank0[host_sub_addr];
            2'b01:   read_data = bank1[host_sub_addr];
            2'b10:   read_data = bank2[host_sub_addr];
            2'b11:   read_data = bank3[host_sub_addr];
            default: read_data = 5'd0;
        endcase
    end

endmodule
