param([Parameter(Mandatory = $true)][string]$ReportPath)

$bytes = [System.IO.File]::ReadAllBytes((Resolve-Path -LiteralPath $ReportPath).Path)
if ($bytes.Length -ne 192) { throw "Expected exactly 192 report bytes; got $($bytes.Length)." }

$words = @(for ($i = 0; $i -lt 48; $i++) { [BitConverter]::ToUInt32($bytes, $i * 4) })
if ($words[1] -ne 0) {
    throw ('Payload stopped at stage {0} with status {1}; create result 0x{2:X8}.' -f $words[2], $words[1], $words[3])
}
$checks = @{
    0 = 0x4D534E56; 1 = 0; 2 = 8; 4 = 4; 5 = 24; 6 = 1
    15 = 0x4D534E56; 16 = 0xFF000000; 17 = 0xFFFF0000
    18 = 0xFF00FF00; 19 = 0xFFFF8000; 20 = 0xFFFF0000
    21 = 0xFF00FF00; 22 = 0xFF0000FF; 23 = 0xFFFFFFFF
    27 = 0; 28 = 2; 29 = 0; 30 = 3
    32 = 0; 33 = 1; 35 = 1; 36 = 0x00C00000
    37 = 3; 38 = 18; 39 = 1
    40 = 0xFFFF0000; 41 = 0xFF00FF00; 42 = 0xFF0000FF
    43 = 0xFFFFFFFF; 44 = 0xFFFF0000; 45 = 0xFF00FF00
    46 = 0xFF00FF00
    47 = 0x4D534E56
}
foreach ($slot in $checks.Keys) {
    $expected = [BitConverter]::ToUInt32([BitConverter]::GetBytes([int32]$checks[$slot]), 0)
    if ($words[$slot] -ne $expected) {
        throw ('Report[{0}] expected 0x{1:X8}, got 0x{2:X8}' -f $slot, $expected, $words[$slot])
    }
}
if ([BitConverter]::ToInt32($bytes, 34 * 4) -ne -21203) {
    throw "Replacement refusal was not NEON_VK_CHROME_ERR_CAPACITY."
}
Write-Output 'Separate-image sprite proof passed: resident pixels survived rejected replacement.'
