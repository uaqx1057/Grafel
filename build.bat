@echo off
REM ============================================================
REM  Grafel - full build: icon -> single exe -> installer
REM  Requires: Python 3.x on PATH. Inno Setup 6 for the installer
REM  (winget install JRSoftware.InnoSetup)
REM ============================================================
setlocal
cd /d "%~dp0"

for /f "usebackq delims=" %%V in (`python -c "from grafel_core.release import read_app_version; print(read_app_version('grafel.py'))"`) do set APPVER=%%V
for /f "usebackq delims=" %%I in (`python -c "from grafel_core.release import detect_inno_setup; print(detect_inno_setup() or '')"`) do set ISCC=%%I

echo [preflight] Checking release inputs...
python -c "from grafel_core.release import release_preflight; import os, sys; p=release_preflight(repo_root='.', grafel_py_path='grafel.py', spec_path='Grafel.spec', installer_script='installer.iss', iscc_path=r'%ISCC%', output_dir=os.path.join(os.environ.get('LocalAppData',''), 'GrafelBuild'), require_inno=False); print('version', p.get('version')); print('errors', p.get('errors')); sys.exit(0 if p.get('ok') else 1)" || goto :fail

echo [0/5] Verifying repo...
powershell -ExecutionPolicy Bypass -File "%~dp0verify-grafel.ps1" || goto :fail

echo [1/5] Installing build dependencies...
python -m pip install --quiet --upgrade pyinstaller pillow pystray || goto :fail
python -m pip install --quiet "graphifyy[watch]==0.9.81" || goto :fail

echo [2/5] Generating icon...
python assets\make_icon.py || goto :fail

echo [3/5] Cleaning old build artifacts...
if exist build rmdir /s /q build
if exist dist rmdir /s /q dist

echo [4/5] Building single-file exe (engine bundled inside)...
python -m PyInstaller --noconfirm --clean Grafel.spec || goto :fail
powershell -ExecutionPolicy Bypass -File "%~dp0validate-package.ps1" -ExePath "%~dp0dist\Grafel.exe" -RepoPath "%~dp0." || goto :fail

echo [5/5] Compiling installer (Inno Setup)...
REM Output outside OneDrive to avoid resource-update file locks.
set OUTDIR=%LocalAppData%\GrafelBuild
if defined ISCC (
    "%ISCC%" /O"%OUTDIR%" /DAppVersion=%APPVER% installer.iss || goto :fail
    echo.
    echo DONE: %OUTDIR%\GrafelSetup.exe  ^(one-click installer, version %APPVER%^)
) else (
    echo Inno Setup not found - skipped installer step.
    echo Install it with:  winget install JRSoftware.InnoSetup
    echo Then re-run this script, or just distribute dist\Grafel.exe directly.
)

echo.
echo Portable exe: dist\Grafel.exe
exit /b 0

:fail
echo BUILD FAILED - see output above.
exit /b 1
