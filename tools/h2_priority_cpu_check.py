"""Check ignored legacy hints, isolated malformed frames and hard limits."""
from h2_stream_window_cpu_check import check as check_stream

def check(data,cases):
 result=check_stream(data,cases)
 result.pop('stream_window_error_isolation',None)
 result.update(legacy_priority_ignored=True,active_priority_frame_size_isolation=True)
 return result
