"""Official sky130 LVS with KLayout (efabless deck sky130.lvs, C:\\klayout\\sky130_lvs).

layout : ldo_final.gds (postproc.build_final)
source : ldo.cdl (scripts/ldo_cdl.py, from sizes.json)
output : lvs_klayout/ldo.lvsdb, lvs_klayout/ldo_extracted.cir, lvs_klayout/run.log

    python run_lvs.py
"""
import sys

from postproc import GDS_OUT, ROOT, build_final, kl

sys.path.insert(0, str(ROOT.parent / "scripts"))
from ldo_cdl import cdl  # noqa: E402

DECK = r"C:\klayout\sky130_lvs\sky130.lvs"
out_dir = ROOT / "lvs_klayout"
out_dir.mkdir(exist_ok=True)
(ROOT / "ldo.cdl").write_text(cdl())

print(build_final())
rc, log = kl(DECK, input=GDS_OUT, schematic=ROOT / "ldo.cdl", report=out_dir / "ldo.lvsdb",
             target_netlist=out_dir / "ldo_extracted.cir", thr=4, run_mode="deep",
             lvs_sub="gnd", spice_net_names="true", spice_comments="false", scale="false",
             verbose="false", schematic_simplify="true", net_only="false",
             top_lvl_pins="false", combine="false", purge="false", purge_nets="false")
(out_dir / "run.log").write_text(log)
tail = [l for l in log.splitlines() if "match" in l.lower() or "error" in l.lower()]
print("\n".join(tail[-10:]))
print("LVS", "MATCH" if rc == 0 and "Netlists match" in log else "MISMATCH (see lvs_klayout/run.log)")
