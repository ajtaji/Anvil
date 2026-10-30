"""Compile malformed field isolation with post-error HPACK dynamic reuse."""
from pathlib import Path
import argparse,json
from build_h2_client_cpu import build as build_client
from build_h2_stream_window_cpu import transform

def build(compiler,out):
 rows=json.loads((Path(__file__).parent/'h2_header_error_cases.json').read_text())
 return build_client(compiler,out,rows,transform)

if __name__=='__main__':
 ap=argparse.ArgumentParser(description=__doc__)
 ap.add_argument('--compiler',required=True);ap.add_argument('--out',required=True,type=Path)
 a=ap.parse_args();build(a.compiler,a.out.resolve())
