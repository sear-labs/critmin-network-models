"""Run Alavi's six-stage network model (sear-labs/mineralnet-optsc) unchanged, on her own data.

This produces the reference the lab model is compared against (network.check_agreement()). Her notebook is executed
cell by cell from a clone of her repository, which is only read. Only three things are changed: the Colab-only
lines (pip, drive.mount, files.download, the WLS licence env), the data path, and the per-cell
display calls. The model code itself is untouched.

    python scripts/reference_sara_network.py <path to a mineralnet-optsc clone>
        # -> data/interim/reference/sara_network_*.csv

This is how src/critmin_net/data/reference/ was made (at the commit named in src/critmin_net/data/SOURCES.md).
"""
import json, re, sys
from pathlib import Path

import gurobipy as gp

ROOT = Path(__file__).resolve().parents[1]
REPO = Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT.parent / "mineralnet-optsc"
NB = REPO / "notebooks" / "full6stage-network.ipynb"
DATA = (REPO / "data" / "raw" / "input_data_3region").as_posix() + "/"
OUT = ROOT / "data" / "interim" / "reference"
OUT.mkdir(parents=True, exist_ok=True)

SKIP = ("pip install", "drive.mount", "files.download", "WLSACCESSID", "to_excel", "plt.")


def main():
    cells = [c for c in json.loads(NB.read_text(encoding="utf-8"))["cells"] if c["cell_type"] == "code"]
    ns = {"env": gp.Env()}
    for c in cells:
        src = "".join(c["source"])
        if any(s in src for s in ("WLSACCESSID", "plt.", "ExcelWriter")):
            continue                                       # licence env, plots, Excel export
        src = "\n".join(l for l in src.splitlines()
                        if not any(s in l for s in SKIP) and "google.colab" not in l
                        and not l.lstrip().startswith("!"))
        src = re.sub(r"(['\"])/content/drive/MyDrive/input_data_3region/", r"\1" + DATA, src)
        src = src.replace("env = gp.Env(params=params)", "")
        exec(compile(src, "<alavi-notebook>", "exec"), ns)
    m = ns["m"]
    assert m.SolCount > 0, "reference model returned no solution"
    ns["df_cost"].to_csv(OUT / "sara_network_cost_by_region.csv", index=False)
    for s in ("mine", "proc", "cath"):
        ns[f"df_{s}"].to_csv(OUT / f"sara_network_{s}.csv", index=False)
    ns["df_trade"].to_csv(OUT / "sara_network_trade.csv", index=False)
    meta = dict(status=int(m.Status), objective=m.ObjVal, mip_gap=m.MIPGap, runtime_s=m.Runtime,
                n_vars=m.NumVars, n_constrs=m.NumConstrs, n_int=m.NumIntVars,
                alpha=ns["alpha"], import_coef=ns["import_coef"], region_share=ns["region_share"],
                years=[int(min(ns["Y"])), int(max(ns["Y"]))])
    (OUT / "sara_network_meta.json").write_text(json.dumps(meta, indent=2))
    print(json.dumps(meta, indent=2))
    print(ns["df_cost"].to_string(index=False))


if __name__ == "__main__":
    main()
