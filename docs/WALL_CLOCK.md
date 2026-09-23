# Wall clock and SNTP

Anvil keeps wall time as a UTC epoch anchored to the board's monotonic tick
source. Reading the clock never depends on processor clock rate, and elapsed
time continues while network service is offline. At cold start the clock is
unset unless `clock.utc` contains a valid saved floor. A restored floor is
reported as untrusted until the operator sets the clock or a validated SNTP
reply arrives.

The graphical caption prints `Time not synchronized` for both an unset clock
and a restored floor, so clipping cannot leave a believable date after its
warning. `time` status still prints the restored floor and its full provenance.
A manual caption begins with `Manual:`; a validated SNTP caption is the compact
live date/time and zone.

The clock's caption is the first part of the banner's status row, which also
carries the part's temperature and, where one is driven, the fan's duty. See
[BANNER_STATUS_ROW.md](BANNER_STATUS_ROW.md).

The service is asynchronous. Boot only initializes state; the prompt service
performs bounded DNS, ARP and SNTP steps. Missing configuration, an offline
link, an unanswered neighbour, a lost DHCP lease and a reply timeout all enter
bounded retry/backoff. None waits inside boot or the command interpreter.

Server selection is, in order:

1. the explicit `ntp.server` setting;
2. the first usable address in DHCP option 42, bound to the interface whose
   lease supplied it; and
3. `time.cloudflare.com` through a usable DHCP/configured DNS resolver.

The default hostname follows Cloudflare's published device-use guidance. It is
not a location service and never selects a time zone. The DHCP option format is
defined by [RFC 2132 section 8.3](https://www.rfc-editor.org/rfc/rfc2132#section-8.3).

Every accepted reply must come from the exact selected interface, destination
address, server IPv4 address and UDP port 123. It must be an SNTPv4 unicast
server reply with leap state synchronized, stratum 1 through 15, a nonzero
transmit timestamp and an originate timestamp equal to the opaque nonce in the
outstanding request. The 32-bit NTP seconds field is interpreted across the
2036 era boundary only when the result is in Anvil's supported 1980 through
2099 civil range. These checks follow [RFC 4330](https://www.rfc-editor.org/rfc/rfc4330)
and [RFC 5905](https://www.rfc-editor.org/rfc/rfc5905).

Plain SNTP is **not cryptographically authenticated**. Exact tuple and nonce
validation rejects unrelated, stale and unsolicited datagrams, but it does not
defeat an on-path attacker. Status and source text state that limitation.

## Commands and settings

`time` prints live local civil time, provenance, source age, zone and service
state. `time sync` schedules a refresh and immediately returns to the prompt.

`time server <IPv4-or-hostname>` selects an explicit unicast server in memory.
`time server default` restores DHCP-option-42 then Cloudflare fallback. A
malformed hostname, zero/broadcast/multicast address or unknown zone is refused.

`time zone UTC` selects UTC. `time zone America/Chicago` applies the U.S.
Central rules represented in the supported 1980 through 2099 range and labels
the live result CST or CDT. `time zone fixed:+HH:MM` and
`time zone fixed:-HH:MM` select a fixed offset that never changes for daylight
saving time. Public/default behavior is UTC; no IP-based zone guessing occurs.

`time set <unix-seconds-UTC>` supplies trusted manual time. The saved value
becomes a restored floor after a reboot rather than being described as an RTC
reading.

All command changes are initially in memory. `settings save` persists ordinary
non-secret `clock.utc`, `clock.zone` and `ntp.server` entries to `SETTINGS.TXT`.
On a target with no network backend, the common clock still supports status,
manual time and zones, and honestly reports that SNTP is unavailable.

The supported named-zone rules are code, not an online time-zone database. If
U.S. law changes future Central transitions, a newer Anvil build is required;
until then UTC remains the unambiguous fallback.
