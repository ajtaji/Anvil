param([Parameter(Mandatory = $true)][string]$ReportPath)

$bytes = [System.IO.File]::ReadAllBytes((Resolve-Path -LiteralPath $ReportPath).Path)
if ($bytes.Length -ne 256) { throw "Expected exactly 256 report bytes; got $($bytes.Length)." }
$words = @(for ($i = 0; $i -lt 64; $i++) { [BitConverter]::ToUInt32($bytes, $i * 4) })
if ($words[1] -ne 0) {
    throw ('Payload stopped at stage {0}, status {1}, Vulkan fault count {2}, text 0x{3:X8}.' -f $words[2], $words[1], $words[13], $words[14])
}
$checks = @{
    0 = 0x4D42524E; 1 = 0; 2 = 9; 3 = 0; 4 = 0; 5 = 0; 6 = 1
    7 = 4; 8 = 24; 9 = 0xFFFF0000; 10 = 0xFF0000FF; 12 = 0
    13 = 0; 14 = 0; 15 = 0x4D42524E; 16 = 0; 17 = 1
    21 = 1; 22 = 6; 24 = 2; 25 = 12; 27 = 1; 28 = 6
    29 = 0; 30 = 0
}
foreach ($slot in $checks.Keys) {
    $expected = [BitConverter]::ToUInt32([BitConverter]::GetBytes([int32]$checks[$slot]), 0)
    if ($words[$slot] -ne $expected) {
        throw ('Report[{0}] expected 0x{1:X8}, got 0x{2:X8}.' -f $slot, $expected, $words[$slot])
    }
}
if ($words[18] -eq 0) { throw 'Retained source image handles changed before repeat submission.' }
$refusals = @{ 19 = -21201; 20 = -21201; 23 = -21203; 26 = -21202 }
foreach ($slot in $refusals.Keys) {
    if ([BitConverter]::ToInt32($bytes, [int]$slot * 4) -ne $refusals[$slot]) {
        throw "Report[$slot] was not the expected refusal."
    }
}
foreach ($slot in @(11) + @(31..63)) {
    if ($words[$slot] -ne 0) { throw "Reserved report[$slot] is nonzero." }
}
Write-Output 'Retained sprite-batch proof passed: atomic ordered append, direct-draw pixel parity, repeat-frame reuse, clip/transform/tint, capacity and stale-source refusals, teardown.'
