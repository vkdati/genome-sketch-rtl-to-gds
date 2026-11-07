// ============================================================================
// Testbench: tb_genome_sketch_gl.v (Phase C - Step 2 & Step 5: Gate-Level TB)
// Project: SCL 180nm Streaming Genome Sketching ASIC (genome-sketch-rtl-to-gds)
//
// Description:
//   Self-checking Post-Synthesis & Post-Layout Gate-Level Netlist Testbench
//   for `genome_sketch_top`. Uses strictly the 22 external ASIC pins:
//     - Verifies `kmer_valid` and `write_en` on EVERY cycle across 31,968
//       cycles (2,065-cycle Corner-Case Suite + 29,903-cycle SARS-CoV-2).
//     - Verifies all 256 x 5-bit HLL registers after Suite 1 and Suite 2
//       (512 / 512 registers total) via `read_addr[7:0] -> read_data[4:0]`.
//     - Optionally dumps VCD switching activity (`-DDUMP_GL_VCD`) on the
//       synthesized/routed gate-level netlist for OpenSTA power signoff.
// ============================================================================

`timescale 1ns / 1ps

module tb_genome_sketch_gl;

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
    always #2.5 clk = ~clk; // 200.0 MHz (5.0 ns period)

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

    localparam integer REG_CYCLES  = 2065;
    localparam integer SARS_CYCLES = 29903;
    localparam integer NUM_REGS    = 256;

    reg [7:0]   reg_stim_mem    [0:REG_CYCLES-1];
    reg [127:0] reg_trace_mem   [0:REG_CYCLES-1];
    reg [7:0]   reg_sketch_mem  [0:NUM_REGS-1];

    reg [7:0]   sars_stim_mem   [0:SARS_CYCLES-1];
    reg [127:0] sars_trace_mem  [0:SARS_CYCLES-1];
    reg [7:0]   sars_sketch_mem [0:NUM_REGS-1];

    reg        exp_kmer_valid;
    reg        exp_write_en;

    integer cyc;
    integer idx;
    integer trace_errors;
    integer sketch_errors;
    integer total_errors;

    task check_gl_pins;
        input [127:0] trace_word;
        input integer cycle_num;
        begin
            exp_kmer_valid = trace_word[28];
            exp_write_en   = trace_word[24];

            if (kmer_valid !== exp_kmer_valid || write_en !== exp_write_en) begin
                trace_errors = trace_errors + 1;
                if (trace_errors <= 10) begin
                    $display("[GL ERROR] Cycle %0d pin mismatch! Expected kv=%b we=%b | Got kv=%b we=%b",
                             cycle_num, exp_kmer_valid, exp_write_en, kmer_valid, write_en);
                end
            end
        end
    endtask

    initial begin
        $readmemh("tv/stimulus_dna.hex",               reg_stim_mem);
        $readmemh("tv/expected_trace.hex",             reg_trace_mem);
        $readmemh("tv/expected_sketch.hex",            reg_sketch_mem);

        $readmemh("tv/sars_cov_2_stimulus.hex",        sars_stim_mem);
        $readmemh("tv/sars_cov_2_expected_trace.hex",  sars_trace_mem);
        $readmemh("tv/sars_cov_2_expected_sketch.hex", sars_sketch_mem);

        total_errors = 0;

        // --------------------------------------------------------------------
        // SUITE 1: Corner-Case Regression (2,065 Clock Cycles)
        // --------------------------------------------------------------------
        rst_n         = 1'b0;
        clear_sketch  = 1'b0;
        clear_window  = 1'b0;
        valid_in      = 1'b0;
        base_in       = 2'b00;
        read_addr     = 8'd0;
        trace_errors  = 0;
        sketch_errors = 0;

        repeat (3) @(negedge clk);
        rst_n = 1'b1;

        for (cyc = 0; cyc < REG_CYCLES; cyc = cyc + 1) begin
            clear_sketch = reg_stim_mem[cyc][4];
            clear_window = reg_stim_mem[cyc][3];
            valid_in     = reg_stim_mem[cyc][2];
            base_in      = reg_stim_mem[cyc][1:0];

            @(posedge clk);
            #1;
            check_gl_pins(reg_trace_mem[cyc], cyc + 1);
            @(negedge clk);
        end

        clear_sketch = 1'b0;
        clear_window = 1'b0;
        valid_in     = 1'b0;
        base_in      = 2'b00;
        @(posedge clk);
        #1;

        for (idx = 0; idx < NUM_REGS; idx = idx + 1) begin
            read_addr = idx[7:0];
            #1;
            if (read_data !== reg_sketch_mem[idx][4:0]) begin
                sketch_errors = sketch_errors + 1;
                $display("[GL ERROR] Suite 1 HLL Reg[%0d] mismatch: exp=%02h, got=%02h",
                         idx, reg_sketch_mem[idx][4:0], read_data);
            end
        end

        $display("  [GL SUITE 1] Pin Trace: %0d/%0d | HLL Regs: %0d/%0d (Errors: %0d)",
                 REG_CYCLES - trace_errors, REG_CYCLES,
                 NUM_REGS - sketch_errors, NUM_REGS,
                 trace_errors + sketch_errors);
        total_errors = total_errors + trace_errors + sketch_errors;

        // --------------------------------------------------------------------
        // SUITE 2: Full SARS-CoV-2 Viral Genome (29,903 Clock Cycles)
        // --------------------------------------------------------------------
        @(negedge clk);
        clear_sketch = 1'b1;
        @(posedge clk);
        #1;
        @(negedge clk);
        clear_sketch = 1'b0;

        `ifdef DUMP_GL_VCD
            $dumpfile("asic/reports/sars_cov_2_gl.vcd");
            $dumpvars(0, tb_genome_sketch_gl.dut);
        `endif

        trace_errors  = 0;
        sketch_errors = 0;

        for (cyc = 0; cyc < SARS_CYCLES; cyc = cyc + 1) begin
            clear_sketch = sars_stim_mem[cyc][4];
            clear_window = sars_stim_mem[cyc][3];
            valid_in     = sars_stim_mem[cyc][2];
            base_in      = sars_stim_mem[cyc][1:0];

            @(posedge clk);
            #1;
            check_gl_pins(sars_trace_mem[cyc], cyc + 1);
            @(negedge clk);
        end

        clear_sketch = 1'b0;
        clear_window = 1'b0;
        valid_in     = 1'b0;
        base_in      = 2'b00;
        @(posedge clk);
        #1;

        `ifdef DUMP_GL_VCD
            $dumpoff;
        `endif

        for (idx = 0; idx < NUM_REGS; idx = idx + 1) begin
            read_addr = idx[7:0];
            #1;
            if (read_data !== sars_sketch_mem[idx][4:0]) begin
                sketch_errors = sketch_errors + 1;
                $display("[GL ERROR] Suite 2 HLL Reg[%0d] mismatch: exp=%02h, got=%02h",
                         idx, sars_sketch_mem[idx][4:0], read_data);
            end
        end

        $display("  [GL SUITE 2] Pin Trace: %0d/%0d | HLL Regs: %0d/%0d (Errors: %0d)",
                 SARS_CYCLES - trace_errors, SARS_CYCLES,
                 NUM_REGS - sketch_errors, NUM_REGS,
                 trace_errors + sketch_errors);
        total_errors = total_errors + trace_errors + sketch_errors;

        if (total_errors == 0) begin
            $display("[PASS] GATE-LEVEL NETLIST SIMULATION PASSED (31,968 / 31,968 cycles & 512 / 512 HLL regs 100%% bit-identical!)");
        end else begin
            $display("[FAIL] Gate-Level Simulation failed with %0d errors.", total_errors);
        end
        $finish;
    end

endmodule
