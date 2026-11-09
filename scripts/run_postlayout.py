"""Post-layout run of the full sim_all.py suite on the extracted netlist
(KLayout-PEX 2.5D RC, TICER-reduced at 10 ps; see pex_netlist.py).
Writes scripts/sim_results_pex.json and figures/*_pex.png.

    python run_postlayout.py
"""
import os

os.environ["LDO_VER"] = "pex"
os.environ["LDO_SPICE_TIMEOUT"] = "14400"   # the RC transient takes long

import sim_all  # noqa: E402
from pex_netlist import core_pex, core_pex_dc, prepare  # noqa: E402

if __name__ == "__main__":
    print(prepare(), flush=True)
    sim_all.main(netfn=core_pex, dcfn=core_pex_dc, esrs=[0, 10e-3, 1.0],
                 il_step="0.5m", vin_step=0.01, resume=True)
