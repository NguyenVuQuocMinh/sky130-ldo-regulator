"""Where does the high-frequency plateau of the post-layout loop gain come from?

Above ~10 MHz the post-layout |T| stays at -15 .. -25 dB instead of rolling off,
so some path bypasses the loop break at the gate of M2. Test: every extracted
coupling capacitor between the feedback net (fb side of the break) and another
net is replaced by two capacitors of the same value to ground, one on each side
(the load on each net stays, the coupling goes). If the plateau disappears, the
path is capacitive coupling into the feedback net.
"""
import os

from pex_netlist import SUB, prepare
from sim_all import loop_gain
import pex_netlist

prepare()
fb_base = "S110"           # feedback net in the extracted netlist (prepare() reports it)
lines = SUB.read_text().splitlines()
out, n_dec, c_dec = [], 0, 0.0


def is_fb(n):
    return n == "fb" or n.split(".")[0] == fb_base


def val(s):
    return float(s[:-1]) * 1e-15 if s.endswith("f") else float(s)


for l in lines:
    t = l.split()
    if t and t[0].startswith("C") and (is_fb(t[1]) != is_fb(t[2])) and "0" not in (t[1], t[2]):
        out.append(f"{t[0]}a {t[1]} 0 {t[3]}")
        out.append(f"{t[0]}b {t[2]} 0 {t[3]}")
        n_dec += 1
        c_dec += val(t[3])
    else:
        out.append(l)
dec = SUB.with_name("ldo_pex_fbdecoupled.sub")
dec.write_text("\n".join(out) + "\n")
print(f"coupling capacitors of the feedback net moved to ground: {n_dec}, total {c_dec*1e15:.2f} fF")

orig = pex_netlist.SUB
for il in (0.1e-3, 50e-3):
    for nm, sub in (("extracted", orig), ("fb coupling removed", dec)):
        pex_netlist.SUB = sub
        lg = loop_gain(il, tag=f"fbcpl_{nm.split()[0]}_{il*1e3:g}", netfn=pex_netlist.core_pex)
        f, mag = lg["f"], lg["mag"]
        hi = mag[f >= 1e8].max()
        print(f"{il*1e3:g} mA, {nm:20s}: PM {lg['PM']:.1f} deg, UGF {lg['UGF']/1e3:.0f} kHz, "
              f"max |T| above 100 MHz {hi:.1f} dB", flush=True)
pex_netlist.SUB = orig
