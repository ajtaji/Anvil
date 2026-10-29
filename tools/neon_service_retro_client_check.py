import struct
def check(blob):
 expected=[-21501,-21501,0,0,-21500,0,-21503,0,-21503,-21500,0,0,0,0,1,1,6]
 assert struct.unpack_from('<2q',blob)==(0x4e525431,len(expected))
 actual=struct.unpack_from('<17q',blob,64)
 assert actual==tuple(expected),(actual,expected)
 return dict(checks=len(expected),provider_calls=actual[-1],scope='CPU client transport and capability checks; synthetic provider')
