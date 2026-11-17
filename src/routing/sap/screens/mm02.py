"""MM02 - production versions of a material (docs/uipath/ui_elements.md 3.4).

Screen code from SAP_automation/change_bom/production_version.py (open_production_versions,
read_versions, enter_new_version, save_material, read_popup_text).
"""
from datetime import date

from routing.sap import elements as el
from routing.sap import table
from routing.sap.session import SapError


def open_versions(sap, material):
    """MM02 -> select views / org levels popups -> MRP view -> production version list (wnd[1])."""
    sap.start_transaction("MM02")
    sap.set_text(el.INIT_MATERIAL, material)
    sap.enter()
    sap.raise_on_error(f"MM02 {material}")
    for step in ("select views", "org levels"):
        if not sap.has_window(1):
            raise SapError(f"Expected popup '{step}' not shown ({sap.where()})")
        sap.enter(window=1)
    sap.press(el.MM02_PROD_VERSIONS)
    if not sap.exists(el.VERSION_TABLE):
        raise SapError(f"Production version list not shown ({sap.where()})")


def read_versions(sap):
    """Version numbers in the list, all pages, until the first blank row."""
    versions = []

    def collect(row):
        versions.append(table.cell_text(sap, el.VERSION_TABLE, el.VERSION_COL, row))
        return False
    table.find_row(sap, el.VERSION_TABLE, collect, blank_col=el.VERSION_COL)
    return [v for v in versions if v]


def add_version(sap, version, text, key, alt_bom, bom_usage="1"):
    """New Details (wnd[2]) -> fill -> Check -> close. Returns the Check warning text ('' = none)."""
    sap.press(el.VERSION_NEW_DETAILS)
    if not sap.has_window(2):
        raise SapError(f"New details popup not shown ({sap.where()})")
    sap.set_text(el.PV_VERSION, version)
    sap.set_text(el.PV_TEXT, text)
    sap.set_text(el.PV_VALID_FROM, date.today().strftime(el.PV_DATE_FORMAT))
    sap.set_text(el.PV_VALID_TO, el.PV_VALID_TO_VALUE)
    sap.find(el.PV_TASK_LIST_TYPE).key = "N"
    sap.set_text(el.PV_GROUP, key.group)
    sap.set_text(el.PV_COUNTER, key.counter)
    sap.set_text(el.PV_ALT_BOM, alt_bom)
    sap.set_text(el.PV_BOM_USAGE, bom_usage)
    sap.press(el.PV_CHECK)

    warning = ""
    if sap.has_window(3):               # group / counter / BOM not valid -> keep the text, close it
        warning = popup_text(sap, 3) or "Check warning (no text)"
        sap.press(f"wnd[3]/{el.BTN_ENTER}")
    sap.press(el.PV_CANCEL_CHECK)       # red cross, as in the recording
    sap.press(f"wnd[2]/{el.BTN_ENTER}")
    return warning


def delete_version(sap, version):
    """Select the row of `version` in the list and press Delete. VERIFY: confirmation popup."""
    row = table.find_row(sap, el.VERSION_TABLE,
                         lambda r: table.cell_text(sap, el.VERSION_TABLE, el.VERSION_COL, r) == version,
                         blank_col=el.VERSION_COL)
    if row is None:
        raise SapError(f"Production version {version} not in the list")
    sap.find(el.VERSION_TABLE).getAbsoluteRow(int(sap.find(el.VERSION_TABLE).VerticalScrollbar.Position) + row).selected = True
    sap.press(el.VERSION_DELETE)
    if sap.has_window(2):               # VERIFY: "delete?" confirmation
        sap.press(f"wnd[2]/{el.BTN_ENTER}")


def close_and_save(sap, what):
    """Close the version list and save the material. A popup after Save stops the step."""
    sap.press(f"wnd[1]/{el.BTN_ENTER}")
    sap.press(el.BTN_SAVE)
    if sap.has_window(1):
        raise SapError(f"Popup after Save of {what}: {popup_text(sap, 1)}")
    sap.raise_on_error(f"Save {what}")
    return sap.status()[1]


def popup_text(sap, window):
    """All visible texts of a popup (title + labels / message lines)."""
    texts = [sap.window_title(window)]
    for element in sap.find(f"wnd[{window}]/usr").Children:
        texts.append(str(getattr(element, "Text", "")).strip())
    return " | ".join(t for t in texts if t)
