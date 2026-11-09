"""Electromigration check of the pass-device power path (IL = 50 mA, DC).

Limits: SkyWater tech LEF sky130_fd_sc_hd.tlef (DCCURRENTDENSITY AVERAGE, Tj = 90 C):
  met1/met2 2.8 mA/um, met3/met4 6.8 mA/um, met5 10.17 mA/um,
  per cut: mcon 0.36, via 0.29, via2 0.48, via3 0.48, via4 2.49 mA.

Method: worst-case bound per element, i.e. the whole current a branch can
carry is assumed to pass through its narrowest element (no current sharing).
Cut counts are measured on ldo_final.gds; widths are measured on the GDS too.
Load current per finger = IL / (number of pass fingers).

    ..\\.venv_pex\\Scripts\\python em_check.py        (needs the klayout module)
"""
import json
import pathlib

import klayout.db as db

ROOT = pathlib.Path(__file__).resolve().parent
S = json.loads((ROOT.parent / "scripts" / "sizes.json").read_text())
IL = 50e-3
LIM_W = {"met1": 2.8, "met2": 2.8, "met3": 6.8, "met4": 6.8}            # mA/um
LIM_CUT = {"mcon": 0.36, "via": 0.29, "via2": 0.48, "via3": 0.48}       # mA per cut
LAY = {"met1": (68, 20), "met2": (69, 20), "met3": (70, 20), "met4": (71, 20),
       "mcon": (67, 44), "via": (68, 44), "via2": (69, 44), "via3": (70, 44)}

ly = db.Layout()
ly.read(str(ROOT / "ldo_final.gds"))
top = ly.cell("ldo")
um = ly.dbu


def region(name):
    r = db.Region(top.begin_shapes_rec(ly.layer(*LAY[name])))
    r.merge()
    return r


def box(x0, y0, x1, y1):
    return db.Region(db.Box(int(x0 / um), int(y0 / um), int(x1 / um), int(y1 / um)))


# pass array geometry (same constants as gen_layout.py)
NCOL, NF = 4, 40
W, LP = S["WPf"], S["LP"]
X0, PITCH, Y0 = 89.0, 13.0, 17.0
ROW = LP + 0.28
y_top = Y0 + NF * ROW
y_mid = (Y0 + y_top) / 2
nf_total = NCOL * NF
i_f = IL / nf_total * 1e3                    # mA per finger
i_row = 2 * i_f                              # inner S/D row feeds two fingers
nstrap = 3                                   # strap pairs per column
PLATE = {"vout": (15.1, y_mid - 0.35), "vin": (y_mid + 0.35, 36.2)}   # as gen_layout.py


def strap_bound(net):
    """Current of the rows of one type that have no via2 of their own (outside
    the plate), all flowing along one strap into the first plate via2; edge
    rows (k = 0, NF) feed one finger, inner rows two; split over nstrap straps."""
    yb, yt = PLATE[net]
    ks = range(1, NF, 2) if net == "vout" else range(0, NF + 1, 2)
    tot = 0.0
    for k in ks:
        y = Y0 + k * ROW
        if not (yb + 0.3 <= y <= yt - 0.3):
            tot += i_f if k in (0, NF) else i_row
    return tot / nstrap


i_strap = {net: strap_bound(net) for net in PLATE}
i_strap_max = max(i_strap.values())

rows = []


def report(item, i_ma, cap_ma, note=""):
    ok = i_ma <= cap_ma
    rows.append((item, i_ma, cap_ma, ok, note))


# 1. mcon per contact row (count on the first inner row of column 0)
x0 = X0
cuts_mcon = box(x0 - W / 2, Y0 + ROW - 0.15, x0 + W / 2, Y0 + ROW + 0.15) & region("mcon")
n = cuts_mcon.count()
report("mcon, one S/D row", i_row, n * LIM_CUT["mcon"], f"{n} cuts")

# 2. met1 bar of a row (0.26 um wide arcs from the mcon bar to each via1)
m1 = box(x0 - W / 2 - 1, Y0 + ROW - 0.2, x0 + W / 2 + 1, Y0 + ROW + 0.2).interacting(
    box(x0 - 0.01, Y0 + ROW - 0.01, x0 + 0.01, Y0 + ROW + 0.01))
