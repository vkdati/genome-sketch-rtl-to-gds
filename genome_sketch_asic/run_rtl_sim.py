#!/usr/bin/env python3
"""
Cross-Platform Verilog RTL Simulation Runner (Windows & Ubuntu Linux)
Project: SCL 180nm Streaming Genome Sketching ASIC (genome-sketch-rtl-to-gds)

Compiles all synthesizable RTL modules (`rtl/*.v`) and the self-checking
testbench (`tb/tb_genome_sketch.v`) using Icarus Verilog (`iverilog`),
then executes the simulation via `vvp`.

Usage:
  python run_rtl_sim.py          # Fast cycle-accurate simulation (< 0.2s)
  python run_rtl_sim.py --vcd    # Also dumps `genome_sketch_tb.vcd` for GTKWave
"""

import argparse
import os
import shutil
import subprocess
import sys
from pathlib import Path

ASIC_DIR = Path(__file__).resolve().parent

RTL_FILES = [
    "rtl/nthash32_engine.v",
    "rtl/lzd24.v",
    "rtl/hll_banked_mem.v",
    "rtl/genome_sketch_top.v",
    "tb/tb_genome_sketch.v",
]


def find_iverilog_bin() -> str:
    """Locates iverilog on PATH or in standard Windows user/system directories."""
    env_path = os.environ.get("PATH", "")
    candidates = [
        Path.home() / "iverilog" / "bin",
        Path("C:/iverilog/bin"),
    ]
    for cand in candidates:
        if (cand / "iverilog.exe").exists() or (cand / "iverilog").exists():
            os.environ["PATH"] = f"{cand}{os.pathsep}{env_path}"
            break

    iverilog_exe = shutil.which("iverilog")
    if not iverilog_exe:
        raise FileNotFoundError(
            "Could not find `iverilog`. Install via `sudo apt install iverilog` (Ubuntu) "
            "or `winget install Icarus.Verilog` (Windows)."
        )
    return iverilog_exe


def main() -> int:
    parser = argparse.ArgumentParser(description="Compile and run the Genome Sketching ASIC RTL simulation.")
    parser.add_argument("--vcd", action="store_true", help="Dump VCD waveform to genome_sketch_tb.vcd")
    args = parser.parse_args()

    find_iverilog_bin()
    vvp_out = ASIC_DIR / "tb_genome_sketch.vvp"

    cmd_compile = ["iverilog", "-g2012", "-I", "tv", "-o", str(vvp_out)]
    if args.vcd:
        cmd_compile.extend(["-D", "DUMP_VCD"])
    cmd_compile.extend(RTL_FILES)

    print(f"[1/2] Compiling Verilog RTL: {' '.join(cmd_compile)}")
    res_comp = subprocess.run(cmd_compile, cwd=ASIC_DIR)
    if res_comp.returncode != 0:
        return res_comp.returncode

    print("[2/2] Running Cycle-Accurate RTL Simulation (`vvp`)...\n")
    res_sim = subprocess.run(["vvp", str(vvp_out.name)], cwd=ASIC_DIR)

    if vvp_out.exists() and not args.vcd:
        vvp_out.unlink()

    return res_sim.returncode


if __name__ == "__main__":
    sys.exit(main())
