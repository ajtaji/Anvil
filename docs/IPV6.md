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


## Neighbor discovery messages

`ipv6_neighbor.pbi` validates Ethernet Router Solicitation, Router Advertisement,
Neighbor Solicitation and Neighbor Advertisement messages. It checks the IPv6
hop limit, ICMPv6 code/checksum, source/target restrictions, bounded options and
DAD destination rules. Fragmented ND is refused, including atomic fragments
(RFC 6980). The packet view now exposes `fragmented` for this policy.
Redirect messages are not implemented. A successful parse is not authorization
to update a neighbor cache: ownership, interface scope and state remain the
endpoint's responsibility. Returned spans borrow the input packet.

`IPv6NeighborSolicit` and `IPv6NeighborAdvertise` emit complete IPv6 messages
with checksums. Solicitation with an unspecified source emits the DAD form
without a source link-layer option. Advertisement emits the owned address and
Ethernet target option; a multicast destination forbids the solicited flag.
Inputs must not overlap output, and insufficient capacity fails before writes.

Anvil 427 capture 282 passed 30 independently constructed message cases and
byte-exact output/guard checks. Capture 283 passed 67 packet cases including
the explicit atomic-fragment marker. Both returned with cores, fonts and
Vulkan healthy. Pi 3 and Rock Pi compile the shared neighbor implementation;
these are compile checks, not physical qualification on those targets.
Multicast reception, neighbor state, DAD/SLAAC and IPv6 transport integration
are still required before this can carry web traffic.


## Neighbor reachability policy

`ipv6_reachability.pbi` supplies caller-owned, interface-scoped entry state.
Init starts address resolution. Tick returns at most one multicast/unicast
solicitation action and consumes one bounded attempt; it never waits or sends.
After three unanswered attempts it reports failure once. The endpoint must
dispatch each action, fail queued packets and invalidate dependent routes.
The caller supplies monotonic milliseconds, the interface retransmit interval,
and randomized reachable duration. This library does not choose randomness.

Use transitions expired/stale entries through the five-second DELAY before
unicast probing. Learn applies validated NS/RA address information. Advertise
implements solicited/override/router flag handling, preserves an existing MAC
when override is refused, and explicitly reports a router-to-host transition.
Confirm accepts upper-layer evidence of forward progress; receiving arbitrary
traffic or duplicate ACKs does not qualify. Address ownership, entry allocation,
route/cache management and packet queues remain the endpoint's responsibility.

Capture 284 on Anvil 427 passed 388 cases: 336 advertisement combinations,
timer boundaries, retry limits, upper-layer confirmation, use/learning and init.
All cores, fonts and Vulkan remained healthy. Pi 3/Rock Pi compilation passed.
This is physical execution of shared policy, not an IPv6 wire qualification.
