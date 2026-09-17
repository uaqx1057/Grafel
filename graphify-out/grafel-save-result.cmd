@echo off
setlocal
for %%I in ("%~dp0..") do set REPO=%%~fI
if exist "%LocalAppData%\Programs\Grafel\GrafelCLI.exe" (
  "%LocalAppData%\Programs\Grafel\GrafelCLI.exe" --proof-command "%REPO%" "save-result" %*
  exit /b %errorlevel%
)
where GrafelCLI.exe >nul 2>nul
if not errorlevel 1 (
  GrafelCLI.exe --proof-command "%REPO%" "save-result" %*
  exit /b %errorlevel%
)
if exist "%REPO%\grafel.py" (
  python "%REPO%\grafel.py" --proof-command "%REPO%" "save-result" %*
  exit /b %errorlevel%
)
python -m graphify save-result %*
