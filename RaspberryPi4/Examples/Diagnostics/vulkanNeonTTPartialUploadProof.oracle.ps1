param([Parameter(Mandatory = $true)][string]$ReportPath)

$bytes = [System.IO.File]::ReadAllBytes((Resolve-Path -LiteralPath $ReportPath).Path)
if ($bytes.Length -ne 128) { throw "Expected exactly 128 report bytes; got $($bytes.Length)." }
$words = @(for ($i = 0; $i -lt 32; $i++) { [BitConverter]::ToUInt32($bytes, $i * 4) })
if ($words[1] -ne 0) {
    throw ('Payload stopped at stage {0}, status {1}, Vulkan fault count {2}, text 0x{3:X8}.' -f $words[2], $words[1], $words[13], $words[14])
}
$fullBytes = 512 * 1024 * 4
$firstSourceOffset = 64 + ((24 * 512 + 48) * 4)
$checks = @{
    0 = 0x4D534E56; 1 = 0; 2 = 9; 3 = 0
    4 = 1; 5 = 2; 6 = 128; 7 = $firstSourceOffset; 8 = 512; 9 = 48; 10 = 24
    11 = 2; 12 = 4; 13 = 0; 14 = 0; 15 = 0x4D534E56
    16 = 0xFF112233; 17 = 0xFFABCDEF; 18 = 0xFF102030; 19 = 0xFFFF0000
    20 = 0xFF445566; 21 = 0xFF778899; 22 = 0xFF000000; 23 = $fullBytes
    24 = $fullBytes; 25 = 5; 26 = 2; 27 = 3; 28 = 0; 29 = 1; 30 = 0x00020001
    31 = 0x4D534E56
}
foreach ($slot in $checks.Keys) {
    $expected = [BitConverter]::ToUInt32([BitConverter]::GetBytes([int32]$checks[$slot]), 0)
    if ($words[$slot] -ne $expected) {
        throw ('Report[{0}] expected 0x{1:X8}, got 0x{2:X8}.' -f $slot, $expected, $words[$slot])
    }
}
Write-Output 'TrueType-atlas partial upload proof passed: aligned strided region, two reduced transfers (2 then 1 guarded DMA operations), cache hit without transfer, full fallback/reset, GPU pixels and untouched atlas pixel.'
