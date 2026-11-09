"""Check of the suspicious corner point hh, 27 C, VIN = 1.8 V, IL = 50 mA
(the DC sweep in corners.py ended on VOUT = 1.69 V).

Three independent ways to get VOUT at 50 mA:
  1. .op at IL = 50 mA (with the nodeset of core())
  2. transient: IL ramps 0.1 -> 50 mA in 10 us, then held 200 us
  3. DC sweep of IL, listing the isolated points that leave the 1.4-1.6 V band
"""
import numpy as np

from ldo_netlist import core
from spice import read, run

C, T, VIN = "hh", 27, 1.8
base = core(corner=C)

run(f"""* op
{base}
.temp {T}
vvin vin 0 {VIN}
iload vout 0 50m
.control
op
print v(vout) v(fb) v(g) v(ea)
.endc
.end
""", "hh_op")
log = (read.__globals__["SIM"] / "hh_op.log").read_text()
print("1. .op at 50 mA:", [l.strip() for l in log.splitlines() if l.strip().startswith("v(vout)")])

run(f"""* tran
{base}
.temp {T}
vvin vin 0 {VIN}
iload vout 0 pwl(0 0.1m 50u 0.1m 60u 50m)
.control
tran 0.2u 260u
wrdata hh_tran.txt v(vout)
.endc
.end
""", "hh_tran")
d = read("hh_tran.txt", 1)
t, v = d[:, 0], d[:, 1]
print(f"2. transient: VOUT at 49 us = {np.interp(49e-6, t, v):.4f} V, "
      f"at 260 us (50 mA settled) = {v[-1]:.4f} V, min/max after step {v[t > 60e-6].min():.4f}/{v[t > 60e-6].max():.4f}")

run(f"""* sweep
{base}
.temp {T}
vvin vin 0 {VIN}
iload vout 0 0.1m
.control
dc iload 0.1m 50m 0.1m
wrdata hh_sweep.txt v(vout)
.endc
.end
""", "hh_sweep")
d = read("hh_sweep.txt", 1)
i, v = d[:, 0], d[:, 1]
bad = np.where((v < 1.4) | (v > 1.6))[0]
print(f"3. DC sweep: {len(bad)} of {len(v)} points outside 1.4-1.6 V:",
      ", ".join(f"{i[k]*1e3:.1f} mA -> {v[k]:.4g} V" for k in bad))
good = np.delete(v, bad)
print(f"   other points: {good.min():.4f} .. {good.max():.4f} V")
