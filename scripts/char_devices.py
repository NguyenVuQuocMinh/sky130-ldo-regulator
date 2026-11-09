"""Characterise sky130 1.8 V devices (nfet_01v8, pfet_01v8) in ngspice.

For each L: ID-VGS at |VDS| = 0.9 V (W = 10 um), extract
  VTH  : saturation sqrt(ID) extrapolation (steepest tangent of sqrt(ID) vs VGS)
  KP   : u Cox from the square-law fit 2 ID / (W/L) / VOV^2 at VOV = 0.2 V
  gm/ID versus ID/(W/L)  (saved for the design script)
  ro   : from ID-VDS slope at VOV = 0.2 V, |VDS| = 0.6 V   ->  lambda = 1/(ro ID)
Writes params.json and figures/gm_over_id.png.
Usage: python char_devices.py [corner]   (default tt)
"""
import os
import json
import pathlib
import sys
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from spice import run, read, SIM

ROOT = pathlib.Path(__file__).resolve().parent.parent
LIB = os.environ.get("SKY130_FD_PR", "path/to/sky130_fd_pr/models").rstrip("/") + "/sky130.lib.spice"
CORNER = sys.argv[1] if len(sys.argv) > 1 else "tt"
W = 10.0          # um (models use scale 1e-6)
LS = [0.15, 0.5, 1.0, 2.0]
MODEL = {"n": "sky130_fd_pr__nfet_01v8", "p": "sky130_fd_pr__pfet_01v8"}


def idvg(kind, L, vds=0.9, corner=CORNER, tag=None):
    """Return (VGS magnitude array, ID magnitude array) for one W = 10 um device."""
    tag = tag or f"idvg_{kind}_{L:g}_{corner}"
    if kind == "n":
        dev = f"xm d g 0 0 {MODEL['n']} w={W} l={L}"
        src = f"vd d 0 {vds}\nvg g 0 0"
        sweep, vec = "dc vg 0 1.8 0.005", "-i(vd)"
    else:
        dev = f"xm d g s s {MODEL['p']} w={W} l={L}"
        src = f"vs s 0 1.8\nvd d 0 {1.8 - vds}\nvg g 0 1.8"
        sweep, vec = "dc vg 1.8 0 -0.005", "i(vd)"
    net = f"""* {tag}
.lib "{LIB}" {corner}
{src}
{dev}
.control
{sweep}
wrdata {tag}.txt {vec}
.endc
.end
"""
    run(net, tag)
    d = read(f"{tag}.txt", 1)
    vg = d[:, 0] if kind == "n" else 1.8 - d[:, 0]
    return vg, np.abs(d[:, 1])


def idvd(kind, L, vov, vth, corner=CORNER):
    tag = f"idvd_{kind}_{L:g}_{corner}"
    if kind == "n":
        dev = f"xm d g 0 0 {MODEL['n']} w={W} l={L}"
        src = f"vd d 0 0\nvg g 0 {vth + vov}"
        sweep, vec = "dc vd 0 1.8 0.01", "-i(vd)"
    else:
        dev = f"xm d g s s {MODEL['p']} w={W} l={L}"
        src = f"vs s 0 1.8\nvd d 0 1.8\nvg g 0 {1.8 - vth - vov}"
        sweep, vec = "dc vd 1.8 0 -0.01", "i(vd)"
    net = f"""* {tag}
.lib "{LIB}" {corner}
{src}
{dev}
.control
{sweep}
wrdata {tag}.txt {vec}
.endc
.end
"""
    run(net, tag)
    d = read(f"{tag}.txt", 1)
    vd = d[:, 0] if kind == "n" else 1.8 - d[:, 0]
    return vd, np.abs(d[:, 1])


def extract(kind, L):
    vg, i = idvg(kind, L)
    gm = np.gradient(i, vg)
    # saturation: sqrt(ID) is linear in VGS above threshold; extrapolate the
    # steepest tangent of sqrt(ID) to zero
    sq = np.sqrt(i)
    dsq = np.gradient(sq, vg)
    k = int(np.argmax(dsq))
    vth = float(vg[k] - sq[k] / dsq[k])
    vov = 0.2
    i_at = float(np.interp(vth + vov, vg, i))
    kp = 2 * i_at / (W / L) / vov ** 2
    vd, idd = idvd(kind, L, vov, vth)
    g_ds = np.gradient(idd, vd)
    i6 = float(np.interp(0.6, vd, idd))
    gds6 = float(np.interp(0.6, vd, g_ds))
    lam = gds6 / i6
    gmid = gm / np.maximum(i, 1e-15)
    jd = i / (W / L)                           # current density per square
    return dict(VTH=vth, KP=kp, LAMBDA=lam, ID_at_vov02=i_at,
                gmid=gmid.tolist(), jd=jd.tolist(), vgs=vg.tolist())


def main():
    P = {"corner": CORNER, "W_char_um": W}
    for kind in "np":
        for L in LS:
            r = extract(kind, L)
            P[f"{kind}_L{L:.2f}"] = r
            print(f"{CORNER} {kind}fet L={L:<5} VTH={r['VTH']:.3f} V  KP={r['KP']*1e6:7.1f} uA/V^2"
                  f"  lambda={r['LAMBDA']:.3f} 1/V (at |VDS|=0.6, VOV=0.2)")
    out = ROOT / "scripts" / f"params_{CORNER}.json"
    out.write_text(json.dumps(P))
    fig, ax = plt.subplots(1, 2, figsize=(9, 3.4))
    for j, kind in enumerate("np"):
        for L in LS:
            r = P[f"{kind}_L{L:.2f}"]
            jd, g = np.array(r["jd"]), np.array(r["gmid"])
            m = jd > 1e-9
            ax[j].semilogx(jd[m], g[m], label=f"L={L} um")
        ax[j].set_xlabel("ID/(W/L) (A)")
        ax[j].set_ylabel("gm/ID (1/V)")
        ax[j].set_title(f"{MODEL[kind]} ({CORNER})", fontsize=9)
        ax[j].grid(alpha=0.3)
        ax[j].legend(fontsize=7)
    fig.tight_layout()
    fig.savefig(ROOT / "figures" / "gm_over_id.png", dpi=150)


if __name__ == "__main__":
    main()
