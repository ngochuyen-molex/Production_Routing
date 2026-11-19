"""SAP GUI scripting element ids, one place (docs/uipath/ui_elements.md section 3).

`VERIFY` = taken from the UiPath XAML, not yet run from Python; check with the SAP GUI script
recorder before the first live run.
"""

# ------------------------------------------------------------ common
OKCODE = "wnd[0]/tbar[0]/okcd"
STATUS_BAR = "wnd[0]/sbar"
BTN_ENTER = "tbar[0]/btn[0]"            # relative to a window: f"wnd[1]/{BTN_ENTER}"
BTN_BACK = "wnd[0]/tbar[0]/btn[3]"
BTN_SAVE = "wnd[0]/tbar[0]/btn[11]"
POPUP_YES = "wnd[1]/usr/btnSPOP-OPTION1"     # standard SAP confirmation popup, first button
POPUP_NO = "wnd[1]/usr/btnSPOP-OPTION2"      # second button

# ------------------------------------------------------------ CA01 / CA02 initial screen
INIT_MATERIAL = "wnd[0]/usr/ctxt[0]"
INIT_PLANT = "wnd[0]/usr/ctxt[1]"
CA01_COPY_FROM = "wnd[0]/tbar[1]/btn[5]"

#first popup
# "Entry Option: Group" - groups of the material (CA01 + CA02); from SAP_automation routing.py
GROUP_POPUP_TABLE = "wnd[1]/usr/tblSAPLCPSLTCTRL_2110"
GROUP_POPUP_GROUP_COL = 0               # group only filled on the first row of each group
GROUP_POPUP_COUNTER_COL = 1
GROUP_POPUP_DESC_COL = 2

# CA01 copy dialog
TITLE_SELECT_TYPE = "Select Type"                       # popup title as in the UiPath scope
COPY_SELECT_TYPE_CONTINUE = "wnd[1]/tbar[0]/btn[0]"     # "Select Type" popup
COPY_MATERIAL = "wnd[1]/usr/ctxt[0]"                    # "Select Object to be Copied"
COPY_PLANT = "wnd[1]/usr/ctxt[1]"

#second pop up
COPY_LIST_TABLE = "wnd[1]/usr/tblSAPLCPSLTCTRL_2120"    # routings to copy from ("TL Groups")
# recorded 2026-11-19 (material 5051070099): ctxt[0,row] group (first row of each group only),
# txt[1,row] GCt, txt[7,row] description; columns between: lot sizes, unit, status, usage
COPY_LIST_GROUP_COL = 0
COPY_LIST_COUNTER_COL = 1
COPY_LIST_DESC_COL = 7                  # double-clicked; UiPath's tableCol='2' was a different count

# "Choose Alternative BOM" popup: list, element txt[row, column position]; from SAP_automation
BOM_POPUP = "wnd[1]/usr/sub/1"
BOM_POPUP_ALT_COL = 19                  # AltBOM; VERIFY: from SAP_automation, UiPath double-clicks col 8
BOM_POPUP_USAGE_COL = 0                 # BOM usage, UiPath main_bom_assignment reads txt[1,0]
PRODUCTION_BOM_USAGE = "1"              # usage 2 -> UiPath "check bom again"

# CA01 Header Data Check / Header Details
HEADER_DESCRIPTION = "wnd[0]/usr/sub/2/txt[1]"
HEADER_GROUP = "wnd[0]/usr/sub/2/ctxt[0]"
HEADER_COUNTER = "wnd[0]/usr/sub/2/txt[0]"
HEADER_STATUS = "wnd[0]/usr/sub/6/ctxt[1]"
HEADER_DELETION_FLAG = "wnd[0]/usr/sub/6/chk"           # CA02 header details
BTN_HEADER = "wnd[0]/tbar[1]/btn[5]"                    # Header (F5) on the operation overview
BTN_OPERATIONS = "wnd[0]/tbar[1]/btn[7]"                # Operations (CA01 header screens) / CompAlloc

# CA01 "Create Routing: Operation - Check": after the header Enter SAP stops on each copied operation
# without a setup value (status "Enter standard value Setup", e.g. C_AUTO MP03). Same fields as
# Operation Details; the setup unit field has no recorded id, it is found next to DETAIL_SETUP.
TITLE_OPERATION_CHECK = "Operation - Check"
SETUP_MISSING_TEXT = "Enter standard value Setup"
SETUP_DEFAULT = "1"
SETUP_DEFAULT_UNIT = "H"

