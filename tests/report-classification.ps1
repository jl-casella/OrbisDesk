$ErrorActionPreference = 'Stop'
. "$PSScriptRoot/../tools/probe-outcome.ps1"
$start = 'PWPS4 {"event":"start","case":"files","status":"running","code":0,"detail":""}'
$passed = 'PWPS4 {"event":"result","case":"files","status":"passed","code":0,"detail":"ok"}'
$failed = 'PWPS4 {"event":"result","case":"files","status":"failed","code":1,"detail":"read failed"}'
$cases = @(
    @{text="$start`n$passed"; code=0; timeout=$false; expected='passed'},
    @{text="$start`n$failed"; code=1; timeout=$false; expected='failed'},
    @{text="$start`n$passed"; code=7; timeout=$false; expected='blocked'},
    @{text="$start`n$passed"; code=0; timeout=$true; expected='blocked'},
    @{text=$passed; code=0; timeout=$false; expected='blocked'},
    @{text="$start`nPWPS4 {broken}"; code=0; timeout=$false; expected='blocked'},
    @{text="$start`n$passed`nCommonStub: Stub: sysarch (nid: example) called, returning zero"; code=0; timeout=$false; expected='blocked'},
    @{text="$start`n$failed`nCommonStub: Stub: sysarch (nid: example) called, returning zero"; code=1; timeout=$false; expected='blocked'},
    @{text="$start`n$passed`n[Core.Linker] Stub resolved foo as poll"; code=0; timeout=$false; expected='passed'},
    @{text="$start`n$passed`nprocess.cpp:312 exit: Unreachable code!`nExiting with status code 0"; code=-2147483645; timeout=$false; expected='passed'}
    @{text="$start`n$passed"; code=7; timeout=$false; expected='passed'; expectedExit=7},
    @{text="$start`n$passed"; code=0; timeout=$false; expected='blocked'; expectedExit=7},
    @{text="$start`n$passed`nprocess.cpp:312 exit: Unreachable code!`nExiting with status code 7"; code=-2147483645; timeout=$false; expected='blocked'; expectedExit=7},
    @{text="$start`nPWPS4 {`"event`":`"result`",`"case`":`"files`",`"status`":`"blocked`",`"code`":-5,`"detail`":`"unsupported instruction`"}"; code=1; timeout=$false; expected='blocked'},
    @{text=("$start`n$passed`nprocess.cpp:312 exit: Unreachable code!`nExiting with status code 0" -replace '"case":"files"','"case":"process-exit-zero"'); code=-2147483645; timeout=$false; expected='blocked'; caseName='process-exit-zero'}
)
foreach ($case in $cases) {
    $expectedExit = if ($case.ContainsKey('expectedExit')) { $case.expectedExit } else { 0 }
    $caseName = if ($case.ContainsKey('caseName')) { $case.caseName } else { 'files' }
    $outcome = Get-ProbeOutcome -Case $caseName -LogText $case.text -ExitCode $case.code -TimedOut $case.timeout -ExpectedExitCode $expectedExit
    if ($outcome.status -ne $case.expected) {
        throw "Expected $($case.expected), got $($outcome.status): $($case.text)"
    }
}
Write-Host "$($cases.Count) reporting scenarios passed."
