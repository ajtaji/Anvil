# IPv6 implementation status

The shared address and packet codecs are physically qualified on the Pi 4.
They do not yet provide IPv6 connectivity: neighbor discovery, address
configuration, IPv6 routes, transport integration and AAAA resolution remain
unfinished. Existing web transport still refuses IPv6 literals. HTTP/2 and
HTTP/3 are separate unfinished work.

## Address bytes

`Anvil/Network/ipv6_address.pbi` uses exactly 16 network-order bytes, never an
IPv4-sized integer. The caller owns all spans; no global scratch is used.
`IPv6AddressParse(text, bytes, out)` accepts compressed/uncompressed hexadecimal
and an embedded dotted IPv4 tail. It returns zero or -1 and leaves output
unchanged on refusal. Input and the 16-byte output must not overlap. Scope
identifiers, brackets and prefix suffixes must be handled by higher layers.
Leading zeroes in a multi-digit dotted-decimal octet are refused.

`IPv6AddressFormat(address, out, capacity)` returns the explicit text length
and includes a trailing NUL when writing. It emits lowercase hexadecimal,
compressing the first longest run of at least two zero groups. IPv4-mapped
addresses also use hexadecimal output; the dotted display recommendation of
RFC 5952 section 5 is not implemented. Null output with zero capacity measures;
insufficient capacity returns -2 without writing. Output must not overlap
the address. `IPv6AddressPrefix(a, b, bits)` compares 0..128 prefix bits and
returns 1/0, or -1 for an invalid argument.

## Packet views

`Anvil/Network/ipv6_packet.pbi` provides `IPv6PacketParse(packet, bytes, view)`
and `IPv6PacketHeader(out, capacity, source, destination, payloadBytes,
protocol, hops, traffic, flow)`. Header emission writes exactly 40 bytes and
returns 40, or a negative error before writing. Address spans must be separate
from output; the caller writes the payload and computes transport checksums.

The parser returns zero or a negative reason. A successful view borrows packet
storage; retain it until the view is no longer needed. View storage must be
separate from the packet. The declared packet length excludes link padding.
It exposes the source/destination spans, final protocol, payload offset/length,
hop limit, traffic class and flow label. No Next Header ignores trailing bytes.
It validates bounded Hop-by-Hop and Destination option spans and refuses a
misplaced Hop-by-Hop header. Unknown skip-action options are skipped. Other
unknown options return their action bits and offset so the endpoint can discard
and, where required, generate ICMP. No ICMP is sent by this codec.

Routing headers with zero segments left are skipped as unrecognized types;
nonzero segments return a routing error and offset. Atomic fragments can be
viewed; fragments requiring reassembly are refused. Duplicate fragment headers,
more than eight extensions, AH/ESP, and malformed/truncated headers are refused.
Jumbograms are unsupported. The caller must enforce destination/source policy,
hop-limit rules, transport validity and checksums; this is not a complete IPv6
endpoint or a substitute for fragment reassembly.

## Physical qualification

Anvil 426 capture 278 checked 120 address cases, including 91 valid addresses,
output guards, exact bytes, formatter sizing and all 129 prefix lengths.
The first host check expected dotted notation for two IPv4-mapped addresses,
contrary to this formatter's explicit hexadecimal contract. Corrected expected
metadata passed against the same captured bytes; rebuilt raw and PMF payloads
were byte-identical. The original refused check remains in the evidence.

Capture 279 checked exact header construction and packet parsing, including
extension/option actions, atomic/non-atomic fragments, routing, every truncated
fixed-header length, and link padding. Both returning tests left all cores,
fonts and Vulkan healthy. Pi 3 and Rock Pi compilation passed; no physical
execution is claimed for those boards. Evidence and reproducible builders are
under `docs/evidence/anvil-ipv6-20261029` and `tools/build_ipv6_*_cpu.py`.


## Shared transport checksums

The Internet sum/fold/finish arithmetic now has one owner in
`Anvil/Network/internet_checksum.pbi`. IPv4 retains compatibility wrappers;
IPv6 uses the same implementation. `IPv6TransportChecksum` receives 16-byte
source/destination addresses, the final upper-layer protocol, and a payload
span of 0..65535 bytes. Extension headers are excluded. It returns the checksum
or -1 for an invalid argument. A received message including its checksum
validates when the result is zero. A UDP sender maps a computed zero to 65535.

The sum helper operates on valid spans with a nonnegative seed and Anvil's
64-bit integer ABI. When summing consecutive spans, all except the last must
have even lengths. Capture 280 checked 60 cases against independent host
sums, with all four pointer alignments and payload lengths through 65535.

The full Anvil 427 image also passed verified HTTPS gzip/deflate over its
existing IPv4 link after installing the shared checksum owner. Capture 281
returned healthy; the cooperative TLS timings remained approximately 2.7 ms
maximum service and 8.6 ms HTTP Step in that run. This is IPv4 regression
evidence, not an IPv6 wire test.
