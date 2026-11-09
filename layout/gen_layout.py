"""Generate the sky130 LDO layout and schematic in Electric (library ldo_sky130).

Floorplan (um, y up):
  y ~ 35        vin rail (met3) over an n-tap strip
  y 16.5..34    nwell: PMOS row (M3, M4, MBL, MD) and the pass device MP
                (4 columns x 40 fingers, W = 10 um, L = 0.15 um)
  y 15.4        vout rail (met3), under the pass array only
  y 7..14.2     signal tracks (met3): nb, tail, vref, fb, ea, d1, g
  y 0..5        NMOS row (MBN, MT, M1, M2, MCS)
  y -2.0        tail track for the M1/M2 sources
  y -3.6        gnd rail (met3) over a p-tap strip
  left          feedback divider: 6 xhigh_po units + 2 dummies (black-box cell rxh)
Device terminals reach the tracks through vertical met2 straps (drains / sources)
and met2 stubs (gates); via2 where a strap or stub meets its track.
vout to the divider: a met4 line from the vout rail (sense line, no load current).
"""
import json
import pathlib
import sys
from lay import Lay, mos, run_electric, g, ROOT

S = json.loads((ROOT.parent / "scripts" / "sizes.json").read_text())

# ------------------------------------------------------------------ tracks
TR = {"nb": 7.0, "tail": 8.2, "vref": 9.4, "fb": 10.6, "ea": 11.8, "d1": 13.0, "g": 14.2}
TW = 0.6                       # signal track width (met3)
Y_TAILB = -2.0
Y_GND, W_GND = -3.6, 1.6
Y_VOUT, W_VOUT = 15.6, 1.0     # under the pass array, just below the nwell
Y_PROW = 17.0                  # row 0 of the PMOS devices and the pass columns
NCOL, NF_COL = 4, 40
X_PASS0, PASS_PITCH = 89.0, 13.0


class Net:
    """Collects via2 points per net and draws the met3 track through them."""
    def __init__(self, L_):
        self.L = L_
        self.pts = {}

    def add(self, net, x, y, vid):
        self.pts.setdefault((net, y), []).append((x, vid))

    def draw(self, widths):
        for (net, y), pts in self.pts.items():
            pts.sort()
            w = widths.get(net, TW)
            for k in range(len(pts) - 1):
                self.L.arc("met3", w, pts[k][1], "-", pts[k][0], y, pts[k + 1][1], "-", pts[k + 1][0], y)


def strap_to_track(L_, nets, net, x, y, pin, sw):
    """strap end pin (met2) -> via2 -> track at the same point"""
    v2 = L_.via2(x, y, max(0.4, min(sw, 1.2)), 0.6 if net not in ("gnd", "vin", "vout") else 0.6)
    L_.arc("met2", 0.3, pin, "-", x, y, v2, "-", x, y)
    nets.add(net, x, y, v2)


def gate_to_track(L_, nets, net, dev, ytrack):
    """gate contact (met1) -> via1 -> met2 stub -> via2 -> track"""
    xg, yg, gm = dev["gate"]
    v1 = L_.via1(xg, yg, 0.32, 0.32)
    L_.arc("met1", 0.29, gm, "-", xg, yg, v1, "-", xg, yg)
    v2 = L_.via2(xg, ytrack, 0.4, 0.6)
    L_.arc("met2", 0.3, v1, "-", xg, yg, v2, "-", xg, ytrack)
    nets.add(net, xg, ytrack, v2)


