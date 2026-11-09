"""Fill ldo_sky130.tex.in with the numbers produced by the scripts and build the PDF.

Sources: scripts/sizes.json, scripts/sim_results_sch.json, scripts/sim_results_pex.json,
scripts/corners_sch.json, layout/em_check.json, layout/lvs_klayout/ldo_extracted.cir,
layout/drc_klayout/ldo_drc.lyrdb, sim/ldo_pex.sub, sim/check_sense_point.out,
layout/pex/ldo_final__ldo/*.spice.

    python build_doc.py            (TECTONIC = path of tectonic.exe, else 'tectonic')
"""
import datetime
import json
import math
import os
import pathlib
import re
import subprocess
import xml.etree.ElementTree as ET

DOC = pathlib.Path(__file__).resolve().parent
ROOT = DOC.parent
S = json.loads((ROOT / "scripts" / "sizes.json").read_text())
SCH = json.loads((ROOT / "scripts" / "sim_results_sch.json").read_text())
_pj = ROOT / "scripts" / "sim_results_pex.json"
PEX = json.loads(_pj.read_text()) if _pj.exists() else {}
CORN = json.loads((ROOT / "scripts" / "corners_sch.json").read_text())
EM = json.loads((ROOT / "layout" / "em_check.json").read_text())


def tex_num(x, fmt):
    return fmt.format(x)


def pm_gm(r, key):
    lp = r["loop"][key]
    gm = lp["GM_dB"]
    gms = "no $-180^\\circ$ crossing" if (gm is None or math.isinf(gm)) else f"{gm:.0f} dB"
    return lp, gms


def get(r, *path, default=None):
    for p in path:
        if not isinstance(r, dict) or p not in r:
            return default
        r = r[p]
    return r


def fmt_or_dash(v, f):
    return "--" if v is None else f.format(v)


# ------------------------------------------------------------------ summary table
rows = []


def row(name, target, fs, fp, key_fn):
    vs, vp = key_fn(SCH), key_fn(PEX)
    rows.append(f"{name} & {target} & {fmt_or_dash(vs, fs)} & {fmt_or_dash(vp, fp)} \\\\")


row("$\\VOUT$ at $\\IL = 0.1$\\,mA (V)", "1.5", "{:.4f}", "{:.4f}", lambda r: get(r, "loadreg", "v_light"))
row("$\\VOUT$ at $\\IL = 50$\\,mA (V)", "", "{:.4f}", "{:.4f}", lambda r: get(r, "loadreg", "v_heavy"))
row("load regulation 0.1$\\to$50\\,mA (mV)", "", "{:.2f}", "{:.2f}",
    lambda r: None if get(r, "loadreg", "dV") is None else 1e3 * r["loadreg"]["dV"])
for il in ("0.1mA", "50mA"):
    row(f"line regulation 1.7--1.9\\,V, {il[:-2]}\\,mA (mV/V)", "", "{:.1f}", "{:.1f}",
        lambda r, il=il: None if get(r, "linereg", il, "slope") is None else 1e3 * r["linereg"][il]["slope"])
row("dropout ($\\VOUT$ $-1\\%$) at 50\\,mA (mV)", "", "{:.0f}", "{:.0f}",
    lambda r: None if get(r, "linereg", "50mA", "VDO_1pct") is None else 1e3 * r["linereg"]["50mA"]["VDO_1pct"])
row("quiescent current at 1.8\\,V ($\\mu$A)", "", "{:.1f}", "{:.1f}",
    lambda r: None if get(r, "iq", "at_1p8") is None else 1e6 * r["iq"]["at_1p8"])
for il in ("0.1mA", "50mA"):
    row(f"PSRR at 1\\,kHz, {il[:-2]}\\,mA (dB)", "", "{:.1f}", "{:.1f}",
        lambda r, il=il: get(r, "psrr", il, "1kHz"))
for il in ("0.1mA", "1mA", "10mA", "50mA"):
    row(f"phase margin, {il[:-2]}\\,mA (\\textdegree)", "$\\ge 45$" if il == "0.1mA" else "", "{:.1f}", "{:.1f}",
        lambda r, il=il: get(r, "loop", il, "PM"))
for il in ("0.1mA", "50mA"):
    row(f"unity-gain frequency, {il[:-2]}\\,mA (kHz)", "", "{:.0f}", "{:.0f}",
        lambda r, il=il: None if get(r, "loop", il, "UGF") is None else r["loop"][il]["UGF"] / 1e3)
