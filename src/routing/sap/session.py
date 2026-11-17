"""SAP GUI session: connect, find elements, status bar, popups, reset. No business rules.

Connection code from SAP_automation/change_bom/connect.py (get_session, SlowSAP).
"""
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

    def reset(self):
        """Close popups and leave the transaction without saving, so the next row starts clean."""
        for window in (3, 2, 1):
            if self.has_window(window):
                self.find(f"wnd[{window}]").close()
        self.set_text(el.OKCODE, "/n")
        self.enter()
        if self.has_window(1):          # "Data will be lost" -> Yes
            yes = "wnd[1]/usr/btnSPOP-OPTION1"
            if self.exists(yes):
                self.press(yes)
