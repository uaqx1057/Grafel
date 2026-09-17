import glob
import json
import os
import tempfile


def find_workspace_for(repo_path, parse_workspace_folders, extra_roots=None):
    """Find a .code-workspace file that includes repo_path among its folders."""
    if not repo_path:
        return None, []
    target = os.path.normcase(os.path.normpath(repo_path))
    roots = []
    seen_root = set()

    def add_root(root):
        if root and os.path.isdir(root) and root not in seen_root:
            seen_root.add(root)
            roots.append(root)

    for pattern in ("~/Desktop", "~/OneDrive*/Desktop", "~/Documents", "~"):
        for root in glob.glob(os.path.expanduser(pattern)):
            add_root(root)
    for root in extra_roots or []:
        add_root(root)
    path = repo_path
    for _ in range(4):
        path = os.path.dirname(path)
        add_root(path)
    for root in roots:
        try:
            names = os.listdir(root)
        except OSError:
            continue
        for name in names:
            if not name.lower().endswith(".code-workspace"):
                continue
            ws_file = os.path.join(root, name)
            folders = parse_workspace_folders(ws_file)
            if any(os.path.normcase(os.path.normpath(folder)) == target for folder in folders):
                return ws_file, folders
    return None, []


def load_config(config_file):
    try:
        with open(config_file, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return {}


def save_config(config_file, cfg):
    """Atomic write: dump to a temp file in the same directory, then
    os.replace() it over the target, so a crash or hard exit (os._exit)
    mid-write can never leave a truncated/corrupted config behind."""
    try:
        fd, tmp_path = tempfile.mkstemp(
            dir=os.path.dirname(config_file) or ".",
            prefix=os.path.basename(config_file) + ".",
            suffix=".tmp",
        )
    except OSError:
        return
    replaced = False
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(cfg, f, indent=2)
        os.replace(tmp_path, config_file)
        replaced = True
    except OSError:
        pass
    finally:
        if not replaced:
            try:
                os.remove(tmp_path)
            except OSError:
                pass
