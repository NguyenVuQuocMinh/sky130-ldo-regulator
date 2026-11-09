"""LDO netlist for SkyWater sky130 (ngspice), built from sizes.json.

Topology:
  bias            : external current IBIAS into NMOS diode MBN; mirrored to the
                    OTA tail MT (ratio MT_M : MBN_M)
  error amplifier : NMOS-input five-transistor OTA. M1 gate = VREF (diode side),
                    M2 gate = FB (output side), PMOS mirror load M3/M4.
                    Output node "ea".
  gate driver     : NMOS common-source MCS (gate = ea) sinks current from the
                    diode-connected PMOS MD; MD and the pass device MP form a
                    1 : N current mirror (same L, same finger width), so the
                    pass-gate node "g" has impedance 1/gm(MD).
                    Bleeder MBL (PMOS, gate = d1, mirror of M3) sources a small
                    fixed current into g, so MD and MP carry only the part of the
                    MCS current above it. Without it the subthreshold current of
                    MCS at the lowest OTA output (hot corners) times N exceeds
                    the minimum load and VOUT drifts up.
  pass device     : PMOS MP, N fingers, bulk = VIN
  feedback        : R1 (VOUT -> FB) and R2 (FB -> GND), each a series string of
                    identical xhigh_po unit resistors
  off chip        : VREF (ideal), CL with series ESR, load current IL
Pins of the chip: vin, vout, gnd (0), vref, ibias.
"""
import json
import os
import pathlib

ROOT = pathlib.Path(__file__).resolve().parent.parent
LIB = str((ROOT / "sim" / "ldo_corners.lib").as_posix())   # see make_corner_lib.py
SIZES = os.environ.get("LDO_SIZES", "sizes.json")


def load_sizes():
    return json.loads((ROOT / "scripts" / SIZES).read_text())


def mos(name, d, g, s, b, kind, W, L, m=1):
    """sky130 1.8 V device; W is the width of ONE finger, m = number of fingers.
    Junction areas for a finger with 0.29 um diffusion on each side of the gate
    (shared contacts between fingers are ignored: conservative)."""
    model = "sky130_fd_pr__nfet_01v8" if kind == "n" else "sky130_fd_pr__pfet_01v8"
    ad = W * 0.29
    pd = 2 * (W + 0.29)
    return (f"x{name} {d} {g} {s} {b} {model} w={W:g} l={L:g} m={m} "
            f"ad={ad:.4g} as={ad:.4g} pd={pd:.4g} ps={pd:.4g}")


def res_string(name, a, b, n, l_unit):
    """n identical xhigh_po 0.35 um units in series from a to b (body = gnd)."""
    nodes = [a] + [f"{name}_{k}" for k in range(1, n)] + [b]
    return [f"x{name}{k} {nodes[k]} {nodes[k + 1]} 0 sky130_fd_pr__res_xhigh_po_0p35 l={l_unit:.4g}"
            for k in range(n)]


def core(S=None, loop_break=False, esr=None, cl=None, corner="tt", vref=None):
    s = S or load_sizes()
    esr = s["ESR"] if esr is None else esr
    cl = s["CL"] if cl is None else cl
    vref = s["VREF"] if vref is None else vref
    L = [
        f'.lib "{LIB}" {corner}',
        # bias: IBIAS flows from VIN into the NMOS diode MBN
        f"ibias vin nb {s['IBIAS']}",
        mos("mbn", "nb", "nb", "0", "0", "n", s["WB"], s["LB"], s["MBN_M"]),
        mos("mt", "tail", "nb", "0", "0", "n", s["WB"], s["LB"], s["MT_M"]),
        # OTA: M1 = VREF (diode side), M2 = FB (output side)
        mos("m1", "d1", "vref", "tail", "0", "n", s["W12"], s["L12"], s["M12"]),
        mos("m2", "ea", "fbi", "tail", "0", "n", s["W12"], s["L12"], s["M12"]),
        mos("m3", "d1", "d1", "vin", "vin", "p", s["W34"], s["L34"], s["M34"]),
        mos("m4", "ea", "d1", "vin", "vin", "p", s["W34"], s["L34"], s["M34"]),
        f"vref vref 0 {vref}",
        # gate driver
        mos("mcs", "g", "ea", "0", "0", "n", s["WCS"], s["LCS"], s["MCS_M"]),
        mos("md", "g", "g", "vin", "vin", "p", s["WPf"], s["LP"], s["MD_M"]),
        mos("mbl", "g", "d1", "vin", "vin", "p", s["WBL"], s["LBL"], s["MBL_M"]),
        # pass device
        mos("mp", "vout", "g", "vin", "vin", "p", s["WPf"], s["LP"], s["MP_M"]),
    ]
    L += res_string("r1", "vout", "fb", s["N_R1"], s["L_RU"])
    L += res_string("r2", "fb", "0", s["N_R2"], s["L_RU"])
    L += [f"cl vout nesr {cl}", f"resr nesr 0 {esr}"]
    # starting guess for the DC solver: without it ngspice can land on a
    # non-physical solution of the poly-resistor model (seen: fb = 1 kV)
    L += [f".nodeset v(vout)={s['VOUT']} v(fb)={vref} v(fbi)={vref}",
          ".option noopiter gminsteps=0"]
    if loop_break:
        L += ["lbrk fb fbi 1e9", "cbrk fbi vt 1e3", "vt vt 0 dc 0 ac 1"]
    else:
        L += ["rshort fb fbi 1e-3"]
    return "\n".join(L)


if __name__ == "__main__":
    print(core())
