#!/usr/bin/env bash
# =============================================================================
# Step 0: Ubuntu EDA Toolchain & 180nm PDK Environment Setup
# Project: SCL 180nm Streaming Genome Sketching ASIC (genome-sketch-rtl-to-gds)
#
# Usage:
#   source genome_sketch_asic/asic/config/env_setup.sh
#   (Optional) export PDK_TARGET="scl180"  # Switch to proprietary tsl18fs120
# =============================================================================

export ASIC_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
export PROJECT_ROOT="$(cd "${ASIC_DIR}/.." && pwd)"

# Add userspace Micromamba EDA environments to PATH
export PATH="/home/nithin/openroad_env/bin:/home/nithin/eda_env/bin:/home/nithin/.local/bin:${PATH}"

# Tool Binary Paths
export YOSYS_BIN="/usr/bin/yosys"
export OPENROAD_BIN="/home/nithin/openroad_env/bin/openroad"
export IVERILOG_BIN="/home/nithin/eda_env/bin/iverilog"
export VVP_BIN="/home/nithin/eda_env/bin/vvp"
export MAGIC_BIN="/home/nithin/eda_env/bin/magic"
export KLAYOUT_BIN="/home/nithin/eda_env/bin/klayout"
export VOLARE_BIN="/home/nithin/eda_env/bin/volare"
export PYTHON_EDA="/home/nithin/eda_env/bin/python3"

# Target PDK Selection: "gf180mcuD" (Open-Source 180nm) or "scl180" (SCL tsl18fs120)
export PDK_TARGET="${PDK_TARGET:-gf180mcuD}"

if [ "${PDK_TARGET}" = "gf180mcuD" ]; then
    export PDK_ROOT="/home/nithin/.volare"
    export PDK="gf180mcuD"
    export STD_CELL_LIBRARY="gf180mcu_fd_sc_mcu9t5v0"
    export LIB_DIR="${PDK_ROOT}/${PDK}/libs.ref/${STD_CELL_LIBRARY}/lib"
    export LEF_DIR="${PDK_ROOT}/${PDK}/libs.ref/${STD_CELL_LIBRARY}/lef"
    export TECHLEF_DIR="${PDK_ROOT}/${PDK}/libs.ref/${STD_CELL_LIBRARY}/techlef"
    export GDS_DIR="${PDK_ROOT}/${PDK}/libs.ref/${STD_CELL_LIBRARY}/gds"

    # Primary Liberty (.lib) Corners:
    #   - 5.0V TT/SS/FF (Standard thick-oxide MCU characterization for high-speed 200 MHz target)
    #   - 1.8V TT/SS/FF (Matched directly to SCL 180nm 1.8V +/- 10% voltage rails)
    export LIB_TT_5V0="${LIB_DIR}/${STD_CELL_LIBRARY}__tt_025C_5v00.lib"
    export LIB_SS_4V5="${LIB_DIR}/${STD_CELL_LIBRARY}__ss_125C_4v50.lib"
    export LIB_FF_5V5="${LIB_DIR}/${STD_CELL_LIBRARY}__ff_n40C_5v50.lib"

    export LIB_TT_1V8="${LIB_DIR}/${STD_CELL_LIBRARY}__tt_025C_1v80.lib"
    export LIB_SS_1V62="${LIB_DIR}/${STD_CELL_LIBRARY}__ss_125C_1v62.lib"
    export LIB_FF_1V98="${LIB_DIR}/${STD_CELL_LIBRARY}__ff_n40C_1v98.lib"

    # Active synthesis & PnR libraries (defaults to 5V0 TT for timing closure + 1V8 multi-corner check)
    export LIB_SYNTH="${LIB_SYNTH:-${LIB_TT_5V0}}"
    export TECH_LEF="${TECHLEF_DIR}/${STD_CELL_LIBRARY}__nom.tlef"
    export CELLS_LEF="${LEF_DIR}/${STD_CELL_LIBRARY}.lef"
    export CELLS_GDS="${GDS_DIR}/${STD_CELL_LIBRARY}.gds"
    export TRACKS_INFO="${PDK_ROOT}/${PDK}/libs.tech/openlane/${STD_CELL_LIBRARY}/tracks.info"
    export RCX_RULES="${PDK_ROOT}/${PDK}/libs.tech/openlane/rules.openrcx.${PDK}.nom"

    # SCL 180nm Foundry Equivalence Constraints Enforced on gf180mcuD:
    # Restrict routing strictly to 4 Metal layers (Metal1..Metal4)
    export RT_MIN_LAYER="Metal2"
    export RT_MAX_LAYER="Metal4"
else
    # Proprietary SCL Mohali 180nm (tsl18fs120) Drop-In Configuration
    export SCL_PDK_ROOT="${SCL_PDK_ROOT:-/opt/pdk/scl180}"
    export STD_CELL_LIBRARY="tsl18fs120"
    export LIB_SYNTH="${SCL_PDK_ROOT}/lib/tsl18fs120_tt_1p8v_25c.lib"
    export LIB_SS_1V62="${SCL_PDK_ROOT}/lib/tsl18fs120_ss_1p62v_125c.lib"
    export LIB_FF_1V98="${SCL_PDK_ROOT}/lib/tsl18fs120_ff_1p98v_m40c.lib"
    export TECH_LEF="${SCL_PDK_ROOT}/lef/tsl18l4.tlef"
    export CELLS_LEF="${SCL_PDK_ROOT}/lef/tsl18fs120.lef"
    export CELLS_GDS="${SCL_PDK_ROOT}/gds/tsl18fs120.gds"
    export RT_MIN_LAYER="M1"
    export RT_MAX_LAYER="M4"
fi
