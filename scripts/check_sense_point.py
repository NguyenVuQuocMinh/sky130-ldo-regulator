"""Second hypothesis for the higher post-layout phase margin at 50 mA:
the divider (feedback) taps the vout plate at its left edge, not at the pin
where CL sits, so the loop senses  pass drain -R_a- sense -R_b- pin(CL).

1. post-layout .op at 50 mA: mean drain voltage, divider-top voltage, pin voltage
   -> R_a = (V_drain - V_sense) / IL,  R_b = (V_sense - V_pin) / IL
2. schematic with the same split (the divider on node 'sense'), loop gain at 50 mA
   -> compare PM / UGF with the post-layout result (101.6 deg, 1.37 MHz).
"""
import re

import numpy as np

from ldo_netlist import core, load_sizes
from pex_netlist import SUB, core_pex
from sim_all import loop_gain
from spice import run

IL = 50e-3
s = load_sizes()
drains, rtop = set(), set()
for line in SUB.read_text().splitlines():
    t = line.split()
    if not t or not t[0].startswith("X"):
        continue
    if "sky130_fd_pr__pfet_01v8" in t and "l=0.15" in t and "w=10" in t:
        drains |= {n for n in (t[1], t[3]) if n.startswith("vout")}
    if "sky130_fd_pr__res_xhigh_po_0p35" in t:
        rtop |= {n for n in (t[1], t[2]) if n.startswith("vout")}
nodes = ["vout"] + sorted(drains) + sorted(rtop)
log = run(f"""* sense point
{core_pex()}
vvin vin 0 1.8
iload vout 0 {IL}
.control
op
print {' '.join(f'v({n})' for n in nodes)}
.endc
.end
""", "sense_point_op")
v = {}
for line in log.splitlines():
    m = re.match(r"\s*v\(([^)]+)\)\s*=\s*([-0-9.eE+]+)", line)
    if m:
        v[m.group(1).lower()] = float(m.group(2))
vp = v["vout"]
vd = np.mean([v[n.lower()] for n in drains])
vs = np.mean([v[n.lower()] for n in rtop])
ra, rb = (vd - vs) / IL, (vs - vp) / IL
print(f"divider-top node(s) {sorted(rtop)}: V_drain {vd:.5f}, V_sense {vs:.5f}, V_pin {vp:.5f} V")
print(f"R_a (drain -> sense) = {ra*1e3:.1f} mOhm, R_b (sense -> pin) = {rb*1e3:.1f} mOhm")


def split_net(**kw):
    """schematic core() with: pass drain on 'vd', R_a to 'sense', R_b to the pin 'vout';
    the divider top moved to 'sense'."""
    net = core(**kw)
    out = []
    for l in net.splitlines():
        if l.startswith("xmp "):
            l = l.replace("xmp vout ", "xmp vd ", 1)
        if l.startswith("xr10 vout "):
            l = l.replace("xr10 vout ", "xr10 sense ", 1)
        out.append(l)
    out += [f"rra vd sense {ra}", f"rrb sense vout {max(rb, 1e-6)}"]
    return "\n".join(out)


for nm, fn in (("schematic", core), ("schematic + R_a/R_b split", split_net)):
    lg = loop_gain(IL, tag=f"sense_{nm[:5]}_{len(nm)}", netfn=fn)
    print(f"{nm:28s}: PM {lg['PM']:.1f} deg, UGF {lg['UGF']/1e6:.2f} MHz, T0 {lg['T0_dB']:.1f} dB, "
          f"GM {lg['GM_dB']:.1f} dB")
print("post-layout (run_postlayout.py): PM 101.6 deg, UGF 1.37 MHz, T0 45.7 dB")
