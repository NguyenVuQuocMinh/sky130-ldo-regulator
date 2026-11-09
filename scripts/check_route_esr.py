"""Why is the post-layout phase margin at 50 mA higher than the schematic one?
Hypothesis: the metal between the pass-device drains and the vout pin is in
series with CL and acts as extra ESR (a left-half-plane zero).

1. post-layout .op at IL = 50 mA: voltage of every pass-device drain node vs
   the vout pin; R_route = mean(V_drain - V_pin) / IL
2. schematic loop gain at 50 mA with ESR = ESR_nominal + R_route; if the
   hypothesis holds, its PM is close to the post-layout PM.
"""
import re

import numpy as np

from ldo_netlist import core, load_sizes
from pex_netlist import SUB, core_pex
from sim_all import loop_gain
from spice import run

IL = 50e-3
s = load_sizes()
text = SUB.read_text()
drains = set()
for line in text.splitlines():
    t = line.split()
    if t and t[0].startswith("X") and "sky130_fd_pr__pfet_01v8" in t and "l=0.15" in t and "w=10" in t:
        for n in (t[1], t[3]):                    # drain / source (either order)
            if n.startswith("vout"):
                drains.add(n)
drains = sorted(drains)
prints = " ".join(f"v({n})" for n in ["vout"] + drains)
log = run(f"""* route esr
{core_pex()}
vvin vin 0 1.8
iload vout 0 {IL}
.control
op
print {prints}
.endc
.end
""", "route_esr_op")
v = {}
for line in log.splitlines():
    m = re.match(r"\s*v\(([^)]+)\)\s*=\s*([-0-9.eE+]+)", line)
    if m:
        v[m.group(1).lower()] = float(m.group(2))
vp = v["vout"]
dv = np.array([v[n.lower()] - vp for n in drains if n.lower() in v])
r_route = dv.mean() / IL
print(f"{len(dv)} drain nodes: V_drain - V_pin mean {dv.mean()*1e3:.2f} mV, "
      f"min {dv.min()*1e3:.2f}, max {dv.max()*1e3:.2f} mV -> R_route = {r_route*1e3:.1f} mOhm")

for esr in (s["ESR"], s["ESR"] + r_route):
    lg = loop_gain(IL, esr=esr, tag=f"route_esr_{esr*1e3:.0f}m", netfn=core)
    print(f"schematic, ESR = {esr*1e3:.1f} mOhm: PM {lg['PM']:.1f} deg, UGF {lg['UGF']/1e6:.2f} MHz, "
          f"GM {lg['GM_dB']:.1f} dB")
