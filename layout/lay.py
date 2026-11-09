"""Layout primitives for Electric's skywater130 technology (writes a command
file for electric_runtime.bsh).

Coordinates in um. Electric Fet nodes have the gate horizontal: channel width W
along x, source/drain above and below. A multi-finger device is a vertical
stack: contact row 0, gate 0, contact row 1, gate 1, ... contact row nf.
Even rows = source (S), odd rows = drain (D). Gates are joined by a vertical
poly bar on the left and contacted there.

sky130 numbers used (periphery rules):
  licon 0.17, licon-to-gate 0.055, diff enclosure of licon 0.04 / 0.06
  li1 width/space 0.17, li1 enclosure of licon 0.08 on one of two adjacent sides
  mcon 0.17 space 0.19, met1 enclosure of mcon 0.03 / 0.06
  via 0.15 space 0.17, met1 enclosure 0.055 / 0.085, met2 enclosure 0.055 / 0.085
  met1 / met2 width 0.14 space 0.14; poly width 0.15 space 0.21; poly-diff 0.075
  nwell enclosure of p+ diff 0.18; n+ diff to nwell 0.34
"""
import math
import subprocess
import pathlib

ROOT = pathlib.Path(__file__).resolve().parent
ELECTRIC = r"C:\Electric\electricBinaryFull-9.08.jar"
GRID = 0.005


def g(v):
    """snap to the 5 nm manufacturing grid"""
    return round(round(v / GRID) * GRID, 4)


class Lay:
    def __init__(self):
        self.cmd = []
        self.n = 0

    def c(self, s):
        self.cmd.append(s)

    def nid(self, p):
        self.n += 1
        return f"{p}{self.n}"

    def node(self, proto, x, y, w=0, h=0, pre="n"):
        i = self.nid(pre)
        self.c(f"N {i} {proto} {g(x)} {g(y)} {g(w)} {g(h)}")
        return i

    def arc(self, kind, w, a, pa, xa, ya, b, pb, xb, yb):
        w = round(round(w / 0.01) * 0.01, 3)      # even number of grid steps
        self.c(f"A {kind} {w} {a} {pa} {g(xa)} {g(ya)} {b} {pb} {g(xb)} {g(yb)}")

    def pin(self, layer, x, y):
        return self.node(f"{layer}-Pin", x, y, 0, 0, pre="p")

    def rect(self, layer, x0, y0, x1, y1):
        """pure-layer rectangle"""
        return self.node(layer, (x0 + x1) / 2, (y0 + y1) / 2, abs(x1 - x0), abs(y1 - y0), pre="r")

    def wire(self, layer, w, pts):
        """chain of pins joined by arcs of one layer; returns the pin ids"""
        ids = [self.pin(layer, x, y) for x, y in pts]
        for k in range(len(pts) - 1):
            self.arc(layer, w, ids[k], "-", *pts[k], ids[k + 1], "-", *pts[k + 1])
        return ids

    # ------------------------------------------------------------ contacts
    def via1(self, x, y, w=0.32, h=0.32):
        return self.node("via-X", x, y, w, h, pre="v")

    def via2(self, x, y, w=0.4, h=0.4):
        # sizes that hold a whole number of 0.2 um cuts (pitch 0.4): 0.33, 0.73, 1.13
        w = min((0.33, 0.73, 1.13), key=lambda v: abs(v - w))
        h = min((0.37, 0.77), key=lambda v: abs(v - h))
        return self.node("via2-X", x, y, w, h, pre="v")

    def via3(self, x, y, w=0.4, h=0.4):
        return self.node("via3-X", x, y, w, h, pre="v")

    def stack_m1_m3(self, x, y, w=0.6, h=0.6):
        """met1 -> met2 -> met3 via stack at one point; returns (via1, via2)"""
        v1 = self.via1(x, y, w, h)
        v2 = self.via2(x, y, w, h)
        self.arc("met2", min(w, h) - 0.06, v1, "-", x, y, v2, "-", x, y)
        return v1, v2