def tap_strip(L_, kind, x0, x1, y, nets, net, stack_pitch=3.0):
    """Well / substrate tap strip (pure layers: tap, implant, licon, li1, mcon,
    met1) with via1 + via2 stacks into the rail of `net` every stack_pitch.
    kind 'n' = n+ tap in nwell (nsdm), 'p' = p+ substrate tap (psdm)."""
    h = 0.5
    L_.rect("tap", x0, y - h / 2, x1, y + h / 2)
    L_.rect("nsdm" if kind == "n" else "psdm", x0 - 0.125, y - h / 2 - 0.125, x1 + 0.125, y + h / 2 + 0.125)
    L_.rect("li1", x0 + 0.02, y - 0.17, x1 - 0.02, y + 0.17)
    n = int((x1 - x0 - 0.3) // 0.5)
    xs0 = x0 + (x1 - x0 - (n - 1) * 0.5) / 2
    for k in range(n):
        xc = xs0 + k * 0.5
        L_.rect("licon1", xc - 0.085, y - 0.085, xc + 0.085, y + 0.085)
        if k % 2 == 0:
            L_.rect("mcon", xc - 0.085, y - 0.085, xc + 0.085, y + 0.085)
    m = int((x1 - x0 - 1.0) // stack_pitch) + 1
    taken = [x for x, _ in nets.pts.get((net, y), [])]
    # met1 of the strip as a connected wire through the via1 nodes
    chain = [(L_.pin("met1", x0 + 0.19, y), x0 + 0.19)]
    for k in range(m):
        xc = x0 + 0.5 + k * stack_pitch
        if xc > x1 - 0.5:
            break
        if any(abs(xc - xt) < 1.5 for xt in taken):
            continue                      # a strap via2 already sits here
        v1 = L_.via1(xc, y, 0.32, 0.32)
        chain.append((v1, xc))
        v2 = L_.via2(xc, y, 0.4, 0.4)
        L_.arc("met2", 0.3, v1, "-", xc, y, v2, "-", xc, y)
        nets.add(net, xc, y, v2)
    chain.append((L_.pin("met1", x1 - 0.19, y), x1 - 0.19))
    for k in range(len(chain) - 1):
        L_.arc("met1", 0.34, chain[k][0], "-", chain[k][1], y, chain[k + 1][0], "-", chain[k + 1][1], y)


# ------------------------------------------------------------- resistors
RU_L = S["L_RU"]               # body length of one unit (um)
RU_HEAD = 2.08                 # poly head beyond the body, holds the 0.19 x 2.0 contact slot
RU_W = 0.35
RU_PITCH = 1.4


def rxh_cell(L_):
    """Unit xhigh_po resistor, 0.35 um wide, as a black-box cell rxh{lay} with
    exports a (bottom end) and b (top end) on met1. Geometry follows the sky130
    xhigh_po device: poly body + heads, 0.19 x 2.0 licon slots, li1, mcon, met1,
    urpm + psdm cover. (The poly_rs marker 66/13 has no layer in Electric's
    skywater130 technology; add_marker.py adds it to the GDS.)"""
    tot = RU_L + 2 * RU_HEAD
    L_.c("CELL rxh lay")
    L_.c("CVAR NCC blackBox unit xhigh_po resistor; geometry checked by DRC")
    L_.rect("poly", -RU_W / 2, -tot / 2, RU_W / 2, tot / 2)
    ends = {}
    for nm, sgn in (("a", -1), ("b", 1)):
        yc = sgn * (RU_L / 2 + RU_HEAD / 2)          # centre of the head
        L_.rect("licon1", -0.095, yc - 1.0, 0.095, yc + 1.0)
        L_.rect("li1", -0.175, yc - 1.08, 0.175, yc + 1.08)
        L_.rect("npc", -0.195, yc - 1.1, 0.195, yc + 1.1)
        for k in range(-2, 3):
            L_.rect("mcon", -0.085, yc + 0.36 * k - 0.085, 0.085, yc + 0.36 * k + 0.085)
        pins = L_.wire("met1", 0.35, [(0, yc - 0.9), (0, yc), (0, yc + 0.9)])
        L_.c(f"E {nm} {pins[1]} - bidir")
        ends[nm] = yc
    return ends, tot


def rxh_sch(L_):
    L_.c("CELL rxh sch")
    L_.c("CVAR NCC blackBox unit xhigh_po resistor; geometry checked by DRC")
    # black box: only the two terminals (a resistor primitive would be merged
    # away by NCC and short a to b)
    pa = L_.node("sch:Wire_Pin", 0, -3, 0, 0, pre="p")
    pb = L_.node("sch:Wire_Pin", 0, 3, 0, 0, pre="p")
    L_.c(f"E a {pa} - bidir")
    L_.c(f"E b {pb} - bidir")
    return pa


def build():
    L_ = Lay()
    lib = (ROOT / "ldo_sky130.jelib").as_posix()
    L_.c(f"LIB {lib} ldo_sky130")
    ends, tot = rxh_cell(L_)

    L_.c("CELL ldo lay")
    nets = Net(L_)

    # ---------------------------------------------------------- NMOS row
    yb = 0.0
    nmos = {}
    spec_n = [  # name, x0, W(finger), L, nf, s net, d net, g net
        ("mbn", 0.0, S["WB"], S["LB"], S["MBN_M"], "gnd", "nb", "nb"),
        ("mt", 7.0, S["WB"], S["LB"], S["MT_M"], "gnd", "tail", "nb"),
        ("m1", 15.0, S["W12"] / 2, S["L12"], 2 * S["M12"], "tailb", "d1", "vref"),
        ("m2", 25.0, S["W12"] / 2, S["L12"], 2 * S["M12"], "tailb", "ea", "fb"),
        ("mcs", 37.0, S["WCS"], S["LCS"], S["MCS_M"], "gnd", "g", "ea"),
    ]
    for nm, x0, W, L, nf, sn, dn, gn in spec_n:
        s_end = Y_GND if sn == "gnd" else Y_TAILB
        d = mos(L_, nm, "n", W, L, nf, x0, yb, s_end=s_end, d_end=TR[dn])
        for xs, ye, p in d["s_straps"]:
            strap_to_track(L_, nets, "gnd" if sn == "gnd" else "tail", xs, ye, p, d["strap_w"])
        for xs, ye, p in d["d_straps"]:
            strap_to_track(L_, nets, dn, xs, ye, p, d["strap_w"])
        gate_to_track(L_, nets, gn, d, TR[gn])
        nmos[nm] = (d, sn, dn, gn)
    # tail jumper: bottom tail track <-> mid tail track (met2, between MT and M1)
    xj = 10.0
    va = L_.via2(xj, Y_TAILB, 0.4, 0.6)
    vb = L_.via2(xj, TR["tail"], 0.4, 0.6)
    L_.arc("met2", 0.4, va, "-", xj, Y_TAILB, vb, "-", xj, TR["tail"])
    nets.add("tail", xj, Y_TAILB, va)
    nets.add("tail", xj, TR["tail"], vb)


    # ---------------------------------------------------------- PMOS row
    spec_p = [  # name, x0, W, L, nf, d net, g net   (sources = vin, up)
        ("m3", 50.0, S["W34"] / 2, S["L34"], 2 * S["M34"], "d1", "d1"),
        ("m4", 60.0, S["W34"] / 2, S["L34"], 2 * S["M34"], "ea", "d1"),
        ("mbl", 68.0, S["WBL"], S["LBL"], S["MBL_M"], "g", "d1"),
        ("md", 77.0, S["WPf"], S["LP"], S["MD_M"], "g", "g"),
    ]
    pass_top = Y_PROW + NF_COL * (S["LP"] + 0.28)
    Y_VTAP = pass_top + 1.0
    Y_VIN = Y_VTAP
    pmos = {}
    for nm, x0, W, L, nf, dn, gn in spec_p:
        d = mos(L_, nm, "p", W, L, nf, x0, Y_PROW, s_end=Y_VIN, d_end=TR[dn])
        for xs, ye, p in d["s_straps"]:
            strap_to_track(L_, nets, "vin", xs, ye, p, d["strap_w"])
        for xs, ye, p in d["d_straps"]:
            strap_to_track(L_, nets, dn, xs, ye, p, d["strap_w"])
        gate_to_track(L_, nets, gn, d, TR[gn])
        pmos[nm] = d

    # ---------------------------------------------------------- pass device
    cols = []
    for c in range(NCOL):
        x0 = X_PASS0 + c * PASS_PITCH
        d = mos(L_, f"mp{c}", "p", S["WPf"], S["LP"], NF_COL, x0, Y_PROW, nstrap=3,
                s_end=Y_VIN, d_end=Y_VOUT)
        for xs, ye, p in d["s_straps"]:
            strap_to_track(L_, nets, "vin", xs, ye, p, d["strap_w"])
        for xs, ye, p in d["d_straps"]:
            strap_to_track(L_, nets, "vout", xs, ye, p, d["strap_w"])
        gate_to_track(L_, nets, "g", d, TR["g"])
        cols.append(d)

    # ---------------------------------------------------------- power plates
    # EM: the 50 mA load current must not run along a narrow rail. met3 + met4
    # plates over the pass array, vout over the lower half and vin over the
    # upper half. Each drain (source) row inside the vout (vin) plate gets a
    # via2 from its met2 strap; the via2s of one strap are chained by met3 to
    # the strap's rail via2, so Electric sees the connection; via3 arrays join
    # the met3 and met4 plates. Pins vin / vout sit on the plates (exports below).
    y_top = Y_PROW + NF_COL * (S["LP"] + 0.28)
    y_mid = (Y_PROW + y_top) / 2
    px0, px1 = cols[0]["bbox"][0] - 0.2, cols[-1]["bbox"][2] + 0.5
    plates = {"vout": (Y_VOUT - W_VOUT / 2, y_mid - 0.35, Y_VOUT, "d_vias"),
              "vin": (y_mid + 0.35, Y_VIN + 1.0, Y_VIN, "s_vias")}
    for net, (yb_, yt_, y_rail, key) in plates.items():
        L_.rect("met3", px0, yb_, px1, yt_)
        L_.rect("met4", px0, yb_, px1, yt_)
        rail = {round(x, 3): vid for x, vid in nets.pts[(net, y_rail)]}
        for d in cols:
            sw = d["strap_w"]
            for xs, vids in d[key]:
                inside = [(vid, y) for vid, y in vids if yb_ + 0.3 <= y <= yt_ - 0.3]
                chain = [(rail[round(xs, 3)], y_rail)]
                for vid, y in inside:
                    v2 = L_.via2(xs, y, sw, 0.77)            # 3 x 2 cuts
                    L_.arc("met2", sw - 0.06, vid, "-", xs, y, v2, "-", xs, y)
                    chain.append((v2, y))
                chain.sort(key=lambda t: t[1])
                for (va, ya), (vb, yb2) in zip(chain, chain[1:]):
                    L_.arc("met3", 0.4, va, "-", xs, ya, vb, "-", xs, yb2)
            # via3 arrays (met3 plate <-> met4 plate): 2 rows x 4 per column
            x0c = (d["bbox"][0] + d["bbox"][2]) / 2
            for xv in (x0c - 4.5, x0c - 1.5, x0c + 1.5, x0c + 4.5):
                for yv in (yb_ + (yt_ - yb_) * 0.27, yb_ + (yt_ - yb_) * 0.73):
                    L_.via3(xv, yv, 2.0, 2.0)
    X_PIN = (px0 + px1) / 2                  # vin / vout pins: plate centre

    # nwell over the PMOS row and the pass array, n-tap strip under the vin rail
    x_nw0 = pmos["m3"]["bbox"][0] - 1.0
    x_nw1 = cols[-1]["bbox"][2] + 1.0
    L_.rect("nwell", x_nw0, Y_PROW - 1.0, x_nw1, Y_VTAP + 0.8)
    tap_strip(L_, "n", x_nw0 + 0.6, x_nw1 - 0.6, Y_VTAP, nets, "vin")

    # ---------------------------------------------------------- divider
    # units left of the NMOS row, poly vertical; order: D u1 u2 u3 u4 u5 u6 D
    xr0 = -18.0
    yr = (Y_GND + 2.0) + tot / 2 + 0.5         # centre of the units
    units = []
    for k in range(8):
        xk = xr0 + k * RU_PITCH
        L_.c(f"I r{k} rxh{{lay}} {g(xk)} {g(yr)}")
        units.append((f"r{k}", xk))
    L_.rect("urpm", xr0 - 0.8, yr - tot / 2 - 0.6, xr0 + 7 * RU_PITCH + 0.8, yr + tot / 2 + 0.6)
    L_.rect("psdm", xr0 - 0.6, yr - tot / 2 - 0.4, xr0 + 7 * RU_PITCH + 0.6, yr + tot / 2 + 0.4)
    ya, ybb = yr + ends["a"], yr + ends["b"]

    def rpin(k, end):
        return units[k][0], end, units[k][1], (ya if end == "a" else ybb)

    def jump(k1, e1, k2, e2):
        i1, p1, x1, y1 = rpin(k1, e1)
        i2, p2, x2, y2 = rpin(k2, e2)
        L_.arc("met1", 0.35, i1, p1, x1, y1, i2, p2, x2, y2)

    # chain: vout - u1(a..b) - u2(b..a) = fb - u3(a..b) - u4(b..a) - u5(a..b) - u6(b..a) = gnd
    jump(1, "b", 2, "b")
    jump(2, "a", 3, "a")
    jump(3, "b", 4, "b")
    jump(4, "a", 5, "a")
    jump(5, "b", 6, "b")
    # dummies: both ends to gnd (r0, r7)
    # terminals: u1.a = vout, u2.a/u3.a = fb, u6.a = gnd ; dummies a ends to gnd
    def term(k, end, net, y_to):
        i, p, x, y = rpin(k, end)
        v1 = L_.via1(x, y, 0.32, 0.32)
        L_.arc("met1", 0.35, i, p, x, y, v1, "-", x, y)
        return v1, x, y

    # gnd: u6.a and the dummies' a ends, down to the gnd rail by met2
    for k in (0, 6, 7):
        v1, x, y = term(k, "a", "gnd", Y_GND)
        v2 = L_.via2(x, Y_GND, 0.4, 0.6)
        L_.arc("met2", 0.3, v1, "-", x, y, v2, "-", x, Y_GND)
        nets.add("gnd", x, Y_GND, v2)
    for k in (0, 7):                               # dummy b ends tied to their a ends
        i, p, x, y = rpin(k, "b")
        i2, p2, x2, y2 = rpin(k, "a")
        L_.arc("met1", 0.35, i, p, x, y, i2, p2, x2, y2)
    # fb: u2.a (joined to u3.a) up to the fb track by met2
    v1, x, y = term(2, "a", "fb", TR["fb"])
    # route: met2 down-left is blocked by the units; go straight up past the top heads
    v2 = L_.via2(x, TR["fb"], 0.4, 0.6)
    L_.arc("met2", 0.3, v1, "-", x, y, v2, "-", x, TR["fb"])
    nets.add("fb", x, TR["fb"], v2)
    # vout: u1.a -> met2 -> via3 -> met4 sense line to the vout rail
    v1, x, y = term(1, "a", "vout", None)
    y_s = Y_TAILB - 0.0
    v2 = L_.via2(x, y, 0.4, 0.4)
    L_.arc("met2", 0.3, v1, "-", x, y, v2, "-", x, y)
    v3 = L_.via3(x, y, 0.4, 0.4)
    L_.arc("met3", 0.4, v2, "-", x, y, v3, "-", x, y)
    L_.rect("met3", x - 0.3, y - 0.3, x + 0.3, y + 0.3)   # landing pad: m3.6 needs area >= 0.24 um^2
    # met4 from the divider up to the vout rail level, then right to the pass array
    xr = cols[0]["d_straps"][0][0]
    v3r = L_.via3(xr, Y_VOUT, 0.4, 0.4)
    nets.add("vout", xr, Y_VOUT, v3r)          # via3 sits on the vout rail (met3)
    pk = L_.pin("met4", x, Y_VOUT)
    L_.arc("met4", 0.6, v3, "-", x, y, pk, "-", x, Y_VOUT)
    L_.arc("met4", 0.6, pk, "-", x, Y_VOUT, v3r, "-", xr, Y_VOUT)

    # p-substrate tap strip under the gnd rail (from the divider to MCS)
    tap_strip(L_, "p", -21.0, 43.0, Y_GND, nets, "gnd")

    # ---------------------------------------------------------- tracks
    nets.draw({"gnd": W_GND, "vin": 2.0, "vout": W_VOUT})

    # ---------------------------------------------------------- exports
    def export_at(net, y, name, kind):
        pts = sorted(nets.pts[(net, y)])
        if net in ("vin", "vout"):            # on the power plate, near its centre
            pts.sort(key=lambda p: abs(p[0] - X_PIN))
        L_.c(f"E {name} {pts[0][1]} - {kind}")
    export_at("vin", Y_VIN, "vin", "pwr")
    export_at("gnd", Y_GND, "gnd", "gnd")
    export_at("vout", Y_VOUT, "vout", "out")
    export_at("vref", TR["vref"], "vref", "in")
    export_at("nb", TR["nb"], "ibias", "in")

    geom = dict(Y_VIN=Y_VIN, Y_VOUT=Y_VOUT, Y_GND=Y_GND, TR=TR, cols=len(cols))
    return L_, geom


def schematic(L_):
    """ldo{sch}: same devices and nets, for NCC. Transistor W is the total width
    (fingers merged by NCC), resistors are rxh{sch} instances (black boxes)."""
    rxh_sch(L_)
    L_.c("CELL ldo sch")
    pins = {}

    def netpin(net):
        if net not in pins:
            pins[net] = L_.node("sch:Wire_Pin", 100 + 10 * len(pins), 100, 0, 0, pre="w")
        return pins[net]

    devs = [  # name, kind, Wtot, L, d, g, s
        ("mbn", "nmos", S["WB"] * S["MBN_M"], S["LB"], "nb", "nb", "gnd"),
        ("mt", "nmos", S["WB"] * S["MT_M"], S["LB"], "tail", "nb", "gnd"),
        ("m1", "nmos", S["W12"] * S["M12"], S["L12"], "d1", "vref", "tail"),
        ("m2", "nmos", S["W12"] * S["M12"], S["L12"], "ea", "fb", "tail"),
        ("mcs", "nmos", S["WCS"] * S["MCS_M"], S["LCS"], "g", "ea", "gnd"),
        ("m3", "pmos", S["W34"] * S["M34"], S["L34"], "d1", "d1", "vin"),
        ("m4", "pmos", S["W34"] * S["M34"], S["L34"], "ea", "d1", "vin"),
        ("mbl", "pmos", S["WBL"] * S["MBL_M"], S["LBL"], "g", "d1", "vin"),
        ("md", "pmos", S["WPf"] * S["MD_M"], S["LP"], "g", "g", "vin"),
        ("mp", "pmos", S["WPf"] * NCOL * NF_COL, S["LP"], "vout", "g", "vin"),
    ]
    for k, (nm, kind, W, L, dn, gn, sn) in enumerate(devs):
        x, y = 10 * k, 0
        t = L_.node("sch:Transistor", x, y, 0, 0, pre="T")
        L_.c(f"FN {t} {kind}")
        L_.c(f"SZ {t} {g(W)} {g(L)}")
        for port, net in (("d", dn), ("g", gn), ("s", sn)):
            w = netpin(net)
            L_.c(f"A sch:wire 0 {t} {port} c c {w} - c c")
    # divider units, (a, b) nets in the same order and orientation as the layout
    # serpentine: R0 / R7 dummies, R1..R2 = R1 (vout -> fb), R3..R6 = R2 (fb -> gnd)
    chain = [("gnd", "gnd"), ("vout", "n1"), ("fb", "n1"), ("fb", "n2"), ("n3", "n2"),
             ("n3", "n4"), ("gnd", "n4"), ("gnd", "gnd")]
    for k, (na, nb_) in enumerate(chain):
        L_.c(f"I R{k} rxh{{sch}} {200 + 10 * k} 0")
        for port, net in (("a", na), ("b", nb_)):
            w = netpin(net)
            L_.c(f"A sch:wire 0 R{k} {port} c c {w} - c c")
    for net, name, kind in (("vin", "vin", "pwr"), ("gnd", "gnd", "gnd"), ("vout", "vout", "out"),
                            ("vref", "vref", "in"), ("nb", "ibias", "in")):
        L_.c(f"E {name} {netpin(net)} - {kind}")


if __name__ == "__main__":
    L_, geom = build()
    schematic(L_)
    L_.c("SAVE")
    L_.c("DRC ldo{lay}")
    L_.c(f"DUMP ldo{{lay}} {(ROOT / 'ldo.dump').as_posix()}")
    L_.c(f"GDS {(ROOT / 'ldo_electric.gds').as_posix()} ldo{{lay}}")
    L_.c("NCC ldo{lay} ldo{sch}")
    out = run_electric(L_.cmd, "ldo")
    keep = [l for l in out.splitlines() if (l.startswith(("ERR", "DRCRESULT", "RUNTIME", "NCC"))
            or "rror" in l or "mismatch" in l.lower()) and not l.startswith("DRCMSG")]
    print("\n".join(keep[:80]))
    drc = [l for l in out.splitlines() if l.startswith("DRCMSG")]
    print(len(drc), "DRC messages")
    import collections
    kinds = collections.Counter(l.split("[rule")[-1] for l in drc)
    print(kinds.most_common(30))
    (ROOT / "geom.json").write_text(json.dumps(geom))
