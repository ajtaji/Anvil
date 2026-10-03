param([Parameter(Mandatory = $true)][string]$ReportPath)

$bytes = [System.IO.File]::ReadAllBytes((Resolve-Path -LiteralPath $ReportPath).Path)
if ($bytes.Length -ne 192) { throw "Expected exactly 192 report bytes; got $($bytes.Length)." }
$words = @(for ($i = 0; $i -lt 48; $i++) { [BitConverter]::ToUInt32($bytes, $i * 4) })
if ($words[1] -ne 0) {
    throw ('Payload stopped at stage {0}, status {1}, Vulkan fault count {2}, text 0x{3:X8}.' -f $words[2], $words[1], $words[13], $words[14])
}
$checks = @{
    0 = 0x4D534E56; 1 = 0; 2 = 9; 3 = 0
    4 = 0; 5 = 0; 6 = 1; 7 = 1
    11 = 4; 12 = 24
    13 = 0; 14 = 0; 15 = 0x4D534E56
    16 = 0xFFFF0000; 17 = 0xFFFF0000; 18 = 0xFF0000FF
    19 = 0xFFFF0000; 20 = 0xFFFFFFFF
    21 = 0xFF00FF00; 22 = 0xFF008000; 23 = 0xFF000000
    25 = 0; 26 = 0; 31 = 0x4D534E56
    32 = 1; 33 = 1; 38 = 4; 39 = 24
    40 = 0xFFFF0000; 41 = 0xFFFFFF00; 42 = 2; 45 = 3
    46 = 0; 47 = 0x4D534E56
}
foreach ($slot in $checks.Keys) {
    $expected = [BitConverter]::ToUInt32([BitConverter]::GetBytes([int32]$checks[$slot]), 0)
    if ($words[$slot] -ne $expected) {
        throw ('Report[{0}] expected 0x{1:X8}, got 0x{2:X8}.' -f $slot, $expected, $words[$slot])
    }
}
foreach ($slot in @(8, 24)) {
    if ([BitConverter]::ToInt32($bytes, $slot * 4) -ne -21203) {
        throw "Report[$slot] was not the expected capacity refusal."
    }
}
foreach ($slot in @(9, 10)) {
    if ([BitConverter]::ToInt32($bytes, $slot * 4) -ne -21201) {
        throw "Report[$slot] was not the expected transform argument refusal."
    }
}
if ($words[27] -eq 0 -or $words[28] -eq 0 -or $words[27] -eq $words[28] -or
    $words[29] -eq 0 -or $words[30] -eq 0 -or $words[29] -eq $words[30]) {
    throw 'The two resident images or descriptor sets are absent or aliased.'
}
foreach ($pair in @(@(27, 34), @(28, 35), @(29, 36), @(30, 37), @(27, 43))) {
    if ($words[$pair[0]] -ne $words[$pair[1]]) {
        throw "A resident slot changed across refusal or replacement: $($pair[0])/$($pair[1])."
    }
}
if ($words[44] -eq 0 -or $words[44] -eq $words[28]) {
    throw 'The second slot did not publish a distinct replacement image.'
}
Write-Output 'Transformed image proof passed: rotated and cropped/tinted ID 16, atlas/ID 1 coexistence, extreme-coordinate refusal and replacement.'
