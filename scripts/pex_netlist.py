"""Post-layout netlist of the LDO for ngspice, from the KLayout-PEX (2.5D, RC)
extraction of layout/ldo_final.gds.

prepare() reads layout/pex/ldo_final__ldo/ldo_k25d_pex_netlist.spice and writes
sim/ldo_pex.sub:
  * node / device names cleaned for ngspice ('\\' dropped, '$' -> 'S')
  * the gate terminals of M2 (the OTA input on the feedback side) moved to a
    new port fbi, and the node they sat on exported as port fb, so that the
    loop can be broken at the same point as in the schematic (ldo_netlist.core)
  * the substrate port sky130_gnd is tied to gnd in core_pex() (the p-taps
    connect the substrate to gnd; the 2.5D engine has no substrate resistance)

core_pex() has the same signature and off-chip parts as ldo_netlist.core().
"""
import os
import pathlib

from ldo_netlist import LIB, load_sizes

ROOT = pathlib.Path(__file__).resolve().parent.parent
PEXDIR = ROOT / "layout" / "pex" / "ldo_final__ldo"
# full RC netlist, or the TICER-reduced one (tau = 10 ps) for AC / transient runs
RAW = PEXDIR / os.environ.get("LDO_PEX_NET", "ldo_k25d_pex_netlist_ticer10p.spice")
SUB = ROOT / "sim" / "ldo_pex.sub"
SUB_DC = ROOT / "sim" / "ldo_pex_dc.sub"


def _clean(tok):
    return tok.replace("\\", "").replace("$", "S")


def prepare():
    lines = []
    for raw in RAW.read_text().splitlines():
        if raw.startswith("+") and lines:
            lines[-1] += " " + raw[1:].strip()
        elif raw.strip() and not raw.startswith("*"):
            lines.append(raw.strip())
    head = [l for l in lines if l.upper().startswith(".SUBCKT")][0]
    ports = head.split()[2:]
    devs = [l.split() for l in lines if l[0] in "XRC"]

    # vref gate nets and the bias net, to recognise M1 / MT / MBN
    def base(n):
        return n.split(".")[0]

    nf = [d for d in devs if d[0].startswith("X") and "sky130_fd_pr__nfet_01v8" in d]
    # OTA input pair: nfet with L = 1 and W = 8 (two 8 um fingers per device)
    pair = [d for d in nf if "l=1" in d and "w=8" in d]
    gate_nets = {base(d[2]) for d in pair}
    fb_nets = [g for g in gate_nets if g != "vref"]
    assert len(fb_nets) == 1, f"cannot identify the feedback net: {gate_nets}"
    fbn = fb_nets[0]
    m2 = [d for d in pair if base(d[2]) == fbn]
    assert len(m2) == 2, f"expected 2 fingers of M2, found {len(m2)}"
    fb_node = m2[0][2]
    for d in m2:
        d[2] = "fbi"

    # written flat (top level), not as a .subckt: ngspice's subcircuit
    # expansion of ~1e5 elements takes more than 10 minutes, flat it does not.
    # Port nets are renamed to the top-level names used by core_pex().
    top = {"gnd": "0", "sky130_gnd": "0", "ibias": "nb"}

    def node(t):
        # only the port nodes themselves; sub-nodes such as gnd.P0.poly are
        # internal parasitic nodes joined to the port node by extracted resistors
        return top.get(t, _clean(t))

    # probe node g = gate net of the pass device (named as in the schematic, for
    # sim_all.transient); joined by 1 ohm to a node that carries no current
    mp = [d for d in devs if d[0].startswith("X") and "sky130_fd_pr__pfet_01v8" in d
          and "l=0.15" in d and (d[1].startswith("vout") or d[3].startswith("vout"))]
    g_net = base(mp[0][2])
    assert all(base(d[2]) == g_net for d in mp), "pass fingers on different gate nets"
    out = [f"* post-layout LDO (KLayout-PEX 2.5D RC) from {RAW.name}, flat",
           f"rfbtap {_clean(fb_node)} fb 1e-3",
           f"rgprobe {_clean(g_net)} g 1"]
    for d in devs:
        nn = {"X": len(d) - 1 - sum("=" in t for t in d) - 1, "R": 2, "C": 2}[d[0][0]]
        out.append(" ".join([_clean(d[0])] + [node(t) for t in d[1:1 + nn]] +
                            [_clean(t) for t in d[1 + nn:]]))
    SUB.write_text("\n".join(out) + "\n")
    # DC variant: the capacitors do not enter a DC solution, and without them
    # ngspice sets the circuit up in seconds instead of minutes
    SUB_DC.write_text("\n".join(l for l in out if not l.startswith("C")) + "\n")
    n_r = sum(d[0].startswith("R") for d in devs)
    n_c = sum(d[0].startswith("C") for d in devs)
    n_x = sum(d[0].startswith("X") for d in devs)
    return dict(ports=ports, fb_net=fbn, fb_node=fb_node, g_net=g_net, devices=n_x, R=n_r, C=n_c)


def core_pex(S=None, loop_break=False, esr=None, cl=None, corner="tt", vref=None, dc=False):
    s = S or load_sizes()
    esr = s["ESR"] if esr is None else esr
    cl = s["CL"] if cl is None else cl
    vref = s["VREF"] if vref is None else vref
    L = [f'.lib "{LIB}" {corner}',
         f'.include "{(SUB_DC if dc else SUB).as_posix()}"',      # flat: nets 0, nb, vin, vout, vref, fb, fbi
         f"ibias vin nb {s['IBIAS']}",
         f"vref vref 0 {vref}",
         f"cl vout nesr {cl}", f"resr nesr 0 {esr}",
         f".nodeset v(vout)={s['VOUT']} v(fb)={vref} v(fbi)={vref}",
         ".option noopiter gminsteps=0"]
    if loop_break:
        L += ["lbrk fb fbi 1e9", "cbrk fbi vt 1e3", "vt vt 0 dc 0 ac 1"]
    else:
        L += ["rshort fb fbi 1e-3"]
    return "\n".join(L)


if __name__ == "__main__":
    print(prepare())


def core_pex_dc(**kw):
    """resistor-only post-layout netlist, for DC analyses"""
    return core_pex(dc=True, **kw)
