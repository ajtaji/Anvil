# Pi 4 matched particle staging fast-path profile

The returning `vulkanNeonParticleMatchedCsdProfile.pi4` payload uses the
Pi 4 producer's axis-aligned staging fast path. Anvil build 244 verified its
1,369,732-byte PMFBOOT container (SHA-256
`AB4167A3CAA1A3E29E79984B3209AF2DDDB90A8EA59A8DD976DFFA0C6D0265D4`)
at `0x00800000`. It returned `x0 = 0x00B79D00` after 6.5 seconds under a
confirmed 15-second deadman. A second identical run also returned safely.
No boot image, filesystem, or display scanout was changed.

The first [CSD report](report.bin) has SHA-256
`5D034237C198B5CDC77D2B4A7A5D73CFA0308411B34EC9E764E85438E78A74AE`.
The [repeat CSD report](repeat-report.bin) has SHA-256
`3E56BC4BDC20C4A09759BE671DAC960CFB20946657B7F4DCB379D074C73AA10B`;
its paired [repeat CPU report](repeat-cpu-report.bin) has SHA-256
`6ED66F49AC90D10C8DB35CF1E3E110DEA3892EB955BD75FB11D69881AC86AC07`.
All reports passed the matched checker: one warm-up and three measured
800×800 frames of 10,000 identical green particles, 20,000 final pixels,
four bin/render jobs, no GPU faults, and clean teardown. The unchanged CPU
baseline and both CSD runs used the same Chrome capacity, palette, target,
pre-frame idle, and pixel oracle.

In the first pairing, median CPU and CSD frame times were 589,087 µs and
553,604 µs, a 35,483 µs CSD gain. In the repeat pairing they were 588,397 µs
and 553,626 µs, a 34,771 µs gain. CSD compact-record staging fell from
291,879 µs in the earlier implementation to about 121,000 µs. CSD compute
itself remained about 21,100 µs, while Chrome particle Prepare still
took about 201,000 µs per frame. That span includes geometry validation,
state copying, idle checks, and any palette transfer; it does not isolate
upload cost. This is a narrow static-color workload,
and the frame remains far above 16.7 ms. The CSD route remains opt-in.
