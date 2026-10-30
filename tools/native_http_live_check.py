import struct
def check(report,cases):
 vals=struct.unpack_from('<4q',report)
 assert vals==(200,20000,20101,0),vals
 assert report[256:856]==bytes(32+i%95 for i in range(600))
 return dict(status=200,bodyBytes=20000,previewVerified=600,received=20101)
