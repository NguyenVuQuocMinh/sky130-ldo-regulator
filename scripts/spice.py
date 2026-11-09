"""Small helper: run an ngspice netlist in batch mode and read wrdata output."""
import os
import subprocess
import pathlib
import numpy as np

# ngspice console executable; override with the NGSPICE environment variable
NGSPICE = os.environ.get("NGSPICE", r"C:\ngspice\ngspice-46_64\Spice64\bin\ngspice_con.exe")
SIM = pathlib.Path(__file__).resolve().parent.parent / "sim"


def run(netlist_text: str, name: str) -> str:
    """Write sim/<name>.cir, run ngspice in batch mode, return its log text."""
    cir = SIM / f"{name}.cir"
    cir.write_text(netlist_text, encoding="ascii")
    res = subprocess.run([NGSPICE, "-b", cir.name], cwd=SIM,
                         capture_output=True, text=True,
                         timeout=int(os.environ.get("LDO_SPICE_TIMEOUT", "600")))
    log = res.stdout + res.stderr
    (SIM / f"{name}.log").write_text(log, encoding="utf-8")
    if res.returncode != 0 or "error" in log.lower() and "no error" not in log.lower():
        bad = [l for l in log.splitlines() if "error" in l.lower()]
        if bad:
            print(f"[{name}] ngspice reported:\n  " + "\n  ".join(bad[:10]))
    return log


def read(fname: str, ncols: int) -> np.ndarray:
    """Read a wrdata file. wrdata writes (x, y) pairs per vector; keep x once.

    Returns an array of shape (N, ncols + 1): column 0 = x, then the vectors.
    For complex vectors wrdata writes x, re, im; handle that with ncols counting
    every numeric column after the first.
    """
    raw = np.loadtxt(SIM / fname)
    if raw.ndim == 1:
        raw = raw[None, :]
    return raw


def meas(log: str, key: str) -> float:
    """Pull a '.meas'/'meas' result 'key = value' out of the log."""
    for line in log.splitlines():
        s = line.strip()
        if s.lower().startswith(key.lower()) and "=" in s:
            try:
                return float(s.split("=")[1].split()[0])
            except ValueError:
                pass
    raise KeyError(key)
