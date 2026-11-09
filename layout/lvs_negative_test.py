"""Sanity check of the LVS flow: the correct netlist must match, and each
deliberately wrong netlist must fail. Run after run_lvs.py (needs ldo_final.gds).

    python lvs_negative_test.py
"""
import sys
import tempfile
import pathlib

from postproc import GDS_OUT, ROOT, kl

sys.path.insert(0, str(ROOT.parent / "scripts"))
from ldo_cdl import cdl  # noqa: E402

DECK = r"C:\klayout\sky130_lvs\sky130.lvs"
good = cdl()
cases = {
    "correct netlist": (good, None),
    "pass device m=150 instead of 160": (good.replace("l=0.15u m=160", "l=0.15u m=150"), True),
    "M2 gate on vref instead of fb": (good.replace("Mm2 ea fb ", "Mm2 ea vref "), True),
    "one R2 unit l=5u instead of 4.27u": (good.replace("Rr23 r2_3 gnd gnd sky130_fd_pr__res_xhigh_po_0p35 l=4.27u",
                                                       "Rr23 r2_3 gnd gnd sky130_fd_pr__res_xhigh_po_0p35 l=5u"), True),
    "MCS L=0.6u instead of 0.5u": (good.replace("w=10u l=0.5u m=2", "w=10u l=0.6u m=2"), True),
}
tmp = pathlib.Path(tempfile.mkdtemp())
ok_all = True
for name, (text, must_fail) in cases.items():
    if must_fail and text == good:
        print(f"{name:40s} SKIPPED: replacement did not apply"); ok_all = False; continue
    f = tmp / "case.cdl"
    f.write_text(text)
    rc, log = kl(DECK, input=GDS_OUT, schematic=f, report=tmp / "case.lvsdb",
                 target_netlist=tmp / "case.cir", thr=4, run_mode="deep", lvs_sub="gnd",
                 schematic_simplify="true")
    match = rc == 0 and "Netlists match" in log
    expect = not must_fail
    ok_all &= match == expect
    print(f"{name:40s} {'MATCH' if match else 'MISMATCH':9s} {'ok' if match == expect else 'WRONG'}")
print("all as expected" if ok_all else "SOME CASES WRONG")
