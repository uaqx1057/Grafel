"""Grafel - the memory layer for AI coding.

A minimal desktop app that maps any local folder or GitHub repo into a persistent
knowledge graph, then wires it into your AI tools (Copilot, Claude Code, Codex)
so they answer from the graph instead of re-reading the whole codebase - cutting
token/credit usage dramatically. Pure AST extraction = zero tokens to build.
"""

import json
import math
import os
import queue
import random
import re
import shutil
import socket
import subprocess
import sys
import tempfile
import threading
import time
import webbrowser
import tkinter as tk
from tkinter import messagebox, simpledialog, ttk

from grafel_core.chat_export import claude_exchanges, copilot_exchanges, trim_text
from grafel_core.brevity import (
    BREVITY_DEFAULT,
    BREVITY_START,
    BREVITY_LEVELS,
    brevity_dashboard_lines,
    compress_memory_file,
    default_memory_candidates,
    output_savings_snapshot,
    write_brevity_block,
)
from grafel_core.config import (
    ROUTING_START,
    merge_json_servers,
    parse_workspace_folders,
    write_routing_block,
)
from grafel_core.graphs import (
    diff_graph_snapshot,
    graph_artifact_state,
    graph_report_text,
    repo_install_health,
    graph_wired_status,
    workspace_wire_summary,
)
from grafel_core.live import (
    initial_meter_sessions,
    path_is_related,
    refresher_sessions,
    repo_live_session_health,
    session_in_scope as live_session_in_scope,
    watch_event_kind,
)
from grafel_core.meter_runtime import (
    claude_baseline_update,
    claude_prompt_summary,
    copilot_apply_events,
    copilot_ready_indexes,
    meter_fallback_message,
    meter_machine_sessions_message,
    meter_start_state,
    meter_unscoped_console_notice,
    prices_for_model,
    prompt_recording_decision,
    seed_baseline_if_missing,
)
from grafel_core.optimizer import build_optimizer_plan
from grafel_core.proof import append_graph_use_event, graph_use_summary, read_graph_use_events
from grafel_core.savings import (
    ab_report_lines,
    count_tokens,
    graph_token_stats,
    prompt_comparison_lines,
    question_match_stats,
    reduction_percent,
    repo_token_stats,
    savings_report_lines,
)
from grafel_core.strict_mcp import serve_stdio as serve_strict_mcp
from grafel_core.sessions import (
    accumulate_usage_bucket,
    claude_log_dir,
    codex_session_cwd_fast,
    fmt_tokens,
    human_ago as _human_ago,
    iter_codex_token_counts,
    iter_vscode_chat_events,
    list_ai_sessions,
    list_vscode_copilot_sessions,
    parse_claude_jsonl_chunk,
    read_complete_lines,
    scan_claude_usage,
    scan_codex_usage,
    scan_copilot_cli_usage,
    session_detector_catalog,
    session_cwd,
    session_cwd_fast,
    session_bypass_risk,
    session_graph_usage,
)
from grafel_core.workspace import find_workspace_for, load_config, save_config
from grafel_core.workflows import (
    build_graph,
    ensure_gitignore_entry,
    install_repo_mcp,
    install_selected_integrations,
    write_repo_brevity,
    write_repo_routing,
)
from grafel_core.watch_runtime import (
    classify_watch_line,
    terminate_watch_process,
    watch_exit_state,
    watch_popen_kwargs,
    watch_start_plan,
)

GITHUB_RE = re.compile(r"^https?://github\.com/([^/]+)/([^/\s]+?)(?:\.git)?/?$")
CONFIG_FILE = os.path.join(os.path.expanduser("~"), ".grafel.json")
APP_VERSION = "1.0.0"
APP_AUTHOR = "Codewithusman.com"

# --- Savings Report config ---
# Code file types counted as "full codebase context" an agent would otherwise read.
SAVINGS_CODE_EXT = {
    ".py", ".js", ".ts", ".tsx", ".jsx", ".java", ".go", ".rs", ".rb", ".php",
    ".c", ".h", ".cpp", ".hpp", ".cc", ".cs", ".swift", ".kt", ".dart", ".scala",
    ".m", ".mm", ".sh", ".ps1", ".sql", ".vue", ".svelte", ".html", ".css",
    ".scss", ".json", ".yaml", ".yml", ".toml", ".md", ".txt",
}
SAVINGS_SKIP_DIRS = {
    ".git", "graphify-out", "node_modules", ".venv", "venv", "env",
    "__pycache__", "dist", "build", ".next", ".nuxt", ".idea", ".vscode",
    "target", "bin", "obj", ".gradle", "vendor", ".dart_tool",
}
# Published INPUT prices per 1M tokens (shown on screen). Approximate list prices;
# users can override any/all in ~/.grafel.json -> "prices": {"Model": <usd_per_million>}.
SAVINGS_PRICES = {
    "Claude Sonnet": 3.00,
    "Claude Opus": 15.00,
    "GPT-4o": 2.50,
    "Gemini 2.5 Pro": 1.25,
}
# Per-model Claude rates ($/M tokens): input, cache-write, cache-read, output.
CLAUDE_RATES = {
    "opus":   {"in": 15.0, "cw": 18.75, "cr": 1.50, "out": 75.0},
    "sonnet": {"in": 3.0,  "cw": 3.75,  "cr": 0.30, "out": 15.0},
    "haiku":  {"in": 0.80, "cw": 1.00,  "cr": 0.08, "out": 4.0},
    "other":  {"in": 3.0,  "cw": 3.75,  "cr": 0.30, "out": 15.0},
}
# Query budget graphify caps a scoped answer at (tokens).
SAVINGS_QUERY_TOKENS = 2000
# Standard questions used by Benchmark mode.
BENCHMARK_QS = [
    "how does authentication work?",
    "where is the main entry point?",
    "how is data stored or persisted?",
    "what are the main modules and how do they connect?",
    "how is configuration handled?",
]

# Modern Windows folder picker (Vista+ IFileOpenDialog COM), with the legacy
# FolderBrowserDialog only as a fallback. Runs as a temp .ps1 (STA required).
FOLDER_PICKER_PS = r'''
$ErrorActionPreference = 'Stop'
try {
$src = @"
using System;
using System.Runtime.InteropServices;
public static class GrafelPicker {
[ComImport, Guid("DC1C5A9C-E88A-4dde-A5A1-60F82A20AEF7")] internal class FileOpenDialogRCW { }
[ComImport, Guid("42f85136-db7e-439c-85f1-e4075d135fc8"), InterfaceType(ComInterfaceType.InterfaceIsIUnknown)]
internal interface IFileOpenDialog {
[PreserveSig] uint Show(IntPtr parent);
void SetFileTypes(); void SetFileTypeIndex(); void GetFileTypeIndex();
void Advise(); void Unadvise(); void SetOptions(uint fos); void GetOptions(out uint fos);
void SetDefaultFolder(); void SetFolder(); void GetFolder(); void GetCurrentSelection();
void SetFileName(); void GetFileName(); void SetTitle([MarshalAs(UnmanagedType.LPWStr)] string t);
void SetOkButtonLabel(); void SetFileNameLabel(); void GetResult(out IShellItem si);
}
[ComImport, Guid("43826d1e-e718-42ee-bc55-a1e261c37bfe"), InterfaceType(ComInterfaceType.InterfaceIsIUnknown)]
internal interface IShellItem {
void BindToHandler(); void GetParent();
void GetDisplayName(uint sigdn, [MarshalAs(UnmanagedType.LPWStr)] out string name);
void GetAttributes(); void Compare();
}
public static string Pick() {
var d = (IFileOpenDialog)new FileOpenDialogRCW();
uint o; d.GetOptions(out o); d.SetOptions(o | 0x20 | 0x40);
d.SetTitle("Select project folder");
if (d.Show(IntPtr.Zero) != 0) return "";
IShellItem it; d.GetResult(out it);
string p; it.GetDisplayName(0x80058000, out p); return p;
}
}
"@
Add-Type -TypeDefinition $src -Language CSharp | Out-Null
$sel = [GrafelPicker]::Pick()
if ($sel) { [Console]::Out.Write($sel) }
} catch {
Add-Type -AssemblyName System.Windows.Forms | Out-Null
$fb = New-Object System.Windows.Forms.FolderBrowserDialog
$fb.Description = 'Select project folder'
if ($fb.ShowDialog() -eq [System.Windows.Forms.DialogResult]::OK) { [Console]::Out.Write($fb.SelectedPath) }
}
'''

# graphify's built-in per-tool installers: label -> CLI subcommand
# Each writes instruction files/hooks into the repo so that AI tool queries the
# graph (`graphify query`) instead of re-reading the whole codebase every time.
INTEGRATIONS = [
    ("VS Code Copilot", "vscode"),
    ("Claude Code", "claude"),
    ("Codex", "codex"),
    ("Cursor", "cursor"),
    ("Gemini CLI", "gemini"),
    ("Aider", "aider"),
    ("Windsurf", "windsurf"),
    ("Cline", "cline"),
    ("Continue", "continue"),
]
# Executable name used to auto-detect whether each AI tool is installed.
DETECT_BIN = {
    "vscode": "code", "claude": "claude", "codex": "codex",
    "cursor": "cursor", "gemini": "gemini", "aider": "aider",
    "windsurf": "windsurf",
}
# Tools graphify has no native installer for: we write their own rules file
# (relative to the repo) so they also route through the graph. JetBrains AI has
# no standard project-rules file, so it is intentionally omitted (honest).
CUSTOM_RULE_FILES = {
    "windsurf": os.path.join(".windsurf", "rules", "grafel.md"),
    "cline": os.path.join(".clinerules", "grafel.md"),
    "continue": os.path.join(".continue", "rules", "grafel.md"),
}
METER_SCOPE_OPTIONS = {
    "Repo Only": "repo",
    "Workspace Only": "workspace",
    "All PC Sessions": "all",
}
METER_SCOPE_LABELS = {value: key for key, value in METER_SCOPE_OPTIONS.items()}
STRICT_MODE_OPTIONS = {
    "Advisory": "advisory",
    "Required": "required",
    "Required + Alerts": "required_alerts",
}
STRICT_MODE_LABELS = {value: key for key, value in STRICT_MODE_OPTIONS.items()}
BREVITY_OPTIONS = {
    "Lite": "lite",
    "Full": "full",
    "Ultra": "ultra",
}
BREVITY_LABELS = {value: key for key, value in BREVITY_OPTIONS.items()}


def tool_installed(cmd):
    exe = DETECT_BIN.get(cmd, cmd)
    return bool(shutil.which(exe) or shutil.which(exe + ".cmd"))


def find_graphify():
    return shutil.which("graphify")


def resource_path(name):
    """Locate bundled assets both in dev and in a PyInstaller onefile exe."""
    base = getattr(sys, "_MEIPASS",
                   os.path.join(os.path.dirname(os.path.abspath(__file__)), "assets"))
    return os.path.join(base, name)


# graphify >= the #3799 fix re-execs itself to pin PYTHONHASHSEED and calls
# sys.stdout.flush() first - under pythonw / the windowed exe stdout is None,
# so every graphify command dies with exit 1. Pre-pinning the seed in our
# env (inherited by all children) makes graphify skip that re-exec.
os.environ.setdefault("PYTHONHASHSEED", "0")

# Pinned engine version - bump deliberately after testing a new graphifyy
# release (build.bat and .github/workflows/build.yml pin the same version).
GRAPHIFY_SPEC = "graphifyy[watch]==0.9.81"


def console_python():
    """Interpreter for engine subprocesses. pythonw.exe has no console, so
    sys.stdout/stderr are None and graphify (tested only from consoles) can
    crash silently with exit 1. Use the sibling python.exe instead - callers
    spawn with CREATE_NO_WINDOW, so no console window appears."""
    exe = sys.executable
    if os.name == "nt" and os.path.basename(exe).lower() == "pythonw.exe":
        alt = os.path.join(os.path.dirname(exe), "python.exe")
        if os.path.isfile(alt):
            return alt
    return exe


def graphify_cmd():
    """Resolve how to invoke the graphify engine, in preference order:
    python -m graphify -> bundled engine inside this exe -> system CLI shim.
    -m is preferred over the pip console-script shim (graphify.EXE) because
    that shim can be blocked by Windows Application Control policy
    (WinError 4551) even when the graphify module itself runs fine."""
    if getattr(sys, "frozen", False):
        return [sys.executable, "--run-graphify"]  # self-dispatch (bundled)
    try:
        import importlib.util
        if importlib.util.find_spec("graphify") is not None:
            return [console_python(), "-m", "graphify"]
    except Exception:
        pass
    exe = find_graphify()
    if exe:
        return [exe]
    return [console_python(), "-m", "graphify"]


def engine_available():
    if find_graphify() or getattr(sys, "frozen", False):
        return True
    try:
        import importlib.util
        return importlib.util.find_spec("graphify") is not None
    except Exception:
        return False
def run_cmd(cmd, log, cwd=None):
    """Run a command, stream output lines to log(). Returns (exit_code, full_output).
    Benign engine warnings (skill-version notices, empty-config files, API-key tips)
    are kept out of the console so the user sees a clean, confident progress log."""
    log(f"$ {' '.join(cmd)}\n")
    proc = subprocess.Popen(
        cmd,
        cwd=cwd,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        encoding="utf-8",
        errors="replace",
        creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
    )
    lines = []
    try:
        for line in proc.stdout:
            lines.append(line)
            if not _is_engine_noise(line):
                log(line)
        proc.wait()
    finally:
        if proc.stdout is not None:
            proc.stdout.close()
    return proc.returncode, "".join(lines)


# Benign engine chatter hidden from the console (kept in the returned output for
# parsing). These are informational notices, not errors the user must act on.
_ENGINE_NOISE = (
    "skill is from graphify",
    "run 'graphify install'",
    "would downgrade the skill",
    "skill references/ sidecar",
    "skill dir exists but skill.md",
    "produced zero nodes",
    "tip: set gemini_api_key",
    "for doc/paper/image changes run",
)


def _is_engine_noise(line):
    low = line.lower()
    return any(marker in low for marker in _ENGINE_NOISE)


# ---------- alien-tech theme ----------

BG = "#050810"        # void black-blue
PANEL = "#0a1626"     # dark panel
CYAN = "#00f0ff"      # primary neon
MAGENTA = "#ff2fd6"   # secondary neon
GREEN = "#39ff88"     # active/ok
RED = "#ff3860"       # error
DIM = "#31506b"       # disabled / faint
TEXT = "#9fd8cf"      # console text
SPIN = "⣾⣽⣻⢿⡿⣟⣯⣷"


class NeonButton(tk.Canvas):
    """Angular cyber-style button with hover glow and disabled state."""

    def __init__(self, master, text, command, color=CYAN, width=150, height=34,
                 state="normal"):
        super().__init__(master, width=width, height=height, bg=BG,
                         highlightthickness=0, bd=0)
        self.txt = text
        self.command = command
        self.color = color
        self.btn_state = state
        self.w, self.h = width, height
        self.hover = False
        self.bind("<Button-1>", self._click)
        self.bind("<Enter>", lambda e: self._set_hover(True))
        self.bind("<Leave>", lambda e: self._set_hover(False))
        self._draw()

    def _set_hover(self, on):
        self.hover = on
        self._draw()

    def _draw(self):
        self.delete("all")
        active = self.btn_state == "normal"
        c = self.color if active else DIM
        fill = "#122438" if (self.hover and active) else "#0a1420"
        cut = 12
        pts = [cut, 2, self.w - 2, 2, self.w - 2, self.h - cut,
               self.w - cut, self.h - 2, 2, self.h - 2, 2, cut]
        if self.hover and active:  # outer glow line
            self.create_polygon([p + (1 if i % 2 == 0 else 0) for i, p in enumerate(pts)],
                                fill="", outline=c, width=3)
        self.create_polygon(pts, fill=fill, outline=c, width=1)
        self.create_text(self.w // 2, self.h // 2, text=self.txt, fill=c,
                         font=("Consolas", 10, "bold"))
        # corner accents
        self.create_line(cut, 2, cut + 10, 2, fill=c, width=3)
        self.create_line(self.w - cut, self.h - 2, self.w - cut - 10, self.h - 2,
                         fill=c, width=3)

    def _click(self, _):
        if self.btn_state == "normal" and self.command:
            self.command()

    def configure(self, **kw):
        if "state" in kw:
            self.btn_state = kw.pop("state")
        if "text" in kw:
            self.txt = kw.pop("text")
        if kw:
            super().configure(**kw)
        self._draw()

    config = configure


