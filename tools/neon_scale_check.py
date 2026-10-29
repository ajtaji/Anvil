"""Numerical vector-scale and dot-product coordinate checks using nonzero terms."""
import struct
from neon_computed_uv_check import check as coordinate_check

def check(report,picture):
 pixels=struct.unpack_from('<9Q',report,16144)
 assert pixels==(0xff0000ff,0xff0000ff,0xff0000ff,0xffff0000,0xffff0000,0xffff0000,0xffff0000,0xffff0000,0xff0000ff),pixels
 clean=bytearray(report);clean[16144:16216]=bytes(72)
 result=coordinate_check(clean,picture)
 result.update(dot_offsets=[0.75,-0.25,0.0],dot_extra_pixels=list(pixels))
 result.pop('offsets')
 return result
