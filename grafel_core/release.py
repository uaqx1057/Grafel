import os
import re
import subprocess


def detect_inno_setup():
    candidates = [
        os.path.join(os.environ.get("ProgramFiles(x86)", ""), "Inno Setup 6", "ISCC.exe"),
        os.path.join(os.environ.get("ProgramFiles", ""), "Inno Setup 6", "ISCC.exe"),
        os.path.join(os.environ.get("LocalAppData", ""), "Programs", "Inno Setup 6", "ISCC.exe"),
    ]
    for candidate in candidates:
        if candidate and os.path.exists(candidate):
            return candidate
    return None


def read_app_version(grafel_py_path):
    with open(grafel_py_path, encoding="utf-8", errors="ignore") as f:
        text = f.read()
    match = re.search(r'APP_VERSION\s*=\s*"([^"]+)"', text)
    if not match:
        raise RuntimeError("Could not find APP_VERSION in grafel.py")
    return match.group(1)


def build_installer_command(iscc_path, installer_script, outdir, app_version):
    return [
        iscc_path,
        f"/O{outdir}",
        f"/DAppVersion={app_version}",
        installer_script,
    ]


def run_installer_build(iscc_path, installer_script, outdir, app_version):
    cmd = build_installer_command(iscc_path, installer_script, outdir, app_version)
    return subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace")


def release_preflight(
    repo_root,
    grafel_py_path,
    spec_path,
    installer_script,
    iscc_path,
    output_dir,
    require_inno=True,
):
    errors = []
    warnings = []
    if not os.path.isdir(repo_root):
        errors.append("repo root missing")
    if not os.path.exists(grafel_py_path):
        errors.append("grafel.py missing")
    if not os.path.exists(spec_path):
        errors.append("Grafel.spec missing")
    if not os.path.exists(installer_script):
        errors.append("installer.iss missing")
    if not output_dir:
        errors.append("output dir missing")
    elif "OneDrive" in output_dir:
        warnings.append("output dir is inside OneDrive")
    if require_inno and not iscc_path:
        errors.append("Inno Setup not found")
    elif not iscc_path:
        warnings.append("Inno Setup not found")
    version = None
    if os.path.exists(grafel_py_path):
        try:
            version = read_app_version(grafel_py_path)
        except Exception as exc:
            errors.append(str(exc))
    return {"ok": not errors, "errors": errors, "warnings": warnings, "version": version}
