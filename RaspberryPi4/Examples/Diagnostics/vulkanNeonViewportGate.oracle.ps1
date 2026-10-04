param([Parameter(Mandatory = $true)][string]$ReportPath)

$bytes = [System.IO.File]::ReadAllBytes((Resolve-Path -LiteralPath $ReportPath).Path)
if ($bytes.Length -ne 128) { throw "Expected exactly 128 report bytes; got $($bytes.Length)." }
$words = @(for ($i = 0; $i -lt 32; $i++) { [BitConverter]::ToUInt32($bytes, $i * 4) })
if ($words[1] -ne 0) {
    throw ('Viewport gate stopped at stage {0}, status {1}.' -f $words[2], $words[1])
}
$expected = @{
    0 = 0x56504E56; 1 = 0; 2 = 7
    3 = 0; 4 = 40; 5 = 1280; 6 = 720
    7 = 41943040; 8 = 23592960
    9 = 56; 10 = 889; 11 = 107; 12 = 563
    13 = 49; 14 = 901; 15 = 107; 16 = 563
    17 = 761; 18 = 5128; 19 = 1499; 20 = 3693
}
foreach ($slot in $expected.Keys) {
    if ($words[$slot] -ne [uint32]$expected[$slot]) {
        throw ('Report[{0}] expected {1}, got {2}.' -f $slot, $expected[$slot], $words[$slot])
    }
}
foreach ($slot in 21..31) {
    if ($words[$slot] -ne 0) { throw "Reserved report[$slot] is nonzero." }
}
Write-Output 'Neon viewport gate passed: float32 letterbox geometry, inverse pointer mapping, bar rejection, and invalid-plan refusal.'
