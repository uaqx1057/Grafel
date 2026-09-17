import os
import subprocess

from grafel_core.live import watch_event_kind


def watch_popen_kwargs(os_name):
    kwargs = {
        "stdout": subprocess.PIPE,
        "stderr": subprocess.STDOUT,
        "text": True,
        "bufsize": 1,
    }
    if os_name == "nt":
        kwargs["creationflags"] = subprocess.CREATE_NO_WINDOW
    return kwargs


def terminate_watch_process(proc, os_name=None, run=None):
    """Stop the watcher including its children.

    graphify_cmd() resolves to a pip console-script launcher (graphify.exe)
    or, when frozen, a PyInstaller onefile exe — on Windows both run the real
    engine as a *child* process, which a plain .terminate() on the launcher
    orphans (the watcher keeps rebuilding after the UI says stopped). Use
    taskkill /T to kill the whole tree on Windows; fall back to .terminate()
    elsewhere or if taskkill is unavailable."""
    if proc is None or proc.poll() is not None:
        return
    os_name = os_name if os_name is not None else os.name
    runner = run if run is not None else subprocess.run
    if os_name == "nt":
        try:
            runner(
                ["taskkill", "/F", "/T", "/PID", str(proc.pid)],
                capture_output=True,
                creationflags=subprocess.CREATE_NO_WINDOW,
            )
            return
        except OSError:
            pass
    try:
        proc.terminate()
    except OSError:
        pass


def watch_start_plan(path, quiet):
    plan = {
        "button_text": "STOP WATCH",
        "status": "Sentinel active - watching",
        "logs": [],
    }
    if not quiet:
        plan["logs"] = [
            (f"\n=== Watching {path} - graph auto-rebuilds on save ===\n", None),
            ("(edit & save any code file; you'll see 'Rebuilt: N nodes' here)\n", "dim"),
        ]
    return plan


def classify_watch_line(line):
    kind = watch_event_kind(line)
    if kind in ("empty", "noise"):
        return None
    if kind == "rebuild":
        return {"tag": "ok", "status": "Graph rebuilt", "text": f"[watch] {line}\n"}
    if kind == "error":
        return {"tag": "err", "status": None, "text": f"[watch] {line}\n"}
    return {"tag": "dim", "status": None, "text": f"[watch] {line}\n"}


def watch_exit_state(code, started_at, saw_output, now):
    quick_fail = code not in (0, None) and (now - started_at) < 3 and not saw_output
    if quick_fail:
        return {
            "status": "Watch failed",
            "button_text": "WATCH",
            "log": (
                "[watch] watcher exited immediately - is the 'watchdog' "
                "package installed for the engine?\n",
                "err",
            ),
        }
    return {"status": "Watch offline", "button_text": "WATCH", "log": None}
