"""Build the deduplicated SAP UI element catalogue from tools/uipath_dump.py output.

Usage: python tools/uipath_catalog.py docs/uipath/raw/ui_elements_raw.csv docs/uipath/ui_elements.csv
Adds the SAP GUI scripting ID (findById form) and whether SAP_automation\\change_bom already uses it.
"""
import csv
import re
import sys
from collections import OrderedDict

# Window level of each popup title (main session screens are wnd[0]).
POPUP_LEVEL = {"Production Version Details": 2}

# IDs used by SAP_automation\change_bom (read-only reference, copied 2026-11-16).
KNOWN = {
    "wnd[0]/usr/ctxt[0]", "wnd[0]/usr/ctxt[1]", "wnd[0]/sbar", "wnd[0]/tbar[0]/btn[11]",
    "wnd[0]/tbar[1]/btn[7]", "wnd[0]/tbar[1]/btn[5]", "wnd[0]/usr/sub/6/btn",
    "wnd[0]/usr/tblSAPLCPDITCTRL_1200", "wnd[0]/usr/tblSAPLCMDITCTRL_1000",
    "wnd[1]/usr/tblSAPLCPSLTCTRL_2110", "wnd[1]/usr/sub/1", "wnd[1]/usr/txt[0]",
    "wnd[1]/usr/tblSAPLMDIAT_MKAL_NEW", "wnd[1]/tbar[0]/btn[7]", "wnd[1]/tbar[0]/btn[0]",
    "wnd[2]/usr/ctxt[0]", "wnd[2]/usr/txt[0]", "wnd[2]/usr/ctxt[1]", "wnd[2]/usr/ctxt[2]",
    "wnd[2]/usr/cmb[1]", "wnd[2]/usr/ctxt[3]", "wnd[2]/usr/txt[4]", "wnd[2]/usr/ctxt[6]",
    "wnd[2]/usr/ctxt[7]", "wnd[2]/usr/btn", "wnd[2]/tbar[0]/btn[12]", "wnd[2]/tbar[0]/btn[0]",
}

TCODE = [
    ("Create Routing", "CA01"), ("Change Routing", "CA02"), ("Routing Change", "CA02"),
    ("Material Component Overview", "CA01/CA02"), ("Display Work Center", "CA01 (WC display)"),
    ("Change Material", "MM02"), ("Production Version", "MM02"), ("Organizational Levels", "MM02"),
    ("Choose Alternative BOM", "CA01/CA02"), ("Entry Option: Group", "CA01/CA02"),
    ("Select Type", "CA01"), ("Create Using Copy Function", "CA01"), ("New Assignment", "CA01/CA02"),
]


def tcode(window):
    for key, tc in TCODE:
        if key in window:
            return tc
    return ""


def scripting_id(row):
    sid = row["sap_id"].replace("?", "/")
    level = POPUP_LEVEL.get(row["window"], 1) if row["popup"] else 0
    sid = f"wnd[{level}]/{sid}"
    if "sbar/pane[0]" in sid:
        sid = sid.replace("/pane[0]", "")  # status bar text: SAP_automation reads wnd[0]/sbar
    cell = row["cell"]
    col = re.search(r"tableCol='([^']+)'", cell)
    r = re.search(r"tableRow='([^']+)'", cell)
    tip = re.search(r"colTooltip='([^']+)'", cell)
    if r or col:
        c = col.group(1) if col else f"<col of '{tip.group(1)}'>" if tip else "?"
        sid += f"/<txt|ctxt>[{c},{r.group(1) if r else '?'}]  (UiPath row/col, verify)"
    return sid


def action(activity):
    return {"NTypeInto": "type", "NClick": "click", "NGetText": "read", "NCheckState": "exists?",
            "NExtractDataGeneric": "read table", "NKeyboardShortcuts": "keys"}.get(activity, activity)


def main(src, dst):
    rows = list(csv.DictReader(open(src, encoding="utf-8")))
    out = OrderedDict()
    for r in rows:
        key = (r["window"], r["sap_id"], r["cell"])
        e = out.setdefault(key, {
            "tcode": tcode(r["window"]), "window": r["window"], "popup": r["popup"],
            "uipath_id": r["sap_id"], "cell": r["cell"], "scripting_id": scripting_id(r),
            "in_sap_automation": "", "dynamic": r["dynamic"], "actions": set(), "names": set(),
            "values": set(), "files": set(),
        })
        base = e["scripting_id"].split("  ")[0].split("/<")[0]
        e["in_sap_automation"] = "yes" if base in KNOWN or any(base.startswith(k + "/") for k in KNOWN
                                                                  if "tbl" in k or k.endswith("sub/1")) else ""
        e["actions"].add(action(r["activity"]))
        e["names"].add(r["display_name"])
        if r["value"]:
            e["values"].add(r["value"])
        e["files"].add(r["file"])
    fields = ["tcode", "window", "popup", "uipath_id", "cell", "scripting_id", "in_sap_automation",
              "dynamic", "actions", "names", "values", "files"]
    with open(dst, "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=fields)
        w.writeheader()
        for e in sorted(out.values(), key=lambda e: (e["tcode"], e["window"], e["uipath_id"], e["cell"])):
            w.writerow({k: " | ".join(sorted(v)) if isinstance(v, set) else v for k, v in e.items()})
    print(f"{len(rows)} raw -> {len(out)} unique elements")


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