for il in ("0.1mA", "50mA"):
    gs = get(SCH, "loop", il, "GM_dB")
    gp = get(PEX, "loop", il, "GM_dB")
    f = lambda g: "--" if g is None else ("none$^\\dagger$" if math.isinf(g) else f"{g:.0f}")
    rows.append(f"gain margin, {il[:-2]}\\,mA (dB) & & {f(gs)} & {f(gp)} \\\\")
row("load step: dip below the 0.1\\,mA level (mV)", "", "{:.2f}", "{:.2f}",
    lambda r: None if get(r, "tran", "dip_from_initial") is None else 1e3 * r["tran"]["dip_from_initial"])
row("load step: peak above the 50\\,mA level (mV)", "", "{:.2f}", "{:.2f}",
    lambda r: None if get(r, "tran", "peak_from_heavy") is None else 1e3 * r["tran"]["peak_from_heavy"])

pex_note = ("$^\\dagger$: the phase does not reach $-180^\\circ$ below 1\\,GHz. "
            "Schematic DC sweeps: 0.1\\,mA / 2\\,mV steps; post-layout: 0.5\\,mA / 10\\,mV steps.")

# ------------------------------------------------------------------ corners
a = lambda k: [r[k] for r in CORN]
pm_min = min(min(r["PM_light"], r["PM_heavy"]) for r in CORN)
worst = min(CORN, key=lambda r: min(r["PM_light"], r["PM_heavy"]))
corner_summary = (f"$\\VOUT$ = {min(a('v_light')):.4f}--{max(a('v_light')):.4f}\\,V at 0.1\\,mA and "
                  f"{min(a('v_heavy')):.4f}--{max(a('v_heavy')):.4f}\\,V at 50\\,mA, quiescent current "
                  f"{1e6*min(a('iq')):.1f}--{1e6*max(a('iq')):.1f}\\,$\\mu$A, lowest phase margin "
                  f"{pm_min:.1f}\\textdegree\\ ({worst['corner']}, {worst['temp']}\\,\\textdegree C, "
                  f"$\\VIN$ = {worst['vin']}\\,V).")

# ------------------------------------------------------------------ sizes
size_rows = []
for name, typ, w, l, m in [
        ("$M_{BN}$", "nfet", "WB", "LB", "MBN_M"), ("$M_T$", "nfet", "WB", "LB", "MT_M"),
        ("$M_1$, $M_2$", "nfet", "W12", "L12", None), ("$M_3$, $M_4$", "pfet", "W34", "L34", None),
        ("$M_{CS}$", "nfet", "WCS", "LCS", "MCS_M"), ("$M_D$", "pfet", "WPf", "LP", "MD_M"),
        ("$M_{BL}$", "pfet", "WBL", "LBL", "MBL_M"), ("$M_P$", "pfet", "WPf", "LP", "MP_M")]:
    if m is None:          # input pair and mirror: drawn as 2 fingers of W/2
        size_rows.append(f"{name} & {typ}\\_01v8 & {S[w]/2:g} & {S[l]:g} & 2 \\\\")
    else:
        size_rows.append(f"{name} & {typ}\\_01v8 & {S[w]:g} & {S[l]:g} & {S[m]} \\\\")
size_rows.append(f"$R_1$, $R_2$ units & res\\_xhigh\\_po\\_0p35 & 0.35 & {S['L_RU']:g} & "
                 f"{S['N_R1']} + {S['N_R2']} (+2 dummies) \\\\")
size_rows.append(f"bias, load & -- & \\multicolumn{{3}}{{l}}{{$I_{{BIAS}}$ = {S['IBIAS']*1e6:g}\\,$\\mu$A, "
                 f"$V_{{REF}}$ = {S['VREF']:g}\\,V, $C_L$ = {S['CL']*1e6:g}\\,$\\mu$F, "
                 f"$R_{{ESR}}$ = {S['ESR']*1e3:g}\\,m$\\Omega$}} \\\\")

# ------------------------------------------------------------------ LVS extracted netlist
lines, cur = [], ""
for l in (ROOT / "layout" / "lvs_klayout" / "ldo_extracted.cir").read_text().splitlines():
    if l.startswith("+"):
        lines[-1] += " " + l[1:]
    elif l[:1] in ("M", "R"):
        lines.append(l)
