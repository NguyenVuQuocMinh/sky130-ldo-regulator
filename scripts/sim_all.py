"""Performance simulations of the sky130 LDO (schematic level).

  loop gain (broken at the OTA input M2 with an L-C break) at IL = 0.1, 1, 10, 50 mA
  PSRR (AC on VIN, loop closed) at IL = 0.1 and 50 mA
  load regulation (DC sweep of IL), line regulation + dropout (DC sweep of VIN)
  quiescent current versus VIN
  load transient 0.1 <-> 50 mA, 1 us edges
  phase margin versus ESR at IL = 0.1 and 50 mA
Writes scripts/sim_results_<VER>.json and figures/*_<VER>.png.
Environment: LDO_VER (tag, default "sch"), LDO_SIZES (sizes file).
"""
import json
import os
import pathlib
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from spice import run, read
from ldo_netlist import core

ROOT = pathlib.Path(__file__).resolve().parent.parent
VER = os.environ.get("LDO_VER", "sch")
FIG = ROOT / "figures"
R = {}


def loop_gain(il, esr=None, vin=1.8, tag=None, corner="tt", temp=27, netfn=core):
    tag = tag or f"lg_{il*1e3:g}mA_{VER}"
    net = f"""* loop gain {tag}
{netfn(loop_break=True, esr=esr, corner=corner)}
.temp {temp}
vvin vin 0 {vin}
iload vout 0 {il}
.control
ac dec 100 1 1e9
let T = -v(fb)/v(fbi)
let tm = db(T)
let tp = 180/pi*cph(T)
wrdata {tag}.txt tm tp
.endc
.end
"""
    run(net, tag)
    d = read(f"{tag}.txt", 2)
    f, mag, ph = d[:, 0], d[:, 1], d[:, 3]
    k = int(np.argmax(mag < 0))
    f0 = float(np.exp(np.interp(0, [mag[k], mag[k - 1]], [np.log(f[k]), np.log(f[k - 1])])))
    ph0 = float(np.interp(np.log(f0), [np.log(f[k - 1]), np.log(f[k])], [ph[k - 1], ph[k]]))
    pm = 180 + ph0
    j = int(np.argmax(ph < -180))
    gm_db = float(-mag[j]) if j > 0 else float("inf")
    return dict(f=f, mag=mag, ph=ph, T0_dB=float(mag[0]), UGF=f0, PM=pm, GM_dB=gm_db)


def psrr(il, netfn=core):
    tag = f"psrr_{il*1e3:g}mA_{VER}"
    net = f"""* PSRR {tag}
{netfn()}
vvin vin 0 dc 1.8 ac 1
iload vout 0 {il}
.control
ac dec 50 1 1e8
let p = -db(v(vout))
wrdata {tag}.txt p
.endc
.end
"""
    run(net, tag)
    d = read(f"{tag}.txt", 1)
    return d[:, 0], d[:, 1]


def dc_sweep(src_line, sweep, vec, tag, netfn=core):
    net = f"""* {tag}
{netfn()}
{src_line}
.control
dc {sweep}
wrdata {tag}.txt {vec}
.endc
.end
"""
    run(net, tag)
    return read(f"{tag}.txt", 1)


def transient(netfn=core, tag=None):
    tag = tag or f"tran_{VER}"
    net = f"""* load transient
{netfn()}
vvin vin 0 1.8
iload vout 0 pwl(0 0.1m 20u 0.1m 21u 50m 120u 50m 121u 0.1m 300u 0.1m)
.control
tran 5n 300u 0 20n
wrdata {tag}.txt v(vout) v(g)
.endc
.end
"""
    run(net, tag)
    d = read(f"{tag}.txt", 2)
    t, vo, vg = d[:, 0], d[:, 1], d[:, 3]
    v0 = float(np.interp(19e-6, t, vo))
    m1 = (t > 20e-6) & (t < 120e-6)
    m2 = t > 120e-6
    v_heavy = float(np.interp(119e-6, t, vo))
    v_end = float(vo[-1])
    res = dict(v_light=v0, v_heavy=v_heavy, v_end=v_end,
               undershoot=float(v_heavy - vo[m1].min()),
               overshoot=float(vo[m2].max() - v_end),
               dip_from_initial=float(v0 - vo[m1].min()),
               peak_from_heavy=float(vo[m2].max() - v_heavy))

    def settle(t0, t1, vfinal):
        mm = (t > t0) & (t < t1)
        tt, vv = t[mm], vo[mm]
        bad = np.where(np.abs(vv - vfinal) > 1e-3)[0]
        return float(tt[bad[-1]] - t0) if len(bad) else 0.0
    res["settle_up"] = settle(21e-6, 120e-6, v_heavy)
    res["settle_down"] = settle(121e-6, 300e-6, v_end)
    return res, (t, vo, vg)


