"""Initial application adapters.

These encode knowledge only — recognition, known controls, shortcuts, state
markers, safe/risky actions and known failure modes. The framework is the point;
a new adapter is a new record, not new engine code. Excel, VS Code, terminals and
PDF readers should PREFER structured/native paths where Eclipse already has them
(the file system, code intelligence, the terminal subsystem, document parsing) and
use Computer Use only when UI interaction is genuinely required.
"""

from __future__ import annotations

from .base import ApplicationAdapter, GenericAdapter


class ExcelAdapter(ApplicationAdapter):
    id = "excel"
    name = "Microsoft Excel"
    executables = ("excel.exe", "excel")
    title_patterns = (".xlsx", ".xlsm", ".xls", "excel", "workbook")
    has_native_api = True
    controls = {
        "name box": {"name": "Name Box", "role": "edit", "shortcut": "ctrl+g"},
        "formula bar": {"name": "Formula Bar", "role": "edit"},
        "save": {"name": "Save", "role": "button", "shortcut": "ctrl+s"},
        "cell": {"name": "", "role": "gridcell"},
    }
    shortcuts = {
        "save": "ctrl+s", "save_as": "F12", "undo": "ctrl+z", "redo": "ctrl+y",
        "find": "ctrl+f", "go_to": "ctrl+g", "edit_cell": "F2", "select_all": "ctrl+a",
        "new_sheet": "shift+F11", "recalc": "F9", "autosum": "alt+=",
    }
    ready_markers = ("ready",)
    busy_markers = ("calculating", "opening", "saving")
    safe_actions = ("observe", "read_cell", "navigate", "copy", "select")
    risky_actions = ("delete_sheet", "overwrite_workbook", "macro")
    failure_modes = ("macro_warning", "read_only_mode", "protected_sheet", "external_links_prompt")
    # NOTE: for bulk cell edits, prefer the structured file/data path. CUA is the
    # UI fallback; do not drive thousands of cells through mouse clicks.


class VSCodeAdapter(ApplicationAdapter):
    id = "vscode"
    name = "Visual Studio Code"
    executables = ("code.exe", "code", "code - insiders")
    title_patterns = ("visual studio code", " - code", "vscode")
    has_native_api = True
    controls = {
        "command palette": {"name": "Command Palette", "role": "edit", "shortcut": "ctrl+shift+p"},
        "quick open": {"name": "Go to File", "role": "edit", "shortcut": "ctrl+p"},
        "terminal": {"name": "Terminal", "role": "pane", "shortcut": "ctrl+`"},
        "sidebar": {"name": "Explorer", "role": "tree", "shortcut": "ctrl+shift+e"},
    }
    shortcuts = {
        "command_palette": "ctrl+shift+p", "quick_open": "ctrl+p", "save": "ctrl+s",
        "save_all": "ctrl+k ctrl+s", "terminal": "ctrl+`", "find": "ctrl+f",
        "replace": "ctrl+h", "go_to_symbol": "ctrl+shift+o",
    }
    safe_actions = ("observe", "navigate", "copy", "select")
    risky_actions = ("delete_file", "revert_all")
    failure_modes = ("extension_host_crash", "workspace_trust_prompt")
    # Normal code operations should use Eclipse's filesystem/code-intel tools.


class TerminalAdapter(ApplicationAdapter):
    id = "terminal"
    name = "Terminal"
    executables = ("windowsterminal.exe", "wt.exe", "cmd.exe", "powershell.exe", "pwsh.exe",
                   "conhost.exe", "bash", "gnome-terminal", "konsole", "xterm")
    title_patterns = ("terminal", "powershell", "command prompt", "bash", "cmd")
    has_native_api = True
    shortcuts = {"copy": "ctrl+shift+c", "paste": "ctrl+shift+v", "clear": "ctrl+l",
                 "interrupt": "ctrl+c", "new_tab": "ctrl+shift+t"}
    safe_actions = ("observe", "read", "copy")
    risky_actions = ("execute_command",)
    failure_modes = ("blocked_on_input", "pager_active", "long_running_command")
    # Shell COMMANDS should go through the terminal subsystem, not CUA. CUA is
    # for interacting with the terminal UI itself.


class ChromeAdapter(ApplicationAdapter):
    id = "chrome"
    name = "Google Chrome"
    executables = ("chrome.exe", "google chrome")
    title_patterns = ("google chrome", " - chrome")
    controls = {
        "address bar": {"name": "Address and search bar", "role": "edit", "shortcut": "ctrl+l"},
        "new tab": {"name": "New Tab", "role": "button", "shortcut": "ctrl+t"},
        "devtools": {"name": "Developer Tools", "role": "pane", "shortcut": "F12"},
    }
    shortcuts = {"address_bar": "ctrl+l", "new_tab": "ctrl+t", "close_tab": "ctrl+w",
                 "reload": "F5", "devtools": "F12", "find": "ctrl+f"}
    safe_actions = ("observe", "navigate", "copy", "select")
    risky_actions = ("clear_data", "install_extension")
    failure_modes = ("permission_prompt", "download_prompt", "auth_popup")
    # Page CONTENT should use the browser subsystem; CUA owns browser chrome only.


