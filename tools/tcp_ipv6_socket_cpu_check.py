"""Read actual CPU assertion results for mixed-family production TCP."""
import struct
def check(report,cases):
 magic,ipv4,ipv6=struct.unpack_from('<3q',report)
 assert magic==0x534f434b,hex(magic)
 assert ipv4==0,('IPv4 regression assertion',ipv4)
 assert ipv6==0,('IPv6 assertion',ipv6)
 assert report[24:]==b'\xa5'*(len(report)-24),'report guard'
 return dict(passed=True,suites=cases)