def mos(L_, name, kind, W, L, nf, x0, y0, nstrap=None, strap_w=None, s_ext=1.0, d_ext=1.0,
        s_end=None, d_end=None):
    """Multi-finger MOS stack. kind 'n' | 'p'. Returns a dict with the ids and
    coordinates needed for routing:
      rows      : list of (row y, mcon id)
      s_straps  : list of (x, y_end, pin id) met2 straps of the source
      d_straps  : list of (x, y_end, pin id) met2 straps of the drain
                  (strap ends at s_end / d_end if given, otherwise s_ext below
                  the bottom row / d_ext above the top row)
      gate      : (x, y, mcon id) gate contact on met1
      bbox      : (xlo, ylo, xhi, yhi) of the device geometry (without straps)
    """
    P = L + 0.28                         # row pitch (= gate pitch)
    fet = "Fet-N" if kind == "n" else "Fet-P"
    rows = []
    ys = [y0 + k * P for k in range(nf + 1)]
    # contact rows
    for k, y in enumerate(ys):
        dc = L_.node("DCont-X", x0, y, W, 0.25, pre="dc")
        mc = L_.node("mcon-X", x0, y, W - 0.1, 0.26, pre="mc")
        L_.arc("li1", 0.17, dc, "-", x0, y, mc, "-", x0, y)
        rows.append((y, dc, mc))
        if k == 0 or k == nf:
            # outer row: extend diff so that it encloses the licon by >= 0.04
            yc = y - 0.07 if k == 0 else y + 0.07     # 0.14 tall: covers the diff arc end
            r = L_.node("diff", x0, yc, W, 0.14, pre="r")
            L_.arc("diff", 0.14, r, "-", x0, yc, dc, "-", x0, y)
    # fingers
    xbar = x0 - W / 2 - 0.45
    bar_pins = []
    for k in range(nf):
        yg = ys[k] + P / 2
        f = L_.node(fet, x0, yg, 0, 0, pre="m")
        L_.c(f"SZ {f} {g(W)} {g(L)}")
        L_.arc("diff", 0.14, f, "diff-bot", x0, ys[k], rows[k][1], "-", x0, ys[k])
        L_.arc("diff", 0.14, f, "diff-top", x0, ys[k + 1], rows[k + 1][1], "-", x0, ys[k + 1])
        pp = L_.pin("poly", xbar, yg)
        gl = x0 - W / 2 - 0.19          # gate-left port of the Electric Fet node
        L_.arc("poly", L, f, "gate-left", gl, yg, pp, "-", xbar, yg)   # full gate length: no notch
        bar_pins.append((pp, yg))
    # poly bar and gate contact at mid height
    for k in range(nf - 1):
        L_.arc("poly", 0.3, bar_pins[k][0], "-", xbar, bar_pins[k][1],
               bar_pins[k + 1][0], "-", xbar, bar_pins[k + 1][1])
    ym = bar_pins[nf // 2][1] if nf > 1 else bar_pins[0][1]
    pc = L_.node("PCont-X", xbar, ym, 0.34, 0.34, pre="pc")
    L_.rect("npc", xbar - 0.185, ym - 0.185, xbar + 0.185, ym + 0.185)   # licon.15: npc encloses poly licon by 0.1
    L_.arc("poly", 0.3, bar_pins[nf // 2 if nf > 1 else 0][0], "-", xbar, ym, pc, "-", xbar, ym)
    gm = L_.node("mcon-X", xbar, ym, 0.29, 0.29, pre="mc")
    L_.arc("li1", 0.17, pc, "-", xbar, ym, gm, "-", xbar, ym)
    # met2 straps: alternate D, S, D, S ... from left to right
    if nstrap is None:
        nstrap = max(1, int(W // 2.5))       # pairs
    npos = 2 * nstrap
    pitch = W / npos
    sw = round(round((strap_w or min(1.4, pitch - 0.3)) / 0.01) * 0.01, 3)
    ytop, ybot = ys[-1], ys[0]
    if d_end is None:
        d_end = ytop + d_ext
    if s_end is None:
        s_end = ybot - s_ext
    s_straps, d_straps = [], []
    s_vias, d_vias = [], []                  # per strap: (x, [(via1 id, y), ...])
    for j in range(npos):
        xs = g(x0 - W / 2 + pitch * (j + 0.5))
        is_d = (j % 2 == 0)
        my_rows = [r for k, r in enumerate(rows) if (k % 2 == 1) == is_d]
        if not my_rows:
            continue
        vids = []
        for (y, dc, mc) in my_rows:
            v = L_.via1(xs, y, sw, 0.32)
            L_.arc("met1", 0.26, mc, "-", x0, y, v, "-", xs, y)
            vids.append((v, y))
        for k in range(len(vids) - 1):
            L_.arc("met2", sw - 0.06, vids[k][0], "-", xs, vids[k][1], vids[k + 1][0], "-", xs, vids[k + 1][1])
        yend = d_end if is_d else s_end
        # strap leaves from the via closest to its end point
        vfrom = vids[-1] if yend > vids[-1][1] else vids[0]
        p = L_.pin("met2", xs, yend)
        L_.arc("met2", sw - 0.06, vfrom[0], "-", xs, vfrom[1], p, "-", xs, yend)
        (d_straps if is_d else s_straps).append((xs, yend, p))
        (d_vias if is_d else s_vias).append((xs, vids))
    imp = "nsdm" if kind == "n" else "psdm"
    L_.rect(imp, x0 - W / 2 - 0.125, ybot - 0.255, x0 + W / 2 + 0.125, ytop + 0.255)
    bbox = (xbar - 0.2, ybot - 0.3, x0 + W / 2, ytop + 0.3)
    return dict(name=name, rows=rows, s_straps=s_straps, d_straps=d_straps,
                s_vias=s_vias, d_vias=d_vias,
                gate=(xbar, ym, gm), bbox=bbox, W=W, L=L, nf=nf, kind=kind,
                strap_w=sw)


def run_electric(cmd_lines, tag, timeout=900):
    cmdf = ROOT / f"{tag}.cmd"
    cmdf.write_text("\n".join(cmd_lines) + "\n")
    res = subprocess.run(["java", f"-Dldo.cmd={cmdf}", "-jar", ELECTRIC, "-batch", "-s",
                          str(ROOT / "electric_runtime.bsh")],
                         cwd=str(ROOT), capture_output=True, text=True, timeout=timeout)
    out = res.stdout + res.stderr
    (ROOT / f"{tag}.log").write_text(out)
    return out
