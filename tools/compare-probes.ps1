[CmdletBinding()]
param(
    [Parameter(Mandatory)][string]$Reference,
    [Parameter(Mandatory)][string]$Candidate,
    [Parameter(Mandatory)][string]$Output
)
$ErrorActionPreference = 'Stop'
$before = Get-Content -Raw -LiteralPath $Reference | ConvertFrom-Json
$after = Get-Content -Raw -LiteralPath $Candidate | ConvertFrom-Json
if ($before.elf.sha256 -ne $after.elf.sha256) { throw 'Comparison requires the same guest executable.' }
$fixtureHashes = [ordered]@{}
$referenceFixtures = @($before.fixtures.PSObject.Properties | Where-Object { $null -ne $_ })
$candidateFixtures = @($after.fixtures.PSObject.Properties | Where-Object { $null -ne $_ })
if ($referenceFixtures.Count -ne $candidateFixtures.Count) { throw 'Fixture sets differ.' }
foreach ($fixture in $referenceFixtures) {
    $match = $candidateFixtures | Where-Object Name -eq $fixture.Name
    if (!$match -or $match.Value.sha256 -ne $fixture.Value.sha256) { throw 'Comparison requires identical fixture hashes.' }
    $fixtureHashes[$fixture.Name] = $fixture.Value.sha256
}
if (@($before.results.case | Sort-Object -Unique).Count -ne $before.results.Count -or
    @($after.results.case | Sort-Object -Unique).Count -ne $after.results.Count) { throw 'Duplicate test cases.' }
if (Compare-Object @($before.results.case) @($after.results.case)) { throw 'Case sets differ.' }
$cases = foreach ($previous in $before.results) {
    $current = $after.results | Where-Object case -eq $previous.case
    [ordered]@{
        case = $previous.case
        reference_status = $previous.status
        candidate_status = $current.status
        changed = $previous.status -ne $current.status
        reference_exit_code = $previous.emulator_exit_code
        candidate_exit_code = $current.emulator_exit_code
        reason = $current.reason
    }
}
[ordered]@{
    schema_version = 1
    guest_sha256 = $after.elf.sha256
    fixture_sha256 = $fixtureHashes
    reference_run = $before.run_id
    candidate_run = $after.run_id
    reference_emulator = $before.emulator
    candidate_emulator = $after.emulator
    cases = @($cases)
} | ConvertTo-Json -Depth 10 | Set-Content -LiteralPath $Output -Encoding utf8
Write-Host "Comparison saved: $Output"