class App:
    def __init__(self, root):
        self.root = root
        root.title("GRAFEL // ALIEN CORE")
        root.geometry("920x680")
        root.minsize(760, 540)
        root.configure(bg=BG)

        self.cfg = load_config(CONFIG_FILE)
        self.graph_html = None
        self.worker = None
        self.repo_path = None
        self.watch_proc = None
        self.meter_on = False
        self.meter_thread = None
        self._autowire_asked = None
        self._cfg_lock = threading.Lock()
        self._meter_scope = set()        # normalized folders the meter is scoped to
        self._meter_scope_dirs = set()   # Claude session dirs in scope
        self._meter_scope_state = {}
        self._meter_other_sessions = []
        self._status_text = "SYSTEM IDLE"
        self._spin_i = 0
        self._sweep = 0.0
        self._paused = False
        self._logq = queue.Queue()
        self._browsing = False
        self._last_metrics = None
        self._tray = None
        self._nodes = [[random.uniform(0, 900), random.uniform(8, 104),
                        random.uniform(-0.5, 0.5), random.uniform(-0.3, 0.3)]
                       for _ in range(16)]

        # dark ttk styling for the combobox + scrollbar
        style = ttk.Style(root)
        try:
            style.theme_use("clam")
        except tk.TclError:
            pass
        style.configure("TCombobox", fieldbackground=PANEL, background=PANEL,
                        foreground=CYAN, bordercolor=DIM, arrowcolor=CYAN,
                        insertcolor=CYAN, selectbackground=DIM,
                        selectforeground=CYAN)
        style.map("TCombobox", fieldbackground=[("readonly", PANEL)])
        style.configure("Vertical.TScrollbar", background=PANEL,
                        troughcolor=BG, bordercolor=BG, arrowcolor=CYAN)
        root.option_add("*TCombobox*Listbox.background", PANEL)
        root.option_add("*TCombobox*Listbox.foreground", CYAN)
        root.option_add("*TCombobox*Listbox.selectBackground", CYAN)
        root.option_add("*TCombobox*Listbox.selectForeground", BG)

        # animated neural-network header
        self.header = tk.Canvas(root, height=112, bg=BG, highlightthickness=0)
        self.header.pack(fill="x")

        frm = tk.Frame(root, bg=BG, padx=16, pady=6)
        frm.pack(fill="both", expand=True)

        # target input row
        row = tk.Frame(frm, bg=BG)
        row.pack(fill="x")
        tk.Label(row, text="◢ TARGET", bg=BG, fg=MAGENTA,
                 font=("Consolas", 10, "bold")).pack(side="left")
        self.path_var = tk.StringVar()
        self.entry = ttk.Combobox(row, textvariable=self.path_var,
                                  values=self.cfg.get("recent", []),
                                  font=("Consolas", 10))
        self.entry.pack(side="left", fill="x", expand=True, padx=10, ipady=4)
        NeonButton(row, "BROWSE", self.browse, color=CYAN, width=110).pack(side="left")

        # AI uplink panel
        integ = tk.LabelFrame(frm, text=" ◢ NEURAL LINKS // AI UPLINK ", bg=BG,
                              fg=MAGENTA, font=("Consolas", 9, "bold"), bd=1,
                              relief="solid", labelanchor="nw")
        integ.pack(fill="x", pady=(12, 0))
        saved = self.cfg.get("integrations", {})

        def check(parent, text, var):
            tk.Checkbutton(parent, text=text, variable=var, bg=BG, fg=TEXT,
                           activebackground=BG, activeforeground=CYAN,
                           selectcolor=PANEL, font=("Consolas", 9),
                           highlightthickness=0, bd=0).pack(side="left",
                                                            padx=(6, 8), pady=5)

        self.integ_vars = {}
        for label, cmd in INTEGRATIONS:
            # auto-detect installed tools; saved choice wins if present
            var = tk.BooleanVar(value=saved.get(cmd, tool_installed(cmd)))
            self.integ_vars[cmd] = var
            check(integ, label.upper(), var)
        self.hooks_var = tk.BooleanVar(value=saved.get("hooks", True))
        check(integ, "GIT HOOKS", self.hooks_var)
        self.gitignore_var = tk.BooleanVar(value=saved.get("gitignore", True))
        check(integ, ".GITIGNORE", self.gitignore_var)
        self.mcp_var = tk.BooleanVar(value=saved.get("mcp", True))
        check(integ, "MCP: CTX7+FS", self.mcp_var)

        # command deck (grouped rows so new product features fit without
        # forcing the whole window wider every time we add another action).
        btns = tk.Frame(frm, bg=BG)
        btns.pack(fill="x", pady=(12, 4))
        btns_primary = tk.Frame(btns, bg=BG)
        btns_primary.pack(fill="x")
        self.run_btn = NeonButton(btns_primary, "▶ INITIATE SCAN", self.start,
                                  color=GREEN, width=160)
        self.run_btn.pack(side="left")
        self.brevity_level_var = tk.StringVar(
            value=BREVITY_LABELS.get(self.cfg.get("brevity_level", BREVITY_DEFAULT), "Full")
        )
        self.strict_mode_var = tk.StringVar(
            value=STRICT_MODE_LABELS.get(self.cfg.get("strict_mode", "required_alerts"), "Required + Alerts")
        )
        self.optimize_btn = NeonButton(btns_primary, "◆ OPTIMIZE", self.run_optimizer,
                                       color=MAGENTA, width=116)
        self.optimize_btn.pack(side="left", padx=8)
        self.optimize_mode_var = tk.StringVar(value="Auto")
        self.optimize_mode_pick = ttk.Combobox(
            btns_primary,
            textvariable=self.optimize_mode_var,
            values=["Auto"],
            state="disabled",
            width=8,
            font=("Consolas", 9),
        )
        self.optimize_mode_pick.pack(side="left", padx=(0, 8), ipady=2)
        self.brevity_btn = NeonButton(btns_primary, "✂ BREVITY", self.install_brevity_mode,
                                      color=CYAN, width=116)
        self.brevity_btn.pack(side="left")
        self.brevity_pick = ttk.Combobox(
            btns_primary,
            textvariable=self.brevity_level_var,
            values=list(BREVITY_OPTIONS.keys()),
            state="readonly",
            width=8,
            font=("Consolas", 9),
        )
        self.brevity_pick.pack(side="left", padx=(8, 0), ipady=2)
        self.brevity_pick.bind("<<ComboboxSelected>>", self._on_brevity_changed)
        self.strict_mode_pick = ttk.Combobox(
            btns_primary,
            textvariable=self.strict_mode_var,
            values=list(STRICT_MODE_OPTIONS.keys()),
            state="readonly",
            width=18,
            font=("Consolas", 9),
        )
        self.strict_mode_pick.pack(side="left", padx=(8, 0), ipady=2)
        self.strict_mode_pick.bind("<<ComboboxSelected>>", self._on_strict_mode_changed)
        self.watch_btn = NeonButton(btns_primary, "◭ WATCH", self.toggle_watch,
                                    color=MAGENTA, width=105, state="disabled")
        self.watch_btn.pack(side="left", padx=8)
        self.meter_btn = NeonButton(btns_primary, "◉ LIVE METER", self.toggle_meter,
                                    color=GREEN, width=135, state="disabled")
        self.meter_btn.pack(side="left", padx=8)
        self.meter_scope_var = tk.StringVar(
            value=METER_SCOPE_LABELS.get(self.cfg.get("meter_scope_mode", "repo"), "Repo Only")
        )
        self.meter_scope_pick = ttk.Combobox(
            btns_primary,
            textvariable=self.meter_scope_var,
            values=list(METER_SCOPE_OPTIONS.keys()),
            state="readonly",
            width=12,
            font=("Consolas", 9),
        )
        self.meter_scope_pick.pack(side="left", padx=(8, 0), ipady=2)
        self.meter_scope_pick.bind("<<ComboboxSelected>>", self._on_meter_scope_changed)
        self.code_btn = NeonButton(btns_primary, "⌬ VS CODE", self.open_in_vscode,
                                   color=CYAN, width=110, state="disabled")
        self.code_btn.pack(side="left", padx=8)
        self.open_btn = NeonButton(btns_primary, "◉ VIEW GRAPH", self.open_graph,
                                   color=CYAN, width=135, state="disabled")
        self.open_btn.pack(side="left", padx=8)
        btns_status = tk.Frame(btns, bg=BG)
        btns_status.pack(fill="x", pady=(6, 0))
        self.status_var = tk.StringVar(value="◇ SYSTEM IDLE")
        self.status_lbl = tk.Label(btns_status, textvariable=self.status_var, bg=BG,
                                   fg=GREEN, font=("Consolas", 10, "bold"))
        self.status_lbl.pack(side="right")
        # Persistent "background services live" indicator so the user always sees
        # WATCH and LIVE METER running side by side, independent of the status text.
        self.svc_var = tk.StringVar(value="")
        self.svc_lbl = tk.Label(btns_status, textvariable=self.svc_var, bg=BG,
                                fg=GREEN, font=("Consolas", 9, "bold"))
        self.svc_lbl.pack(side="right", padx=(0, 14))

        btns2 = tk.Frame(frm, bg=BG)
        btns2.pack(fill="x", pady=(0, 4))
        btns_actions_a = tk.Frame(btns2, bg=BG)
        btns_actions_a.pack(fill="x")
        self.savings_btn = NeonButton(btns_actions_a, "▤ SAVINGS", self.show_savings,
                                      color=GREEN, width=118, state="disabled")
        self.savings_btn.pack(side="left")
        self.ab_btn = NeonButton(btns_actions_a, "⇄ A/B TEST", self.run_ab_test,
                                 color=MAGENTA, width=118, state="disabled")
        self.ab_btn.pack(side="left", padx=8)
        self.ask_btn = NeonButton(btns_actions_a, "? ASK GRAPH", self.run_ask,
                                  color=CYAN, width=125, state="disabled")
        self.ask_btn.pack(side="left")
        self.batch_btn = NeonButton(btns_actions_a, "▦ BATCH", self.run_batch,
                                    color=CYAN, width=100)
        self.batch_btn.pack(side="left", padx=8)
        self.dash_btn = NeonButton(btns_actions_a, "◪ DASHBOARD", self.show_dashboard,
                                   color=GREEN, width=135)
        self.dash_btn.pack(side="left")
        self.card_btn = NeonButton(btns_actions_a, "⎙ CARD", self.export_card,
                                   color=MAGENTA, width=95, state="disabled")
        self.card_btn.pack(side="left", padx=8)
        btns_actions_b = tk.Frame(btns2, bg=BG)
        btns_actions_b.pack(fill="x", pady=(6, 0))
        self.usage_btn = NeonButton(btns_actions_b, "⤓ USAGE", self.scan_usage,
                                    color=CYAN, width=105)
        self.usage_btn.pack(side="left")
        self.chatmd_btn = NeonButton(btns_actions_b, "⧩ CHAT MD", self.export_chats,
                                     color=GREEN, width=115)
        self.chatmd_btn.pack(side="left", padx=8)
        self.compress_btn = NeonButton(btns_actions_b, "▣ COMPRESS MD", self.compress_memory_docs,
                                       color=GREEN, width=135)
        self.compress_btn.pack(side="left")
        self.newwin_btn = NeonButton(btns_actions_b, "⧉ NEW WIN", self.open_new_window,
                                     color=CYAN, width=115)
        self.newwin_btn.pack(side="left", padx=8)

        # tabbed output console (Console / Insights / Q&A)
        style.configure("Grafel.TNotebook", background=BG, borderwidth=0)
        style.configure("Grafel.TNotebook.Tab", background=PANEL, foreground=TEXT,
                        padding=(16, 6), font=("Consolas", 9, "bold"),
                        borderwidth=0)
        style.map("Grafel.TNotebook.Tab",
                  background=[("selected", "#122438")],
                  foreground=[("selected", CYAN)])
        self.nb = ttk.Notebook(frm, style="Grafel.TNotebook")
        self.nb.pack(fill="both", expand=True)
        self._boxes = {}
        self._tab_frames = {}
        for key, title in (("console", "◢ CONSOLE"),
                           ("insights", "▤ INSIGHTS"),
                           ("qa", "? Q&A"),
                           ("graph", "◉ GRAPH")):
            fr = tk.Frame(self.nb, bg=DIM)
            box = tk.Text(fr, wrap="word", state="disabled", bg="#040a12", fg=TEXT,
                          insertbackground=CYAN, font=("Consolas", 9), bd=0,
                          padx=12, pady=10)
            box.pack(side="left", fill="both", expand=True, padx=1, pady=1)
            sb = ttk.Scrollbar(fr, command=box.yview)
            box.configure(yscrollcommand=sb.set)
            sb.pack(side="right", fill="y")
            for tag, color in (("cmd", CYAN), ("ok", GREEN), ("err", RED),
                               ("dim", "#5a7186"), ("mag", MAGENTA)):
                box.tag_configure(tag, foreground=color)
            self.nb.add(fr, text=title)
            self._boxes[key] = box
            self._tab_frames[key] = fr

        # Live multi-session view: scoped tabs first, machine-wide summary below.
        sess_fr = tk.Frame(self.nb, bg=DIM)
        self.sess_hint_var = tk.StringVar(
            value="  Start the Live Meter to load repo-linked AI sessions. "
                  "Machine-wide sessions are summarized separately unless you switch to ALL PC SESSIONS."
        )
        hint = tk.Label(sess_fr, bg="#040a12", fg="#5a7186", anchor="w",
                        font=("Consolas", 9), textvariable=self.sess_hint_var)
        hint.pack(fill="x")
        self.sess_scope_var = tk.StringVar(value="  Scoped sessions")
        self.sess_scope_lbl = tk.Label(sess_fr, bg=DIM, fg=CYAN, anchor="w",
                                       font=("Consolas", 9, "bold"),
                                       textvariable=self.sess_scope_var)
        self.sess_scope_lbl.pack(fill="x", pady=(4, 0))
        self.sess_nb = ttk.Notebook(sess_fr, style="Grafel.TNotebook")
        self.sess_nb.pack(fill="both", expand=True)
        self._session_boxes = {}
        self.other_sess_fr = tk.Frame(sess_fr, bg=DIM)
        self.other_sess_title_var = tk.StringVar(value="Machine-wide sessions outside this repo")
        tk.Label(self.other_sess_fr, bg=DIM, fg=MAGENTA, anchor="w",
                 font=("Consolas", 9, "bold"),
                 textvariable=self.other_sess_title_var).pack(fill="x", pady=(8, 2))
        self.other_sess_box = tk.Text(
            self.other_sess_fr,
            wrap="word",
            height=7,
            state="disabled",
            bg="#040a12",
            fg=TEXT,
            insertbackground=CYAN,
            font=("Consolas", 9),
            bd=0,
            padx=12,
            pady=10,
        )
        self.other_sess_box.pack(side="left", fill="both", expand=True, padx=1, pady=1)
        other_sb = ttk.Scrollbar(self.other_sess_fr, command=self.other_sess_box.yview)
        self.other_sess_box.configure(yscrollcommand=other_sb.set)
        other_sb.pack(side="right", fill="y")
        for tag, color in (("cmd", CYAN), ("ok", GREEN), ("err", RED),
                           ("dim", "#5a7186"), ("mag", MAGENTA)):
            self.other_sess_box.tag_configure(tag, foreground=color)
        self.nb.add(sess_fr, text="◈ SESSIONS")
        self._tab_frames["sessions"] = sess_fr

        self.log("◢ GRAFEL ALIEN CORE :: ONLINE\n", "mag")
        self.log("◢ ZERO-TOKEN AST ENGINE ARMED — AWAITING TARGET COORDINATES...\n\n", "dim")

        # menu bar (everything reachable, keeps the toolbar uncluttered)
        menubar = tk.Menu(root)
        analyze = tk.Menu(menubar, tearoff=0)
        analyze.add_command(label="Savings Report", command=self.show_savings)
        analyze.add_command(label="A/B Test", command=self.run_ab_test)
        analyze.add_command(label="Benchmark (5 questions)", command=self.run_benchmark)
        analyze.add_command(label="Ask the graph", command=self.run_ask)
        analyze.add_command(label="Real Usage Scan", command=self.scan_usage)
        analyze.add_command(label="Compress repo memory docs", command=self.compress_memory_docs)
        analyze.add_command(label="Export chats → Markdown digests",
                            command=self.export_chats)
        analyze.add_command(label="Dashboard", command=self.show_dashboard)
        analyze.add_command(label="Export savings card", command=self.export_card)
        menubar.add_cascade(label="Analyze", menu=analyze)
        repos = tk.Menu(menubar, tearoff=0)
        repos.add_command(label="Wire a VS Code workspace (multi-root)…",
                          command=self.wire_workspace)
        repos.add_command(label="Batch: graph all repos in a folder",
                          command=self.run_batch)
        repos.add_command(label="Merge repo graphs", command=self.merge_repos)
        repos.add_command(label="Schedule daily rebuild", command=self.schedule_rebuild)
        repos.add_command(label="Graph diff (since last snapshot)",
                          command=self.graph_diff)
        menubar.add_cascade(label="Repos", menu=repos)
        integ_m = tk.Menu(menubar, tearoff=0)
        integ_m.add_command(label="Register MCP query-server",
                            command=self.register_mcp_server)
        integ_m.add_command(label="Launch strict VS Code profile",
                            command=self.open_in_vscode)
        integ_m.add_command(label="Launch strict Claude Code profile",
                            command=self.launch_strict_claude)
        integ_m.add_command(label="Launch strict Codex profile",
                            command=self.launch_strict_codex)
        integ_m.add_command(label="Install Grafel Brevity Mode",
                            command=self.install_brevity_mode)
        menubar.add_cascade(label="Integrations", menu=integ_m)
        cloud_m = tk.Menu(menubar, tearoff=0)
        cloud_m.add_command(label="Upload graph to cloud", command=self.cloud_upload)
        cloud_m.add_command(label="Download team graph", command=self.cloud_download)
        menubar.add_cascade(label="Cloud", menu=cloud_m)
        helpm = tk.Menu(menubar, tearoff=0)
        helpm.add_command(label="Guided tour", command=self._welcome)
        helpm.add_command(label="Check for updates", command=self.check_updates)
        helpm.add_command(label="About Grafel", command=self.show_about)
        menubar.add_cascade(label="Help", menu=helpm)
        root.config(menu=menubar)

        root.protocol("WM_DELETE_WINDOW", self.on_close)
        # FX (continuous animation) is OFF by default for GPU-driver safety.
        # Enable by setting "fx": true in ~/.grafel.json.
        self.fx = bool(self.cfg.get("fx", False))
        self._last_busy = None
        self._busy = False
        self.header.bind("<Configure>",
                         lambda e: self.root.after_idle(self._safe_draw))
        if self.fx:
            self._animate()
        else:
            self.root.after_idle(self._safe_draw)
        self._tick_status()
        self._flush_log()

        # system tray (optional - graceful if pystray missing)
        try:
            self._setup_tray()
        except Exception as e:
            self.log(f"[tray] disabled: {e}\n", "dim")

        # first-run onboarding
        if not self.cfg.get("seen"):
            self.cfg["seen"] = True
            self._save_cfg_locked()
            self.root.after(700, self._welcome)

    # ---------- system tray ----------

    def _setup_tray(self):
        import pystray  # type: ignore  # optional; tray is disabled gracefully
        from PIL import Image  # type: ignore
        img = Image.open(resource_path("grafel.png"))

        def show(icon=None, item=None):
            self.root.after(0, self._tray_show)

        def watch(icon=None, item=None):
            self.root.after(0, self.toggle_watch)

        def quit_(icon=None, item=None):
            self.root.after(0, self._tray_quit)

        self._tray = pystray.Icon("grafel", img, "Grafel", pystray.Menu(
            pystray.MenuItem("Show Grafel", show, default=True),
            pystray.MenuItem("Toggle watch", watch),
            pystray.MenuItem("Quit", quit_),
        ))
        self._tray.run_detached()

    def _tray_show(self):
        try:
            self.root.deiconify()
            self.root.lift()
            self.root.focus_force()
        except tk.TclError:
            pass

    def _tray_quit(self):
        self.on_close(force=True)

    def _welcome(self):
        steps = [
            ("Welcome to Grafel",
             "Grafel maps your codebase into a graph so your AI tools answer from a\n"
             "~2k-token query instead of re-reading everything.\n\nStep 1 of 3"),
            ("1. Scan a repo",
             "Pick a folder or paste a GitHub URL (or Browse), then click\n"
             "▶ INITIATE SCAN. Grafel builds the graph (zero tokens) and wires\n"
             "your AI tools to it.\n\nStep 2 of 3"),
            ("2. See real savings",
             "? ASK GRAPH shows per-prompt cost (with vs without).\n"
             "⤓ USAGE scans your REAL AI spend from local logs.\n"
             "The Analyze / Repos menus hold Benchmark, Dashboard, Merge and more.\n\n"
             "Step 3 of 3"),
        ]
        for title, msg in steps:
            messagebox.showinfo(title, msg, parent=self.root)

    # ---------- animations ----------

    def _safe_draw(self):
        try:
            if self.root.winfo_exists() and not self._paused:
                self._draw_header()
        except tk.TclError:
            pass

    def _animate(self):
        try:
            if not self.root.winfo_exists():
                return
            if not self._paused:
                self._draw_header()
        except tk.TclError:
            return
        self.root.after(150, self._animate)

    def _draw_header(self):
        c = self.header
        w = max(c.winfo_width(), 300)
        h = 112
        c.delete("all")
        busy = self.worker is not None and self.worker.is_alive()
        base = GREEN if busy else CYAN

        # drifting node-graph constellation
        for n in self._nodes:
            n[0] = (n[0] + n[2] * (4 if busy else 2)) % w
            n[1] += n[3]
            if n[1] < 6 or n[1] > h - 6:
                n[3] = -n[3]
        for i, a in enumerate(self._nodes):
            for b in self._nodes[i + 1:]:
                dx, dy = a[0] - b[0], a[1] - b[1]
                if dx * dx + dy * dy < 9000:
                    c.create_line(a[0], a[1], b[0], b[1], fill="#0d3348", width=1)
        pulse = 0.5 + 0.5 * math.sin(time.time() * 3)
        r = 2 + pulse
        for n in self._nodes:
            c.create_oval(n[0] - r, n[1] - r, n[0] + r, n[1] + r,
                          fill=base, outline="")

        # scan sweep
        self._sweep = (self._sweep + (22 if busy else 9)) % (w + 240)
        x = self._sweep - 120
        for off, col in ((0, base), (-8, "#0a4a5a"), (-16, "#07303d")):
            c.create_line(x + off, 0, x + off, h, fill=col, width=2)

        # glowing title
        title = "G R A F E L"
        for dx, dy in ((-1, 0), (1, 0), (0, 1)):
            c.create_text(26 + dx, 40 + dy, text=title, anchor="w",
                          font=("Consolas", 22, "bold"), fill="#083a44")
        c.create_text(26, 40, text=title, anchor="w",
                      font=("Consolas", 22, "bold"), fill=base)
        c.create_text(27, 68, text="NEURAL CODEBASE MAPPER :: TOKEN-ZERO AST ENGINE",
                      anchor="w", font=("Consolas", 9), fill="#5a7186")

        # corner brackets
        for x0, y0, sx, sy in ((4, 4, 1, 1), (w - 4, 4, -1, 1),
                               (4, h - 4, 1, -1), (w - 4, h - 4, -1, -1)):
            c.create_line(x0, y0, x0 + 26 * sx, y0, fill=MAGENTA, width=2)
            c.create_line(x0, y0, x0, y0 + 14 * sy, fill=MAGENTA, width=2)

    def _tick_status(self):
        self._spin_i = (self._spin_i + 1) % len(SPIN)
        try:
            self._refresh_status()
        except tk.TclError:
            return
        self.root.after(150, self._tick_status)

    def _refresh_status(self):
        busy = (self.worker is not None and self.worker.is_alive()) or self._busy
        # Always-visible service badges: both WATCH and METER can run side by side.
        svc = []
        if self.watch_proc is not None and self.watch_proc.poll() is None:
            svc.append("◭ WATCH ●")
        if self.meter_on:
            svc.append("◉ METER ●")
        self.svc_var.set(("   ".join(svc) + "   ") if svc else "")
        if busy != self._last_busy:
            self._last_busy = busy
            if not self.fx:
                self._safe_draw()  # static mode: recolor header on state change only
        text = self._status_text.upper()
        if busy:
            self.status_lbl.configure(fg=CYAN)
            self.status_var.set(f"{SPIN[self._spin_i]} {text}")
        else:
            ok = "FAIL" not in text
            self.status_lbl.configure(fg=GREEN if ok else RED)
            self.status_var.set(f"{'◇' if ok else '⬧'} {text}")

    # ---------- UI helpers ----------

    def _pick_folder(self):
        """Show a folder picker (blocking); return a path or ''. Uses the modern
        Windows IFileOpenDialog on Windows, tkinter's dialog elsewhere."""
        if os.name != "nt":
            try:
                from tkinter import filedialog
                return filedialog.askdirectory(title="Select project folder") or ""
            except Exception:
                return ""
        ps1 = None
        try:
            fd, ps1 = tempfile.mkstemp(suffix=".ps1", prefix="grafel_pick_")
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                f.write(FOLDER_PICKER_PS)
            out = subprocess.run(
                ["powershell", "-NoProfile", "-STA", "-ExecutionPolicy",
                 "Bypass", "-File", ps1],
                capture_output=True, text=True, timeout=600,
                creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
            )
            folder = (out.stdout or "").strip()
            if out.returncode != 0 and out.stderr:
                self.log(f"[browse] picker error: {out.stderr.strip()[:300]}\n", "err")
            return folder if folder and os.path.isdir(folder) else ""
        except Exception as e:
            self.log(f"[browse] picker failed: {e}\n", "err")
            return ""
        finally:
            if ps1:
                try:
                    os.remove(ps1)
                except OSError:
                    pass

    def browse(self):
        """Modern Windows folder picker (IFileOpenDialog) in a subprocess - fully
        decoupled from the Tk event loop, so shell-extension (OneDrive) stalls can
        never freeze the app. Falls back to the legacy dialog on older systems."""
        if self._browsing:
            return
        self._browsing = True
        self.set_status("Awaiting folder selection")

        def worker():
            folder = self._pick_folder()

            def done():
                self._browsing = False
                self.set_status("System idle")
                if folder:
                    self.path_var.set(os.path.normpath(folder))
            self.root.after(0, done)

        threading.Thread(target=worker, daemon=True).start()

    def log(self, text, tag=None, box="console"):
        """Thread-safe: queue the line for a specific tab; a single UI timer
        flushes in batches so fast subprocesses can't flood the event loop."""
        self._logq.put((box, text, tag))

    def _select_tab(self, key):
        try:
            self.nb.select(self._tab_frames[key])
        except (tk.TclError, KeyError):
            pass

    def _flush_log(self):
        # The next tick is re-armed in `finally`: a TclError mid-flush (e.g. a
        # session tab destroyed under us) must never kill every future flush —
        # that used to freeze ALL tabs' logging for the rest of the session.
        try:
            items = []
            try:
                while len(items) < 500:
                    items.append(self._logq.get_nowait())
            except queue.Empty:
                pass
            if items:
                for box_key, text, tag in items:
                    box = (self._boxes.get(box_key)
                           or self._session_boxes.get(box_key)
                           or self._boxes["console"])
                    if tag is None:
                        if text.startswith("$"):
                            tag = "cmd"
                        elif "ERROR" in text or "FAILED" in text:
                            tag = "err"
                        elif "===" in text:
                            tag = "mag"
                        elif "OK" in text or "Done" in text:
                            tag = "ok"
                    try:
                        box.configure(state="normal")
                        box.insert("end", text, tag)
                        box.configure(state="disabled")
                    except tk.TclError:
                        continue
                # trim session tabs too — they used to grow unbounded during
                # long meter runs (only _boxes were capped)
                for box in list(self._boxes.values()) + list(self._session_boxes.values()):
                    try:
                        if float(box.index("end-1c").split(".")[0]) > 4000:
                            box.configure(state="normal")
                            box.delete("1.0", "1000.0")
                            box.configure(state="disabled")
                        box.see("end")
                    except tk.TclError:
                        pass
        except tk.TclError:
            pass
        finally:
            try:
                self.root.after(100, self._flush_log)
            except tk.TclError:
                pass  # app is being torn down

    def set_status(self, text):
        self._status_text = text
        self.root.after(0, self._refresh_status)

    def open_graph(self):
        if self.graph_html and os.path.exists(self.graph_html):
            webbrowser.open(f"file:///{self.graph_html.replace(os.sep, '/')}")
        else:
            messagebox.showinfo("Grafel", "No graph.html found yet. Run a scan first.",
                                parent=self.root)

    def open_in_vscode(self):
        if not self.repo_path:
            return
        self.prepare_strict_launcher_profile(self.repo_path, "VS Code")
        code = shutil.which("code") or shutil.which("code.cmd")
        if not code:
            messagebox.showinfo("Grafel", "VS Code 'code' command not found on PATH.",
                                parent=self.root)
            return
        subprocess.Popen([code, self.repo_path],
                         creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0)
        self.set_status("Strict VS Code profile launched")

    def prepare_strict_launcher_profile(self, path, tool_label):
        self.cfg["strict_mode"] = "required_alerts"
        if hasattr(self, "strict_mode_var"):
            self.strict_mode_var.set(STRICT_MODE_LABELS["required_alerts"])
        self._save_cfg_locked()
        self.log(f"\n=== Preparing strict {tool_label} profile ===\n", "mag")
        self.install_integrations(path)
        if self.mcp_var.get():
            self.install_mcp(path)
        self.ensure_gitignore(path)
        self.log("[launcher] grafel-strict MCP and helper commands are ready.\n", "ok")

    def launch_strict_cli_tool(self, cmd_name, label):
        if not self.repo_path:
            messagebox.showinfo("Grafel", "Run a scan or choose a target repo first.", parent=self.root)
            return
        exe = shutil.which(cmd_name) or shutil.which(cmd_name + ".cmd")
        if not exe:
            messagebox.showinfo("Grafel", f"{label} command not found on PATH.", parent=self.root)
            return
        self.prepare_strict_launcher_profile(self.repo_path, label)
        if os.name == "nt":
            subprocess.Popen(
                ["cmd", "/k", f'cd /d "{self.repo_path}" && "{exe}"'],
                cwd=self.repo_path,
            )
        else:
            subprocess.Popen([exe], cwd=self.repo_path)
        self.set_status(f"Strict {label} profile launched")

    def launch_strict_claude(self):
        self.launch_strict_cli_tool("claude", "Claude Code")

    def launch_strict_codex(self):
        self.launch_strict_cli_tool("codex", "Codex")

    def open_new_window(self):
        """Launch a second independent Grafel window (own process, no instance
        lock) so you can watch/scan several repos side by side."""
        if getattr(sys, "frozen", False):
            cmd = [sys.executable, "--new-window"]
        else:
            cmd = [sys.executable, os.path.abspath(__file__), "--new-window"]
        try:
            subprocess.Popen(cmd)
            self.set_status("New Grafel window launched")
        except OSError as e:
            messagebox.showerror("Grafel", f"Could not open a new window:\n{e}",
                                 parent=self.root)

    def remember(self, target):
        # runs on the pipeline worker thread — hold _cfg_lock across the whole
        # read-modify-write-persist (non-reentrant lock, so save_config directly)
        with self._cfg_lock:
            recent = self.cfg.get("recent", [])
            if target in recent:
                recent.remove(target)
            recent.insert(0, target)
            self.cfg["recent"] = recent[:10]
            self.cfg["integrations"] = {cmd: var.get() for cmd, var in self.integ_vars.items()}
            self.cfg["integrations"]["hooks"] = self.hooks_var.get()
            self.cfg["integrations"]["gitignore"] = self.gitignore_var.get()
            self.cfg["integrations"]["mcp"] = self.mcp_var.get()
            save_config(CONFIG_FILE, self.cfg)
        self.root.after(0, lambda: self.entry.configure(values=self.cfg["recent"]))

    # ---------- pipeline ----------

    def start(self):
        target = self.path_var.get().strip().strip('"')
        if not target:
            messagebox.showwarning("Grafel", "Enter a folder path or GitHub URL first.",
                                   parent=self.root)
            return
        if self.worker and self.worker.is_alive():
            return
        self._need_install = False
        if not engine_available():
            if messagebox.askyesno(
                "Grafel",
                "The Grafel engine is not installed yet.\n\n"
                "Install it automatically now? (one-time, ~30s)",
                parent=self.root,
            ):
                self._need_install = True
            else:
                return
        self.run_btn.configure(state="disabled")
        self.open_btn.configure(state="disabled")
        self.graph_html = None
        self.worker = threading.Thread(target=self.pipeline, args=(target,), daemon=True)
        self.worker.start()

    def pipeline(self, target):
        try:
            m = GITHUB_RE.match(target)
            if m:
                path = self.clone(target, m.group(1), m.group(2))
                if not path:
                    return
            else:
                path = os.path.abspath(target)
                if not os.path.isdir(path):
                    self.fail(f"Folder not found: {path}")
                    return

            self.remember(target)
            if "onedrive" in path.lower():
                self.log("\nNOTE: This project is inside OneDrive. graphify-out/ will be "
                         "re-synced on every rebuild - consider excluding it from OneDrive "
                         "sync or moving heavy projects outside OneDrive.\n")

            if self._need_install:
                self.set_status("Installing Grafel engine")
                self.log("\n=== Installing Grafel engine (one-time) ===\n")
                # NOTE: "graphifyy" (double y) IS the real PyPI distribution
                # name; the importable module is "graphify". Not a typo —
                # build.bat and CI install the same package.
                code, _ = run_cmd([console_python(), "-m", "pip", "install",
                                   GRAPHIFY_SPEC], self.log)
                if code != 0:
                    self.fail("Could not install the Grafel engine. "
                              f"Run: pip install {GRAPHIFY_SPEC}")
                    return
                self._need_install = False

            self.set_status("Scanning codebase :: zero tokens")
            self.log(f"\n=== Running graphify on: {path} ===\n")
            build = build_graph(path, run_cmd, graphify_cmd, self.log)
            if build["code"] != 0:
                self.fail(f"graphify update exited with code {build['code']}")
                return

            self.repo_path = path
            self.install_integrations(path)
            if self.mcp_var.get():
                self.install_mcp(path)
            if self.gitignore_var.get():
                self.ensure_gitignore(path)

            html = build["graph_html"]
            if html:
                self.graph_html = html
                self.log(f"\nDone. Graph: {html}\n")
                self.set_status("Scan complete")
                self.root.after(0, lambda: self.open_btn.configure(state="normal"))
                self.root.after(0, self.open_graph)  # auto-open in browser
            else:
                self.log("\nGraph built, but graph.html was not generated.\n")
                out = os.path.join(path, "graphify-out")
                self.log(f"Check output folder: {out}\n")
                self.set_status("Complete (no HTML)")
            self.root.after(0, lambda: self.watch_btn.configure(state="normal"))
            self.root.after(0, lambda: self.meter_btn.configure(state="normal"))
            self.root.after(0, lambda: self.code_btn.configure(state="normal"))
            self.root.after(0, lambda: self.savings_btn.configure(state="normal"))
            self.root.after(0, lambda: self.ab_btn.configure(state="normal"))
            self.root.after(0, lambda: self.ask_btn.configure(state="normal"))
            # already on the pipeline worker thread; _load_graph_report does
            # the repo walk here and marshals only the UI update itself
            self._load_graph_report(path)
        except Exception as e:
            self.fail(str(e))
        finally:
            self.root.after(0, lambda: self.run_btn.configure(state="normal"))

    def clone(self, url, owner, repo):
        self.set_status(f"Cloning {owner}/{repo}")
        self.log(f"=== Cloning {url} ===\n")
        code, out = run_cmd(graphify_cmd() + ["clone", url], self.log)
        if code != 0:
            # fall back to plain git clone
            dest = os.path.join(os.path.expanduser("~"), ".graphify", "repos", owner, repo)
            if not os.path.isdir(os.path.join(dest, ".git")):
                os.makedirs(os.path.dirname(dest), exist_ok=True)
                self.log("graphify clone failed, trying git clone…\n")
                code, _ = run_cmd(["git", "clone", "--depth", "1", url, dest], self.log)
                if code != 0:
                    self.fail("Clone failed. Check the URL and your network.")
                    return None
            return dest
        # parse printed path from graphify clone output
        for line in reversed(out.splitlines()):
            candidate = line.strip().strip('"')
            if candidate and os.path.isdir(candidate):
                return candidate
        default = os.path.join(os.path.expanduser("~"), ".graphify", "repos", owner, repo)
        if os.path.isdir(default):
            return default
        self.fail("Cloned, but could not locate the repo folder.")
        return None

    def install_integrations(self, path):
        """Wire every selected AI tool to the graph. Tools graphify supports use its
        native installer; the rest (Windsurf/Cline/Continue) get a rules file."""
        selected = [cmd for cmd, var in self.integ_vars.items() if var.get()]
        if not selected and not self.hooks_var.get():
            return
        self.set_status("Linking AI uplinks")
        self.log("\n=== Installing AI tool integrations ===\n")
        install_selected_integrations(
            path,
            selected,
            self.hooks_var.get(),
            CUSTOM_RULE_FILES,
            run_cmd,
            graphify_cmd,
            write_routing_block,
            self.log,
            write_brevity_block,
            self._brevity_level(),
            self._strict_mode(),
        )
        self.write_routing(path)
        self.install_brevity_mode(path=path, log_only=True)

    def ensure_gitignore(self, path):
        """Keep Grafel's outputs local: graph artifacts AND chat digests
        (grafel-chats/ contains full chat text — secrets pasted mid-conversation
        must not get committed by default; the feature is framed 'local only')."""
        ensure_gitignore_entry(path, "graphify-out", self.log)
        ensure_gitignore_entry(path, "grafel-chats", self.log)

    # ---------- MCP servers + tool routing ----------

    def install_mcp(self, path):
        """Configure per-repo MCP servers (Context7 + grafel-strict; plus the
        Filesystem server in Advisory mode only) and append tool-routing rules
        so agents pick the cheapest context source."""
        strict_mode = self._strict_mode()
        self.log("\n=== Configuring MCP servers ===\n")
        if strict_mode == "advisory" and not (shutil.which("npx") or shutil.which("npx.cmd")):
            self.log("[mcp] note: npx (Node.js) not found - filesystem server "
                     "will not start until Node.js is installed\n")
        install_repo_mcp(path, merge_json_servers, self.log, strict_mode)
        # Codex - global ~/.codex/config.toml (stdio only, registered once)
        self.codex_mcp()
        # Routing rules into every agent instruction file
        self.write_routing(path)

    def codex_mcp(self):
        codex_cfg = os.path.join(os.path.expanduser("~"), ".codex", "config.toml")
        try:
            existing = ""
            if os.path.exists(codex_cfg):
                with open(codex_cfg, encoding="utf-8", errors="replace") as f:
                    existing = f.read()
            if "[mcp_servers.context7]" in existing:
                self.log("[mcp] codex config.toml already has context7\n")
                return
            os.makedirs(os.path.dirname(codex_cfg), exist_ok=True)
            with open(codex_cfg, "a", encoding="utf-8") as f:
                if existing and not existing.endswith("\n"):
                    f.write("\n")
                f.write('\n[mcp_servers.context7]\ncommand = "npx"\n'
                        'args = ["-y", "@upstash/context7-mcp"]\n')
            self.log("[mcp] codex config.toml: added context7 (global)\n")
        except OSError as e:
            self.log(f"[mcp] codex config update failed: {e}\n")

    def write_routing(self, path):
        write_repo_routing(path, write_routing_block, self.log, self._strict_mode())

    def write_brevity(self, path):
        write_repo_brevity(path, write_brevity_block, self.log, self._brevity_level())

    def install_brevity_mode(self, path=None, log_only=False):
        path = path or self.repo_path
        if not path:
            messagebox.showinfo("Grafel", "Set a target repo first.", parent=self.root)
            return
        level = self._brevity_level()
        self.cfg["brevity_level"] = level
        self._save_cfg_locked()
        self.log(f"\n=== Installing Grafel Brevity Mode ({level}) ===\n", "mag")
        self.write_brevity(path)
        selected = [cmd for cmd, var in self.integ_vars.items() if var.get() and cmd in CUSTOM_RULE_FILES]
        for cmd in selected:
            rule = os.path.join(path, CUSTOM_RULE_FILES[cmd])
            write_brevity_block(rule, level, self.log)
        self.log("[brevity] concise rule blocks installed for repo instruction files.\n", "ok")
        if not log_only:
            self.set_status(f"Brevity mode: {level}")

    def compress_memory_docs(self):
        if not self.repo_path:
            messagebox.showinfo("Grafel", "Set a target repo first.", parent=self.root)
            return
        threading.Thread(target=self._compress_memory_docs_worker, daemon=True).start()

    def _compress_memory_docs_worker(self):
        self.set_status("Compressing memory docs")
        self.root.after(0, lambda: self._select_tab("insights"))
        level = self._brevity_level()
        paths = [p for p in default_memory_candidates(self.repo_path) if os.path.exists(p)]
        self.log(f"\n=== GRAFEL MEMORY COMPRESSION ({level}) ===\n", "mag", box="insights")
        if not paths:
            self.log("No compressible repo memory files found.\n", "err", box="insights")
            self.set_status("No memory docs found")
            return
        total_saved = 0
        changed = 0
        for path in paths:
            result = compress_memory_file(path, level)
            name = os.path.basename(path)
            if result.get("ok"):
                changed += 1
                total_saved += result["saved_tokens"]
                self.log(
                    f"✓ {name}: saved ~{result['saved_tokens']:,} tokens "
                    f"({result['before_tokens']:,} -> {result['after_tokens']:,})\n",
                    "ok",
                    box="insights",
                )
            else:
                self.log(f"• {name}: skipped ({result.get('reason', 'unknown')})\n", "dim", box="insights")
        if total_saved:
            self._record_memory_compression_saved(total_saved)
        self.log(
            f"\nMemory compression complete: {changed} changed, ~{total_saved:,} tokens removed from future context loads.\n",
            "mag",
            box="insights",
        )
        self.set_status("Memory compression complete")

    # ---------- watch mode ----------

    def toggle_watch(self):
        if self.watch_proc and self.watch_proc.poll() is None:
            terminate_watch_process(self.watch_proc)
            self.watch_proc = None
            self.watch_btn.configure(text="◭ WATCH")
            self.set_status("Watch offline")
            self.log("\n=== Watch stopped ===\n")
            return
        if not self.repo_path:
            return
        self._start_watch(self.repo_path)

    def _start_watch(self, path, quiet=False):
        """Start the file-watcher on a repo. Safe to call from any thread; the
        watcher streams its own rebuild output into the console so the user sees it
        working. WATCH runs independently of (and side by side with) the Live Meter.
        (No release_preflight here: that's a build/release check — in the installed
        exe Grafel.spec/installer.iss don't exist and the warning only confused
        users clicking WATCH.)"""
        self.watch_proc = subprocess.Popen(
            graphify_cmd() + ["watch", path],
            **watch_popen_kwargs(os.name),
        )
        plan = watch_start_plan(path, quiet)
        self.root.after(0, lambda: self.watch_btn.configure(text=plan["button_text"]))
        self.set_status(plan["status"])
        for text, tag in plan["logs"]:
            self.log(text, tag)
        threading.Thread(target=self._watch_reader,
                         args=(self.watch_proc,), daemon=True).start()

    def _watch_reader(self, proc):
        """Pump watcher stdout into the console and flag if it dies immediately."""
        started = time.time()
        saw_output = False
        try:
            for line in iter(proc.stdout.readline, ""):
                line = line.rstrip()
                event = classify_watch_line(line)
                if not event:
                    continue
                saw_output = True
                self.log(event["text"], event["tag"])
                if event["status"]:
                    self.set_status(event["status"])
        except Exception:
            pass
        # process ended
        code = proc.poll()
        if proc is self.watch_proc:
            self.watch_proc = None
            exit_state = watch_exit_state(code, started, saw_output, time.time())
            self.root.after(0, lambda: self.watch_btn.configure(text=exit_state["button_text"]))
            if exit_state["log"]:
                self.log(exit_state["log"][0], exit_state["log"][1])
            self.set_status(exit_state["status"])

    # ---------- live per-prompt cost meter ----------


    def _meter_scope_mode(self):
        return METER_SCOPE_OPTIONS.get(self.meter_scope_var.get(), "repo")

    def _on_meter_scope_changed(self, _event=None):
        self.cfg["meter_scope_mode"] = self._meter_scope_mode()
        self._save_cfg_locked()
        if self.meter_on:
            self.log(
                "\n[meter] scope changed - stop and restart LIVE METER to apply the new mode.\n",
                "dim",
                box="console",
            )

    def _brevity_level(self):
        return BREVITY_OPTIONS.get(self.brevity_level_var.get(), BREVITY_DEFAULT)

    def _on_brevity_changed(self, _event=None):
        self.cfg["brevity_level"] = self._brevity_level()
        self._save_cfg_locked()

    def _strict_mode(self):
        return STRICT_MODE_OPTIONS.get(self.strict_mode_var.get(), "required_alerts")

    def _on_strict_mode_changed(self, _event=None):
        self.cfg["strict_mode"] = self._strict_mode()
        self._save_cfg_locked()
        if self.repo_path:
            self.write_routing(self.repo_path)
        self.log(
            f"\n[strict] mode set to {STRICT_MODE_LABELS.get(self._strict_mode(), 'Advisory')}.\n",
            "ok",
            box="console",
        )

    def _set_other_sessions_summary(self, sessions, detector_counts=None):
        self._meter_other_sessions = list(sessions or [])
        if not sessions:
            if self.other_sess_fr.winfo_ismapped():
                self.other_sess_fr.pack_forget()
            self._write_other_sessions_box("")
            return
        detector_counts = dict(detector_counts or {})
        if not detector_counts:
            detector_counts = {"claude": 0, "copilot": 0, "codex": 0, "other": 0}
            for session in sessions:
                kind = session.get("kind") or "other"
                if kind not in detector_counts:
                    kind = "other"
                detector_counts[kind] += 1
        parts = []
        if detector_counts.get("claude"):
            parts.append(f"{detector_counts['claude']} Claude")
        if detector_counts.get("codex"):
            parts.append(f"{detector_counts['codex']} Codex")
        if detector_counts.get("copilot"):
            parts.append(f"{detector_counts['copilot']} Copilot")
        if detector_counts.get("other"):
            parts.append(f"{detector_counts['other']} other")
        summary = ", ".join(parts) if parts else f"{len(sessions)} session(s)"
        self.other_sess_title_var.set(
            f"Machine-wide sessions outside this scope ({len(sessions)}: {summary})"
        )
        catalog = session_detector_catalog()
        extra = [item["label"] for item in catalog if not item.get("implemented")]
        lines = [
            "Grafel is keeping your main live tabs scoped to the selected codebase.\n",
            f"\nDetected elsewhere on this PC: {summary}\n",
        ]
        for session in sessions[:24]:
            age = _human_ago(session.get("age", 0))
            level = (session.get("scope_level") or "machine").upper()
            cwd = session.get("cwd") or "(no cwd)"
            reasons = session.get("attribution_reasons") or []
            state, _usage, _bypass = self._session_savings_state(session)
            lines.append(
                f" - [{level}] {session.get('name', 'session')} | {session.get('detector', session.get('tool', 'AI'))} | {age} | {state}\n"
            )
            lines.append(f"   cwd: {cwd}\n")
            if reasons:
                lines.append(f"   why: {reasons[0]}\n")
        if len(sessions) > 24:
            lines.append(f"\n... and {len(sessions) - 24} more session(s).\n")
        if extra:
            lines.append("\nDetector foundation prepared for: " + ", ".join(extra) + "\n")
        lines.append("Switch LIVE METER scope to ALL PC SESSIONS if you want live tabs for every session above.\n")
        self._write_other_sessions_box("".join(lines))
        if not self.other_sess_fr.winfo_ismapped():
            self.other_sess_fr.pack(fill="x", pady=(6, 0))

    def _write_other_sessions_box(self, text):
        self.other_sess_box.configure(state="normal")
        self.other_sess_box.delete("1.0", "end")
        if text:
            self.other_sess_box.insert("end", text)
        self.other_sess_box.configure(state="disabled")

    def toggle_meter(self):
        """Open live tabs for repo/workspace-linked AI sessions, with machine-wide sessions summarized separately."""
        if self.meter_on:
            self.meter_on = False
            self.meter_btn.configure(text="◉ LIVE METER")
            self.set_status("Live meter off")
            self._set_other_sessions_summary([], {})
            return
        scope_mode = self._meter_scope_mode()
        meter = meter_start_state(
            self.repo_path,
            scope_mode,
            find_workspace_for,
            parse_workspace_folders,
            claude_log_dir,
            list_ai_sessions,
            lambda path: codex_session_cwd_fast(path) or session_cwd_fast(path),
        )
        self._meter_scope = meter["scope"]
        self._meter_scope_dirs = meter["dirs"]
        self._meter_scope_folders = meter["folders"]
        self._meter_scope_state = meter["scope_state"]
        all_sessions = meter["all_sessions"]
        sessions = meter["sessions"]
        other_sessions = meter.get("other_sessions", [])
        if not sessions and not meter["has_any"]:
            messagebox.showinfo(
                "Grafel Live Meter",
                "No Claude Code, Codex, or VS Code Copilot Chat sessions found for this "
                "machine/repo yet.\n\nSend one prompt in either tool, then start "
                "the Live Meter. It reads local logs only (never uploads).",
                parent=self.root)
            return
        if not sessions:
            title, body = meter_machine_sessions_message(
                self._meter_scope_folders,
                meter.get("out_of_scope_count", 0),
                meter.get("out_of_scope_counts", {}),
            )
            if not messagebox.askyesno(
                title,
                body,
                    parent=self.root):
                return
            sessions = all_sessions
            self._meter_scope = set()            # user chose unscoped
            self._meter_scope_dirs = set()
            self._meter_scope_state = dict(self._meter_scope_state, mode="all", scope=set(), dirs=set(), folders=[])
            notice, tag = meter_unscoped_console_notice()
            self.log(notice, tag, box="console")
        elif scope_mode != "all" and meter.get("out_of_scope_count", 0):
            self.log(
                f"\n[meter] monitoring {len(sessions)} in-scope session(s); "
                f"{meter['out_of_scope_count']} additional AI session(s) exist elsewhere on this machine.\n",
                "dim",
                box="console",
            )
        self._set_other_sessions_summary(
            [] if self._meter_scope_state.get("mode") == "all" else other_sessions,
            meter.get("out_of_scope_counts", {}),
        )
        self.meter_on = True
        self.meter_btn.configure(text="⏹ STOP METER")
        label = self.meter_scope_var.get().upper()
        self.set_status(f"Live meter ({label}): {len(sessions)} sessions")
        self._build_session_tabs(sessions)
        self.root.after(0, lambda: self._select_tab("sessions"))
        for s in sessions:
            self._start_session_monitor(s)
        threading.Thread(target=self._session_refresher, daemon=True).start()

    def _start_session_monitor(self, s):
        if s.get("kind") == "copilot":
            target = self._copilot_monitor
        elif s.get("kind") == "codex":
            target = self._codex_monitor
        else:
            target = self._session_monitor
        threading.Thread(target=target, args=(s,), daemon=True).start()

    def _session_in_scope(self, s):
        """True if a session belongs to the meter's current repo/workspace scope."""
        return live_session_in_scope(s, self._meter_scope, self._meter_scope_dirs, lambda path: codex_session_cwd_fast(path) or session_cwd_fast(path))

    def _build_session_tabs(self, sessions):
        """(Re)build the scoped live tabs."""
        for tab in self.sess_nb.tabs():
            self.sess_nb.forget(tab)
        self._session_boxes.clear()
        if self._meter_scope_state.get("mode") == "all":
            self.sess_scope_var.set("  All detected AI sessions on this PC")
        elif self._meter_scope_state.get("mode") == "workspace":
            self.sess_scope_var.set("  Workspace-linked sessions")
        else:
            self.sess_scope_var.set("  Repo-linked sessions")
        for s in sessions:
            self._add_session_tab(s)

    def _add_session_tab(self, s):
        if s["dir"] in self._session_boxes:
            return
        fr = tk.Frame(self.sess_nb, bg=DIM)
        box = tk.Text(fr, wrap="word", state="disabled", bg="#040a12", fg=TEXT,
                      insertbackground=CYAN, font=("Consolas", 9), bd=0,
                      padx=12, pady=10)
        box.pack(side="left", fill="both", expand=True, padx=1, pady=1)
        sb = ttk.Scrollbar(fr, command=box.yview)
        box.configure(yscrollcommand=sb.set)
        sb.pack(side="right", fill="y")
        for tag, color in (("cmd", CYAN), ("ok", GREEN), ("err", RED),
                           ("dim", "#5a7186"), ("mag", MAGENTA)):
            box.tag_configure(tag, foreground=color)
        icon = s["status"].split()[0]
        scope_tag = {"repo": "R", "workspace": "W", "machine": "M"}.get(
            s.get("scope_level"),
            "R" if self._meter_scope_state.get("mode") != "all" else "M",
        )
        attr_tag = "H" if s.get("hard_link") else "?"
        state, _usage, _bypass = self._session_savings_state(s)
        graph_tag = {"graph-using": "G", "linked-bypassed-graph": "!", "linked-not-using-graph": "-", "not-linked": "?"}.get(state, "-")
        self.sess_nb.add(fr, text=f"{scope_tag}{attr_tag}{graph_tag} {icon} {s['name']}")
        self._session_boxes[s["dir"]] = box

    def _session_refresher(self):
        """While the meter runs, add scoped live tabs for new sessions and refresh the machine-wide summary."""
        while self.meter_on:
            time.sleep(4)
            try:
                fresh = refresher_sessions(
                    self._meter_scope_state,
                    parse_workspace_folders,
                    list_ai_sessions,
                    lambda path: codex_session_cwd_fast(path) or session_cwd_fast(path),
                )
                self.root.after(
                    0,
                    lambda data=fresh: self._set_other_sessions_summary(
                        [] if self._meter_scope_state.get("mode") == "all" else data.get("other", []),
                        {},
                    ),
                )
                for s in fresh.get("scoped", []):
                    if s["dir"] not in self._session_boxes and self.meter_on:
                        self.root.after(0, lambda ss=s: self._add_session_tab(ss))
                        time.sleep(0.3)  # let the tab be created before monitoring
                        self._start_session_monitor(s)
                        self.log(f"\n◉ New AI session/chat opened: {s['name']} "
                                 "(new tab added)\n", "ok", box="console")
            except Exception:
                pass

    def _save_cfg_locked(self):
        with self._cfg_lock:
            save_config(CONFIG_FILE, self.cfg)

    def _baseline_for(self, real_cwd, bkey, baselines):
        """Look up the recorded cache-read baseline for a repo. If none has ever
        been measured (e.g. the repo was wired before any unwired session ran, so
        claude_baseline_update never got a sample), seed an estimated one from the
        repo's own token size so 'proven' savings isn't permanently unreachable."""
        if not bkey:
            return None
        # baselines is self.cfg["meter_baselines"], shared across monitor threads.
        # The repo_token_stats walk (full os.walk + tokenize, slow on large or
        # OneDrive-synced repos) runs OUTSIDE _cfg_lock: the Tk main thread also
        # acquires _cfg_lock synchronously in UI callbacks (_save_cfg_locked via
        # _on_brevity_changed etc.), so holding it across the walk would freeze
        # the whole GUI until the walk finished. Only the fast seed+persist step
        # holds the lock, with the membership check repeated inside it so that
        # if two monitors both walked concurrently, only the first to acquire
        # the lock seeds and persists — no double-write, no clear()/update()
        # window visible to readers.
        # (_cfg_lock is non-reentrant, so save_config is called directly here.)
        if bkey not in baselines and real_cwd and os.path.isdir(real_cwd):
            repo_tokens = repo_token_stats(real_cwd, SAVINGS_CODE_EXT, SAVINGS_SKIP_DIRS)["tokens"]
            with self._cfg_lock:
                if bkey not in baselines:  # re-check: another thread may have seeded meanwhile
                    seeded_baselines, seeded = seed_baseline_if_missing(baselines, bkey, repo_tokens)
                    if seeded:
                        baselines.clear()
                        baselines.update(seeded_baselines)
                        save_config(CONFIG_FILE, self.cfg)
        with self._cfg_lock:
            return baselines.get(bkey, {}).get("cr")

    def _session_graph_usage(self, session):
        path = session.get("file") or session.get("dir") or ""
        return session_graph_usage(path) if path else {"detected": False, "matches": []}

    def _session_bypass_risk(self, session):
        path = session.get("file") or session.get("dir") or ""
        return session_bypass_risk(path) if path else {"detected": False, "matches": []}

    def _session_repo_proof(self, session):
        if not (self.repo_path and session.get("hard_link")):
            return None
        events = [e for e in read_graph_use_events(self.repo_path, limit=25) if e.get("success")]
        if not events:
            return None
        session_mtime = float(session.get("mtime", 0) or 0)
        session_age = float(session.get("age", 999999) or 999999)
        newest = events[-1]
        event_ts = float(newest.get("ts", 0) or 0)
        if session_age < 3600 or event_ts >= max(0, session_mtime - 300):
            return newest
        return None

    def _session_savings_state(self, session):
        usage = self._session_graph_usage(session)
        bypass = self._session_bypass_risk(session)
        if usage["detected"]:
            return "graph-using", usage, bypass
        proof = self._session_repo_proof(session)
        if proof:
            return "graph-using", {"detected": True, "matches": [f"repo proof: {proof.get('source', 'unknown')}"]}, bypass
        if session.get("hard_link") and bypass["detected"]:
            return "linked-bypassed-graph", usage, bypass
        if session.get("hard_link"):
            return "linked-not-using-graph", usage, bypass
        return "not-linked", usage, bypass

    def _log_session_identity(self, session, box):
        attr = session.get("attribution", "outside").upper()
        level = (session.get("scope_level") or "machine").upper()
        self.log(f"Attribution: {attr} ({level})\n", "dim", box=box)
        for reason in session.get("attribution_reasons") or []:
            self.log(f" - {reason}\n", "dim", box=box)
        savings_state, usage, bypass = self._session_savings_state(session)
        if savings_state == "graph-using":
            self.log("Savings state: graph usage detected in this session log.\n", "ok", box=box)
            if usage["matches"]:
                self.log(f" - evidence: {usage['matches'][0]}\n", "dim", box=box)
        elif savings_state == "linked-bypassed-graph":
            self.log("Savings state: linked but bypassed graph.\n", "err", box=box)
            if bypass["matches"]:
                self.log(f" - bypass evidence: {bypass['matches'][0]}\n", "dim", box=box)
        elif savings_state == "linked-not-using-graph":
            self.log("Savings state: linked to this repo, but graph usage not yet detected.\n", "err", box=box)
        else:
            self.log("Savings state: not linked to this repo scope.\n", "err", box=box)

    def _copilot_monitor(self, s):
        """Replay + live-tail a VS Code Copilot Chat session into its tab —
        requests, prompt/completion tokens, and Copilot premium credits (credits
        are the unit your Copilot plan actually meters)."""
        box = s["dir"]
        path = s["file"]
        self.log(f"=== LIVE METER :: {s['name']} ===\n", "mag", box=box)
        self.log("GitHub Copilot (VS Code) session. Usage = requests + tokens + "
                 "premium\ncredits — read locally from VS Code's own chat log.\n",
                 "dim", box=box)
        self._log_session_identity(s, box)
        reqs = []          # [{'text','pt','ct','cr'}] in request order
        printed = 0
        pos = 0
        last_activity = time.time()
        replayed = False

        def print_req(i):
            r = reqs[i]
            tok = (r["pt"] or 0) + (r["ct"] or 0)
            self.log(f"\n--- Request #{i + 1} ---\n", "ok", box=box)
            if r["text"]:
                one = " ".join(r["text"].split())[:90]
                self.log(f"   “{one}”\n", "dim", box=box)
            self.log(f"   tokens: {tok:,}  (prompt {r['pt']:,} · "
                     f"completion {r['ct']:,})\n", "mag", box=box)
            if r["cr"]:
                self.log(f"   Copilot credits: {r['cr']:.2f}\n", box=box)
            tpt = sum((x["pt"] or 0) + (x["ct"] or 0) for x in reqs[:i + 1])
            tcr = sum(x["cr"] or 0 for x in reqs[:i + 1])
            self.log(f"   session so far: {i + 1} requests · "
                     f"{fmt_tokens(tpt)} tokens · {tcr:.1f} credits\n", box=box)

        while self.meter_on:
            events, pos = iter_vscode_chat_events(path, pos)
            if events:
                last_activity = time.time()
            reqs = copilot_apply_events(reqs, events)
            if not replayed:
                replayed = True
                for idx in copilot_ready_indexes(reqs, printed, replayed=False, idle_seconds=0):
                    print_req(idx)
                    printed = idx + 1
                self.log("   — caught up; now live —\n", "dim", box=box)
            else:
                ready = copilot_ready_indexes(reqs, printed, replayed=True, idle_seconds=time.time() - last_activity)
                for idx in ready:
                    print_req(idx)
                    printed = idx + 1
            time.sleep(1.5)

    def _codex_monitor(self, s):
        """Replay Codex token-count updates, then tail them live for the active session."""
        box = s["dir"]
        path = s["file"]
        cwd = s.get("cwd") or codex_session_cwd_fast(path)
        self.log(f"=== LIVE METER :: {s['name']} ===\n", "mag", box=box)
        self.log("Codex session. Usage is read locally from Codex session logs.\n", "dim", box=box)
        if cwd:
            self.log(f"Workspace: {cwd}\n", "dim", box=box)
        self._log_session_identity(s, box)
        pos = 0
        seen_total = None
        replayed = False
        while self.meter_on:
            events, pos = iter_codex_token_counts(path, pos)
            if events:
                for event in events:
                    total = event["total"]
                    delta = event["last"]
                    if replayed and seen_total == total["all"]:
                        continue
                    seen_total = total["all"]
                    self.log(
                        f"\n--- Update ---\n"
                        f"   last: {fmt_tokens(delta['all'])} tokens "
                        f"(in {fmt_tokens(delta['input'])} | cached {fmt_tokens(delta['cached'])} | "
                        f"out {fmt_tokens(delta['output'])} | reasoning {fmt_tokens(delta['reasoning'])})\n",
                        "ok",
                        box=box,
                    )
                    self.log(
                        f"   session so far: {fmt_tokens(total['all'])} tokens "
                        f"(in {fmt_tokens(total['input'])} | cached {fmt_tokens(total['cached'])} | "
                        f"out {fmt_tokens(total['output'])} | reasoning {fmt_tokens(total['reasoning'])})\n",
                        "mag",
                        box=box,
                    )
            if not replayed:
                replayed = True
                self.log("   - caught up; now live -\n", "dim", box=box)
            time.sleep(1.5)

    def _session_monitor(self, s):
        """Replay a session's cost history into its tab, then tail it live. Runs per
        session; all monitors stop when meter_on goes False."""
        import glob
        box = s["dir"]
        proj_dir = s["dir"]
        F = float(self.cfg.get("codebase_context_fraction", 0.5))

        def newest():
            js = glob.glob(os.path.join(proj_dir, "*.jsonl"))
            return max(js, key=os.path.getmtime) if js else None

        cur = newest()
        pos = 0                                       # replay this session from start
        real_cwd = session_cwd(cur) if cur else None
        baselines = self.cfg.setdefault("meter_baselines", {})
        bkey = (os.path.normcase(os.path.normpath(real_cwd))
                if real_cwd and os.path.isdir(real_cwd) else None)
        base_cr = self._baseline_for(real_cwd, bkey, baselines)
        self.log(f"=== LIVE METER :: {s['name']} ===\n", "mag", box=box)
        self.log("Replaying this session's usage history, then following it live.\n",
                 "dim", box=box)
        self.log("Usage = requests + tokens. $ figures are API-EQUIVALENT value — on "
                 "a\nClaude Pro/Max or Copilot subscription that is NOT what you "
                 "pay.\n", "dim", box=box)
        self._log_session_identity(s, box)
        # Workspace-aware: this one Claude session usually spans a whole multi-root
        # workspace, so report the workspace membership + every project's wire status.
        ws_file, folders = (find_workspace_for(real_cwd, parse_workspace_folders)
                            if real_cwd and os.path.isdir(real_cwd) else (None, []))
        if ws_file and len(folders) > 1:
            wsname = os.path.basename(ws_file).rsplit(".code-workspace", 1)[0]
            self.log(f"Workspace: {wsname}  ({len(folders)} interlinked projects)\n",
                     "dim", box=box)
            self._report_workspace_wire_status(folders, box=box)
        elif real_cwd and os.path.isdir(real_cwd):
            self._report_wire_status(real_cwd, box=box)
        seen, bucket, last_activity = set(), None, time.time()
        state = {"n": 0, "reqs": 0, "tok": 0, "cost": 0.0,
                 "opp": 0.0, "opp_tok": 0, "realized": 0.0, "saved_tok": 0}

        def flush(b, caught_up):
            if not b or not b["msgs"]:
                return
            nonlocal base_cr
            wired_now = all(self._graph_wired_status(real_cwd)) if bkey else False
            # Price this prompt at the model it actually ran on (opus/sonnet/
            # haiku/other), not a hardcoded Sonnet rate.
            prices = prices_for_model(b.get("model"), CLAUDE_RATES)
            summary = claude_prompt_summary(state, b, base_cr, wired_now, F, prices)
            if not summary:
                return
            state.update(summary["state"])
            self.log(f"\n--- Prompt #{state['n']} ({b['msgs']} requests) ---\n",
                     "ok", box=box)
            self.log(f"   tokens: {summary['token_total']:,}  (cache-read {b['cr']:,} · "
                     f"out {b['out']:,})\n", "mag", box=box)
            self.log(f"   API-equiv: ${summary['real_cost']:.4f}  (cache re-read ${summary['cache_read_cost']:.4f})\n",
                     "dim", box=box)
            # Historical replay (meter start / resumed chat file) must be
            # side-effect-free: display only, never re-persist old savings or
            # re-feed the baseline with duplicate samples.
            decision = prompt_recording_decision(
                caught_up, summary["proven"], summary["saved_tokens"]
            )
            if summary["proven"]:
                self.log(f"   ✓ PROVEN saved {summary['saved_tokens']:,} tokens "
                         f"(~{int(summary['cache_read_per_request']):,}/turn vs ~{int(base_cr):,} baseline)\n",
                         "ok", box=box)
                if decision["record_saved"]:
                    self._record_saved(summary["saved_tokens"])
                else:
                    self.log("   (replayed history — shown, not re-recorded)\n",
                             "dim", box=box)
            else:
                self.log(f"   recoverable if wired: ~{summary['recoverable_tokens']:,} tokens\n", "ok",
                         box=box)
            if decision["update_baseline"]:
                # baselines is shared self.cfg state — mutate and persist under
                # _cfg_lock (non-reentrant, so save_config directly, not
                # _save_cfg_locked) so other monitor threads never observe the
                # clear()/update() window or lose this update.
                with self._cfg_lock:
                    updated_baselines, rec = claude_baseline_update(
                        baselines, bkey, wired_now, summary["cache_read_per_request"]
                    )
                    if rec:
                        baselines.clear()
                        baselines.update(updated_baselines)
                        base_cr = rec["cr"]
                        if rec["n"] % 3 == 0:
                            save_config(CONFIG_FILE, self.cfg)
            tail = (f"{fmt_tokens(state['saved_tok'])} tok PROVEN saved"
                    if state["realized"] else
                    f"~{fmt_tokens(state['opp_tok'])} tok recoverable")
            self.log(f"   session so far: {state['reqs']:,} requests · "
                     f"{fmt_tokens(state['tok'])} tokens "
                     f"(${state['cost']:.2f} API-equiv) · {tail}\n", box=box)

        replayed = False
        while self.meter_on:
            f = newest()
            if f and f != cur:
                # A resumed session's new jsonl re-contains the prior transcript:
                # treat the new file as another replay pass (side-effect-free).
                cur, pos, seen, bucket, replayed = f, 0, set(), None, False
                real_cwd = session_cwd(cur)
                bkey = (os.path.normcase(os.path.normpath(real_cwd))
                        if real_cwd and os.path.isdir(real_cwd) else None)
                base_cr = self._baseline_for(real_cwd, bkey, baselines)
                self.log("\n◉ New chat in this session — now following it.\n",
                         "ok", box=box)
            if not cur:
                time.sleep(1.5)
                continue
            # Newline-boundary-safe tail: only complete lines are consumed, so a
            # poll landing mid-write re-reads that line whole next time instead
            # of dropping both halves. Truncation reset is handled inside.
            chunk, pos = read_complete_lines(cur, pos)
            if chunk:
                events, seen = parse_claude_jsonl_chunk(chunk, seen)
                for kind, payload in events:
                    if kind == "user":
                        flush(bucket, replayed)
                        bucket = {"in": 0, "cr": 0, "cw": 0, "out": 0, "msgs": 0}
                        last_activity = time.time()
                    elif kind == "assistant_usage":
                        bucket = accumulate_usage_bucket(bucket, payload)
                        if payload.get("model"):
                            bucket["model"] = payload["model"]
                        last_activity = time.time()
            if not replayed:
                replayed = True
                # last prompt of the replay: still history, still display-only
                flush(bucket, False)
                bucket = None
                self.log("   — caught up; now live —\n", "dim", box=box)
            elif bucket and bucket["msgs"] and (time.time() - last_activity) > 6:
                flush(bucket, replayed)
                bucket = None
            time.sleep(1.5)

    def _graph_wired_status(self, path):
        return graph_wired_status(path, ROUTING_START)

    def _report_wire_status(self, path, box="insights"):
        """Tell the user, in the meter, whether the live repo is actually wired —
        and if not, offer to wire it so the cost above stops being wasted."""
        has_graph, has_routing = self._graph_wired_status(path)
        name = os.path.basename(path)
        if has_graph and has_routing:
            self.log(f"\n   ✓ graph is WIRED for {name} — ask the agent to query the "
                     "graph and this cost drops on the next prompts.\n", "ok",
                     box=box)
            return
        miss = []
        if not has_graph:
            miss.append("no graph built")
        if not has_routing:
            miss.append("routing not installed")
        self.log(f"\n   ⚠ GRAPH NOT WIRED for {name} ({', '.join(miss)}).\n", "err",
                 box=box)
        self.log("   The cost above is the FULL un-optimized price — nothing is being\n",
                 "err", box=box)
        self.log("   saved yet. Grafel can wire it now so future prompts cost less.\n",
                 "err", box=box)
        self.root.after(0, lambda p=path: self._offer_autowire(p))

    def _report_workspace_wire_status(self, folders, box="insights"):
        """Report wire status for every project in a multi-root workspace, and offer
        to wire the whole workspace if any project is missing the graph/routing."""
        summary = workspace_wire_summary(folders, ROUTING_START)
        wired = summary["wired"]
        unwired = summary["unwired"]
        if not unwired:
            self.log(f"\n   ✓ ALL {len(folders)} workspace projects are WIRED — the "
                     "agent can query the graph across the whole workspace.\n", "ok",
                     box=box)
            return
        self.log(f"\n   ⚠ {len(wired)}/{len(folders)} workspace projects wired. "
                 f"NOT wired: {', '.join(unwired)}\n", "err", box=box)
        self.log("   Wire the WHOLE workspace so every project's queries are cheap and\n",
                 "err", box=box)
        self.log("   cross-project questions work — nothing is saved on the unwired ones.\n",
                 "err", box=box)
        self.root.after(0, lambda p=folders[0]: self._offer_autowire(p))

    def _offer_autowire(self, path):
        if self._autowire_asked == path:
            return
        self._autowire_asked = path
        ws_file, folders = find_workspace_for(path, parse_workspace_folders)
        if ws_file and len(folders) > 1:
            names = ", ".join(os.path.basename(f) for f in folders)
            wsname = os.path.basename(ws_file)
            choice = messagebox.askyesnocancel(
                "Grafel — wire the whole workspace?",
                f"'{os.path.basename(path)}' belongs to a multi-root workspace:\n"
                f"    {wsname}\n"
                f"    {len(folders)} interlinked projects: {names}\n\n"
                "YES = wire the ENTIRE workspace (build every project's graph, merge\n"
                "         into one cross-project graph, install routing everywhere).\n"
                "         Best when the projects reference each other.\n\n"
                "NO = wire only this one folder.\n\n"
                "CANCEL = do nothing.",
                parent=self.root)
            if choice is None:
                return
            targets = folders if choice else [path]
            threading.Thread(target=self._autowire_worker,
                             args=(targets, ws_file if choice else None),
                             daemon=True).start()
            return
        if messagebox.askyesno(
            "Grafel — wire the graph and start saving?",
            f"Your live Claude session is working in:\n    {path}\n\n"
            "…but the graph isn't wired there, so every prompt pays the full "
            "un-optimized cost shown in the meter.\n\n"
            "Wire it now? Grafel will:\n"
            "  •  build the knowledge graph (AST — no tokens, no API cost)\n"
            "  •  install routing so the agent queries the graph instead of "
            "loading whole files\n"
            "  •  install your selected AI-tool integrations + git hooks\n\n"
            "New prompts (or a fresh session) should then carry far less context.",
                parent=self.root):
            threading.Thread(target=self._autowire_worker,
                             args=([path], None), daemon=True).start()

    def _autowire_worker(self, paths, ws_file=None):
        multi = len(paths) > 1
        label = (os.path.basename(ws_file).rsplit(".code-workspace", 1)[0]
                 if ws_file else os.path.basename(paths[0]))
        self.set_status(f"Wiring {'workspace' if multi else 'graph'}: {label}")
        self.root.after(0, lambda: self._select_tab("console"))
        self.log(f"\n=== AUTO-WIRE :: {'workspace ' if multi else ''}{label} ===\n",
                 "mag")
        self._busy = True
        try:
            self._do_autowire(paths, ws_file, multi, label)
        finally:
            self._busy = False

    def _do_autowire(self, paths, ws_file, multi, label):
        if not engine_available():
            self.log("[auto-wire] graph engine not available.\n", "err")
            self.set_status("Auto-wire failed")
            return
        # If WATCH is live, pause it during wiring so the routing-file writes don't
        # trigger a rebuild storm, then resume it — both keep running side by side.
        resume_watch = None
        if self.watch_proc is not None and self.watch_proc.poll() is None:
            resume_watch = self.repo_path
            self.log("[auto-wire] pausing WATCH during wiring (resumes after)…\n",
                     "dim")
            try:
                terminate_watch_process(self.watch_proc)
            except Exception:
                pass
            self.watch_proc = None
            self.root.after(0, lambda: self.watch_btn.configure(text="◭ WATCH"))
        try:
            self._autowire_build(paths, ws_file, multi, label)
        finally:
            if resume_watch and os.path.isdir(resume_watch):
                # If the user clicked WATCH while wiring ran (the button looked
                # idle), a watcher is already tracked — resuming anyway would
                # spawn a second `graphify watch` on the same repo and orphan
                # the user's one (invisible to STOP WATCH and app shutdown).
                already_running = (self.watch_proc is not None
                                   and self.watch_proc.poll() is None)
                if already_running:
                    self.log("[auto-wire] WATCH already running (started during "
                             "wiring) — not starting a second watcher.\n", "dim")
                else:
                    self._start_watch(resume_watch, quiet=True)
                    self.log(f"[auto-wire] ✓ WATCH resumed — watching "
                             f"{os.path.basename(resume_watch)}; graph auto-rebuilds on "
                             "save (edit a file to see 'Rebuilt: N nodes').\n", "ok")

    def _autowire_build(self, paths, ws_file, multi, label):
        total = len(paths)
        if multi:
            self.log(f"Building {total} project graphs one by one. Large repos take a\n"
                     "minute or two each (AST extraction — no tokens, no API cost).\n"
                     "Watch the % below; the window stays responsive throughout.\n",
                     "dim")
        built = []
        for i, p in enumerate(paths, 1):
            name = os.path.basename(p)
            self.log(f"\n--- [{i}/{total}] {name} ---\n", "mag")
            self.set_status(f"Building graph {i}/{total}: {name}")
            self.log(f"[{name}] extracting graph (AST, no tokens)…\n", "dim")
            t0 = time.time()
            code, out = run_cmd(graphify_cmd() + ["update", p], self.log)
            dt = time.time() - t0
            m = re.search(r"Rebuilt:\s*([\d,]+)\s*nodes", out)
            nodes = f", {m.group(1)} nodes" if m else ""
            if code == 0:
                built.append(p)
                self.log(f"[{name}] ✓ graph built in {dt:.0f}s{nodes}\n", "ok")
            else:
                self.log(f"[{name}] ✗ graph build failed (see output above)\n", "err")
            self.set_status(f"Wiring tools {i}/{total}: {name}")
            self.write_routing(p)          # key lever: makes the agent use the graph
            self.install_integrations(p)   # selected tools + git hooks
            if self.mcp_var.get():
                self.install_mcp(p)
            if self.gitignore_var.get():
                self.ensure_gitignore(p)
            self.log(f"[{name}] ✓ wired  ({i}/{total} projects done)\n", "ok")
        # cross-project graph so interlinked projects can be queried together
        if multi and len(built) > 1 and ws_file:
            graphs = [os.path.join(p, "graphify-out", "graph.json") for p in built
                      if os.path.exists(os.path.join(p, "graphify-out", "graph.json"))]
            if len(graphs) > 1:
                out = os.path.join(os.path.dirname(ws_file), "grafel-workspace",
                                   "graph.json")
                os.makedirs(os.path.dirname(out), exist_ok=True)
                self.set_status("Merging cross-project graph")
                self.log(f"\n=== Merging {len(graphs)} project graphs -> "
                         "cross-project graph ===\n", "mag")
                run_cmd(graphify_cmd() + ["merge-graphs", *graphs, "--out", out],
                        self.log)
                self.log(f"[workspace] cross-project graph: {out}\n", "ok")
                self.log("   Point Grafel's TARGET here and use ASK for questions that "
                         "span projects.\n", "dim")
        if multi:
            ok = sum(1 for p in paths if all(self._graph_wired_status(p)))
            self.log("\n╔══════════════════════════════════════════════╗\n", "ok")
            self.log(f"  ✓ WORKSPACE WIRED — {ok}/{len(paths)} projects now query "
                     "the graph\n", "ok")
            self.log("  Start a FRESH Claude prompt/session — the Live Meter will\n",
                     "ok")
            self.log("  show the cache-read (and your bill) drop, proven live.\n", "ok")
            self.log("╚══════════════════════════════════════════════╝\n", "ok")
            self.set_status(f"Workspace wired ({ok}/{len(paths)}) - savings active")
            return
        has_graph, has_routing = self._graph_wired_status(paths[0])
        if has_graph and has_routing:
            self.log(f"\n[auto-wire] ✓ {label} is now WIRED.\n", "ok")
            self.log("   Tell Claude to 'use the graph' or start a fresh prompt — the\n",
                     "ok")
            self.log("   cache-read (and your bill) should drop on the next turns.\n",
                     "ok")
            self.set_status("Graph wired - savings active")
        else:
            self.log("[auto-wire] finished with warnings; check the log above.\n", "err")
            self.set_status("Auto-wire done (check log)")

    def wire_workspace(self):
        """Let the user pick a .code-workspace file and wire every interlinked
        project in it (build graphs + routing + one cross-project graph)."""
        from tkinter import filedialog
        ws = filedialog.askopenfilename(
            parent=self.root, title="Select a VS Code .code-workspace file",
            filetypes=[("VS Code workspace", "*.code-workspace"), ("All files", "*.*")])
        if not ws:
            return
        folders = parse_workspace_folders(ws)
        if not folders:
            messagebox.showinfo("Grafel", "No folders found in that workspace file.",
                                parent=self.root)
            return
        names = ", ".join(os.path.basename(f) for f in folders)
        if messagebox.askyesno(
            "Grafel — wire workspace?",
            f"Wire all {len(folders)} projects in this workspace?\n\n{names}\n\n"
            "Grafel will build each project's graph, install routing, and create one\n"
            "merged cross-project graph so interlinked projects can be queried "
            "together.",
                parent=self.root):
            threading.Thread(target=self._autowire_worker,
                             args=(folders, ws), daemon=True).start()


    def on_close(self, force=False):

        # X and tray Quit both fully exit (no minimize-to-tray trap)
        self.meter_on = False
        # final locked flush: baseline updates are only persisted every 3rd
        # sample and stats may be pending — write them before the hard exit
        # below can kill the process. Never let a save failure block quitting.
        try:
            self._save_cfg_locked()
        except Exception:
            pass
        if self.watch_proc and self.watch_proc.poll() is None:
            terminate_watch_process(self.watch_proc)
        if self._tray is not None:
            try:
                self._tray.stop()
            except Exception:
                pass
        try:
            self.root.destroy()
        except tk.TclError:
            pass
        # hard-guarantee the process exits so the single-instance lock frees
        # and no tray/watcher thread can leave a zombie behind
        os._exit(0)

    # ---------- savings report ----------

    def show_savings(self):
        """Measure real token savings: full codebase context vs Grafel's graph
        index. Runs off the UI thread (walks files)."""
        if not self.repo_path:
            return
        threading.Thread(target=self._compute_savings,
                         args=(self.repo_path,), daemon=True).start()

    def _compute_savings(self, path):
        self.set_status("Measuring token savings")
        repo_stats = repo_token_stats(path, SAVINGS_CODE_EXT, SAVINGS_SKIP_DIRS)
        repo_tokens = repo_stats["tokens"]
        files = repo_stats["files"]
        exact = repo_stats["exact"]
        graph_tokens = graph_token_stats(path)["tokens"]

        if repo_tokens == 0:
            self.log("\n[savings] no code files found to measure.\n", "err")
            self.set_status("System idle")
            return

        prices = self.cfg.get("prices") or SAVINGS_PRICES
        lines = savings_report_lines(
            repo_tokens, files, exact, graph_tokens, SAVINGS_QUERY_TOKENS, prices
        )
        self.root.after(0, lambda: self._select_tab("insights"))
        for ln in lines:
            tag = "mag" if ln.startswith("===") else None
            self.log(ln, tag, box="insights")
        reduction = (1 - graph_tokens / repo_tokens) * 100 if graph_tokens else 0
        self._last_metrics = {
            "type": "savings",
            "repo": repo_tokens,
            "graph": graph_tokens,
            "reduction": reduction,
        }
        self._record_estimated(repo_tokens - graph_tokens)
        self.root.after(0, lambda: self.card_btn.configure(state="normal"))
        self.set_status("Savings measured")

    # ---------- live A/B test ----------

    def run_ab_test(self):
        """Ask a real codebase question and compare, in actual tokens, what an agent
        would read WITHOUT the graph (grep + read matching files) vs WITH the graph
        (a real `graphify query`)."""
        if not self.repo_path:
            return
        question = simpledialog.askstring(
            "Grafel A/B Test",
            "Ask a question about this codebase\n(e.g. 'how does authentication work?'):",
            parent=self.root,
        )
        if not question or not question.strip():
            return
        threading.Thread(target=self._compute_ab,
                         args=(question.strip(),), daemon=True).start()

    def _compute_ab(self, question):
        self.set_status("Running A/B test")
        code, out, with_tokens = self._run_managed_graph_query(
            self.repo_path, question, source="ab_test", budget=SAVINGS_QUERY_TOKENS
        )
        exact = bool(out.strip())
        match_stats = question_match_stats(
            self.repo_path, question, SAVINGS_CODE_EXT, SAVINGS_SKIP_DIRS
        )
        without_tokens = match_stats["tokens"]
        matched = match_stats["matched"]
        exact = exact and match_stats["exact"]

        if with_tokens == 0:
            self.log("\n[a/b] graph query returned nothing - is the graph built?\n", "err")
            self.set_status("System idle")
            return

        prices = self.cfg.get("prices") or SAVINGS_PRICES
        lines = ab_report_lines(question, exact, without_tokens, matched, with_tokens, prices)
        cut = reduction_percent(without_tokens, with_tokens)
        self.root.after(0, lambda: self._select_tab("insights"))
        for ln in lines:
            tag = "mag" if ln.startswith("===") else None
            self.log(ln, tag, box="insights")
        self._last_metrics = {
            "type": "ab",
            "without": without_tokens,
            "with": with_tokens,
            "reduction": cut,
            "question": question,
        }
        self._record_estimated(without_tokens - with_tokens)
        self.root.after(0, lambda: self.card_btn.configure(state="normal"))
        self.set_status("A/B test complete")

    # ---------- ask / batch / dashboard / card ----------

    def run_ask(self):
        """Ask a question; show the graph answer AND the real per-prompt cost
        (tokens/credits with vs without Grafel) in the Q&A tab."""
        if not self.repo_path:
            return
        question = simpledialog.askstring(
            "Grafel - Ask the graph",
            "Ask a question about this codebase:",
            parent=self.root,
        )
        if not question or not question.strip():
            return
        threading.Thread(target=self._ask_worker,
                         args=(question.strip(),), daemon=True).start()

    def _ask_worker(self, q):
        self.set_status("Querying graph")
        self.root.after(0, lambda: self._select_tab("qa"))

        def qlog(t, tag=None):
            self.log(t, tag, box="qa")

        qlog(f'\n=== ASK: "{q}" ===\n', "mag")
        code, out, with_tokens = self._run_managed_graph_query(
            self.repo_path, q, source="ask_graph", budget=SAVINGS_QUERY_TOKENS
        )
        match_stats = question_match_stats(
            self.repo_path, q, SAVINGS_CODE_EXT, SAVINGS_SKIP_DIRS
        )
        without_tokens = match_stats["tokens"]
        matched = match_stats["matched"]
        prices = self.cfg.get("prices") or SAVINGS_PRICES
        cut = reduction_percent(without_tokens, with_tokens)

        qlog("\n-- THIS PROMPT :: COST COMPARISON --\n", "mag")
        for line in prompt_comparison_lines(without_tokens, matched, with_tokens, prices):
            tag = "ok" if line.startswith("WITH") else None
            qlog(line, tag)
        qlog("\n-- GRAPH ANSWER --\n", "mag")
        if out.strip():
            qlog(out if out.endswith("\n") else out + "\n")
        else:
            qlog("(no answer - is the graph built for this repo?)\n", "err")
        if with_tokens:
            self._last_metrics = {
                "type": "ab",
                "without": without_tokens,
                "with": with_tokens,
                "reduction": cut,
                "question": q,
            }
            self._record_estimated(without_tokens - with_tokens)
            self.root.after(0, lambda: self.card_btn.configure(state="normal"))
        self.set_status("Answer ready" if code == 0 else "Query failed")

    def run_batch(self):
        """Graph every git repo directly under a chosen parent folder."""
        if self._browsing:
            return
        self._browsing = True
        self.set_status("Awaiting batch folder")

        def w():
            parent = self._pick_folder()
            self._browsing = False
            if not parent:
                self.set_status("System idle")
                return
            repos = []
            try:
                for name in sorted(os.listdir(parent)):
                    p = os.path.join(parent, name)
                    if os.path.isdir(os.path.join(p, ".git")):
                        repos.append(p)
            except OSError:
                pass
            if os.path.isdir(os.path.join(parent, ".git")):
                repos.insert(0, parent)
            if not repos:
                self.log(f"\n[batch] no git repos found under {parent}\n", "err")
                self.set_status("System idle")
                return
            self.log(f"\n=== BATCH: {len(repos)} repos under {parent} ===\n", "mag")
            for i, p in enumerate(repos, 1):
                self.set_status(f"Batch {i}/{len(repos)}")
                self.log(f"\n--- [{i}/{len(repos)}] {p} ---\n", "mag")
                code, _ = run_cmd(graphify_cmd() + ["update", p], self.log)
                if code == 0:
                    self.install_integrations(p)
                    if self.mcp_var.get():
                        self.install_mcp(p)
                    if self.gitignore_var.get():
                        self.ensure_gitignore(p)
            self.log("\n=== BATCH COMPLETE ===\n", "ok")
            self.set_status("Batch complete")
        threading.Thread(target=w, daemon=True).start()

    def _record_saved(self, tokens_saved):
        """Realized, meter-proven savings ONLY (live session tailing). The
        hypothetical deltas from SAVINGS/A/B/ASK/BENCHMARK go through
        _record_estimated instead — never mix the two counters."""
        with self._cfg_lock:
            st = self.cfg.setdefault("stats", {})
            st["saved_tokens"] = int(st.get("saved_tokens", 0)) + max(0, int(tokens_saved))
            st["events"] = int(st.get("events", 0)) + 1
            save_config(CONFIG_FILE, self.cfg)

    def _record_estimated(self, tokens_estimated):
        """Hypothetical/what-if deltas (savings report, A/B test, ask, benchmark):
        what WOULD be saved, not what a live session actually saved. Kept in
        stats['estimated_tokens'], separate from meter-proven stats['saved_tokens']."""
        with self._cfg_lock:
            st = self.cfg.setdefault("stats", {})
            st["estimated_tokens"] = int(st.get("estimated_tokens", 0)) + max(0, int(tokens_estimated))
            st["estimated_events"] = int(st.get("estimated_events", 0)) + 1
            save_config(CONFIG_FILE, self.cfg)

    def _record_brevity_saved(self, tokens_saved):
        with self._cfg_lock:
            st = self.cfg.setdefault("stats", {})
            st["brevity_output_saved_tokens_estimate"] = max(
                int(st.get("brevity_output_saved_tokens_estimate", 0)),
                max(0, int(tokens_saved)),
            )
            st["brevity_events"] = int(st.get("brevity_events", 0)) + 1
            save_config(CONFIG_FILE, self.cfg)

    def _record_memory_compression_saved(self, tokens_saved):
        with self._cfg_lock:
            st = self.cfg.setdefault("stats", {})
            st["memory_compression_saved_tokens"] = int(st.get("memory_compression_saved_tokens", 0)) + max(0, int(tokens_saved))
            st["memory_compression_events"] = int(st.get("memory_compression_events", 0)) + 1
            save_config(CONFIG_FILE, self.cfg)

    def _run_managed_graph_query(self, repo_path, question, source, budget=SAVINGS_QUERY_TOKENS):
        code, out = run_cmd(
            graphify_cmd() + ["query", question, "--budget", str(budget)],
            lambda _t, _tag=None: None,
            cwd=repo_path,
        )
        tokens, _exact = count_tokens(out) if out.strip() else (0, False)
        if code == 0 and out.strip():
            try:
                append_graph_use_event(
                    repo_path,
                    source=source,
                    command="query",
                    argv=[question, "--budget", str(budget)],
                    cwd=repo_path,
                    tokens=tokens,
                    success=True,
                )
            except OSError:
                pass
        return code, out, tokens

    def _savings_health_snapshot(self):
        if not self.repo_path:
            return None
        install = repo_install_health(self.repo_path, ROUTING_START, BREVITY_START)
        live = repo_live_session_health(
            self.repo_path,
            find_workspace_for,
            parse_workspace_folders,
            claude_log_dir,
            list_ai_sessions,
            lambda path: codex_session_cwd_fast(path) or session_cwd_fast(path),
        )
        graph_using = 0
        bypassed = 0
        for session in live["linked_sessions"]:
            state, _usage, _bypass = self._session_savings_state(session)
            if state == "graph-using":
                graph_using += 1
            elif state == "linked-bypassed-graph":
                bypassed += 1
        proof = graph_use_summary(self.repo_path)
        freshness = graph_artifact_state(self.repo_path, SAVINGS_CODE_EXT, SAVINGS_SKIP_DIRS)
        stats = self.cfg.get("stats", {})
        proven_saved = int(stats.get("saved_tokens", 0))
        proven_events = int(stats.get("events", 0))
        estimated_saved = int(stats.get("estimated_tokens", 0))
        estimated_events = int(stats.get("estimated_events", 0))
        return {
            "repo_path": self.repo_path,
            "graph_built": install["graph_built"],
            "routing_installed": install["routing_installed"],
            "brevity_installed": install["brevity_installed"],
            "linked_session_count": live["linked_count"],
            "linked_session_counts": live["linked_counts"],
            "graph_using_session_count": graph_using,
            "bypassed_session_count": bypassed,
            "repo_graph_proof_events": proof["successful_events"],
            "repo_graph_proof_recent": proof["recent_successful_events"],
            "repo_graph_proof_latest": proof["latest_event"],
            "graph_stale": bool(freshness["graph_exists"] and (freshness["graph_stale"] or freshness["report_stale"])),
            "machine_session_count": live["machine_count"],
            "other_session_count": live["other_count"],
            "has_any_sessions": live["has_any"],
            "proven_savings_seen": proven_saved > 0 and proven_events > 0,
            "proven_saved_tokens": proven_saved,
            "proven_events": proven_events,
            "estimated_saved_tokens": estimated_saved,
            "estimated_events": estimated_events,
            "strict_mode": self._strict_mode(),
        }

    def _log_savings_health(self, box="insights"):
        health = self._savings_health_snapshot()
        self.log("\n=== SAVINGS HEALTH CHECK ===\n", "mag", box=box)
        if not health:
            self.log("No target repo selected yet.\n", "dim", box=box)
            self.log("============================\n\n", "mag", box=box)
            return
        self.log(f"Repo: {health['repo_path']}\n", "dim", box=box)
        strict_on = "ON" if health["strict_mode"] in ("required", "required_alerts") else "ADVISORY"
        graph_state = "Stale" if health["graph_stale"] else "Fresh"
        self.log(
            "Status: "
            f"Strict MCP: {strict_on} | Graph: {graph_state} | "
            f"Linked: {health['linked_session_count']} | "
            f"Graph-used: {health['graph_using_session_count']} | "
            f"Bypassed: {health['bypassed_session_count']}\n",
            "ok" if not health["graph_stale"] and not health["bypassed_session_count"] else "err",
            box=box,
        )
        self.log(
            f"Graph built: {'YES' if health['graph_built'] else 'NO'}\n",
            "ok" if health["graph_built"] else "err",
            box=box,
        )
        self.log(
            f"Routing installed: {'YES' if health['routing_installed'] else 'NO'}\n",
            "ok" if health["routing_installed"] else "err",
            box=box,
        )
        self.log(
            f"Brevity installed: {'YES' if health['brevity_installed'] else 'NO'}\n",
            "ok" if health["brevity_installed"] else "err",
            box=box,
        )
        self.log(
            f"Strict mode: {STRICT_MODE_LABELS.get(health['strict_mode'], 'Advisory')}\n",
            "dim",
            box=box,
        )
        if health["graph_stale"]:
            self.log("Graph freshness: STALE (run INITIATE SCAN or WATCH)\n", "err", box=box)
        else:
            self.log("Graph freshness: READY\n", "ok", box=box)
        if health["has_any_sessions"]:
            linked_counts = health["linked_session_counts"]
            kinds = []
            for kind in ("claude", "codex", "copilot", "other"):
                count = int(linked_counts.get(kind, 0))
                if count:
                    kinds.append(f"{count} {kind}")
            kind_text = ", ".join(kinds) if kinds else "0 linked"
            linked = health["linked_session_count"]
            total = health["machine_session_count"]
            other = health["other_session_count"]
            self.log(
                f"Current live sessions linked to this repo: "
                f"{'YES' if linked else 'NO'} ({linked}/{total} on this machine; {kind_text})\n",
                "ok" if linked else "err",
                box=box,
            )
            self.log(
                f"Linked sessions with graph-use evidence: {health['graph_using_session_count']}\n",
                "ok" if health["graph_using_session_count"] else "dim",
                box=box,
            )
            self.log(
                f"Linked sessions that bypassed graph: {health['bypassed_session_count']}\n",
                "err" if health["bypassed_session_count"] else "ok",
                box=box,
            )
            self.log(
                f"Managed graph proof events for this repo: {health['repo_graph_proof_events']} "
                f"({health['repo_graph_proof_recent']} recent)\n",
                "ok" if health["repo_graph_proof_events"] else "dim",
                box=box,
            )
            latest_proof = health.get("repo_graph_proof_latest") or {}
            if latest_proof:
                self.log(
                    f"Latest managed proof source: {latest_proof.get('source', 'unknown')}\n",
                    "dim",
                    box=box,
                )
            if other:
                self.log(f"Other machine sessions outside this repo: {other}\n", "dim", box=box)
        else:
            self.log("Current live sessions linked to this repo: NO (no local AI sessions found yet)\n", "err", box=box)
        self.log(
            f"Proven savings seen (realized, live meter): {'YES' if health['proven_savings_seen'] else 'NO'}",
            "ok" if health["proven_savings_seen"] else "err",
            box=box,
        )
        if health["proven_savings_seen"]:
            self.log(
                f" ({health['proven_saved_tokens']:,} tokens across {health['proven_events']} live prompts)\n",
                box=box,
            )
        else:
            self.log(" (start the LIVE METER on a wired repo to prove savings)\n", "dim", box=box)
        if health["estimated_events"]:
            self.log(
                f"Estimated savings (hypothetical, not realized): ~{health['estimated_saved_tokens']:,} "
                f"tokens across {health['estimated_events']} SAVINGS/A/B/ASK/BENCHMARK runs\n",
                "dim",
                box=box,
            )
        self.log("============================\n\n", "mag", box=box)

    def show_dashboard(self):
        """Cumulative, persisted counters — kept honestly separate: realized
        savings proven by the live meter vs hypothetical estimates from the
        SAVINGS/A/B/ASK/BENCHMARK panels."""
        self.root.after(0, lambda: self._select_tab("insights"))
        st = self.cfg.get("stats", {})
        saved = int(st.get("saved_tokens", 0))
        events = int(st.get("events", 0))
        est = int(st.get("estimated_tokens", 0))
        est_events = int(st.get("estimated_events", 0))
        prices = self.cfg.get("prices") or SAVINGS_PRICES
        self._log_savings_health(box="insights")
        self.log("\n=== GRAFEL DASHBOARD ===\n", "mag", box="insights")
        if events == 0 and est_events == 0:
            self.log("No measurements yet - run SAVINGS, A/B TEST, or the LIVE METER first.\n",
                     "dim", box="insights")
        if events:
            self.log("-- REALIZED (proven by the live meter) --\n", "ok", box="insights")
            self.log(f"Live prompts with proven savings: {events}\n", box="insights")
            self.log(f"Tokens actually kept out of AI context: ~{saved:,}\n",
                     "ok", box="insights")
            self.log("Realized cost avoided (input pricing):\n", box="insights")
            for m, p in prices.items():
                self.log(f"   {m}: ~${saved / 1_000_000 * p:.2f}\n", box="insights")
        elif est_events:
            self.log("-- REALIZED (proven by the live meter) --\n", "ok", box="insights")
            self.log("None yet - start the LIVE METER on a wired repo.\n",
                     "dim", box="insights")
        if est_events:
            self.log("-- ESTIMATED (hypothetical what-if, NOT realized) --\n",
                     "mag", box="insights")
            self.log(f"SAVINGS/A/B/ASK/BENCHMARK runs: {est_events}\n", box="insights")
            self.log(f"Tokens that WOULD be kept out per those measurements: ~{est:,}\n",
                     box="insights")
            self.log("Estimated cost that WOULD be avoided (input pricing):\n",
                     box="insights")
            for m, p in prices.items():
                self.log(f"   {m}: ~${est / 1_000_000 * p:.2f}\n", box="insights")
        self.log("========================\n\n", "mag", box="insights")
        for line in brevity_dashboard_lines(st, prices, self._brevity_level()):
            self.log(line, "mag" if line.startswith("===") else None, box="insights")

    def scan_usage(self):
        """Scan REAL local AI-tool usage logs (token counts only) and report actual
        consumption + spend. Privacy: reads token numbers on this machine only,
        never chat content, never uploads anything."""
        threading.Thread(target=self._scan_usage_worker, daemon=True).start()

    def _scan_usage_worker(self):
        self.set_status("Scanning real AI usage")
        self.root.after(0, lambda: self._select_tab("insights"))

        def L(t, tag=None):
            self.log(t, tag, box="insights")

        L("\n=== REAL AI USAGE SCAN (local logs) ===\n", "mag")
        L("Reads token counts only, on this machine. No chat content read or sent.\n", "dim")

        claude = scan_claude_usage()
        if not claude or not sum(claude["totals"].values()):
            L("No Claude Code logs found (~/.claude/projects) or no token usage found.\n", "err")
            self.set_status("System idle")
            return

        totals = claude["totals"]
        total = sum(totals.values())
        cost = (
            totals["in"] / 1e6 * 3.0
            + totals["cw"] / 1e6 * 3.75
            + totals["cr"] / 1e6 * 0.30
            + totals["out"] / 1e6 * 15.0
        )
        L(f"Sessions scanned: {claude['files']} files\n")
        L("Real tokens used (Claude Code):\n", "ok")
        L(f"   input:        ~{totals['in']:,}\n")
        L(f"   cache write:  ~{totals['cw']:,}\n")
        L(f"   cache read:   ~{totals['cr']:,}\n")
        L(f"   output:       ~{totals['out']:,}\n")
        L(f"   TOTAL:        ~{total:,} tokens\n", "ok")
        L(f"Estimated real spend (Sonnet rates): ~${cost:,.2f}\n", "mag")
        top = sorted(claude["per_project"].items(), key=lambda kv: -kv[1])[:5]
        L("Top projects by tokens:\n")
        for name, tok in top:
            nm = name.replace("c--Users-", "").replace("-", "/")[:48]
            L(f"   {nm}: ~{tok:,}\n")
        recent = sorted((k for k in claude["months"] if k != "unknown"), reverse=True)[:6]
        if recent:
            L("Monthly trend (Claude Code tokens):\n")
            for mk in reversed(recent):
                L(f"   {mk}: ~{claude['months'][mk]:,}\n")

        codex = scan_codex_usage()
        if codex and codex["total"]:
            ccost = (
                codex["input"] / 1e6 * 2.50
                + codex["cached"] / 1e6 * 0.25
                + codex["output"] / 1e6 * 10.0
            )
            L(f"\nReal tokens used (Codex, {codex['files']} sessions):\n", "ok")
            L(
                f"   input ~{codex['input']:,}  cached ~{codex['cached']:,}  "
                f"output ~{codex['output']:,}  reasoning ~{codex['reasoning']:,}\n"
            )
            L(f"   TOTAL ~{codex['total']:,} tokens\n", "ok")
            L(f"   Estimated spend (GPT-class rates): ~${ccost:,.2f}\n", "mag")

        copilot = scan_copilot_cli_usage()
        if copilot and not copilot.get("error"):
            L(f"\nReal Copilot CLI usage ({copilot['sessions']} sessions):\n", "ok")
            L(f"   requests (turns): {copilot['turns']}\n", "ok")
            L("   Copilot bills per premium request (~$0.04 each beyond your plan's allowance).\n", "dim")
            L(f"   Estimated overage if all beyond plan: ~${copilot['turns'] * 0.04:,.2f}\n", "mag")
            recent = sorted(copilot["months"], reverse=True)[:6]
            if recent:
                L("   Monthly requests:\n")
                for mk in reversed(recent):
                    L(f"      {mk}: {copilot['months'][mk]}\n")
            L("   (VS Code Copilot Chat inline requests are not logged locally - see your GitHub Copilot dashboard for those.)\n", "dim")
        elif copilot and copilot.get("error"):
            L(f"   (Copilot store read failed: {copilot['error']})\n", "dim")
        else:
            L("\nCopilot: no local CLI store found. VS Code Copilot Chat requests are not logged locally - track them in your GitHub Copilot dashboard.\n", "dim")

        brevity = output_savings_snapshot(claude, codex, copilot, self._brevity_level())
        if brevity["estimated_output_tokens"]:
            L("\nGrafel Brevity Mode potential:\n", "ok")
            L(
                f"   level {brevity['level']}: save ~{brevity['estimated_saved_tokens']:,} output tokens "
                f"(~{brevity['estimated_saved_percent']}% of ~{brevity['estimated_output_tokens']:,})\n",
                "ok",
            )
            self._record_brevity_saved(brevity["estimated_saved_tokens"])

        L("\nGrafel targets the codebase-reading share of this. Wire the graph into\n")
        L("your tools, then use Brevity Mode to cut answer verbosity too.\n", "dim")
        L("=======================================\n\n", "mag")
        self.set_status("Usage scan complete")

    # ---------- chat → markdown export ----------

    def export_chats(self):
        """Write agent-readable Markdown digests of every AI chat related to the
        current repo/workspace into <repo>/grafel-chats/ — so future agent
        sessions read one small MD instead of replaying whole chats (token saver)."""
        if not self.repo_path:
            messagebox.showinfo("Grafel", "Set a target repo first.",
                                parent=self.root)
            return
        threading.Thread(target=self._export_chats_worker, daemon=True).start()

    def _export_chats_worker(self):
        import glob
        repo = self.repo_path
        self.set_status("Exporting chat digests")
        self.root.after(0, lambda: self._select_tab("console"))
        self.log("\n=== CHAT → MARKDOWN EXPORT ===\n", "mag")
        self.log("Digesting Claude Code + GitHub Copilot chats for this repo into\n"
                 "grafel-chats/ — note: these files CONTAIN chat text (local only).\n",
                 "dim")
        _ws, folders = find_workspace_for(repo, parse_workspace_folders)
        folders = folders or [repo]
        outdir = os.path.join(repo, "grafel-chats")
        os.makedirs(outdir, exist_ok=True)
        # transcripts can contain pasted secrets — keep them out of git even if
        # the user never ran the pipeline's gitignore step
        ensure_gitignore_entry(repo, "grafel-chats", self.log)
        made = []

        def write(name, title, meta, exchanges):
            fp = os.path.join(outdir, name)
            try:
                with open(fp, "w", encoding="utf-8") as f:
                    f.write(f"# {title}\n\n{meta}\n\n")
                    for i, (u, a, usage) in enumerate(exchanges, 1):
                        f.write(f"## Prompt {i}\n\n")
                        if u:
                            f.write(f"**User:** {u}\n\n")
                        if a:
                            f.write(f"**Agent:** {a}\n\n")
                        if usage:
                            f.write(f"*{usage}*\n\n")
            except OSError as e:
                self.log(f"   ✗ {name}: {e}\n", "err")
                return
            made.append((name, title, len(exchanges)))
            self.log(f"   ✓ {name}  ({len(exchanges)} prompts)\n", "ok")

        # --- Claude Code sessions ---
        for fld in folders:
            d = claude_log_dir(fld)
            if not d:
                continue
            for fp in glob.glob(os.path.join(d, "*.jsonl")):
                # claude_log_dir's encoded name collides across similarly-named
                # repos (repo-x vs repo_x) — cross-check the session's real cwd
                # so another repo's chats never land in this repo's digests
                real_cwd = session_cwd_fast(fp)
                if real_cwd and not path_is_related(fld, real_cwd):
                    continue
                ex = claude_exchanges(fp, trim=trim_text)
                if ex:
                    day = time.strftime("%Y-%m-%d",
                                        time.localtime(os.path.getmtime(fp)))
                    sid = os.path.basename(fp).split(".")[0][:8]
                    write(f"claude-{day}-{sid}.md",
                          f"Claude Code chat — {os.path.basename(fld)} ({day})",
                          f"Source: `{fp}`", ex)

        # --- VS Code Copilot Chat sessions ---
        for s in list_vscode_copilot_sessions(folders, parse_workspace_folders):
            ex = copilot_exchanges(s["file"], trim=trim_text)
            if ex:
                day = time.strftime("%Y-%m-%d", time.localtime(s["mtime"]))
                sid = os.path.basename(s["file"]).split(".")[0][:8]
                write(f"copilot-vscode-{day}-{sid}.md",
                      f"Copilot Chat (VS Code) — {s['name']} ({day})",
                      f"Source: `{s['file']}`", ex)

        # --- Copilot CLI sessions (session-store.db) ---
        db = os.path.join(os.path.expanduser("~"), ".copilot", "session-store.db")
        want = {os.path.normcase(os.path.normpath(f)) for f in folders}
        if os.path.exists(db):
            try:
                import sqlite3
                con = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
                cur = con.cursor()
                for sid, cwd, summ, upd in cur.execute(
                        "SELECT id, cwd, summary, updated_at FROM sessions"):
                    if (not cwd or os.path.normcase(os.path.normpath(cwd))
                            not in want):
                        continue
                    ex = [(trim_text(u), trim_text(a), "") for u, a in cur.execute(
                        "SELECT user_message, assistant_response FROM turns "
                        "WHERE session_id=? ORDER BY turn_index", (sid,))][:200]
                    if ex:
                        day = (upd or "")[:10] or "unknown"
                        meta = f"Source: Copilot CLI session `{sid}`"
                        if summ:
                            meta += f"\n\nSession summary: {trim_text(summ, 300)}"
                        write(f"copilot-cli-{day}-{sid[:8]}.md",
                              f"Copilot CLI chat — {os.path.basename(cwd)} ({day})",
                              meta, ex)
                con.close()
            except Exception as e:
                self.log(f"   (Copilot CLI store read failed: {e})\n", "dim")

        if not made:
            self.log("No AI chats found for this repo/workspace yet.\n", "err")
            self.set_status("No chats to export")
            return
        try:
            with open(os.path.join(outdir, "index.md"), "w",
                      encoding="utf-8") as f:
                f.write("# AI chat digests for this repo\n\n"
                        "Agents: read the relevant digest below instead of "
                        "replaying full chat logs.\n\n")
                for name, title, n in sorted(made):
                    f.write(f"- [{title}]({name}) — {n} prompts\n")
        except OSError:
            pass
        self.log(f"\n✓ {len(made)} chat digests written to "
                 f"{outdir}\\\n", "ok")
        self.log("  Point your agent at grafel-chats/index.md to resume context "
                 "cheaply.\n", "dim")
        self.set_status(f"Chat export: {len(made)} digests")

    # ---------- optimizer / savings advisor ----------



    def run_optimizer(self):
        """Analyze real usage and print a personalized, data-backed plan to cut
        AI credits/tokens, with an estimated monthly saving per recommendation."""
        threading.Thread(target=self._optimize_worker, daemon=True).start()

    def _optimize_worker(self):
        self.set_status("Building savings plan")
        self.root.after(0, lambda: self._select_tab("insights"))

        def L(t, tag=None):
            self.log(t, tag, box="insights")

        L("\n=== GRAFEL OPTIMIZER :: YOUR PERSONALIZED SAVINGS PLAN ===\n", "mag")
        L("Every number below is computed from your own local logs.\n", "dim")

        claude = scan_claude_usage()
        codex = scan_codex_usage()
        copilot = scan_copilot_cli_usage()
        repo_has_graph = None
        if self.repo_path:
            repo_has_graph = os.path.exists(os.path.join(self.repo_path, "graphify-out", "graph.json"))
        plan = build_optimizer_plan(
            claude, codex, copilot, repo_has_graph, CLAUDE_RATES, SAVINGS_QUERY_TOKENS
        )
        recs = plan["recommendations"]
        summary = plan["claude_summary"]

        if summary:
            totals = summary["totals"]
            L(
                f"\nClaude Code — deduped across {claude['files']} sessions, "
                f"{summary['responses']:,} real model responses:\n",
                "ok",
            )
            L(
                f"   tokens: in {totals['in']:,} · cache-read {totals['cr']:,} · "
                f"cache-write {totals['cw']:,} · out {totals['out']:,}\n"
            )
            L(
                f"   estimated spend: ~${summary['total_cost']:,.2f} lifetime"
                + (
                    f" · ~${summary['month_cost']:,.2f} in {summary['recent_key']}\n"
                    if summary["recent_key"] else "\n"
                ),
                "mag",
            )
            if summary["by_model"]:
                L(
                    "   model split: " + " · ".join(
                        f"{cls} ${cost:,.2f}"
                        for cls, cost in sorted(summary["by_model"].items(), key=lambda kv: -kv[1])
                    ) + "\n",
                    "dim",
                )
        elif claude is None:
            L("\nNo Claude Code logs found. Use Claude Code, then re-run OPTIMIZE.\n", "dim")

        if not recs:
            L("\nYou're already lean — no high-impact changes detected. Keep the graph\n"
              "wired and re-run OPTIMIZE as your usage grows.\n", "ok")
            L("=========================================================\n\n", "mag")
            self.set_status("Optimizer: already lean")
            return

        wire_tags = {"GRAPH", "SETUP"}
        directive_tags = {"MODEL", "OUTPUT", "CACHE", "CODEX", "COPILOT"}
        can_apply = bool(self.repo_path) and bool(recs)
        L("\n----- RECOMMENDATIONS (highest impact first) -----\n", "mag")
        for n, rec in enumerate(recs, 1):
            L(f"\n{n}. [{rec['tag']}] {rec['title']}\n", "ok")
            for ln in rec["detail"]:
                L(f"     - {ln}\n")
            if rec["save"] > 0:
                L(f"     ≈ est. saving: ${rec['save']:,.2f}/month\n", "mag")
            if rec["tag"] in wire_tags:
                L("     ▶ Grafel APPLIES this by building + wiring the graph.\n", "ok")
            elif rec["tag"] in directive_tags:
                L("     ▶ Grafel APPLIES this as an agent rule your AI tools follow "
                  "(installed when you wire).\n", "ok")
            else:
                L("     • manual — do this yourself.\n", "dim")
        if plan["total_save"] > 0:
            L(f"\nEstimated total if you apply these: ~${plan['total_save']:,.2f}/month "
              f"(~${plan['total_save'] * 12:,.2f}/yr)\n", "mag")
        L("These are estimates from your own logs; your mileage will vary.\n", "dim")
        L("=========================================================\n\n", "mag")
        if can_apply:
            L("▶ APPLY ALL: Grafel will wire the graph AND install the efficiency\n"
              "rules (diffs-not-rewrites, batch requests, cheaper models, warm cache)\n"
              "into your agent files, so your tools follow them automatically. Re-run\n"
              "OPTIMIZE afterward to see the impact.\n", "ok")
            self._autowire_asked = None
            self.root.after(0, lambda: self._offer_autowire(self.repo_path))
            self.set_status("Savings plan ready — applying fixes")
        else:
            self.set_status("Savings plan ready")

    def export_card(self):
        """Render a shareable PNG savings card from the last measurement."""
        m = self._last_metrics
        if not m:
            messagebox.showinfo("Grafel", "Run SAVINGS or A/B TEST first.",
                                parent=self.root)
            return
        try:
            from PIL import Image, ImageDraw, ImageFont  # type: ignore
        except Exception:
            messagebox.showinfo("Grafel", "Pillow not available for card export.",
                                parent=self.root)
            return

        def font(sz, bold=True):
            for name in (("arialbd.ttf", "consolab.ttf") if bold
                         else ("arial.ttf", "consola.ttf")):
                try:
                    return ImageFont.truetype(name, sz)
                except OSError:
                    continue
            return ImageFont.load_default()

        W, H = 1200, 630
        img = Image.new("RGB", (W, H), (5, 8, 16))
        d = ImageDraw.Draw(img)
        d.rectangle([0, 0, W - 1, H - 1], outline=(0, 120, 140), width=3)
        d.text((60, 50), "GRAFEL", font=font(72), fill=(0, 240, 255))
        d.text((66, 140), "THE MEMORY LAYER FOR AI CODING", font=font(22, False),
                fill=(90, 113, 134))
        reduction = int(round(m.get("reduction", 0)))
        d.text((60, 250), f"{reduction}% FEWER TOKENS", font=font(84),
               fill=(57, 255, 136))
        if m["type"] == "savings":
            sub = f"Codebase ~{m['repo']:,} tokens  →  Grafel graph ~{m['graph']:,} tokens"
        else:
            sub = (f"Q: {m.get('question', '')[:60]}   "
                   f"~{m['without']:,} → ~{m['with']:,} tokens")
        d.text((60, 380), sub, font=font(24, False), fill=(159, 216, 207))
        prices = self.cfg.get("prices") or SAVINGS_PRICES
        price = next(iter(prices.values()), 3.0)
        if m["type"] == "savings":
            saved_tok = m["repo"] - m["graph"]
        else:
            saved_tok = m["without"] - m["with"]
        d.text((60, 440), f"~${saved_tok / 1_000_000 * price:.2f} saved on this alone "
                          f"(at ${price:.2f}/M input)", font=font(24, False),
               fill=(255, 47, 214))
        d.text((60, 550), "Cut your AI token bill · grafel", font=font(20, False),
               fill=(49, 80, 107))
        try:
            logo = Image.open(resource_path("grafel.png")).convert("RGBA")
            logo = logo.resize((150, 150), Image.LANCZOS)
            img.paste(logo, (W - 210, 60), logo)
        except Exception:
            pass
        out = os.path.join(os.path.expanduser("~"), "Desktop", "grafel_savings_card.png")
        try:
            img.save(out)
            self.log(f"\n[card] saved shareable card -> {out}\n", "ok")
            webbrowser.open(f"file:///{out.replace(os.sep, '/')}")
        except OSError as e:
            self.log(f"[card] could not save: {e}\n", "err")

    # ---------- benchmark / merge / schedule ----------

    def _measure_prompt(self, q):
        _c, out = run_cmd(
            graphify_cmd() + ["query", q, "--budget", str(SAVINGS_QUERY_TOKENS)],
            lambda _t, _g=None: None, cwd=self.repo_path,
        )
        with_tokens, _ = count_tokens(out) if out.strip() else (0, False)
        match_stats = question_match_stats(
            self.repo_path, q, SAVINGS_CODE_EXT, SAVINGS_SKIP_DIRS
        )
        return with_tokens, match_stats["tokens"], match_stats["matched"]

    def run_benchmark(self):
        if not self.repo_path:
            messagebox.showinfo("Grafel", "Run a scan first.", parent=self.root)
            return
        threading.Thread(target=self._benchmark_worker, daemon=True).start()

    def _benchmark_worker(self):
        self.set_status("Benchmarking")
        self.root.after(0, lambda: self._select_tab("insights"))

        def L(t, tag=None):
            self.log(t, tag, box="insights")

        L("\n=== GRAFEL BENCHMARK (5 standard questions) ===\n", "mag")
        tot_w = tot_wo = 0
        for q in BENCHMARK_QS:
            w, wo, _m = self._measure_prompt(q)
            tot_w += w
            tot_wo += wo
            c = (1 - w / wo) * 100 if wo else 0
            L(f"  \"{q[:38]}\"  {wo:,} -> {w:,}  (~{c:.0f}% less)\n")
        cut = (1 - tot_w / tot_wo) * 100 if tot_wo else 0
        prices = self.cfg.get("prices") or SAVINGS_PRICES
        L(f"\nTOTAL: {tot_wo:,} -> {tot_w:,} tokens  (~{cut:.0f}% fewer)\n", "ok")
        for m, p in prices.items():
            L(f"   {m}: ~${tot_wo / 1e6 * p:.4f} -> ~${tot_w / 1e6 * p:.4f}\n")
        L("================================\n\n", "mag")
        if tot_w:
            # benchmark deltas are hypothetical too — same estimated counter
            self._record_estimated(tot_wo - tot_w)
            self._last_metrics = {"type": "ab", "without": tot_wo, "with": tot_w,
                                  "reduction": cut, "question": "benchmark (5 Qs)"}
            self.root.after(0, lambda: self.card_btn.configure(state="normal"))
        self.set_status("Benchmark complete")

    def merge_repos(self):
        """Merge the graphs of every repo under a chosen folder into one graph."""
        if self._browsing:
            return
        self._browsing = True
        self.set_status("Awaiting merge folder")

        def w():
            import glob
            parent = self._pick_folder()
            self._browsing = False
            if not parent:
                self.set_status("System idle")
                return
            graphs = glob.glob(os.path.join(parent, "**", "graphify-out", "graph.json"),
                               recursive=True)
            if len(graphs) < 2:
                self.log(f"\n[merge] need >=2 repo graphs under {parent} "
                         f"(found {len(graphs)}). Build them first with BATCH.\n", "err")
                self.set_status("System idle")
                return
            out = os.path.join(parent, "grafel-merged", "graph.json")
            os.makedirs(os.path.dirname(out), exist_ok=True)
            self.log(f"\n=== MERGE: {len(graphs)} graphs -> {out} ===\n", "mag")
            run_cmd(graphify_cmd() + ["merge-graphs", *graphs, "--out", out], self.log)
            self.log("=== MERGE COMPLETE ===\n", "ok")
            self.set_status("Merge complete")
        threading.Thread(target=w, daemon=True).start()

    def schedule_rebuild(self):
        """Register a daily Windows scheduled task to rebuild this repo's graph."""
        if not self.repo_path:
            messagebox.showinfo("Grafel", "Run a scan first.", parent=self.root)
            return
        base = re.sub(r"[^A-Za-z0-9]", "_", os.path.basename(self.repo_path))[:30]
        task = "Grafel_Rebuild_" + base
        cmd = graphify_cmd() + ["update", self.repo_path]
        tr = " ".join(f'"{c}"' if " " in c else c for c in cmd)
        try:
            r = subprocess.run(
                ["schtasks", "/Create", "/F", "/SC", "DAILY", "/TN", task,
                 "/TR", tr, "/ST", "09:00"],
                capture_output=True, text=True,
                creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
            )
            if r.returncode == 0:
                self.log(f"\n[schedule] daily 09:00 graph rebuild registered "
                         f"as '{task}'\n", "ok")
                messagebox.showinfo("Grafel", f"Scheduled a daily graph rebuild at "
                                    f"09:00.\nTask: {task}\n\nRemove it anytime in Task "
                                    f"Scheduler.", parent=self.root)
            else:
                self.log(f"[schedule] failed: {(r.stderr or '').strip()[:200]}\n", "err")
        except Exception as e:
            self.log(f"[schedule] error: {e}\n", "err")

    def show_about(self):
        messagebox.showinfo(
            "About Grafel",
            f"Grafel {APP_VERSION} - the memory layer for AI coding.\n"
            f"by {APP_AUTHOR}\n\n"
            "Maps your codebase into a graph so Copilot, Claude Code, Codex and\n"
            "more answer from a ~2k-token query instead of re-reading everything.\n\n"
            "Includes real token/cost proof and a local AI-usage scanner.",
            parent=self.root,
        )

    def check_updates(self):
        base = (self.cfg.get("server_url") or "").rstrip("/")
        if not base:
            messagebox.showinfo(
                "Grafel", "No update server configured.\n\n"
                "Set \"server_url\" in ~/.grafel.json to your deployed backend.",
                parent=self.root)
            return
        threading.Thread(target=self._update_worker, args=(base,),
                         daemon=True).start()

    def _update_worker(self, base):
        import urllib.request
        try:
            with urllib.request.urlopen(base + "/update/manifest", timeout=8) as r:
                data = json.loads(r.read().decode("utf-8"))
        except Exception as e:
            err = str(e)
            self.root.after(0, lambda: messagebox.showwarning(
                "Grafel", f"Update check failed:\n{err}", parent=self.root))
            return
        latest = str(data.get("version", ""))
        if latest and latest != APP_VERSION:
            def offer():
                if messagebox.askyesno(
                    "Grafel", f"Update available: {latest} "
                    f"(you have {APP_VERSION}).\n\n{data.get('notes', '')}\n\n"
                    "Open the download page?", parent=self.root):
                    webbrowser.open(data.get("url", ""))
            self.root.after(0, offer)
        else:
            self.root.after(0, lambda: messagebox.showinfo(
                "Grafel", f"You're on the latest version ({APP_VERSION}).",
                parent=self.root))

    # ---------- graph view / diff / MCP server ----------

    def _load_graph_report(self, path):
        """Load GRAPH_REPORT.md into the in-app GRAPH tab (no browser needed).

        Call from a WORKER thread: graph_artifact_state walks the whole repo
        computing mtimes (multi-second on large/OneDrive-synced repos), which
        used to freeze the UI when this ran on the Tk main thread. Only the
        final text-box update is marshalled back via root.after."""
        txt = graph_report_text(path)
        state = graph_artifact_state(path, SAVINGS_CODE_EXT, SAVINGS_SKIP_DIRS)
        if state["graph_exists"] and (state["graph_stale"] or state["report_stale"]):
            txt = (
                "[freshness] graph artifacts may be stale. Re-run INITIATE SCAN or WATCH.\n\n"
                + txt
            )
        self.root.after(0, lambda: self._set_graph_report_text(txt))

    def _set_graph_report_text(self, txt):
        box = self._boxes.get("graph")
        if not box:
            return
        try:
            box.configure(state="normal")
            box.delete("1.0", "end")
            box.insert("end", txt[:200000])
            box.configure(state="disabled")
        except tk.TclError:
            pass

    def graph_diff(self):
        if not self.repo_path:
            messagebox.showinfo("Grafel", "Run a scan first.", parent=self.root)
            return
        threading.Thread(target=self._diff_worker, daemon=True).start()

    def _diff_worker(self):
        self.root.after(0, lambda: self._select_tab("insights"))

        def L(t, tag=None):
            self.log(t, tag, box="insights")

        gpath = os.path.join(self.repo_path, "graphify-out", "graph.json")
        snap = os.path.join(self.repo_path, "graphify-out", ".grafel_snapshot.json")
        diff = diff_graph_snapshot(gpath, snap)
        L("\n=== GRAPH DIFF ===\n", "mag")
        if diff.get("error") == "missing_graph":
            L("\n[diff] no graph.json - run a scan first.\n", "err")
            return
        if diff.get("error"):
            L(f"[diff] cannot read graph: {diff['error']}\n", "err")
            return
        if diff["baseline"]:
            L(f"No previous snapshot - saving baseline ({diff['current_count']} nodes).\n")
        else:
            L(f"Since last snapshot:  +{len(diff['added'])} nodes  -{len(diff['removed'])} nodes\n", "ok")
            for node in diff["added"][:15]:
                L(f"   + {str(node)[:70]}\n")
            for node in diff["removed"][:15]:
                L(f"   - {str(node)[:70]}\n", "err")
            if not diff["added"] and not diff["removed"]:
                L("   (no node-level changes)\n", "dim")
        if diff["snapshot_updated"]:
            L("Snapshot updated.\n", "dim")
        L("==================\n\n", "mag")

    def mcp_cmd(self, graph_json):
        """Resolve how to launch graphify's MCP server for this graph."""
        if getattr(sys, "frozen", False):
            return [sys.executable, "--run-mcp", "--graph", graph_json]
        exe = shutil.which("graphify-mcp") or shutil.which("graphify-mcp.cmd")
        if exe:
            return [exe, "--graph", graph_json]
        return [sys.executable, "-m", "graphify.serve", "--graph", graph_json]

    def register_mcp_server(self):
        """Register the repo's graph as an MCP server so agents query it natively."""
        if not self.repo_path:
            messagebox.showinfo("Grafel", "Run a scan first.", parent=self.root)
            return
        gpath = os.path.join(self.repo_path, "graphify-out", "graph.json")
        cmd = self.mcp_cmd(gpath)
        server = {"command": cmd[0], "args": cmd[1:]}
        merge_json_servers(
            os.path.join(self.repo_path, ".vscode", "mcp.json"), "servers",
            {"grafel-graph": {"type": "stdio", **server}}, self.log,
        )
        merge_json_servers(
            os.path.join(self.repo_path, ".mcp.json"), "mcpServers",
            {"grafel-graph": server}, self.log,
        )
        self.log("[mcp] registered 'grafel-graph' query-server "
                 "(agents can call the graph natively)\n", "ok")
        messagebox.showinfo("Grafel", "Registered the graph as an MCP server "
                            "('grafel-graph').\nRestart your AI tool to load it.",
                            parent=self.root)

    def cloud_upload(self):
        """Upload this repo's graph to the Grafel backend for team sharing."""
        if not self.repo_path:
            messagebox.showinfo("Grafel", "Run a scan first.", parent=self.root)
            return
        base = (self.cfg.get("server_url") or "").rstrip("/")
        key = self.cfg.get("license_key", "")
        if not base or not key:
            messagebox.showinfo("Grafel", "Set \"server_url\" and \"license_key\" in "
                                "~/.grafel.json first.", parent=self.root)
            return
        gpath = os.path.join(self.repo_path, "graphify-out", "graph.json")
        if not os.path.exists(gpath):
            messagebox.showinfo("Grafel", "No graph.json - run a scan first.",
                                parent=self.root)
            return
        proj = os.path.basename(self.repo_path)
        threading.Thread(target=self._cloud_upload_worker,
                         args=(base, key, proj, gpath), daemon=True).start()

    def _cloud_upload_worker(self, base, key, proj, gpath):
        import urllib.request
        self.set_status("Uploading graph")
        try:
            with open(gpath, "rb") as f:
                data = f.read()
            req = urllib.request.Request(
                f"{base}/graph/{proj}", data=data, method="PUT",
                headers={"X-License-Key": key, "Content-Type": "application/json"})
            with urllib.request.urlopen(req, timeout=20) as r:
                self.log(f"\n[cloud] uploaded graph for '{proj}' (HTTP {r.status})\n", "ok")
            self.set_status("Uploaded")
        except Exception as e:
            self.log(f"[cloud] upload failed: {e}\n", "err")
            self.set_status("Cloud error")

    def cloud_download(self):
        """Download a shared team graph from the Grafel backend into this repo."""
        if not self.repo_path:
            messagebox.showinfo("Grafel", "Open a repo first (Browse or scan).",
                                parent=self.root)
            return
        base = (self.cfg.get("server_url") or "").rstrip("/")
        key = self.cfg.get("license_key", "")
        if not base or not key:
            messagebox.showinfo("Grafel", "Set \"server_url\" and \"license_key\" in "
                                "~/.grafel.json first.", parent=self.root)
            return
        proj = os.path.basename(self.repo_path)
        threading.Thread(target=self._cloud_download_worker,
                         args=(base, key, proj), daemon=True).start()

    def _cloud_download_worker(self, base, key, proj):
        import urllib.request
        self.set_status("Downloading graph")
        try:
            req = urllib.request.Request(f"{base}/graph/{proj}",
                                         headers={"X-License-Key": key})
            with urllib.request.urlopen(req, timeout=20) as r:
                payload = json.loads(r.read().decode("utf-8"))
            outdir = os.path.join(self.repo_path, "graphify-out")
            os.makedirs(outdir, exist_ok=True)
            with open(os.path.join(outdir, "graph.json"), "w", encoding="utf-8") as f:
                json.dump(payload.get("graph", {}), f)
            self.log(f"\n[cloud] downloaded team graph for '{proj}' "
                     "-> graphify-out/graph.json\n", "ok")
            self.set_status("Downloaded")
        except Exception as e:
            self.log(f"[cloud] download failed: {e}\n", "err")
            self.set_status("Cloud error")

    def fail(self, msg):
        self.log(f"\nERROR: {msg}\n")
        self.set_status("Failure detected")


