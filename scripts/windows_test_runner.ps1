# Bounded test subprocess. On a Windows host failure/hang, surface only the last
# test name as a check annotation, not arbitrary captured output or credentials.
param([Parameter(Mandatory=$true)][string[]]$Files)
$stdout = Join-Path $env:RUNNER_TEMP 'vox-pytest-out.txt'
$stderr = Join-Path $env:RUNNER_TEMP 'vox-pytest-err.txt'
$arguments = @('-u', '-m', 'pytest', '-vv', '-s', '--timeout=25', '--timeout-method=thread', '-m', '"not desktop"') + $Files
$p = Start-Process -FilePath 'python' -ArgumentList $arguments -PassThru -RedirectStandardOutput $stdout -RedirectStandardError $stderr
$timedOut = !$p.WaitForExit(90000)
if ($timedOut) {
    & taskkill /PID $p.Id /T /F | Out-Null
} else {
    $p.WaitForExit()
}
if (Test-Path $stdout) { Get-Content $stdout }
if (Test-Path $stderr) { Get-Content $stderr }
if ($timedOut -or $p.ExitCode -ne 0) {
    $last = Get-Content $stdout | Where-Object { $_ -match '^tests[/\\].*::test_' } | Select-Object -Last 1
    if (!$last) { $last = 'collection or startup' }
    Write-Output "::error title=Windows tests incomplete::Timed out or failed at $last"
    exit 1
}
