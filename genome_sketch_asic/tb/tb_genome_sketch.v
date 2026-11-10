// ============================================================================
// Testbench: tb_genome_sketch.v
// Project: Streaming Genome Sketching ASIC (180nm CMOS)
//
// Description:
//   RTL testbench for `genome_sketch_top`. Compares internal pipeline signals
//   and final 256-register HLL sketches against golden vectors across synthetic
//   and SARS-CoV-2 test sequences.
// ============================================================================

`timescale 1ns / 1ps

module tb_genome_sketch;

    // ========================================================================
    // 1. Clock (200 MHz -> 5.0 ns period) & DUT Signals
    // ========================================================================
    reg        clk;
    reg        rst_n;
    reg        clear_sketch;
    reg        clear_window;
    reg        valid_in;
    reg  [1:0] base_in;
    reg  [7:0] read_addr;

    wire [4:0] read_data;
    wire       kmer_valid;
    wire       write_en;

    initial clk = 1'b0;
    always #2.5 clk = ~clk; // 200 MHz clock

    // ========================================================================
    // 2. Instantiate Top-Level ASIC Under Test (DUT)
    // ========================================================================
    genome_sketch_top dut (
        .clk          (clk),
        .rst_n        (rst_n),
        .clear_sketch (clear_sketch),
        .clear_window (clear_window),
        .valid_in     (valid_in),
        .base_in      (base_in),
        .read_addr    (read_addr),
        .read_data    (read_data),
        .kmer_valid   (kmer_valid),
        .write_en     (write_en)
    );

    // ========================================================================
    // 3. Test Vector Memories for Suite 1 (2,065 cycles) & Suite 2 (29,903 cycles)
    // ========================================================================
    localparam integer REG_CYCLES  = 2065;
    localparam integer SARS_CYCLES = 29903;
    localparam integer NUM_REGS    = 256;

    reg [7:0]   reg_stim_mem    [0:REG_CYCLES-1];
    reg [127:0] reg_trace_mem   [0:REG_CYCLES-1];
    reg [7:0]   reg_sketch_mem  [0:NUM_REGS-1];

    reg [7:0]   sars_stim_mem   [0:SARS_CYCLES-1];
    reg [127:0] sars_trace_mem  [0:SARS_CYCLES-1];
    reg [7:0]   sars_sketch_mem [0:NUM_REGS-1];

    // Unpacked expected fields for current cycle
    reg [31:0] exp_h_fwd;
    reg [31:0] exp_h_rev;
    reg [31:0] exp_h_mixed;
    reg        exp_kmer_valid;
    reg        exp_write_en;
    reg [7:0]  exp_flat_idx;
    reg [4:0]  exp_rho;
    reg [4:0]  exp_new_val;

    integer cyc;
    integer idx;
    integer trace_errors;
    integer sketch_errors;
    integer total_errors;

    // ========================================================================
    // 4. Helper Task: Unpack 128-bit Expected Trace Word & Compare to DUT
    // ========================================================================
    task check_cycle_trace;
        input [127:0] trace_word;
        input integer cycle_num;
        input [127:0] suite_name;
        begin
            exp_h_fwd      = trace_word[127:96];
            exp_h_rev      = trace_word[95:64];
            exp_h_mixed    = trace_word[63:32];
            exp_kmer_valid = trace_word[28];
            exp_write_en   = trace_word[24];
            exp_flat_idx   = trace_word[23:16];
            exp_rho        = trace_word[12:8];
            exp_new_val    = trace_word[4:0];

            if (dut.w_h_fwd      !== exp_h_fwd      ||
                dut.w_h_rev      !== exp_h_rev      ||
                dut.w_h_mixed    !== exp_h_mixed    ||
                dut.kmer_valid   !== exp_kmer_valid ||
                dut.write_en     !== exp_write_en   ||
                dut.w_flat_idx   !== exp_flat_idx   ||
                dut.w_rho        !== exp_rho        ||
                dut.w_new_val    !== exp_new_val) begin

                trace_errors = trace_errors + 1;
                if (trace_errors <= 10) begin
                    $display("[ERROR] Cycle %0d mismatch!", cycle_num);
                    $display("  Expected: h_fwd=%08h h_rev=%08h h_mix=%08h kv=%b we=%b idx=%02h rho=%02h new=%02h",
                             exp_h_fwd, exp_h_rev, exp_h_mixed, exp_kmer_valid,
                             exp_write_en, exp_flat_idx, exp_rho, exp_new_val);
                    $display("  Observed: h_fwd=%08h h_rev=%08h h_mix=%08h kv=%b we=%b idx=%02h rho=%02h new=%02h",
                             dut.w_h_fwd, dut.w_h_rev, dut.w_h_mixed, dut.kmer_valid,
                             dut.write_en, dut.w_flat_idx, dut.w_rho, dut.w_new_val);
                end
            end
        end
    endtask

    // ========================================================================
    // 5. Main Verification Sequence
    // ========================================================================
    initial begin
        `ifdef DUMP_VCD
            $dumpfile("genome_sketch_tb.vcd");
            $dumpvars(0, tb_genome_sketch);
        `endif

        // Load all .hex test vectors generated by Python Golden Model
        $readmemh("tv/stimulus_dna.hex",              reg_stim_mem);
        $readmemh("tv/expected_trace.hex",            reg_trace_mem);
        $readmemh("tv/expected_sketch.hex",           reg_sketch_mem);

        $readmemh("tv/sars_cov_2_stimulus.hex",       sars_stim_mem);
        $readmemh("tv/sars_cov_2_expected_trace.hex", sars_trace_mem);
        $readmemh("tv/sars_cov_2_expected_sketch.hex",sars_sketch_mem);

        total_errors = 0;

        // --------------------------------------------------------------------
        // SUITE 1: Corner-Case Regression (2,065 Clock Cycles)
        // --------------------------------------------------------------------
        $display("============================================================================");
        $display("[SUITE 1] Running Corner-Case Regression Suite (%0d cycles)...", REG_CYCLES);
        $display("============================================================================");

        rst_n        = 1'b0;
        clear_sketch = 1'b0;
        clear_window = 1'b0;
        valid_in     = 1'b0;
        base_in      = 2'b00;
        read_addr    = 8'd0;
        trace_errors = 0;
        sketch_errors = 0;

        repeat (3) @(negedge clk);
        rst_n = 1'b1;

        for (cyc = 0; cyc < REG_CYCLES; cyc = cyc + 1) begin
            // Drive stimulus on negedge clk
            clear_sketch = reg_stim_mem[cyc][4];
            clear_window = reg_stim_mem[cyc][3];
            valid_in     = reg_stim_mem[cyc][2];
            base_in      = reg_stim_mem[cyc][1:0];

            // Sample & verify after posedge clk
            @(posedge clk);
            #1;
            check_cycle_trace(reg_trace_mem[cyc], cyc + 1, "REGRESSION");
            @(negedge clk);
        end

        // 1 idle clock cycle to commit the final cycle's HLL register write
        clear_sketch = 1'b0;
        clear_window = 1'b0;
        valid_in     = 1'b0;
        base_in      = 2'b00;
        @(posedge clk);
        #1;

        // Read out all 256 HLL registers via the narrow read_addr[7:0] port
        for (idx = 0; idx < NUM_REGS; idx = idx + 1) begin
            read_addr = idx[7:0];
            #1;
            if (read_data !== reg_sketch_mem[idx][4:0]) begin
                sketch_errors = sketch_errors + 1;
                $display("[ERROR] Suite 1 HLL Reg[%0d] mismatch: exp=%02h, got=%02h",
                         idx, reg_sketch_mem[idx][4:0], read_data);
            end
        end

        $display("  -> Cycle Trace Checks : %0d / %0d matched (Errors: %0d)",
                 REG_CYCLES - trace_errors, REG_CYCLES, trace_errors);
        $display("  -> HLL Sketch Readout : %0d / %0d registers matched (Errors: %0d)",
                 NUM_REGS - sketch_errors, NUM_REGS, sketch_errors);
        total_errors = total_errors + trace_errors + sketch_errors;

        // --------------------------------------------------------------------
        // SUITE 2: Full SARS-CoV-2 Viral Genome (29,903 Clock Cycles)
        // --------------------------------------------------------------------
        $display("============================================================================");
        $display("[SUITE 2] Running Full SARS-CoV-2 RefSeq Genome (%0d cycles)...", SARS_CYCLES);
        $display("============================================================================");

        // Pulse synchronous clear_sketch for 1 cycle to clear HLL registers
        @(negedge clk);
        clear_sketch = 1'b1;
        @(posedge clk);
        #1;
        @(negedge clk);
        clear_sketch = 1'b0;

        trace_errors  = 0;
        sketch_errors = 0;

        for (cyc = 0; cyc < SARS_CYCLES; cyc = cyc + 1) begin
            clear_sketch = sars_stim_mem[cyc][4];
            clear_window = sars_stim_mem[cyc][3];
            valid_in     = sars_stim_mem[cyc][2];
            base_in      = sars_stim_mem[cyc][1:0];

            @(posedge clk);
            #1;
            check_cycle_trace(sars_trace_mem[cyc], cyc + 1, "SARS_COV_2");
            @(negedge clk);
        end

        // 1 idle clock cycle to commit final HLL register write
        clear_sketch = 1'b0;
        clear_window = 1'b0;
        valid_in     = 1'b0;
        base_in      = 2'b00;
        @(posedge clk);
        #1;

        for (idx = 0; idx < NUM_REGS; idx = idx + 1) begin
            read_addr = idx[7:0];
            #1;
            if (read_data !== sars_sketch_mem[idx][4:0]) begin
                sketch_errors = sketch_errors + 1;
                $display("[ERROR] Suite 2 HLL Reg[%0d] mismatch: exp=%02h, got=%02h",
                         idx, sars_sketch_mem[idx][4:0], read_data);
            end
        end

        $display("  -> Cycle Trace Checks : %0d / %0d matched (Errors: %0d)",
                 SARS_CYCLES - trace_errors, SARS_CYCLES, trace_errors);
        $display("  -> HLL Sketch Readout : %0d / %0d registers matched (Errors: %0d)",
                 NUM_REGS - sketch_errors, NUM_REGS, sketch_errors);
        total_errors = total_errors + trace_errors + sketch_errors;

        // --------------------------------------------------------------------
        // Final Summary
        // --------------------------------------------------------------------
        $display("============================================================================");
        if (total_errors == 0) begin
            $display("[PASS] ALL RTL SIMULATIONS PASSED (31,968 / 31,968 cycles & 512 / 512 HLL regs 100%% bit-accurate!)");
        end else begin
            $display("[FAIL] RTL Simulation completed with %0d total errors.", total_errors);
        end
        $display("============================================================================");
        $finish;
    end

endmodule
