function Get-ProbeOutcome {
    param([string]$Case, [string]$LogText, [int]$ExitCode, [bool]$TimedOut, [int]$ExpectedExitCode = 0)
    $events = @()
    foreach ($line in ($LogText -split "`n")) {
        $marker = $line.IndexOf('PWPS4 {')
        if ($marker -lt 0) { continue }
        try {
            $event = $line.Substring($marker + 6) | ConvertFrom-Json
            if ($event.case -eq $Case) { $events += $event }
        } catch { }
    }
    $terminal = @($events | Where-Object { $_.event -eq 'result' })
    $started = @($events | Where-Object { $_.event -eq 'start' }).Count -gt 0
    $stubCalls = @([regex]::Matches($LogText, 'CommonStub: Stub: ([^\r\n]+?) called, returning zero') |
        ForEach-Object { $_.Groups[1].Value } | Sort-Object -Unique)
    $shutdown = if ($ExitCode -eq $ExpectedExitCode) { 'clean' } else { 'failed' }
    if ($ExpectedExitCode -eq 0 -and $LogText -match 'Exiting with status code 0\b' -and $LogText -match 'process\.cpp:\d+ exit: Unreachable code!') {
        $shutdown = 'guest-zero-exit-traps-in-emulator'
    }
    $status = 'blocked'
    $reason = 'No guest completion record; inspect emulator logs.'
    $guestPassed = $false
    if ($TimedOut) { $reason = 'Emulator exceeded the time limit.' }
    elseif ($stubCalls.Count -gt 0) {
        $reason = 'Guest invoked unimplemented emulator functions: ' + ($stubCalls -join ', ')
        if ($terminal.Count) { $guestPassed = $terminal[-1].status -eq 'passed' -and $terminal[-1].code -eq 0 }
    } elseif ($started -and $terminal.Count -gt 0) {
        $last = $terminal[-1]
        $guestPassed = $last.status -eq 'passed' -and $last.code -eq 0
        if ($last.status -eq 'blocked') {
            $reason = $last.detail
        } elseif ($guestPassed -and $Case -like 'process-exit-*' -and $shutdown -ne 'clean') {
            $reason = 'Dedicated exit test requires the expected host exit code without an emulator assertion.'
        } elseif ($guestPassed -and $shutdown -in 'clean','guest-zero-exit-traps-in-emulator') {
            $status = 'passed'; $reason = $last.detail
        } elseif ($guestPassed) {
            $reason = 'Guest reported success, but emulator terminated abnormally.'
        } else {
            $status = 'failed'; $reason = $last.detail
        }
    }
    return [ordered]@{
        status=$status; reason=$reason; events=$events; guest_reported_pass=$guestPassed
        emulator_shutdown=$shutdown; invoked_stubs=$stubCalls
    }
}
