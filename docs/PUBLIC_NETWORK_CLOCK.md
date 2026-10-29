# Shared byte order and prompt counters

`Anvil/Network/byte_order.pbi` owns NetReadBE16/32 and NetWriteBE16/32.
Callers provide a valid span of two or four bytes. Byte-based access accepts
unaligned fields. The network stack's private names delegate to this owner;
the DNS codec includes it without importing the packet stack.

`Anvil/Kernel/Scheduler/prompt_clock.pbi` supplies raw counter values and
frequency through the existing published Ticks/TickHz contracts. These are
raw ticks; the payload service clock reports microseconds. Core prompt
qualification uses the published HwIdEl contract. Board-specific WFE policy
and counter-access control remain unfinished architecture work.

## DNS terminal-dot correction

A query for `example.com.` previously wrote two root bytes before QTYPE,
producing 30 bytes instead of 29. The terminal empty label now reuses its
reserved root position. Ordinary and terminal-dot names produce exactly the
same 29 wire bytes. A one-letter terminal-dot name is also checked. The
[RFC 1035 question format](https://www.rfc-editor.org/rfc/rfc1035.html#section-4.1.2)
has one terminating root byte followed by QTYPE and QCLASS.

Pi4 capture 498 detected the defect at check 51. Corrected capture 499
returns zero and passes 99 byte-order, query/reply, bounds and counter checks.
The entire 8192-byte report is checked, including unused space. Its checker
rejects 218 damaged reports. Runtime timestamps are checked for frequency,
ordering and bounded elapsed time, rather than fixed timestamp values.

The same codec proof compiles for UnoQ only. Removing a trailing blank line
preserved full PMF bytes on both targets, so the captured Pi4 binary is also
the current proof binary. This is not live DNS or full prompt qualification.
Anvil 370 remains installed. Normal build 371 succeeds but is not installed.

## Exact declared runtime hooks

The architecture gate now applies its existing declared-seam rule to legacy
underscore names too. `str_print_at` was already explicitly published in
hal.pbi. Regression fixtures permit calls and addresses of that exact hook,
while rejecting an undeclared helper with the same prefix and a name only
mentioned in prose. Self-tests use their explicit fixture manifest; normal
publication checks retain the authoritative Git inventory. No seam,
fingerprint or ratchet was expanded.

The review removes 10 architecture finding keys, leaving 107 architecture
findings and 98 unchanged provenance omissions. Publication still refuses.
Full Neon and Vulkan completion remain open.
