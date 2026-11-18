"""Dump UiPath XAML workflows to readable pseudo-code + a UI element table.

Read-only helper for the UiPath -> Python migration (README.md Background).
Usage: python tools/uipath_dump.py "<uipath project dir>" docs/uipath/raw
Writes one <name>.txt (activity tree) per XAML and ui_elements_raw.csv.
"""
import csv
import re
import sys
from pathlib import Path
from xml.etree import ElementTree as ET

X_KEY = "{http://schemas.microsoft.com/winfx/2006/xaml}Key"
X_TYPE = "{http://schemas.microsoft.com/winfx/2006/xaml}TypeArguments"

# Tags that are layout / designer noise.
SKIP = {
    "WorkflowViewStateService.ViewState", "WorkflowViewState.IdRef", "VisualBasic.Settings",
    "TextExpression.NamespacesForImplementation", "TextExpression.ReferencesForImplementation",
    "VirtualizedContainerService.HintSize", "Dictionary", "Members", "Collection",
}
NOISE_ATTRS = {"HintSize", "IdRef", "ScopeGuid", "Version", "HealingAgentBehavior", "ContinueOnError",
               "Guid", "ScopeIdentifier", "InformativeScreenshot", "DesignTimeRectangle",
               "DesignTimeScaleFactor", "Reference", "ElementType", "ContentHash", "SearchSteps",
               "FuzzySelectorArgument", "Visibility", "WaitForReady", "Timeout", "DelayAfter",
               "DelayBefore", "AnnotationText", "VerifyOptions", "TargetAnchorable",
               "ElementVisibilityArgument", "UnSafe", "ActivateBefore", "InteractionMode",
               "KeyModifiers", "MouseButton", "EmptyFieldMode", "TopMost"}
SELECTOR_ATTRS = ("FullSelectorArgument", "ScopeSelectorArgument", "Selector", "SemanticSelectorArgument")
NOISE_PROPS = {"VerifyOptions", "OCREngine"}


def local(tag: str) -> str:
    return tag.split("}", 1)[-1]


def clean(v: str) -> str:
    v = v.replace("&quot;", '"').replace("[UiPath.UIAutomationNext.Enums.", "[").strip()
    v = re.sub(r"\[N\w+\.(\w+)\]", r"\1", v)
    v = re.sub(r"<Table .*</Table>", "<Table ...>", v, flags=re.S)
    return re.sub(r"\s+", " ", v)


def interesting_attrs(el):
    out = {}
    for k, v in el.attrib.items():
        if k == X_KEY:
            out["Key"] = v
            continue
        k = local(k).split(".")[-1]
        if k in NOISE_ATTRS or v in ("{x:Null}", ""):
            continue
        out[k] = clean(v)
    return out