def run_headless(target):
    """CLI companion: `Grafel.exe <path>` (or `.`) builds the graph and wires AI
    tools without the GUI, printing progress to the parent console."""
    if getattr(sys, "frozen", False) and os.name == "nt":
        try:
            import ctypes
            ctypes.windll.kernel32.AttachConsole(-1)
            sys.stdout = open("CONOUT$", "w", encoding="utf-8")
            sys.stderr = sys.stdout
        except Exception:
            pass
    path = os.path.abspath(target)
    if not os.path.isdir(path):
        print(f"Grafel: not a folder: {path}")
        return 1

    def log(text, tag=None):
        try:
            sys.stdout.write(text)
            sys.stdout.flush()
        except Exception:
            pass

    print(f"Grafel :: building graph for {path}\n")
    status = build_graph(path, run_cmd, graphify_cmd, log)
    build_code = status.get("code", 1) if isinstance(status, dict) else 1
    for cmd in ("vscode", "claude", "codex"):
        run_cmd(graphify_cmd() + [cmd, "install"], log, cwd=path)
    if os.path.isdir(os.path.join(path, ".git")):
        run_cmd(graphify_cmd() + ["hook", "install"], log, cwd=path)
    install_repo_mcp(path, merge_json_servers, log)
    write_repo_routing(path, write_routing_block, log)
    if build_code != 0:
        print(f"\nGrafel :: graph build FAILED (exit {build_code}); "
              "AI tool wiring was still written, but the graph is stale/missing.")
        return build_code
    print("\nGrafel :: done. AI tools now query the graph for this repo.")
    return 0


