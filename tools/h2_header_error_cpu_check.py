"""Check semantic header resets while dependent compressed siblings succeed."""
from h2_stream_window_cpu_check import check as check_stream

def check(data,cases):
 result=check_stream(data,cases)
 result.pop('stream_window_error_isolation',None)
 result.update(header_error_isolation=True,post_error_dynamic_reuse=True)
 return result
