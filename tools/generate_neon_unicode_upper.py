#!/usr/bin/env python3
"""Derive default full uppercase data from pinned official Unicode17 inputs."""
from pathlib import Path
import argparse,hashlib,json,unicodedata
PINS={'UnicodeData.txt':'2e1efc1dcb59c575eedf5ccae60f95229f706ee6d031835247d843c11d96470c',
      'SpecialCasing.txt':'efc25faf19de21b92c1194c111c932e03d2a5eaf18194e33f1156e96de4c9588'}
def mappings(unicode_data,special_casing):
 for p,name in [(unicode_data,'UnicodeData.txt'),(special_casing,'SpecialCasing.txt')]:
  assert hashlib.sha256(p.read_bytes()).hexdigest()==PINS[name],('Pinned Unicode17 input mismatch',name)
 table={}
 for line in unicode_data.read_text(encoding='utf8').splitlines():
  f=line.split(';');cp=int(f[0],16)
  if f[12]:table[cp]=(int(f[12],16),)
 for raw in special_casing.read_text(encoding='utf8').splitlines():
  line=raw.split('#',1)[0].strip()
  if not line:continue
  f=[x.strip() for x in line.split(';')]
  if f[4]:continue
  table[int(f[0],16)]=tuple(int(x,16) for x in f[3].split())
 return {cp:value for cp,value in sorted(table.items()) if value!=(cp,)}
def main():
 ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--unicode-data',type=Path,required=True);ap.add_argument('--special-casing',type=Path,required=True);ap.add_argument('--out',type=Path,required=True);a=ap.parse_args()
 table=mappings(a.unicode_data,a.special_casing);rows=[];blob=bytearray();cross=0;new=[]
 for cp,target in table.items():
  raw=''.join(map(chr,target)).encode('utf8');assert raw and b'\0' not in raw
  rows.append((cp,len(blob),len(raw)));blob.extend(raw)
  if unicodedata.category(chr(cp))!='Cn' and all(unicodedata.category(chr(c))!='Cn' for c in target):
   assert chr(cp).upper()==''.join(map(chr,target)),hex(cp);cross+=1
  else:new.append(cp)
 s='''; SPDX-License-Identifier: Unicode-3.0
; Copyright (c) 1991-2026 Unicode, Inc. See licenses/Unicode-Data-V3.txt.
; Source: https://www.unicode.org/Public/17.0.0/ucd/UnicodeData.txt
; Source: https://www.unicode.org/Public/17.0.0/ucd/SpecialCasing.txt
; Derived default full uppercase mappings only; no locale/context tailoring.
; Inputs are pinned by SHA256 in tools/generate_neon_unicode_upper.py.
'''
 s+=f'#NEON_UNICODE_UPPER_COUNT={len(rows)}\n#NEON_UNICODE_UPPER_BYTES={len(blob)}\nDataSection\nnuuRows:\n'
 for cp,offset,size in rows:s+=f' Data.l ${cp:06X},{offset},{size}\n'
 s+='nuuBytes:\n'
 for i in range(0,len(blob),64):s+=' Data.a '+','.join(map(str,blob[i:i+64]))+'\n'
 s+='EndDataSection\n';assert not a.out.exists();a.out.write_text(s,encoding='utf8',newline='\n')
 print(json.dumps(dict(mappings=len(rows),data_bytes=len(blob),host_unicode=unicodedata.unidata_version,independent_host_crosschecks=cross,not_in_host_unicode=[hex(cp) for cp in new],sha256=hashlib.sha256(a.out.read_bytes()).hexdigest()),indent=2))
if __name__=='__main__':main()