def _ensure_cli_console():
    """The installed Grafel.exe is built windowed (console=False, see Grafel.spec)
    for the GUI, so it has no stdout/stderr — the --proof-query/--proof-command
    CLI dispatch below (what grafel-query.cmd/grafel-path.cmd/grafel-explain.cmd/
    grafel-save-result.cmd shell out to) would otherwise run silently: graphify
    still executes and the proof log still gets the usage event, but the caller
    (an AI agent's shell) sees zero output. Attach to the launching shell's
    console so the answer actually reaches it; fall back to allocating a fresh
    console if there's no parent one (e.g. launched from Task Scheduler). No-op
    in dev mode (`python grafel.py ...`), where a real console is already
    attached and both calls below simply fail (ERROR_ACCESS_DENIED) and leave
    sys.stdout untouched."""
    if os.name != "nt":
        return
    import ctypes
    ATTACH_PARENT_PROCESS = -1
    attached = ctypes.windll.kernel32.AttachConsole(ATTACH_PARENT_PROCESS)
    if not attached:
        attached = ctypes.windll.kernel32.AllocConsole()
    if not attached:
        return
    try:
        sys.stdout = open("CONOUT$", "w", encoding="utf-8", errors="replace")
        sys.stderr = open("CONOUT$", "w", encoding="utf-8", errors="replace")
        sys.stdin = open("CONIN$", "r", encoding="utf-8", errors="replace")
    except OSError:
        pass