class Dumper:
    def __init__(self, fname):
        self.fname = fname
        self.lines = []
        self.ui = []
        self.scope = []  # application card display names
        self.stack = []  # activity stack, so targets map to their owning activity

    def emit(self, depth, text):
        self.lines.append("  " * depth + text)

    def walk(self, el, depth=0):
        tag = local(el.tag)
        if tag in SKIP or "ViewState" in tag:
            return
        if "." in tag:
            self.prop(el, tag.split(".", 1)[1], depth)
            return
        if tag in ("ActivityAction", "DelegateInArgument", "Variable", "String"):
            for c in el:
                self.walk(c, depth)
            return
        if tag in ("InArgument", "OutArgument", "InOutArgument") and not list(el):
            return
        if tag in ("TargetApp", "TargetAnchorable"):
            self.target(el, depth)
            return
        attrs = interesting_attrs(el)
        dn = attrs.pop("DisplayName", "")
        key = attrs.pop("Key", None)
        sel = {k: attrs.pop(k) for k in list(attrs) if k in SELECTOR_ATTRS}
        desc = tag + (f" '{dn}'" if dn and dn != tag else "") + (f" <case {key}>" if key else "")
        extra = ", ".join(f"{k}={v}" for k, v in attrs.items())
        self.emit(depth, desc + (f" [{extra}]" if extra else ""))
        self.stack.append((tag, dn, attrs))
        if sel:
            self.target_sel(sel, depth)
        is_card = tag == "NApplicationCard"
        if is_card:
            self.scope.append(dn)
        for c in el:
            self.walk(c, depth + 1)
        if is_card:
            self.scope.pop()
        self.stack.pop()

    def prop(self, el, prop, depth):
        if prop in NOISE_PROPS:
            return
        if prop in ("Body", "Handler", "Argument", "Argument1", "Argument2"):
            for c in el:
                self.walk(c, depth)
            return
        if prop == "Variables":
            vs = [f"{c.get('Name')}:{c.get(X_TYPE) or ''}" + (f"={clean(c.get('Default'))}" if c.get("Default") else "")
                  for c in el]
            if vs:
                self.emit(depth, "vars: " + ", ".join(vs))
            return
        if prop == "Arguments":
            args = [f"{c.get(X_KEY)}({local(c.tag).replace('Argument', '')})={clean(c.text or '')}" for c in el]
            if any(a for a in args if not a.startswith("None")):
                self.emit(depth, "args: " + "; ".join(args))
            return
        if prop in ("Target", "TargetApp"):
            for c in el:
                self.target(c, depth)
            return
        kids = list(el)
        if kids and all(len(list(c)) == 0 for c in kids):
            vals = [clean(c.text or "") for c in kids if (c.text or "").strip()]
            if vals:
                self.emit(depth, f"{prop}: " + " | ".join(vals))
            return
        self.emit(depth, f"{prop}:")
        for c in kids:
            self.walk(c, depth + 1)

    def target(self, el, depth):
        attrs = interesting_attrs(el)
        sel = {k: v for k, v in attrs.items() if k in SELECTOR_ATTRS}
        if sel:
            self.target_sel(sel, depth)
        if "FilePath" in attrs:
            self.emit(depth, f"  @ app={attrs['FilePath']}")

    def target_sel(self, sel, depth):
        self.emit(depth, "  @ " + " | ".join(f"{k}={v}" for k, v in sel.items()))
        full = sel.get("FullSelectorArgument") or ""
        if "sap " in full:
            act = self.stack[-1] if self.stack else ("", "", {})
            self.record_ui(act[0], act[1], sel, act[2])

    def record_ui(self, tag, dn, sel, attrs):
        full = sel.get("FullSelectorArgument") or ""
        ids = re.findall(r"<sap [^>]*?\bid='([^']+)'", full)
        cell = " ".join(re.findall(r"(table(?:Row|Col)='[^']+'|colTooltip='[^']+')", full))
        title = re.search(r"title='([^']*)'", sel.get("ScopeSelectorArgument", ""))
        cls = re.search(r"cls='([^']*)'", sel.get("ScopeSelectorArgument", ""))
        self.ui.append({
            "file": self.fname, "card": " > ".join(self.scope), "activity": tag, "display_name": dn,
            "window": title.group(1) if title else "", "popup": "yes" if cls and cls.group(1) == "#32770" else "",
            "sap_id": ids[-1] if ids else "", "cell": cell, "dynamic": "yes" if full.startswith("[") else "",
            "value": attrs.get("Text") or attrs.get("TextString") or attrs.get("ExtractedData") or "",
            "selector": full,
        })


def main(src, dst):
    src, dst = Path(src), Path(dst)
    dst.mkdir(parents=True, exist_ok=True)
    allui = []
    for f in sorted(src.rglob("*.xaml")):
        if f.name.startswith("~"):  # Studio autosave copy
            continue
        rel = f.relative_to(src).as_posix()
        root = ET.parse(f).getroot()
        d = Dumper(rel)
        for c in root:
            if local(c.tag) == "Members":
                for p in c:
                    d.lines.append(f"ARG {p.get('Name')}: {p.get('Type')}")
        for c in root:
            d.walk(c)
        (dst / (rel.replace("/", "__") + ".txt")).write_text("\n".join(d.lines), encoding="utf-8")
        allui.extend(d.ui)
    with open(dst / "ui_elements_raw.csv", "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=list(allui[0].keys()))
        w.writeheader()
        w.writerows(allui)
    print(f"{len(allui)} ui rows")


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
