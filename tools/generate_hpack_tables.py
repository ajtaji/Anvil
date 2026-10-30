"""Arrange RFC 7541 Appendix A/B wire constants into original lookup tables.

Pass the normative plain-text RFC as --rfc; no third-party implementation is read.
The resulting table and the bit/hex consistency checks are deterministic.
"""
from pathlib import Path
import re,json,hashlib,argparse
parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--rfc',type=Path,required=True);args=parser.parse_args()
r=Path(__file__).resolve().parents[1]
s=args.rfc.read_text(encoding='utf8')
a=s[s.index('Appendix A.  Static Table Definition',20000):s.index('Appendix B.  Huffman Code',30000)];rows=re.findall(r'^ *\| *(\d+) *\| *([^|\n]+?) *\| *([^|\n]*?) *\|',a,re.M);rows=[(int(i),n.strip(),v.strip()) for i,n,v in rows];assert [i for i,n,v in rows]==list(range(1,62))
codes=re.findall(r'\(\s*(\d+)\)\s+([|01]+)\s+([0-9a-f]+)\s+\[\s*(\d+)\]',s);assert len(codes)==257
nodes=[[None,None]]
for sym,bits,hexd,width in codes:
 bits=bits.replace('|','');assert len(bits)==int(width) and int(bits,2)==int(hexd,16)
 node=0
 for k,ch in enumerate(bits):
  bit=int(ch)
  if k==len(bits)-1:assert nodes[node][bit] is None;nodes[node][bit]=-int(sym)-1
  else:
   if nodes[node][bit] is None:nodes[node][bit]=len(nodes);nodes.append([None,None])
   node=nodes[node][bit];assert node>=0
assert len(nodes)==256 and all(c is not None for n in nodes for c in n)
out='''; RFC 7541 Appendix A/B protocol constants, independently arranged as a trie.
; https://www.rfc-editor.org/rfc/rfc7541.html
; No upstream implementation code. Initialize before starting any connections.
Global Dim hpName.i[62]
Global Dim hpValue.i[62]
Global Dim hpNameLength.i[62]
Global Dim hpValueLength.i[62]
Global Dim hpHuff.i[512]
Global hpTablesReady.i
Procedure HpackTablesInit()
 Define i.i,n.i,p.i
 If hpTablesReady<>0 : ProcedureReturn : EndIf
'''
for i,n,v in rows:out+=f' hpName[{i}]="{n}" : hpValue[{i}]="{v}"\n hpNameLength[{i}]={len(n)} : hpValueLength[{i}]={len(v)}\n'
for i,(left,right) in enumerate(nodes):out+=f' hpHuff[{i*2}]={left} : hpHuff[{i*2+1}]={right}\n'
out+=' hpTablesReady=1\nEndProcedure\n';(r/'Anvil/Network/hpack_tables.pbi').write_text(out,encoding='utf8')
print(json.dumps(dict(rfc_sha256=hashlib.sha256(args.rfc.read_bytes()).hexdigest(),static_entries=61,huffman_codes=257,trie_nodes=256)))
