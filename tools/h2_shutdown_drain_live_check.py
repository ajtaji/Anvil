"""Verify live HTTP/2 completion and resident TLS output draining."""
import struct
from h2_shutdown_live_check import check as check_shutdown

def check(data,cases):
 result=check_shutdown(data,cases)
 calls,pending,last,maximum,minor=struct.unpack_from('<5q',data,0x60)
 assert minor>=14 and calls>0 and last==1 and 0<=pending<calls,(calls,pending,last,minor)
 result.update(tls_drain_calls=calls,tls_drain_pending=pending,max_drain_us=maximum,abi_minor=minor)
 return result