def run_proof_command(repo_path, command_name, argv):
    repo_path = os.path.abspath(repo_path)
    if not os.path.isdir(repo_path):
        print(f"Grafel: not a folder: {repo_path}")
        return 1
    if not argv:
        print(f"Grafel: missing graphify {command_name} arguments")
        return 1
    code, out = run_cmd(
        graphify_cmd() + [command_name] + argv,
        lambda _t, _tag=None: None,
        cwd=repo_path,
    )
    if out:
        sys.stdout.write(out if out.endswith("\n") else out + "\n")
    if code == 0 and out.strip():
        tokens, _ = count_tokens(out)
        try:
            append_graph_use_event(
                repo_path,
                source="repo_helper",
                command=command_name,
                argv=list(argv),
                cwd=repo_path,
                tokens=tokens,
                success=True,
            )
        except OSError:
            pass
    return code


def main():
    # Self-dispatch: "Grafel.exe --run-graphify <args>" runs the BUNDLED
    # graphify engine (used when the exe is installed on a machine without
    # Python/graphify - the engine ships inside the exe).
    if len(sys.argv) > 1 and sys.argv[1] == "--run-graphify":
        sys.argv = ["graphify"] + sys.argv[2:]
        from graphify.__main__ import main as graphify_main  # type: ignore
        sys.exit(graphify_main())

    # MCP server dispatch: "Grafel.exe --run-mcp <args>" serves the graph over MCP.
    if len(sys.argv) > 1 and sys.argv[1] == "--run-mcp":
        sys.argv = ["graphify-mcp"] + sys.argv[2:]
        from graphify.serve import _main as mcp_main  # type: ignore
        sys.exit(mcp_main())

    if len(sys.argv) > 2 and sys.argv[1] == "--run-grafel-strict-mcp":
        serve_strict_mcp(sys.argv[2], graphify_cmd())
        return

    if len(sys.argv) > 1 and sys.argv[1] in ("--proof-query", "--proof-command"):
        _ensure_cli_console()

    if len(sys.argv) > 1 and sys.argv[1] == "--proof-query":
        repo = sys.argv[2] if len(sys.argv) > 2 else ""
        args = sys.argv[3:] if len(sys.argv) > 3 else []
        sys.exit(run_proof_command(repo, "query", args))
    if len(sys.argv) > 1 and sys.argv[1] == "--proof-command":
        repo = sys.argv[2] if len(sys.argv) > 2 else ""
        command_name = sys.argv[3] if len(sys.argv) > 3 else ""
        args = sys.argv[4:] if len(sys.argv) > 4 else []
        sys.exit(run_proof_command(repo, command_name, args))

    # CLI companion: "Grafel.exe <path>" or "Grafel.exe ." runs headless.
    if len(sys.argv) > 1 and not sys.argv[1].startswith("-"):
        sys.exit(run_headless(sys.argv[1]))

    # Windows taskbar / Task Manager: give Grafel its own AppUserModelID so it
    # shows Grafel's icon instead of being grouped under python/pythonw.
    if os.name == "nt":
        try:
            import ctypes
            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(
                "Codewithusman.Grafel.1")
        except Exception:
            pass

    # pythonw has no stderr - capture crashes/tracebacks to a log file instead
    if sys.stderr is None or sys.stdout is None:
        err_path = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                "grafel.err.log")
        sys.stderr = sys.stdout = open(err_path, "a", encoding="utf-8")
    # single-instance lock: if already running, tell that instance to show
    # itself and exit quietly (relaunch = focus, not an error dialog).
    # "--new-window" (or the NEW WIN button) skips the lock so multiple
    # independent Grafel windows can run side by side.
    lock = None
    if "--new-window" not in sys.argv:
        lock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        try:
            lock.bind(("127.0.0.1", 51799))
            lock.listen(1)
        except OSError:
            try:
                c = socket.create_connection(("127.0.0.1", 51799), timeout=2)
                c.sendall(b"SHOW")
                c.close()
            except OSError:
                # Port is taken but nothing answers our connect — this is a
                # port conflict with an unrelated app, not a running Grafel.
                # Never exit with zero feedback and no window.
                try:
                    err_root = tk.Tk()
                    err_root.withdraw()
                    messagebox.showerror(
                        "Grafel",
                        "Grafel could not start: another program is using port "
                        "51799 (Grafel's single-instance lock), and it does not "
                        "respond like a running Grafel window.\n\n"
                        "Close the program holding the port, or launch Grafel "
                        "with --new-window to skip the single-instance check.",
                        parent=err_root)
                    err_root.destroy()
                except tk.TclError:
                    print("Grafel: port 51799 is in use by another program - "
                          "close it or launch with --new-window.")
            return
    root = tk.Tk()
    root._instance_lock = lock  # keep alive for process lifetime
    try:
        root.iconbitmap(resource_path("grafel.ico"))
    except tk.TclError:
        pass
    try:
        root.call("tk", "scaling", 1.3)
    except tk.TclError:
        pass
    App(root)

    def _accept_focus():
        while True:
            try:
                conn, _ = lock.accept()
                conn.close()
                root.after(0, lambda: (root.deiconify(), root.lift(),
                                       root.focus_force()))
            except OSError:
                break
    if lock is not None:
        threading.Thread(target=_accept_focus, daemon=True).start()
    root.mainloop()
    os._exit(0)


if __name__ == "__main__":
    main()
