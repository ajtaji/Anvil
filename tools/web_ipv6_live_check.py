"""Exact live HTTP response evidence and bounds from the physical board."""
import struct,hashlib
def check(report,cases):
 magic,rc,status,n,elapsed,sent,received=struct.unpack_from('<7q',report)
 assert magic==0x48545436
 assert rc==0,(rc,status,n,elapsed)
 assert status==200 and n==cases['body_bytes'],(status,n)
 assert hashlib.sha256(report[256:256+n]).hexdigest()==cases['body_sha256']
 assert report[56:256]==b'\xa5'*200
 assert report[256+n:]==b'\xa5'*(len(report)-256-n)
 return dict(passed=True,status=status,body_bytes=n,elapsed_ms=elapsed,sent=sent,received=received)
