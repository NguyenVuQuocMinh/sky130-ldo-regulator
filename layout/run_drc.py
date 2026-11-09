"""Official sky130 DRC with KLayout (efabless deck sky130A_mr.drc).

1. postproc.build_final(): ldo_electric.gds -> ldo_final.gds (poly_rs + labels)
2. sky130A_mr.drc on ldo_final.gds, FEOL + BEOL + off-grid checks
3. prints the violation count per rule from drc_klayout/ldo_drc.lyrdb

    python run_drc.py
"""
import collections
import xml.etree.ElementTree as ET

from postproc import GDS_OUT, ROOT, build_final, kl

DECK = r"C:\klayout\sky130_drc\sky130A_mr.drc"

out_dir = ROOT / "drc_klayout"
out_dir.mkdir(exist_ok=True)
rdb = out_dir / "ldo_drc.lyrdb"

print(build_final())
rc, log = kl(DECK, input=GDS_OUT, report=rdb, feol="true", beol="true", offgrid="true",
             floating_met="false", seal="false", thr=4)
(out_dir / "run.log").write_text(log)
if rc:
    raise SystemExit(log[-3000:])

items = ET.parse(rdb).getroot().find("items")
cnt = collections.Counter((i.find("category").text.strip("'"), i.find("cell").text) for i in items)
print(f"DRC violations: {sum(cnt.values())}")
for (rule, cell), n in cnt.most_common():
    print(f"  {n:4d}  {rule:20s} cell {cell}")
