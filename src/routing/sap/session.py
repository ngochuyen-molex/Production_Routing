"""SAP GUI session: connect, find elements, status bar, popups, reset. No business rules.

Connection code from SAP_automation/change_bom/connect.py (get_session, SlowSAP).
"""
import re
import subprocess
import time

from routing.core.config import SAP_CONNECTION_NAME
from routing.sap import elements as el

SAP_LOGON_PATH = r"C:\Program Files (x86)\SAP\FrontEnd\SapGui\saplogon.exe"
STEP_DELAY = 0.5                        # slow mode: seconds after every action


class SapError(RuntimeError):
    """SAP did not do what the step expected; message includes the status bar."""


class SapConnectionError(SapError):
    pass


class SapSkip(SapError):
    """SAP refuses the material (status E3, does not exist): the row is skipped, not failed.
    UiPath: status bar contains MATERIAL STATUS / E3 / NOT EXIST -> Continue (docs/uipath_flows.md)."""


# status bar texts that mean "skip this row" (UiPath create_routing_*, inactive_routing, production_version_main).
# E3 is normally skipped while planning already (pipelines/run.SKIP_MATERIAL_STATUSES); this is the safety net.
# Other material status messages (S1, S2) are not a skip: a warning gets an extra Enter (pass_warnings).
SKIP_TEXT = re.compile(r"\bE3\b|NOT EXIST", re.IGNORECASE)
WARNING_ENTERS = 2                      # UiPath sends an extra Enter after the initial screen

# exit popup after "/n" in reset(): a save question is answered No, "data will be lost" Yes.
# \bsave\b so "unsaved" does not count as a save question.
SAVE_QUESTION = re.compile(r"\bsave\b", re.IGNORECASE)
DATA_LOST = re.compile(r"\blost\b|exit editing", re.IGNORECASE)


class SlowSAP:
    """Wraps a SAP GUI object: waits STEP_DELAY after actions, reads are not delayed.
    # from SAP_automation/change_bom/connect.py:SlowSAP"""
    ACTIONS = {"press", "sendVKey", "setFocus", "select"}
    SET_ACTIONS = {"text", "selected", "Position", "caretPosition", "key"}

    def __init__(self, obj):
        object.__setattr__(self, "_obj", obj)

    def __getattr__(self, name):
        value = getattr(self._obj, name)
        if hasattr(value, "_oleobj_"):
            return SlowSAP(value)
        if callable(value):
            def call(*args):
                result = value(*args)
                if name in self.ACTIONS:
                    print(f"  [slow] {name}{args}")
                    time.sleep(STEP_DELAY)
                return _wrap(result)
            return call
        return value

    def __setattr__(self, name, value):
        setattr(self._obj, name, value)
        if name in self.SET_ACTIONS:
            print(f"  [slow] {name} = {value!r}")
            time.sleep(STEP_DELAY)

    def __iter__(self):
        for item in self._obj:
            yield _wrap(item)


def _wrap(value):
    return SlowSAP(value) if hasattr(value, "_oleobj_") else value


def _raw_session():
    # from SAP_automation/change_bom/connect.py:_get_session
    import win32com.client      # pywin32, only needed when SAP is really used

    if "saplogon.exe" not in subprocess.run(["tasklist", "/FI", "IMAGENAME eq saplogon.exe"],
                                            capture_output=True, text=True).stdout.lower():
        subprocess.Popen([SAP_LOGON_PATH])
        time.sleep(5)

    application = None
    for attempt in range(5):
        try:
            application = win32com.client.GetObject("SAPGUI").GetScriptingEngine
            break
        except Exception:
            time.sleep(2)
    if application is None:
        raise SapConnectionError("Could not connect to the SAP GUI scripting engine "
                                 "(is scripting enabled in SAP GUI options?)")

    if application.Children.Count > 0 and application.Children(0).Children.Count > 0:
        return application.Children(0).Children(0)
    connection = application.OpenConnection(SAP_CONNECTION_NAME, True)
    time.sleep(3)
    if connection.Children.Count == 0:
        raise SapConnectionError("Connection opened but no session available")
    return connection.Children(0)