lvs_rows = []
for l in lines:
    t = l.split()
    p = dict(kv.split("=") for kv in t if "=" in kv)
    nets = t[1:4] if l[0] == "M" else t[1:3]
    model = [x for x in t if x.startswith("sky130_fd_pr")][0]
    if l[0] == "M":
        d, g, s_ = nets
        W, L = float(p["W"]), float(p["L"])
        if "pfet" in model:
            name = ("$M_P$" if W > 100 else "$M_D$" if L < 0.2 else "$M_{BL}$" if W < 5
                    else "$M_3$" if g == s_ or g == d else "$M_4$")
        else:
            name = ("$M_1$" if g == "vref" else "$M_{CS}$" if L < 0.9 else
                    "$M_{BN}$" if g == "ibias" and W < 5 else "$M_T$" if g == "ibias" else "$M_2$")
        lvs_rows.append(f"{name} & {model.replace('sky130_fd_pr__', '').replace('_', chr(92) + '_')} & "
                        f"{W:g} & {L:g} \\\\")
    else:
        R, L, W = float(p["R"]), float(p["L"]), float(p["W"])
        name = "dummies (parallel)" if nets[0] == nets[1] else ("$R_1$" if "vout" in nets else "$R_2$")
        lvs_rows.append(f"{name} & res\\_xhigh\\_po\\_0p35 & {W:g} & $l$ = {L:g}\\,$\\mu$m, "
                        f"{R/1e3:.1f}\\,k$\\Omega$ \\\\")

# ------------------------------------------------------------------ EM
em_rows = []
for e in EM:
    nm = e["element"].replace("_", "\\_")
    note = e["note"].replace(" um", "\\,$\\mu$m")
    nm = nm.replace("full IL", "full $\\IL$")
    em_rows.append(f"{nm} & {e['I_mA']:.3f} & {e['limit_mA']:.3f} & {note} \\\\")
via2 = [e for e in EM if e["element"].startswith("via2")]
em_via2 = ", ".join(f"{e['I_mA']:.2f} of {e['limit_mA']:.2f}\\,mA" for e in via2)
via3 = sorted({int(re.search(r"(\d+) cuts", e["note"]).group(1)) for e in EM if e["element"].startswith("via3")})

# ------------------------------------------------------------------ DRC count
drc_n = len(ET.parse(ROOT / "layout" / "drc_klayout" / "ldo_drc.lyrdb").getroot().find("items"))

# ------------------------------------------------------------------ PEX sizes
def count_rc(p):
    txt = p.read_text()
    return (sum(1 for l in txt.splitlines() if l.startswith("R")),
            sum(1 for l in txt.splitlines() if l.startswith("C")))


pexdir = ROOT / "layout" / "pex" / "ldo_final__ldo"
rf, cf = count_rc(pexdir / "ldo_k25d_pex_netlist.spice")
rr, cr = count_rc(pexdir / "ldo_k25d_pex_netlist_ticer10p.spice")

# ------------------------------------------------------------------ PEX discussion
sp = (ROOT / "sim" / "check_sense_point.out").read_text()
m = re.search(r"V_drain ([\d.]+), V_sense ([\d.]+), V_pin ([\d.]+)", sp)
ra = re.search(r"R_a \(drain -> sense\) = ([\d.]+) mOhm, R_b \(sense -> pin\) = ([\d.]+) mOhm", sp)
split = re.search(r"R_a/R_b split\s*: PM ([\d.]+) deg, UGF ([\d.]+) MHz", sp)
fc = (ROOT / "sim" / "check_fb_coupling.out").read_text()
mm = re.search(r"moved to ground: (\d+), total ([\d.]+) fF", fc)
fbc = {"n": int(mm.group(1)), "c": float(mm.group(2)), "ext": {}, "dec": {}}
for il, kind, pm, hi in re.findall(r"([\d.]+) mA, (extracted|fb coupling removed)\s*: PM ([\d.]+) deg, "
                                   r"UGF \d+ kHz, max \|T\| above 100 MHz ([-\d.]+) dB", fc):
    fbc["ext" if kind == "extracted" else "dec"][float(il) if float(il) < 1 else int(float(il))] = (float(pm), float(hi))