def save():
    (ROOT / "scripts" / f"sim_results_{VER}.json").write_text(json.dumps(R, indent=1))


def main(netfn=core, esrs=None, il_step="0.1m", vin_step=0.002, dcfn=None, resume=False):
    """esrs / il_step / vin_step: coarser settings for the slow post-layout runs.
    Results are saved after every section (sim_results_<VER>.json).
    dcfn: netlist for the DC sweeps (default netfn); resume: keep the sections
    already in the saved JSON instead of running them again."""
    dcfn = dcfn or netfn
    js = ROOT / "scripts" / f"sim_results_{VER}.json"
    if resume and js.exists():
        R.update(json.loads(js.read_text()))
        print("resume: kept", list(R), flush=True)
    loads = [0.1e-3, 1e-3, 10e-3, 50e-3]
    fig, ax = plt.subplots(2, 1, figsize=(6.4, 5.6), sharex=True)
    skip_loop = "loop" in R
    R["loop"] = R.get("loop", {})
    for il in loads:
        if skip_loop:
            continue
        lg = loop_gain(il, netfn=netfn)
        R["loop"][f"{il*1e3:g}mA"] = {k: lg[k] for k in ("T0_dB", "UGF", "PM", "GM_dB")}
        print(f"loop IL={il*1e3:5g} mA: T0={lg['T0_dB']:.1f} dB  UGF={lg['UGF']/1e3:.1f} kHz"
              f"  PM={lg['PM']:.1f} deg  GM={lg['GM_dB']:.1f} dB")
        ax[0].semilogx(lg["f"], lg["mag"], label=f"$I_L$ = {il*1e3:g} mA")
        ax[1].semilogx(lg["f"], lg["ph"])
    ax[0].axhline(0, color="k", lw=0.6)
    ax[0].set_ylabel("|T| (dB)")
    ax[0].legend(fontsize=8)
    ax[1].axhline(-180, color="k", lw=0.6)
    ax[1].set_ylabel("phase of T (deg)")
    ax[1].set_xlabel("frequency (Hz)")
    ax[0].set_ylim(-60, 80)
    ax[1].set_ylim(-270, 10)
    for a in ax:
        a.grid(alpha=0.3, which="both")
    fig.tight_layout()
    if not skip_loop:
        fig.savefig(FIG / f"loop_gain_{VER}.png", dpi=200)
    plt.close(fig)
    save()

    fig, ax = plt.subplots(figsize=(6.4, 3.4))
    skip_psrr = "psrr" in R
    R["psrr"] = R.get("psrr", {})
    for il in (0.1e-3, 50e-3):
        if skip_psrr:
            continue
        f, p = psrr(il, netfn=netfn)
        R["psrr"][f"{il*1e3:g}mA"] = {"dc": float(p[0]),
                                      "1kHz": float(np.interp(3, np.log10(f), p)),
                                      "100kHz": float(np.interp(5, np.log10(f), p)),
                                      "min": float(p.min()),
                                      "f_min": float(f[np.argmin(p)])}
        ax.semilogx(f, p, label=f"$I_L$ = {il*1e3:g} mA")
        print(f"PSRR IL={il*1e3:g} mA: " + ", ".join(
            f"{k} {v:.1f}" for k, v in R["psrr"][f"{il*1e3:g}mA"].items()))
    ax.set_xlabel("frequency (Hz)")
    ax.set_ylabel("PSRR (dB)")
    ax.grid(alpha=0.3, which="both")
    ax.legend()
    fig.tight_layout()
    if not skip_psrr:
        fig.savefig(FIG / f"psrr_{VER}.png", dpi=200)
    plt.close(fig)
    save()

    d = dc_sweep("vvin vin 0 1.8\niload vout 0 0.1m", f"iload 0.1m 50m {il_step}", "v(vout)",
                 f"loadreg_{VER}", netfn=dcfn)
    il, vo = d[:, 0], d[:, 1]
    R["loadreg"] = dict(v_light=float(vo[0]), v_heavy=float(vo[-1]), dV=float(vo[0] - vo[-1]))
    print("load reg:", R["loadreg"])
    fig, ax = plt.subplots(figsize=(6.4, 3.0))
    ax.plot(il * 1e3, vo * 1e3)
    ax.set_xlabel("$I_L$ (mA)")
    ax.set_ylabel("$V_{OUT}$ (mV)")
    ax.grid(alpha=0.3)
    fig.tight_layout()
    fig.savefig(FIG / f"load_regulation_{VER}.png", dpi=200)
    plt.close(fig)

    R["linereg"] = {}
    fig, ax = plt.subplots(figsize=(6.4, 3.2))
    for ilv in (0.1e-3, 50e-3):
        tag = f"line_{ilv*1e3:g}mA_{VER}"
        d = dc_sweep(f"vvin vin 0 1.8\niload vout 0 {ilv}", f"vvin 1.4 1.95 {vin_step}",
                     "v(vout)", tag, netfn=dcfn)
        vin, vo = d[:, 0], d[:, 1]
        slope = (np.interp(1.9, vin, vo) - np.interp(1.7, vin, vo)) / 0.2
        v_nom = float(np.interp(1.8, vin, vo))
        ok = vo >= 0.99 * v_nom
        k = int(np.argmax(ok))
        vdo = float(vin[k] - vo[k])
        R["linereg"][f"{ilv*1e3:g}mA"] = dict(slope=float(slope), v_nom=v_nom,
                                              v_at_1p7=float(np.interp(1.7, vin, vo)),
                                              VDO_1pct=vdo)
        ax.plot(vin, vo, label=f"$I_L$ = {ilv*1e3:g} mA")
        print(f"line IL={ilv*1e3:g} mA: slope={slope*1e3:.2f} mV/V, VDO(1%)={vdo*1e3:.0f} mV,"
              f" VOUT(1.7)={np.interp(1.7, vin, vo):.4f}")
    ax.plot([1.4, 1.95], [1.4, 1.95], "k:", lw=0.8, label="$V_{OUT}=V_{IN}$")
    ax.set_xlabel("$V_{IN}$ (V)")
    ax.set_ylabel("$V_{OUT}$ (V)")
    ax.set_ylim(1.3, 1.56)
    ax.grid(alpha=0.3)
    ax.legend(fontsize=8)
    fig.tight_layout()
    fig.savefig(FIG / f"line_dropout_{VER}.png", dpi=200)
    plt.close(fig)

    d = dc_sweep("vvin vin 0 1.8\niload vout 0 0.1m", "vvin 1.7 1.9 0.01", "-i(vvin)",
                 f"iq_{VER}", netfn=dcfn)
    R["iq"] = dict(at_1p8=float(np.interp(1.8, d[:, 0], d[:, 1]) - 0.1e-3),
                   max=float(d[:, 1].max() - 0.1e-3))
    print("Iq (IL = 0.1 mA subtracted):", R["iq"])
    save()

    tr, (t, vo, vg) = transient(netfn=netfn)
    R["tran"] = tr
    print("tran:", tr)
    save()
    fig, ax = plt.subplots(2, 1, figsize=(6.4, 4.6), sharex=True)
    ax[0].plot(t * 1e6, vo * 1e3)
    ax[0].set_ylabel("$V_{OUT}$ (mV)")
    ax[1].plot(t * 1e6, vg)
    ax[1].set_ylabel("$V_G$ (V)")
    ax[1].set_xlabel("time (us)")
    for a in ax:
        a.grid(alpha=0.3)
    ax[0].set_title("load step 0.1 mA -> 50 mA at 20 us, back at 120 us (1 us edges)",
                    fontsize=9)
    fig.tight_layout()
    fig.savefig(FIG / f"load_transient_{VER}.png", dpi=200)
    plt.close(fig)

    esrs = esrs or [0, 5e-3, 10e-3, 20e-3, 50e-3, 100e-3, 200e-3, 500e-3, 1.0]
    R["esr"] = {}
    for il in (0.1e-3, 50e-3):
        pms = []
        for e in esrs:
            lg = loop_gain(il, esr=max(e, 1e-6), tag=f"esr_{il*1e3:g}_{e*1e3:g}_{VER}",
                           netfn=netfn)
            pms.append((e, lg["PM"], lg["UGF"], lg["GM_dB"]))
        R["esr"][f"{il*1e3:g}mA"] = pms
        print(f"ESR sweep IL={il*1e3:g} mA:",
              ", ".join(f"{e*1e3:g}m: PM {p:.0f} GM {g:.0f}dB" for e, p, u, g in pms))
    fig, ax = plt.subplots(figsize=(6.4, 3.2))
    for il in (0.1e-3, 50e-3):
        pms = R["esr"][f"{il*1e3:g}mA"]
        ax.semilogx([max(p[0], 1e-3) for p in pms], [p[1] for p in pms], "o-",
                    label=f"$I_L$ = {il*1e3:g} mA")
    ax.axhline(45, color="k", ls=":", lw=0.8)
    ax.set_xlabel("ESR ($\\Omega$)  (first point = 0)")
    ax.set_ylabel("phase margin (deg)")
    ax.grid(alpha=0.3, which="both")
    ax.legend()
    fig.tight_layout()
    fig.savefig(FIG / f"pm_vs_esr_{VER}.png", dpi=200)
    plt.close(fig)

    save()


if __name__ == "__main__":
    main()
