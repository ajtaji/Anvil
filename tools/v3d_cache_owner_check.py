#!/usr/bin/env python3
"""Strict physical report checker for explicit cold-cache ownership."""
import struct
def check(report,picture=None):
    assert len(report)==16384
    q=lambda o:struct.unpack_from('<q',report,o)[0]
    values=[0,0,0,1,0,1,1,1,1,2,3,-1,1,1,0,0,-1,4,1,0,-1,0,4,1,1,1,4,1,0]
    assert q(0)==0x4e434f31 and q(8)==q(32) and q(8)>0 and (q(8)&5)==0
    assert q(16)==0 and q(24)==len(values)
    for i,v in enumerate(values):assert q(256+i*16)==q(264+i*16)==v,(i,q(256+i*16),v)
    original=bytearray(report);original[:40]=bytes(40);original[256:256+len(values)*16]=bytes(len(values)*16)
    assert not any(original)
    return dict(passed=True,checks=len(values),sctlr=hex(q(8)),scope='CPU policy/default/reset/uncached-span and batch refusal behavior; cache-off physical run only')
