#!/usr/bin/env python3
"""
Step 0 Verification Script: Ubuntu EDA Toolchain & 180nm PDK Smoke Test
Project: SCL 180nm Streaming Genome Sketching ASIC (genome-sketch-rtl-to-gds)
"""

import os
import subprocess
import sys
from pathlib import Path

ASIC_DIR = Path(__file__).resolve().parent.parent
PROJECT_DIR = ASIC_DIR.parent
PDK_ROOT = Path("/home/nithin/.volare/gf180mcuD")
SC_LIB = "gf180mcu_fd_sc_mcu9t5v0"


def check_cmd(name: str, cmd: list[str]) -> str:
    res = subprocess.run(cmd, capture_output=True, text=True, check=False)
    output = (res.stdout + "\n" + res.stderr).strip().splitlines()
    first_line = output[0] if output else "OK"
    if res.returncode != 0 and name not in ("OpenROAD",):
        raise RuntimeError(f"Tool {name} failed: {res.stderr}")
    return first_line


def main() -> int:
    print("=" * 76)
    print("  STEP 0: UBUNTU EDA TOOLCHAIN & 180nm PDK (gf180mcuD) VERIFICATION")
    print("=" * 76)

    tools = [
        ("Yosys (Logic Synthesis)", ["/usr/bin/yosys", "-V"]),
        ("OpenROAD (PnR, CTS, STA)", ["/home/nithin/openroad_env/bin/openroad", "-version"]),
        ("Icarus Verilog (Sim/VCD)", ["/home/nithin/eda_env/bin/iverilog", "-V"]),
        ("Magic VLSI (GDS/DRC)", ["/home/nithin/eda_env/bin/magic", "--version"]),
        ("KLayout (GDSII Viewer/DRC)", ["/home/nithin/eda_env/bin/klayout", "-v"]),
        ("Volare (PDK Manager)", ["/home/nithin/eda_env/bin/volare", "--version"]),
    ]

    print("\n[1/4] Checking Installed EDA Binaries:")
    for label, cmd in tools:
        ver = check_cmd(label, cmd)
        print(f"  [PASS] {label:<28} : {ver}")

    print("\n[2/4] Auditing 180nm PDK Files (gf180mcu_fd_sc_mcu9t5v0):")
    required_files = {
        "Tech LEF (Nominal)": PDK_ROOT / f"libs.ref/{SC_LIB}/techlef/{SC_LIB}__nom.tlef",
        "Standard Cell LEF": PDK_ROOT / f"libs.ref/{SC_LIB}/lef/{SC_LIB}.lef",
        "Standard Cell GDSII": PDK_ROOT / f"libs.ref/{SC_LIB}/gds/{SC_LIB}.gds",
        "Liberty TT (1.80V, 25C)": PDK_ROOT / f"libs.ref/{SC_LIB}/lib/{SC_LIB}__tt_025C_1v80.lib",
        "Liberty SS (1.62V, 125C)": PDK_ROOT / f"libs.ref/{SC_LIB}/lib/{SC_LIB}__ss_125C_1v62.lib",
        "Liberty FF (1.98V, -40C)": PDK_ROOT / f"libs.ref/{SC_LIB}/lib/{SC_LIB}__ff_n40C_1v98.lib",
        "Liberty TT (5.00V, 25C)": PDK_ROOT / f"libs.ref/{SC_LIB}/lib/{SC_LIB}__tt_025C_5v00.lib",
        "Routing Tracks Info": PDK_ROOT / f"libs.tech/openlane/{SC_LIB}/tracks.info",
        "OpenRCX Parasitic Rules": PDK_ROOT / "libs.tech/openlane/rules.openrcx.gf180mcuD.nom",
    }

    for desc, fpath in required_files.items():
        if not fpath.is_file():
            print(f"  [FAIL] Missing {desc}: {fpath}")
            return 1
        size_kb = fpath.stat().st_size / 1024.0
        print(f"  [PASS] {desc:<28} : {fpath.name} ({size_kb:,.1f} KB)")

    print("\n[3/4] Running OpenROAD LEF/Liberty Read Smoke Test:")
    smoke_tcl = (
        f'source "{ASIC_DIR / "config/pdk_config.tcl"}"\n'
        'read_lef $TECH_LEF\n'
        'read_lef $CELLS_LEF\n'
        'read_liberty $LIB_TYPICAL\n'
        'puts "OPENROAD_PDK_SMOKE_TEST_PASSED"\n'
        'exit\n'
    )
    res_or = subprocess.run(
        ["/home/nithin/openroad_env/bin/openroad", "-exit"],
        input=smoke_tcl,
        capture_output=True,
        text=True,
        check=False,
    )
    if "OPENROAD_PDK_SMOKE_TEST_PASSED" not in res_or.stdout:
        print("  [FAIL] OpenROAD failed to load PDK LEF/Liberty:")
        print(res_or.stdout)
        print(res_or.stderr)
        return 1
    print("  [PASS] OpenROAD loaded TechLEF, Standard-Cell LEF (9-track), and Liberty (.lib) cleanly.")

    print("\n[4/4] Re-verifying Phase B RTL Simulation on Ubuntu (Icarus Verilog 13.0):")
    env = os.environ.copy()
    env["PATH"] = f"/home/nithin/eda_env/bin:{env.get('PATH', '')}"
    res_sim = subprocess.run(
        [sys.executable, str(PROJECT_DIR / "run_rtl_sim.py")],
        cwd=str(PROJECT_DIR),
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    if res_sim.returncode != 0:
        print("  [FAIL] Phase B RTL simulation failed:")
        print(res_sim.stdout)
        print(res_sim.stderr)
        return 1
    for line in res_sim.stdout.splitlines():
        if any(k in line for k in ("PASS", "OVERALL", "Mismatches", "31,968")):
            print(f"  {line.strip()}")

    print("\n" + "=" * 76)
    print("  STEP 0 COMPLETE: Toolchain & 180nm PDK Ready for Step 1 (SDC & Synthesis)")
    print("=" * 76)
    return 0


if __name__ == "__main__":
    sys.exit(main())
