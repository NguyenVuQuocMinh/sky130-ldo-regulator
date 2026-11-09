"""On-chip part of the LDO as a CDL netlist for LVS (sky130 device names).

Same devices and sizes as ldo_netlist.core(), without the off-chip parts
(VREF source, IBIAS source, CL, ESR, loop-break elements). Pins: vin, vout,
gnd, vref, ibias (ibias = drain/gate of the bias diode MBN, net nb).
The divider has two dummy units (both ends and body on gnd), as in the layout.

    python ldo_cdl.py            -> writes layout/ldo.cdl
"""
import pathlib

from ldo_netlist import load_sizes

ROOT = pathlib.Path(__file__).resolve().parent.parent


def cdl(s=None):
    s = s or load_sizes()
    N, P = "sky130_fd_pr__nfet_01v8", "sky130_fd_pr__pfet_01v8"
    R = "sky130_fd_pr__res_xhigh_po_0p35"

    def m(name, d, g, src, b, model, w, l, mult=1):
        return f"M{name} {d} {g} {src} {b} {model} w={w:g}u l={l:g}u m={mult}"

    L = [".SUBCKT ldo vin vout gnd vref ibias",
         m("mbn", "ibias", "ibias", "gnd", "gnd", N, s["WB"], s["LB"], s["MBN_M"]),
         m("mt", "tail", "ibias", "gnd", "gnd", N, s["WB"], s["LB"], s["MT_M"]),
         m("m1", "d1", "vref", "tail", "gnd", N, s["W12"], s["L12"], s["M12"]),
         m("m2", "ea", "fb", "tail", "gnd", N, s["W12"], s["L12"], s["M12"]),
         m("m3", "d1", "d1", "vin", "vin", P, s["W34"], s["L34"], s["M34"]),
         m("m4", "ea", "d1", "vin", "vin", P, s["W34"], s["L34"], s["M34"]),
         m("mcs", "g", "ea", "gnd", "gnd", N, s["WCS"], s["LCS"], s["MCS_M"]),
         m("md", "g", "g", "vin", "vin", P, s["WPf"], s["LP"], s["MD_M"]),
         m("mbl", "g", "d1", "vin", "vin", P, s["WBL"], s["LBL"], s["MBL_M"]),
         m("mp", "vout", "g", "vin", "vin", P, s["WPf"], s["LP"], s["MP_M"])]
    lu = s["L_RU"]

    def chain(name, a, b, n):
        nodes = [a] + [f"{name}_{k}" for k in range(1, n)] + [b]
        return [f"R{name}{k} {nodes[k]} {nodes[k + 1]} gnd {R} l={lu:g}u w=0.35u" for k in range(n)]

    L += chain("r1", "vout", "fb", s["N_R1"])
    L += chain("r2", "fb", "gnd", s["N_R2"])
    L += [f"Rdum{k} gnd gnd gnd {R} l={lu:g}u w=0.35u" for k in (0, 1)]
    L += [".ENDS ldo"]
    return "\n".join(L) + "\n"


if __name__ == "__main__":
    p = ROOT / "layout" / "ldo.cdl"
    p.write_text(cdl())
    print(p.read_text())