lp50s = SCH["loop"]["50mA"]
lp50p = get(PEX, "loop", "50mA") or {"T0_dB": float("nan"), "PM": float("nan")}
disc = (
    f"At light load the two agree closely. At 50\\,mA the extracted netlist has a lower loop gain "
    f"({lp50p['T0_dB']:.1f} against {lp50s['T0_dB']:.1f}\\,dB) and a \\emph{{higher}} phase margin "
    f"({lp50p['PM']:.1f}\\textdegree\\ against {lp50s['PM']:.1f}\\textdegree). "
    f"The operating point at 50\\,mA shows where this comes from (\\texttt{{scripts/check\\_sense\\_point.py}}): "
    f"the pass-device drains sit at {float(m.group(1)):.4f}\\,V, the top of the divider at "
    f"{float(m.group(2)):.4f}\\,V and the vout pin at {float(m.group(3)):.4f}\\,V, i.e.\\ "
    f"{float(ra.group(1)):.0f}\\,m$\\Omega$ of wiring (diffusion, contacts, straps, plate) lies between the "
    f"drains and the feedback tap and {float(ra.group(2)):.0f}\\,m$\\Omega$ between the tap and the pin. "
    f"Inserting these two resistors into the schematic raises its phase margin at 50\\,mA from "
    f"{lp50s['PM']:.1f}\\textdegree\\ to {float(split.group(1)):.1f}\\textdegree\\ "
    f"(unity-gain frequency {float(split.group(2)):.2f}\\,MHz), so most of the difference is this series "
    f"resistance. "
    f"Above about 10\\,MHz the post-layout loop gain does not roll off but stays near "
    f"${fbc['ext'][0.1][1]:.0f}$\\,dB (Fig.~\\ref{{fig:lg}}). This is capacitive coupling into the feedback net, "
    f"which bypasses the loop break: moving its {fbc['n']} coupling capacitors ({fbc['c']:.1f}\\,fF in total) "
    f"to ground lowers $|T|$ above 100\\,MHz from ${fbc['ext'][0.1][1]:.0f}$ to ${fbc['dec'][0.1][1]:.0f}$\\,dB at 0.1\\,mA "
    f"and changes the phase margin at 50\\,mA only from {fbc['ext'][50][0]:.1f}\\textdegree\\ to "
    f"{fbc['dec'][50][0]:.1f}\\textdegree\\ (\\texttt{{scripts/check\\_fb\\_coupling.py}}). "
    f"The remaining {fbc['dec'][50][0] - float(split.group(1)):.0f}\\textdegree\\ were not attributed. "
    f"(Treating the same resistance as extra ESR of $C_L$ does not reproduce the result: it moves the "
    f"unity-gain frequency to 25\\,MHz, \\texttt{{scripts/check\\_route\\_esr.py}}.) The same resistance costs "
    f"$\\approx${float(ra.group(1)) * 50e-3:.0f}\\,mV of headroom at 50\\,mA, which appears in the post-layout dropout."
)

esr_p = {k: {round(e, 4): pm for e, pm, *_ in v} for k, v in PEX.get("esr", {}).items()}
esr_s = {k: {round(e, 4): pm for e, pm, *_ in v} for k, v in SCH.get("esr", {}).items()}
if esr_p:
    parts = []
    for il in ("0.1mA", "50mA"):
        parts.append(f"at {il[:-2]}\\,mA " + ", ".join(
            f"{esr_p[il][e]:.0f}\\textdegree\\ ({esr_s[il][e]:.0f}\\textdegree)" for e in (0.0, 0.01, 1.0)))
    disc += (" Phase margin against the ESR of $C_L$ = 0, 10\\,m$\\Omega$, 1\\,$\\Omega$, post-layout "
             "(schematic in brackets): " + "; ".join(parts) + ". The loop stays stable in all of them.")

extra = ""
miss =[k for k in ("loop", "psrr", "loadreg", "linereg", "iq", "tran", "esr") if k not in PEX]
if miss:
    extra = ("\\item Not available in this build of the report (post-layout run unfinished): "
             + ", ".join(miss) + ".")