class EdgeAdapter(ChromeAdapter):
    id = "edge"
    name = "Microsoft Edge"
    executables = ("msedge.exe", "microsoft edge")
    title_patterns = ("microsoft edge", " - edge")


class PdfAdapter(ApplicationAdapter):
    id = "pdf"
    name = "PDF reader"
    executables = ("acrord32.exe", "acroread", "sumatrapdf.exe", "foxitreader.exe",
                   "evince", "preview")
    title_patterns = (".pdf", "pdf", "document")
    shortcuts = {"find": "ctrl+f", "next_page": "pagedown", "prev_page": "pageup",
                 "zoom_in": "ctrl+=", "zoom_out": "ctrl+-", "print": "ctrl+p"}
    safe_actions = ("observe", "read", "copy", "navigate")
    risky_actions = ("sign_document", "print")
    failure_modes = ("protected_document", "fillable_form", "signature_required")


class TradingTerminalAdapter(ApplicationAdapter):
    """Base for financial terminals — CUA is often the ONLY path here."""

    id = "trading_terminal"
    name = "Trading terminal"
    executables = ()
    title_patterns = ()
    has_native_api = False
    controls = {
        "buy": {"name": "Buy", "role": "button"},
        "sell": {"name": "Sell", "role": "button"},
        "symbol": {"name": "Symbol", "role": "edit"},
        "quantity": {"name": "Quantity", "role": "edit"},
        "order ticket": {"name": "Order Ticket", "role": "pane"},
    }
    safe_actions = ("observe", "read", "navigate", "select", "prepare_order")
    # Every financial mutation is risky and MUST pass the finance firewall.
    risky_actions = ("buy", "sell", "short", "cover", "submit_order",
                     "cancel_order", "modify_order", "transfer", "withdraw")
    failure_modes = ("market_closed", "insufficient_buying_power", "order_rejected",
                     "stale_price", "confirmation_changed", "wrong_account")
    # A terminal that is reconnecting/loading must not be driven blind.
    busy_markers = ("connecting", "loading", "synchronizing", "reconnecting")
    ready_markers = ("connected", "ready", "online")


class TradingViewAdapter(TradingTerminalAdapter):
    id = "tradingview"
    name = "TradingView"
    executables = ("tradingview", "tradingview.exe")
    title_patterns = ("tradingview",)
    controls = {
        **TradingTerminalAdapter.controls,
        "timeframe": {"name": "Interval", "role": "button"},
        "chart": {"name": "Chart", "role": "pane"},
        "watchlist": {"name": "Watchlist", "role": "list"},
    }
    shortcuts = {"symbol_search": "/", "screenshot": "alt+shift+s"}


class MT5Adapter(TradingTerminalAdapter):
    id = "mt5"
    name = "MetaTrader 5"
    executables = ("terminal64.exe", "metatrader", "mt5")
    title_patterns = ("metatrader", "meta trader", "mt5")
    controls = {
        **TradingTerminalAdapter.controls,
        "new order": {"name": "New Order", "role": "button", "shortcut": "F9"},
        "one click trading": {"name": "One Click Trading", "role": "button"},
        "algo trading": {"name": "Algo Trading", "role": "button"},
    }
    shortcuts = {"new_order": "F9", "market_watch": "ctrl+m", "navigator": "ctrl+n"}


class IBKRAdapter(TradingTerminalAdapter):
    id = "ibkr"
    name = "Interactive Brokers"
    executables = ("tws.exe", "tws", "ibgateway.exe", "ibkr")
    title_patterns = ("trader workstation", "interactive brokers", "ib gateway", "tws")
    controls = {
        **TradingTerminalAdapter.controls,
        "order entry": {"name": "Order Entry", "role": "pane"},
        "mosaic": {"name": "Mosaic", "role": "pane"},
    }
    failure_modes = TradingTerminalAdapter.failure_modes + ("gateway_disconnected", "two_factor_prompt")


class BloombergAdapter(TradingTerminalAdapter):
    id = "bloomberg"
    name = "Bloomberg Terminal"
    executables = ("bbcomm.exe", "blp.exe", "wintrv.exe")
    title_patterns = ("bloomberg", " - blp")
    controls = {
        "command line": {"name": "Command", "role": "edit"},
        **TradingTerminalAdapter.controls,
    }
    failure_modes = TradingTerminalAdapter.failure_modes + ("login_required", "biometric_prompt")


# The shipped adapter set. Order matters: the FIRST match wins, so a specific
# adapter precedes a general one (edge before chrome, mt5 before trading term).
ADAPTERS: tuple[ApplicationAdapter, ...] = (
    ExcelAdapter(), VSCodeAdapter(), TerminalAdapter(), EdgeAdapter(), ChromeAdapter(),
    PdfAdapter(), MT5Adapter(), IBKRAdapter(), TradingViewAdapter(), BloombergAdapter(),
    GenericAdapter(),
)


__all__ = [
    "ADAPTERS", "BloombergAdapter", "ChromeAdapter", "EdgeAdapter", "ExcelAdapter",
    "GenericAdapter", "IBKRAdapter", "MT5Adapter", "PdfAdapter", "TerminalAdapter",
    "TradingTerminalAdapter", "TradingViewAdapter", "VSCodeAdapter",
]
