"""Corner sweep of the sky130 LDO (schematic level).

Process corners tt, ss, ff, sf, fs (typical R/C) and ll, hh (low/high R and C,
typical devices); temperatures -40, 27, 125 C; VIN = 1.7, 1.8, 1.9 V.
Per case: VOUT at IL = 0.1 mA and 50 mA (DC sweep of IL), quiescent current,
and the loop gain at both loads (PM, UGF, GM).
Writes scripts/corners_<VER>.json and prints a table.
"""
import itertools
import json
import os
import pathlib
import numpy as np
from spice import run, read
from ldo_netlist import core
from sim_all import loop_gain

ROOT = pathlib.Path(__file__).resolve().parent.parent
VER = os.environ.get("LDO_VER", "sch")
CORNERS = ["tt", "ss", "ff", "sf", "fs", "ll", "hh"]
TEMPS = [-40, 27, 125]
VINS = [1.7, 1.8, 1.9]


def dc_case(corner, temp, vin):
    """VOUT and Iq from a separate .op at each load. (A DC sweep of IL was used
    before; at hh/27 C/1.8 V its last point landed on a non-physical solution of
    the poly-resistor model, 1.69 V, while .op and a transient give 1.4959 V;
    see check_hh.py.)"""
    tag = f"pc_{corner}_{temp}_{vin}_{VER}"
    res = {}
    for il, key in (("0.1m", "light"), ("50m", "heavy")):
        net = f"""* corner {tag} IL={il}
{core(corner=corner)}
.temp {temp}
vvin vin 0 {vin}
iload vout 0 {il}
.control
op
print v(vout) i(vvin)
.endc
.end
"""
        log = run(net, f"{tag}_{key}")
        vals = {}
        for line in log.splitlines():
            s = line.strip().split("=")
            if len(s) == 2 and s[0].strip() in ("v(vout)", "i(vvin)"):
                vals[s[0].strip()] = float(s[1])
        res[f"v_{key}"] = vals["v(vout)"]
        if key == "light":
            res["iq"] = -vals["i(vvin)"] - 0.1e-3
    return res


def main():
    out = []
    for corner, temp, vin in itertools.product(CORNERS, TEMPS, VINS):
        r = dict(corner=corner, temp=temp, vin=vin)
        r.update(dc_case(corner, temp, vin))
        for il, key in ((0.1e-3, "light"), (50e-3, "heavy")):
            lg = loop_gain(il, vin=vin, corner=corner, temp=temp,
                           tag=f"rob_{corner}_{temp}_{vin}_{key}_{VER}")
            r[f"PM_{key}"] = lg["PM"]
            r[f"UGF_{key}"] = lg["UGF"]
            r[f"GM_{key}"] = lg["GM_dB"]
            r[f"T0_{key}"] = lg["T0_dB"]
        out.append(r)
        print(f"{corner:>2} {temp:>4}C VIN={vin}: VOUT {r['v_light']:.4f}/{r['v_heavy']:.4f} V"
              f"  Iq {r['iq']*1e6:5.1f} uA  PM {r['PM_light']:.0f}/{r['PM_heavy']:.0f}"
              f"  UGF {r['UGF_light']/1e3:.1f}k/{r['UGF_heavy']/1e3:.0f}k"
              f"  GM {r['GM_light']:.0f}/{r['GM_heavy']:.0f} dB", flush=True)
    (ROOT / "scripts" / f"corners_{VER}.json").write_text(json.dumps(out, indent=1))
    a = lambda k: np.array([r[k] for r in out])
    print("ranges: VOUT light", a("v_light").min(), a("v_light").max(),
          "| VOUT heavy", a("v_heavy").min(), a("v_heavy").max(),
          "| Iq max", a("iq").max(), "| PM min", min(a("PM_light").min(), a("PM_heavy").min()))


if __name__ == "__main__":
    main()
