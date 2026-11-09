"""Shared helpers: KLayout batch call and ldo_electric.gds -> ldo_final.gds.

ldo_final.gds = Electric GDS + poly_rs marker on the resistor bodies + pin
labels (met3 70/5) at the export points of cell ldo{lay} (read from ldo.cmd).
"""
import json
import pathlib
import subprocess

ROOT = pathlib.Path(__file__).resolve().parent
KL = r"C:\klayout\klayout-0.30.12-win64\klayout_app.exe"
S = json.loads((ROOT.parent / "scripts" / "sizes.json").read_text())
GDS_IN, GDS_OUT = ROOT / "ldo_electric.gds", ROOT / "ldo_final.gds"


def kl(script, **rd):
    args = [KL, "-b"]
    for k, v in rd.items():
        args += ["-rd", f"{k}={v}"]
    args += ["-r", str(script)]
    r = subprocess.run(args, capture_output=True, text=True)
    return r.returncode, r.stdout + r.stderr


def export_points():
    """(name, x, y) of the exports of cell 'ldo lay' in the Electric command file."""
    nodes, pts, cell = {}, [], None
    for line in (ROOT / "ldo.cmd").read_text().splitlines():
        t = line.split()
        if not t:
            continue
        if t[0] == "CELL":
            cell = " ".join(t[1:])
        elif t[0] == "N" and cell == "ldo lay":
            nodes[t[1]] = (float(t[3]), float(t[4]))
        elif t[0] == "E" and cell == "ldo lay":
            pts.append((t[1], *nodes[t[2]]))
    return pts


def build_final():
    labels = ";".join(f"{n},{x},{y}" for n, x, y in export_points())
    rc, out = kl(ROOT / "add_marker.rb", input=GDS_IN, output=GDS_OUT,
                 body=S["L_RU"], width=0.35, labels=labels)
    if rc:
        raise SystemExit(out)
    return out.strip()


if __name__ == "__main__":
    print(build_final())
