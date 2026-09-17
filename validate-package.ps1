param(
    [string]$ExePath = ".\dist\Grafel.exe",
    [string]$RepoPath = "."
)

$ErrorActionPreference = "Stop"

$ExePath = $ExePath.Trim('"')
$RepoPath = $RepoPath.Trim('"')

if (!(Test-Path -LiteralPath $ExePath)) {
    throw "Grafel executable not found: $ExePath"
}

$resolvedExe = (Resolve-Path -LiteralPath $ExePath).Path
$resolvedRepo = (Resolve-Path -LiteralPath $RepoPath).Path

$requestFile = [System.IO.Path]::GetTempFileName()
Set-Content -LiteralPath $requestFile -Encoding ASCII -Value @(
    '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{}}',
    '{"jsonrpc":"2.0","id":2,"method":"tools/list","params":{}}'
)

$cmdLine = "type `"$requestFile`" | `"$resolvedExe`" --run-grafel-strict-mcp `"$resolvedRepo`""
$psi = New-Object System.Diagnostics.ProcessStartInfo
$psi.FileName = "cmd.exe"
$psi.Arguments = "/d /s /c `"$cmdLine`""
$psi.RedirectStandardOutput = $true
$psi.RedirectStandardError = $true
$psi.UseShellExecute = $false
$psi.CreateNoWindow = $true

$proc = [System.Diagnostics.Process]::Start($psi)
$first = $proc.StandardOutput.ReadLine()
$second = $proc.StandardOutput.ReadLine()
if (!$proc.WaitForExit(10000)) {
    $proc.Kill()
}
Remove-Item -LiteralPath $requestFile -Force -ErrorAction SilentlyContinue

if ($first -notmatch '"serverInfo"') {
    throw "Strict MCP initialize response missing serverInfo: $first"
}
if ($second -notmatch '"grafel.query"' -or $second -notmatch '"grafel.read_file"') {
    throw "Strict MCP tools/list response missing Grafel tools: $second"
}

Write-Host "Package validation passed: strict MCP works from $resolvedExe"
