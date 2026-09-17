@echo off
setlocal
for %%I in ("%~dp0..") do set REPO=%%~fI
if exist "%LocalAppData%\Programs\Grafel\GrafelCLI.exe" (
  "%LocalAppData%\Programs\Grafel\GrafelCLI.exe" --run-grafel-strict-mcp "%REPO%"
  exit /b %errorlevel%
)
where GrafelCLI.exe >nul 2>nul
if not errorlevel 1 (
  GrafelCLI.exe --run-grafel-strict-mcp "%REPO%"
  exit /b %errorlevel%
)
if exist "%REPO%\grafel.py" (
  python "%REPO%\grafel.py" --run-grafel-strict-mcp "%REPO%"
  exit /b %errorlevel%
)
echo Grafel strict MCP requires GrafelCLI.exe or source checkout.
exit /b 1
