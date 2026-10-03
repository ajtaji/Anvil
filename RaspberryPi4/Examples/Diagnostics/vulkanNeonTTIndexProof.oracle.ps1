param([Parameter(Mandatory = $true)][string]$ReportPath)

$bytes = [System.IO.File]::ReadAllBytes((Resolve-Path -LiteralPath $ReportPath).Path)
if ($bytes.Length -ne 128) { throw "Expected exactly 128 report bytes; got $($bytes.Length)." }
$words = @(for ($i = 0; $i -lt 32; $i++) { [BitConverter]::ToUInt32($bytes, $i * 4) })
if ($words[1] -ne 0) {
    throw ('Payload stopped at stage {0}, status {1}, Vulkan fault count {2}, text 0x{3:X8}.' -f $words[2], $words[1], $words[13], $words[14])
}
$checks = @{
    0 = 0x4D534E56; 1 = 0; 2 = 7; 3 = 0
    4 = 512; 5 = 385; 6 = 512; 7 = 2; 8 = 896
    11 = 0; 12 = 0; 13 = 0; 14 = 0; 15 = 0x4D534E56
    17 = 1; 18 = 512; 19 = 0; 31 = 0x4D534E56
}
foreach ($slot in $checks.Keys) {
    $expected = [BitConverter]::ToUInt32([BitConverter]::GetBytes([int32]$checks[$slot]), 0)
    if ($words[$slot] -ne $expected) {
        throw ('Report[{0}] expected 0x{1:X8}, got 0x{2:X8}.' -f $slot, $expected, $words[$slot])
    }
}
foreach ($slot in @(9, 10)) {
    if ([BitConverter]::ToInt32($bytes, $slot * 4) -ne -1) {
        throw "Report[$slot] did not refuse a full table before rasterization."
    }
}
if ($words[16] -eq 0) { throw 'The atlas image was not created.' }
for ($slot = 20; $slot -le 30; $slot++) {
    if ($words[$slot] -ne 0) { throw "Report[$slot] changed outside the defined bounds." }
}
Write-Output 'TrueType cache index proof passed: 512 colliding full-key lookups, misses, full-table refusal before rasterization, reset and teardown.'