# CA02 header overview (routings of the selected group); from SAP_automation routing.py
HEADER_LIST_TABLE = "wnd[0]/usr/tblSAPLCPDITCTRL_1200"
HEADER_LIST_COUNTER_COL = 0
HEADER_LIST_DESC_COL = 1

# ------------------------------------------------------------ operation overview / details
OPERATION_TABLE = "wnd[0]/usr/tblSAPLCPDITCTRL_1400"
OPERATION_WORK_CENTER_TITLES = ("Work center", "Work Center")   # column found by title at run time
OPERATION_BASE_QTY_COL = 5
OPERATION_DESC_COL = 6                  # double-click -> Operation Details

DETAIL_WORK_CENTER_TEXT = "wnd[0]/usr/sub/2/txt[2]"     # read
DETAIL_OPERATION_TEXT = "wnd[0]/usr/sub/2/txt[4]"
DETAIL_BASE_QTY = "wnd[0]/usr/sub/3/txt[3]"
DETAIL_HEADER_QTY = "wnd[0]/usr/sub/3/txt[0]"           # unit conversion header qty = tool cavity
DETAIL_SETUP = "wnd[0]/usr/sub/3/txt[6]"
DETAIL_EFFICIENCY = "wnd[0]/usr/sub/15/txt[11]"
DETAIL_UTILIZATION = "wnd[0]/usr/sub/15/txt[13]"

DETAIL_FIELDS = {                       # layout field name -> element id
    "op_text": DETAIL_OPERATION_TEXT,
    "base_qty": DETAIL_BASE_QTY,
    "cavity": DETAIL_HEADER_QTY,
    "setup": DETAIL_SETUP,
    "efficiency": DETAIL_EFFICIENCY,
    "utilization": DETAIL_UTILIZATION,
}

WORK_CENTER_DISPLAY_TEXT = "wnd[0]/usr/sub/1/txt[2]"    # Display Work Center: Basic Data

# ------------------------------------------------------------ component allocation (CA02)
# from SAP_automation/change_bom/routing.py; run there today
BTN_COMPONENT_ALLOCATION = "wnd[0]/tbar[1]/btn[7]"      # same button as BTN_OPERATIONS on CA01 header
COMPONENT_TABLE = "wnd[0]/usr/tblSAPLCMDITCTRL_1000"
COMPONENT_OPERATION_COL = 10            # txt[10,row] = assigned operation ("" = not assigned)
COMPONENT_DESC_COL = 13                 # material description
COMPONENT_SELECT = "chk[0,{row}]"       # relative to COMPONENT_TABLE
BTN_NEW_ASSIGNMENT = "wnd[0]/tbar[1]/btn[5]"
NEW_ASSIGNMENT_OPERATION = "wnd[1]/usr/txt[0]"

# ------------------------------------------------------------ MM02 production versions
# from SAP_automation/change_bom/production_version.py; identical in UiPath (ui_elements.md 2)
MM02_PROD_VERSIONS = "wnd[0]/usr/sub/6/btn"
VERSION_TABLE = "wnd[1]/usr/tblSAPLMDIAT_MKAL_NEW"
VERSION_COL = 0
VERSION_TEXT_COL = 1                    # version text; SAP_automation production_version_fix TEXT_COL, UiPath tableCol='1'
VERSION_NEW_DETAILS = "wnd[1]/tbar[0]/btn[7]"
VERSION_DELETE = "wnd[1]/tbar[0]/btn[14]"               # confirmed in 4 UiPath flows, no confirmation popup
PV_VERSION = "wnd[2]/usr/ctxt[0]"
PV_TEXT = "wnd[2]/usr/txt[0]"
PV_VALID_FROM = "wnd[2]/usr/ctxt[1]"
PV_VALID_TO = "wnd[2]/usr/ctxt[2]"
PV_TASK_LIST_TYPE = "wnd[2]/usr/cmb[1]"
PV_GROUP = "wnd[2]/usr/ctxt[3]"
PV_COUNTER = "wnd[2]/usr/txt[4]"
PV_ALT_BOM = "wnd[2]/usr/ctxt[6]"
PV_BOM_USAGE = "wnd[2]/usr/ctxt[7]"
PV_CHECK = "wnd[2]/usr/btn"
PV_CANCEL_CHECK = "wnd[2]/tbar[0]/btn[12]"   # VERIFY: SAP_automation recording; UiPath scope is ambiguous (wnd[2] or wnd[3])
PV_DATE_FORMAT = "%Y/%m/%d"
PV_VALID_TO_VALUE = "9999/12/31"