class SapSession:
    """Thin layer over the COM session; screens use only these methods."""

    def __init__(self, com_session):
        self.com = com_session

    @classmethod
    def connect(cls, slow=False):
        session = _raw_session()
        return cls(SlowSAP(session) if slow else session)

    # ---------------------------------------------------------------- elements
    def find(self, element_id):
        element = self.com.findById(element_id, False)
        if element is None:
            raise SapError(f"SAP element not found: {element_id} ({self.where()})")
        return element

    def exists(self, element_id):
        return self.com.findById(element_id, False) is not None

    def set_text(self, element_id, value):
        self.find(element_id).text = str(value)

    def get_text(self, element_id):
        return str(self.find(element_id).text).strip()

    def press(self, element_id):
        self.find(element_id).press()

    def enter(self, window=0):
        self.find(f"wnd[{window}]").sendVKey(0)

    def double_click(self, element_id, window=0):
        self.find(element_id).setFocus()
        self.find(f"wnd[{window}]").sendVKey(2)

    # ---------------------------------------------------------------- screens
    def start_transaction(self, tcode):
        self.set_text(el.OKCODE, f"/n{tcode}")
        self.enter()

    def status(self):
        """(type, text) of the status bar; type 'E' error, 'W' warning, 'S' success, '' none."""
        bar = self.find(el.STATUS_BAR)
        return str(getattr(bar, "MessageType", "") or "").strip(), str(bar.text).strip()

    def raise_on_error(self, what):
        kind, text = self.status()
        if kind in ("E", "A"):
            raise SapError(f"{what}: {text}")

    def pass_warnings(self, what):
        """After an Enter: a warning (W) in the status bar needs one more Enter (UiPath sends a
        second Enter in CA01 / CA02); at most WARNING_ENTERS times. Errors -> SapError."""
        for _ in range(WARNING_ENTERS):
            if self.status()[0] != "W":
                break
            self.enter()
        self.raise_on_error(what)

    def check_initial(self, what):
        """First screen of CA01 / CA02 / MM02: skip texts -> SapSkip, then pass_warnings."""
        kind, text = self.status()
        if SKIP_TEXT.search(text):
            raise SapSkip(f"{what}: {text}")
        self.pass_warnings(what)
        if SKIP_TEXT.search(self.status()[1]):
            raise SapSkip(f"{what}: {self.status()[1]}")

    def window_title(self, window=0):
        return str(self.find(f"wnd[{window}]").text).strip() if self.has_window(window) else ""

    def has_window(self, window):
        return self.exists(f"wnd[{window}]")

    def where(self):
        """Short description of the current screen, for error messages."""
        windows = [f"wnd[{n}] '{self.window_title(n)}'" for n in range(4) if self.has_window(n)]
        try:
            text = self.status()[1]
        except SapError:
            text = ""
        return ", ".join(windows) + (f", status '{text}'" if text else "")

    def popup_text(self, window):
        """All visible texts of a popup (title + labels / message lines)."""
        texts = [self.window_title(window)]
        if self.exists(f"wnd[{window}]/usr"):
            for element in self.find(f"wnd[{window}]/usr").Children:
                texts.append(str(getattr(element, "Text", "")).strip())
        return " | ".join(t for t in texts if t)

    def reset(self):
        """Close popups and leave the transaction WITHOUT saving, so the next row starts clean.
        The exit popup is read first: a save question gets No, "data will be lost" gets Yes
        (= leave, nothing saved); any other popup -> SapError, never a blind Yes."""
        for window in (3, 2, 1):
            if self.has_window(window):
                self.find(f"wnd[{window}]").close()
        self.set_text(el.OKCODE, "/n")
        self.enter()
        if not self.has_window(1):
            return
        text = self.popup_text(1)
        if SAVE_QUESTION.search(text):
            answer = el.POPUP_NO                    # "Save changes?" -> No
        elif DATA_LOST.search(text):
            answer = el.POPUP_YES                   # "Data will be lost. Exit?" -> Yes, leave unsaved
        else:
            raise SapError(f"Unknown popup while leaving without saving: '{text}'")
        if not self.exists(answer):
            raise SapError(f"Popup while leaving without saving has no expected button: '{text}'")
        self.press(answer)
        if self.has_window(1):
            raise SapError(f"Popup still open after leaving without saving: '{self.popup_text(1)}'")