lyw, lyh = 155.3, 40.6          # bbox of ldo_final.gds, measured with KLayout
fill = {
    "DATE": datetime.date.today().strftime("%d %B %Y"),
    "DRC_N": str(drc_n),
    "PEX_NOTE": pex_note,
    "SUMMARY_ROWS": "\n".join(rows),
    "CORNER_SUMMARY": corner_summary,
    "MP_M": str(S["MP_M"]),
    "L_RU": f"{S['L_RU']:g}",
    "N_R1": str(S["N_R1"]), "N_R2": str(S["N_R2"]),
    "VOUT_IDEAL": f"{S['VREF'] * (1 + S['N_R1'] / S['N_R2']):.2f}",
    "SIZE_ROWS": "\n".join(size_rows),
    "AREA": f"{lyw} \\times {lyh}\\,\\mu\\mathrm{{m}}",
    "VIA3": " / ".join(str(v) for v in via3),
    "LVS_ROWS": "\n".join(lvs_rows),
    "EM_ROWS": "\n".join(em_rows),
    "EM_VIA2": em_via2,
    "PEX_R_FULL": f"{rf:,}", "PEX_C_FULL": f"{cf:,}", "PEX_R": f"{rr:,}", "PEX_C": f"{cr:,}",
    "PEX_DISCUSSION": disc,
    "EXTRA_LIMITS": extra,
}
src = (DOC / "ldo_sky130.tex.in").read_text(encoding="utf-8")
for k, v in fill.items():
    src = src.replace(f"@@{k}@@", v)
left = re.findall(r"@@\w+@@", src)
assert not left, left
(DOC / "ldo_sky130.tex").write_text(src, encoding="utf-8")
tect = os.environ.get("TECTONIC", "tectonic")
r = subprocess.run([tect, "-X", "compile", "ldo_sky130.tex"], cwd=DOC, capture_output=True, text=True)
print(r.stdout[-1500:], r.stderr[-3000:])
print("PDF:", DOC / "ldo_sky130.pdf", "exists" if (DOC / "ldo_sky130.pdf").exists() else "MISSING")

# ------------------------------------------------------------------ README (same numbers)
def md(v, f):
    return "–" if v is None else ("none (no −180° crossing)" if isinstance(v, float) and math.isinf(v) else f.format(v))


md_rows = ["| | schematic (tt, 27 °C) | post-layout (extracted RC) |", "|---|---|---|"]
for name, fn, f in [
        ("V_OUT at 0.1 / 50 mA (V)", lambda r: (get(r, "loadreg", "v_light"), get(r, "loadreg", "v_heavy")), "{:.4f}"),
        ("load regulation 0.1→50 mA (mV)", lambda r: (None if get(r, "loadreg", "dV") is None else 1e3 * r["loadreg"]["dV"],), "{:.2f}"),
        ("dropout at 50 mA (mV)", lambda r: (None if get(r, "linereg", "50mA", "VDO_1pct") is None else 1e3 * r["linereg"]["50mA"]["VDO_1pct"],), "{:.0f}"),
        ("quiescent current (µA)", lambda r: (None if get(r, "iq", "at_1p8") is None else 1e6 * r["iq"]["at_1p8"],), "{:.1f}"),
        ("PSRR at 1 kHz, 0.1 / 50 mA (dB)", lambda r: (get(r, "psrr", "0.1mA", "1kHz"), get(r, "psrr", "50mA", "1kHz")), "{:.1f}"),
        ("phase margin, 0.1 / 50 mA (°)", lambda r: (get(r, "loop", "0.1mA", "PM"), get(r, "loop", "50mA", "PM")), "{:.1f}"),
        ("load step 0.1↔50 mA, dip / peak (mV)", lambda r: (None if get(r, "tran", "dip_from_initial") is None else 1e3 * r["tran"]["dip_from_initial"],
                                                           None if get(r, "tran", "peak_from_heavy") is None else 1e3 * r["tran"]["peak_from_heavy"]), "{:.2f}")]:
    md_rows.append(f"| {name} | {' / '.join(md(v, f) for v in fn(SCH))} | {' / '.join(md(v, f) for v in fn(PEX))} |")
md_rows.append("")
md_rows.append(f"63 schematic corners (tt/ss/ff/sf/fs/ll/hh × −40/27/125 °C × V_IN 1.7/1.8/1.9 V): "
               f"V_OUT {min(a('v_heavy')):.3f}–{max(a('v_light')):.3f} V, lowest phase margin {pm_min:.1f}°.")
readme = (ROOT / "README.md.in").read_text(encoding="utf-8")
readme = readme.replace("@@RESULTS@@", "\n".join(md_rows)).replace("@@DRC@@", str(drc_n))
(ROOT / "README.md").write_text(readme, encoding="utf-8")
print("README.md written")