m1 = region("met1").interacting(box(x0 - 0.01, Y0 + ROW - 0.01, x0 + 0.01, Y0 + ROW + 0.01))
h_m1 = m1.bbox().height() * um                # the bar through the row centre
report("met1 row bar (all row current, one side)", i_row, h_m1 * LIM_W["met1"], f"height {h_m1:.2f} um")

# 3. via1 per row per strap
v1 = box(x0 - W / 2, Y0 + ROW - 0.2, x0 + W / 2, Y0 + ROW + 0.2) & region("via")
per_strap = v1.count() / nstrap
report("via1, one row into one strap (whole row)", i_row, per_strap * LIM_CUT["via"], f"{per_strap:.0f} cuts")

# 4. met2 straps: narrowest strap width inside the array
m2 = box(x0 - W / 2, y_mid - 0.1, x0 + W / 2, y_mid + 0.1) & region("met2")
w_m2 = min(p.bbox().width() for p in m2.each()) * um
report("met2 strap at the plate edge", i_strap_max, w_m2 * LIM_W["met2"], f"width {w_m2:.2f} um")

# 5. via2 per plate via node (the node next to the plate edge takes the strap current)
for net, (yb, yt) in PLATE.items():
    # only the via2 cuts on the straps of this net (drain straps j = 0, 2, 4 under
    # vout, source straps j = 1, 3, 5 under vin), not the n-tap stacks
    pitch_s = W / (2 * nstrap)
    js = (0, 2, 4) if net == "vout" else (1, 3, 5)
    cuts = db.Region()
    for j in js:
        xs = x0 - W / 2 + pitch_s * (j + 0.5)
        cuts += box(xs - 0.6, yb, xs + 0.6, yt) & region("via2")
    # group cuts into via nodes: cuts closer than 0.24 um belong to one node
    nodes = cuts.sized(int(0.12 / um))
    nodes.merge()
    min_cuts = min((cuts & db.Region(p)).count() for p in nodes.each())
    report(f"via2 node in {net} plate (strap current)", i_strap[net], min_cuts * LIM_CUT["via2"],
           f"{min_cuts} cuts, {nodes.count()} nodes in column 0")

    # 6. plates: 50 mA crossing the narrowest vertical cut of the met3 / met4 plate
    for lay in ("met3", "met4"):
        h = (box(X0 - W / 2, yb - 1, X0 + (NCOL - 1) * PITCH + W / 2, yt + 1) & region(lay))
        hmin = min((h & box(xc, yb - 1, xc + 0.01, yt + 1)).area() / (0.01 / um) * um
                   for xc in (X0, X0 + PITCH * 1.5, X0 + PITCH * 3))
        report(f"{lay} {net} plate, full IL", IL * 1e3, hmin * LIM_W[lay], f"height {hmin:.2f} um")

    # 7. via3 between the plates: all of IL, if the outside connection is on met4
    v3 = box(X0 - W, yb, X0 + (NCOL - 1) * PITCH + W, yt) & region("via3")
    report(f"via3 {net} plate (if the pin is met4)", IL * 1e3, v3.count() * LIM_CUT["via3"],
           f"{v3.count()} cuts")

print(f"IL = {IL*1e3:.0f} mA, {nf_total} fingers, {i_f*1e3:.1f} uA per finger, "
      f"strap bound {i_strap_max:.2f} mA\n")
print(f"{'element':48s} {'I (mA)':>8s} {'limit (mA)':>11s}  ok   note")
for item, i_ma, cap, ok, note in rows:
    print(f"{item:48s} {i_ma:8.3f} {cap:11.3f}  {'yes' if ok else 'NO '}  {note}")
print("\nALL WITHIN LIMITS" if all(r[3] for r in rows) else "\nSOME ELEMENTS EXCEED THE LIMIT")
(ROOT / "em_check.json").write_text(json.dumps(
    [dict(element=i, I_mA=a, limit_mA=c, ok=o, note=n) for i, a, c, o, n in rows], indent=1))
