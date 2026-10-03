param([Parameter(Mandatory = $true)][string]$ReportPath)

$bytes = [System.IO.File]::ReadAllBytes((Resolve-Path -LiteralPath $ReportPath).Path)
if ($bytes.Length -ne 256) { throw "Expected exactly 256 report bytes; got $($bytes.Length)." }
$words = @(for ($i = 0; $i -lt 64; $i++) { [BitConverter]::ToUInt32($bytes, $i * 4) })
if ($words[1] -ne 0) {
    throw ('Payload stopped at stage {0}, status {1}, Vulkan fault count {2}, text 0x{3:X8}.' -f $words[2], $words[1], $words[13], $words[14])
}
$checks = @{
    0 = 0x4D534E56; 1 = 0; 2 = 7; 3 = 0; 4 = 16; 5 = 1
    8 = 17; 9 = 102; 10 = 0xFFFF0000; 11 = 0xFF000000
    12 = 0; 13 = 0; 14 = 0; 15 = 0x4D534E56
}
foreach ($slot in $checks.Keys) {
    $expected = [BitConverter]::ToUInt32([BitConverter]::GetBytes([int32]$checks[$slot]), 0)
    if ($words[$slot] -ne $expected) {
        throw ('Report[{0}] expected 0x{1:X8}, got 0x{2:X8}.' -f $slot, $expected, $words[$slot])
    }
}
foreach ($slot in @(6, 7)) {
    if ([BitConverter]::ToInt32($bytes, $slot * 4) -ne -21201) {
        throw "Report[$slot] was not the expected ID 17 argument refusal."
    }
}
$pixels = @(
    0xFF0D070B, 0xFF1A0E16, 0xFF271521, 0xFF341C2C,
    0xFF412337, 0xFF4E2A42, 0xFF5B314D, 0xFF683858,
    0xFF753F63, 0xFF82466E, 0xFF8F4D79, 0xFF9C5484,
    0xFFA95B8F, 0xFFB6629A, 0xFFC369A5, 0xFFD070B0
)
for ($id = 1; $id -le 16; $id++) {
    $actual = $words[15 + $id]
    $expected = [BitConverter]::ToUInt32([BitConverter]::GetBytes([int32]$pixels[$id - 1]), 0)
    if ($actual -ne $expected) {
        throw ('Image ID {0} pixel expected 0x{1:X8}, got 0x{2:X8}.' -f $id, $expected, $actual)
    }
}
foreach ($start in @(32, 48)) {
    $handles = @($words[$start..($start + 15)])
    if ($handles.Contains([uint32]0)) { throw "A handle in report[$start..$($start + 15)] is zero." }
    if (@($handles | Sort-Object -Unique).Count -ne 16) {
        throw "The sixteen handles in report[$start..$($start + 15)] are not distinct."
    }
}
Write-Output 'Sixteen-image proof passed: all pixels and live handles distinct, atlas intact, ID 17 refused, and clean teardown.'
