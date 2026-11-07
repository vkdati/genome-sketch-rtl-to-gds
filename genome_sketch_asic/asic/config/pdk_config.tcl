# =============================================================================
# Step 0: Parameterized 180nm PDK Configuration for OpenROAD / Yosys Tcl Flows
# Project: SCL 180nm Streaming Genome Sketching ASIC (genome-sketch-rtl-to-gds)
#
# Supports seamless switching between:
#   1. Open-Source 180nm (`gf180mcuD` - 9-track 5.04um cells, 4-Metal constrained)
#   2. Proprietary SCL Mohali 180nm (`tsl18fs120` - 5.60um cells, 4-Metal stack)
# =============================================================================

set DESIGN_NAME "genome_sketch_top"
set CLOCK_PORT  "clk"
set CLOCK_PERIOD_NS 5.000 ;# 200.0 MHz target clock (5.0 ns)

set PDK_TARGET [expr {[info exists ::env(PDK_TARGET)] ? $::env(PDK_TARGET) : "gf180mcuD"}]

if { $PDK_TARGET eq "gf180mcuD" } {
    set PDK_ROOT "/home/nithin/.volare"
    set PDK "gf180mcuD"
    set STD_CELL_LIB "gf180mcu_fd_sc_mcu9t5v0"

    set LIB_DIR     "$PDK_ROOT/$PDK/libs.ref/$STD_CELL_LIB/lib"
    set LEF_DIR     "$PDK_ROOT/$PDK/libs.ref/$STD_CELL_LIB/lef"
    set TECHLEF_DIR "$PDK_ROOT/$PDK/libs.ref/$STD_CELL_LIB/techlef"
    set GDS_DIR     "$PDK_ROOT/$PDK/libs.ref/$STD_CELL_LIB/gds"

    # Liberty timing libraries (5.0V nominal high-speed & 1.8V SCL-matched corners)
    set LIB_TT_5V0  "$LIB_DIR/${STD_CELL_LIB}__tt_025C_5v00.lib"
    set LIB_SS_4V5  "$LIB_DIR/${STD_CELL_LIB}__ss_125C_4v50.lib"
    set LIB_FF_5V5  "$LIB_DIR/${STD_CELL_LIB}__ff_n40C_5v50.lib"

    set LIB_TT_1V8  "$LIB_DIR/${STD_CELL_LIB}__tt_025C_1v80.lib"
    set LIB_SS_1V62 "$LIB_DIR/${STD_CELL_LIB}__ss_125C_1v62.lib"
    set LIB_FF_1V98 "$LIB_DIR/${STD_CELL_LIB}__ff_n40C_1v98.lib"

    set LIB_TYPICAL $LIB_TT_5V0
    set TECH_LEF    "$TECHLEF_DIR/${STD_CELL_LIB}__nom.tlef"
    set CELLS_LEF   "$LEF_DIR/${STD_CELL_LIB}.lef"
    set CELLS_GDS   "$GDS_DIR/${STD_CELL_LIB}.gds"
    set TRACKS_FILE "$PDK_ROOT/$PDK/libs.tech/openlane/$STD_CELL_LIB/tracks.info"
    set RCX_RULES   "$PDK_ROOT/$PDK/libs.tech/openlane/rules.openrcx.$PDK.nom"

    # Placement Site & Cell Mapping for gf180mcu_fd_sc_mcu9t5v0 (9-track, 5.04 um height)
    set PLACE_SITE       "GF018hv5v_green_sc9"
    set TIEHI_CELL_AND_PORT "${STD_CELL_LIB}__tieh Z"
    set TIELO_CELL_AND_PORT "${STD_CELL_LIB}__tiel ZN"
    set MIN_BUF_CELL_AND_PORTS "${STD_CELL_LIB}__buf_1 I Z"
    set TAP_CELL_NAME    "${STD_CELL_LIB}__filltie"
    set ENDCAP_CELL_NAME "${STD_CELL_LIB}__endcap"
    set FILL_CELLS       "${STD_CELL_LIB}__fillcap_16 ${STD_CELL_LIB}__fillcap_8 ${STD_CELL_LIB}__fillcap_4 ${STD_CELL_LIB}__fill_64 ${STD_CELL_LIB}__fill_32 ${STD_CELL_LIB}__fill_16 ${STD_CELL_LIB}__fill_8 ${STD_CELL_LIB}__fill_4 ${STD_CELL_LIB}__fill_2 ${STD_CELL_LIB}__fill_1"
    set CTS_ROOT_BUF     "${STD_CELL_LIB}__clkbuf_16"
    set CTS_BUF_LIST     "${STD_CELL_LIB}__clkbuf_2 ${STD_CELL_LIB}__clkbuf_4 ${STD_CELL_LIB}__clkbuf_8"
    set DIODE_CELL       "${STD_CELL_LIB}__antenna"

    # Enforce SCL 180nm 4-Metal Stack Constraint (Metal1..Metal4 only; Metal5 disabled)
    set MIN_ROUTING_LAYER "Metal2"
    set MAX_ROUTING_LAYER "Metal4"
    set IO_HLAYER         "Metal3"
    set IO_VLAYER         "Metal2"
    set PDN_RAIL_LAYER    "Metal1"
    set PDN_VERT_LAYER    "Metal3"
    set PDN_HORIZ_LAYER   "Metal4"
    set WIRE_RC_DATA_LAYER "Metal2"
    set WIRE_RC_CLK_LAYER  "Metal4"
} else {
    # Proprietary SCL Mohali 180nm (tsl18fs120, 4-Metal) Configuration
    set SCL_ROOT [expr {[info exists ::env(SCL_PDK_ROOT)] ? $::env(SCL_PDK_ROOT) : "/opt/pdk/scl180"}]
    set STD_CELL_LIB "tsl18fs120"
    set LIB_TYPICAL  "$SCL_ROOT/lib/tsl18fs120_tt_1p8v_25c.lib"
    set LIB_SS_1V62  "$SCL_ROOT/lib/tsl18fs120_ss_1p62v_125c.lib"
    set LIB_FF_1V98  "$SCL_ROOT/lib/tsl18fs120_ff_1p98v_m40c.lib"
    set TECH_LEF     "$SCL_ROOT/lef/tsl18l4.tlef"
    set CELLS_LEF    "$SCL_ROOT/lef/tsl18fs120.lef"
    set CELLS_GDS    "$SCL_ROOT/gds/tsl18fs120.gds"
    set PLACE_SITE   "CoreSite"
    set MIN_ROUTING_LAYER "M2"
    set MAX_ROUTING_LAYER "M4"
    set IO_HLAYER         "M3"
    set IO_VLAYER         "M2"
}
